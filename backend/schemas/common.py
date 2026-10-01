from pydantic import BaseModel

SNIPPET_LIMIT = 80


class Reference(BaseModel):
    """引用片段：POST /api/chat 响应与 chat_history.used_chunks 共用这一形状，
    两处结构必须一致，否则实时渲染和历史渲染会分叉（spec 6.3）。"""

    document_id: int
    parent_id: str
    filename: str
    snippet: str
