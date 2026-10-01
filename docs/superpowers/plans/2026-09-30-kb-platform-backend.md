# 知识库平台后端拆分（阶段一 · 后端）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Streamlit 单体的业务层剥离成 FastAPI HTTP 后端（文档入库、RAG/普通问答、会话历史），并修掉拆分过程会真实踩到的 5 个问题。

**Architecture:** 两个独立进程，后端只提供 `/api/*` JSON 接口；`core/` 四模块（database / document_processor / vector_store / rag_system）复制进 `backend/` 后逻辑基本不变，由 `lifespan` 在启动期构造五个单例挂到 `app.state`，请求函数用 `Depends` 取——因此测试可以用 `dependency_overrides` 注入假对象，不依赖 MySQL / Chroma / API key。

**Tech Stack:** Python 3.12.3、FastAPI 0.141.1、Pydantic 2.13.5、SQLAlchemy 2.0.52 + PyMySQL、ChromaDB 1.5.9、LangChain 1.x、pytest 9.0.2 + httpx 0.28.1。

**Spec:** `docs/superpowers/specs/2026-09-30-kb-platform-frontend-backend-split-design.md`（本文所有"坑 N"指 `知识库平台开发文档.md` 第七节编号，"spec x.x"指该设计文档章节）

---

## Global Constraints

- **解释器是 `D:\python\python.exe`（Python 3.12.3，PATH 上的 `python`）**。`D:/AI-python/.venv` 是个只有 pip 的空 3.14 venv，**用了就会 "module not found"**。所有命令直接用 `python` / `python -m pytest`。
- **不安装、不升级任何包。** 实测 fastapi 0.141.1、starlette 1.6.0、uvicorn 0.52.4、pydantic 2.13.5、python-multipart 0.0.32、pytest 9.0.2、httpx 0.28.1、chromadb 1.5.9、langchain-core 1.6.1、SQLAlchemy 2.0.52、PyMySQL 1.1.1、python-dotenv 1.2.3 **全部已装**。`requirements.txt` 只做记录（spec 十一节的"只新增不升级"在此体现为"连新增都不需要"）。
- **响应不加统一壳**；错误一律 HTTP 状态码 + `{"detail": "..."}`（spec 六节）。
- **不新增配置键**：`.env` 只有 `DASHSCOPE_API_KEY`、`DASHSCOPE_BASE_URL`、`LOCAL_MODEL_PATH`、`MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USER`、`MYSQL_PASSWORD`、`MYSQL_DATABASE`、`CHROMA_PERSIST_DIR`、`CHUNK_SIZE`、`CHUNK_OVERLAP`、`TOP_K` 十二个键。日志级别交给 `uvicorn --log-level`（spec 八节）。
- **`legacy_streamlit/` 与根目录 `app.py`、`config/`、`core/` 在本计划期间一律不改**（走复制，spec 7.2）。
- **注释只写"为什么"**，一行以内；不写解释代码在做什么的注释。
- 每个 Task 结尾提交一次，身份临时指定：`git -c user.name="31439" -c user.email="31439@local" commit ...`（本机没有配 git user.name/user.email，**不要**去改配置）。
- 基线事实（供断言用）：MySQL `documents` 1 行、`parent_chunks` 2、`child_chunks` 7、`chat_history` 2；Chroma `parent_document` count 2、`child_document` count 7。
- 本计划的验收 = spec 第十节手测清单 1–6 + 全部 pytest 绿。**不做** spec 第十二节遗留项。

---

## File Structure

```
backend/                                # 本计划的全部产物
├── main.py                 # create_app()：lifespan 单例、CORS、异常映射、/api/health
├── deps.py                 # request.app.state → Depends 函数（测试 override 的接缝）
├── exceptions.py           # 4 个领域异常
├── config/config.py        # 复制 + 改造：.env 定位与 cwd 无关（spec 7.1）
├── core/                   # 复制 + 修补（坑 1/3、签名、不吞异常、used_chunks）
│   ├── database.py document_processor.py vector_store.py rag_system.py
├── schemas/
│   ├── common.py           # Reference（响应与 used_chunks 共用的唯一形状）
│   ├── documents.py chat.py
├── api/
│   ├── documents.py chat.py history.py
├── .env.example            # 模板，无真实值
├── .env                    # 真实配置，gitignored
├── data/chroma_db/         # 从 D:/AI-python/core/chroma_db 复制
└── tests/
    ├── conftest.py         # sys.path + 假对象 fixture（不触发 lifespan）
    ├── fakes.py            # FakeDB / FakeVectorStore / FakeRAG / FakeProcessor
    ├── test_config.py test_chroma_data.py test_document_processor.py
    ├── test_vector_store.py test_schemas.py test_api_documents.py
    ├── test_api_chat.py test_api_history.py test_health.py
    └── test_live_database.py   # 需要真 MySQL，单独 marker
```

前端（spec 第十一节第 6–7 步）是**另一份计划**：`docs/superpowers/plans/2026-09-30-kb-platform-frontend.md`，本计划完成后另写——把它塞进同一份会被挤成占位符。后端做完即可独立验收：打开 `http://127.0.0.1:8000/docs` 就能跑通全部能力。

---

## Task 1: backend 骨架 + 配置层（spec 7.1）

**Files:**
- Create: `backend/config/config.py`、`backend/.env.example`、`backend/.env`、`requirements.txt`、`backend/tests/conftest.py`、`backend/tests/test_config.py`
- Copy（不改原文件）: `core/*.py` → `backend/core/`

**Interfaces:**
- Consumes: 无
- Produces: `Config` 类，属性名与旧 `config/config.py` 完全一致（`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`LOCAL_MODEL_PATH`、`MYSQL_*`、`CHROMA_PERSIST_DIR`、`CHUNK_SIZE`、`CHUNK_OVERLAP`、`TOP_K`），**外加** `BASE_DIR`（`backend/` 的绝对 Path）。所有后续 Task 的构造函数继续吃 `Config()`，签名不变。

- [ ] **Step 1: 建目录并复制四模块**

```bash
cd "D:/知识库平台-前后端分离"
mkdir -p backend/config backend/core backend/schemas backend/api backend/tests backend/data
cp core/database.py core/document_processor.py core/vector_store.py core/rag_system.py backend/core/
touch backend/core/__init__.py backend/config/__init__.py backend/schemas/__init__.py backend/api/__init__.py backend/tests/__init__.py
```

复制后**不需要改任何 import**：`core/` 四个模块互不引用，只通过构造函数接收 `config`（spec 四节"严格单向依赖"的回报）。

- [ ] **Step 2: 写失败的配置测试**

`backend/tests/test_config.py`：

```python
from pathlib import Path
from config.config import Config


def test_chroma_dir_is_absolute():
    """坑 2：相对 cwd 的 CHROMA_PERSIST_DIR 会因启动目录不同而静默换库。"""
    assert Path(Config.CHROMA_PERSIST_DIR).is_absolute()


def test_env_file_is_located_by_file_position_not_cwd(tmp_path, monkeypatch):
    """spec 7.1：配置来源必须与 cwd 无关。"""
    from config import config as config_module
    monkeypatch.chdir(tmp_path)
    assert config_module.ENV_FILE.exists()
    assert config_module.BASE_DIR == Path(__file__).resolve().parents[2] / "backend"


def test_required_keys_present():
    for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "LOCAL_MODEL_PATH", "MYSQL_DATABASE"):
        assert getattr(Config, key)
```

- [ ] **Step 3: 运行确认失败**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests/test_config.py -v
```
预期：`ModuleNotFoundError: No module named 'config.config'` 或 `.env` 缺失的 RuntimeError。

- [ ] **Step 4: 写 `backend/config/config.py`**

```python
import os
from pathlib import Path
from dotenv import load_dotenv

# BASE_DIR 由本文件位置推导，不依赖启动时的 cwd（spec 7.1）
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

if not ENV_FILE.exists():
    raise RuntimeError(
        f"缺少配置文件 {ENV_FILE}：请复制 backend/.env.example 为 backend/.env 并填入真实值"
    )

load_dotenv(ENV_FILE)


class Config:
    OPENAI_API_KEY = os.getenv("DASHSCOPE_API_KEY")
    OPENAI_BASE_URL = os.getenv("DASHSCOPE_BASE_URL")
    LOCAL_MODEL_PATH = os.getenv("LOCAL_MODEL_PATH")

    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "mydb")

    CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "")
    _chroma = Path(CHROMA_PERSIST_DIR)
    if not _chroma.is_absolute():
        raise RuntimeError(
            f"CHROMA_PERSIST_DIR 必须是绝对路径，当前为 {CHROMA_PERSIST_DIR!r}（坑 2）"
        )

    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 1000))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 200))
    TOP_K = int(os.getenv("TOP_K", 5))
```

