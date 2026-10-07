"""归属的服务端一侧（spec 3.3）。

离线判据只能证两件事：**端点把 user.id 传下去了**、**越权拿到 404**。
"甲的列表里没有乙的文档"这种真过滤 fake 演不出来，归 live 组（Step 8）。
"""
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from deps import (get_config, get_current_user, get_db, get_doc_processor,
                  get_rag_system, get_vector_store)
from fakes import (FakeConfig, FakeDocProcessor, FakeRAG, FakeUser,
                   FakeVectorStore, with_auth)
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
        # 人人都有的这一枚，只为让 Task 7 的名单门禁放行——越权那两枪必须红在 404
        self.user_models = [("fake-model", True)]

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

    def list_user_models(self, user_id):
        """Task 7 的门禁在查白名单**之前**读名单，缺这格时两条越权判据会红在 409 而不是 404。

        名单内容与归属无关（人人都有这一枚），所以不记进 self.calls——那份是逐字比较的。
        """
        return list(self.user_models)

    def get_chat_history(self, session_id, *, user_id, limit=10):
        return []

    def delete_chat_history(self, session_id, *, user_id):
        return 0

    def count_documents(self):
        """/api/health 读的是这一格（main.py:85-96），不是 get_all_documents(user_id=...)。

        Task 4 有意把 count_documents 留在"不加归属"那一侧（它是运维探针的总量口径），
        这里就得有它——否则 test_health_stays_open 红在 AttributeError，
        测的不再是"health 没上门"而是"假库缺一格"。
        """
        return len(self.rows)

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


def make_isolation_client(db=None, user=FakeUser(user_id=OWNER), rag=None, gate=True):
    """隔离判据的公共装配：documents 与 chat/history 与 health 三组路径共用一套替身。

    Task 5 起它多覆盖两格：get_rag_system（问答端点的第一个依赖，缺它 chat 那两条
    越权判据红在 app.state 上而不是红在白名单上）与 get_config（/api/health 要读
    CHROMA_PERSIST_DIR）。缺省 db 用会过滤的 OwnerAwareDB，缺省 rag 用 FakeRAG。
    """
    app = create_app()
    store = StampingVectorStore()
    db = db or OwnerAwareDB()
    rag = rag or FakeRAG()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_doc_processor] = lambda: FakeDocProcessor()
    app.dependency_overrides[get_vector_store] = lambda: store
    app.dependency_overrides[get_rag_system] = lambda: rag
    app.dependency_overrides[get_config] = lambda: FakeConfig()
    # gate=False 时不覆盖 get_current_user——真依赖会去库里查令牌，这就是 401 判据的走法
    if gate:
        with_auth(app, user)
    return TestClient(app), store


def test_upload_stamps_the_owner_in_database_and_vectors():
    db = OwnerAwareDB()
    client, store = make_isolation_client(db)
    res = client.post("/api/documents", files={"file": ("甲.txt", "正文".encode("utf-8"), "text/plain")})
    assert res.status_code == 201
    assert ("save_document", OWNER) in db.calls
    assert store.stamped_with == [OWNER]


def test_list_and_chunks_forward_the_owner():
    db = OwnerAwareDB()
    client, _ = make_isolation_client(db, user=FakeUser(user_id=OWNER))
    assert client.get("/api/documents").status_code == 200
    assert client.get("/api/documents/chunks").status_code == 200
    assert ("get_all_documents", OWNER) in db.calls
    assert ("search_parent_chunks", OWNER) in db.calls

    other = OwnerAwareDB()
    client2, _ = make_isolation_client(other, user=FakeUser(user_id=INTRUDER))
    assert client2.get("/api/documents").json() == []
    assert client2.get("/api/documents/chunks").json() == []


def test_deleting_another_users_chunk_is_404_with_the_existing_line():
    """越权与不存在共用一句文案：区分它们等于承认"这块存在"。"""
    db = OwnerAwareDB()
    client, _ = make_isolation_client(db, user=FakeUser(user_id=INTRUDER))
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
    client, store = make_isolation_client(db, user=FakeUser(user_id=OWNER))

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


BUSINESS_ENDPOINTS = [
    ("post", "/api/documents"),
    ("get", "/api/documents"),
    ("get", "/api/documents/chunks"),
    ("delete", "/api/documents/7/chunks/x_parent_0"),
    ("post", "/api/chat"),
    ("post", "/api/chat/stream"),
    ("get", "/api/history/some-session"),
    ("delete", "/api/history/some-session"),
]


@pytest.mark.parametrize("method,path", BUSINESS_ENDPOINTS,
                         ids=[f"{m}-{p}" for m, p in BUSINESS_ENDPOINTS])
