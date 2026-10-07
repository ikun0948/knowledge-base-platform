from datetime import datetime

from fastapi.testclient import TestClient

from deps import get_db
from fakes import FakeUser, with_auth
from main import create_app
from schemas.common import Reference

REF = Reference(document_id=1, parent_id="p", filename="a.txt", snippet="片段")


class Row:
    def __init__(self, used_chunks, document_ids=None):
        self.user_message = "问"
        self.assistant_message = "答"
        self.used_chunks = used_chunks
        self.document_ids = document_ids
        self.created_at = datetime(2026, 9, 30, 10, 0)


class HistoryDB:
    def __init__(self, rows):
        self.rows = rows
        self.cleared_with = None
        self.history_calls = []

    def get_chat_history(self, session_id, *, user_id, limit=10):
        self.history_calls.append((session_id, limit, user_id))
        return self.rows

    def delete_chat_history(self, session_id, *, user_id):
        self.cleared_with = (session_id, user_id)
        return 2


def make_client(db, user=None):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    # 端点上了登录门，这批测就得覆盖它；阶段二起 user.id 会被读进两条 SQL
    # （GET 读历史、DELETE 删历史各一处），所以断言现在也钉 user_id 那一格。
    with_auth(app, user or FakeUser())
    return TestClient(app)


def test_one_db_row_expands_into_two_messages():
    db = HistoryDB([Row('[{"document_id":1,"parent_id":"p","filename":"a.txt","snippet":"片段"}]')])
    body = make_client(db).get("/api/history/s1").json()
    assert [m["role"] for m in body] == ["user", "assistant"]
    assert body[0]["references"] is None
    assert body[1]["references"][0]["snippet"] == "片段"


def test_legacy_rows_without_used_chunks_still_load():
    """库里已有行 used_chunks 为 NULL：历史必须能恢复，不能因脏数据 500。"""
    body = make_client(HistoryDB([Row(None)])).get("/api/history/s1").json()
    assert body[1]["references"] == []


def test_corrupt_used_chunks_degrades_to_empty():
    body = make_client(HistoryDB([Row("不是JSON")])).get("/api/history/s1").json()
    assert body[1]["references"] == []


def test_limit_is_capped_at_200():
    assert make_client(HistoryDB([])).get("/api/history/s1?limit=500").status_code == 422


def test_delete_returns_cleared_count():
    db = HistoryDB([])
    body = make_client(db).delete("/api/history/s1").json()
    assert body == {"cleared": 2}
    assert db.cleared_with == ("s1", 1)


def test_every_row_becomes_a_user_then_assistant_pair():
    body = make_client(HistoryDB([Row(None), Row(None)])).get("/api/history/s1").json()
    assert [m["role"] for m in body] == ["user", "assistant", "user", "assistant"]
    assert [m["content"] for m in body] == ["问", "答", "问", "答"]


def test_used_chunks_array_survives_the_round_trip_with_all_reference_fields():
    """历史里的引用必须是 Reference 的四个键（spec 6.3：实时渲染与历史渲染不能分叉）。"""
    body = make_client(HistoryDB([Row(
        '[{"document_id":1,"parent_id":"p","filename":"a.txt","snippet":"片段"}]'
    )])).get("/api/history/s1").json()
    assert body[1]["references"] == [
        {"document_id": 1, "parent_id": "p", "filename": "a.txt", "snippet": "片段"}
    ]


def test_created_at_is_returned_as_iso8601():
    body = make_client(HistoryDB([Row(None)])).get("/api/history/s1").json()
    assert body[0]["created_at"] == "2026-09-30T10:00:00"


def test_session_id_and_limit_are_forwarded_to_the_query():
    """limit 不转发就等于永远只取 DB 默认的 10 行，前端翻页会静默丢历史。"""
    db = HistoryDB([])
    make_client(db).get("/api/history/s42")
    assert db.history_calls == [("s42", 50, 1)]

    db = HistoryDB([])
    make_client(db).get("/api/history/s42?limit=200")
    assert db.history_calls == [("s42", 200, 1)]


def test_limit_below_one_is_422():
    assert make_client(HistoryDB([])).get("/api/history/s1?limit=0").status_code == 422


def test_empty_history_returns_empty_array():
    assert make_client(HistoryDB([])).get("/api/history/nobody").json() == []


# --- mode 派生（阶段二 Task 3，闭合 L-4）---


def test_assistant_mode_is_rag_when_document_ids_present():
    body = make_client(HistoryDB([Row('[]', document_ids="69,71")])).get("/api/history/s1").json()
    assert body[0]["mode"] is None            # user 行永远不带 mode
    assert body[1]["mode"] == "rag"


def test_assistant_mode_is_normal_when_document_ids_missing():
    body = make_client(HistoryDB([Row(None)])).get("/api/history/s1").json()
    assert body[1]["mode"] == "normal"


def test_legacy_rows_read_as_normal_and_load_cleanly():
    """改造前的老行 document_ids 也是 NULL：统一读成 normal。
    把老 rag 轮误标成"自由对话"是可接受的代价——加 mode 列的迁移没有赚头（终审 L-4 裁定路径）。"""
    body = make_client(HistoryDB([Row('[{"document_id":1,"parent_id":"p","filename":"a.txt","snippet":"片"}]')])) \
        .get("/api/history/0a6e5ed2-legacy").json()
    assert body[1]["mode"] == "normal"
    assert body[1]["references"][0]["filename"] == "a.txt"


def test_history_reads_and_deletes_carry_the_logged_in_user_id():
    """登录门只证明"有人"，user.id 才证明"是谁"。这两格漏传一个，
    拿到别人 session_id 的人就能读走整段历史——uuid 难猜不是边界（spec 2.2）。"""
    db = HistoryDB([])
    make_client(db, user=FakeUser(user_id=99)).get("/api/history/s7")
    assert db.history_calls == [("s7", 50, 99)]

    db = HistoryDB([])
    make_client(db, user=FakeUser(user_id=99)).delete("/api/history/s7")
    assert db.cleared_with == ("s7", 99)
