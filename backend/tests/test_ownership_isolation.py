"""归属的服务端一侧（spec 3.3）。

离线判据只能证两件事：**端点把 user.id 传下去了**、**越权拿到 404**。
"甲的列表里没有乙的文档"这种真过滤 fake 演不出来，归 live 组（Step 8）。
"""
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from deps import get_current_user, get_db, get_doc_processor, get_vector_store
from fakes import FakeDocProcessor, FakeUser, FakeVectorStore, with_auth
from main import create_app

# 刻意不取 1：fakes.FakeUser 的默认 user_id 就是 1，撞上了端点里硬编码 user_id=1
# 也能通过全部离线判据（评审 F12）。这两个数还彼此不同，越权那一臂才是真越权。
OWNER = 41
INTRUDER = 42


class OwnerAwareDB:
    """假库只做两件事：记下每次调用收到的 user_id，以及**按它过滤**。

    记下参数才能钉住"端点没漏传"；按它过滤才能钉住"漏传之后行为会怎么变"——
    两个都是判据，缺一个就会留下一类静默越权。
    """

    def __init__(self):
        self.calls = []                       # [(方法名, user_id)]
        self.doc_owner = OWNER
        self.rows = [SimpleNamespace(id=7, filename="甲.txt", chunk_count=1,
                                     created_at=datetime(2026, 10, 6))]

    def _record(self, name, user_id):
        self.calls.append((name, user_id))
        return user_id == self.doc_owner

    def save_document(self, filename, file_path, content, chunk_count=0, *, user_id):
        self._record("save_document", user_id)
        return 7

    def save_chunks(self, doc_id, parent_docs, child_docs, parent_vector_ids, child_vector_ids):
        pass

    def get_document(self, doc_id, *, user_id):
        if not self._record("get_document", user_id):
            return None
        return self.rows[0]

    def get_all_documents(self, *, user_id):
        self._record("get_all_documents", user_id)
        return list(self.rows) if user_id == self.doc_owner else []

    def search_parent_chunks(self, *, user_id, query="", suffix="", parent_ids=(), limit=50):
        self._record("search_parent_chunks", user_id)
        if user_id != self.doc_owner:
            return []
        return [SimpleNamespace(parent_id="甲.txt_parent_0", document_id=7,
                                content="正文", filename="甲.txt", child_count=2)]

    def plan_chunk_deletion(self, document_id, parent_id, *, user_id):
        if not self._record("plan_chunk_deletion", user_id):
            return None
        return {"document_id": document_id, "parent_id": parent_id,
                "parent_vector_id": "pv", "child_vector_ids": ["cv"]}

    def delete_parent_chunk(self, document_id, parent_id, *, user_id):
        # 与非变更方法同形：真库这一步也是"按 (document_id, parent_id, 主人) 联合定位，
        # 查不到就回 None"（core/database.py 的 _find_parent_chunk）。假库若在唯一那个
        # 变更方法上丢了过滤，别人来删就看不出差别了。
        if not self._record("delete_parent_chunk", user_id):
            return None
        return {"deleted_children": 1, "chunk_count": 0, "document_hidden": True}

    def owned_parent_ids(self, parent_ids, *, user_id):
        """Task 5 的问答白名单靠它：不是你的块就不出现在返回值里。

        口径与真库上那个方法逐字一致——按入参去重、别人的静默少回。
        """
        if not self._record("owned_parent_ids", user_id):
            return []
        return [pid for pid in dict.fromkeys(parent_ids) if pid == "甲.txt_parent_0"]

    def get_chat_history(self, session_id, limit=10):
        return []

    def delete_chat_history(self, session_id):
        return 0

    def get_user_by_token(self, token_hash):
        """gate=False 那一臂走真依赖时，它第一个碰库的就是这一格。

        Python 先解析 `db.get_user_by_token` 这个属性、再算实参，所以替身缺这一格时，
        "没带令牌"的判据炸的是 AttributeError（→500）而不是 bearer_token 的 AuthError（→401）：
        真库有这个方法，替身就得有，缺它测的就不再是那扇门。本条判据里它恒不被调用——
        没有 Authorization 头时 `bearer_token` 在实参那一层就抛了。
        """
        return None

    def delete_document(self, doc_id):
        return 1


class StampingVectorStore(FakeVectorStore):
    def __init__(self):
        super().__init__()
        self.stamped_with = []

    def add_documents(self, parent_docs, child_docs, document_id, *, user_id):
        self.stamped_with.append(user_id)
        # 把 user_id 传下去：不传的话基类 fakes.py 里那句 self.stamped_user = user_id
        # 恒为 None，成了"写了没人读"的误导字段（形状照 test_api_documents.py 的 RecordingVectorStore）。
        return super().add_documents(parent_docs, child_docs, document_id, user_id=user_id)


