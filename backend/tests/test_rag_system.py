import json
import logging
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableGenerator, RunnableLambda

from core.rag_system import RAGSystem
from exceptions import LLMError, RetrievalError
from schemas.common import Reference, SNIPPET_LIMIT


def chat(user, assistant):
    return SimpleNamespace(user_message=user, assistant_message=assistant)


class StubDb:
    """只记录 save_chat_history 的 kwargs，绝不碰真 MySQL（ruling 5）。"""

    def __init__(self, history=(), filenames=None, parents=None):
        self.history = list(history)
        self.filenames = filenames or {}
        # parent_id -> document_id：反查表，缺键即"这个块已经不在库里了"
        self.parents = parents or {}
        self.saved = []

    def get_chat_history(self, session_id, limit=10):
        return self.history

    def get_filenames_by_ids(self, doc_ids):
        return {i: self.filenames.get(i, "") for i in doc_ids}

    def document_ids_for_parents(self, parent_ids):
        self.reverse_calls = list(parent_ids)
        out = []
        for pid in parent_ids:
            doc_id = self.parents.get(pid)
            if doc_id is not None and doc_id not in out:
                out.append(doc_id)
        return out

    def save_chat_history(self, **kwargs):
        self.saved.append(kwargs)


class StubVectorStore:
    def __init__(self, parent_docs, compressed=None, retriever_error=None):
        self.parent_docs = parent_docs
        self.retriever_error = retriever_error
        self.compressor = SimpleNamespace(
            compress_documents=lambda docs, q: (compressed if compressed is not None else docs)
        )

    def create_retriever(self, parent_ids):
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
    db = StubDb(filenames={7: "操作手册.txt"}, parents={"p0": 7})
    vs = StubVectorStore(parent_docs=[parent()])
    rag = build(db, vs, ok_llm("带引用的回答"))
    answer, refs = rag.chat_with_documents("父子索引是什么", ["p0"], "s1")

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
    db = StubDb(filenames={3: "a.txt"}, parents={"p0": 3})
    vs = StubVectorStore(parent_docs=[parent(doc_id=3, content="父  块\n\t内容")])
    _, refs = build(db, vs, ok_llm()).chat_with_documents("q", ["p0"], "s")
    assert refs[0].snippet == "父 块 内容"

    # 截断：超长片段留 SNIPPET_LIMIT 字符 + 省略号
    long_text = "字" * (SNIPPET_LIMIT + 30)
    db2 = StubDb(filenames={4: "b.txt"}, parents={"p0": 4})
    vs2 = StubVectorStore(parent_docs=[parent(doc_id=4, content="  " + long_text + "\n")])
    _, refs2 = build(db2, vs2, ok_llm()).chat_with_documents("q", ["p0"], "s")
    assert refs2[0].snippet == long_text[:SNIPPET_LIMIT] + "..."
    assert len(refs2[0].snippet) == SNIPPET_LIMIT + 3


def test_chat_empty_retrieval_persists_the_turn_exactly_once():
    """空检索是业务结果，但这一轮照样得进历史：前端只留后端有的，不落库的轮次刷新后就消失了（终审 D4）。"""
    db = StubDb(parents={"p0": 7})
    rag = build(db, StubVectorStore(parent_docs=[]), ok_llm())
    answer, refs = rag.chat_with_documents("无关问题", ["p0"], "s1")
    assert refs == []
    assert "未在选中的文档里找到" in answer
    assert db.saved == [{
        "session_id": "s1",
        "user_message": "无关问题",
        "assistant_message": answer,
        "document_ids": "7",
        "used_chunks": None,
    }]


def test_chat_retrieval_failure_raises_not_swallowed():
    db = StubDb()
    rag = build(db, StubVectorStore(parent_docs=[], retriever_error=RuntimeError("chroma down")), ok_llm())
    with pytest.raises(RetrievalError):
        rag.chat_with_documents("q", ["p0"], "s1")
    assert db.saved == []


def test_chat_llm_failure_raises_not_swallowed():
    db = StubDb()
    rag = build(db, StubVectorStore(parent_docs=[parent()]), RunnableLambda(boom_llm))
    with pytest.raises(LLMError):
        rag.chat_with_documents("q", ["p0"], "s1")
    assert db.saved == []


def test_history_still_keys_on_document_ids_found_by_reverse_lookup():
    """契约换成 parent_ids，但 chat_history.document_ids 这一列的形状不能变：
    mode 派生与引用补全 filename 都吃它，加第二列是第二份真相。"""
    db = StubDb(filenames={7: "手册.txt"}, parents={"甲_p_0": 7, "乙_p_1": 9})
    rag = build(db, StubVectorStore(parent_docs=[parent()]), ok_llm("答"))
    rag.chat_with_documents("问", ["甲_p_0", "乙_p_1", "早删了_p_9"], "s1")
    assert db.saved[0]["document_ids"] == "7,9"
    assert db.reverse_calls == ["甲_p_0", "乙_p_1", "早删了_p_9"]


