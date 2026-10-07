import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.auth import router as auth_router
from api.chat import router as chat_router
from api.documents import router as documents_router
from api.history import router as history_router
from config.config import Config
from core.database import DatabaseManager
from core.document_processor import DocumentProcessor
from core.migrations import run_migrations
from core.rag_system import RAGSystem
from core.vector_store import VectorStore
from deps import get_config, get_db, get_vector_store
from exceptions import (
    AuthError,
    LLMError,
    RetrievalError,
    StorageError,
    UnsupportedDocumentType,
)

logger = logging.getLogger("kb")

# spec 八节：领域异常 → 状态码。数字与语义对应，别在函数里临场决定。
STATUS_BY_ERROR = {
    UnsupportedDocumentType: 415,
    StorageError: 500,
    RetrievalError: 502,
    LLMError: 502,
    AuthError: 401,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动期一次性构造五个单例。

    这是原来 @st.cache_resource 承担的职责：VectorStore 会加载本地 0.6B
    embedding 模型，每个请求 new 一次必然把进程打死。
    """
    config = Config()
    app.state.config = config
    app.state.db = DatabaseManager(config)
    app.state.doc_processor = DocumentProcessor(config)
    app.state.vector_store = VectorStore(config)
    # 迁移挂在 lifespan 而不是 DatabaseManager.init_database：
    # ① test_observability.py 钉死了 init 只发 engine + create_all 两次调用；
    # ② 补向量戳需要 vector_store 那个 Chroma client，它在 db 之后才构造。
    # 每次开机重跑，靠幂等把三处不同进度的库收拢（core/migrations.py 顶部）。
    run_migrations(app.state.db.engine, app.state.vector_store.chroma_client, config)
    app.state.rag_system = RAGSystem(app.state.db, app.state.vector_store)
    logger.info("后端初始化完成，chroma=%s", config.CHROMA_PERSIST_DIR)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="知识库平台 API", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    for error_cls, status_code in STATUS_BY_ERROR.items():
        # 领域异常的 message 由 raise site 写成用户可读中文，原始异常文本只进日志（core/rag_system.py）

        @app.exception_handler(error_cls)
        async def handler(request: Request, exc: Exception, _status=status_code):
            return JSONResponse(status_code=_status, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        logger.exception("未处理异常: %s", request.url.path)
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误"})

    @app.get("/api/health")
    def health(
        config=Depends(get_config),
        db=Depends(get_db),
        vector_store=Depends(get_vector_store),
    ):
        return {
            "status": "ok",
            "chroma_dir": config.CHROMA_PERSIST_DIR,
            "document_count": db.count_documents(),
            "vector_counts": vector_store.collection_counts(),
        }

    app.include_router(auth_router)
    app.include_router(documents_router)
    app.include_router(chat_router)
    app.include_router(history_router)

    return app


app = create_app()
