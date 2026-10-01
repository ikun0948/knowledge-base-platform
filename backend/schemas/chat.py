from datetime import datetime

from pydantic import BaseModel, Field

from schemas.common import Reference


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1)
    document_ids: list[int] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    references: list[Reference]
    mode: str


class HistoryMessage(BaseModel):
    role: str
    content: str
    references: list[Reference] | None = None
    created_at: datetime | None = None
