# Task 1 报告：backend 骨架 + 配置层（spec 7.1）

分支：`feat/backend-split`（未切换）
提交：`533e78c2443116210e86c65532477e25fbddb3b9` — `feat(backend): 骨架与配置层，.env 定位脱离 cwd`
状态：DONE（3 passed，工作区干净）
解释器：`D:\python\python.exe` (3.12.3)，PATH 上的 `python`；未使用 `D:/AI-python/.venv`；未安装/升级任何包。

---

## 一、逐文件产出

### 新建（本次提交，14 个文件，全部为新增，无修改项）

| 文件 | 动作 | 说明 |
|---|---|---|
| `D:/知识库平台-前后端分离/backend/config/config.py` | Create | Step 4 代码逐字复制：`BASE_DIR`/`ENV_FILE` 由本文件位置推导；缺 `.env` 抛 RuntimeError；`CHROMA_PERSIST_DIR` 非绝对路径抛 RuntimeError；`Config` 属性名与旧 `config/config.py` 一致 |
| `D:/知识库平台-前后端分离/backend/config/__init__.py` | Create | 空（Step 1 `touch`） |
| `D:/知识库平台-前后端分离/backend/core/database.py` | Copy | 与 `core/database.py` 逐字节相同（`cmp -s` 校验通过） |
| `D:/知识库平台-前后端分离/backend/core/document_processor.py` | Copy | 同上 |
| `D:/知识库平台-前后端分离/backend/core/vector_store.py` | Copy | 同上 |
| `D:/知识库平台-前后端分离/backend/core/rag_system.py` | Copy | 同上 |
| `D:/知识库平台-前后端分离/backend/core/__init__.py` | Create | 空 |
| `D:/知识库平台-前后端分离/backend/schemas/__init__.py` | Create | 空（Step 1 建目录，Task 6 填充） |
| `D:/知识库平台-前后端分离/backend/api/__init__.py` | Create | 空（Step 1 建目录，Task 3 填充） |
| `D:/知识库平台-前后端分离/backend/tests/__init__.py` | Create | 空 |
| `D:/知识库平台-前后端分离/backend/tests/conftest.py` | Create | Step 5：把 `backend/` 插入 `sys.path[0]`，使从项目根跑测试也能 `import config`/`core` |
| `D:/知识库平台-前后端分离/backend/tests/test_config.py` | Create | Step 2 的 3 个测试，逐字复制 |
| `D:/知识库平台-前后端分离/backend/.env.example` | Create | Step 6 模板，12 个键，无真实值 |
| `D:/知识库平台-前后端分离/requirements.txt` | Create | Step 7 内容逐字复制 |

### 新建但不入库（.gitignore 已排除，未 `-f` 强加）

- `D:/知识库平台-前后端分离/backend/.env` — Step 6 脚本生成，**12 个键**（`写入键数: 12`），无空值键；`CHROMA_PERSIST_DIR=D:/知识库平台-前后端分离/backend/data/chroma_db`（绝对路径、POSIX 分隔）。`git check-ignore` 确认命中 `.gitignore:9`。
- `D:/知识库平台-前后端分离/backend/data/`（空目录）— 命中 `.gitignore:12`。`backend/data/chroma_db` 尚未创建，属 Task 2。

### 未触碰（已用 git 验证）

`git diff --name-status 3e28870..HEAD` 只有 `A`（新增），没有任何 `M`。`app.py`、`config/`、`core/`、`streamlit页面.py`、`知识库平台开发文档.md`、`docs/`、`.gitignore` 均与基线一致。`D:/AI-python/.env` 只读，未写入。

---

## 二、TDD 过程与实测输出

### Step 3：先失败（写实现之前）

命令：

```
cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests/test_config.py -v
```

尾部输出（关键行）：

```
tests\test_config.py:2: in <module>
    from config.config import Config
E   ModuleNotFoundError: No module named 'config.config'
=========================== short test summary info ===========================
ERROR tests/test_config.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
============================== 1 error in 0.50s ===============================
```

与预期一致。

### Step 8：实现后通过

命令：

```
cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests/test_config.py -v
```

