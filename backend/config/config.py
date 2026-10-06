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


# 校验放在模块函数里：类体内的临时名会泄漏成 Config 的幽灵属性（后续按属性集做注入时会被误读）
def _chroma_persist_dir() -> str:
    raw = os.getenv("CHROMA_PERSIST_DIR")
    if raw is None:
        raise RuntimeError(
            f"CHROMA_PERSIST_DIR 未设置：{ENV_FILE} 里没有这个键，参考 backend/.env.example 补齐"
        )
    if not raw or not Path(raw).is_absolute():
        raise RuntimeError(f"CHROMA_PERSIST_DIR 必须是绝对路径，当前为 {raw!r}（坑 2）")
    return raw


class Config:
    OPENAI_API_KEY = os.getenv("DASHSCOPE_API_KEY")
    OPENAI_BASE_URL = os.getenv("DASHSCOPE_BASE_URL")
    # 坑 9：答题与压缩两处共用这一个值。属调参键（同 TOP_K/CHUNK_SIZE），缺配置走默认，
    # 不像 CHROMA_PERSIST_DIR 那样缺键就炸——换模型不该变成起不动服务。
    LLM_MODEL = os.getenv("LLM_MODEL", "qwen3.7-flash")
    LOCAL_MODEL_PATH = os.getenv("LOCAL_MODEL_PATH")

    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
    MYSQL_USER = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "mydb")

    CHROMA_PERSIST_DIR = _chroma_persist_dir()

    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 1000))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 200))
    TOP_K = int(os.getenv("TOP_K", 5))
