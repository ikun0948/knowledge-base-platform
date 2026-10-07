"""阶段二的全部理由压在这个模块：一次问答用**谁的** key、打**哪台**模型。

四条判据各挡一种坏法：
① 构造参数原样来自 ctx.llm —— 挡"忘了接用户行、又去读 Config"，那等于阶段一的形状原地不动；
② 答题 0.7 + streaming、压缩 0 且不流式 —— 挡"搬迁顺手把行为改了"（回归判据，不是新功能）；
③ 两个构造点吃同一枚 ctx.llm —— 坑 9 的新钉法。旧的两条判据（`test_rag_system.py:357`、
   `test_vector_store.py:144`）各看一个 `__init__`，谁都不表达"同源"；合成一条才真正钉住；
④ 半套配置当场拒绝 —— 有 key 没路由的请求会打到默认端点上，表征是一句看不懂的 401。
"""
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from core.llm_factory import (
    LLMConfig,
    NotConfiguredError,
    RunContext,
    build_compressor,
    build_llm,
    llm_config_for,
)
from exceptions import KnowledgeBaseError


def make_ctx(model="qwen-max", user_id=7):
    return RunContext(user_id=user_id,
                      llm=LLMConfig(api_key="sk-user-key", base_url="https://u.internal/v1", model=model))


def test_build_llm_uses_the_callers_own_credentials(monkeypatch):
    """api_key/base_url/model 三值只能来自 ctx.llm：这一格读 Config 就是阶段一没走完。"""
    seen = {}

    class Recorder:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr("core.llm_factory.ChatOpenAI", Recorder)
    build_llm(make_ctx())
    assert seen["api_key"] == "sk-user-key"
    assert seen["base_url"] == "https://u.internal/v1"
    assert seen["model"] == "qwen-max"


def test_build_llm_keeps_the_answer_chain_temperature_and_streaming(monkeypatch):
    """0.7 与 streaming=True 是 rag_system.py:31-32 的既有行为，搬迁不许顺手改。"""
    seen = {}

    class Recorder:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr("core.llm_factory.ChatOpenAI", Recorder)
    build_llm(make_ctx())
    assert seen["temperature"] == 0.7
    assert seen["streaming"] is True


def test_build_compressor_is_temperature_zero_and_shares_the_model_name(monkeypatch):
    """压缩器不开流式（`vector_store.py:42-47` 的老形状就是 `temperature=0` 一个参数），
    模型名必须与答题同一个来源——坑 9 的历史事故正是这两处分叉。"""
    seen = {}
    extracted = {}

    class Recorder:
        def __init__(self, **kwargs):
            seen.update(kwargs)
            self.model = kwargs.get("model")

    monkeypatch.setattr("core.llm_factory.ChatOpenAI", Recorder)
    monkeypatch.setattr("core.llm_factory.LLMChainExtractor",
                        SimpleNamespace(from_llm=lambda llm: extracted.setdefault("llm", llm)))
    build_compressor(make_ctx(model="qwen-turbo"))

    assert seen["temperature"] == 0
    assert "streaming" not in seen, "压缩链不是逐字输出的，别顺手给它加流式"
    assert extracted["llm"].model == "qwen-turbo"


def test_llm_config_for_returns_the_three_values():
    user = SimpleNamespace(id=3, api_key="sk-live-key", base_url="https://vLLM.internal/v1")
    conf = llm_config_for(user, model="qwen-plus")
    assert (conf.api_key, conf.base_url, conf.model) == (
        "sk-live-key", "https://vLLM.internal/v1", "qwen-plus")


@pytest.mark.parametrize("api_key,base_url", [
    (None, "https://u/v1"),
    ("sk-key-abcdef", None),
    ("", "https://u/v1"),
    ("sk-key-abcdef", ""),
])
def test_llm_config_for_refuses_a_half_set(api_key, base_url):
    """只有 key 没有路由的请求会打到 OpenAI 官方端点，表征是一句看不懂的 401。"""
    user = SimpleNamespace(id=3, api_key=api_key, base_url=base_url)
    with pytest.raises(NotConfiguredError):
        llm_config_for(user, model="qwen-max")


def test_run_context_is_frozen():
    """链子里就地改 ctx 会污染同一次请求的后续步骤（四个方法共用一枚）。"""
    ctx = make_ctx()
    with pytest.raises(FrozenInstanceError):
        ctx.user_id = 9
    with pytest.raises(FrozenInstanceError):
        ctx.llm.model = "别的模型"


def test_not_configured_error_is_a_domain_error():
    """Task 7 靠 `STATUS_BY_ERROR` 把它翻成 409；不在 KnowledgeBaseError 家族里就只会落兜底 500。"""
    assert issubclass(NotConfiguredError, KnowledgeBaseError)