完整尾部输出：

```
============================= test session starts =============================
platform win32 -- Python 3.12.3, pytest-9.0.2, pluggy-1.6.0 -- D:\python\python.exe
cachedir: .pytest_cache
metadata: {'Python': '3.12.3', 'Platform': 'Windows-11-10.0.26200-SP0', 'Packages': {'pytest': '9.0.2', 'pluggy': '1.6.0'}, 'Plugins': {'anyio': '4.14.2', 'langsmith': '0.12.1', 'platformdirs': '4.12.1', 'html': '4.2.0', 'metadata': '3.1.1'}, 'JAVA_HOME': 'D:\\program\\lzhjdk8'}
rootdir: D:\AI-python\知识库平台\backend
plugins: anyio-4.14.2, langsmith-0.12.1, platformdirs-4.12.1, html-4.2.0, metadata-3.1.1
collecting ... collected 3 items

tests/test_config.py::test_chroma_dir_is_absolute PASSED                 [ 33%]
tests/test_config.py::test_env_file_is_located_by_file_position_not_cwd PASSED [ 66%]
tests/test_config.py::test_required_keys_present PASSED                  [100%]

============================== 3 passed in 0.03s ===============================
```

### 附加验证（超出 brief 要求，只读/只跑，无文件改动）

1. **从项目根跑同样通过**（这正是 conftest 的用途，Task 3+ 大概率从根跑）：
   `cd "D:/知识库平台-前后端分离" && python -m pytest backend/tests/test_config.py -v` → `3 passed in 0.04s`（rootdir 变为项目根，`config` 仍解析到 `backend/config`，未被旧 `config/` 遮蔽，因为 conftest 把 `backend/` 放在 `sys.path[0]`）。
2. **接口契约**：`Config()` 可无参实例化（旧代码的调用姿势不变）；`Config` 实例属性集合与旧 `config/config.py` 的属性名 **完全一致**（脚本比对：`old only: []`，`new only: ['_chroma']`，`_chroma` 是 brief 代码里的类内校验临时名）；模块级 `BASE_DIR = D:\AI-python\知识库平台\backend`、`ENV_FILE = backend/.env` 已导出。
3. **`backend/core/` 四模块确实互不引用**：grep `^\s*(from|import)\s+(core|config|\.)` 无命中，且文件内无 `streamlit` / `st.` 字样 —— 与 brief Step 1「复制后不需要改任何 import」一致。
4. **requirements.txt 的版本约束与实机一致**（`importlib.metadata` 实测，未安装/升级）：fastapi 0.141.1、uvicorn 0.52.4、python-multipart 0.0.32、python-dotenv 1.2.3、sqlalchemy 2.0.52、PyMySQL 1.1.1、chromadb 1.5.9、langchain-core 1.6.1、langchain-openai 1.1.9、langchain-chroma 1.1.0、langchain-huggingface 1.2.2、langchain-text-splitters 1.1.2、langchain-community 0.3.31、langchain-classic 1.0.8、sentence-transformers 6.0.1、pypdf 6.16.2、docx2txt 0.9、pytest 9.0.2、httpx 0.28.1。全部满足文件里的下界。

---

## 三、与 brief 的偏差（及原因）

