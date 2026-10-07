import json

from fastapi.testclient import TestClient

from deps import get_config, get_db, get_rag_system
from exceptions import LLMError, RetrievalError, StorageError
from fakes import FakeConfig, FakeOwnedParentsDB, FakeRAG, FakeUser, with_auth
from main import create_app
from schemas.common import Reference


def make_client(rag, db=None, user=None):
    app = create_app()
    app.dependency_overrides[get_rag_system] = lambda: rag
    # chat 端点现在真的会用到 db（越权白名单），漏这一格那 29 条会一起 500：
    # app.state.db 在测试里根本不存在
    app.dependency_overrides[get_db] = lambda: db or FakeOwnedParentsDB()
    app.dependency_overrides[get_config] = lambda: FakeConfig()
    with_auth(app, user or FakeUser())
    return TestClient(app)


REF = Reference(document_id=1, parent_id="a.txt_parent_0", filename="a.txt", snippet="片段")


def test_with_documents_uses_rag_mode_and_returns_references():
    client = make_client(FakeRAG(answer="基于文档", refs=[REF]))
    body = client.post("/api/chat", json={
        "session_id": "s1", "question": "q", "parent_ids": ["a.txt_parent_0"]}).json()
    assert body["mode"] == "rag"
    assert body["answer"] == "基于文档"
    assert body["references"][0]["filename"] == "a.txt"


def test_empty_parent_ids_falls_back_to_normal_mode():
    client = make_client(FakeRAG(answer="闲聊"))
    body = client.post("/api/chat", json={"session_id": "s1", "question": "q", "parent_ids": []}).json()
    assert body["mode"] == "normal"
    assert body["references"] == []


def test_llm_failure_returns_502_not_an_answer_in_a_200():
    """原来错误文本会被当答案返回并写进历史；现在必须是 502。"""
    client = make_client(FakeRAG(error=LLMError("大模型调用失败: boom")))
    res = client.post("/api/chat", json={
        "session_id": "s1", "question": "q", "parent_ids": ["a.txt_parent_0"]})
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
        self.seen_user_ids = []

    def chat_with_documents(self, ctx, question, parent_ids, session_id):
        self.calls.append(("rag", question, list(parent_ids), session_id))
        self.seen_user_ids.append(ctx.user_id)
        return super().chat_with_documents(ctx, question, parent_ids, session_id)

    def normal_chat(self, ctx, question, session_id):
        self.calls.append(("normal", question, session_id))
        self.seen_user_ids.append(ctx.user_id)
        return super().normal_chat(ctx, question, session_id)


def test_rag_chain_receives_the_payload_in_the_right_positions():
    rag = SpyRAG(answer="基于文档", refs=[REF])
    make_client(rag).post(
        "/api/chat", json={"session_id": "s9", "question": "营收多少",
                           "parent_ids": ["丙_p_0", "甲_p_0"]}
    )
    assert rag.calls == [("rag", "营收多少", ["丙_p_0", "甲_p_0"], "s9")]


def test_normal_chain_receives_question_and_session_only():
    rag = SpyRAG(answer="闲聊")
    make_client(rag).post(
        "/api/chat", json={"session_id": "s9", "question": "你好", "parent_ids": []}
    )
    assert rag.calls == [("normal", "你好", "s9")]


def test_rag_question_passes_the_parent_pool_through_the_whitelist():
    """白名单确实被调、而且拿到的是这个用户的 id——不传 user.id 的写法在这里必红。

    user_id 显式取 5：`FakeUser()` 的默认是 1，端点若把归属硬编码成 1 就永远测不出来（评审 F12）。
    另一半牙是状态码（评审 Minor 6）：只断 calls 的话，"照样调白名单、却把合法主人 404 掉"
    这种写法照样绿，所以这里同时钉 200。
    """
    db = FakeOwnedParentsDB()
    client = make_client(FakeRAG(), db=db, user=FakeUser(user_id=5))
    res = client.post("/api/chat", json={"session_id": "s1", "question": "q",
                                         "parent_ids": ["a.txt_parent_0"]})
    assert res.status_code == 200, res.text
    assert db.calls == [(("a.txt_parent_0",), 5)]


def test_reference_serializes_to_exactly_the_spec_fields():
    """实时答案与历史渲染共用 Reference，多一个键或少一个键都会让前端分叉（spec 6.3）。"""
    body = make_client(FakeRAG(answer="基于文档", refs=[REF])).post(
        "/api/chat", json={"session_id": "s1", "question": "q", "parent_ids": ["a.txt_parent_0"]}
    ).json()
    assert body["references"] == [
        {"document_id": 1, "parent_id": "a.txt_parent_0", "filename": "a.txt", "snippet": "片段"}
    ]