def make_client(db, user=FakeUser(user_id=OWNER), vector_store=None, gate=True):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_doc_processor] = lambda: FakeDocProcessor()
    store = vector_store or StampingVectorStore()
    app.dependency_overrides[get_vector_store] = lambda: store
    # gate=False 时不覆盖 get_current_user——真依赖会去库里查令牌，这就是 401 判据的走法
    if gate:
        with_auth(app, user)
    return TestClient(app), store


def test_upload_stamps_the_owner_in_database_and_vectors():
    db = OwnerAwareDB()
    client, store = make_client(db)
    res = client.post("/api/documents", files={"file": ("甲.txt", "正文".encode("utf-8"), "text/plain")})
    assert res.status_code == 201
    assert ("save_document", OWNER) in db.calls
    assert store.stamped_with == [OWNER]


def test_list_and_chunks_forward_the_owner():
    db = OwnerAwareDB()
    client, _ = make_client(db, user=FakeUser(user_id=OWNER))
    assert client.get("/api/documents").status_code == 200
    assert client.get("/api/documents/chunks").status_code == 200
    assert ("get_all_documents", OWNER) in db.calls
    assert ("search_parent_chunks", OWNER) in db.calls

    other = OwnerAwareDB()
    client2, _ = make_client(other, user=FakeUser(user_id=INTRUDER))
    assert client2.get("/api/documents").json() == []
    assert client2.get("/api/documents/chunks").json() == []


def test_deleting_another_users_chunk_is_404_with_the_existing_line():
    """越权与不存在共用一句文案：区分它们等于承认"这块存在"。"""
    db = OwnerAwareDB()
    client, _ = make_client(db, user=FakeUser(user_id=INTRUDER))
    res = client.delete("/api/documents/7/chunks/甲.txt_parent_0")
    assert res.status_code == 404
    assert res.json() == {"detail": "文档块不存在或已被删除"}
    assert ("plan_chunk_deletion", INTRUDER) in db.calls
    # 404 来自 plan 返回 None，端点在 api/documents.py 那道 raise 就停了：
    # 变更方法一次都没被调用。假库的 delete_parent_chunk 会过滤（评审 F14），
    # 但这条判据的红必须仍然来自 plan 那一颗牙，不是这里。
    assert not [name for name, _ in db.calls if name == "delete_parent_chunk"]


def test_owner_deleting_a_chunk_forwards_the_owner_to_both_remaining_callsites():
    """成功删除那条路上最后两个归属调用点：api/documents.py 的 delete_parent_chunk 与 get_document。

    补这条之前，把这两行的 `user_id=user.id` 删掉，全套 246 条一条都不红——
    越权那条判据在 plan 那步就 404 了，永远走不到这里；而 test_api_documents.py 的
    ChunkDB 收了 `user_id=None` 却从不读它。这正好打在 Task 4 的主张上：
    归属参数是必填关键字参数，忘了传就该当场 TypeError，而不是静默少一道主人。
    """
    db = OwnerAwareDB()
    client, store = make_client(db, user=FakeUser(user_id=OWNER))

    res = client.delete("/api/documents/7/chunks/甲.txt_parent_0")

    assert res.status_code == 200, res.text
    assert ("plan_chunk_deletion", OWNER) in db.calls
    assert ("delete_parent_chunk", OWNER) in db.calls
    assert ("get_document", OWNER) in db.calls
    # 顺序契约：向量先清、行后删（见端点 docstring）
    assert store.deleted == [(["pv"], ["cv"])]
    # 出参契约不变：DocumentOut，且那行读的是按主人过滤后的 get_document
    assert res.json() == {"id": 7, "filename": "甲.txt", "chunk_count": 1,
                          "created_at": "2026-10-06T00:00:00"}


@pytest.mark.parametrize("method,path", [
    ("post", "/api/documents"),
    ("get", "/api/documents"),
    ("get", "/api/documents/chunks"),
    ("delete", "/api/documents/7/chunks/x_parent_0"),
])
def test_documents_endpoints_reject_a_missing_token(method, path):
    """spec 3.2 那张清单的前四条。Task 5 会把 chat/history 那四条并进来。"""
    client, _ = make_client(OwnerAwareDB(), gate=False)
    # 这一行是本条判据的牙齿：覆盖没撤干净，测的就是替身而不是那扇真门
    assert get_current_user not in client.app.dependency_overrides
    res = getattr(client, method)(path)
    assert res.status_code == 401
    assert res.json() == {"detail": "未登录或登录已过期"}