- [ ] **Step 5: 写 `backend/tests/conftest.py`**

```python
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
```

`python -m pytest` 从 `backend/` 启动时 cwd 已在路径里，这一步是为了从项目根或其它目录跑测试也能 import `config`/`core`。

- [ ] **Step 6: 创建 `.env.example` 与 `.env`**

`backend/.env.example`（不含任何真实值）：

```bash
# 复制为 backend/.env 后填写。.env 已被 .gitignore 排除，永不入库。
# 注意：D:/AI-python/.env 是其它脚本共用的，本项目不再读它（spec 7.1）。
DASHSCOPE_API_KEY=
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
# 本地 sentence-transformers 模型目录；换模型必须重建 Chroma 集合
LOCAL_MODEL_PATH=
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_DATABASE=mydb
# 必须是绝对路径（坑 2）
CHROMA_PERSIST_DIR=/absolute/path/to/backend/data/chroma_db
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
TOP_K=5
```

生成真实 `.env`（从共用 `.env` 摘取本项目需要的键，改写 `CHROMA_PERSIST_DIR`；不修改、不删除共用文件）：

```bash
cd "D:/知识库平台-前后端分离" && python - <<'PY'
from pathlib import Path

KEEP = {"DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL", "LOCAL_MODEL_PATH",
        "MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DATABASE",
        "CHUNK_SIZE", "CHUNK_OVERLAP", "TOP_K"}
src = Path("D:/AI-python/.env").read_text(encoding="utf-8")
lines = [l.strip() for l in src.splitlines()
         if "=" in l and not l.strip().startswith("#") and l.split("=", 1)[0].strip() in KEEP]
lines.append("CHROMA_PERSIST_DIR=" + (Path.cwd() / "backend/data/chroma_db").resolve().as_posix())
Path("backend/.env").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("写入键数:", len(lines), "→ backend/.env（值未打印）")
PY
```

预期输出 `写入键数: 12`。**若少于 12**，说明共用 `.env` 里缺键，停下报告，不要猜值。

- [ ] **Step 7: 写 `requirements.txt`（项目根）**

```bash
# 记录实测已装版本；本机 python 是 D:\python\python.exe (3.12.3)，不是 D:/AI-python/.venv。
# 约束：只新增不升级（详见 plan 的 Global Constraints）；本文件当前描述的是"已满足"的状态。
fastapi>=0.141
uvicorn>=0.52
python-multipart>=0.0.32
python-dotenv>=1.2
sqlalchemy>=2.0,<2.1
pymysql>=1.1
chromadb>=1.5,<2
langchain-core>=1.6
langchain-openai>=1.1
langchain-chroma>=1.1
langchain-huggingface>=1.2
langchain-text-splitters>=1.1
langchain-community>=0.3
langchain-classic>=1.0
sentence-transformers>=6.0
pypdf>=6.16
docx2txt>=0.9
pytest>=9.0
httpx>=0.28
```

- [ ] **Step 8: 运行确认通过**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests/test_config.py -v
```
预期：3 passed。

- [ ] **Step 9: 提交**

```bash
cd "D:/知识库平台-前后端分离"
git add backend/config backend/core backend/tests requirements.txt backend/.env.example .gitignore
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(backend): 骨架与配置层，.env 定位脱离 cwd"
```

---

## Task 2: Chroma 数据搬家 + 计数基线（spec 坑 2、验收判据 1）

**Files:**
- Create: `backend/data/chroma_db/`（复制）、`backend/tests/test_chroma_data.py`

**Interfaces:**
- Consumes: `Config.CHROMA_PERSIST_DIR`
- Produces: 断言基线 `PARENT_COUNT = 2`、`CHILD_COUNT = 7`，Task 3 的 `/api/health` 用同一组常量

- [ ] **Step 1: 复制数据目录**

```bash
cd "D:/知识库平台-前后端分离"
cp -r "D:/AI-python/langchain框架/core/chroma_db" backend/data/chroma_db
ls backend/data/chroma_db
```

原目录 `D:/AI-python/langchain框架/core/chroma_db` **保留不动**（回退只需把 `.env` 那行改回去）。

> **事实修正（Task 2 实测）**：本节原写源目录为 `D:/AI-python/core/chroma_db`，该路径**不存在**（`find D:/AI-python -maxdepth 4 -type d -name chroma_db` 只有 `langchain框架/core/chroma_db` 与本计划的 `backend/data/chroma_db` 两个结果）。判定 `langchain框架/core/chroma_db` 就是本项目旧库的证据：其 `parent_document` 里两条记录的 metadata 为 `parent_id: deepseek简介.docx_parent_0 / _1`、`document_id: '1'`，与 MySQL `documents.id=1`（`deepseek简介.docx`）和 `parent_chunks.parent_id` 两行逐一对应，计数 2/7 也与 `parent_chunks`/`child_chunks` 行数一致。这也解释了坑 2 为何危险：`../core/chroma_db` 只有在 cwd 位于 `langchain框架` 下时才落到真实旧库，其它启动目录会静默新建空库。

- [ ] **Step 2: 写搬家校验测试**

`backend/tests/test_chroma_data.py`：

```python
from pathlib import Path

import chromadb
from config.config import Config

# 搬家前在旧目录实测的计数，作为"数据没丢"的判据（spec 第十节判据 1）
PARENT_COUNT = 2
CHILD_COUNT = 7


def test_collection_counts_survived_the_move():
    # PersistentClient 对不存在的路径会静默新建空库，所以先证明这确实是搬进来的库
    assert (Path(Config.CHROMA_PERSIST_DIR) / "chroma.sqlite3").exists(), f"向量库未搬家：{Config.CHROMA_PERSIST_DIR}"
    client = chromadb.PersistentClient(path=Config.CHROMA_PERSIST_DIR)
    counts = {c.name: c.count() for c in client.list_collections()}
    assert counts == {"parent_document": PARENT_COUNT, "child_document": CHILD_COUNT}
```

`list_collections()` 返回的 Collection 对象在本机 chromadb 1.5.9 上**有** `count()`（Task 2 修复轮实测），不要用 `get_collection(name)` 二次查找——那会额外打开集合。

> **Task 2 修复轮对测试的两处加强（已落地，Task 3 起以修复后版本为准）**：只断言 2/7 是"多重集盲视"（丢一行补一行仍绿），故补 `PARENT_IDS` / `CHILD_IDS` 有序 id 基线做身份比对，并补 `Config.CHROMA_PERSIST_DIR == BASE_DIR/"data"/"chroma_db"` 的路径钉（否则 `.env` 指回旧库照样绿）；又因为 `PersistentClient` 打开即改写 `chroma.sqlite3`，测试改为 `shutil.copytree` 到 `tmp_path` 后读副本，并挂 `@pytest.mark.migration`——搬家是一次性证明，Task 5/7/9 会合法改动集合内容，无条件常驻会把这条测试变成永久红。`backend/pytest.ini` 因此在 Task 2 就创建（注册 `migration` 与 `live`，**不写 `addopts`**），Task 9 只往里补内容。

- [ ] **Step 3: 运行**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests/test_chroma_data.py -v
```
预期：PASS。若 FAIL 且计数为 0，先确认 `cp -r` 是否把整棵目录（含 `chroma.sqlite3`）复制完整，**不要**改测试里的常量去"适配"结果。

- [ ] **Step 4: 提交**

```bash
cd "D:/知识库平台-前后端分离" && git add backend/tests/test_chroma_data.py
git -c user.name="31439" -c user.email="31439@local" commit -m "test(backend): Chroma 搬家后集合计数与旧库一致"
```

（`backend/data/` 已在 `.gitignore` 里，不入库。）

---

## Task 3: main.py + deps.py + lifespan + `/api/health`

**Files:**
- Create: `backend/main.py`、`backend/deps.py`、`backend/exceptions.py`、`backend/tests/fakes.py`、`backend/tests/test_health.py`
- Modify: `backend/core/vector_store.py`（加集合名常量与 `collection_counts()`）、`backend/core/database.py`（加 `count_documents()`；修坑 1）

