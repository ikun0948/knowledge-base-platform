import os
import shutil
import subprocess
import sys
from pathlib import Path

from config import config as config_module
from config.config import Config

BACKEND_DIR = Path(__file__).resolve().parents[1]
CONFIG_SRC = Path(config_module.__file__)
SANCTIONED_ATTRS = {
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "LOCAL_MODEL_PATH",
    "MYSQL_HOST",
    "MYSQL_PORT",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "MYSQL_DATABASE",
    "CHROMA_PERSIST_DIR",
    "CHUNK_SIZE",
    "CHUNK_OVERLAP",
    "TOP_K",
}


def _child_env(**extra):
    # 继承的 CHROMA_PERSIST_DIR 会让键完全缺失那条用例失真，子进程里先剔掉
    env = {k: v for k, v in os.environ.items() if k != "CHROMA_PERSIST_DIR"}
    # 守卫消息含中文，子进程 stderr 编码不固定时断言会误判
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(extra)
    return env


def _run_import(cwd, python_path, code="import config.config", **extra_env):
    """在子进程 import 配置模块：父进程 sys.modules 里它已加载，reload/chdir 测不到真实行为。"""
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=cwd,
        env=_child_env(PYTHONPATH=str(python_path), **extra_env),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def _run_import_with_env_file(tmp_path, dotenv_text):
    """用当前 config.py 源码加受控 .env 搭一个临时 backend/，改写真实 .env 会牵连配置文件。"""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "__init__.py").write_text("", encoding="utf-8")
    shutil.copyfile(CONFIG_SRC, tmp_path / "config" / "config.py")
    (tmp_path / ".env").write_text(dotenv_text, encoding="utf-8")
    return _run_import(tmp_path, tmp_path)


def test_env_file_is_located_by_file_position_not_cwd(tmp_path):
    """spec 7.1：配置来源必须与 cwd 无关，BASE_DIR 改成 Path.cwd() 时这条要变红。"""
    result = _run_import(
        tmp_path,
        BACKEND_DIR,
        "from config import config as c; print(c.BASE_DIR); print(c.ENV_FILE); print(c.ENV_FILE.exists())",
    )
    assert result.returncode == 0, result.stderr
    base_dir, env_file, env_exists = [line.strip() for line in result.stdout.splitlines()]
    assert Path(base_dir) == BACKEND_DIR
    assert Path(env_file) == BACKEND_DIR / ".env"
    assert env_exists == "True"


def test_relative_chroma_dir_is_rejected():
    """坑 2：删掉 config.py 的绝对路径守卫，这条必须变红。"""
    result = _run_import(BACKEND_DIR, BACKEND_DIR, CHROMA_PERSIST_DIR="data/chroma_db")
    # 依赖 load_dotenv 默认不覆盖已设置的进程环境变量，相对值才能活到守卫里
    assert result.returncode != 0, result.stdout
    assert "CHROMA_PERSIST_DIR 必须是绝对路径" in result.stderr


def test_missing_chroma_dir_key_says_missing(tmp_path):
    """键完全不存在时要报未设置，报成必须是绝对路径会让用户去补一个本来就在的键。"""
    result = _run_import_with_env_file(tmp_path, "DASHSCOPE_API_KEY=x\nMYSQL_DATABASE=mydb\n")
    assert result.returncode != 0, result.stdout
    assert "CHROMA_PERSIST_DIR 未设置" in result.stderr


def test_relative_chroma_dir_in_env_file_is_rejected(tmp_path):
    """守卫拦的是最终生效值：写在 .env 里的相对路径同样要拦下。"""
    result = _run_import_with_env_file(tmp_path, "DASHSCOPE_API_KEY=x\nCHROMA_PERSIST_DIR=data/chroma_db\n")
    assert result.returncode != 0, result.stdout
    assert "CHROMA_PERSIST_DIR 必须是绝对路径" in result.stderr


def test_config_class_exposes_only_sanctioned_attrs():
    """校验用的临时名不能泄漏成 Config 的幽灵属性，按属性集做注入时会被误读。"""
    assert {name for name in vars(Config) if not name.startswith("__")} == SANCTIONED_ATTRS


def test_env_file_and_base_dir_are_exported():
    """spec 7.1：后续 Task 复用模块级 BASE_DIR，不再自己推导 .env 位置。"""
    assert config_module.BASE_DIR == BACKEND_DIR
    assert config_module.ENV_FILE == BACKEND_DIR / ".env"
    assert config_module.ENV_FILE.is_file()


def test_required_keys_present():
    for key in ("OPENAI_API_KEY", "OPENAI_BASE_URL", "LOCAL_MODEL_PATH", "MYSQL_DATABASE"):
        assert getattr(Config, key)