def test_all_selected_chunks_dead_still_goes_down_the_rag_path():
    """选中的块全被删时不改判 normal：mode 只看请求里带没带池子。
    空召回自有 EMPTY_RETRIEVAL_ANSWER 那条路，落库照旧。"""
    db = StubDb(parents={})
    rag = build(db, StubVectorStore(parent_docs=[]), ok_llm("不该被调用"))
    answer, refs = rag.chat_with_documents("问", ["死块_p_0"], "s1")
    assert refs == []
    assert answer.startswith("未在选中的文档里找到相关内容")
    assert db.saved[0]["document_ids"] == ""      # 反查空 → 空串，不是 None 也不是 "None"


# --- 坑 6 注入面：detail 直接进前端提示，不能带内部原文（Task 6 评审结转）---

INTERNAL_TEXT = "OperationalError(2003): 无法连接 127.0.0.1:3306 密码 hunter2 @ D:/secret/chroma.sqlite3"
LLM_DETAIL = "大模型调用失败，请稍后重试"
RETRIEVAL_DETAIL = "检索或上下文压缩失败，请稍后重试"


def boom_with(message):
    def _boom(_):
        raise RuntimeError(message)

    return _boom


def assert_detail_is_curated(exc, error_cls, caplog):
    """响应侧只剩固定文案，原文只在日志里。"""
    assert isinstance(exc, error_cls)
    assert INTERNAL_TEXT not in str(exc)
    assert INTERNAL_TEXT in caplog.text


def test_normal_chat_llm_failure_hides_internals_from_detail(caplog):
    rag = build(StubDb(), StubVectorStore([]), RunnableLambda(boom_with(INTERNAL_TEXT)))
    with caplog.at_level(logging.ERROR):
        with pytest.raises(LLMError) as exc_info:
            rag.normal_chat("你好", "s1")
    assert str(exc_info.value) == LLM_DETAIL
    assert_detail_is_curated(exc_info.value, LLMError, caplog)


def test_chat_retrieval_failure_hides_internals_from_detail(caplog):
    vs = StubVectorStore(parent_docs=[], retriever_error=RuntimeError(INTERNAL_TEXT))
    rag = build(StubDb(), vs, ok_llm())
    with caplog.at_level(logging.ERROR):
        with pytest.raises(RetrievalError) as exc_info:
            rag.chat_with_documents("q", ["p0"], "s1")
    assert str(exc_info.value) == RETRIEVAL_DETAIL
    assert_detail_is_curated(exc_info.value, RetrievalError, caplog)


def test_chat_llm_failure_hides_internals_from_detail(caplog):
    rag = build(StubDb(), StubVectorStore(parent_docs=[parent()]), RunnableLambda(boom_with(INTERNAL_TEXT)))
    with caplog.at_level(logging.ERROR):
        with pytest.raises(LLMError) as exc_info:
            rag.chat_with_documents("q", ["p0"], "s1")
    assert str(exc_info.value) == LLM_DETAIL
    assert_detail_is_curated(exc_info.value, LLMError, caplog)


# --- 流式生成器（阶段二 Task 1）---


def stream_llm(tokens, error_at=None):
    """假 LLM 的流式版：RunnableGenerator 让 `prompt | llm` 的 .stream() 逐块产出。
    error_at=i 表示产出第 i 块时抛错（None = 全程顺利）。"""
    def gen(_):
        for i, t in enumerate(tokens):
            if error_at is not None and i == error_at:
                raise RuntimeError("流到一半断了")
            yield SimpleNamespace(content=t)
    return RunnableGenerator(gen)


def collect(gen):
    events = list(gen)
    return events, "".join(d for k, d in events if k == "token")


def test_rag_stream_yields_references_before_tokens_and_saves_once():
    db = StubDb(filenames={7: "操作手册.txt"}, parents={"p0": 7})
    rag = build(db, StubVectorStore(parent_docs=[parent()]), stream_llm(["基于", "文档"]))
    events, answer = collect(rag.chat_with_documents_stream("父子索引是什么", ["p0"], "s1"))

    assert [k for k, _ in events] == ["references", "token", "token"]
    assert events[0][1] == [Reference(document_id=7, parent_id="p0",
                                      filename="操作手册.txt", snippet="父 块 内容")]
    assert answer == "基于文档"
    assert len(db.saved) == 1
    saved = db.saved[0]
    assert saved["assistant_message"] == "基于文档"
    assert saved["document_ids"] == "7"
    assert saved["used_chunks"].startswith('[{"document_id"')
    # 镜像非流式那条（:112-116）的强断言：流式落库的 used_chunks 必须与 references 帧**逐字节相同**
    # 且能原样读回同一批 Reference——"流式/非流持久化同形"这条约束只有 round-trip 才钉得住。
    refs = events[0][1]
    assert "操作手册.txt" in saved["used_chunks"]
    assert saved["used_chunks"] == json.dumps([r.model_dump() for r in refs], ensure_ascii=False)
    assert [Reference(**i) for i in json.loads(saved["used_chunks"])] == refs