**Interfaces:**
- Consumes: `Config`、四个 core 类
- Produces:
  - `create_app() -> FastAPI`，单例在 `app.state.config / db / doc_processor / vector_store / rag_system`
  - `deps.py`：`get_config`、`get_db`、`get_doc_processor`、`get_vector_store`、`get_rag_system`（全部 `Depends` 可用）
  - `VectorStore.collection_counts() -> dict[str, int]`（键固定 `"parent"`/`"child"`）
  - `DatabaseManager.count_documents() -> int`
  - 领域异常：`UnsupportedDocumentType`、`StorageError`、`RetrievalError`、`LLMError`
  - `GET /api/health` → `{status, chroma_dir, document_count, vector_counts:{parent, child}}`

- [ ] **Step 1: 写 `backend/exceptions.py`**

```python
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
```

- [ ] **Step 2: 修坑 1 并补 `count_documents()`**

`backend/core/database.py`：把 4 处 `default=datetime.now()` 改成 `default=datetime.now`（**去掉括号**，传函数引用）。

```python
    created_at = Column(DateTime, default=datetime.now)
```

四处位置：`Document:18`、`ParentChunk:35`、`ChildChunk:58`、`ChatHistory:81`（行号指原始 `core/database.py`）。
**限定**（spec 第七节）：只影响此后新写入的行，库里已有记录仍是假的启动时刻。

在同文件 `get_all_documents` 之后加：

```python
    def count_documents(self) -> int:
        session = self.get_session()
        try:
            return session.query(Document).filter(Document.is_active == True).count()
        finally:
            session.close()
```

- [ ] **Step 3: 给 `VectorStore` 加集合名常量与计数**

`backend/core/vector_store.py` 文件顶部（`import` 之后）加：

```python
COLLECTION_PARENT = "parent_document"
COLLECTION_CHILD = "child_document"
```

把 `__init__` 里两处 `collection_name="parent_document"` / `"child_document"` 改成用这两个常量（spec 只允许这一处顺带整理，因为 health 要读同名集合）。在 `add_documents` 之前加方法：

```python
    def collection_counts(self) -> dict:
        return {
            "parent": self.chroma_client.get_collection(COLLECTION_PARENT).count(),
            "child": self.chroma_client.get_collection(COLLECTION_CHILD).count(),
        }
```

- [ ] **Step 4: 写失败的 health 测试**

`backend/tests/test_health.py`：

```python
from fakes import FakeConfig, FakeDatabase, FakeVectorStore
from deps import get_config, get_db, get_vector_store
from main import create_app
from fastapi.testclient import TestClient


def make_client():
    app = create_app()
    app.dependency_overrides[get_config] = lambda: FakeConfig()
    app.dependency_overrides[get_db] = lambda: FakeDatabase()
    app.dependency_overrides[get_vector_store] = lambda: FakeVectorStore()
    # 不进 with：TestClient 只在上下文管理器里才跑 lifespan，这里故意让它不跑，
    # 否则每个接口测试都会连真 MySQL 并加载 0.6B embedding 模型。
    return TestClient(app)


def test_health_reports_counts_from_both_stores():
    client = make_client()
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["chroma_dir"] == "fake://chroma"
    assert body["document_count"] == 1
    assert body["vector_counts"] == {"parent": 2, "child": 7}
```

- [ ] **Step 5: 写 `backend/tests/fakes.py`**

```python
class FakeConfig:
    CHROMA_PERSIST_DIR = "fake://chroma"


class FakeDatabase:
    def __init__(self):
        self.saved_history = []

    def count_documents(self):
        return 1


class FakeVectorStore:
    def __init__(self, counts=None):
        self.counts = counts or {"parent": 2, "child": 7}
        self.deleted = []

    def collection_counts(self):
        return dict(self.counts)

    def delete_by_ids(self, parent_ids, child_ids):
        self.deleted.append((list(parent_ids), list(child_ids)))

    def add_documents(self, parent_docs, child_docs, document_id):
        return [f"p{i}" for i in range(len(parent_docs))], [f"c{i}" for i in range(len(child_docs))]


class FakeDocProcessor:
    def __init__(self, fail_with=None):
        self.fail_with = fail_with

    def load_document(self, filename, raw_bytes):
        if self.fail_with:
            raise self.fail_with
        return [type("D", (), {"page_content": raw_bytes.decode("utf-8"), "metadata": {}})()]

    def create_parent_child_chunks(self, documents, filename):
        parent = type("D", (), {"page_content": "父块", "metadata": {"parent_id": f"{filename}_parent_0", "doc_type": "parent"}})
        child = type("D", (), {"page_content": "子块", "metadata": {"parent_id": f"{filename}_parent_0", "child_id": "child_0_0", "doc_type": "child"}})
        return [parent()], [child()]


class FakeRAG:
    def __init__(self, answer="回答", refs=(), error=None):
        self.answer = answer
        self.refs = list(refs)
        self.error = error

    def generate_session_id(self):
        return "fake-session"

    def chat_with_documents(self, question, document_ids, session_id):
        if self.error:
            raise self.error
        return self.answer, self.refs

    def normal_chat(self, question, session_id):
        if self.error:
            raise self.error
        return self.answer
```

- [ ] **Step 6: 运行确认失败**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests/test_health.py -v
```
预期：`ModuleNotFoundError: No module named 'main'`。

- [ ] **Step 7: 写 `backend/deps.py`**

```python
from fastapi import Request


def get_config(request: Request):
    return request.app.state.config


def get_db(request: Request):
    return request.app.state.db


def get_doc_processor(request: Request):
    return request.app.state.doc_processor


def get_vector_store(request: Request):
    return request.app.state.vector_store


def get_rag_system(request: Request):
    return request.app.state.rag_system
```

- [ ] **Step 8: 写 `backend/main.py`**

```python
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config.config import Config
from core.database import DatabaseManager
from core.document_processor import DocumentProcessor
from core.rag_system import RAGSystem
from core.vector_store import VectorStore
from deps import get_config, get_db, get_vector_store
from exceptions import (
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
    app.state.rag_system = RAGSystem(config, app.state.db, app.state.vector_store)
    logger.info("后端初始化完成，chroma=%s", config.CHROMA_PERSIST_DIR)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="知识库平台 API", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
    )

    for error_cls, status_code in STATUS_BY_ERROR.items():

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

    return app


app = create_app()
```

`chroma_dir` 必须来自 `get_config`，不要写成 `vector_store.config.CHROMA_PERSIST_DIR`——测试注入的是 `FakeVectorStore`，它没有 `config` 属性，那样写会让 health 测试无法与真实对象解耦。

- [ ] **Step 9: 单元测试转绿**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests -v
```
预期：`test_config`、`test_chroma_data`、`test_health` 全 PASS。

- [ ] **Step 10: live 验证（真 MySQL + 真 Chroma）**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m uvicorn main:app --port 8000 --log-level info
```

另开一个终端：

```bash
curl -s http://127.0.0.1:8000/api/health
```

预期：`{"status":"ok","chroma_dir":"D:/知识库平台-前后端分离/backend/data/chroma_db","document_count":1,"vector_counts":{"parent":2,"child":7}}`。
**这一步就是 spec 第十节判据 1**：`vector_counts` 等于搬家前实测值，证明"向量库没因换启动目录而消失"。

- [ ] **Step 11: 提交**

```bash
cd "D:/知识库平台-前后端分离"
git add backend/main.py backend/deps.py backend/exceptions.py backend/tests backend/core
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(backend): lifespan 单例装配、异常映射与 /api/health；修坑1时间戳默认值"
```

---

## Task 4: 文档解析层解耦 Streamlit（`load_document` 签名）

**Files:**
- Modify: `backend/core/document_processor.py`
- Create: `backend/tests/test_document_processor.py`

**Interfaces:**
- Consumes: `exceptions.UnsupportedDocumentType`
- Produces: `DocumentProcessor.load_document(filename: str, raw_bytes: bytes) -> list[Document]`（**不再是 `uploaded_file` 对象**，spec 四节）、`create_parent_child_chunks(documents, filename)` 不变

- [ ] **Step 1: 写失败的测试**

`backend/tests/test_document_processor.py`：

```python
import pytest
from core.document_processor import DocumentProcessor
from exceptions import UnsupportedDocumentType


class Cfg:
    CHUNK_SIZE = 30
    CHUNK_OVERLAP = 5


@pytest.fixture
def processor():
    return DocumentProcessor(Cfg())


def test_txt_bytes_are_loaded(processor):
    docs = processor.load_document("a.txt", "第一段。\n\n第二段。".encode("utf-8"))
    assert docs[0].page_content.startswith("第一段")


def test_unsupported_extension_raises_domain_error(processor):
    with pytest.raises(UnsupportedDocumentType):
        processor.load_document("virus.exe", b"MZ\x00")


