from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from schemas.common import Reference


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1)
    # 块级允许池：元素上界对齐 ParentChunk.parent_id 的 String(100)，与删块端点同源。
    # G-1 的 50 项上界照旧成立：落库列存的是反查出的 document_id，≤50 个 ⇒ 499 字符 ≤ String(500)。
    # 老字段 document_ids 不留 shim：唯一客户端是自家前端，同仓同部署，留着就是永不有人删的死入口。
    parent_ids: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        default_factory=list, max_length=50)
    # 用户自带模型名：不在他的名单里就 409（api/chat.py::_llm_context），空着走他的默认模型。
    # 上界 100 与 user_models.name / ModelIn 同源（Task 2 已记这笔账）。
    model_name: str | None = Field(default=None, min_length=1, max_length=100)


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
