"""真 MySQL 上的回归（spec 九节的 live 组）。

`-m "not live"` 会整组跳过：这里的每一条都要连真库，探针数据一律在 finally 里删干净，
所以同一台机器上连跑两遍都绿，也不会把 migration 基线（documents 1 行）带偏。
"""
import json
import time
from datetime import timedelta

import pytest
from config.config import Config
from core.database import DatabaseManager
from schemas.common import Reference

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def db():
    """连接探测：没库就 skip 而不是 fail（无 MySQL 的环境也要能收集这一组）。"""
    try:
        return DatabaseManager(Config())
    except Exception as exc:  # create_all 是第一处真连接，连不上就整组跳过
        pytest.skip(f"MySQL 不可用：{type(exc).__name__}: {exc}")


def test_new_rows_get_their_own_timestamp(db):
    """坑 1 的行为面：两条记录的时间戳不应相同（原 default=datetime.now() 会相等）。"""
    first = db.save_document(filename="probe-a.txt", file_path="", content="a", chunk_count=0)
    time.sleep(1.1)
    second = db.save_document(filename="probe-b.txt", file_path="", content="b", chunk_count=0)
    try:
        a, b = db.get_document(first), db.get_document(second)
        assert abs(b.created_at - a.created_at) >= timedelta(seconds=1)
    finally:
        db.delete_document(first)
        db.delete_document(second)


def test_delete_document_cascades_chunks(db):
    """回滚依赖 ORM cascade，这里在真库上验它确实把父子块一起带走。"""
    doc_id = db.save_document(filename="probe-c.txt", file_path="", content="c", chunk_count=0)
    parent = type("D", (), {"page_content": "父", "metadata": {"parent_id": "probe_parent_0"}})
    child = type("D", (), {"page_content": "子",
                           "metadata": {"parent_id": "probe_parent_0", "child_id": "probe_child_0"}})
    db.save_chunks(doc_id, [parent()], [child()], ["vp"], ["vc"])
    try:
        assert db.delete_document(doc_id) == 1
        assert db.get_document(doc_id) is None
    finally:
        db.delete_document(doc_id)


def test_delete_document_reports_missing_rows_as_zero(db):
    """补偿路径按"删了几行"判断幽灵状态，不存在的 id 必须是 0 而不是 None/异常。"""
    missing = db.save_document(filename="probe-x.txt", file_path="", content="x", chunk_count=0)
    assert db.delete_document(missing) == 1
    assert db.delete_document(missing) == 0
    assert db.get_document(missing) is None


def test_get_filenames_by_ids_is_one_in_query(db):
    """Task 6 的 IN 查询此前只在 fake 上跑过：真库里钉住 id→filename、缺行不给 None。"""
    plain = db.save_document(filename="probe-d.txt", file_path="", content="d", chunk_count=0)
    chinese = db.save_document(filename="探针·中文.txt", file_path="", content="e", chunk_count=0)
    try:
        assert db.get_filenames_by_ids([plain, chinese, 10 ** 9]) == {
            plain: "probe-d.txt", chinese: "探针·中文.txt"
        }
        assert db.get_filenames_by_ids([]) == {}
    finally:
        db.delete_document(plain)
        db.delete_document(chinese)


def test_used_chunks_round_trips_through_json(db):
    ref = Reference(document_id=999, parent_id="p", filename="中文名.txt", snippet="含 <script> 的片段")
    db.save_chat_history(session_id="probe-live", user_message="问", assistant_message="答",
                         document_ids="999",
                         used_chunks=json.dumps([ref.model_dump()], ensure_ascii=False))
    db.save_chat_history(session_id="probe-live", user_message="第二问", assistant_message="第二答")
    try:
        rows = db.get_chat_history("probe-live")
        # 旧→新：历史窗口 [-3:] 取的就是这个顺序
        assert [r.user_message for r in rows] == ["问", "第二问"]
        assert Reference(**json.loads(rows[0].used_chunks)[0]) == ref
        assert rows[1].used_chunks is None
        assert db.delete_chat_history("probe-live") == 2
    finally:
        db.delete_chat_history("probe-live")
    assert db.get_chat_history("probe-live") == []


