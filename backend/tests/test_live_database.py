"""真 MySQL 上的回归（spec 九节的 live 组）。

`-m "not live"` 会整组跳过：这里的每一条都要连真库，探针数据一律在 finally 里删干净，
所以同一台机器上连跑两遍都绿，也不会把 migration 基线（documents 1 行）带偏。
"""
import json
import time
import uuid
from datetime import datetime, timedelta

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


def probe(db, filename, blocks):
    """造一篇探针文档：blocks 是 {parent_id: 子块数}，返回 doc_id。

    parent_id 由调用方带上本次运行的唯一 tag——这些测试连的是共享真库，
    不加隔离的话断言会吃到基线那 11 个块。调用方负责 finally 里 delete_document。
    """
    doc_id = db.save_document(filename=filename, file_path="", content="正文",
                              chunk_count=sum(blocks.values()))
    parent_docs = [type("D", (), {"page_content": f"{p} 的正文", "metadata": {"parent_id": p}})()
                   for p in blocks]
    child_docs = [
        type("D", (), {"page_content": f"{p} 的子块 {i}",
                       "metadata": {"parent_id": p, "child_id": f"c_{p}_{i}"}})()
        for p, n in blocks.items() for i in range(n)
    ]
    db.save_chunks(doc_id, parent_docs, child_docs,
                   [f"vp_{p}" for p in blocks],
                   [f"vc_{c.metadata['child_id']}" for c in child_docs])
    return doc_id


def new_tag():
    return f"probe{uuid.uuid4().hex[:8]}"


def test_search_parent_chunks_matches_filename_and_content_without_touching_wildcards(db):
    """候选池的 SQL 语义只在真 MySQL 上有牙齿：fake 里没有第二张表，通配符也从不生效。"""
    tag = new_tag()
    doc_a = probe(db, f"{tag}甲.txt", {f"{tag}甲_p_0": 2})
    doc_b = probe(db, f"{tag}乙.pdf", {f"{tag}乙_p_0": 1, f"{tag}乙_p_1": 1})
    try:
        by_filename = db.search_parent_chunks(query=f"{tag}甲")
        assert [r.parent_id for r in by_filename] == [f"{tag}甲_p_0"]
        assert by_filename[0].filename == f"{tag}甲.txt"
        assert by_filename[0].child_count == 2      # GROUP BY 的聚合，不是 documents.chunk_count 那个手写数

        # 只出现在父块正文里的串：证明搜的是 content，不只是文件名
        assert [r.parent_id for r in db.search_parent_chunks(query=f"{tag}乙_p_1")] == [f"{tag}乙_p_1"]
        assert db.search_parent_chunks(query=f"{tag}查无此词") == []

        # 转义的两条活体判据：不转义时 % 会命中这批探针块、_ 会顶掉文件名里那个真实的点
        assert db.search_parent_chunks(query=f"{tag}%") == []
        assert db.search_parent_chunks(query=f"{tag}甲_txt") == []

        assert [r.parent_id for r in db.search_parent_chunks(query=tag, suffix="pdf")] == [
            f"{tag}乙_p_0", f"{tag}乙_p_1"]
        assert [r.parent_id for r in db.search_parent_chunks(query=tag, suffix="txt")] == [f"{tag}甲_p_0"]

        # 排序钉 document_id（创建顺序）：created_at 同批相同，用它排会漂
        assert [r.parent_id for r in db.search_parent_chunks(query=tag)] == [
            f"{tag}甲_p_0", f"{tag}乙_p_0", f"{tag}乙_p_1"]
        assert list(db.search_parent_chunks(query=tag, limit=2)) == list(db.search_parent_chunks(query=tag))[:2]
    finally:
        db.delete_document(doc_a)
        db.delete_document(doc_b)


def test_search_parent_chunks_batch_mode_ignores_query_and_survives_commas_in_ids(db):
    """hydrate 的通路：批量点查优先于 query/suffix/limit，且含逗号的 parent_id 原样往返。

    parent_id 由清洗后的文件名拼出，逗号是合法字符——所以契约用重复键而不是逗号拼接。
    """
    tag = new_tag()
    weird = f"{tag},带逗号.txt"
    doc_a = probe(db, weird, {f"{weird}_p_0": 1})
    doc_b = probe(db, f"{tag}丙.txt", {f"{tag}丙_p_0": 1})
    try:
        rows = db.search_parent_chunks(query="不存在这个词", suffix="pdf",
                                       parent_ids=[f"{weird}_p_0", f"{tag}丙_p_0"])
        assert sorted(r.parent_id for r in rows) == sorted([f"{weird}_p_0", f"{tag}丙_p_0"])
        # 未知 id 静默少返回：前端 hydrate 拿"少返回"当剪死 id 的唯一信号
        assert db.search_parent_chunks(parent_ids=[f"{tag}早就没了_p_9"]) == []
        # 重复入参只出一行（GROUP BY 挡住 fan-out）
        dup = db.search_parent_chunks(parent_ids=[f"{tag}丙_p_0", f"{tag}丙_p_0"])
        assert [r.parent_id for r in dup] == [f"{tag}丙_p_0"]
        # 批量模式不吃 limit：limit=1 仍应把两个 id 都问回来
        assert len(db.search_parent_chunks(parent_ids=[f"{weird}_p_0", f"{tag}丙_p_0"], limit=1)) == 2
    finally:
        db.delete_document(doc_a)
        db.delete_document(doc_b)


