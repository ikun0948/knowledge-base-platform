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
