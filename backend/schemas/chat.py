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


def mode_of(document_ids) -> Literal["rag", "normal"]:
    """走了检索链还是纯对话链，唯一判据：有没有带文档。

    入参有三种形状——请求里的 list[int]、历史行里的 "1,2" 字符串、历史行的 None，
    全部按真假收敛，所以这里不做类型解析（阶段三建议 4：三处派生收成一处）。
    """
    return "rag" if document_ids else "normal"


class HistoryMessage(BaseModel):
    role: str
    content: str
    references: list[Reference] | None = None
    created_at: datetime | None = None
    # 由 mode_of(行的 document_ids) 派生（api/history.py），不给 chat_history 加列——L-4 的最小闭法
    mode: Literal["rag", "normal"] | None = None
