from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from schemas.common import Reference


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1)
    # G-1：上限 50 项——String(500) 的落库列与检索扇出都吃不消无界列表
    # M-e：元素 1..999_999_999——9 位×50 + 49 逗号 = 499 ≤ String(500)，落库炸点不后移到生成完成后
    document_ids: list[Annotated[int, Field(ge=1, le=999_999_999)]] = Field(
        default_factory=list, max_length=50)


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
    # 由行的 document_ids 派生（api/history.py），不给 chat_history 加列——L-4 的最小闭法
    mode: Literal["rag", "normal"] | None = None
