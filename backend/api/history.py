import json
import logging

from fastapi import APIRouter, Depends, Query

from deps import get_db
from schemas.chat import HistoryMessage, mode_of
from schemas.common import Reference

router = APIRouter(prefix="/api/history")
logger = logging.getLogger("kb.api.history")


def _parse_references(raw: str | None) -> list[Reference]:
    """脏数据降级为空列表而不是 500：历史里有本次改造之前写入的行。"""
    if not raw:
        return []
    try:
        return [Reference(**item) for item in json.loads(raw)]
    except (ValueError, TypeError) as exc:
        logger.warning("used_chunks 解析失败，按空引用处理: %s", exc)
        return []


@router.get("/{session_id}", response_model=list[HistoryMessage])
def get_history(
    session_id: str,
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
):
    messages: list[HistoryMessage] = []
    for row in db.get_chat_history(session_id, limit=limit):
        mode = mode_of(row.document_ids)
        messages.append(HistoryMessage(role="user", content=row.user_message,
                                       references=None, created_at=row.created_at))
        messages.append(HistoryMessage(role="assistant", content=row.assistant_message,
                                       references=_parse_references(row.used_chunks),
                                       created_at=row.created_at, mode=mode))
    return messages


@router.delete("/{session_id}")
def clear_history(session_id: str, db=Depends(get_db)):
    return {"cleared": db.delete_chat_history(session_id)}
