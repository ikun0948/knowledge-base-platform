# Task 2 报告：Chroma 数据搬家 + 计数基线

状态：**DONE_WITH_CONCERNS**（唯一问题：brief 写的源目录不存在，实际搬家源另有其路径，见"偏差"一节）
提交：`d72a054086733c18ca10e494e7a3cbfc2fbfb637`（分支 `feat/backend-split`）

---

## Step 1：复制数据目录

**brief 写的源目录 `D:/AI-python/core/chroma_db` 在本机上不存在**（`ls` 报 No such file or directory）。
全盘（`D:/AI-python` 下 maxdepth 6）搜索 `*chroma*` 目录，只有一个命中且有内容：

```
D:/AI-python/langchain框架/core/chroma_db
```

判定它就是"旧库"的三条证据：

1. `D:/AI-python/.env`（其它脚本共用的那份）里 `CHROMA_PERSIST_DIR=../core/chroma_db`，是相对 cwd 的路径；
   从 `D:/AI-python/langchain框架/codeXX` 启动时正好解析成上面这个目录。根目录 `config/config.py` 的默认值也是同一个相对串。
2. 里面正好是 `parent_document` / `child_document` 两个集合，计数 2 / 7，与 brief 的基线事实完全吻合。
3. 它的 mtime 是 `2026-09-30 21:51:54` / `21:53:26`，早于计划文档提交 `7849e66`（22:01:20），符合"计划写之前实测"的时间线。

执行的复制命令（只 cp，不 move / rename / delete；原目录全程未被打开过，只在复制完成后复核其 mtime 与哈希）：

```bash
cd "D:/知识库平台-前后端分离"
cp -r "D:/AI-python/langchain框架/core/chroma_db" backend/data/chroma_db
```

复制后的完整性核对（Python 逐文件 size + md5，不只看计数）：

| 侧 | 路径 | 文件数 | 总字节 | MiB |
|---|---|---|---|---|
| 源 | `D:/AI-python/langchain框架/core/chroma_db` | **9** | **1,245,512** | 1.19 |
| 目标 | `D:/知识库平台-前后端分离/backend/data/chroma_db` | **9** | **1,245,512** | 1.19 |

`ls backend/data/chroma_db`：

```
7ffdbec3-f523-4ff4-ba91-0b6e4be2f5e3/   (data_level0.bin 423600, header.bin 100, length.bin 400, link_lists.bin 0)
e5ecac39-b151-4ace-8fdd-c2f0482b9150/   (同上 4 个文件)
chroma.sqlite3                            397312
```

- **`chroma.sqlite3` 存在**（397,312 字节），两个 HNSW 段目录及其 4 个 bin 文件也都在。
- 复制瞬间（打开数据库之前）逐文件比对：文件名集合相同，**9/9 文件的 size 与 md5 全部一致**。
- 之后第一次用 `PersistentClient` 打开**目标**库，Chroma 自己回写了目标侧 `chroma.sqlite3`（size 仍是 397312，md5 变了）。
  这是打开持久化库的正常行为，不影响数据；8 个二进制索引文件仍然与源逐字节相同。
- 源目录复核：文件数 9、总字节 1,245,512 未变，`chroma.sqlite3` mtime 仍是 `2026-09-30 21:53:26`（我操作期间没有任何写入）。

## Step 2：`backend/tests/test_chroma_data.py`

内容与 brief 有两处不同（详见"偏差"）：计数走 `client.get_collection(name).count()`，另加一条 `chroma.sqlite3` 存在性前置断言。

## Step 3：运行

命令与完整尾部输出（interpreter 为 PATH 上的 `D:\python\python.exe` 3.12.3，未使用 `D:/AI-python/.venv`）：

```
$ cd "D:/知识库平台-前后端分离/backend" && PYTHONIOENCODING=utf-8 python -m pytest tests/test_chroma_data.py -v
============================= test session starts =============================
platform win32 -- Python 3.12.3, pytest-9.0.2, pluggy-1.6.0 -- D:\python\python.exe
cachedir: .pytest_cache
rootdir: D:\AI-python\知识库平台\backend
collected 1 item

tests/test_chroma_data.py::test_collection_counts_survived_the_move PASSED [100%]

============================== 1 passed in 0.77s ==============================
```

Task 1 未受影响（全量 8 条，含 `test_config.py` 的 7 条）：

