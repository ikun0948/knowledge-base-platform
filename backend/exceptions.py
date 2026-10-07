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


class NotConfiguredError(KnowledgeBaseError):
    """409：账号本身没问题，是"这个账号还没具备问答的前提"——没配 key、没配路由、
    模型名单为空、点了个名单外的模型。四种成因共用一个类：它们对用户的指引都是
    "去设置里补齐"。状态码取 409 而不是 400，因为要改的是服务器上的资源状态（spec 3.4）。"""
