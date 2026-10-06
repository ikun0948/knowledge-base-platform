from pydantic import BaseModel

SNIPPET_LIMIT = 80


def snippet_of(text: str) -> str:
    """引用片段与候选池卡片共用这一份截断：压掉换行/制表/多余空格，超长补省略号。

    两处若各写一遍，历史渲染与实时渲染会在"第 80 个字符之后长什么样"上分叉。
    """
    flat = " ".join(text.split())
    return f"{flat[:SNIPPET_LIMIT]}..." if len(flat) > SNIPPET_LIMIT else flat


class Reference(BaseModel):
    """引用片段：POST /api/chat 响应与 chat_history.used_chunks 共用这一形状，
    两处结构必须一致，否则实时渲染和历史渲染会分叉（spec 6.3）。"""

    document_id: int
    parent_id: str
    filename: str
    snippet: str