```
$ cd "D:/知识库平台-前后端分离/backend" && PYTHONIOENCODING=utf-8 python -m pytest tests -v
collected 8 items

tests/test_chroma_data.py::test_collection_counts_survived_the_move PASSED [ 12%]
tests/test_config.py::test_env_file_is_located_by_file_position_not_cwd PASSED [ 25%]
tests/test_config.py::test_relative_chroma_dir_is_rejected PASSED        [ 37%]
tests/test_config.py::test_missing_chroma_dir_key_says_missing PASSED    [ 50%]
tests/test_config.py::test_relative_chroma_dir_in_env_file_is_rejected PASSED [ 62%]
tests/test_config.py::test_config_class_exposes_only_sanctioned_attrs PASSED [ 75%]
tests/test_config.py::test_env_file_and_base_dir_are_exported PASSED     [ 87%]
tests/test_config.py::test_required_keys_present PASSED                  [100%]

============================== 8 passed in 1.15s ==============================
```

实测计数：`{'parent_document': 2, 'child_document': 7}` —— 与基线常量一致，**没有改动任何常量去适配结果**。

## Step 4：提交

```
$ cd "D:/知识库平台-前后端分离" && git add backend/tests/test_chroma_data.py
$ git -c user.name="31439" -c user.email="31439@local" commit -m "test(backend): Chroma 搬家后集合计数与旧库一致"
[feat/backend-split d72a054] 1 file changed, 16 insertions(+)
 create mode 100644 backend/tests/test_chroma_data.py
```

入库文件清单（**只有 1 个文件**，`git diff --cached --name-only` 的输出）：

- `backend/tests/test_chroma_data.py`

未入库且已验证被忽略（`git check-ignore -v`）：

- `backend/data/chroma_db/**` → `.gitignore:12: backend/data/`
- `backend/.env` → `.gitignore:9: backend/.env`

没有使用 `git add -f`。提交后 `git status --short` 为空（工作区干净）。
其它约束核对：根 `app.py` / `config/` / `core/` 未改动；`backend/core/*.py` 与根 `core/*.py` 仍逐字节相同
（`diff -q` 对 database.py / document_processor.py / rag_system.py / vector_store.py 全部 OK）。

## 偏差（没能照 brief 字面执行的地方）

1. **源目录路径**：brief Step 1 的 `D:/AI-python/core/chroma_db` 不存在，命令原样执行会直接失败。
   实际源改为 `D:/AI-python/langchain框架/core/chroma_db`（判定依据见上）。
   后果：验收判据 1 的"旧库"参照物现在写死在这一节里 —— Task 10 归档 / 回退说明如果引用 `D:/AI-python/core/chroma_db`，需要同步改成这个路径。
2. **计数 API**：brief Step 2 的 `{c.name: c.count() for c in client.list_collections()}`。
   本环境 chromadb 1.5.9 的 `list_collections()` 确实返回 `chromadb.api.models.Collection.Collection` 对象且带 `count`，
   但按环境已验证事实（`langchain_chroma.Chroma` 无 `get_collection`）与计划 Task 3 的写法（`chroma_client.get_collection(COLLECTION_PARENT).count()`），
   测试改为 `client.get_collection(name).count()`，与后续 `/api/health` 用同一条路径，避免两处口径不同。
   保留了 brief 的"整字典相等"断言语义：字典的 key 来自 `list_collections()` 的实际集合名，所以多出第三个集合同样会变红。
3. **多加一条前置断言**（brief 没有）：`(Path(Config.CHROMA_PERSIST_DIR) / "chroma.sqlite3").is_file()`。
   原因是 `PersistentClient` 对不存在的目录会静默新建空库，没有这条就只能看到 `counts == {}`，看不出"目录根本没搬过来"。
4. **给 pytest 命令加了 `PYTHONIOENCODING=utf-8`**：Git Bash 下中文路径/输出编码不稳，只影响控制台可读性，不影响断言。
5. 未安装/升级任何包；未使用 `D:/AI-python/.venv`；未 `--amend`；未改 git 配置；未跳过 hook。

---

## Fix round 1

评审判定 Needs fixes（测试证明不了它声称的东西），本轮只改测试本身 + 它需要的 marker 落点，**没有**重做搬家、**没有**碰向量数据、**没有**改结构。
提交：**`bf2398d4b0db8f49a3fcf81c1444e3335551de03`**（`test(backend): 搬家校验改为身份比对且不再写入迁移后的库`，只含 2 个文件：`backend/tests/test_chroma_data.py`、新建 `backend/pytest.ini`）。

### 改了什么、为什么