def test_parent_child_ids_line_up(processor):
    """父子索引是全项目的立身之本：child 的 parent_id 必须能在 parent 列表里找到。"""
    documents = processor.load_document("a.txt", ("句子一。句子二。\n\n" * 8).encode("utf-8"))
    parents, children = processor.create_parent_child_chunks(documents, "a.txt")
    assert parents and children
    parent_ids = {p.metadata["parent_id"] for p in parents}
    assert all(c.metadata["parent_id"] in parent_ids for c in children)
    assert all(p.metadata["doc_type"] == "parent" for p in parents)
    assert all(c.metadata["doc_type"] == "child" for c in children)
    assert all(c.metadata["child_id"].startswith("child_") for c in children)


def test_single_short_document_does_not_index_error(processor):
    documents = processor.load_document("tiny.txt", "只有一行".encode("utf-8"))
    parents, children = processor.create_parent_child_chunks(documents, "tiny.txt")
    assert len(parents) == 1 and len(children) >= 1
```

- [ ] **Step 2: 运行确认失败**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests/test_document_processor.py -v
```
预期：FAIL——`load_document()` 仍只接受一个位置参数，`AttributeError: 'str' object has no attribute 'getvalue'`。

- [ ] **Step 3: 改 `backend/core/document_processor.py`**

整段替换 `load_document`，并把 `print(tmp_path)` 换成 logger：

```python
import logging
import os
import tempfile

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_core.documents import Document  # noqa: F401  (类型一致性检查用)
from langchain_text_splitters import RecursiveCharacterTextSplitter

from exceptions import UnsupportedDocumentType

logger = logging.getLogger("kb.document_processor")

SUPPORTED_SUFFIXES = (".pdf", ".docx", ".txt")
LOADER_BY_SUFFIX = {".pdf": PyPDFLoader, ".docx": Docx2txtLoader, ".txt": TextLoader}
```

```python
    def load_document(self, filename: str, raw_bytes: bytes):
        """加载上传的文档。

        不再接收 Streamlit 的 UploadedFile：FastAPI 的 UploadFile、测试里的 bytes
        都能直接调用（spec 四节）。
        """
        # 去掉任何路径成分：客户端可以塞 "a/../../b.txt"
        safe_name = os.path.basename(filename)
        suffix = os.path.splitext(safe_name)[1].lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise UnsupportedDocumentType(f"不支持的文件类型: {suffix or safe_name}")

        loader_cls = LOADER_BY_SUFFIX[suffix]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(raw_bytes)
            tmp_path = tmp_file.name
        logger.debug("临时文件: %s", tmp_path)

        try:
            return loader_cls(tmp_path).load()
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
```

`__init__` 与 `create_parent_child_chunks` **不动**（含那个没被主链路使用的 `self.text_splitter`，spec 十二节已记为遗留）。原 `else: raise ValueError(...)` 由白名单检查取代——`ValueError` 无法映射 415。

- [ ] **Step 4: 运行转绿**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests/test_document_processor.py -v
```
预期：4 passed。

- [ ] **Step 5: 提交**

```bash
cd "D:/知识库平台-前后端分离"
git add backend/core/document_processor.py backend/tests/test_document_processor.py
git -c user.name="31439" -c user.email="31439@local" commit -m "refactor(backend): load_document 改为 (filename, bytes)，脱离 Streamlit"
```

---

## Task 5: `VectorStore.delete_by_ids` + 父块回溯测试（spec 坑 3 前置）

**Files:**
- Modify: `backend/core/vector_store.py`
- Create: `backend/tests/test_vector_store.py`

**Interfaces:**
- Consumes: `langchain_chroma.Chroma.delete(ids=...)`（已实测存在，签名 `(self, ids: list[str] | None = None, **kwargs)`）
- Produces: `VectorStore.delete_by_ids(parent_ids: list[str], child_ids: list[str]) -> None`（Task 8 的上传回滚调它）

- [ ] **Step 1: 写失败的测试**

`backend/tests/test_vector_store.py`：

```python
import pytest
from core.vector_store import COLLECTION_CHILD, COLLECTION_PARENT, VectorStore


class StubCollection:
    def __init__(self):
        self.deleted = []

    def delete(self, ids=None, **kwargs):
        self.deleted.extend(ids or [])


@pytest.fixture
def store():
    """绕开 __init__：构造会加载 0.6B embedding 模型，测试里绝不能触发。"""
    vs = VectorStore.__new__(VectorStore)
    vs.parent_vectorstore = StubCollection()
    vs.child_vectorstore = StubCollection()
    return vs


def test_delete_by_ids_targets_the_right_collection(store):
    store.delete_by_ids(["p0", "p1"], ["c0"])
    assert store.parent_vectorstore.deleted == ["p0", "p1"]
    assert store.child_vectorstore.deleted == ["c0"]


def test_delete_with_empty_lists_touches_nothing(store):
    store.delete_by_ids([], [])
    assert store.parent_vectorstore.deleted == []
    assert store.child_vectorstore.deleted == []


def test_collection_names_match_existing_chroma(store):
    assert (COLLECTION_PARENT, COLLECTION_CHILD) == ("parent_document", "child_document")


def test_get_parent_documents_dedupes_shared_parent():
    """多个子块同属一个父块时只回溯一次（坑 7 的行为面，本次不优化查询次数，只锁语义）。"""
    vs = VectorStore.__new__(VectorStore)
    calls = []

    class GetStub:
        def get(self, where=None, include=None):
            calls.append(where["parent_id"])
            return {"documents": [f"父内容:{where['parent_id']}"], "metadatas": [{"parent_id": where["parent_id"]}]}

    vs.parent_vectorstore = GetStub()
    children = [
        type("D", (), {"metadata": {"parent_id": "a_parent_0"}})(),
        type("D", (), {"metadata": {"parent_id": "a_parent_0"}})(),
        type("D", (), {"page_content": "", "metadata": {}})(),
    ]
    parents = vs.get_parent_documents(children)
    assert calls == ["a_parent_0"]
    assert len(parents) == 1
```

- [ ] **Step 2: 运行确认失败**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests/test_vector_store.py -v
```
预期：`AttributeError: 'VectorStore' object has no attribute 'delete_by_ids'`。

- [ ] **Step 3: 实现**

`backend/core/vector_store.py` 里 `collection_counts` 之后加：

```python
    def delete_by_ids(self, parent_ids, child_ids):
        """回滚入口：按向量 id 删除刚写入的块（spec 第七节 坑 3 的补偿动作）。"""
        if parent_ids:
            self.parent_vectorstore.delete(ids=parent_ids)
        if child_ids:
            self.child_vectorstore.delete(ids=child_ids)
```

同文件把 `get_parent_documents_by_metadata` 里那句 `print(f"获取父文档时出错 ...")` 换成 `logger.warning("获取父文档失败 parent_id=%s: %s", parent_id, exc)`，并在文件顶部加：

```python
import logging

logger = logging.getLogger("kb.vector_store")
```

（spec 八节：`core/` 里 6 处 `print` 全部转 logger，这是最后一处。）

- [ ] **Step 4: 运行转绿**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests/test_vector_store.py -v
```
预期：4 passed。

- [ ] **Step 5: 提交**

```bash
cd "D:/知识库平台-前后端分离"
git add backend/core/vector_store.py backend/tests/test_vector_store.py
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(backend): VectorStore.delete_by_ids 与父块回溯语义测试"
```

---

## Task 6: `Reference` 契约 + `rag_system` 不再吞异常 + `used_chunks`

**Files:**
- Create: `backend/schemas/common.py`、`backend/tests/test_schemas.py`
- Modify: `backend/core/rag_system.py`、`backend/core/database.py`（`save_chat_history` 签名不变，新增 `get_filenames_by_ids`、`delete_chat_history`）

**Interfaces:**
- Consumes: `exceptions.RetrievalError`、`LLMError`
- Produces:
  - `Reference(document_id: int, parent_id: str, filename: str, snippet: str)`，`SNIPPET_LIMIT = 80`
  - `RAGSystem.chat_with_documents(question, document_ids, session_id) -> tuple[str, list[Reference]]`
  - `RAGSystem.normal_chat(question, session_id) -> str`
  - `DatabaseManager.get_filenames_by_ids(ids: list[int]) -> dict[int, str]`、`delete_chat_history(session_id: str) -> int`

- [ ] **Step 1: 写 `backend/schemas/common.py`**

```python
from pydantic import BaseModel

SNIPPET_LIMIT = 80


class Reference(BaseModel):
    """引用片段：POST /api/chat 响应与 chat_history.used_chunks 共用这一形状，
    两处结构必须一致，否则实时渲染和历史渲染会分叉（spec 6.3）。"""

    document_id: int
    parent_id: str
    filename: str
    snippet: str