def test_retrieval_failure_is_also_502():
    client = make_client(FakeRAG(error=RetrievalError("检索或上下文压缩失败: chroma down")))
    res = client.post("/api/chat", json={
        "session_id": "s1", "question": "q", "parent_ids": ["a.txt_parent_0"]})
    assert res.status_code == 502
    assert res.json()["detail"] == "检索或上下文压缩失败: chroma down"


def test_normal_chain_llm_failure_is_502():
    client = make_client(FakeRAG(error=LLMError("大模型调用失败: boom")))
    res = client.post("/api/chat", json={"session_id": "s1", "question": "q", "parent_ids": []})
    assert res.status_code == 502


def test_storage_error_on_rag_path_is_not_hijacked_into_502():
    """StorageError 不是聊天系异常：端点必须放行，让 main.py 的 STATUS_BY_ERROR 给 500。
    宽 except KnowledgeBaseError 会把它改写成 502，中央映射就形同虚设（spec 八节）。"""
    client = make_client(FakeRAG(error=StorageError("存储坏了")))
    res = client.post("/api/chat", json={
        "session_id": "s1", "question": "q", "parent_ids": ["a.txt_parent_0"]})
    assert res.status_code == 500
    assert res.json()["detail"] == "存储坏了"


def test_storage_error_on_normal_path_is_not_hijacked_into_502():
    """normal 分支的 except 同样只该接管 RetrievalError/LLMError。"""
    client = make_client(FakeRAG(error=StorageError("存储坏了")))
    res = client.post("/api/chat", json={"session_id": "s1", "question": "q", "parent_ids": []})
    assert res.status_code == 500
    assert res.json()["detail"] == "存储坏了"


def test_empty_retrieval_is_a_200_business_result_not_an_error():
    """rag_system 检索为空时不抛异常而是回说明文案，端点不得把它升级成 502。"""
    client = make_client(FakeRAG(answer="未在选中的文档里找到相关内容，请换个问法或确认文档已上传。", refs=[]))
    res = client.post("/api/chat", json={
        "session_id": "s1", "question": "q", "parent_ids": ["a.txt_parent_0"]})
    assert res.status_code == 200
    body = res.json()
    assert body["mode"] == "rag"
    assert body["references"] == []


def test_blank_question_is_422():
    client = make_client(FakeRAG())
    assert client.post("/api/chat", json={"session_id": "s1", "question": ""}).status_code == 422


def test_overlong_parent_id_is_422():
    """元素上界对齐 ParentChunk.parent_id 的 String(100)：超长的 id 不可能在库里。"""
    res = make_client(FakeRAG()).post("/api/chat", json={
        "session_id": "s1", "question": "q", "parent_ids": ["x" * 101]})
    assert res.status_code == 422


def test_empty_parent_id_element_is_422():
    res = make_client(FakeRAG()).post("/api/chat", json={
        "session_id": "s1", "question": "q", "parent_ids": [""]})
    assert res.status_code == 422


def test_legacy_document_ids_field_is_ignored_not_rejected():
    """老字段静默丢弃 → 空池 → normal。写死这条，免得以后有人把它当兼容入口重新接上。"""
    body = make_client(FakeRAG()).post(
        "/api/chat", json={"session_id": "s1", "question": "q", "document_ids": [1]}).json()
    assert body["mode"] == "normal"


HTML_SNIPPET = "<script>alert(1)</script> & \"quotes\" 'single'"


def test_backend_hands_the_snippet_back_as_plain_text_and_escapes_nothing():
    """坑 6 的后端侧：转义是渲染层职责，后端既不拼 HTML 也不提前转义（spec 七节）。"""
    ref = Reference(document_id=1, parent_id="p", filename="a.txt", snippet=HTML_SNIPPET)
    res = make_client(FakeRAG(answer=HTML_SNIPPET, refs=[ref])).post(
        "/api/chat", json={"session_id": "s1", "question": "q", "parent_ids": ["a.txt_parent_0"]}
    )
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/json")
    body = res.json()
    assert body["references"][0]["snippet"] == HTML_SNIPPET
    assert body["answer"] == HTML_SNIPPET
    # JSON 里的引号会被转义成 \"，原文匹配只用不带引号的那半截
    assert "<script>alert(1)</script>" in res.text
    assert "&lt;script&gt;" not in res.text and "&amp;" not in res.text