| 评审条目 | 改动 | 为什么 |
|---|---|---|
| Important 1（路径没钉住） | 首条断言 `Path(Config.CHROMA_PERSIST_DIR).resolve() == BASE_DIR / "data" / "chroma_db"`，`BASE_DIR` 从 `config.config` import（Task 1 的 `test_config.py` 已覆盖它，不自己推导） | 原来只读 `Config.CHROMA_PERSIST_DIR` 并断言绝对路径，键改指搬家前的旧库 `D:/AI-python/langchain框架/core/chroma_db` 一样全绿 —— 测试其实在验证别的东西 |
| Important 2（计数看不出丢数据） | 保留 `PARENT_COUNT = 2` / `CHILD_COUNT = 7`（Task 3 `/api/health` 共用），新增模块级 `PARENT_IDS` / `CHILD_IDS`（迁移后的库实测、已排序），断言 `sorted(collection.get()["ids"]) == sorted(...)` | 少一行、多一行、或从同一份 docx 重建，计数断言都还是绿的；身份基线把"某集合有 2 条和 7 条"升级成"就是这几条活下来了" |
| Important 4（不 hermetic + 永久红陷阱） | ① 用 `shutil.copytree` 把库复制到 `tmp_path` 再开副本，套件不再写 `backend/data/chroma_db`；② 建 `backend/pytest.ini` 注册 `migration` 与 `live` 两个 marker，本测试打 `@pytest.mark.migration` | 开持久化库本身就是写（上一轮实测：复制 23:01:11，跑一次测试后 `chroma.sqlite3` mtime 变 23:04:16）。Task 5 的 `delete_by_ids`、Task 7 的上传、Task 9 的 live 测试都会合法改变集合内容，届时 2/7 + id 断言会永久红，而文件内唯一的出路就是 brief 禁止的"改常量" |
| Minor（裸断言无消息） | `assert sqlite.is_file(), f"{sqlite} 不存在：向量库未搬家，先把旧库复制进 backend/data/chroma_db"` | 失败时要直接说出路径和解法 |
| Minor（错的注释） | 计数改回 `c.count()`（直接用在 `list_collections()` 返回的 Collection 对象上），删掉 `get_collection` 那层间接与相关注释 | 实测本机 chromadb 1.5.9：`list_collections()` 返回 `chromadb.api.models.Collection.Collection`，`hasattr(c, "count")` 为 True，`{c.name: c.count()}` 得到 `{'child_document': 7, 'parent_document': 2}`。原来那条"必须用 get_collection"的理由站不住，注释就没了 —— 不留错注释 |

`pytest.ini` 只有 `[pytest]` + `markers =`（`migration`、`live` 各一行描述），**没有** `addopts`、没有任何 deselect：Task 9 要靠显式 `-m "not live"` / `-m live`，先注册 `live` 是为了 Task 9 不再另建一份 ini 撞车。marker 未注册就打标会出 `PytestUnknownMarkWarning`，所以 ini 先落地、再改测试。

`c.count()` 的可行性是在**旧库的临时副本**上验的（`shutil.copytree` 到 `%TEMP%`，只对副本开 `PersistentClient`），旧库全程 `os.stat`/`md5` 读取，未被打开。

### 捕获到的身份基线（迁移后的 `backend/data/chroma_db` 实测，非编造 UUID）

`parent_document`（2 条，排序后）：

```
a677b2f1-63b5-4836-aae5-c86355093902
e3985550-9937-42d9-a13a-acb7c75ca1ed
```

`child_document`（7 条，排序后）：

```
42d647ea-3be1-4d21-a5c5-ea0d760477af
584148b1-9a83-4336-bdcc-a491f2ea08c9
770d63d5-685b-4256-9916-1c19c1ba6cb3
7ab5915f-b357-4544-8f43-09d7366e1aaf
b2e1cbda-1235-486e-94c5-bc76a077f393
c276a890-fb5a-4bbd-8323-611e9ac238d3
ee6ccabc-d25a-49af-b843-f1ced132a151
```

写完后用一次性脚本（仓库外的 `%TEMP%` 下，用完已删）把测试文件里的字面量与捕获时的 dump 逐条比对：`PARENT_IDS == parent_document -> True`、`CHILD_IDS == child_document -> True`，两边都已是升序。

### 变异证明（先红后绿，改完恢复、工作区干净）

命令均为 `cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests/test_chroma_data.py -v`（未设 `PYTHONIOENCODING`）。

1. **改一条身份基线**：`CHILD_IDS[0]` 末位 `...60477af` → `...60477aa`。计数仍是 7/2，只有身份断言抓得到。红尾：

```
E       AssertionError: assert ['42d647ea-3b...ac238d3', ...] == ['42d647ea-3b...ac238d3', ...]
E         At index 0 diff: '42d647ea-3be1-4d21-a5c5-ea0d760477af' != '42d647ea-3be1-4d21-a5c5-ea0d760477aa'
tests\test_chroma_data.py:44: AssertionError
FAILED tests/test_chroma_data.py::test_collection_identity_survived_the_move
============================== 1 failed in 1.24s ==============================
```

