import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from deps import get_rag_system
from exceptions import LLMError, RetrievalError, StorageError
from schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/chat")
logger = logging.getLogger("kb.api.chat")


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest, rag=Depends(get_rag_system)):
    """document_ids 为空即普通对话，用 mode 回传实际走了哪条链（spec 6.2）。"""
    if payload.document_ids:
        try:
            answer, references = rag.chat_with_documents(
                payload.question, payload.document_ids, payload.session_id
            )
        except (RetrievalError, LLMError) as exc:
            # 失败不写历史：残缺答案进 chat_history 会污染后续上下文（spec 七节）
            logger.warning("RAG 问答失败: %s", exc)
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        mode = "rag"
    else:
        try:
            answer = rag.normal_chat(payload.question, payload.session_id)
        except (RetrievalError, LLMError) as exc:
            logger.warning("普通对话失败: %s", exc)
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        references, mode = [], "normal"

    return ChatResponse(answer=answer, references=references, mode=mode)


def _sse(event: str, data) -> str:
    # json.dumps 的字符串里换行必是 \\n，裸换行不会出现——一帧一个 data 行由此保证
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/stream")
def chat_stream(payload: ChatRequest, rag=Depends(get_rag_system)):
    """SSE 流式版问答（spec 6.4 帧表逐字）。meta 发出后状态码已定格 200：
    之后的失败一律降级为 error 帧，前端读 detail，HTTP 语义让位于流协议。
    /api/chat 原样保留——spec 十一节的回退路径。"""
    if payload.document_ids:
        events = rag.chat_with_documents_stream(
            payload.question, payload.document_ids, payload.session_id
        )
        mode = "rag"
    else:
        events = rag.normal_chat_stream(payload.question, payload.session_id)
        mode = "normal"

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
        headers={"Cache-Control": "no-cache"},
    )
