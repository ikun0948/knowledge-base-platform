"""每用户一套 LLM 客户端：凭证从用户行读，不读 Config。

阶段一留下的形状是两枚进程级单例——`RAGSystem.__init__` 建一枚答题用、
`VectorStore.__init__` 再建一枚压缩用。坑 9 的教训（两处构造点早晚分叉）在阶段二
不能重演，所以这里收成全项目**唯一**的构造点，且每请求一次、用完即弃：
`ChatOpenAI(...)` 只是拼参数，不发网络请求，构造成本可以忽略（真连接发生在 invoke 时）。
"""
from dataclasses import dataclass

from langchain_classic.retrievers.document_compressors import LLMChainExtractor
from langchain_openai import ChatOpenAI

from exceptions import NotConfiguredError

# 409 的第一句文案，与设置弹窗（Task 9）的入口名一致——别改成 "前往 settings"。
NOT_CONFIGURED = "还没有配置大模型，请先在设置里填写 API Key 与路由"


@dataclass(frozen=True)
class LLMConfig:
    """一次问答要的三个值。frozen 本身有判据（`test_run_context_is_frozen`）。"""
    api_key: str
    base_url: str
    model: str


@dataclass(frozen=True)
class RunContext:
    """一次问答的"用谁的身份、打哪台模型"。Task 5 的四个链方法各收一枚。

    `user_id` 与 `llm` 必须同源、一起进来：分成两个参数的话就会出现"A 的身份配 B 的 key"，
    而那正是这套隔离唯一不该出现的形状（spec 2.3）。读侧过滤吃的就是这里的 `user_id`，
    所以这一格传错等于越权，不是"少一次比较"的小事。
    """
    user_id: int
    llm: LLMConfig


def llm_config_for(user, model: str) -> LLMConfig:
    """从用户行折成 LLMConfig，key 与路由缺一即拒。

    校验和组装写在同一个函数里而不是两步：分开了就会出现"检查过 api_key、
    组装时读的是另一份 base_url"，而这两格在同一行上，本来就该一起判。
    `model` 由调用方（Task 7 的 `_llm_context`）从模型名单里解析出来——工厂不知道名单。
    """
    if not (user.api_key and user.base_url):
        raise NotConfiguredError(NOT_CONFIGURED)
    return LLMConfig(api_key=user.api_key, base_url=user.base_url, model=model)


def build_llm(ctx: RunContext):
    """答题链：温度 0.7、开流式（原 `rag_system.py:27-33` 一字不动，只换凭证来源）。"""
    return ChatOpenAI(
        api_key=ctx.llm.api_key,
        base_url=ctx.llm.base_url,
        model=ctx.llm.model,
        temperature=0.7,
        streaming=True,
    )


def build_compressor(ctx: RunContext):
    """上下文压缩器：温度 0、不开流式（原 `vector_store.py:42-49`）。

    每请求新建而不是存成属性：`VectorStore` 是 lifespan 里的单例，
    把压缩器挂在它身上就等于让全平台共用一个人的 key——那正是本次要拆掉的东西。
    """
    llm = ChatOpenAI(
        api_key=ctx.llm.api_key,
        base_url=ctx.llm.base_url,
        model=ctx.llm.model,
        temperature=0,
    )
    return LLMChainExtractor.from_llm(llm)
