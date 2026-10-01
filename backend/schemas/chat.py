from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from schemas.common import Reference


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1)
    document_ids: list[int] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    references: list[Reference]
    # spec 6.1 的两值枚举：脏 mode 在 schema 边界就被拒，不靠端点断言兜
    mode: Literal["rag", "normal"]


class HistoryMessage(BaseModel):
    role: str
    content: str
    references: list[Reference] | None = None
    created_at: datetime | None = None
