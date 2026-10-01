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