```

- [ ] **Step 2: 写往返测试**

`backend/tests/test_schemas.py`：

```python
import json
from schemas.common import Reference


def test_reference_json_round_trip_keeps_chinese_readable():
    ref = Reference(document_id=3, parent_id="a.txt_parent_0", filename="a.txt", snippet="中文片段")
    dumped = json.dumps([ref.model_dump()], ensure_ascii=False)
    assert "中文片段" in dumped
    assert [Reference(**item) for item in json.loads(dumped)] == [ref]


def test_empty_chunk_content_still_produces_a_reference():
    ref = Reference(document_id=1, parent_id="p", filename="f.txt", snippet="")
    assert ref.model_dump()["snippet"] == ""
```

- [ ] **Step 3: 运行**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests/test_schemas.py -v
```
预期：2 passed（这组测试测的是契约本身，先立住再改生产代码）。

- [ ] **Step 4: 补两个 `DatabaseManager` 方法**

```python
    def get_filenames_by_ids(self, doc_ids):
        """一次 IN 查询，供引用片段补 filename（spec 6.3，不做 N+1）。"""
        if not doc_ids:
            return {}
        session = self.get_session()
        try:
            rows = session.query(Document.id, Document.filename).filter(Document.id.in_(doc_ids)).all()
            return {row.id: row.filename for row in rows}
        finally:
            session.close()

    def delete_chat_history(self, session_id):
        session = self.get_session()
        try:
            deleted = session.query(ChatHistory).filter(ChatHistory.session_id == session_id).delete()
            session.commit()
            return deleted
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
```

- [ ] **Step 5: 重写 `backend/core/rag_system.py` 的两个问答方法**

关键改动：**删掉 `try/except` 把错误文本当答案返回**（spec 第七节"新增"那条），失败改为抛出，由 api 层转 502、且不写历史。

```python
import json
import logging
import uuid

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from exceptions import LLMError, RetrievalError
from schemas.common import SNIPPET_LIMIT, Reference

logger = logging.getLogger("kb.rag")
```

`__init__` 保持原样（**模型名 `qwen3.8-max` 仍是硬编码**，spec 第七节明确本次不动坑 9），`generate_session_id`、`rag_prompt` 不动。替换两个方法为：

```python
    def normal_chat(self, question, session_id):
        """普通对话（不使用文档）。"""
        chat_history = self.db_manager.get_chat_history(session_id)
        messages = []
        for chat in chat_history[-5:]:
            messages.append(f"Human: {chat.user_message}")
            messages.append(f"Assistant: {chat.assistant_message}")
        messages.append(f"Human: {question}")

        try:
            answer = self.llm.invoke("\n".join(messages) + "\nAssistant:").content
        except Exception as exc:
            raise LLMError(f"大模型调用失败: {exc}") from exc

        self.db_manager.save_chat_history(
            session_id=session_id, user_message=question, assistant_message=answer
        )
        return answer

    def chat_with_documents(self, question, document_ids, session_id):
        """基于文档的 RAG 问答：子块召回 → 回溯父块 → 压缩 → 带历史生成。"""
        try:
            retriever = self.vector_store.create_retriever(document_ids)
            retrieved_docs = retriever.invoke(question)
            parent_docs = self.vector_store.get_parent_documents(retrieved_docs)
            if not parent_docs:
                # 检索为空不是故障：这是业务结果，原样返回，让接口用 200 携带说明文案
                return "未在选中的文档里找到相关内容，请换个问法或确认文档已上传。", []
            compressed_docs = self.vector_store.compressor.compress_documents(parent_docs, question)
        except Exception as exc:
            raise RetrievalError(f"检索或上下文压缩失败: {exc}") from exc

        context = "\n\n".join(d.page_content for d in compressed_docs)
        logger.debug("最终检索上下文长度: %d", len(context))

        chat_history = self.db_manager.get_chat_history(session_id)
        history_msgs = []
        for chat in chat_history[-3:]:
            history_msgs.append(HumanMessage(content=chat.user_message))
            history_msgs.append(AIMessage(content=chat.assistant_message))

        try:
            answer = (self.rag_prompt | self.llm).invoke(
                {"context": context, "chat_history": history_msgs, "question": question}
            ).content
        except Exception as exc:
            raise LLMError(f"大模型调用失败: {exc}") from exc

        references = self._build_references(compressed_docs)
        self.db_manager.save_chat_history(
            session_id=session_id,
            user_message=question,
            assistant_message=answer,
            document_ids=",".join(map(str, document_ids)),
            used_chunks=json.dumps([r.model_dump() for r in references], ensure_ascii=False),
        )
        return answer, references

    def _build_references(self, compressed_docs):
        filenames = self.db_manager.get_filenames_by_ids(
            sorted({int(d.metadata["document_id"]) for d in compressed_docs})
        )
        references = []
        for doc in compressed_docs:
            text = " ".join(doc.page_content.split())
            if len(text) > SNIPPET_LIMIT:
                text = text[:SNIPPET_LIMIT] + "..."
            document_id = int(doc.metadata["document_id"])
            references.append(Reference(
                document_id=document_id,
                parent_id=doc.metadata.get("parent_id", ""),
                filename=filenames.get(document_id, ""),
                snippet=text,
            ))
        return references
```

- [ ] **Step 6: 运行全部测试**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests -v
```
预期：全绿（含 Task 3 的 health；若 `main.py` import 了被改名的符号会在这里暴露）。

- [ ] **Step 7: live 验证 `used_chunks` 真的写进去了**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m uvicorn main:app --port 8000 &
curl -s -X POST http://127.0.0.1:8000/api/documents -F "file=@D:/知识库平台-前后端分离/知识库平台开发文档.md;filename=devdoc.txt;type=text/plain"
curl -s -X POST http://127.0.0.1:8000/api/chat -H "Content-Type: application/json" \
  -d '{"session_id":"probe-1","question":"父子索引是什么","document_ids":[2]}'
```

再查库（**只查不改**）：

```bash
cd "D:/知识库平台-前后端分离" && python -c "
from dotenv import load_dotenv; load_dotenv('backend/.env')
import os, pymysql
c=pymysql.connect(host=os.getenv('MYSQL_HOST'),user=os.getenv('MYSQL_USER'),password=os.getenv('MYSQL_PASSWORD'),database=os.getenv('MYSQL_DATABASE'))
cur=c.cursor(); cur.execute('select used_chunks from chat_history order by id desc limit 1')
print('USED_CHUNKS_HEAD', (cur.fetchone()[0] or '')[:60])
" 2>&1 | grep USED_CHUNKS_HEAD
```

预期：打印出以 `[{"document_id"` 开头的 JSON（而不是 `NULL`、也不是 Python dict 的单引号 `repr`）。
注意 `document_ids:[2]` 里的 2 要换成上一步上传返回的真实 `id`；这一步会产生一次真实 LLM 调用，问句随意即可。

- [ ] **Step 8: 提交**

```bash
cd "D:/知识库平台-前后端分离"
git add backend/schemas backend/core/rag_system.py backend/core/database.py backend/tests/test_schemas.py
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(backend): Reference 契约、rag_system 抛出异常、used_chunks 入库"
```

---

## Task 7: `POST /api/documents`（含坑 3 回滚）+ `GET /api/documents`

**Files:**
- Create: `backend/schemas/documents.py`、`backend/api/documents.py`、`backend/tests/test_api_documents.py`
- Modify: `backend/main.py`（挂 router）、`backend/core/database.py`（新增 `delete_document`）

**Interfaces:**
- Consumes: `DocumentProcessor.load_document/create_parent_child_chunks`、`VectorStore.add_documents/delete_by_ids`、`DatabaseManager.save_document/save_chunks/delete_document`、异常 `UnsupportedDocumentType`/`StorageError`
- Produces:
  - `DatabaseManager.delete_document(doc_id: int) -> int`（走 ORM `session.delete`，靠既有 `cascade="all, delete-orphan"` 带走父子块；仅供回滚内部使用，不是面向用户的删除功能——spec 一节非目标）
  - `POST /api/documents` → `201 {"id","filename","chunk_count","created_at"}`；`GET /api/documents` → `[{...}]`

- [ ] **Step 1: 写 `backend/schemas/documents.py`**

```python
from datetime import datetime

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: int
    filename: str
    chunk_count: int
    created_at: datetime
```

- [ ] **Step 2: 加 `DatabaseManager.delete_document` 与 `get_document`**

