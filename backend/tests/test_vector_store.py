import logging
from types import SimpleNamespace

import pytest
from core.vector_store import COLLECTION_CHILD, COLLECTION_PARENT, VectorStore


class StubCollection:
    def __init__(self):
        self.deleted = []
        self.calls = 0
        self.wheres = []

    def delete(self, ids=None, **kwargs):
        self.calls += 1
        self.deleted.extend(ids or [])
        if "where" in kwargs:
            self.wheres.append(kwargs["where"])


@pytest.fixture
def store():
    """绕开 __init__：构造会加载 0.6B embedding 模型，测试里绝不能触发。"""
    vs = VectorStore.__new__(VectorStore)
    vs.parent_vectorstore = StubCollection()
    vs.child_vectorstore = StubCollection()
    return vs


def test_delete_by_ids_targets_the_right_collection(store):
    store.delete_by_ids(["p0", "p1"], ["c0"])
    assert store.parent_vectorstore.deleted == ["p0", "p1"]
    assert store.child_vectorstore.deleted == ["c0"]


def test_delete_with_empty_lists_touches_nothing(store):
    store.delete_by_ids([], [])
    # deleted 只能证明"没删到东西"，无法区分"没调用"和"用空列表调用"；
    # 真正有牙齿的是 calls：移除 if parent_ids:/if child_ids: 守卫会立刻红。
    assert store.parent_vectorstore.calls == 0
    assert store.child_vectorstore.calls == 0
    assert store.parent_vectorstore.deleted == []
    assert store.child_vectorstore.deleted == []


def test_delete_by_document_id_sweeps_both_collections_with_the_metadata_stamp(store):
    """add_documents 在两次写入之前就打好了 document_id 戳，孤儿向量只能按它找回（终审 D2）。"""
    store.delete_by_document_id(42)
    assert store.parent_vectorstore.wheres == [{"document_id": "42"}]
    assert store.child_vectorstore.wheres == [{"document_id": "42"}]
    assert (store.parent_vectorstore.calls, store.child_vectorstore.calls) == (1, 1)


def test_delete_by_document_id_is_best_effort_and_never_raises(store, caplog):
    """清扫失败不外抛（否则补偿链自己变成 500），且第一步炸了也不截断第二步。"""

    class DownCollection(StubCollection):
        def delete(self, ids=None, **kwargs):
            self.calls += 1
            raise RuntimeError("chroma 不可用")

    store.parent_vectorstore = DownCollection()
    with caplog.at_level(logging.ERROR):
        store.delete_by_document_id(7)
    assert store.child_vectorstore.calls == 1
    assert "按 document_id 清扫父集合失败" in caplog.text


def test_delete_by_user_id_sweeps_both_collections_with_the_owner_stamp(store):
    """注销账号找不回 `document_id`：`users` 那一行已经删了，"他名下有哪几篇文档"从此无从问起。
    还剩下的钥匙只有 `add_documents` 盖上的主人戳，所以这里必须按 `user_id` 整片扫。

    `str(user_id)` 与写入侧逐字同形不是洁癖：Chroma 的 where 是标量相等、不做隐式转换，
    传裸 int 不报错，只是**永远匹配不上**——表征是"注销成功但向量还在占盘"，没人会去查。
    """
    store.delete_by_user_id(42)
    assert store.parent_vectorstore.wheres == [{"user_id": "42"}]
    assert store.child_vectorstore.wheres == [{"user_id": "42"}]
    assert (store.parent_vectorstore.calls, store.child_vectorstore.calls) == (1, 1)


def test_delete_by_user_id_is_best_effort_and_never_raises(store, caplog):
    """行已经删干净了，这个账号没法"再注销一次"：这里外抛只会把 204 变成一条谎报的 500。

    父集合炸了也不许截断子集合那一枪（与 `delete_by_document_id` 同一条规矩）——两个集合
    各自独立，漏扫一半比整片没扫更难查。
    """

    class DownCollection(StubCollection):
        def delete(self, ids=None, **kwargs):
            self.calls += 1
            raise RuntimeError("chroma 不可用")

    store.parent_vectorstore = DownCollection()
    with caplog.at_level(logging.ERROR):
        store.delete_by_user_id(7)
    assert store.child_vectorstore.calls == 1
    assert "按 user_id 清扫父集合失败" in caplog.text