1. **Step 9 的 `git add` 清单漏了 Step 1 自己创建的两个骨架文件**。brief 只列了 `backend/config backend/core backend/tests requirements.txt backend/.env.example .gitignore`，未含 `backend/api/__init__.py`、`backend/schemas/__init__.py`（Step 1 的 `touch` 产物）。我仍把它们一并提交了：否则 Task 3 写 `backend/api/*.py`、Task 6 写 `backend/schemas/*.py` 时，新克隆的仓库里这两个目录不存在（空目录 git 也不跟踪），骨架在 git 里是残缺的。提交内容与 brief 的消息、作者（`-c user.name/-c user.email`）完全一致，只多了这 2 个空文件。
2. **`backend/.env` 里 `LOCAL_MODEL_PATH` 这一行带一个键名后的空格**（形如 `LOCAL_MODEL_PATH =D:\...`）。原因：Step 6 脚本按 brief 逐字运行，共用 `D:/AI-python/.env` 源文件里该键名本身带尾随空格（过滤时用了 `.strip()` 匹配，但写出的是原始行）。已实测 python-dotenv 会剥离键名空白，`os.getenv("LOCAL_MODEL_PATH")` 正常取值，`test_required_keys_present` 通过。为了让 brief 的脚本保持逐字，未做规范化改写。
3. **Step 9 的 `.gitignore` 参数是空操作**：`.gitignore` 在基线提交里就已包含 `backend/.env`、`backend/data/`（本次无需改动，工作区里它也没有 diff），所以 `git add .gitignore` 没带来任何暂存内容。
4. **Step 3 的失败形态是收集期 ImportError**（`ModuleNotFoundError: No module named 'config.config'`），正是 brief 给的两种预期之一（当时 `.env` 与 config 都还不存在）。
5. 其余全部逐字照抄：`config.py`、`test_config.py`、`conftest.py`、`.env.example`、`requirements.txt`、`.env` 生成脚本、注释与中文提示语均未增删。

补充：`python -m pytest` 会在 `backend/.pytest_cache/` 与根 `.pytest_cache/` 落盘，pytest 自身在其中写了 `.gitignore`（内容 `*`），因此 `git status` 依然干净，无需额外忽略规则；`__pycache__/` 已在 `.gitignore`。

---

## 四、对后续 Task 的提醒 / 隐患

1. **Task 2 是唯一还没满足的前提**：`backend/data/chroma_db` 目前不存在（`Path(Config.CHROMA_PERSIST_DIR).exists()` 为 False）。配置层对此不报错（只校验绝对路径），所以 Task 2 搬库前若有测试去查集合数量会拿到 0，别误判为回归。
2. **`Config` 默认值与旧文件有一处刻意的差别**：`MYSQL_PASSWORD` 默认从旧的 `"123456"` 改成 `""`（brief 如此）。真实值来自 `backend/.env`，运行时行为不变；但任何"脱离 .env 跑默认值"的测试会看到空密码。
3. **`backend/core/*.py` 仍是带已知 bug 的逐字副本**：时间戳默认值、被吞掉的异常、以及需要和 Streamlit 解耦的签名（grep 显示这四个文件内部其实没有 `st.` 调用，耦合在 `app.py` 侧，Task 4 请以此为起点）都在 Task 3–6 处理，本任务一行未改。
4. **旧 `config/` 与新 `backend/config/` 在 git 里同名共存**，从项目根跑测试时靠 conftest 的 `sys.path.insert(0, backend)` 抢占。若 Task 3+ 有人加 `pytest.ini`/`pyproject.toml` 改 import 模式（如 `importmode=importlib`）或把 `backend/tests/__init__.py` 删掉，请重跑 Step 8 那条从根执行的命令，确认没有遮蔽回退到旧 `config/config.py`（旧文件 `load_dotenv()` 读 cwd，会让 `test_chroma_dir_is_absolute` 失败——那其实是很有用的哨兵）。
5. **`.env` 是手工从共用文件摘出来的**，日后共用 `D:/AI-python/.env` 里的 MySQL/DASHSCOPE 值变更不会自动同步到 `backend/.env`；`backend/.env.example` 是唯一可信的键清单（正好 12 键）。
6. Task 3 若要加 `backend/main.py`，请从 `config.config` 导入 `Config`（不要复制 `BASE_DIR` 逻辑）；`BASE_DIR` 现可用于定位 `backend/` 下的静态资源。

---

## Fix round 1

评审结论：生产代码通过，测试质量 Needs fixes。本轮只动测试与两条 Minor 的实现细节，不改架构、不动 Task 3–6 的范围。

分支：`feat/backend-split`（未切换）
提交：`4b0f750` — `test(backend): 让配置层守卫与 cwd 无关性真正可回归`（新提交，未 `--amend`，未跳 hook）
状态：DONE。`7 passed`，输出干净（无新增 warning）。

### 一、起点状态说明