def test_every_business_endpoint_rejects_a_missing_token(method, path):
    """八条一个不漏：这条参数化就是 spec 3.2 那张清单的自动化形态。

    漏一条门的表现是"未登录也能查别人的历史"，而它不会让任何一条现有测变红——
    所以这里必须按清单数，不能按"改了几个文件"数。
    """
    client, _ = make_isolation_client(gate=False)
    # 这一行是本条判据的牙齿：覆盖没撤干净，测的就是替身而不是那扇真门
    assert get_current_user not in client.app.dependency_overrides
    payload = {"session_id": "s1", "question": "q"} if method == "post" else None
    # 计划的 getattr(client, method)(path, json=...) 对 8 条臂里的 5 条当场 TypeError：
    # inspect.signature 实测 httpx.Client 只有 post/put/patch/request 收 json=，**get 与 delete 都不收**，
    # 而这份清单是 3 条 GET + 2 条 DELETE + 3 条 POST ⇒ 5 条臂走不通。request() 八个动词同一条路。
    res = client.request(method.upper(), path, json=payload)
    assert res.status_code == 401, f"{method.upper()} {path} 没上门"
    assert res.json() == {"detail": "未登录或登录已过期"}


def test_health_stays_open():
    """/api/health 是运维探针，spec 3.2 明写不上门。

    这条判据的两格牙：health 一旦被人误上门 → 401 当场红；`make_isolation_client`
    覆盖的 get_config / get_db / get_vector_store 三格少一格 → AttributeError → 500 红。
    所以这里是硬断言 200，不是"只要不是 401 就行"。

    它**不**校验健康检查里的数字：本条走的是替身，`OwnerAwareDB.count_documents()` 恒回
    `len(self.rows)`=1（见上面那格）、`FakeVectorStore.collection_counts()` 恒回
    `{"parent": 2, "child": 7}`（tests/fakes.py）。活文档 4 / 父块 4 / 子块 10 那条基线计数
    的常驻入口是 `tests/test_chroma_data.py`——注意它两条都在 `migration` 组里，默认门
    （`addopts = -m "not migration"`）不跑它，要显式 `-m migration` 且它会打开真 Chroma。
    """
    client, _ = make_isolation_client(gate=False)
    assert client.get("/api/health").status_code == 200


def test_asking_with_a_foreign_parent_id_is_404():
    db = OwnerAwareDB()
    client, _ = make_isolation_client(db, user=FakeUser(user_id=INTRUDER))
    res = client.post("/api/chat", json={
        "session_id": "s1", "question": "q", "parent_ids": ["甲.txt_parent_0"]})
    assert res.status_code == 404
    assert res.json() == {"detail": "文档块不存在或已被删除"}
    # 状态码 + 文案还不够：模块 docstring 主张"钉的是端点把 user.id 传下去了"，
    # 所以这里也得像上面 documents 越权那条一样断言转发本身（评审 Minor 5）。
    assert ("owned_parent_ids", INTRUDER) in db.calls


def test_stream_endpoint_refuses_a_foreign_parent_id_before_the_first_frame():
    """流式端点必须在 meta 帧**之前**拒：一旦发出 200，HTTP 语义就让位给流协议了。

    这条判据的形状（404 + JSON detail，而不是 error 帧）就是"检查放在 StreamingResponse
    构造之前"的唯一证据——放错位置照样"能跑"，只是没人能从状态码看出来。
    """
    db = OwnerAwareDB()
    client, _ = make_isolation_client(db, user=FakeUser(user_id=INTRUDER))
    res = client.post("/api/chat/stream", json={
        "session_id": "s1", "question": "q", "parent_ids": ["甲.txt_parent_0"]})
    assert res.status_code == 404
    assert res.json() == {"detail": "文档块不存在或已被删除"}
    assert ("owned_parent_ids", INTRUDER) in db.calls


def test_owner_asking_the_same_chunk_twice_in_one_question_is_not_a_404():
    """一次提问里同一个块出现两次是合法入参：比较式**两侧**都得按去重后的长度算。

    `api/chat.py` 那句 `len(owned) != len(list(dict.fromkeys(parent_ids)))` 若把右边写成
    `len(parent_ids)`（不去重），`owned_parent_ids` 按入参去重只回 1 个、右边数出 2 个，
    "同一个人问同一个块两次"就会被误判 404——而本文件其余各条传的都是不重复的池，
    全套判据一条都不红（评审 Minor 7，与 Task 4 的 F11 同一类）。

    这条钉的是**去重口径**，不是"有没有这道检查"：把那个 `if` 整块删掉它照样绿，
    变红的是上面两条越权判据。
    """
    db = OwnerAwareDB()
    client, _ = make_isolation_client(db, user=FakeUser(user_id=OWNER))
    res = client.post("/api/chat", json={
        "session_id": "s1", "question": "q",
        "parent_ids": ["甲.txt_parent_0", "甲.txt_parent_0"]})
    assert res.status_code == 200, res.text
    assert res.json()["mode"] == "rag"