def test_add_documents_stamps_the_owner_as_a_string(store):
    """`doc.metadata['user_id'] = str(user_id)` 的本体判据（Task 4 唯一没被任何判据读到的生产语句）。

    `test_chroma_data.py` 里那句 `meta["user_id"] == "1"` 测的是 `migrations.stamp_vector_owner`
    那条补戳路，不是这里。写成 `= user_id`（裸 int）离线判据全绿，但 Chroma 的 where 是标量相等，
    阶段二按主人收窄召回池时这个键永远匹配不上——所以"存成字符串"必须由一条判据钉住。
    走 `VectorStore.__new__`：真构造会开 PersistentClient，`backend/data/chroma_db` 是单实例锁。
    """
    seen = []

    class AddCollection:
        def __init__(self, prefix):
            self.prefix = prefix

        def add_documents(self, docs):
            seen.extend(docs)
            return [f"{self.prefix}{i}" for i in range(len(docs))]

    store.parent_vectorstore = AddCollection("p")
    store.child_vectorstore = AddCollection("c")
    parent = type("D", (), {"page_content": "父", "metadata": {"parent_id": "甲.txt_parent_0"}})()
    child = type("D", (), {"page_content": "子", "metadata": {"parent_id": "甲.txt_parent_0",
                                                              "child_id": "child_0_0"}})()

    parent_ids, child_ids = store.add_documents([parent], [child], 42, user_id=41)

    assert (parent_ids, child_ids) == (["p0"], ["c0"])
    assert seen == [parent, child]        # 两个集合都收到了，戳是在进 Chroma 之前打上的
    for doc in (parent, child):
        assert doc.metadata["user_id"] == "41", f"主人戳必须是字符串：{doc.metadata!r}"
        assert doc.metadata["document_id"] == "42"   # 两个键形态一致（上一行才因此可比）


def test_collection_names_match_existing_chroma(store):
    assert (COLLECTION_PARENT, COLLECTION_CHILD) == ("parent_document", "child_document")


def test_get_parent_documents_dedupes_shared_parent():
    """多个子块同属一个父块时只回溯一次（坑 7 的行为面，本次不优化查询次数，只锁语义）。
    回溯也带主人：parent_id 全库唯一只保证"找得回那一块"，不保证"那块是你的"。"""
    vs = VectorStore.__new__(VectorStore)
    calls = []

    class GetStub:
        def get(self, where=None, include=None):
            assert where == {"$and": [{"parent_id": "a_parent_0"}, {"user_id": "7"}]}, where
            pid = where["$and"][0]["parent_id"]
            calls.append(pid)
            return {"documents": [f"父内容:{pid}"],
                    "metadatas": [{"parent_id": pid}]}

    vs.parent_vectorstore = GetStub()
    children = [
        type("D", (), {"metadata": {"parent_id": "a_parent_0"}})(),
        type("D", (), {"metadata": {"parent_id": "a_parent_0"}})(),
        type("D", (), {"page_content": "", "metadata": {}})(),
    ]
    parents = vs.get_parent_documents(children, 7)
    assert calls == ["a_parent_0"]
    assert len(parents) == 1


def test_retriever_filters_by_pool_and_owner(store):
    """块级允许池 + 主人边界一起下。子块向量两个键都带（add_documents 与迁移补戳），
    所以收窄不需要重新灌库。"""
    store.config = SimpleNamespace(TOP_K=3)
    store.child_vectorstore.as_retriever = lambda search_kwargs: search_kwargs
    kwargs = store.create_retriever(["甲.txt_parent_0"], 7)
    assert kwargs["filter"] == {"$and": [{"parent_id": {"$in": ["甲.txt_parent_0"]}},
                                         {"user_id": {"$in": ["7"]}}]}
    assert kwargs["k"] == 6          # TOP_K * 2 的老规矩没被顺手改掉


def test_retriever_without_pool_still_filters_by_owner(store):
    """空池不等于无边：纯对话链根本不调它，一旦有人调（Task 7 之后可能有），
    漏掉 user_id 就是全库召回。"""
    store.config = SimpleNamespace(TOP_K=3)
    store.child_vectorstore.as_retriever = lambda search_kwargs: search_kwargs
    assert store.create_retriever([], 7)["filter"] == {"user_id": {"$in": ["7"]}}
    assert store.create_retriever(None, 7)["filter"] == {"user_id": {"$in": ["7"]}}


def test_owner_id_is_written_as_a_string_in_the_filter(store):
    """metadata 里存的是字符串（`add_documents:85-86` 与迁移补戳都写 `str(user_id)`）。
    这里传 int 就必须比出字符串：Chroma 的标量相等不做隐式转换，形态一错的表征是
    "永远召回零条"，而不是报错。"""
    store.config = SimpleNamespace(TOP_K=3)
    store.child_vectorstore.as_retriever = lambda search_kwargs: search_kwargs
    assert store.create_retriever([], 41)["filter"]["user_id"] == {"$in": ["41"]}

