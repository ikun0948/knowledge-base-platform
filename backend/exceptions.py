class KnowledgeBaseError(Exception):
    """后端领域异常基类：api 层按类型映射 HTTP 状态码。"""


class UnsupportedDocumentType(KnowledgeBaseError):
    """415：文件类型不在 pdf/docx/txt 白名单内。"""


class StorageError(KnowledgeBaseError):
    """500：MySQL / Chroma 写入失败，已尽力回滚。"""


class RetrievalError(KnowledgeBaseError):
    """502：向量检索或上下文压缩失败。"""


class LLMError(KnowledgeBaseError):
    """502：大模型调用失败。"""


class AuthError(KnowledgeBaseError):
    """401：缺令牌、坏令牌、过期令牌。三种情况共用一句文案——
    区分它们等于向外人承认"这个账号存在，只是你的票不对"（spec 3.5）。"""
