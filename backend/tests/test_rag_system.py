import json
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableLambda

from core.rag_system import RAGSystem
from exceptions import LLMError, RetrievalError
from schemas.common import Reference, SNIPPET_LIMIT


def chat(user, assistant):
    return SimpleNamespace(user_message=user, assistant_message=assistant)


class StubDb:
    """只记录 save_chat_history 的 kwargs，绝不碰真 MySQL（ruling 5）。"""

    def __init__(self, history=(), filenames=None):
        self.history = list(history)
        self.filenames = filenames or {}
        self.saved = []

    def get_chat_history(self, session_id, limit=10):
        return self.history

    def get_filenames_by_ids(self, doc_ids):
        return {i: self.filenames.get(i, "") for i in doc_ids}

    def save_chat_history(self, **kwargs):
        self.saved.append(kwargs)


class StubVectorStore:
    def __init__(self, parent_docs, compressed=None, retriever_error=None):
        self.parent_docs = parent_docs
        self.retriever_error = retriever_error
        self.compressor = SimpleNamespace(
            compress_documents=lambda docs, q: (compressed if compressed is not None else docs)
        )

    def create_retriever(self, document_ids):
        if self.retriever_error:
            raise self.retriever_error
        return SimpleNamespace(invoke=lambda q: ["child"])

    def get_parent_documents(self, retrieved):
        return self.parent_docs


def build(db, vs, llm):
    """绕开 __init__：真构造会建 ChatOpenAI 客户端。"""
    rag = RAGSystem.__new__(RAGSystem)
    rag.db_manager = db
    rag.vector_store = vs
    rag.llm = llm
    rag.rag_prompt = ChatPromptTemplate.from_messages([
        ("system", "上下文信息:\n{context}"),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{question}"),
    ])
    return rag


def ok_llm(answer="模型回答"):
    return RunnableLambda(lambda _: SimpleNamespace(content=answer))


def boom_llm(_):
    raise RuntimeError("模型挂了")


def parent(doc_id=7, parent_id="p0", content="父 块 内容"):
    return Document(page_content=content, metadata={"document_id": str(doc_id), "parent_id": parent_id})


# --- normal_chat ---

def test_normal_chat_returns_answer_and_saves_plain_history():
    db = StubDb(history=[chat("旧问", "旧答")])
    rag = build(db, StubVectorStore([]), ok_llm("普通回答"))
    answer = rag.normal_chat("你好", "s1")
    assert answer == "普通回答"
    assert db.saved == [{"session_id": "s1", "user_message": "你好", "assistant_message": "普通回答"}]


def test_normal_chat_llm_failure_raises_instead_of_polluting_history():
    db = StubDb()
    rag = build(db, StubVectorStore([]), RunnableLambda(boom_llm))
    with pytest.raises(LLMError):
        rag.normal_chat("你好", "s1")
    assert db.saved == []


# --- chat_with_documents ---

def test_chat_returns_references_and_writes_used_chunks():
    db = StubDb(filenames={7: "操作手册.txt"})
    vs = StubVectorStore(parent_docs=[parent()])
    rag = build(db, vs, ok_llm("带引用的回答"))
    answer, refs = rag.chat_with_documents("父子索引是什么", [7], "s1")

    assert answer == "带引用的回答"
    assert refs == [Reference(document_id=7, parent_id="p0", filename="操作手册.txt", snippet="父 块 内容")]

    saved = db.saved[0]
    assert saved["document_ids"] == "7"
    # Step 7 期望的形状：以 [{"document_id" 开头、中文可读（ensure_ascii=False）
    assert saved["used_chunks"].startswith('[{"document_id"')
    assert "操作手册.txt" in saved["used_chunks"]
    # 历史渲染 == 实时渲染（spec 6.3 / ruling 2）
    assert saved["used_chunks"] == json.dumps([r.model_dump() for r in refs], ensure_ascii=False)
    assert [Reference(**i) for i in json.loads(saved["used_chunks"])] == refs


def test_chat_snippet_collapses_whitespace_and_truncates_at_limit():
    # 折叠：多空格 / 换行 / 制表符归一为单空格
    db = StubDb(filenames={3: "a.txt"})
    vs = StubVectorStore(parent_docs=[parent(doc_id=3, content="父  块\n\t内容")])
    _, refs = build(db, vs, ok_llm()).chat_with_documents("q", [3], "s")
    assert refs[0].snippet == "父 块 内容"

    # 截断：超长片段留 SNIPPET_LIMIT 字符 + 省略号
    long_text = "字" * (SNIPPET_LIMIT + 30)
    db2 = StubDb(filenames={4: "b.txt"})
    vs2 = StubVectorStore(parent_docs=[parent(doc_id=4, content="  " + long_text + "\n")])
    _, refs2 = build(db2, vs2, ok_llm()).chat_with_documents("q", [4], "s")
    assert refs2[0].snippet == long_text[:SNIPPET_LIMIT] + "..."
    assert len(refs2[0].snippet) == SNIPPET_LIMIT + 3


def test_chat_empty_retrieval_is_business_result_not_history():
    db = StubDb()
    rag = build(db, StubVectorStore(parent_docs=[]), ok_llm())
    answer, refs = rag.chat_with_documents("无关问题", [7], "s1")
    assert refs == []
    assert "未在选中的文档里找到" in answer
    assert db.saved == []


def test_chat_retrieval_failure_raises_not_swallowed():
    db = StubDb()
    rag = build(db, StubVectorStore(parent_docs=[], retriever_error=RuntimeError("chroma down")), ok_llm())
    with pytest.raises(RetrievalError):
        rag.chat_with_documents("q", [7], "s1")
    assert db.saved == []


def test_chat_llm_failure_raises_not_swallowed():
    db = StubDb()
    rag = build(db, StubVectorStore(parent_docs=[parent()]), RunnableLambda(boom_llm))
    with pytest.raises(LLMError):
        rag.chat_with_documents("q", [7], "s1")
    assert db.saved == []
