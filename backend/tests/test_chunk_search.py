"""块候选池的三件纯函数 + 端点形状。

SQL 语义（LIKE 转义、child_count 聚合、is_active 排除）fake 给不出证据，
那些判据在 tests/test_live_database.py 的 live 组里。
"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.documents import _suffix_of
from api.documents import router as documents_router
from core.database import _escape_like
from deps import get_db
from fakes import FakeUser, with_auth
from main import create_app
from schemas.common import SNIPPET_LIMIT, snippet_of


def test_snippet_of_collapses_whitespace_then_truncates():
    assert snippet_of("  多 行\n\t文本  ") == "多 行 文本"
    long = "字" * (SNIPPET_LIMIT + 30)
    out = snippet_of(long)
    assert out == "字" * SNIPPET_LIMIT + "..."
    assert len(out) == SNIPPET_LIMIT + 3


def test_snippet_of_leaves_short_text_untouched():
    assert snippet_of("恰好") == "恰好"


def test_escape_like_neutralises_the_three_wildcard_characters():
    # 反斜杠先处理：否则它会把随后补上的转义符再转义一遍
    assert _escape_like("50%") == "50\\%"
    assert _escape_like("a_b") == "a\\_b"
    assert _escape_like("c:\\d") == "c:\\\\d"
    assert _escape_like("普通文件名.pdf") == "普通文件名.pdf"


def test_suffix_of_takes_the_last_dot_and_lowercases():
    assert _suffix_of("手册.PDF") == "pdf"
    assert _suffix_of("a.tar.gz") == "gz"
    assert _suffix_of("README") == ""       # 无后缀不该被当成 "README"
    assert _suffix_of(".env") == "env"      # rpartition：点在最前也算后缀


class ChunkSearchDB:
    """只记录入参、回显预置行：端点的职责是把参数原样交给 db，并把行拼成 ChunkOut。

    user_id 与那四个查询参数记在同一格里——它就是"原样交给 db"的那件新东西。
    """

    def __init__(self, rows=()):
        self.rows = list(rows)
        self.calls = []

    def search_parent_chunks(self, *, user_id=None, query="", suffix="", parent_ids=(), limit=50):
        self.calls.append({"user_id": user_id, "query": query, "suffix": suffix,
                           "parent_ids": list(parent_ids), "limit": limit})
        return self.rows


def row(parent_id="a.txt_parent_0", document_id=3, filename="a.txt", content="父 块 内容"):
    return SimpleNamespace(parent_id=parent_id, document_id=document_id,
                           content=content, filename=filename, child_count=2)


def make_client(db):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    with_auth(app, FakeUser(user_id=9))
    return TestClient(app)


def test_chunks_endpoint_forwards_defaults_and_returns_chunk_shape():
    db = ChunkSearchDB([row(content="x" * 200)])
    body = make_client(db).get("/api/documents/chunks").json()
    assert db.calls == [{"user_id": 9, "query": "", "suffix": "", "parent_ids": [], "limit": 50}]
    assert len(body) == 1
    out = body[0]
    assert out["parent_id"] == "a.txt_parent_0"
    assert out["document_id"] == 3
    assert out["suffix"] == "txt"          # 从 filename 现推，不信前端传来的值
    assert out["child_count"] == 2
    assert out["snippet"] == "x" * 80 + "..."   # 与引用片段同一把尺子


def test_chunks_endpoint_passes_query_and_suffix_through():
    db = ChunkSearchDB()
    make_client(db).get("/api/documents/chunks", params={"query": "手册", "suffix": "pdf", "limit": 7}).json()
    assert db.calls[0] == {"user_id": 9, "query": "手册", "suffix": "pdf", "parent_ids": [], "limit": 7}


def test_chunks_endpoint_dedupes_parent_ids_but_keeps_order():
    db = ChunkSearchDB()
    make_client(db).get("/api/documents/chunks",
                        params=[("parent_ids", "b_p_0"), ("parent_ids", "a_p_0"),
                                ("parent_ids", "b_p_0")]).json()
    assert db.calls[0]["parent_ids"] == ["b_p_0", "a_p_0"]
    # 批量模式下 limit 让位，由 db 侧实现；这里只钉端点没把重复项喂进去
    assert db.calls[0]["limit"] == 50


@pytest.mark.parametrize("params,field", [
    ({"suffix": "exe"}, "suffix"),
    ({"limit": 0}, "limit"),
    ({"limit": 201}, "limit"),
    ({"query": "过" * 101}, "query"),
    ({"parent_ids": ""}, "parent_ids"),
    ({"parent_ids": "x" * 101}, "parent_ids"),
    ({"parent_ids": [f"p{i}" for i in range(51)]}, "parent_ids"),
])
def test_chunks_endpoint_rejects_bad_params_with_422(params, field):
    res = make_client(ChunkSearchDB()).get("/api/documents/chunks", params=params)
    assert res.status_code == 422
    assert any(field in str(item) for item in res.json()["detail"])


def test_chunks_route_wins_over_a_future_path_param_route():
    """FastAPI 按注册顺序匹配，/chunks 必须排在任何 /{...} 动态路由之前。

    今天 GET /{document_id} 还不存在，这条钉的是"将来加它时别插到 /chunks 前面"——
    写反了 /chunks 就变成文档不存在那个 404。
    读 documents_router.routes 而不是 app.routes：这个 FastAPI 版本把 include_router
    记成没有 .path 的 _IncludedRouter，展开后的顺序拿不到。
    """
    paths = [r.path for r in documents_router.routes]
    assert "/api/documents/chunks" in paths
    chunk_index = paths.index("/api/documents/chunks")
    assert all(chunk_index < paths.index(p) for p in paths if "{" in p)
