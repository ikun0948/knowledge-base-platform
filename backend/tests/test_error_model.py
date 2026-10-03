"""spec 八节错误模型的整钉测试（终审 D3）。

端点级测试各自只钉住自己那一条码，中央映射本身此前无人看守：`STATUS_BY_ERROR` 里
"哪个类对应哪个数字"改错一格、或者兜底 handler 的文案变了，全绿照旧。这里的探针路由不碰任何
真服务，只从可覆盖的依赖里抛异常，走的就是线上那条映射路径。
"""
import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from exceptions import LLMError, RetrievalError, StorageError, UnsupportedDocumentType
from core.database import DatabaseManager
from main import STATUS_BY_ERROR, create_app


def unsupported_type_dep():
    """四个探针依赖：线上这些异常来自 core 层，测试用 dependency_overrides 换成同款。"""


def storage_dep():
    """见 unsupported_type_dep。"""


def retrieval_dep():
    """见 unsupported_type_dep。"""


def llm_dep():
    """见 unsupported_type_dep。"""


def unhandled_dep():
    """不可覆盖的那个：裸 RuntimeError 只能由兜底 handler 接住。"""
    raise RuntimeError("OperationalError: 连接 mysql://root:hunter2@127.0.0.1:3306 失败")


probe_router = APIRouter(prefix="/api/probe")


@probe_router.get("/unsupported-type")
def probe_unsupported_type(_=Depends(unsupported_type_dep)):
    return {"unreachable": True}


@probe_router.get("/storage")
def probe_storage(_=Depends(storage_dep)):
    return {"unreachable": True}


@probe_router.get("/retrieval")
def probe_retrieval(_=Depends(retrieval_dep)):
    return {"unreachable": True}


@probe_router.get("/llm")
def probe_llm(_=Depends(llm_dep)):
    return {"unreachable": True}


@probe_router.get("/unhandled")
def probe_unhandled(_=Depends(unhandled_dep)):
    return {"unreachable": True}


def probe_app():
    """create_app 的处理器与中间件全在，只是没有真服务：探针路由用依赖注入抛异常。"""
    app = create_app()
    app.include_router(probe_router)
    return app


CENTRAL_MAP = [
    (unsupported_type_dep, "/api/probe/unsupported-type", UnsupportedDocumentType("不支持的文件类型: .exe"), 415),
    (storage_dep, "/api/probe/storage", StorageError("文档入库失败，已回滚"), 500),
    (retrieval_dep, "/api/probe/retrieval", RetrievalError("检索或上下文压缩失败，请稍后重试"), 502),
    (llm_dep, "/api/probe/llm", LLMError("大模型调用失败，请稍后重试"), 502),
]


@pytest.mark.parametrize("dep, path, error, status_code", CENTRAL_MAP,
                         ids=lambda v: getattr(v, "__name__", None) or str(v))
def test_central_map_pins_the_status_number_of_every_domain_error(dep, path, error, status_code):
    """钉的是"哪一类对应哪一个数字"：把 415/500/502 任一格改错，这条必须红。"""
    app = probe_app()

    def boom():
        raise error

    app.dependency_overrides[dep] = boom
    res = TestClient(app).get(path)

    assert res.status_code == status_code
    assert res.json() == {"detail": str(error)}
    # 路由里没有第二处状态码：数字只来自中央映射这张表
    assert STATUS_BY_ERROR[type(error)] == status_code


def test_central_map_covers_every_domain_error_class():
    """漏一格就等于漏一类：没进表的异常会退化成兜底 500，语义静默改变。"""
    assert set(STATUS_BY_ERROR) == {
        UnsupportedDocumentType, StorageError, RetrievalError, LLMError
    }


def test_unhandled_exception_is_a_generic_500_that_leaks_nothing():
    """spec 八节此前唯一没钉住的一条：兜底文案固定，原始异常文本一个字都不进响应体。"""
    secret = "hunter2@127.0.0.1:3306"
    # Starlette 把响应发出去之后仍会重新抛出这个异常，不看 raise_server_exceptions=False 就接不到那份 500
    res = TestClient(probe_app(), raise_server_exceptions=False).get("/api/probe/unhandled")

    assert res.status_code == 500
    assert res.json() == {"detail": "服务器内部错误"}
    assert secret not in res.text
    assert "OperationalError" not in res.text


class _BoomSession:
    """只演"提交炸"的假 session：save_chat_history 用到的接口全在这里。"""

    def __init__(self):
        self.rolled_back = False
        self.closed = False

    def add(self, obj):
        pass

    def commit(self):
        raise RuntimeError("OperationalError: MySQL server has gone away")

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_save_chat_history_wraps_db_failure_into_curated_storage_error():
    """M2-7/M-b：写历史失败在生产路径曾是裸 sqlalchemy 异常，流式端点只能兜成"服务器内部错误"，
    策展文案（含"请稍后重试"这种可行动指引）永远不可达。这里在数据层收口成 StorageError。"""
    mgr = object.__new__(DatabaseManager)  # 绕开 __init__ 的真 MySQL 连接
    session = _BoomSession()
    mgr.get_session = lambda: session
    with pytest.raises(StorageError) as exc:
        mgr.save_chat_history("s1", "问", "答")
    assert "保存对话历史失败" in str(exc.value)
    assert session.rolled_back is True, "策展文案不能吃回滚"
    assert session.closed is True
    assert isinstance(exc.value.__cause__, RuntimeError), "原异常留在链上供日志排错"