def test_normal_stream_yields_tokens_only_and_saves_plain_history():
    db = StubDb(history=[chat("旧问", "旧答")])
    events, answer = collect(build(db, StubVectorStore([]), stream_llm(["你", "好"])).normal_chat_stream("你好", "s1"))

    assert [k for k, _ in events] == ["token", "token"]
    assert answer == "你好"
    assert db.saved == [{"session_id": "s1", "user_message": "你好", "assistant_message": "你好"}]


def test_rag_stream_empty_retrieval_is_notice_token_and_persists_once():
    db = StubDb(parents={"p0": 7})
    events, answer = collect(build(db, StubVectorStore(parent_docs=[]), stream_llm([])).chat_with_documents_stream("无关问题", ["p0"], "s1"))

    assert events == [("references", []), ("token", "未在选中的文档里找到相关内容，请换个问法或确认文档已上传。")]
    assert len(db.saved) == 1
    assert db.saved[0]["used_chunks"] is None
    assert db.saved[0]["document_ids"] == "7"


def test_rag_stream_retrieval_failure_raises_before_first_event():
    db = StubDb()
    rag = build(db, StubVectorStore(parent_docs=[], retriever_error=RuntimeError("chroma down")), stream_llm(["x"]))
    gen = rag.chat_with_documents_stream("q", ["p0"], "s1")
    with pytest.raises(RetrievalError):
        next(gen)
    assert db.saved == []


def test_rag_stream_llm_failure_midway_raises_llmerror_and_saves_nothing(caplog):
    db = StubDb(filenames={7: "a.txt"})
    rag = build(db, StubVectorStore(parent_docs=[parent()]), stream_llm(["开头", "炸了"], error_at=1))
    with caplog.at_level(logging.ERROR):
        with pytest.raises(LLMError) as exc_info:
            list(rag.chat_with_documents_stream("q", ["p0"], "s1"))
    assert str(exc_info.value) == "大模型调用失败，请稍后重试"
    assert "流到一半断了" in caplog.text
    assert db.saved == []


def test_stream_consumer_disconnect_saves_nothing():
    """消费方只拿前两个事件就 close()：GeneratorExit 落在 yield 点（BaseException，
    不被 except Exception 捕获），落库代码执行不到——spec 6.4"不写半截历史"的机制证明。"""
    db = StubDb(filenames={7: "a.txt"})
    rag = build(db, StubVectorStore(parent_docs=[parent()]), stream_llm(["一段", "二段", "三段"]))
    gen = rag.chat_with_documents_stream("q", ["p0"], "s1")
    next(gen); next(gen)
    gen.close()
    assert db.saved == []


def test_normal_stream_disconnect_saves_nothing():
    db = StubDb()
    gen = build(db, StubVectorStore([]), stream_llm(["x", "y"])).normal_chat_stream("你好", "s1")
    next(gen)
    gen.close()
    assert db.saved == []


def test_stream_variant_uses_the_same_reverse_lookup():
    db = StubDb(filenames={7: "手册.txt"}, parents={"甲_p_0": 7})
    rag = build(db, StubVectorStore(parent_docs=[parent()]), stream_llm(["一", "二"]))
    list(rag.chat_with_documents_stream("问", ["甲_p_0"], "s1"))
    assert db.saved[-1]["document_ids"] == "7"
    assert db.reverse_calls == ["甲_p_0"]


# --- 坑 9：模型名来自 Config，不留第二处字面量 ---

def test_answer_llm_takes_the_model_name_from_config(monkeypatch):
    """真构造会建 ChatOpenAI 客户端，这里把它换成记录器：只验"配置值原样传下去"。

    钉这条的理由是历史事故——2026-10-03 换可用模型时只改了压缩那处，
    答题仍在调旧模型，不报错、只是行为不对。两处都从 config 取值就不可能再分叉。
    """
    seen = {}

    class Recorder:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr("core.rag_system.ChatOpenAI", Recorder)
    config = SimpleNamespace(OPENAI_API_KEY="k", OPENAI_BASE_URL="u", LLM_MODEL="probe-model")

    RAGSystem(config, None, None)

    assert seen["model"] == "probe-model"