def test_emoji_survives_the_history_round_trip(db):
    """4 字节字符必须写得进、读得出：连接串回退成 `charset=utf8` 时这条会红。

    表是 utf8mb4，但 PyMySQL 按连接串的 charset 协商**会话**字符集——utf8 即 utf8mb3，
    只装得下 3 字节。千问很爱在回答里带 😊，于是 INSERT 撞 MySQL 1366 Incorrect string
    value，整轮历史落不进去：用户先看到答案逐字上屏，接着弹一条"保存对话历史失败"，
    刷新后这一轮凭空消失。2026-10-03 换 flash 模型后第一次真正生成成功才暴露——
    此前全在 LLM 那一步 error，写历史那行从未执行过。
    """
    question = "用一个表情符号跟我打个招呼 😀"
    answer = "你好 😀 😊 ✅ 🚀"  # 中文与 4 字节字符混排
    db.save_chat_history(session_id="probe-emoji", user_message=question,
                         assistant_message=answer)
    try:
        rows = db.get_chat_history("probe-emoji")
        assert [(r.user_message, r.assistant_message) for r in rows] == [(question, answer)]
        assert db.delete_chat_history("probe-emoji") == 1
    finally:
        db.delete_chat_history("probe-emoji")
    assert db.get_chat_history("probe-emoji") == []


def test_deleting_a_parent_chunk_takes_its_children_and_hides_the_document(db):
    """删块这条路在真库上的四条判据，fake 一条都给不出：ORM cascade、重算的计数、归零隐存、联合定位。

    cascade 只在 `session.delete(ORM对象)` 这条路上生效，写成 `delete(synchronize_session=...)`
    的批量删就带不走子行——那种写法在 fake 上照样"过"，因为 fake 根本没有第二张表。
    """
    doc_id = db.save_document(filename="probe-parent.txt", file_path="", content="正文",
                              chunk_count=3)
    parents = [type("D", (), {"page_content": f"父{i}",
                              "metadata": {"parent_id": f"probe_p_{i}"}})() for i in (0, 1)]
    children = [
        type("D", (), {"page_content": "子0", "metadata": {"parent_id": "probe_p_0", "child_id": "probe_c_0"}})(),
        type("D", (), {"page_content": "子1", "metadata": {"parent_id": "probe_p_0", "child_id": "probe_c_1"}})(),
        type("D", (), {"page_content": "子2", "metadata": {"parent_id": "probe_p_1", "child_id": "probe_c_2"}})(),
    ]
    db.save_chunks(doc_id, parents, children, ["vp0", "vp1"], ["vc0", "vc1", "vc2"])
    try:
        plan = db.plan_chunk_deletion(doc_id, "probe_p_0")
        # 向量 id 必须在删行之前交出去，而子块的 vector_id 只能从关系里捞
        assert plan["parent_vector_id"] == "vp0"
        assert sorted(plan["child_vector_ids"]) == ["vc0", "vc1"]

        assert db.delete_parent_chunk(doc_id, "probe_p_0") == {
            "deleted_children": 2, "chunk_count": 1, "document_hidden": False}
        # 重算而非 chunk_count - 2：库里历史漂移时减法会算出负数，重算顺手把它修回来
        assert db.get_document(doc_id).chunk_count == 1
        assert db.get_document(doc_id).is_active is True

        assert db.delete_parent_chunk(doc_id, "probe_p_1") == {
            "deleted_children": 1, "chunk_count": 0, "document_hidden": True}
        assert db.get_document(doc_id).is_active is False
        # 列表与计数都读 is_active：0 块的文档留在列表里是个选了就报错的死条目
        assert doc_id not in [d.id for d in db.get_all_documents()]

        # 联合定位：parent_id 单独不是钥匙——跨文档与已删的都得是 None，端点才能只回一个 404
        assert db.plan_chunk_deletion(doc_id, "probe_p_0") is None
        assert db.plan_chunk_deletion(10 ** 9, "probe_p_1") is None
        assert db.delete_parent_chunk(doc_id, "probe_p_0") is None
    finally:
        db.delete_document(doc_id)
    assert db.get_document(doc_id) is None