# --- POST /api/chat/stream（阶段二 Task 2）---


def sse_frames(text):
    """把响应体切成 (event, data) 列表；帧以空行分隔，与前端 client.js 的切法同构。"""
    frames = []
    for block in text.strip().split("\n\n"):
        event = data = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        frames.append((event, data))
    return frames


def stream_client(rag):
    return make_client(rag)


def post_stream(client, payload):
    return client.post("/api/chat/stream", json=payload)


def test_stream_rag_frame_sequence_is_meta_references_tokens_done():
    res = post_stream(stream_client(FakeRAG(refs=[REF], tokens=["基于", "文档"])),
                      {"session_id": "s1", "question": "q", "parent_ids": ["a.txt_parent_0"]})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    frames = sse_frames(res.text)
    assert [e for e, _ in frames] == ["meta", "references", "token", "token", "done"]
    assert frames[0][1] == {"mode": "rag", "session_id": "s1"}
    assert frames[1][1] == [{"document_id": 1, "parent_id": "a.txt_parent_0", "filename": "a.txt", "snippet": "片段"}]
    assert frames[2][1] == {"text": "基于"}
    assert frames[-1][1] == {}


def test_stream_normal_frame_sequence_has_no_references_frame():
    res = post_stream(stream_client(FakeRAG(tokens=["你", "好"])),
                      {"session_id": "s1", "question": "q", "parent_ids": []})
    assert [e for e, _ in sse_frames(res.text)] == ["meta", "token", "token", "done"]
    assert sse_frames(res.text)[0][1] == {"mode": "normal", "session_id": "s1"}


def test_stream_midway_llm_failure_degrades_to_error_frame_after_200():
    """meta 之后头已发出：LLM 中途失败只能是 error 帧，不能是 502 状态码。"""
    res = post_stream(stream_client(FakeRAG(refs=[REF], tokens=["开头"], error=LLMError("大模型调用失败，请稍后重试"), error_after=1)),
                      {"session_id": "s1", "question": "q", "parent_ids": ["a.txt_parent_0"]})
    assert res.status_code == 200
    frames = sse_frames(res.text)
    assert [e for e, _ in frames] == ["meta", "references", "token", "error"]
    assert frames[-1][1] == {"detail": "大模型调用失败，请稍后重试"}
    assert "done" not in [e for e, _ in frames]


def test_stream_storage_error_comes_as_error_frame_not_hijacked():
    """StorageError（写历史失败，发生在生成完成后）：中央映射对已开播的流无能为力，
    detail 必须原文进 error 帧——前端据此撤消息，界面与后端历史一致。"""
    res = post_stream(stream_client(FakeRAG(tokens=["x"], error=StorageError("存储坏了"), error_after=1)),
                      {"session_id": "s1", "question": "q", "parent_ids": ["a.txt_parent_0"]})
    frames = sse_frames(res.text)
    assert frames[-1] == ("error", {"detail": "存储坏了"})


def test_stream_retrieval_failure_is_meta_plus_error_only():
    res = post_stream(stream_client(FakeRAG(error=RetrievalError("检索或上下文压缩失败，请稍后重试"))),
                      {"session_id": "s1", "question": "q", "parent_ids": ["a.txt_parent_0"]})
    assert res.status_code == 200
    assert [e for e, _ in sse_frames(res.text)] == ["meta", "error"]


def test_stream_unknown_failure_gives_generic_detail_without_internals():
    class Boom(FakeRAG):
        # 真实 rag_system 的这条链是生成器：_build_references / get_chat_history 的原始异常
        # 在**迭代时**抛出（不是端点取事件的调用时），桩必须同构，否则测的不是同一条路径。
        def chat_with_documents_stream(self, ctx, q, ids, sid):
            raise RuntimeError("OperationalError(2003): 密码 hunter2 @ 127.0.0.1:3306")
            yield  # 永不执行；仅这一行让上面的 raise 落在迭代期

    res = post_stream(stream_client(Boom()),
                      {"session_id": "s1", "question": "q", "parent_ids": ["a.txt_parent_0"]})
    detail = sse_frames(res.text)[-1][1]["detail"]
    assert detail == "服务器内部错误"
    assert "hunter2" not in res.text


def test_stream_blank_question_is_plain_http_422_before_any_frame():
    """body 校验发生在 StreamingResponse 之前：422 仍是真状态码 + JSON detail。"""
    res = post_stream(stream_client(FakeRAG()),
                      {"session_id": "s1", "question": "", "parent_ids": ["a.txt_parent_0"]})
    assert res.status_code == 422
    assert "event:" not in res.text