接手时工作区已有一条**未提交**的 `backend/config/config.py` 改动（Minor 3、4 的修法：把校验挪进模块函数 `_chroma_persist_dir()`，区分"键缺失"与"值相对"）。我逐行核对了它与 brief 的 12 个属性名/值一致，予以保留，并补上它缺的回归测试，一并提交。`backend/tests/test_config.py` 当时仍是 `533e78c` 的版本。

### 二、Important 1：cwd 无关性测试

原测试 `monkeypatch.chdir(tmp_path)` 后再 `from config import config as config_module` —— 模块已在 `sys.modules`（同文件模块级 import 过），什么都没重算，把 `BASE_DIR` 换成 `Path.cwd()` 也不会红。

改法：子进程执行。`_run_import(tmp_path, BACKEND_DIR, "from config import config as c; print(c.BASE_DIR); print(c.ENV_FILE); print(c.ENV_FILE.exists())")`，cwd 落在与项目无关的 `tmp_path`，`PYTHONPATH` 指到 `backend/`。断言三行输出分别等于 `BACKEND_DIR`、`BACKEND_DIR/.env`、`True`。选子进程而不是 `importlib.reload`，是为了不污染已加载的模块状态（父进程的 `Config` 被其它测试共用），也顺带覆盖"从别处启动"的真实形态。

变异验证（`BASE_DIR = Path.cwd()`）→ **1 failed**，且恰好只红在 `test_env_file_is_located_by_file_position_not_cwd`（子进程 `RuntimeError: 缺少配置文件 C:\...\Temp\pytest-...\test_env_file_is_located_by_fi0\.env`）。恢复后 7 passed。

### 三、Important 2：绝对路径守卫可回归

删掉了 `test_chroma_dir_is_absolute`（断言与守卫是同一个表达式，属于同义反复），换成三条真回归：

| 测试 | 手段 | 覆盖 |
|---|---|---|
| `test_relative_chroma_dir_is_rejected` | 真 `backend/` 目录起子进程，进程环境塞 `CHROMA_PERSIST_DIR=data/chroma_db` | 守卫本体；依赖 `load_dotenv` 默认不覆盖已设置的进程环境变量（测试里有单行 why 注释标注这是 load-bearing 前提） |
| `test_relative_chroma_dir_in_env_file_is_rejected` | 临时 backend 树，`.env` 里写相对值 | 守卫拦的是**最终生效值**，写在 `.env` 里同样拦 |
| `test_missing_chroma_dir_key_says_missing` | 临时 backend 树，`.env` 里**没有**这个键 | Minor 4：缺键必须报"未设置"，不能报"必须是绝对路径 当前为 ''" |

后两条走临时树：把**当前** `config.py` 源码 `shutil.copyfile` 到 `tmp/config/config.py`，再写一份受控 `.env`。这样 `.env` 内容可控，而 `ENV_FILE` 由文件位置推导出来正好落在临时目录，不必改 `backend/.env`。`_child_env()` 会从继承环境里剔掉 `CHROMA_PERSIST_DIR`（否则"键缺失"用例失真），并固定 `PYTHONIOENCODING=utf-8`（守卫消息含中文，stderr 编码不固定会让断言误判）。

变异验证（删掉 `if not raw or not Path(raw).is_absolute()` 那两行）→ **2 failed**（两条相对路径用例同时红，`assert 0 != 0`）。恢复后 7 passed。

### 四、Minor 3 / Minor 4

- Minor 3：`_chroma` 不再成为类属性（校验移进模块函数，`return raw`）。配套 `test_config_class_exposes_only_sanctioned_attrs`：`{n for n in vars(Config) if not n.startswith("__")} == SANCTIONED_ATTRS`（类的命名空间一定带 `__module__`/`__qualname__`/`__doc__`/`__dict__`/`__weakref__`，所以要滤掉双下划线，否则测试会因为无关原因红）。12 个公开属性名与值未改。
- Minor 4：`raw is None` 单独报"未设置：{ENV_FILE} 里没有这个键，参考 backend/.env.example 补齐"；`not raw or not Path(raw).is_absolute()` 才报"必须是绝对路径"。