2. **改一个计数常量**：`PARENT_COUNT = 2` → `3`。红尾：

```
E         Differing items:
E         {'parent_document': 2} != {'parent_document': 3}
tests\test_chroma_data.py:39: AssertionError
FAILED tests/test_chroma_data.py::test_collection_identity_survived_the_move
============================== 1 failed in 1.28s ==============================
```

3. **把路径改指搬家前的旧库**（Important 1 的针对性变异：`os.environ["CHROMA_PERSIST_DIR"] = "D:/AI-python/langchain框架/core/chroma_db"` 后跑同一条测试；旧库绝对路径能过 `config.py` 的守卫，所以这正是原测试漏掉的口子）。红尾：

```
>       assert Path(Config.CHROMA_PERSIST_DIR).resolve() == BASE_DIR / "data" / "chroma_db"
E       AssertionError: assert WindowsPath('D:/AI-python/langchain框架/core/chroma_db') == ((WindowsPath('D:/知识库平台-前后端分离/backend') / 'data') / 'chroma_db')
tests\test_chroma_data.py:31: AssertionError
============================== 1 failed in 1.12s ==============================
```

路径钉死在**第一条**断言，所以这条变异连 `copytree` 都没走到，旧库只被 `os.stat`/`md5` 读过：`OLD-SQLITE-BEFORE`/`OLD-SQLITE-AFTER` 完全相同（size 397312，mtime `2026-09-30 23:04:16.290107`，md5 `c95cfd5df9688b32a81e9820cc95752e`）。

恢复后绿尾（全量 8 条 = Task 1 的 7 条 + 本条）：

```
tests/test_chroma_data.py::test_collection_identity_survived_the_move PASSED [ 12%]
tests/test_config.py::test_required_keys_present PASSED                  [100%]
============================== 8 passed in 1.18s ==============================
```

marker 选择也验过：`-m migration` → `1 passed, 7 deselected`；`-m "not migration"` → `7 passed, 1 deselected`（Task 5/7/9 改动集合内容后可这样跳过搬家证明）；`-m live` → `8 deselected`，无 `PytestUnknownMarkWarning`。
`git status --short` 在变异恢复并提交后均为空。

### 最终一次跑测：迁移后的库没有被写（`chroma.sqlite3` mtime 前后不变）

一次性脚本（放在仓库外的 `%TEMP%`，跑完已删）做法是：对 `backend/data/chroma_db` 全树 9 个文件取 `(size, mtime_ns, md5)` 快照 → 用 `subprocess` 跑一次**原样**的 `python -m pytest tests -v`（该 shell 里 `PYTHONIOENCODING` 为空，也不在脚本里设置）→ 再取一次快照并比较。要复现：`rglob` 两次快照夹一次 `subprocess.run([sys.executable, "-m", "pytest", "tests", "-v"], cwd=backend)` 即可。

`chroma.sqlite3`：

| 时点 | size | mtime | md5 |
|---|---|---|---|
| BEFORE | 397312 | **2026-09-30 23:04:16.220001** | `f0f3eed26d761196c63a3f3c0808797b` |
| AFTER | 397312 | **2026-09-30 23:04:16.220001** | `f0f3eed26d761196c63a3f3c0808797b` |

mtime 没有前进（对比上一轮"跑一次就变 23:04:16"的行为），pytest 退出码 0 / `8 passed`，`STORE TREE IDENTICAL: True` —— 两个 HNSW 段的 8 个 bin 文件 size/mtime_ns/md5 也逐一相同，副本没写回、也没在源目录留下 journal/wal 之类新文件（目录列举仍只有 3 项）。

### 顺带的事实纠正（docs 本轮不许改，留给后续）

`98b5bbc` 写进计划文档的那句"`list_collections()` 返回的对象在本机 chromadb 1.5.9 上没有 `count()`，必须用 `client.get_collection(name).count()`"**是错的**（上面已实测有 `count()` 且能用），本轮测试已按 brief 原写法用 `c.count()`。Task 3 的 `/api/health` 代码片段若沿用 `get_collection(...).count()` 也不算错，但别把那句错误论据抄进新的注释。

### 本轮未做 / 边界

- 未重新搬家、未删改 `backend/data/` 下任何内容（只读）；未动根 `app.py`、根 `config/`、根 `core/`、`backend/core/*.py`、`backend/config/config.py`、`backend/tests/test_config.py`、`backend/.env`、`.gitignore`、`requirements.txt`、`docs/`。
- 未安装/升级任何包；未用 `D:/AI-python/.venv`；新建一个 commit（非 `--amend`）；未改 git 配置；未跳过 hook。
- 探针脚本与临时库副本都在 `%TEMP%` 下（仓库外），跑完已删除，`git status --short` 为空。
