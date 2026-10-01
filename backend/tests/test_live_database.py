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
