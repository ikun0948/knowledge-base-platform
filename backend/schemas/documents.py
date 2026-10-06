from datetime import datetime

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: int
    filename: str
    chunk_count: int
    created_at: datetime


class ChunkOut(BaseModel):
    """父块候选池的一条：弹窗与已选列表都只吃这一个形状。"""

    parent_id: str
    document_id: int
    filename: str
    suffix: str
    snippet: str
    child_count: int