`delete_document` 是坑 3 回滚要用的；`get_document` 是上传成功后回查刚写入那一行（拿到真实 `created_at`）要用的——接口结尾不能再调 `get_all_documents()` 为一条记录拉全表。

```python
    def get_document(self, doc_id):
        session = self.get_session()
        try:
            return session.get(Document, doc_id)
        finally:
            session.close()

    def delete_document(self, doc_id):
        """回滚专用：删 documents 行，parent/child_chunks 由 ORM cascade 带走。"""
        session = self.get_session()
        try:
            doc = session.get(Document, doc_id)
            if doc is None:
                return 0
            session.delete(doc)
            session.commit()
            return 1
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
```

- [ ] **Step 3: 写失败的接口测试**

`backend/tests/test_api_documents.py`：

```python
from datetime import datetime

from fastapi.testclient import TestClient

from deps import get_db, get_doc_processor, get_vector_store
from exceptions import UnsupportedDocumentType
from fakes import FakeDocProcessor, FakeVectorStore
from main import create_app


class RecordingDB:
    def __init__(self, save_chunks_error=None):
        self.save_chunks_error = save_chunks_error
        self.deleted_docs = []
        self.saved_doc_id = 42
        self.chunks_saved = False

    def save_document(self, filename, file_path, content, chunk_count=0):
        return self.saved_doc_id

    def save_chunks(self, doc_id, parent_docs, child_docs, parent_ids, child_ids):
        if self.save_chunks_error:
            raise self.save_chunks_error
        self.chunks_saved = True

    def get_document(self, doc_id):
        return type("Doc", (), {"id": doc_id, "filename": "a.txt", "chunk_count": 1,
                                "created_at": datetime(2026, 9, 30, 12, 0)})()

    def delete_document(self, doc_id):
        self.deleted_docs.append(doc_id)
        return 1

    def get_all_documents(self):
        return []


def make_client(db, processor=None, vector_store=None):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_doc_processor] = lambda: processor or FakeDocProcessor()
    app.dependency_overrides[get_vector_store] = lambda: vector_store or FakeVectorStore()
    return TestClient(app)


def test_upload_txt_returns_201_with_document_shape():
    client = make_client(RecordingDB())
    res = client.post("/api/documents", files={"file": ("a.txt", "内容".encode("utf-8"), "text/plain")})
    assert res.status_code == 201
    body = res.json()
    assert body["id"] == 42
    assert body["filename"] == "a.txt"
    assert body["created_at"].startswith("2026-09-30")


def test_unsupported_type_returns_415_with_detail():
    client = make_client(RecordingDB(), processor=FakeDocProcessor(
        fail_with=UnsupportedDocumentType("不支持的文件类型: .exe")))
    res = client.post("/api/documents", files={"file": ("a.exe", b"MZ", "application/octet-stream")})
    assert res.status_code == 415
    assert res.json()["detail"] == "不支持的文件类型: .exe"


def test_empty_file_returns_422():
    client = make_client(RecordingDB())
    res = client.post("/api/documents", files={"file": ("a.txt", b"", "text/plain")})
    assert res.status_code == 422


def test_chunk_save_failure_rolls_back_vectors_and_document():
    """坑 3：save_chunks 失败后，"向量有、关系库无"的幽灵状态不能残留。"""
    db = RecordingDB(save_chunks_error=RuntimeError("boom"))
    store = FakeVectorStore()
    client = make_client(db, vector_store=store)

    res = client.post("/api/documents", files={"file": ("a.txt", "内容".encode("utf-8"), "text/plain")})
    assert res.status_code == 500
    assert store.deleted == (["p0"], ["c0"])
    assert db.deleted_docs == [42]
    assert db.chunks_saved is False


def test_list_documents_returns_array():
    client = make_client(RecordingDB())
    assert client.get("/api/documents").json() == []
```

- [ ] **Step 4: 运行确认失败**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests/test_api_documents.py -v
```
预期：`ModuleNotFoundError: No module named 'api.documents'` / 404。

- [ ] **Step 5: 写 `backend/api/documents.py`**

```python
import logging
import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from deps import get_db, get_doc_processor, get_vector_store
from exceptions import StorageError, UnsupportedDocumentType
from schemas.documents import DocumentOut

router = APIRouter(prefix="/api/documents")
logger = logging.getLogger("kb.api.documents")

# spec 六节端点表之外的新增校验：整份文件会被 read() 进内存，给个上界防 OOM。
# 若你（执行者）认为不该引入，删掉这两处即可，其余逻辑不受影响。
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


@router.post("", status_code=201, response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    db=Depends(get_db),
    processor=Depends(get_doc_processor),
    vector_store=Depends(get_vector_store),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="文件内容为空")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 20MB")

    # 去掉任何路径成分：客户端可以塞 "a/../../b.txt"
    filename = os.path.basename(file.filename or "")
    try:
        documents = processor.load_document(filename, raw)
    except UnsupportedDocumentType as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    parent_docs, child_docs = processor.create_parent_child_chunks(documents, filename)
    content = "\n".join(d.page_content for d in documents)

    # 先落主记录拿 doc_id：向量元数据里的 document_id 依赖它（spec 六节）
    doc_id = db.save_document(filename=filename, file_path="", content=content,
                              chunk_count=len(child_docs))
    parent_ids, child_ids = [], []
    try:
        parent_ids, child_ids = vector_store.add_documents(parent_docs, child_docs, doc_id)
        db.save_chunks(doc_id, parent_docs, child_docs, parent_ids, child_ids)
    except Exception as exc:
        logger.exception("文档入库失败，开始回滚: %s", filename)
        vector_store.delete_by_ids(parent_ids, child_ids)
        db.delete_document(doc_id)
        raise StorageError("文档入库失败，已回滚") from exc

    saved = db.get_document(doc_id)
    return DocumentOut(id=saved.id, filename=saved.filename,
                       chunk_count=saved.chunk_count, created_at=saved.created_at)


@router.get("", response_model=list[DocumentOut])
def list_documents(db=Depends(get_db)):
    return [
        DocumentOut(id=d.id, filename=d.filename, chunk_count=d.chunk_count, created_at=d.created_at)
        for d in db.get_all_documents()
    ]
```

`router` 用 `prefix="/api/documents"` + 路径 `""`，最终 URL 是 `/api/documents`（不带尾斜杠）。写成 `"/"` 会变成 `/api/documents/`，前端的请求路径就对不上了。

- [ ] **Step 6: 在 `main.py` 挂 router**

```python
from api.documents import router as documents_router

# create_app() 内，health 路由定义之后：
    app.include_router(documents_router)
```

`chat` / `history` 两个 router 在 Task 8 创建后再挂，此处不要留注释占位。

- [ ] **Step 7: 运行转绿**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests -v
```
预期：全绿，其中 `test_chunk_save_failure_rolls_back_vectors_and_document` 通过即代表 spec 第九节"回滚"那行落地。

- [ ] **Step 8: 提交**

```bash
cd "D:/知识库平台-前后端分离"
git add backend/api backend/schemas backend/core/database.py backend/main.py backend/tests/test_api_documents.py
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(api): 文档上传与列表，含坑3 的向量+关系库回滚"
```

---

## Task 8: `POST /api/chat` + `GET/DELETE /api/history/{session_id}`

**Files:**
- Create: `backend/schemas/chat.py`、`backend/api/chat.py`、`backend/api/history.py`、`backend/tests/test_api_chat.py`、`backend/tests/test_api_history.py`
- Modify: `backend/main.py`（挂剩余两个 router）

**Interfaces:**
- Consumes: `RAGSystem.chat_with_documents/normal_chat`、`DatabaseManager.get_chat_history/delete_chat_history`、`Reference`
- Produces:
  - `POST /api/chat` → `{"answer","references":[Reference],"mode":"rag"|"normal"}`；失败 `502 {"detail"}` 且**不写历史**
  - `GET /api/history/{session_id}?limit=50` → `[{role, content, references, created_at}]`（一行 DB → user + assistant 两条）
  - `DELETE /api/history/{session_id}` → `{"cleared": n}`

- [ ] **Step 1: 写 `backend/schemas/chat.py`**

```python
from datetime import datetime

from pydantic import BaseModel, Field

from schemas.common import Reference


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1)
    document_ids: list[int] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    references: list[Reference]
    mode: str


class HistoryMessage(BaseModel):
    role: str
    content: str
    references: list[Reference] | None = None
    created_at: datetime | None = None
```

- [ ] **Step 2: 写失败的测试**

`backend/tests/test_api_chat.py`：

