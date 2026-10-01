from fastapi.testclient import TestClient

from deps import get_rag_system
from exceptions import LLMError, RetrievalError, StorageError
from fakes import FakeRAG
from main import create_app
from schemas.common import Reference


def make_client(rag):
    app = create_app()
    app.dependency_overrides[get_rag_system] = lambda: rag
    return TestClient(app)


REF = Reference(document_id=1, parent_id="a.txt_parent_0", filename="a.txt", snippet="片段")


def test_with_documents_uses_rag_mode_and_returns_references():
    client = make_client(FakeRAG(answer="基于文档", refs=[REF]))
    body = client.post("/api/chat", json={"session_id": "s1", "question": "q", "document_ids": [1]}).json()
    assert body["mode"] == "rag"
    assert body["answer"] == "基于文档"
    assert body["references"][0]["filename"] == "a.txt"


def test_empty_document_ids_falls_back_to_normal_mode():
    client = make_client(FakeRAG(answer="闲聊"))
    body = client.post("/api/chat", json={"session_id": "s1", "question": "q", "document_ids": []}).json()
    assert body["mode"] == "normal"
    assert body["references"] == []


def test_llm_failure_returns_502_not_an_answer_in_a_200():
    """原来错误文本会被当答案返回并写进历史；现在必须是 502。"""
    client = make_client(FakeRAG(error=LLMError("大模型调用失败: boom")))
    res = client.post("/api/chat", json={"session_id": "s1", "question": "q", "document_ids": [1]})
    assert res.status_code == 502
    assert res.json()["detail"] == "大模型调用失败: boom"


def test_missing_question_is_422():
    client = make_client(FakeRAG())
    assert client.post("/api/chat", json={"session_id": "s1"}).status_code == 422


class SpyRAG(FakeRAG):
    """假对象不校验参数顺序，而端点是按位置调用的：一次传错位（session_id 与
    question 互换）在上面的断言里完全看不出来。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calls = []

    def chat_with_documents(self, question, document_ids, session_id):
        self.calls.append(("rag", question, list(document_ids), session_id))
        return super().chat_with_documents(question, document_ids, session_id)

    def normal_chat(self, question, session_id):
        self.calls.append(("normal", question, session_id))
        return super().normal_chat(question, session_id)


def test_rag_chain_receives_the_payload_in_the_right_positions():
    rag = SpyRAG(answer="基于文档", refs=[REF])
    make_client(rag).post(
        "/api/chat", json={"session_id": "s9", "question": "营收多少", "document_ids": [3, 1]}
    )
    assert rag.calls == [("rag", "营收多少", [3, 1], "s9")]


def test_normal_chain_receives_question_and_session_only():
    rag = SpyRAG(answer="闲聊")
    make_client(rag).post(
        "/api/chat", json={"session_id": "s9", "question": "你好", "document_ids": []}
    )
    assert rag.calls == [("normal", "你好", "s9")]


def test_reference_serializes_to_exactly_the_spec_fields():
    """实时答案与历史渲染共用 Reference，多一个键或少一个键都会让前端分叉（spec 6.3）。"""
    body = make_client(FakeRAG(answer="基于文档", refs=[REF])).post(
        "/api/chat", json={"session_id": "s1", "question": "q", "document_ids": [1]}
    ).json()
    assert body["references"] == [
        {"document_id": 1, "parent_id": "a.txt_parent_0", "filename": "a.txt", "snippet": "片段"}
    ]


def test_retrieval_failure_is_also_502():
    client = make_client(FakeRAG(error=RetrievalError("检索或上下文压缩失败: chroma down")))
    res = client.post("/api/chat", json={"session_id": "s1", "question": "q", "document_ids": [1]})
    assert res.status_code == 502
    assert res.json()["detail"] == "检索或上下文压缩失败: chroma down"


def test_normal_chain_llm_failure_is_502():
    client = make_client(FakeRAG(error=LLMError("大模型调用失败: boom")))
    res = client.post("/api/chat", json={"session_id": "s1", "question": "q", "document_ids": []})
    assert res.status_code == 502


def test_storage_error_on_rag_path_is_not_hijacked_into_502():
    """StorageError 不是聊天系异常：端点必须放行，让 main.py 的 STATUS_BY_ERROR 给 500。
    宽 except KnowledgeBaseError 会把它改写成 502，中央映射就形同虚设（spec 八节）。"""
    client = make_client(FakeRAG(error=StorageError("存储坏了")))
    res = client.post("/api/chat", json={"session_id": "s1", "question": "q", "document_ids": [1]})
    assert res.status_code == 500
    assert res.json()["detail"] == "存储坏了"


def test_storage_error_on_normal_path_is_not_hijacked_into_502():
    """normal 分支的 except 同样只该接管 RetrievalError/LLMError。"""
    client = make_client(FakeRAG(error=StorageError("存储坏了")))
    res = client.post("/api/chat", json={"session_id": "s1", "question": "q", "document_ids": []})
    assert res.status_code == 500
    assert res.json()["detail"] == "存储坏了"


def test_empty_retrieval_is_a_200_business_result_not_an_error():
    """rag_system 检索为空时不抛异常而是回说明文案，端点不得把它升级成 502。"""
    client = make_client(FakeRAG(answer="未在选中的文档里找到相关内容，请换个问法或确认文档已上传。", refs=[]))
    res = client.post("/api/chat", json={"session_id": "s1", "question": "q", "document_ids": [1]})
    assert res.status_code == 200
    body = res.json()
    assert body["mode"] == "rag"
    assert body["references"] == []


def test_blank_question_is_422():
    client = make_client(FakeRAG())
    assert client.post("/api/chat", json={"session_id": "s1", "question": ""}).status_code == 422


def test_non_integer_document_ids_is_422():
    client = make_client(FakeRAG())
    res = client.post("/api/chat", json={"session_id": "s1", "question": "q", "document_ids": ["abc"]})
    assert res.status_code == 422


HTML_SNIPPET = "<script>alert(1)</script> & \"quotes\" 'single'"


def test_backend_hands_the_snippet_back_as_plain_text_and_escapes_nothing():
    """坑 6 的后端侧：转义是渲染层职责，后端既不拼 HTML 也不提前转义（spec 七节）。"""
    ref = Reference(document_id=1, parent_id="p", filename="a.txt", snippet=HTML_SNIPPET)
    res = make_client(FakeRAG(answer=HTML_SNIPPET, refs=[ref])).post(
        "/api/chat", json={"session_id": "s1", "question": "q", "document_ids": [1]}
    )
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/json")
    body = res.json()
    assert body["references"][0]["snippet"] == HTML_SNIPPET
    assert body["answer"] == HTML_SNIPPET
    # JSON 里的引号会被转义成 \"，原文匹配只用不带引号的那半截
    assert "<script>alert(1)</script>" in res.text
    assert "&lt;script&gt;" not in res.text and "&amp;" not in res.text
