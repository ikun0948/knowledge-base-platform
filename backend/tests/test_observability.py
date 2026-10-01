"""spec 八节的验收面：print 清零、连接信息走 module logger。

Task 5 预检把最后两处无主 print 划给 Task 9（core/database.py:106,108），
这里同时钉住"别再出现 print"和"database 用的是 kb.database 这个 logger"。
"""
import ast
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from core import database
from core.database import DatabaseManager

BACKEND_DIR = Path(__file__).resolve().parents[1]
SCANNED = ["main.py", "deps.py", "exceptions.py"]
SCANNED_DIRS = ["api", "core", "schemas", "config"]

CFG = SimpleNamespace(MYSQL_USER="u", MYSQL_PASSWORD="p", MYSQL_HOST="localhost",
                      MYSQL_PORT=3306, MYSQL_DATABASE="mydb")


def _print_calls(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [node.lineno for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"]


def test_backend_sources_have_no_bare_print():
    files = [BACKEND_DIR / name for name in SCANNED]
    files += sorted(p for d in SCANNED_DIRS for p in (BACKEND_DIR / d).rglob("*.py"))
    offenders = {str(f.relative_to(BACKEND_DIR)): _print_calls(f) for f in files}
    assert {k: v for k, v in offenders.items() if v} == {}


@pytest.fixture
def fake_engine(monkeypatch):
    """create_engine 与 create_all 都不碰网络：这里测的是连接期怎么说话。"""
    calls = []
    monkeypatch.setattr(database, "create_engine", lambda *a, **k: calls.append("engine") or object())
    monkeypatch.setattr(database.Base.metadata, "create_all",
                        lambda bind: calls.append("create_all"))
    return calls


def test_connect_success_goes_to_the_logger_not_stdout(fake_engine, caplog, capsys):
    with caplog.at_level(logging.INFO, logger="kb.database"):
        DatabaseManager(CFG)
    assert capsys.readouterr().out == ""
    assert fake_engine == ["engine", "create_all"]
    assert [(r.name, r.levelno, r.getMessage()) for r in caplog.records] == [
        ("kb.database", logging.INFO, "数据库连接成功")
    ]


def test_connect_failure_logs_the_error_and_still_raises(monkeypatch, caplog, capsys):
    def boom(*args, **kwargs):
        raise RuntimeError("mysql 不可达")

    monkeypatch.setattr(database, "create_engine", boom)
    with caplog.at_level(logging.INFO, logger="kb.database"):
        with pytest.raises(RuntimeError):
            DatabaseManager(CFG)
    assert capsys.readouterr().out == ""
    records = [r for r in caplog.records if r.name == "kb.database"]
    assert [(r.levelno, r.getMessage()) for r in records] == [(logging.ERROR, "数据库连接失败")]
    assert "mysql 不可达" in caplog.text