```python
from fakes import FakeRAG
from deps import get_rag_system
from exceptions import LLMError
from main import create_app
from fastapi.testclient import TestClient
from schemas.common import Reference


def make_client(rag):
    app = create_app()
    app.dependency_overrides[get_rag_system] = lambda: rag
    return TestClient(app)


REF = Reference(document_id=1, parent_id="a.txt_parent_0", filename="a.txt", snippet="片段")


def test_with_documents_uses_rag_mode_and_returns_references():
    client = make_client(FakeRAG(answer="基于文档", refs=[REF]))
    body = client.post("/api/chat", json={"session_id": "s1", "question": "q", "document_ids": [1]}).json()
    assert body["mode"] == "rag"
    assert body["answer"] == "基于文档"
    assert body["references"][0]["filename"] == "a.txt"


def test_empty_document_ids_falls_back_to_normal_mode():
    client = make_client(FakeRAG(answer="闲聊"))
    body = client.post("/api/chat", json={"session_id": "s1", "question": "q", "document_ids": []}).json()
    assert body["mode"] == "normal"
    assert body["references"] == []


def test_llm_failure_returns_502_not_an_answer_in_a_200():
    """原来错误文本会被当答案返回并写进历史；现在必须是 502。"""
    client = make_client(FakeRAG(error=LLMError("大模型调用失败: boom")))
    res = client.post("/api/chat", json={"session_id": "s1", "question": "q", "document_ids": [1]})
    assert res.status_code == 502
    assert res.json()["detail"] == "大模型调用失败: boom"


def test_missing_question_is_422():
    client = make_client(FakeRAG())
    assert client.post("/api/chat", json={"session_id": "s1"}).status_code == 422
```

`backend/tests/test_api_history.py`：

```python
from datetime import datetime

from deps import get_db
from main import create_app
from fastapi.testclient import TestClient
from schemas.common import Reference

REF = Reference(document_id=1, parent_id="p", filename="a.txt", snippet="片段")


class Row:
    def __init__(self, used_chunks):
        self.user_message = "问"
        self.assistant_message = "答"
        self.used_chunks = used_chunks
        self.created_at = datetime(2026, 9, 30, 10, 0)


class HistoryDB:
    def __init__(self, rows):
        self.rows = rows
        self.cleared_with = None

    def get_chat_history(self, session_id, limit=10):
        return self.rows

    def delete_chat_history(self, session_id):
        self.cleared_with = session_id
        return 2


def make_client(db):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_one_db_row_expands_into_two_messages():
    db = HistoryDB([Row('[{"document_id":1,"parent_id":"p","filename":"a.txt","snippet":"片段"}]')])
    body = make_client(db).get("/api/history/s1").json()
    assert [m["role"] for m in body] == ["user", "assistant"]
    assert body[0]["references"] is None
    assert body[1]["references"][0]["snippet"] == "片段"


def test_legacy_rows_without_used_chunks_still_load():
    """库里已有行 used_chunks 为 NULL：历史必须能恢复，不能因脏数据 500。"""
    body = make_client(HistoryDB([Row(None)])).get("/api/history/s1").json()
    assert body[1]["references"] == []


def test_corrupt_used_chunks_degrades_to_empty():
    body = make_client(HistoryDB([Row("不是JSON")])).get("/api/history/s1").json()
    assert body[1]["references"] == []


def test_limit_is_capped_at_200():
    assert make_client(HistoryDB([])).get("/api/history/s1?limit=500").status_code == 422


def test_delete_returns_cleared_count():
    db = HistoryDB([])
    body = make_client(db).delete("/api/history/s1").json()
    assert body == {"cleared": 2}
    assert db.cleared_with == "s1"
```

- [ ] **Step 3: 运行确认失败**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests/test_api_chat.py tests/test_api_history.py -v
```
预期：404（路由不存在）。

- [ ] **Step 4: 写 `backend/api/chat.py`**

```python
import logging

from fastapi import APIRouter, Depends, HTTPException

from deps import get_rag_system
from exceptions import KnowledgeBaseError
from schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/chat")
logger = logging.getLogger("kb.api.chat")


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest, rag=Depends(get_rag_system)):
    """document_ids 为空即普通对话，用 mode 回传实际走了哪条链（spec 6.2）。"""
    if payload.document_ids:
        try:
            answer, references = rag.chat_with_documents(
                payload.question, payload.document_ids, payload.session_id
            )
        except KnowledgeBaseError as exc:
            # 失败不写历史：残缺答案进 chat_history 会污染后续上下文（spec 七节）
            logger.warning("RAG 问答失败: %s", exc)
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        mode = "rag"
    else:
        try:
            answer = rag.normal_chat(payload.question, payload.session_id)
        except KnowledgeBaseError as exc:
            logger.warning("普通对话失败: %s", exc)
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        references, mode = [], "normal"

    return ChatResponse(answer=answer, references=references, mode=mode)
```

- [ ] **Step 5: 写 `backend/api/history.py`**

```python
import json
import logging

from fastapi import APIRouter, Depends, Query

from deps import get_db
from schemas.chat import HistoryMessage
from schemas.common import Reference

router = APIRouter(prefix="/api/history")
logger = logging.getLogger("kb.api.history")


def _parse_references(raw: str | None) -> list[Reference]:
    """脏数据降级为空列表而不是 500：历史里有本次改造之前写入的行。"""
    if not raw:
        return []
    try:
        return [Reference(**item) for item in json.loads(raw)]
    except (ValueError, TypeError) as exc:
        logger.warning("used_chunks 解析失败，按空引用处理: %s", exc)
        return []


@router.get("/{session_id}", response_model=list[HistoryMessage])
def get_history(
    session_id: str,
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
):
    messages: list[HistoryMessage] = []
    for row in db.get_chat_history(session_id, limit=limit):
        messages.append(HistoryMessage(role="user", content=row.user_message,
                                       references=None, created_at=row.created_at))
        messages.append(HistoryMessage(role="assistant", content=row.assistant_message,
                                       references=_parse_references(row.used_chunks),
                                       created_at=row.created_at))
    return messages


@router.delete("/{session_id}")
def clear_history(session_id: str, db=Depends(get_db)):
    return {"cleared": db.delete_chat_history(session_id)}
```

- [ ] **Step 6: 在 `main.py` 挂剩余两个 router**

在 Task 7 那行 `app.include_router(documents_router)` 之后追加：

```python
from api.chat import router as chat_router
from api.history import router as history_router

    app.include_router(chat_router)
    app.include_router(history_router)
```

- [ ] **Step 7: 全量测试**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests -v
```
预期：全绿。若 `test_health_reports_counts_from_both_stores` 因 `Exception` handler 与 `TestClient` 交互而失败，用 `TestClient(app, raise_server_exceptions=False)`——但**只有真出现才改**，不要预防性加。

- [ ] **Step 8: live 全链路（spec 第十节判据 2、3、4）**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m uvicorn main:app --port 8000 --log-level info
```

另开终端，按顺序：

```bash
# 判据 2：类型与时间戳
curl -s -X POST http://127.0.0.1:8000/api/documents -F "file=@/dev/null;filename=empty.txt;type=text/plain"   # 期望 422
curl -s -X POST http://127.0.0.1:8000/api/documents -F "file=@-;filename=bad.exe;type=text/plain" <<< "x"      # 期望 415
printf '甲公司的营收是 100 元。\n\n乙公司的成本是 40 元。' > /tmp/comp.txt
curl -s -X POST http://127.0.0.1:8000/api/documents -F "file=@/tmp/comp.txt"
curl -s http://127.0.0.1:8000/api/documents
```

预期：新文档的 `created_at` 是**当前时刻**（不是 uvicorn 启动时刻、更不是 2026-09-19）；`chunk_count >= 1`。

```bash
# 判据 3：rag 与 normal 两条模式（把 2 换成上一步返回的真实 id）
curl -s -X POST http://127.0.0.1:8000/api/chat -H "Content-Type: application/json" \
  -d '{"session_id":"live-1","question":"甲公司的营收是多少？","document_ids":[2]}'
curl -s -X POST http://127.0.0.1:8000/api/chat -H "Content-Type: application/json" \
  -d '{"session_id":"live-1","question":"你好","document_ids":[]}'
