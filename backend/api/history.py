import json
import logging

from fastapi import APIRouter, Depends, Query

from deps import get_current_user, get_db
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
def get_history(session_id: str, limit: int = Query(50, ge=1, le=200),
                db=Depends(get_db), user=Depends(get_current_user)):
    """登录门有，user 过滤没有——阶段一的对话隔离靠两件事：
    ① session_id 由后端 uuid4() 铸造（Task 2），外人猜不到；
    ② 这四个端点要求 Bearer 令牌。
    真正的 chat_history.user_id 列与读写过滤在阶段二（spec 2.2 勘误：它和 RAGSystem
    四个方法、34 处调用点是同一批工作量，分两轮改同一个文件只会两次踩同一个坑）。
    """
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
def clear_history(session_id: str, db=Depends(get_db), user=Depends(get_current_user)):
    # 与 GET 同一口径：只上门、不加 user 过滤，阶段二边界见 get_history 的 docstring。
    return {"cleared": db.delete_chat_history(session_id)}