def test_stream_payload_is_forwarded_in_the_right_positions():
    class SpyStreamRAG(FakeRAG):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.stream_calls = []
            self.seen_user_ids = []

        def chat_with_documents_stream(self, ctx, question, parent_ids, session_id):
            self.stream_calls.append(("rag", question, list(parent_ids), session_id))
            self.seen_user_ids.append(ctx.user_id)
            return super().chat_with_documents_stream(ctx, question, parent_ids, session_id)

        def normal_chat_stream(self, ctx, question, session_id):
            self.stream_calls.append(("normal", question, session_id))
            self.seen_user_ids.append(ctx.user_id)
            return super().normal_chat_stream(ctx, question, session_id)

    rag = SpyStreamRAG(tokens=["x"])
    post_stream(stream_client(rag), {"session_id": "s9", "question": "营收多少",
                                     "parent_ids": ["丙_p_0", "甲_p_0"]})
    post_stream(stream_client(rag), {"session_id": "s9", "question": "你好", "parent_ids": []})
    assert rag.stream_calls == [("rag", "营收多少", ["丙_p_0", "甲_p_0"], "s9"), ("normal", "你好", "s9")]
    assert rag.seen_user_ids == [1, 1], "ctx 传错 = 读侧过滤按别人的边界走"


def test_stream_frames_are_single_line_json_with_readable_chinese():
    """帧协议钉死（spec 6.4）：一条帧的 data 恰好一行——ensure_ascii=False 保中文逐字，
    JSON 字符串里的换行自带转义，不可能劈开帧。"""
    ref = Reference(document_id=1, parent_id="p", filename="甲.txt", snippet="中文片段")
    res = post_stream(stream_client(FakeRAG(refs=[ref], tokens=["第一段\n第二段"])),
                      {"session_id": "s1", "question": "q", "parent_ids": ["a.txt_parent_0"]})
    lines = res.text.strip().split("\n")
    assert sum(1 for ln in lines if ln.startswith("data: ")) == 4  # meta/references/token/done
    assert "中文片段" in res.text and "\\u" not in res.text
    assert "第一段\\n第二段" in res.text  # 换行被 JSON 转义在字符串内部


def test_more_than_50_parent_ids_is_422():
    """G-1 收口：落库列 + 检索扇出都不该吃无界列表；50 项上限一次钉住两个端点。

    宽度账照旧成立：50 个 parent_id 反查出的 document_id ≤50 个 ⇒ 499 字符 ≤ String(500)。
    """
    client = make_client(FakeRAG())
    res = client.post("/api/chat", json={"session_id": "s1", "question": "q",
                                         "parent_ids": [f"p{i}" for i in range(51)]})
    assert res.status_code == 422
    res = client.post("/api/chat/stream", json={"session_id": "s1", "question": "q",
                                                "parent_ids": [f"p{i}" for i in range(51)]})
    assert res.status_code == 422
    # 状态码只是另一半：校验发生在 StreamingResponse 之前，这里必须零 SSE 帧、纯 JSON
    assert "event:" not in res.text
    assert res.headers["content-type"].startswith("application/json")
    assert res.json()["detail"]


def test_stream_rejects_overlong_and_empty_parent_ids_with_zero_frames():
    """空串连"一个可能的 id"都不是，同属坏请求；流端点依旧 422 前挡、零帧。"""
    client = make_client(FakeRAG())
    for bad in (["x" * 101], [""], ["a", ""]):
        res = client.post("/api/chat/stream", json={"session_id": "s1", "question": "q",
                                                    "parent_ids": bad})
        assert res.status_code == 422, bad
        assert "event:" not in res.text


def test_stream_headers_forbid_proxy_buffering():
    """M-g/M2-3：反代（nginx 系）默认缓冲响应，逐字流会被憋成"最后一整块"——
    状态码与帧序全对，用户看到的却是转圈后一次吐完。X-Accel-Buffering: no 是关它；
    Cache-Control: no-cache 此前无人断言（M2-3），一并钉住。"""
    res = post_stream(stream_client(FakeRAG(tokens=["你", "好"])),
                      {"session_id": "s1", "question": "q", "parent_ids": []})
    assert res.headers["x-accel-buffering"] == "no"
    assert res.headers["cache-control"] == "no-cache"
    assert res.headers["content-type"].startswith("text/event-stream")