变异验证（把 `config.py` 临时回退成 `533e78c` 原版）→ **2 failed**：`test_missing_chroma_dir_key_says_missing`（原版对缺键报 `必须是绝对路径，当前为 ''`）与 `test_config_class_exposes_only_sanctioned_attrs`（`Extra items in the left set: '_chroma'`）。恢复后 7 passed。也就是说这两条 Minor 现在也有哨兵，不会静默退回。

### 五、实测命令与结果

```
cd D:/知识库平台-前后端分离/backend && python -m pytest tests/test_config.py -v   # 7 passed in 0.36s（基线）
# 变异 A：删守卫       → 2 failed, 5 passed   # 恢复 → 7 passed
# 变异 B：Path.cwd()   → 1 failed, 6 passed   # 恢复 → 7 passed
# 变异 C：回退 533e78c → 2 failed, 5 passed   # 恢复 → 7 passed
cd D:/知识库平台-前后端分离 && python -m pytest backend/tests/test_config.py       # 7 passed in 0.43s（从根跑同样过）
```

测试文件顶部 `from config import config as config_module` 需要 `backend/` 在 `sys.path`，从根跑时由 `conftest.py` 的 `sys.path.insert(0, backend)` 保证，与第二节一致。

### 六、工作区还原确认

`backend/.env` 是 gitignore 的，`git status` 看不见它，变异实验期间全程按 sha256 核对：

- `backend/config/config.py`：`ecd4479c…b12`，三次变异后 `cp` 还原，逐次比对为 `True`（提交里的内容即此哈希）。
- `backend/.env`：`70b56437…153`，从头到尾 `True`。**本轮从未改写 `backend/.env`** —— 相对值走进程环境变量覆盖，缺键/相对值走临时树，因此不存在"忘了还原 gitignored 文件"的风险。
- `git status --short` 在提交前只有 ` M backend/config/config.py`、` M backend/tests/test_config.py`；提交后为空。
- `backend/core/*.py` 与根 `core/` 四个文件 `cmp -s` 全部 identical（本任务一行未改）。
- 临时备份放在 `C:/Users/31439/AppData/Local/Temp/`，用完已删，未进入仓库。

### 七、未做 / 注意事项

1. 明确不在范围的都没动：`load_dotenv` 未加 `override=True`；`backend/.env` 的 `LOCAL_MODEL_PATH `（键名尾随空格）未规范化；根 `app.py`、根 `config/`、根 `core/`、`.gitignore`、`requirements.txt`、`backend/.env.example` 未触碰；未新增 `MYSQL_*`/`CHUNK_*`/`TOP_K` 取值断言。
2. `test_relative_chroma_dir_is_rejected` 读的是**真实** `backend/.env`：它要求 `.env` 存在（否则子进程先撞"缺少配置文件"那条 RuntimeError，消息断言会失败而红）。这是有意的——`.env` 缺失本来就是需要红的状态，且报错信息会直接指出缺文件。
3. 相对值用例里的 `data/chroma_db` 在 Windows/Linux 上 `Path(...).is_absolute()` 都是 False，跨平台一致；没有用 `../x` 之类的写法，避免 `Path` 规范化差异。
4. 子进程约 4 个，整套 0.36–0.45s，成本可忽略。Task 3+ 若把测试扩到几百条，这几条仍然便宜。
5. 后续 Task 请继续沿用"改守卫必须让套件变红"这条标准：新增配置键时，同步把 `SANCTIONED_ATTRS` 补全，否则 `test_config_class_exposes_only_sanctioned_attrs` 会红（那是它该有的反应）。
6. 第四节 4. 那条"旧 `config/` 遮蔽新 `backend/config/` 会让 `test_chroma_dir_is_absolute` 失败"的哨兵说明，按测试名已经过时（本轮删了那条同义反复的用例）。遮蔽场景现在由更强的两处兜住：测试文件模块级的 `CONFIG_SRC = Path(config_module.__file__)` 和 `test_env_file_and_base_dir_are_exported` 都依赖 `BASE_DIR`/`ENV_FILE`，而根 `config/config.py` 没有这两个名字——一旦被遮蔽，整个文件在收集期就报错，比单条用例红更响。

