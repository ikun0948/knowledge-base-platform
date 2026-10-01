import logging

from fastapi import APIRouter, Depends, HTTPException

from deps import get_rag_system
from exceptions import LLMError, RetrievalError
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
