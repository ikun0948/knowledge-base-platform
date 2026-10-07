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

# advisory ⑤（阶段一终审顺延清单第 5 条）：原先 SCANNED + SCANNED_DIRS 两份写死的清单
# 要求"加目录的人记得同时加这里"，那不是门禁。改成自动发现 backend 下所有 *.py。
# 排除四处：tests（测试里合法地 print 过、且它不是交付物）、__pycache__ 与 data（都不是源码）、
# .venv（2026-10-08 实测 backend/ 下没有它，列在这里是纯预防：有人在这儿建虚拟环境时，
# site-packages 不该进扫描面——那会让门禁一夜之间扫出几百个第三方文件）。
EXCLUDED_DIRS = {"tests", "__pycache__", "data", ".venv"}

CFG = SimpleNamespace(MYSQL_USER="u", MYSQL_PASSWORD="p", MYSQL_HOST="localhost",
                      MYSQL_PORT=3306, MYSQL_DATABASE="mydb")


def _backend_py_files():
    return sorted(
        path for path in BACKEND_DIR.rglob("*.py")
        if not any(part in EXCLUDED_DIRS for part in path.relative_to(BACKEND_DIR).parts)
    )


def _print_calls(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [node.lineno for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"]


def test_backend_sources_have_no_bare_print():
    files = _backend_py_files()
    # 下界而不是等号：新增文件不该让门禁红，但"某天 rglob 一个都没找到"必须是红的。
    # 2026-10-08 实测扫到 23 个（阶段二 Task 4 的 core/llm_factory.py 在列），下界取 22 留一格余量。
    assert len(files) >= 22, [str(f.relative_to(BACKEND_DIR)) for f in files]
    offenders = {str(f.relative_to(BACKEND_DIR)): _print_calls(f) for f in files}
    assert {k: v for k, v in offenders.items() if v} == {}


def test_scan_actually_reaches_every_source_dir():
    """自动发现的口径必须真的扫到每个源目录，否则"零违规"是空集给的假绿。

    写死的清单漏的正是这件事（advisory ⑤）：新增一个目录不会有人想起来改它。
    这条判据把"扫到了谁"从副作用升成判据本体。
    """
    rels = {str(f.relative_to(BACKEND_DIR)).replace("\\", "/") for f in _backend_py_files()}
    for must in ("main.py", "deps.py", "core/database.py", "core/llm_factory.py",
                 "api/chat.py", "api/auth.py", "schemas/auth.py", "config/config.py"):
        assert must in rels, must


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
