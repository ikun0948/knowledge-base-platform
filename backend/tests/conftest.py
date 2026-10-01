import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
for path in (str(BACKEND_DIR), str(TESTS_DIR)):
    # tests/ 是包，pytest 只会把 backend/ 塞进 sys.path；fakes 按顶层名导入，得把本目录也补上
    if path not in sys.path:
        sys.path.insert(0, path)