def test_search_parent_chunks_excludes_hidden_documents(db):
    """chunk_count 归零而隐存的文档不该再往弹窗里供块——选了也召回不到，是死条目。"""
    tag = new_tag()
    doc_id = probe(db, f"{tag}丁.txt", {f"{tag}丁_p_0": 1, f"{tag}丁_p_1": 1})
    try:
        assert len(db.search_parent_chunks(query=tag)) == 2
        db.delete_parent_chunk(doc_id, f"{tag}丁_p_0")
        assert len(db.search_parent_chunks(query=tag)) == 1
        db.delete_parent_chunk(doc_id, f"{tag}丁_p_1")     # 归零 → is_active=False
        assert db.search_parent_chunks(query=tag) == []
    finally:
        db.delete_document(doc_id)


def test_search_parent_chunks_returns_the_baseline_pool_readable(db):
    """spec 3.4 的基线 smoke：这台机器上候选池有的可返回，且字段齐得够前端渲染。
    钉"非空 + 字段形状"，不钉条数——条数是要随上传变的（migration 门才管那个）。"""
    rows = db.search_parent_chunks(limit=200)
    assert rows, "基线库里应有 11 个父块"
    assert all(r.parent_id and r.filename and r.child_count >= 1 for r in rows)


def test_document_ids_for_parents_reverse_lookup_is_ordered_deduped_and_silent_on_miss(db):
    """历史列仍写 document_ids，靠这一步补齐。fake 给不出"库里真没有这个块"的形状。"""
    tag = new_tag()
    doc_a = probe(db, f"{tag}戊.txt", {f"{tag}戊_p_0": 1, f"{tag}戊_p_1": 1})
    doc_b = probe(db, f"{tag}己.docx", {f"{tag}己_p_0": 1})
    try:
        # 顺序=入参顺序（不是 document_id 顺序）：历史里"用了哪些文档"该保留挑选的叙述顺序
        assert db.document_ids_for_parents([f"{tag}己_p_0", f"{tag}戊_p_1", f"{tag}戊_p_0"]) == [doc_b, doc_a]
        # 同文档的两个块 → 一个 id，落库不出现 "9,9"
        assert db.document_ids_for_parents([f"{tag}戊_p_0", f"{tag}戊_p_1"]) == [doc_a]
        assert db.document_ids_for_parents([f"{tag}没这个块_p_0"]) == []
        assert db.document_ids_for_parents([]) == []
    finally:
        db.delete_document(doc_a)
        db.delete_document(doc_b)


def _drop_probe_account(db, user_id):
    """删掉探针账号：先 auth_tokens 再 users（前者对后者有外键）。

    生产代码里没有 delete_user——Task 2 用不上，为一条测试加一个只给测试用的删除口是 YAGNI，
    所以清理留在测试侧：这两张表没有基线计数钉着，但探针名带 uuid，不清就每轮长一对
    永远没人再查的孤儿行，共享库里攒的是垃圾而不是证据。
    """
    from core.database import AuthToken, User

    session = db.get_session()
    try:
        session.query(AuthToken).filter(AuthToken.user_id == user_id).delete()
        session.query(User).filter(User.id == user_id).delete()
        session.commit()
    finally:
        session.close()


def test_account_methods_round_trip_on_real_mysql(db):
    """join + expires_at 那两条 SQL 语义 fake 给不出证据：这里钉真库上的成功与过期。"""
    from core.security import hash_password, hash_token, new_token

    tag = f"probe-{new_tag()}"
    user = db.create_user(identifier=f"{tag}@local", identifier_type="email",
                          nickname="探针", password_hash=hash_password("probe-pass"))
    token = new_token()
    try:
        db.create_token(user_id=user.id, token_hash=hash_token(token),
                        expires_at=datetime.now() + timedelta(days=1))
        assert db.get_user_by_token(hash_token(token)).id == user.id
        assert db.count_users() >= 1

        expired = f"{tag}-expired"
        db.create_token(user_id=user.id, token_hash=expired,
                        expires_at=datetime.now() - timedelta(seconds=1))
        assert db.get_user_by_token(expired) is None, "过期令牌仍能换回用户：expires_at 那道滤条件没生效"

        assert db.delete_token(hash_token(token)) == 1
        assert db.get_user_by_token(hash_token(token)) is None
        assert db.delete_token(hash_token(token)) == 0, "重复登出不该报第二行"
    finally:
        _drop_probe_account(db, user.id)
    assert db.get_user_by_id(user.id) is None, "探针账号没清干净：共享库残留"


def test_identifier_unique_on_real_mysql(db):
    """`users.identifier` 的 unique 是 DDL 层事实，只有真库能证。"""
    from sqlalchemy.exc import IntegrityError

    from core.security import hash_password

    tag = f"dup-{new_tag()}"
    user = db.create_user(identifier=f"{tag}@local", identifier_type="email",
                          nickname="甲", password_hash=hash_password("probe-pass"))
    try:
        with pytest.raises(IntegrityError):
            db.create_user(identifier=f"{tag}@local", identifier_type="email",
                           nickname="乙", password_hash=hash_password("probe-pass"))
        # 不补一次空 rollback：create_user 自己的 except 已经 rollback、finally 已经 close，
        # 再 get_session() 只会漏一条没人 close 的连接
        assert db.get_user_by_identifier(f"{tag}@local").nickname == "甲", "第二行撞库了？unique 没挡住"
    finally:
        _drop_probe_account(db, user.id)
    assert db.get_user_by_id(user.id) is None
