"""backend/tests 里的替身不许同名（阶段三 ③）。

开工前的形态（实测）：`tests/` 下 35 个类名里恰好重复 1 个 —— `FakeConfig`。
一枚在 `fakes.py:1`，只带 `/api/health` 读的 `CHROMA_PERSIST_DIR`；另一枚在
`test_migrations.py:182`，带 `run_migrations` 读的 `DEFAULT_USER_PASSWORD` +
`.env` 三键（`OPENAI_API_KEY`/`OPENAI_BASE_URL`/`LLM_MODEL`，见 `core/migrations.py:252-256`）。

两枚都叫 `FakeConfig`，代价不是跑错（形状不匹配会 AttributeError，响得很），是**读不出来**：
`grep -rn FakeConfig` 给两个定义，谁服务谁要靠点进各自的文件才知道；而"顺手合并同名重复"
是所有人的默认动作，这里一合并就把 `fakes.py` 那三键 `OPENAI_*` 又塞回交付面 ——
阶段二 Task 7 刚以「写了没人读的字段在本仓是负资产」为由把它们删掉（那份理由就写在
`fakes.py:2-4` 的注释里）。所以这一条钉的是**名字唯一**，不是"只许一枚 config 替身"：
两枚形状不同、各有各的消费者是正当的，重名才是缺陷。
"""
import ast
from collections import defaultdict
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent


def _fake_class_declarations():
    """返回 [(文件名, 行号, 类名)]，只收 `Fake*` 前缀的类声明。

    口径限定在 `Fake` 前缀：这一族的约定就是"生产码的替身"，名字应当全局唯一。
    其它辅助类（`_Result`、`FakeConn` 之外的私有小工具）不在本条射程内——
    把它们一起纳进来会让这条判据去管它不该管的私事。
    """
    found = []
    for path in sorted(TESTS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name.startswith("Fake"):
                found.append((path.name, node.lineno, node.name))
    return found


def test_no_two_modules_declare_the_same_fake_double():
    decls = _fake_class_declarations()
    assert decls, "扫描面一个 Fake* 替身都没抓到：目录挪窝或改名了，此时这条判据是空集假绿"

    by_name = defaultdict(list)
    for filename, lineno, name in decls:
        by_name[name].append((filename, lineno))

    duplicates = {name: sites for name, sites in by_name.items() if len(sites) > 1}
    assert duplicates == {}, (
        f"同名替身 {duplicates} —— 名字唯一才谈得上'看见名字就知道服务谁'；"
        "要消掉它请改名那枚局部替身，不要合并形状不同的两枚"
    )
