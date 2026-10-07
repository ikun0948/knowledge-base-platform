import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from core.llm_factory import LLMConfig, RunContext
from deps import get_config, get_current_user, get_db, get_rag_system
from exceptions import LLMError, RetrievalError, StorageError
from schemas.chat import ChatRequest, ChatResponse, mode_of

router = APIRouter(prefix="/api/chat")
logger = logging.getLogger("kb.api.chat")


def _require_owned_parents(db, parent_ids, user) -> list[str]:
    """问答允许池过白名单：别人的 parent_id 与不存在的 parent_id 一样，都是 404。

    放在端点而不是 RAGSystem：链子只管问答，"能不能问这几个块"是门口的事（spec 3.4 同款分工）。
    也比在链子里查更便宜——越权请求一次都不该打到 embedding 与 LLM 上。
    """
    if not parent_ids:
        return []
    owned = db.owned_parent_ids(parent_ids, user_id=user.id)
    if len(owned) != len(list(dict.fromkeys(parent_ids))):
        raise HTTPException(status_code=404, detail="文档块不存在或已被删除")
    return owned


def _ctx_from_config(user, config) -> RunContext:
    """Task 5 的过渡形态：凭证仍来自 `.env`（行为一字不变），但 `user_id` 已经是当前用户。

    这一格不是占位——读侧过滤（`create_retriever`/`get_parent_documents`）吃的就是
    `ctx.user_id`，传错就是越权。Task 7 把凭证来源换成用户行、在这里加三条 409，
    所以四个 rag 调用点的形状从本 Task 起不再变化。
    """
    return RunContext(user_id=user.id, llm=LLMConfig(
        api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL, model=config.LLM_MODEL))


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest, db=Depends(get_db), rag=Depends(get_rag_system),
         user=Depends(get_current_user), config=Depends(get_config)):
    """parent_ids 为空即普通对话，用 mode 回传实际走了哪条链（spec 6.2）。"""
    ctx = _ctx_from_config(user, config)
    mode = mode_of(payload.parent_ids)
    if mode == "rag":
        _require_owned_parents(db, payload.parent_ids, user)   # ← 在碰 rag 之前
        try:
            answer, references = rag.chat_with_documents(
                ctx, payload.question, payload.parent_ids, payload.session_id
            )
        except (RetrievalError, LLMError) as exc:
            # 失败不写历史：残缺答案进 chat_history 会污染后续上下文（spec 七节）
            logger.warning("RAG 问答失败: %s", exc)
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    else:
        try:
            answer = rag.normal_chat(ctx, payload.question, payload.session_id)
        except (RetrievalError, LLMError) as exc:
            logger.warning("普通对话失败: %s", exc)
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        references = []

    return ChatResponse(answer=answer, references=references, mode=mode)


def _sse(event: str, data) -> str:
    # json.dumps 的字符串里换行必是 \\n，裸换行不会出现——一帧一个 data 行由此保证
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/stream")
def chat_stream(payload: ChatRequest, db=Depends(get_db), rag=Depends(get_rag_system),
                user=Depends(get_current_user), config=Depends(get_config)):
    """SSE 流式版问答（spec 6.4 帧表逐字）。meta 发出后状态码已定格 200：
    之后的失败一律降级为 error 帧，前端读 detail，HTTP 语义让位于流协议。
    /api/chat 原样保留——spec 十一节的回退路径。"""
    ctx = _ctx_from_config(user, config)
    mode = mode_of(payload.parent_ids)
    if mode == "rag":
        # ← 必须在 frames() 之外：流一旦开播状态码就锁死在 200，越权只能落进 error 帧，
        #   而那不再是"这个请求不该发生"的 HTTP 语义。
        _require_owned_parents(db, payload.parent_ids, user)
        events = rag.chat_with_documents_stream(
            ctx, payload.question, payload.parent_ids, payload.session_id
        )
    else:
        events = rag.normal_chat_stream(ctx, payload.question, payload.session_id)

    def frames():
        # 同步生成器经 threadpool 驱动：每条流占一个 worker 直到 done，默认 40 线程≈并发流上限；阶段三若上多用户再改 async
        yield _sse("meta", {"mode": mode, "session_id": payload.session_id})
        try:
            for kind, data in events:
                if kind == "references":
                    yield _sse("references", [r.model_dump() for r in data])
                else:
                    yield _sse("token", {"text": data})
            yield _sse("done", {})
        except (RetrievalError, LLMError, StorageError) as exc:
            logger.warning("流式问答失败: %s", exc)
            yield _sse("error", {"detail": str(exc)})
        except Exception:
            logger.exception("流式问答未知异常")
            yield _sse("error", {"detail": "服务器内部错误"})

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        # X-Accel-Buffering 关 nginx 系响应缓冲：开着会把逐字流憋成最后一整块（M-g）。
        # 心跳帧仍不做——它只在"网关有 idle 超时"时才有意义，等真上网关再补，别为不存在的环境加复杂度。
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
