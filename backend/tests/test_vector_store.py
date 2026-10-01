import pytest
from core.vector_store import COLLECTION_CHILD, COLLECTION_PARENT, VectorStore


class StubCollection:
    def __init__(self):
        self.deleted = []

    def delete(self, ids=None, **kwargs):
        self.deleted.extend(ids or [])


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
    assert store.parent_vectorstore.deleted == []
    assert store.child_vectorstore.deleted == []


def test_collection_names_match_existing_chroma(store):
    assert (COLLECTION_PARENT, COLLECTION_CHILD) == ("parent_document", "child_document")


def test_get_parent_documents_dedupes_shared_parent():
    """多个子块同属一个父块时只回溯一次（坑 7 的行为面，本次不优化查询次数，只锁语义）。"""
    vs = VectorStore.__new__(VectorStore)
    calls = []

    class GetStub:
        def get(self, where=None, include=None):
            calls.append(where["parent_id"])
            return {"documents": [f"父内容:{where['parent_id']}"], "metadatas": [{"parent_id": where["parent_id"]}]}

    vs.parent_vectorstore = GetStub()
    children = [
        type("D", (), {"metadata": {"parent_id": "a_parent_0"}})(),
        type("D", (), {"metadata": {"parent_id": "a_parent_0"}})(),
        type("D", (), {"page_content": "", "metadata": {}})(),
    ]
    parents = vs.get_parent_documents(children)
    assert calls == ["a_parent_0"]
    assert len(parents) == 1