# 判据 4：历史恢复
curl -s http://127.0.0.1:8000/api/history/live-1
curl -s -X DELETE http://127.0.0.1:8000/api/history/live-1
```

预期：第一条 `mode:"rag"` 且 `references` 非空、每条含 `filename`；第二条 `mode:"normal"` 且 `references:[]`；历史返回 4 条消息（2 行 × 2），assistant 那条带 `references`；DELETE 返回 `{"cleared":2}`，再 GET 返回 `[]`。

- [ ] **Step 9: 提交**

```bash
cd "D:/知识库平台-前后端分离"
git add backend/api backend/schemas backend/main.py backend/tests/test_api_chat.py backend/tests/test_api_history.py
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(api): 问答与历史接口，rag/normal 双模式与 502 错误路径"
```

---

## Task 9: 注入面回归测试（坑 6）+ live 数据库测试 + 计划收尾验证

**Files:**
- Create: `backend/tests/test_live_database.py`、`backend/pytest.ini`

**Interfaces:**
- Consumes: 前 8 个 Task 的全部产物
- Produces: 可在无 MySQL 环境下自动跳过的一组真库测试；`SNIPPET` 注入文本的处理语义（后端只返回纯文本，转义责任在前端）

- [ ] **Step 1: 写 `backend/pytest.ini`**

```ini
[pytest]
markers =
    live: 需要真实 MySQL/Chroma 与网络 LLM，默认手动触发（-m live）
```

- [ ] **Step 2: 写 live 测试**

`backend/tests/test_live_database.py`：

```python
import json
import time
from datetime import timedelta

import pytest
from config.config import Config
from core.database import DatabaseManager
from schemas.common import Reference

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def db():
    return DatabaseManager(Config())


def test_new_rows_get_their_own_timestamp(db):
    """坑 1 的行为面：两条记录的时间戳不应相同（原 default=datetime.now() 会相等）。"""
    first = db.save_document(filename="probe-a.txt", file_path="", content="a", chunk_count=0)
    time.sleep(1.1)
    second = db.save_document(filename="probe-b.txt", file_path="", content="b", chunk_count=0)
    try:
        a, b = db.get_document(first), db.get_document(second)
        assert abs(b.created_at - a.created_at) >= timedelta(seconds=1)
    finally:
        db.delete_document(first)
        db.delete_document(second)


def test_delete_document_cascades_chunks(db):
    """回滚依赖 ORM cascade，这里在真库上验它确实把父子块一起带走。"""
    doc_id = db.save_document(filename="probe-c.txt", file_path="", content="c", chunk_count=0)
    parent = type("D", (), {"page_content": "父", "metadata": {"parent_id": "probe_parent_0"}})
    child = type("D", (), {"page_content": "子",
                           "metadata": {"parent_id": "probe_parent_0", "child_id": "probe_child_0"}})
    db.save_chunks(doc_id, [parent()], [child()], ["vp"], ["vc"])
    try:
        assert db.delete_document(doc_id) == 1
        assert db.get_document(doc_id) is None
    finally:
        db.delete_document(doc_id)


def test_used_chunks_round_trips_through_json(db):
    ref = Reference(document_id=999, parent_id="p", filename="中文名.txt", snippet="含 <script> 的片段")
    db.save_chat_history(session_id="probe-live", user_message="问", assistant_message="答",
                         document_ids="999",
                         used_chunks=json.dumps([ref.model_dump()], ensure_ascii=False))
    try:
        row = db.get_chat_history("probe-live")[0]
        assert Reference(**json.loads(row.used_chunks)[0]) == ref
    finally:
        db.delete_chat_history("probe-live")
```

- [ ] **Step 3: 运行 live 测试**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests -m live -v
```
预期：3 passed（本机 MySQL 已确认可连：`documents` 1 行等）。清理逻辑在 `finally` 里，跑完不留探针数据。

- [ ] **Step 4: 确认后端不产生 HTML（坑 6 的后端侧）**

`POST /api/chat` 的 `references[].snippet` 原样携带 `<script>alert(1)</script>` 文本（Task 9 Step 2 的第三个测试已覆盖"含 `<script>` 的片段"往返不丢），后端**不做任何 HTML 拼接或转义**——转义是渲染层职责，由前端 `{{ }}` 插值承担（spec 第七节 坑 6）。本 Task 只锁"接口返回纯文本"这一侧；页面侧验证在阶段一的计划二（前端）里做。

- [ ] **Step 5: 全量回归**

```bash
cd "D:/知识库平台-前后端分离/backend"
python -m pytest tests -v -m "not live"
python -m pytest tests -m live -v
```

预期：两组都全绿。若只有 `live` 组里出现失败，先怀疑环境（MySQL 连接），不要改断言。

- [ ] **Step 6: 更新 spec 的两处环境事实**

`docs/superpowers/specs/2026-09-30-...-design.md`：
- 第十节代码块里的解释器从 `D:/AI-python/.venv/Scripts/python.exe` 改为 `python`（实测 `D:\python\python.exe` 3.12.3；那个 `.venv` 是空的 3.14 venv）。
- 第十一节"依赖安装注意"改为：**实测无需安装任何东西**，fastapi/uvicorn/python-multipart/pytest/httpx 均已在 3.12 全局环境装好；`requirements.txt` 仅作记录。

- [ ] **Step 7: 提交**

```bash
cd "D:/知识库平台-前后端分离"
git add backend/tests/test_live_database.py backend/pytest.ini docs
git -c user.name="31439" -c user.email="31439@local" commit -m "test(backend): live 数据库回归 + spec 环境事实修订"
```

---

## Task 10: 归档准备（spec 第十一节第 7 步的前半）

**Files:**
- Create: `legacy_streamlit/README.md`
- Modify: `知识库平台开发文档.md`（文末追加一行指向 spec 与本计划）

- [ ] **Step 1: 写 `legacy_streamlit/README.md`**

```markdown
# legacy_streamlit

阶段一改造前的 Streamlit 单体实现，**冻结副本**：`config/`、`core/` 是改造前的原样拷贝，
`app.py` 是原入口。用途只有一个——手测时对照行为、读旧实现。

- 任何功能修改只进 `backend/`，本目录不接受改动。
- 跑它需要 `D:/AI-python/.env`（旧 `config.py` 的向上查找路径命中的那个），
  且 `CHROMA_PERSIST_DIR` 仍指向 `D:/AI-python/core/chroma_db`。
- 阶段一验收通过后由用户决定是否删除本目录。
```

- [ ] **Step 2: 复制归档（复制，不动根目录原文件）**

```bash
cd "D:/知识库平台-前后端分离"
mkdir -p legacy_streamlit
cp app.py streamlit页面.py legacy_streamlit/
cp -r config core .streamlit legacy_streamlit/
```

根目录的 `app.py`/`config/`/`core/` **此时仍保留**（spec 7.2：阶段一期间 originals 原位，任何时刻最多"原始 + backend 副本"两份）。

- [ ] **Step 3: 给开发文档加指针**

`知识库平台开发文档.md` 末尾追加：

```markdown
---

**2026-09-30 更新**：本项目已启动前后端分离改造。
- 设计：`docs/superpowers/specs/2026-09-30-kb-platform-frontend-backend-split-design.md`
- 后端实施计划：`docs/superpowers/plans/2026-09-30-kb-platform-backend.md`
- 本文第七节的坑 1、2、3、6 已在改造中修复（坑 1 只影响新写入的行）。
```

- [ ] **Step 4: 提交**

```bash
cd "D:/知识库平台-前后端分离"
git add legacy_streamlit 知识库平台开发文档.md
git -c user.name="31439" -c user.email="31439@local" commit -m "chore: 归档 Streamlit 单体为冻结副本并互链文档"
```

---

## Plan 完成标准

- `python -m pytest tests -v -m "not live"` 与 `-m live` 两组全绿。
- `GET /api/health` 的 `vector_counts` == `{"parent":2,"child":7}`（spec 判据 1）。
- 上传 415/422/500 三条错误路径都在 pytest 里有断言，其中 500 那条同时断言"向量已删 + documents 行已删"（spec 判据 5，自动化）。
- live 跑通 `rag`/`normal` 两种模式、历史 GET 含 `references`、DELETE 生效（spec 判据 3、4）。
- `legacy_streamlit/` 有冻结副本，根目录 `app.py` 未改动，`git log --oneline` 有 ≥10 次小步提交。
- **不含**任何前端代码（计划二）、不含 SSE（spec 6.4，阶段二）。

## 遗留到计划二 / 阶段二的清单

- 前端 `frontend/` 全套（spec 第五节 + 第十一节第 6～7 步）→ `docs/superpowers/plans/2026-09-30-kb-platform-frontend.md`。
- SSE 端点 `POST /api/chat/stream` 与帧协议（spec 6.4）→ 阶段二，且届时删除前端 `utils/typewriter.js`。
- 根目录 `app.py`、`config/`、`core/` 的最终去留（spec 第十一节第 7 步后半，需用户决定）。
