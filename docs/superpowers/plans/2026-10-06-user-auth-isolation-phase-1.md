# 用户注册登录与数据按用户隔离 · 阶段一 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让平台从"一个匿名会话"变成"多个登录用户，各管各的文档"——注册/登录/登出/`GET /me` 四个端点、一枚可吊销的不透明令牌、8 个业务端点全部上登录门、`documents` 按用户归属过滤，前端未登录只显示登录页、左下角换成头像+昵称+设置按钮。

**Architecture:** 后端加两张表（`users` / `auth_tokens`）与一个纯标准库的口令/令牌模块（`core/security.py`，pbkdf2 + SHA-256），认证走 `Authorization: Bearer <token>` → 库里只存令牌哈希 → `deps.get_current_user` 返回 ORM `User`；归属隔离用**服务端硬校验**（每条 SQL 都带 `user_id`，越权回 404 不回 403），向量层**只补 `user_id` 元数据戳**不做读侧过滤（读侧过滤在阶段二，理由见 spec 2.5 勘误）。启动期一次性改造放在 `core/migrations.py`，由 `lifespan` 调用、每次开机重跑、全程幂等。前端不引 vue-router、不引 Pinia：`useAuth` 持模块级 `user` ref，`App.vue` 用 `v-if` 在登录页与应用壳之间整屏切换，令牌由 `client.js` 的模块级 `setAuthToken()` 统一注入三条网络出口。

**Tech Stack:** FastAPI 0.141 + SQLAlchemy 2.0.52（legacy `session.query` 写法沿用现仓）+ Pydantic 2.13 + chromadb 1.5.9；Vue 3 `<script setup>` + 原生 CSS + vitest 5 / @vue/test-utils。

**Spec:** `docs/superpowers/specs/2026-10-06-user-auth-isolation-design.md`。**本计划以它的第 8 节"阶段一"为边界，并携带 2026-10-06 那六条"计划期勘误"**——勘误改写了 spec 原文的四处归属（`chat_history.user_id` → 阶段二、读侧 `$and` 过滤 → 阶段二、`.env` 三键抄送 → 阶段二、`GET /me` 去掉 `session_id_present`）、一处调用位置（迁移从 `init_database` 改钉 `lifespan`，因为 `test_observability.py:50` 钉死 init 只发两次调用，而补戳又需要 `vector_store`）、以及两处实数（`SANCTIONED_ATTRS` 加两项、`make_client` 定义是 5 处）。两份必须一起读，冲突时**以勘误块为准**。

---

## Global Constraints

- **提交身份**：本机无 `user.name`/`user.email`，每条提交都用 `git -c user.name="31439" -c user.email="31439@local" commit`。**禁止 `--amend`、禁止 `--no-verify`**；一次提交只做一件事，消息用本仓现有中文 conventional 风格（`feat(backend): …` / `test(frontend): …` / `docs(ledger): …`）。
- **解释器**：一律用 PATH 上的 `python`（`D:\python\python.exe` 3.12.3，依赖已装全）。**不要用** `D:/AI-python/.venv`，也不要用 PyCharm 给每个项目自动建的 `.venv`（那里只有 pip）。
- **`.env` 纪律**：后端读的是 `backend/.env`。本计划**只往它追加一行** `DEFAULT_USER_PASSWORD=…`（Task 1 Step 6）；`D:/AI-python/.env` 是别的脚本共用的，**一个字都不改**。任何命令**不得打印** `.env` 内容——验证写了没有只准用 `grep -c`。
- **只有一个 uvicorn**：绝不起第二个实例（embedding 0.6B 按进程加载，会撞 Windows `os error 1455`）。要重启就重启自己起的那一个；杀进程只用 PowerShell 且先核对 `CommandLine`，**绝不批量杀 python/node**。
- **基线数据不做外科手术**：`documents 9 / parent_chunks 11 / child_chunks 22` 不许删改；探针数据一律 `finally` 清干净。`/api/health` 是**全局物理计数**，迁移后仍必须是 9/11/22。
- **同名重传会撞后端唯一键**（`parent_id` 由清洗后的文件名拼出、全库唯一）→ 探针判据一律用新文件名；跨用户同名上传同样撞（spec 3.6），属已知遗留，本轮不修。
- **前端渲染纪律**：**永不用 `v-html`**；颜色一律取 `variables.css` 的 token（G-4 判据见 Task 8）。
- **文件读写**：涉本地文件一律显式 `encoding="utf-8"`（系统默认 cp936）。
- **中文别走 shell 参数**：Git Bash 里 `curl -d '{"question":"中文"}'` 会按 cp936 出门，后端回 400「There was an error parsing the body」。中文载荷必须先用 Python 以 `encoding="utf-8"` 写成文件，再 `--data @payload.json`（相对路径，`@/tmp/...` 那种绝对路径 curl 读不到）。
- **后端门禁基线**：`cd backend && python -m pytest -q` = **176 passed / 0 skipped / 1 deselected**（本机 MySQL 在跑，live 组真执行，约 2 分 40 秒）；`python -m pytest -m migration -q` = **1 passed**；`python -m pytest -m live -q` = **14 passed**。改完允许条数变多，**不允许任何 failed**。报数只抄工具汇总行，不许凭印象。
- **前端门禁基线**：`cd frontend && npm test` = **84 passed（7 文件）**；`npm run build` exit 0。
- **浏览器量测**：视口必须显式设置并回读原始值（in-app 浏览器默认 754px 会掉进 `max-width:768` 断点）；布局判据走 Edge headless 探针（`npm install --no-save puppeteer-core`，验完 `npm prune`），见项目记忆。
- **文档修订留痕**：改既有 spec/计划一律用 `> 2026-10-XX 修订/勘误` 引用块，不抹原文。
- **报数与判据口径**：条数只能抄工具输出的汇总行；"返回空"不等于"过滤生效"——基线里 `deepseek简介.docx_parent_0` 的正文真含一个字面 `%`，隔离类判据要靠**对照两条查询**，不能靠单条空结果。

> **2026-10-06 修订（Task 1 执行期回写，两条门禁口径）**
> ① 上面"后端门禁基线 **176 passed / 0 skipped**"那一格**要求 `:8000` 上有一份活着的 uvicorn**——`test_live_stream.py:34` 与 `:64` 那两条在没有服务时是 `skip` 而不是 `fail`。Task 1–7 按纪律既不起第二个实例也不重启现有服务，所以这几轮的硬口径统一改成：**`0 failed` 为硬性，允许正好 2 条 `skip`，且必须正好是 `test_live_stream.py:34` 与 `:64`**（本机无服务实测基线 = **174 passed / 2 skipped / 1 deselected**）。`0 skipped` 那条硬要求仍然只在 Task 8 生效——那里会重启服务，跑的是改造后的代码。

> **2026-10-06 修订（Task 5 之后：那两条 skip 别再按行号认）**：上面按 `test_live_stream.py:34` / `:64` 点名是错的口径——**行号会被它上方的改动推着走**，Task 5 在文件里插了 `login_token()` helper，两条当场变成 `:53` / `:87`。此后一律按**函数名**认这两条 skip：`test_client_disconnect_mid_stream_leaves_no_rows` 与 `test_full_stream_persists_one_turn_and_frames_are_ordered`（二者都吃 `server` 夹具，无服务时在夹具里 skip）。另记一笔给 Task 8：这两条在**服务活着**的前提下还可能各自再 skip 一次（`test_live_stream.py:73` / `:106`，大模型不可用时报错帧）——那一轮"0 skipped"若被这两条打破，先查 LLM 可用性再查代码。
> ② `pytest -m` 的表达式会**覆盖** `addopts` 里那条 `not migration`，不是追加。于是 `python -m pytest -m "not live" -q` 会把 `@pytest.mark.migration` 的计数钉（11/22）拖进来越界失败，撞出一个与本轮无关的红。要排除 live 就写全：`python -m pytest -m "not live and not migration" -q`。

> **2026-10-07 修订（基线重钉：全计划的 9 / 11 / 22 作废，改用下面这组实数）**
> **为什么作废**：旧 9 篇里有 8 篇在界面上被删到 `chunk_count` 归零（用户在 UI 里删的，不是本轮的副作用），只剩 `deepseek简介.docx` 一份活着；随后按批准的补救方案，用**真 HTTP 通路**（`POST /api/documents`，同一份 uvicorn 进程，不启第二个实例）补传 `baseline-a.txt` / `baseline-b.txt` / `baseline-c.txt` 三篇小文档重建基线。三篇原文与建法记录在 `.superpowers/sdd/2026-10-06-user-auth-isolation-phase-1/baseline-*.txt`，**长期保留**。
> **2026-10-07 实测（MySQL 表 + Chroma 目录副本 + `/api/health` 三路一致）**：
> - **活文档 4 / 父块 4 / 子块 10**。逐篇：`deepseek简介.docx` 1 父 5 子、`baseline-a.txt` 1 父 1 子、`baseline-b.txt` 1 父 3 子、`baseline-c.txt` 1 父 1 子。Chroma `parent_document` 与 `child_document` 的 id 清单已逐字钉进 `backend/tests/test_chroma_data.py`（`PARENT_COUNT = 4` / `CHILD_COUNT = 10`）。
> - **`documents` 物理行 13** = 4 活 + 9 隐存（`is_active=0`、块数 0：`comp/rag/third/xss/comp2/rag2/long/wide/picker-probe`）。13 行**全部 `user_id IS NULL`**。
> - `users` 0 行、`auth_tokens` 0 行。
> **两处口径必须跟着改**（原文写在别的 Task 里，各 Task 有自己的就地修订块）：
> ① **`documents_claimed` 是 13，不是 4**。迁移补的是 `WHERE user_id IS NULL` 的**物理行**，隐存那 9 行同样归户——否则它们日后重新可见时会挂在无人名下。凡原文写 `assert owned == 9` / `documents_claimed: 9` 的格子，本轮一律 **13**。
> ② 上面 `:21` 那句"`/api/health` 是**全局物理计数**"按仓库改判，而且它数出来的**字段名也与原文不同**。真实形状只有四个顶层键（`main.py:84-89`）：
>
> ```json
> {"status": "ok", "chroma_dir": "...", "document_count": 4,
>  "vector_counts": {"parent": 4, "child": 10}}
> ```
>
> `document_count` 走 `DatabaseManager.count_documents()`（`core/database.py:359`，`filter(is_active == True)`）→ 它数的是**活文档 4**；`vector_counts` 才是物理计数，且它的键是 **`parent` / `child`**（`core/vector_store.py:51-55`），**不存在** `parent_chunk_count` / `child_chunk_count` 这两个顶层键——原文与脚本里凡按那两个名字取值的，拿到的都是 `None`。所以 health 只能证明"没伤到活数据"，收尾自查要 **`document_count == 4` + `vector_counts == {"parent": 4, "child": 10}` 与 SQL `documents_total == 13` 并读**才盖住隐存行。
> ③ 旧门禁格（`:26` 的 **176 passed / 0 skipped**、修订 ① 的 **174 passed / 2 skipped**、以及 Task 4 说的"+2"）已随 Task 1/2 的落地漂移。**2026-10-07 当轮实跑（本机无 uvicorn，`0 failed` 硬口径 + 正好 2 条 `test_live_stream.py` skip）**：`python -m pytest -q` = **224 passed / 2 skipped / 1 deselected / 0 failed**；`python -m pytest -m live -q` = **14 passed / 2 skipped / 211 deselected**；`python -m pytest -m migration -q` = **1 passed / 226 deselected**。后续每轮以**当轮命令的汇总行**为准并抄进台账，只允许条数变多、不允许 failed；`-m migration` 那一格现在钉的是新基线 **4 / 10**。

---

### Task 1: 口令与令牌原语 + 两张账号表（纯后端，不碰 HTTP）

**Files:**
- Create: `backend/core/security.py`、`backend/tests/test_security.py`
- Modify: `backend/core/database.py`（`User`/`AuthToken` 两个模型、`Document.user_id`、7 个账号方法 + 3 个迁移用的方法）
- Modify: `backend/config/config.py`（`AUTH_TOKEN_TTL_DAYS`、`DEFAULT_USER_PASSWORD`）
- Modify: `backend/.env.example`（`DEFAULT_USER_PASSWORD` 一行 + 中文注释）
- Modify: `backend/.env`（追加真实值，不入库）
- Modify: `backend/tests/test_config.py`（`SANCTIONED_ATTRS` 加两项）

**Interfaces:**
- Consumes：`Base`/`Document`/`ParentChunk`/`ChildChunk`/`ChatHistory`/`DatabaseManager`（均已存在）。
- Produces：
  - `hash_password(password: str) -> str`、`verify_password(password: str, stored: str) -> bool`、`new_token() -> str`、`hash_token(token: str) -> str`（`core/security.py`）
  - ORM：`User{id, identifier, identifier_type, nickname, avatar, password_hash, created_at}`、`AuthToken{id, user_id, token_hash, created_at, expires_at}`
  - `Document.user_id: int | None`
  - `DatabaseManager.create_user/get_user_by_identifier/get_user_by_id/count_users/create_token/get_user_by_token/delete_token`
  - `DatabaseManager.assign_unowned_documents(user_id) -> int`、`vector_ids_for_user(user_id) -> {"parent": [...], "child": [...]}`
  - `Config.AUTH_TOKEN_TTL_DAYS: int`（默认 30）、`Config.DEFAULT_USER_PASSWORD: str`（默认空串）

> **2026-10-06 修订（Task 1 落地后）：Produces 少一条，`create_*` 多一个动作**
> ① 上面 `DatabaseManager.assign_unowned_documents` / `vector_ids_for_user` 那一条**没有落地，也不该落地**。核实过：Task 3 用原始连接自己实现 `backfill_documents` / `vector_ids_without_owner`，从不调这两条；Task 4 的代码不消费它们；没有任何测覆盖；而 Step 9 里那段节头注释说"这三条"、实际只有两条。任务评审按死代码打回，已删。Task 4 的 Consumes 行同步勘误（见该处）。
> ② `create_user` / `create_token` 在 `commit()` 之后、`close()` 之前多一句 `session.refresh(row)`。原文的 docstring 声称"关掉 session 后仍能读"，而 `expire_on_commit` 默认是 `True`，`close()` 之后读 `.id` 会 `DetachedInstanceError`——那是 Task 2 的 `/register` 与 `/login` 必然踩的 500。`backend/tests/test_security.py` 里有两条测当场钉"返回的行关会话后可读"。

- [ ] **Step 1: 写 `core/security.py` 的失败测试**

创建 `backend/tests/test_security.py`：

```python
"""口令哈希与会话令牌的四条纪律：可验回、盐随机、时序恒定、库里不留原文。

这一段完全不碰 MySQL 也不碰 HTTP——pbkdf2 的迭代数与令牌的形状是"数据泄露后
还剩多少防线"的那条线，值得单独钉住，而不是混在端点测里靠 mock 演一遍。
"""
import time

from core.security import hash_password, hash_token, new_token, verify_password


def test_password_round_trips_and_is_not_the_plaintext():
    stored = hash_password("hunter2-pass")
    assert verify_password("hunter2-pass", stored) is True
    assert verify_password("hunter2-pas", stored) is False
    assert stored != "hunter2-pass"
    assert "hunter2" not in stored


def test_same_password_hashes_differ_each_time():
    # 盐必须随机：两条相同口令的哈希一样，等于把"谁和谁口令相同"写进了库里
    assert hash_password("same-pass") != hash_password("same-pass")


def test_malformed_stored_hash_reports_false_not_raises():
    # 库里被手改过一行不该让登录接口 500：边界只在这四个 split 结果上
    for junk in ["", "not-a-hash", "pbkdf2_sha256$abc$00$00", "sha512$1000$00$00"]:
        assert verify_password("whatever", junk) is False


def test_hash_is_slow_enough_to_be_a_real_barrier():
    # 390k 次迭代不是玄学：单次哈希必须 ≥ 100ms，否则拖库者一秒能枚举上万次
    start = time.perf_counter()
    hash_password("timing-probe")
    assert time.perf_counter() - start >= 0.1


def test_token_is_url_safe_and_stored_only_as_sha256_hex():
    token = new_token()
    assert len(token) >= 32 and token != new_token()
    digest = hash_token(token)
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)
    assert digest == hash_token(token)  # 同输入同输出：查表靠的就是这一点
```

- [ ] **Step 2: 跑红**

```bash
cd backend && python -m pytest tests/test_security.py -q
```
预期：`ModuleNotFoundError`/`ImportError: cannot import name 'hash_password'`——红的是"东西不存在"，不是"文件写一半"。

- [ ] **Step 3: 写 `core/security.py`**

```python
"""口令哈希与会话令牌：只用标准库，不引 bcrypt/PyJWT（spec 4 节）。

为什么是 pbkdf2 而不是 sha256 直哈希：口令短、字符集小，快哈希能被暴力枚举，
慢哈希 + 随机盐把"库泄露 = 全库口令泄露"降级成"每条各自硬算上亿次"。
为什么库里存令牌的 SHA-256 而不是令牌本身：令牌就是凭证原文，拖库者拿到即能登录；
哈希过之后那行数据本身不可用，服务端只需要"算一遍再比对"。
"""
import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 390000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"{ALGORITHM}${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """坏行只说"不对"，不抛：库里一行被手改过不该把登录接口打成 500。"""
    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$")
        if algorithm != ALGORITHM:
            return False
        expected = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
    except (ValueError, TypeError, AttributeError):
        return False
    # compare_digest 而不是 ==：普通字符串比较在第一个不同字节就返回，
    # 逐字节耗时差能把"猜对了几位"读出来
    return hmac.compare_digest(expected.hex(), digest_hex)


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: 跑绿**

```bash
cd backend && python -m pytest tests/test_security.py -q
```
预期：`5 passed`。

- [ ] **Step 5: 钉 Config 的两个新键**

`backend/tests/test_config.py`：`SANCTIONED_ATTRS` 集合里追加两行（放在 `"TOP_K",` 之后）：

```python
    "AUTH_TOKEN_TTL_DAYS",
    "DEFAULT_USER_PASSWORD",
```

同文件末尾追加两条：

```python
def test_auth_keys_have_defaults_and_read_the_environment():
    """令牌寿命与默认用户口令都是调参键：缺配置走默认，不该把服务起不动。"""
    result = _run_import(BACKEND_DIR, BACKEND_DIR,
                         "from config.config import Config; "
                         "print(Config.AUTH_TOKEN_TTL_DAYS, repr(Config.DEFAULT_USER_PASSWORD))",
                         AUTH_TOKEN_TTL_DAYS="7", DEFAULT_USER_PASSWORD="probe-pass")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "7 'probe-pass'"


def test_auth_keys_fall_back_without_the_env_file(tmp_path):
    """缺键的默认值：30 天寿命 + 空口令（空口令 = 默认用户不可登录，spec 6 步骤 3）。"""
    dotenv = f"DASHSCOPE_API_KEY=x\nCHROMA_PERSIST_DIR={tmp_path / 'chroma'}\n"
    result = _run_import_with_env_file(
        tmp_path, dotenv,
        "from config.config import Config; "
        "print(Config.AUTH_TOKEN_TTL_DAYS, repr(Config.DEFAULT_USER_PASSWORD))")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "30 ''"
```

跑红：`cd backend && python -m pytest tests/test_config.py -q`（`test_config_class_exposes_only_sanctioned_attrs` 先红——属性集对不上）。

- [ ] **Step 6: 写 Config、`.env`、`.env.example`**

`backend/config/config.py`，`TOP_K` 那行之后追加：

```python
    # —— 认证（spec 2.6）：两个都是调参键，缺配置走默认，不像 CHROMA_PERSIST_DIR 缺键就炸 ——
    AUTH_TOKEN_TTL_DAYS = int(os.getenv("AUTH_TOKEN_TTL_DAYS", 30))
    # 默认用户（旧数据归属锚点）的初始口令。留空 = 该账号只作归属、不可登录，
    # 那 9 篇旧文档在界面上就永远看不见，所以本仓的 backend/.env 里给了真值（spec 6 步骤 3）。
    DEFAULT_USER_PASSWORD = os.getenv("DEFAULT_USER_PASSWORD", "")
```

`backend/.env.example` 的 `TOP_K=5` 之后追加：

```
# 令牌寿命（天）；不写用 30
AUTH_TOKEN_TTL_DAYS=30
# 默认用户 default@local 的初始口令；留空则该账号不可登录（旧数据仍归它）
DEFAULT_USER_PASSWORD=
```

真实 `backend/.env` 追加一行（**只写，不打印**）：

```bash
cd backend && printf 'AUTH_TOKEN_TTL_DAYS=30\nDEFAULT_USER_PASSWORD=<REDACTED-ROTATED-2026-10-09>' >> .env \
  && grep -c "^DEFAULT_USER_PASSWORD=" .env
```
预期输出：`1`。**不要 `cat .env`**；这条 `grep -c` 就是唯一的验证动作。口令真值 `kb-default-2026` 会出现在 Task 8 的 live 手测里，属演示账号，随时可改（改完必须重启后端才生效——`.env` 改动不会热加载）。

> **2026-10-06 修订（Task 1 执行期）：这条命令与 Global Constraints 打架，按约束裁**
> 散文写"追加一行"，而逐字命令往真实 `.env` 塞了**两个键**。`AUTH_TOKEN_TTL_DAYS` 是调参键，`Config` 里默认 30 就能用，没有任何东西需要它出现在真实配置里。**裁定：真实 `backend/.env` 只留 `DEFAULT_USER_PASSWORD` 那一行**（`backend/.env.example` 作为模板保留两键不动，`Config.AUTH_TOKEN_TTL_DAYS` 与 `test_config.py` 的 `SANCTIONED_ATTRS` 也不为此改）。验证因此是两条计数：`grep -c "^AUTH_TOKEN_TTL_DAYS=" backend/.env` = **0**、`grep -c "^DEFAULT_USER_PASSWORD=" backend/.env` = **1**。仍然只数键，不打印内容。

- [ ] **Step 7: 跑绿 Config 那两条**

```bash
cd backend && python -m pytest tests/test_config.py -q
```
预期：`13 passed`（原 11 + 新 2）。

- [ ] **Step 8: 钉两张表的形状（失败测试）**

`backend/tests/test_security.py` 末尾追加。**这里不建引擎**：`Document.content` 是 MySQL 方言的 `MEDIUMTEXT`，sqlite 编译不出来（`CompileError`），而"列可空吗、有唯一吗、索引建了吗"这三个问题在 `__table__` 元数据上就能答完。真连接与 join 语义留给 Task 2 末尾的 live 组。

```python
from core.database import AuthToken, Document, User


def test_documents_user_column_is_a_nullable_foreign_key():
    """可空是迁移的前提：旧行在被认领之前就是没有归属，NOT NULL 会让 ALTER 直接失败。"""
    column = Document.__table__.c.user_id
    assert column.nullable is True
    assert [fk.target_fullname for fk in column.foreign_keys] == ["users.id"]
    assert "idx_documents_user_id" in {ix.name for ix in Document.__table__.indexes}


def test_users_and_tokens_shapes():
    assert User.__table__.c.identifier.unique is True
    assert User.__table__.c.identifier_type.nullable is False
    assert User.__table__.c.password_hash.nullable is False
    # 默认值钉在列上，不在端点里补：漏一个调用方就会写进一个空 avatar
    assert User.__table__.c.avatar.default.arg == "auto"

    token = AuthToken.__table__
    assert token.c.token_hash.unique is True
    assert token.c.expires_at.nullable is False
    assert [fk.target_fullname for fk in token.c.user_id.foreign_keys] == ["users.id"]
    assert "idx_tokens_user_id" in {ix.name for ix in token.indexes}
```

跑红：`cd backend && python -m pytest tests/test_security.py -q` → `ImportError: cannot import name 'AuthToken'`。

- [ ] **Step 9: 写模型与 `DatabaseManager` 的账号方法**

`backend/core/database.py` 顶部 import 补 `UniqueConstraint`（已有 `Index`/`ForeignKey`，只缺它）。

`ChatHistory` 类定义之后追加两个模型：

```python
# 账号表：identifier 单列存邮箱或手机号原文，配 identifier_type 说明它是哪一种。
# 为什么不做 email/phone 两列：两列各 nullable-unique 会让"同一手机号能注册两次"
# 这类边界要靠额外约束兜，单列 + 类型列天然唯一（spec 2.1）。
class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    identifier = Column(String(255), nullable=False, unique=True)
    identifier_type = Column(String(10), nullable=False)
    nickname = Column(String(50), nullable=False)
    # 预设头像标识（'auto' = 昵称首字母），不是图片 URL：本仓没有文件存储层（spec 决策 5）
    avatar = Column(String(20), nullable=False, default='auto')
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.now)


# 会话表：库里只有令牌哈希，令牌原文只在登录响应里出现一次（spec 4 节）
class AuthToken(Base):
    __tablename__ = 'auth_tokens'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index('idx_tokens_user_id', 'user_id'),
    )
```

`Document` 类里 `is_active` 那行之后追加列与索引：

```python
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)

    __table_args__ = (
        Index('idx_documents_user_id', 'user_id'),
    )
```

`DatabaseManager` 类末尾（`delete_chat_history` 之后）追加：

```python
    # ---------- 账号与会话（spec 3.1/3.2）----------

    def create_user(self, identifier, identifier_type, nickname, password_hash, avatar="auto"):
        """返回 detached 的 User（只有普通列，不碰 relationship，关掉 session 后仍可读）。"""
        session = self.get_session()
        try:
            user = User(identifier=identifier, identifier_type=identifier_type,
                        nickname=nickname, avatar=avatar, password_hash=password_hash)
            session.add(user)
            session.commit()
            return user
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_user_by_identifier(self, identifier):
        session = self.get_session()
        try:
            return session.query(User).filter(User.identifier == identifier).first()
        finally:
            session.close()

    def get_user_by_id(self, user_id):
        session = self.get_session()
        try:
            return session.get(User, user_id)
        finally:
            session.close()

    def count_users(self) -> int:
        session = self.get_session()
        try:
            return session.query(User).count()
        finally:
            session.close()

    def create_token(self, user_id, token_hash, expires_at):
        session = self.get_session()
        try:
            row = AuthToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
            session.add(row)
            session.commit()
            return row
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_user_by_token(self, token_hash):
        """一枚 join 同时验"令牌有效"与"账号还在"。

        过期行不是删除而是查不出来：`expires_at > now()` 让登出之外的第二种失效方式
        不需要后台清扫（30 天不用完的令牌躺在库里也换不到任何东西）。
        """
        session = self.get_session()
        try:
            return (session.query(User)
                    .join(AuthToken, AuthToken.user_id == User.id)
                    .filter(AuthToken.token_hash == token_hash,
                            AuthToken.expires_at > datetime.now())
                    .first())
        finally:
            session.close()

    def delete_token(self, token_hash) -> int:
        """登出 = 删这一行。返回删掉的行数，0 表示"本来就没有"，不是错误。"""
        session = self.get_session()
        try:
            deleted = session.query(AuthToken).filter(
                AuthToken.token_hash == token_hash).delete()
            session.commit()
            return deleted
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---------- 迁移用（Task 3 的 core/migrations.py 调这三条）----------

    def assign_unowned_documents(self, user_id) -> int:
        """只动 user_id IS NULL 的行：跑第二遍就是 0 行，这是整段迁移幂等的支点。"""
        session = self.get_session()
        try:
            n = session.query(Document).filter(Document.user_id.is_(None)).update(
                {Document.user_id: user_id}, synchronize_session=False)
            session.commit()
            return n
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def vector_ids_for_user(self, user_id):
        """按归属取两份 vector_id 清单——Chroma 的 id 就存这两列里（2026-10-04 live 验过）。"""
        session = self.get_session()
        try:
            parents = session.query(ParentChunk.vector_id).join(
                Document, Document.id == ParentChunk.document_id).filter(
                Document.user_id == user_id, ParentChunk.vector_id.isnot(None)).all()
            children = session.query(ChildChunk.vector_id).join(
                Document, Document.id == ChildChunk.document_id).filter(
                Document.user_id == user_id, ChildChunk.vector_id.isnot(None)).all()
            return {"parent": [r[0] for r in parents], "child": [r[0] for r in children]}
        finally:
            session.close()
```

> **2026-10-06 修订（Task 1 落地后）：上面这节代码有两处与仓库不一致，以仓库为准**
> ① **`# ---------- 迁移用（Task 3 ...）----------` 那一节整段删除**（`assign_unowned_documents`、`vector_ids_for_user` 与节头注释）。理由见本 Task Interfaces 处的修订。其余方法照原样落地。
> ② 本 Task 执行期把 Task 3 的两条 DDL **提前落到了真实 MySQL**：`ALTER TABLE \`documents\` ADD COLUMN \`user_id\` INTEGER NULL` 与 `CREATE INDEX idx_documents_user_id ON documents (user_id)`，都用 `information_schema` 守卫、幂等、由一次性脚本走 stdin（不入库）。原因是 ORM 先有列而库里没有列，`test_live_database.py` 的 9 条既有测当场 MySQL 1054 红。**代价**：Task 8 Step 2 期望的"首轮 `columns_added` 含 `('documents', 'user_id')`"这条活证退化为 `[]`，首轮证据只剩 `documents_claimed: 9`；加列那条分支改由 Task 3 的 `FakeConn` 单测守住。

- [ ] **Step 10: 跑绿 + 全量默认门**

```bash
cd backend && python -m pytest tests/test_security.py -q
cd backend && python -m pytest -q
```
预期：前者 `7 passed`（5 条原语 + 2 条形状）；后者 **185 passed / 0 skipped / 1 deselected**（176 + 2 条 Config + 7 条 security，零 failed）。

- [ ] **Step 11: 提交**

```bash
cd D:/知识库平台-前后端分离 && git add backend/core/security.py backend/core/database.py \
  backend/config/config.py backend/.env.example backend/tests/test_security.py backend/tests/test_config.py
git status --short
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(backend): 账号表、会话表与 pbkdf2/令牌原语（阶段一 Task 1）"
```
`git status --short` 必须只列这 6 个文件；出现 `backend/.env` 立刻 `git reset` 重来（`.gitignore` 已排除它，出现就说明哪里错了）。

### Task 2: 四个认证端点、`get_current_user` 与 401 那一格

**Files:**
- Create: `backend/schemas/auth.py`、`backend/api/auth.py`、`backend/tests/test_api_auth.py`
- Modify: `backend/exceptions.py`（加 `AuthError`）
- Modify: `backend/deps.py`（加 `bearer_token` + `get_current_user`）
- Modify: `backend/main.py`（`STATUS_BY_ERROR` 加 401 一格、`include_router(auth_router)`、CORS `allow_methods` 加 `PUT`）
- Modify: `backend/tests/test_error_model.py`（中央映射从 4 格改 5 格，含新探针路由）
- Modify: `backend/tests/test_live_database.py`（账号/令牌方法在真 MySQL 上的往返）

**Interfaces:**
- Consumes: `core/security.py` 四个函数、`DatabaseManager` 的 7 个账号方法、`Config.AUTH_TOKEN_TTL_DAYS`（Task 1）。
- Produces:
  - `exceptions.AuthError`（→ 401）、`deps.LOGIN_REQUIRED = "未登录或登录已过期"`、`deps.bearer_token(request) -> str`、`deps.get_current_user(request, db) -> User`
  - `schemas/auth.py`：`normalize_identifier(kind, raw)`、`default_nickname` 的等价逻辑（在 `api/auth.py`）、`RegisterIn`/`LoginIn`/`UserOut{id, identifier, identifier_type, nickname, avatar}`/`AuthOut{token, user, session_id}`/`MeOut{user}`
  - 端点：`POST /api/auth/register`(201)、`POST /api/auth/login`(200)、`POST /api/auth/logout`(204)、`GET /api/auth/me`(200)

- [ ] **Step 1: 先加异常与依赖（这两件是后面所有判据的支点）**

`backend/exceptions.py` 末尾追加：

```python
class AuthError(KnowledgeBaseError):
    """401：缺令牌、坏令牌、过期令牌。三种情况共用一句文案——
    区分它们等于向外人承认"这个账号存在，只是你的票不对"（spec 3.5）。"""
```

`backend/deps.py` 整文件改成（原五个 provider 一字不动，只加下面这些）：

```python
from fastapi import Depends, Request

from core.security import hash_token
from exceptions import AuthError

LOGIN_REQUIRED = "未登录或登录已过期"


def bearer_token(request: Request) -> str:
    """从 Authorization 头取 Bearer 令牌原文。不合格一律同一句 401，不说哪里不合格。"""
    raw = request.headers.get("Authorization") or ""
    scheme, _, credential = raw.partition(" ")
    if scheme.lower() != "bearer" or not credential.strip():
        raise AuthError(LOGIN_REQUIRED)
    return credential.strip()
```

`get_rag_system` 之后追加：

```python
def get_current_user(request: Request, db=Depends(get_db)):
    """唯一那道门：令牌哈希 → auth_tokens（带有效期）→ users。

    库里只存哈希（spec 4 节），所以这里必须先把原文算一遍再查；任一步查不到
    都只说"未登录或登录已过期"，登出与过期因此在响应上不可分辨。
    """
    user = db.get_user_by_token(hash_token(bearer_token(request)))
    if user is None:
        raise AuthError(LOGIN_REQUIRED)
    return user
```

`main.py` 的 `STATUS_BY_ERROR` 加一格、CORS 加 `PUT`、注册新 router：

```python
from api.auth import router as auth_router
from exceptions import AuthError, LLMError, RetrievalError, StorageError, UnsupportedDocumentType

STATUS_BY_ERROR = {
    UnsupportedDocumentType: 415,
    StorageError: 500,
    RetrievalError: 502,
    LLMError: 502,
    AuthError: 401,
}
```
`allow_methods=["GET", "POST", "DELETE"]` → `["GET", "POST", "PUT", "DELETE"]`（`PUT` 是阶段二的 `PUT /me` 要用的；CORS 属于"部署一次就忘"的那类配置，现在加比将来对着浏览器控制台找半小时便宜）。
`app.include_router(documents_router)` 之前加 `app.include_router(auth_router)`。

- [ ] **Step 2: 写 schemas/auth.py**

```python
"""认证接口的入出参形状（spec 3.1）。

标识符的正则与归一放这里：它是"接口接受什么样的字符串"这件事的一部分，
将来换一种登录入口（比如用户名）要动的就是这个文件，不是端点也不是 core。
"""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_RE = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
PHONE_RE = r"^1[3-9]\d{9}$"
PASSWORD_MIN = 6


def normalize_identifier(kind: str, raw: str) -> str:
    """只验格式、不发验证码（决策 1）。邮箱归一小写：`A@B.com` 与 `a@b.com` 是同一个人。

    手机号只做整串校验、不剔除中间空格/横线——真发验证码的话这里还得归一成纯数字，
    本期没有那件事，多洗一次反而会把用户输进去的号改得他自己都对不上。
    """
    value = raw.strip()
    if kind == "email":
        value = value.lower()
        if not re.match(EMAIL_RE, value):
            raise ValueError("邮箱格式不正确")
    else:
        if not re.match(PHONE_RE, value):
            raise ValueError("手机号格式不正确")
    return value


class RegisterIn(BaseModel):
    identifier_type: Literal["email", "phone"]
    identifier: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=PASSWORD_MIN, max_length=64)
    nickname: str | None = Field(default=None, min_length=1, max_length=50)

    @field_validator("identifier")
    @classmethod
    def _normalize(cls, value: str, info) -> str:
        # 声明顺序保证 identifier_type 先验完，这里才拿得到它；坏值在 Literal 那关就 422 了
        return normalize_identifier(info.data.get("identifier_type", "email"), value)


class LoginIn(BaseModel):
    identifier: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=64)

    @field_validator("identifier")
    @classmethod
    def _normalize(cls, value: str) -> str:
        value = value.strip()
        # 登录不再要求前端声明类型：含 @ 就按邮箱归一大小写，否则原样当手机号
        return value.lower() if "@" in value else value


class UserOut(BaseModel):
    """from_attributes 让它能直接吃 ORM 的 User 行。

    没有 password_hash 这个字段——少写一个字段比写一个"过滤掉敏感列"的逻辑可靠得多。
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    identifier: str
    identifier_type: str
    nickname: str
    avatar: str


class AuthOut(BaseModel):
    token: str
    user: UserOut
    # 对话 id 与登录凭证是两件事（决策 2）：注册/登录那一刻由后端 uuid4() 造一个新的，
    # 刷新页面走 GET /me 不再发新 id，所以刷新不会把当前对话换掉。
    session_id: str


class MeOut(BaseModel):
    user: UserOut
```

- [ ] **Step 3: 写 api/auth.py**

```python
"""注册 / 登录 / 登出 / 我是谁（spec 3.1 的阶段一部分）。

发令牌只在这四个端点里的两个发生：那一刻哈希进库、原文写进响应，
此后服务端再也不认识那串原文——这是"可吊销"唯一的成本，也正是它的意义。
"""
import logging
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError

from core.security import hash_password, hash_token, new_token, verify_password
from deps import LOGIN_REQUIRED, bearer_token, get_config, get_current_user, get_db
from schemas.auth import AuthOut, LoginIn, MeOut, RegisterIn, UserOut

router = APIRouter(prefix="/api/auth")
logger = logging.getLogger("kb.api.auth")

LOGIN_FAILED = "账号或密码不正确"
ACCOUNT_TAKEN = "该账号已注册"

# 账号不存在时也走一次哈希比较，让"没这个账号"与"密码错"在耗时上不可分辨。
# 迭代数给 1000 就够：这条路径要的是"确实花时间算过"，不是"算满 39 万次"。
_DUMMY_HASH = "pbkdf2_sha256$1000$" + "0" * 32 + "$" + "0" * 64


def default_nickname(identifier: str, identifier_type: str) -> str:
    if identifier_type == "email":
        head = identifier.split("@")[0]
        return head[:50] if head else "用户"
    return f"用户{identifier[-4:]}"


def _issue(db, config, user) -> AuthOut:
    token = new_token()
    db.create_token(user_id=user.id, token_hash=hash_token(token),
                    expires_at=datetime.now() + timedelta(days=config.AUTH_TOKEN_TTL_DAYS))
    return AuthOut(token=token, user=UserOut.model_validate(user), session_id=str(uuid.uuid4()))


@router.post("/register", status_code=201, response_model=AuthOut)
def register(payload: RegisterIn, db=Depends(get_db), config=Depends(get_config)):
    try:
        user = db.create_user(
            identifier=payload.identifier,
            identifier_type=payload.identifier_type,
            nickname=(payload.nickname or "").strip() or default_nickname(
                payload.identifier, payload.identifier_type),
            password_hash=hash_password(payload.password),
        )
    except IntegrityError:
        # 并发注册撞 unique 必须收在 409：让它冒到兜底 handler 就成 500，
        # 而 500 会让客户端以为"没注册上"从而重试，重试再撞一个更难看的世界
        logger.info("注册撞已存在的标识: %s", payload.identifier_type)
        raise HTTPException(status_code=409, detail=ACCOUNT_TAKEN)
    return _issue(db, config, user)


@router.post("/login", response_model=AuthOut)
def login(payload: LoginIn, db=Depends(get_db), config=Depends(get_config)):
    user = db.get_user_by_identifier(payload.identifier)
    matched = verify_password(payload.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not matched:
        # 一句文案盖住两种失败：分开回等于把"哪些邮箱注册过"送给外人
        raise HTTPException(status_code=401, detail=LOGIN_FAILED)
    return _issue(db, config, user)


@router.post("/logout", status_code=204)
def logout(request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    db.delete_token(hash_token(bearer_token(request)))
    return None


@router.get("/me", response_model=MeOut)
def me(user=Depends(get_current_user)):
    return MeOut(user=UserOut.model_validate(user))
```

> **2026-10-06 修订（Task 2 Step 3：上面那块里的 `1000` 是计划写错，落地改数不改注释）**
> `verify_password` 的耗时由 **stored 串自己**那段迭代数决定（`core/security.py:26` 从串里解出来、`:30`
> 拿去喂 `pbkdf2_hmac`），不是读全局常量。所以垫片给 1000 时："没这个账号"算 1000 轮、"密码错"算
> 390000 轮，实测差约 190 倍——注释里那句"耗时上不可分辨"当场是假话，攻击者拿秒表就能枚举账号。
> **落地改为同价**，从 `core.security` 引 `ALGORITHM` / `PBKDF2_ITERATIONS` 而不是抄字面量，以后
> `PBKDF2_ITERATIONS` 上调时垫片自动跟上。盐与摘要那两段 hex **提到 f-string 外面**（写成
> `_DUMMY_SALT_HEX` / `_DUMMY_DIGEST_HEX` 两个模块常量），花括号里不放表达式：
>
> ```python
> _DUMMY_SALT_HEX = "0" * 32
> _DUMMY_DIGEST_HEX = "0" * 64
> _DUMMY_HASH = f"{ALGORITHM}${PBKDF2_ITERATIONS}${_DUMMY_SALT_HEX}${_DUMMY_DIGEST_HEX}"
> ```
>
> **明确不做**任何 `sleep` / 取平均 / 补齐到某个墙钟值的"抹平"写法：那只是把假安全感写进生产路径，
> 还多一个随机器负载抖动的判据。代价是未知账号登录多花约 200ms——注册面与登录失败面，不值一提。
> 由两条测钉住：垫片对任意口令恒 `False`（形状对了但恒真也照样是洞）；四段形状与迭代数和真行逐字段相等
> （后者断的是 `_DUMMY_HASH.split("$")[1]`，所以那两个常量名也是判据的一部分）。

- [ ] **Step 4: 写 `tests/test_api_auth.py`**

不连 MySQL：`get_db` 覆盖成字典版假账号库，`get_config` 覆盖成 `SimpleNamespace`（`create_app()` 不进 `with`，lifespan 不跑，`app.state.config` 根本不存在——这条与 `test_health.py` 同一个道理）。

```python
"""四个认证端点的契约。三条判据是这块的全部风险：

① "账号不存在"与"密码错"必须**逐字节相同**（防枚举）；
② 库里/响应里都不许出现口令哈希原文；
③ 登出后同一枚令牌立刻换不回用户（可吊销是这套凭证形态唯一的卖点）。
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from deps import get_config, get_current_user, get_db
from main import create_app
from schemas.auth import normalize_identifier

UUID_RE = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


class FakeAuthDB:
    def __init__(self):
        self.users = []          # SimpleNamespace 列表，字段与 ORM 行同名
        self.tokens = {}         # token_hash -> (user_id, expires_at)
        self._next_id = 1

    def create_user(self, identifier, identifier_type, nickname, password_hash, avatar="auto"):
        if any(u.identifier == identifier for u in self.users):
            raise IntegrityError("INSERT INTO users", {}, Exception("duplicate entry"))
        user = SimpleNamespace(id=self._next_id, identifier=identifier,
                               identifier_type=identifier_type, nickname=nickname,
                               avatar=avatar, password_hash=password_hash)
        self._next_id += 1
        self.users.append(user)
        return user

    def get_user_by_identifier(self, identifier):
        return next((u for u in self.users if u.identifier == identifier), None)

    def create_token(self, user_id, token_hash, expires_at):
        self.tokens[token_hash] = (user_id, expires_at)

    def get_user_by_token(self, token_hash):
        entry = self.tokens.get(token_hash)
        if entry is None or entry[1] <= datetime.now():
            return None
        return next((u for u in self.users if u.id == entry[0]), None)

    def delete_token(self, token_hash):
        return 1 if self.tokens.pop(token_hash, None) else 0


def make_client(db=None):
    db = db or FakeAuthDB()
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_config] = lambda: SimpleNamespace(AUTH_TOKEN_TTL_DAYS=30)
    return TestClient(app), db


def register(client, identifier="a@b.com", **over):
    payload = {"identifier_type": "email", "identifier": identifier, "password": "hunter2-pass", **over}
    return client.post("/api/auth/register", json=payload)
```

第一批用例（注册与格式校验）：

```python
def test_register_returns_token_user_and_a_uuid_session():
    client, db = make_client()
    res = register(client)
    assert res.status_code == 201
    body = res.json()
    assert len(body["token"]) >= 32
    import re
    assert re.match(UUID_RE, body["session_id"])
    assert body["user"] == {"id": 1, "identifier": "a@b.com", "identifier_type": "email",
                            "nickname": "a", "avatar": "auto"}
    assert len(db.tokens) == 1


def test_register_lowercases_the_email_and_reuses_it_for_lookup():
    client, db = make_client()
    assert register(client, identifier="A@Example.COM").status_code == 201
    assert db.users[0].identifier == "a@example.com"
    assert client.post("/api/auth/login", json={"identifier": "a@example.com",
                                                "password": "hunter2-pass"}).status_code == 200


def test_register_nickname_defaults_and_overrides():
    client, _ = make_client()
    assert register(client, identifier="dev@team.io").json()["user"]["nickname"] == "dev"
    assert register(client, identifier="13800000001", identifier_type="phone",
                    ).json()["user"]["nickname"] == "用户0001"
    assert register(client, identifier="x@y.z", nickname="小明").json()["user"]["nickname"] == "小明"


@pytest.mark.parametrize("bad", ["a@b", "a b@c", "@b.com", "a@b.", "a@b.c", "abc.def"])
def test_register_rejects_malformed_email(bad):
    client, _ = make_client()
    assert register(client, identifier=bad).status_code == 422


@pytest.mark.parametrize("bad", ["12345678901", "1380000000", "138000000012", "23800000001", "1380000000a"])
def test_register_rejects_malformed_phone(bad):
    client, _ = make_client()
    assert register(client, identifier=bad, identifier_type="phone").status_code == 422


def test_register_rejects_short_password_and_unknown_type():
    client, _ = make_client()
    assert register(client, password="12345").status_code == 422
    assert register(client, identifier_type="username").status_code == 422


def test_normalize_identifier_is_pure_and_raises_value_error():
    """422 的中文文案就是从这两个 ValueError 来的，所以它们得能单独验。"""
    assert normalize_identifier("email", "  A@B.com  ") == "a@b.com"
    assert normalize_identifier("phone", "13800000001") == "13800000001"
    with pytest.raises(ValueError):
        normalize_identifier("email", "nope")
    with pytest.raises(ValueError):
        normalize_identifier("phone", "12345678901")


def test_duplicate_register_is_409_with_one_chinese_line():
    client, _ = make_client()
    assert register(client).status_code == 201
    res = register(client)
    assert res.status_code == 409
    assert res.json() == {"detail": "该账号已注册"}
```

> **2026-10-06 修订（Task 2 Step 4：上面这两格自相矛盾，落地时改昵称那一格）**
> `test_register_nickname_defaults_and_overrides` 用 `x@y.z` 期望 201，而 `test_register_rejects_malformed_email`
> 把 `a@b.c` 钉成 422——同一件事两个结论。`schemas/auth.py:11` 的 `EMAIL_RE` 要求 TLD 至少两个字母
> （`[A-Za-z]{2,}`），所以单字母 TLD 一律 422，`x@y.z` 当场红。
> **改判：把昵称用例换成 `x@y.zz`，不放宽正则。** 理由是那条 `{2,}` 是生产校验，不是为测试设的门槛——
> 为凑一个测试值把它退成 `{1,}`，等于真实用户能注册出 `a@b.c` 这种过不了任何发信域的邮箱。
> 实现处在那格用例上留了指向 `test_register_rejects_malformed_email` 的注释（单向指针，本格不反指）；
> 后续 Task 抄这段判据时以 `x@y.zz` 为准。

第二批（登录、令牌、登出、`/me`）：

```python
def test_login_mints_a_new_session_id_every_time():
    client, _ = make_client()
    register(client)
    first = client.post("/api/auth/login", json={"identifier": "a@b.com",
                                                 "password": "hunter2-pass"}).json()
    second = client.post("/api/auth/login", json={"identifier": "a@b.com",
                                                  "password": "hunter2-pass"}).json()
    assert first["token"] != second["token"]
    # 需求 2 的正面：重新登录 = 新对话 id
    assert first["session_id"] != second["session_id"]


def test_wrong_password_is_401():
    client, _ = make_client()
    register(client)
    res = client.post("/api/auth/login", json={"identifier": "a@b.com", "password": "wrong-pass"})
    assert res.status_code == 401
    assert res.json() == {"detail": "账号或密码不正确"}


def test_unknown_account_and_wrong_password_are_byte_identical():
    """防枚举钉的是**响应本身**，不是文案：状态码、字节串、长度三样都得一样。"""
    client, _ = make_client()
    register(client)
    known = client.post("/api/auth/login", json={"identifier": "a@b.com", "password": "wrong-pass"})
    unknown = client.post("/api/auth/login", json={"identifier": "nobody@b.com", "password": "wrong-pass"})
    assert unknown.status_code == known.status_code == 401
    assert unknown.content == known.content


def test_me_returns_the_user_and_never_the_password_hash():
    client, db = make_client()
    token = register(client).json()["token"]
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["user"]["identifier"] == "a@b.com"
    assert "password_hash" not in res.text
    assert db.users[0].password_hash not in res.text


@pytest.mark.parametrize("header", [
    None,
    {},
    {"Authorization": ""},
    {"Authorization": "token abc"},          # scheme 不是 Bearer
    {"Authorization": "Bearer "},            # 有 scheme 没凭证
    {"Authorization": "Bearer not-in-db"},   # 真令牌但库里没有
], ids=["none", "empty-dict", "blank", "wrong-scheme", "no-credential", "unknown-token"])
def test_me_rejects_every_kind_of_missing_credential_the_same_way(header):
    client, _ = make_client()
    res = client.get("/api/auth/me", headers=header or {})
    assert res.status_code == 401
    assert res.json() == {"detail": "未登录或登录已过期"}


def test_expired_token_is_rejected_without_deleting_anything():
    """过期靠 expires_at 判定，不靠后台清扫：30 天不动的令牌躺在库里也换不到东西。"""
    client, db = make_client()
    token = register(client).json()["token"]
    from core.security import hash_token
    user_id, _ = db.tokens[hash_token(token)]
    db.tokens[hash_token(token)] = (user_id, datetime.now() - timedelta(seconds=1))
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_logout_revokes_the_same_token_immediately():
    client, _ = make_client()
    token = register(client).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.post("/api/auth/logout", headers=headers).status_code == 401


def test_logout_without_a_token_is_401_not_silently_ok():
    client, _ = make_client()
    assert client.post("/api/auth/logout").status_code == 401
```

跑：`cd backend && python -m pytest tests/test_api_auth.py -q`。
预期：全绿（约 25 条，含两条 parametrize 展开）。**这一步第一次验到"依赖里抛的领域异常能被中央 handler 接住"**——`get_current_user` 抛 `AuthError` 走的是 `STATUS_BY_ERROR`，红的话先确认 `main.py` 的注册循环没漏。

- [ ] **Step 5: 中央映射补第五格**

`backend/tests/test_error_model.py`：

```python
from exceptions import AuthError, LLMError, RetrievalError, StorageError, UnsupportedDocumentType


def auth_dep():
    """见 unsupported_type_dep。"""
```
`probe_router` 追加一条路由：

```python
@probe_router.get("/auth")
def probe_auth(_=Depends(auth_dep)):
    return {"unreachable": True}
```
`CENTRAL_MAP` 追加一行、`test_central_map_covers_every_domain_error_class` 的集合加一类：

```python
    (auth_dep, "/api/probe/auth", AuthError("未登录或登录已过期"), 401),
```
```python
    assert set(STATUS_BY_ERROR) == {
        UnsupportedDocumentType, StorageError, RetrievalError, LLMError, AuthError
    }
```

- [ ] **Step 6: 账号方法在真 MySQL 上的往返（live 组）**

`backend/tests/test_live_database.py` 末尾追加三条。探针账号留在 `users` 里**不清删**：`users` 表没有基线计数（9/11/22 钉的是 documents/parent/child），也没有 `delete_user` 方法——为一条测试加一个只给测试用的删除口不值。

```python
def test_account_methods_round_trip_on_real_mysql(db):
    """join + expires_at 那两条 SQL 语义 fake 给不出证据：这里钉真库上的成功与过期。"""
    from core.security import hash_password, hash_token, new_token
    from datetime import timedelta

    tag = f"probe-{new_tag()}"
    user = db.create_user(identifier=f"{tag}@local", identifier_type="email",
                          nickname="探针", password_hash=hash_password("probe-pass"))
    token = new_token()
    db.create_token(user_id=user.id, token_hash=hash_token(token),
                    expires_at=datetime.now() + timedelta(days=1))
    assert db.get_user_by_token(hash_token(token)).id == user.id
    assert db.count_users() >= 1

    expired = f"{tag}-expired"
    db.create_token(user_id=user.id, token_hash=expired,
                    expires_at=datetime.now() - timedelta(seconds=1))
    assert db.get_user_by_token(expired) is None, "过期令牌仍能换回用户：expires_at 那道滤条件没生效"

    assert db.delete_token(hash_token(token)) == 1
    assert db.get_user_by_token(hash_token(token)) is None
    assert db.delete_token(hash_token(token)) == 0, "重复登出不该报第二行"


def test_identifier_unique_on_real_mysql(db):
    """`users.identifier` 的 unique 是 DDL 层事实，只有真库能证。"""
    from sqlalchemy.exc import IntegrityError
    from core.security import hash_password

    tag = f"dup-{new_tag()}"
    db.create_user(identifier=f"{tag}@local", identifier_type="email",
                   nickname="甲", password_hash=hash_password("probe-pass"))
    with pytest.raises(IntegrityError):
        db.create_user(identifier=f"{tag}@local", identifier_type="email",
                       nickname="乙", password_hash=hash_password("probe-pass"))
    db.get_session().rollback()


def test_new_document_carries_its_owner(db):
    """写入侧归属：这一行不落到 user_id 上，Task 4 的过滤就是空谈。"""
    tag = f"own-{new_tag()}"
    from core.security import hash_password
    user = db.create_user(identifier=f"{tag}@local", identifier_type="email",
                          nickname="丙", password_hash=hash_password("probe-pass"))
    doc_id = db.save_document(filename=f"{tag}.txt", file_path="", content="x",
                              chunk_count=0, user_id=user.id)
    try:
        assert db.get_document(doc_id, user_id=user.id).id == doc_id
        assert db.get_document(doc_id, user_id=user.id + 99999) is None
    finally:
        db.delete_document(doc_id)
```
第三条用到 Task 4 才加的 `get_document(doc_id, user_id=...)` 与 `save_document(..., user_id=...)`——**Step 6 先只落前两条**，第三条留到 Task 4 Step 1 一起写，否则这里必红在签名上。

- [ ] **Step 7: 全量默认门 + 提交**

```bash
cd backend && python -m pytest -q
```
预期：**213 passed / 0 skipped / 1 deselected**（185 + `test_api_auth.py` 25 + error_model 1 新格 + live 2 条 ≈ 213；条数以汇总行为准，别抄这里的加法式）。**允许实数与这个式子差一两条，不允许 failed。**

```bash
cd backend && python -m pytest -m live -q
```
预期：`16 passed`（原 14 + 2）。

```bash
cd D:/知识库平台-前后端分离 && git add backend/exceptions.py backend/deps.py backend/main.py \
  backend/schemas/auth.py backend/api/auth.py backend/tests/test_api_auth.py \
  backend/tests/test_error_model.py backend/tests/test_live_database.py
git status --short
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(backend): 注册登录登出与 /me 四端点，401 进中央映射（阶段一 Task 2）"
```

### Task 3: 启动期迁移 `core/migrations.py`（建表之后补列、塞默认用户、归户、给旧向量补戳）

**Files:**
- Create: `backend/core/migrations.py`、`backend/tests/test_migrations.py`
- Modify: `backend/main.py`（`lifespan` 里 `VectorStore` 之后、`RAGSystem` 之前插一行）

**Interfaces:**
- Consumes：`Base`/`Document`/`ParentChunk`/`ChildChunk`（Task 1）、`DatabaseManager.create_user/count_users`（Task 1）、`hash_password`（Task 1）、`Config.DEFAULT_USER_PASSWORD`（Task 1）、`chromadb`。
- Produces：
  - `migrations.DEFAULT_IDENTIFIER = "default@local"`
  - `migrations.MIGRATED_COLUMNS: list[tuple[str, str, str]]`（`("documents", "user_id", "INTEGER")` 一条）
  - `column_exists(conn, table, column) -> bool`、`add_column(conn, table, column, ddl_type) -> None`、`ensure_columns(conn) -> list[tuple[str, str]]`（返回**这次真的 ALTER 了哪些** `(表, 列)`，判据靠它数）
  - `ensure_default_user(conn, password: str) -> int`（返回 user_id，幂等）
  - `backfill_documents(conn, user_id) -> int`
  - `vector_ids_without_owner(conn) -> {"parent": [...], "child": [...]}`（所属文档仍未归户的向量 id 清单）
  - `stamp_vector_owner(client, vector_ids: dict, user_id: int) -> int`（返回补戳条数；已戳过的跳过，重跑回 0）
  - `run_migrations(engine, chroma_client, password: str) -> dict`（一句话汇总，供 lifespan 打日志）

> **2026-10-06 修订（Task 1 落地后回写，四处，实施本 Task 时以本块为准）**
> ① **本 Task 多一条"补索引"的活。** spec 2.2 要求 `documents.user_id` 带索引 `idx_documents_user_id`，而原文的迁移只管列（`MIGRATED_COLUMNS`），`Base.metadata.create_all` 对已存在的表整表跳过 ⇒ 已部署库会永远带着一个无索引的外键列。Task 1 的任务评审把这条打成 Important，索引已在真实库上当场补齐，**长期收拢靠本 Task**。新增模块常量 `MIGRATED_INDEXES = [("documents", "user_id", "idx_documents_user_id")]`（`(表, 列, 索引名)`），以及三个与列那三条同形的函数：`index_exists(conn, table, index) -> bool`（查 `information_schema.STATISTICS`，`TABLE_SCHEMA = DATABASE()`，表名/索引名走绑定参数 `:table` / `:index`）、`add_index(conn, table, column, index) -> None`（执行且只执行 ``CREATE INDEX `{index}` ON `{table}` (`{column}`)``，f-string 的理由与 `add_column` 同一条：DDL 不接受绑定参数，三个值只可能来自模块常量）、`ensure_indexes(conn) -> list[tuple[str, str]]`（返回这次真的建了哪些 `(表, 索引名)`，末尾 `conn.commit()`）。**顺序是硬要求**：`run_migrations` 里先 `ensure_columns(conn)` 再 `ensure_indexes(conn)`——列还不存在就建索引会当场炸。汇总字典多一格 `"indexes_added": indexes`（紧跟 `columns_added` 之后），Task 8 抄的那行 `迁移完成: {...}` 日志会带上它。
> ② **`FakeConn` 要长两枝**：认得 `SELECT INDEX_NAME` 查询与 `CREATE INDEX` 语句。构造参数加 `existing_indexes=()`（记成 `{(表, 索引名)}`）；`CREATE INDEX` 分支只在对应列已在 `self.columns` 里时才把索引加入集合，否则 `raise AssertionError`——这一句把"先列后索引"的真语义钉在假连接上。Step 1 的测追加一条 `test_ensure_indexes_creates_only_when_missing`：空索引集合时 `ensure_indexes(conn) == [("documents", "idx_documents_user_id")]`，再跑一次 `== []`。因此 Step 5 的"预期 `6 passed`"改为 **`7 passed`**（SQL 决策 3 + 索引决策 1 + Step 4 的 3 条）。
> ③ **空口令哨兵换成不可用的值。** 原文 `ensure_default_user` 在 `password` 为空时写入 `hash_password("this-account-has-no-password")`——那是一枚**源码里看得见的可用凭证**，任何读到这一行的人就拿到了默认账号的口令，而 Step 2 后面那段说明自己也承认"挡不住读代码的人"。改为模块常量 `UNUSABLE_PASSWORD_HASH = "unusable-no-password-set"`：它不含 `$`，`verify_password` 在四段解包那一格就 `ValueError` → 返回 `False`（即便拼出四段，首段也不是 `pbkdf2_sha256`，算法门照样拒绝）；`password_hash` 列的 `NOT NULL` 仍然满足。`backend/tests/test_migrations.py` 加一条纯逻辑判据（不建引擎）：`verify_password("this-account-has-no-password", migrations.UNUSABLE_PASSWORD_HASH) is False` 且 `verify_password("", migrations.UNUSABLE_PASSWORD_HASH) is False`。
> ④ **计数预期**：`python -m pytest -m migration -q` 在本 Task 之前是 1 passed，变 2 的原因是 Step 7 那条 `@pytest.mark.migration` 的向量补戳判据（`test_old_vectors_get_a_user_id_stamp_on_a_copy`），**不是**上面新增的索引决策测——那条属于离线默认门，跟着 Step 5 的 `7 passed` 走。仍然只抄工具汇总行。

**为什么单独立一个 Task**：`Base.metadata.create_all` 只建新表、不给已有表加列（`database.py:119` 那句 `create_all` 的能力边界），而 MySQL 没有 `ADD COLUMN IF NOT EXISTS`。这两件事合起来意味着"加一列"必须自己写成"先查 `information_schema` 再 ALTER"，而且**每次开机都要重跑**——开发者本地库、live 测试用的库和将来部署面上的库处在三个不同的迁移进度上，只有幂等启动能把它们收拢。

- [ ] **Step 1: 写失败的迁移测试（假连接，只验 SQL 决策）**

创建 `backend/tests/test_migrations.py`：

```python
"""迁移的四条纪律：缺列才 ALTER、已戳不再写、重复跑零副作用、口令空则账号不可登录。

这里用假 Connection 记录发出去的 SQL，为的是把"先查再改"这个决策本身钉死——
真 MySQL 上的 ALTER 语义归 live 组，那是另一条判据。
"""

from core import migrations


class FakeConn:
    """只实现 migrations 用到的那三件事：查 information_schema、执行 ALTER、跑 UPDATE。"""

    def __init__(self, existing_columns=(), user_rows=(), owned_doc_ids=()):
        self.columns = set(existing_columns)          # {("documents", "user_id")}
        self.users = list(user_rows)                  # [(id, identifier)]
        self.owned_docs = set(owned_doc_ids)          # 已有 user_id 的文档 id
        self.executed = []                            # 记 DDL/DML，SELECT 不记

    def execute(self, sql, params=None):
        text = str(sql)
        head = text.strip().upper()
        params = params or {}
        if head.startswith("SELECT COLUMN_NAME"):
            table = params["table"]
            rows = [(c,) for (t, c) in self.columns if t == table]
            return _Result(rows)
        if head.startswith("ALTER TABLE"):
            self.executed.append(text)
            table = text.split()[2].strip("`")
            column = text.split("ADD COLUMN")[1].strip().split()[0].strip("`")
            self.columns.add((table, column))
            return _Result([])
        if head.startswith("SELECT COUNT") :
            return _Result([(len(self.users),)])
        if head.startswith("SELECT id, identifier"):
            return _Result(list(self.users))
        if head.startswith("INSERT INTO users"):
            new_id = (max([i for i, _ in self.users], default=0) + 1)
            self.users.append((new_id, params["identifier"]))
            return _Result([])
        if head.startswith("SELECT id FROM documents"):
            return _Result([(i,) for i in range(1, 10) if i not in self.owned_docs])
        if head.startswith("UPDATE documents"):
            self.owned_docs |= {i for i in range(1, 10)}
            return _Result([])
        raise AssertionError(f"FakeConn 没料到的 SQL: {text[:120]}")

    def commit(self):
        pass

    def rollback(self):
        pass


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def rowcount(self):
        return len(self._rows)


def test_ensure_columns_alters_only_when_missing():
    conn = FakeConn(existing_columns=[])
    assert migrations.ensure_columns(conn) == [("documents", "user_id")]
    assert len(conn.executed) == 1
    assert "ADD COLUMN" in conn.executed[0] and "`user_id`" in conn.executed[0]

    conn2 = FakeConn(existing_columns=[("documents", "user_id")])
    assert migrations.ensure_columns(conn2) == []
    assert conn2.executed == []


def test_ensure_default_user_is_idempotent_and_tolerates_empty_password():
    conn = FakeConn()
    first = migrations.ensure_default_user(conn, password="secret-pass")
    second = migrations.ensure_default_user(conn, password="secret-pass")
    assert first == second and len(conn.users) == 1

    blank = FakeConn()
    uid = migrations.ensure_default_user(blank, password="")
    assert uid == blank.users[0][0], "空口令也要建行：这行是旧数据的归属锚点，不能因为没口令就不建"


def test_backfill_documents_only_touches_unowned_rows():
    conn = FakeConn(owned_doc_ids={1, 2})
    changed = migrations.backfill_documents(conn, user_id=7)
    assert changed == 7, "1..9 里已归属的 1、2 必须跳过，剩下 7 行归户"
    assert len(conn.executed) == 1
    assert "WHERE user_id IS NULL" in conn.executed[0]
```

- [ ] **Step 2: 跑红**

```bash
cd backend && python -m pytest tests/test_migrations.py -q
```
预期：`ModuleNotFoundError: No module named 'core.migrations'`。

- [ ] **Step 3: 写 `core/migrations.py`**

```python
"""启动期一次性改造：建表之后补列、造默认用户、旧数据归户、旧向量补戳。

三句写在这里的话不能丢：
① 每一步都必须幂等——lifespan 每次开机都跑，开发者本地库和部署库进度不齐是常态；
② MySQL 没有 `ADD COLUMN IF NOT EXISTS`，所以"先查 information_schema 再 ALTER"
   不是洁癖，是唯一写法；
③ 补向量戳**只改 metadata，绝不重新嵌入**：重嵌一遍 22 条子块要再加载一次 0.6B
   模型，而且会改变已经验过的向量，把迁移变成一次重新灌库。
"""
import logging

from sqlalchemy import text

from core.security import hash_password

logger = logging.getLogger("kb.migrations")

DEFAULT_IDENTIFIER = "default@local"
DEFAULT_NICKNAME = "默认用户"

# (表, 列, DDL 类型)。阶段一只加 documents.user_id；chat_history.user_id 归阶段二
# （spec 2.2 勘误：历史的读写过滤和 RAGSystem 四方法要一起重接，分两轮改同一文件不值）。
MIGRATED_COLUMNS = [("documents", "user_id", "INTEGER")]


def column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(
        text("SELECT COLUMN_NAME FROM information_schema.COLUMNS "
             "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table "
             "AND COLUMN_NAME = :column"),
        {"table": table, "column": column},
    ).fetchall()
    return bool(rows)


def add_column(conn, table: str, column: str, ddl_type: str) -> None:
    # 表名/列名走 f-string 不是注入风险：三者只可能来自 MIGRATED_COLUMNS 这个模块常量，
    # MySQL 的 DDL 又不接受绑定参数——这条"只能拼"是语法事实，不是偷懒。
    conn.execute(text(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {ddl_type} NULL"))


def ensure_columns(conn) -> list:
    """返回这次真的补上的列。判据要数这个返回值，所以不能图省事返回 None。"""
    added = []
    for table, column, ddl_type in MIGRATED_COLUMNS:
        if not column_exists(conn, table, column):
            add_column(conn, table, column, ddl_type)
            added.append((table, column))
    conn.commit()
    return added


def ensure_default_user(conn, password: str) -> int:
    """旧数据的归属锚点。口令为空照样建行、不写可用哈希——spec 2.6 与 6.3 说的是同一件事：
    账号存在的意义是 `documents.user_id` 有个可指的值，能不能登录是另一回事。
    """
    existing = conn.execute(
        text("SELECT id, identifier FROM users WHERE identifier = :identifier"),
        {"identifier": DEFAULT_IDENTIFIER},
    ).fetchall()
    if existing:
        return existing[0][0]
    conn.execute(
        text("INSERT INTO users (identifier, identifier_type, nickname, avatar, "
             "password_hash, created_at) VALUES (:identifier, 'email', :nickname, "
             "'auto', :password_hash, NOW())"),
        {"identifier": DEFAULT_IDENTIFIER, "nickname": DEFAULT_NICKNAME,
         # 空口令时也要有非 NULL 的哈希（列是 NOT NULL）。存一个永不匹配的随机串，
         # 比放一个能匹配的固定值安全：那条登录路径无论如何都进不来。
         "password_hash": hash_password(password) if password else hash_password(
             "this-account-has-no-password")},
    )
    conn.commit()
    return conn.execute(
        text("SELECT id FROM users WHERE identifier = :identifier"),
        {"identifier": DEFAULT_IDENTIFIER},
    ).fetchall()[0][0]
```

> 上面这三条函数与 Step 1 的 `FakeConn` 要能对上：`ensure_default_user` 走的是 `SELECT id, identifier FROM users ...` 与 `INSERT INTO users`，`password` 为空时**仍然**插入一行。Step 1 钉的是"建行与口令无关"；"空口令账号不可登录"这句不由本 Task 的离线判据证。要说准：兜底那句串就写在源码里，所以它挡不住读代码的人，它挡住的是**库里没有一句可猜的固定口令**这件事——`.env` 留空时运营者没有对外公布过任何可登录口令，账号因此只作归属锚点。将来若要给它一条自动化判据，正确的位置是 live 组里"用 `DEFAULT_USER_PASSWORD=''` 走一次 `login` 拿 401"，而不是在这里造假哈希。

> **2026-10-06 修订：上面这段的后半作废。** "兜底那句串就写在源码里，所以它挡不住读代码的人"恰恰是它不该被当口令用的理由——那是一枚源码可见的可用凭证。空口令时改写常量 `UNUSABLE_PASSWORD_HASH`，`verify_password` 无论拿到什么都返回 `False`，并且这一步由 `test_migrations.py` 的一条纯逻辑判据钉住。详见本 Task Interfaces 处的修订 ③。"建行与口令无关"那条判据不变。

继续补三个函数（同一文件，接着写）：

```python
def backfill_documents(conn, user_id: int) -> int:
    """只捡 user_id 为 NULL 的行：已经归过户的一次 UPDATE 白扫全表。"""
    unowned = conn.execute(text("SELECT id FROM documents WHERE user_id IS NULL")).fetchall()
    if not unowned:
        return 0
    conn.execute(text("UPDATE documents SET user_id = :uid WHERE user_id IS NULL"),
                 {"uid": user_id})
    conn.commit()
    return len(unowned)


def vector_ids_without_owner(conn) -> dict:
    """补戳的输入清单：parent_chunks/child_chunks 里那些所属文档还没有 user_id 的向量 id。

    真库上这两列存的**就是** Chroma 的 id（2026-10-04 已 live 验过：用它删向量，
    计数如实下降），所以直接拿它当 get/update 的 ids，不需要任何映射。
    """
    out = {"parent": [], "child": []}
    for key, table in (("parent", "parent_chunks"), ("child", "child_chunks")):
        rows = conn.execute(text(
            f"SELECT c.vector_id FROM {table} c "
            "JOIN documents d ON d.id = c.document_id "
            "WHERE c.vector_id IS NOT NULL AND c.vector_id <> '' AND d.user_id IS NULL"
        )).fetchall()
        out[key] = [r[0] for r in rows]
    return out


def stamp_vector_owner(client, vector_ids: dict, user_id: int) -> int:
    """把无主的旧向量补上 user_id 戳。get → merge → update，跳过已戳的。

    为什么不依赖"Chroma 的 update 只补提供的键"这个较新版本的语义：真依赖它的迁移，
    在语义变化时会静默清掉 document_id/parent_id 这类既有 metadata，而那两个键一丢，
    召回与按文档清扫会同时坏掉，且没有任何报错。读回来合并写是最保守的做法。
    """
    from core.vector_store import COLLECTION_CHILD, COLLECTION_PARENT

    total = 0
    for name, ids in ((COLLECTION_PARENT, vector_ids["parent"]),
                      (COLLECTION_CHILD, vector_ids["child"])):
        if not ids:
            continue
        collection = client.get_collection(name)
        found = collection.get(ids=ids, include=["metadatas"])
        to_update, metadatas = [], []
        for vid, meta in zip(found["ids"], found["metadatas"]):
            meta = meta or {}
            if str(meta.get("user_id", "")) == str(user_id):
                continue  # 已戳：让"每次开机重跑"退化成一次只读扫描
            to_update.append(vid)
            metadatas.append({**meta, "user_id": str(user_id)})
        if to_update:
            collection.update(ids=to_update, metadatas=metadatas)
            total += len(to_update)
    return total


def run_migrations(engine, chroma_client, password: str) -> dict:
    """lifespan 唯一入口。返回一份可直接进日志的汇总，不返回秘密（没有令牌、没有哈希）。"""
    with engine.connect() as conn:
        added = ensure_columns(conn)
        user_id = ensure_default_user(conn, password)
        docs = backfill_documents(conn, user_id)
        pending = vector_ids_without_owner(conn) if docs else {"parent": [], "child": []}
    # 补戳放在连接之外：Chroma 那边可能是一次几秒的只读扫描，别把 MySQL 连接摁在它上面
    vectors = stamp_vector_owner(chroma_client, pending, user_id)
    summary = {"columns_added": added, "default_user_id": user_id,
               "documents_claimed": docs, "vectors_stamped": vectors}
    logger.info("迁移完成: %s", summary)
    return summary
```

> **2026-10-06 修订（补索引，见 Interfaces 处修订 ①）**：`with engine.connect() as conn:` 那一块里，`added = ensure_columns(conn)` 之后**紧接**一行 `indexes = ensure_indexes(conn)`（顺序不能颠倒：列还没加出来就建索引会当场炸），`summary` 字典在 `columns_added` 之后多一格 `"indexes_added": indexes`。其余四格与日志语句不变。

`pending` 那句 `if docs else {...}` 是刻意的短路：只有真归户了文档才可能留下无主向量。第二遍开机 `backfill_documents` 回 0，于是向量那步一次 `get` 都不发，整个迁移退化成"两条 SELECT"。

> **2026-10-07 修订（预飞检查裁定：`run_migrations` 里这两步的顺序反了，补戳在那份原文下永远拿不到清单）**
> `backfill_documents` 的最后一句是 `conn.commit()`（本 Step 上面），而 `vector_ids_without_owner` 的筛选条件是 `d.user_id IS NULL`。按原文顺序 `docs = backfill_documents(...)` 在前、`pending = vector_ids_without_owner(conn)` 在后：commit 之后库里**一行 NULL 都不剩**，于是 `pending` 恒为 `{"parent": [], "child": []}`，`stamp_vector_owner` 一步 `get` 都不会发、`vectors_stamped` **永远是 0**。`FakeConn` 那三条纯逻辑判据演的是"发了什么 SQL"，对顺序无感；Step 7 的 live 判据只查 `documents`，也照不出来——唯一能暴露它的是日志里那一格。后果不是"阶段一读数不对"（读侧 `$and` 过滤按勘误属阶段二），而是**补戳整段是死代码**：阶段一要落地 `user_id` 戳，靠的正是这一步。
>
> **裁定：把读放在写之前**，`with engine.connect() as conn:` 那块改成四行（其余不动）：
>
> ```python
>         added = ensure_columns(conn)
>         indexes = ensure_indexes(conn)
>         user_id = ensure_default_user(conn, password)
>         # 清单必须在归户之前读：backfill_documents 自己会 commit，之后 NULL 行就不存在了
>         pending = vector_ids_without_owner(conn)
>         docs = backfill_documents(conn, user_id)
>         if not docs:
>             pending = {"parent": [], "child": []}
> ```
>
> 短路语义与原文一致（幂等第二遍 `docs == 0`，`stamp_vector_owner` 一次 `get` 都不发），代价是静默那一遍多两条**返回空**的 SELECT——比"补戳静默失效"便宜得多。
>
> **新增一条判据（本修订自带，必须落）**：`test_migrations.py` 里给 `run_migrations` 加一条用 `FakeConn` + 假 client 的测，钉住**调用顺序**：断言 fake client 收到的 `get_collection`/`get` 里带的 id 清单，就是那条 `SELECT ... WHERE ... d.user_id IS NULL` 返回的行（即"清单来自归户之前"）。做法自选，但**不许**只断言 `vectors_stamped > 0`——把两条 SELECT 的顺序写反，那种断言在假连接下照样绿。

- [ ] **Step 4: 补三条纯逻辑判据（假 Chroma client + 真哈希）**

`backend/tests/test_migrations.py` 追加：

```python
class FakeCollection:
    """只实现 stamp_vector_owner 用到的 get/update，并把写过的东西留在身上。"""

    def __init__(self, items):
        self.items = items          # {id: metadata}

    def get(self, ids=None, include=None):
        picked = list(ids) if ids else list(self.items)
        return {"ids": [i for i in picked if i in self.items],
                "metadatas": [self.items[i] for i in picked if i in self.items]}

    def update(self, ids, metadatas):
        for i, m in zip(ids, metadatas):
            self.items[i] = m


class FakeChroma:
    def __init__(self, collections):
        self.collections = collections

    def get_collection(self, name):
        return self.collections[name]


def test_stamp_merges_existing_metadata_and_skips_stamped():
    parent = FakeCollection({
        "p1": {"document_id": "3", "parent_id": "x_parent_0"},
        "p2": {"document_id": "4", "user_id": "7"},
    })
    client = FakeChroma({"parent_document": parent, "child_document": FakeCollection({})})
    # 重跑第二遍必须是零写：判据靠返回值，不靠"看起来没报错"
    assert migrations.stamp_vector_owner(client, {"parent": ["p1", "p2"], "child": []}, 7) == 1
    assert parent.items["p1"] == {"document_id": "3", "parent_id": "x_parent_0", "user_id": "7"}
    assert migrations.stamp_vector_owner(client, {"parent": ["p1", "p2"], "child": []}, 7) == 0


def test_stamp_never_rewrites_a_foreign_users_vector():
    """已戳但戳的是**别人**的向量不该被动——迁移只补 NULL，不改归属。"""
    parent = FakeCollection({"p1": {"user_id": "9"}})
    client = FakeChroma({"parent_document": parent, "child_document": FakeCollection({})})
    assert migrations.stamp_vector_owner(client, {"parent": ["p1"], "child": []}, 7) == 0
    assert parent.items["p1"] == {"user_id": "9"}


def test_default_identifier_is_the_one_the_spec_names():
    assert migrations.DEFAULT_IDENTIFIER == "default@local"
    assert migrations.MIGRATED_COLUMNS == [("documents", "user_id", "INTEGER")]
```

- [ ] **Step 5: 全绿这一文件的默认门**

```bash
cd backend && python -m pytest tests/test_migrations.py -q
```
预期：`6 passed`（Step 1 三条 SQL 决策 + Step 4 三条补戳/常量判据）。红得最可能的地方是 `FakeConn.execute` 的分支匹配——`str(sql)` 在不同 SQLAlchemy 版本上可能带上注释或换行前缀，所以判据一律用 `strip().upper()` 之后比对关键字开头，别去比完整 SQL 文本。

- [ ] **Step 6: lifespan 接线**

`backend/main.py`：

```python
from core.migrations import run_migrations
```

`app.state.vector_store = VectorStore(config)` 与 `app.state.rag_system = RAGSystem(...)` **之间**插：

```python
    # 迁移挂在 lifespan 而不是 DatabaseManager.init_database：
    # ① test_observability.py 钉死了 init 只发 engine + create_all 两次调用；
    # ② 补向量戳需要 vector_store 那个 Chroma client，它在 db 之后才构造。
    # 每次开机重跑，靠幂等把三处不同进度的库收拢（core/migrations.py 顶部）。
    run_migrations(app.state.db.engine, app.state.vector_store.chroma_client,
                   config.DEFAULT_USER_PASSWORD)
```

这五行放 `logger.info("后端初始化完成...")` 之前。`RAGSystem` 的构造位置不动——它不读迁移结果，放在它前后都行，但**放在 `VectorStore` 之后**是硬要求。

- [ ] **Step 7: live 判据（真 MySQL + 真 Chroma + tmp_path 只读副本）**

`backend/tests/test_live_database.py` 末尾追加：

```python
@pytest.mark.live
def test_migration_columns_are_present_and_the_second_pass_is_quiet(db):
    """`ADD COLUMN` 的真语义只有真库能证，而这条判据钉的是"第二遍零 ALTER"。

    这里绝不主动触发第一遍：测试不许改共享库的结构（基线判据靠它）。列的存在本身就是
    证据——它只可能由 lifespan 那次 run_migrations 补出来。
    """
    from sqlalchemy import text

    from core import migrations

    with db.engine.connect() as conn:
        assert migrations.column_exists(conn, "documents", "user_id"), (
            "documents.user_id 不存在：服务没重启过，或迁移没接进 lifespan"
        )
        before = len(conn.execute(text("SHOW COLUMNS FROM documents")).fetchall())
        assert migrations.ensure_columns(conn) == []
        assert migrations.ensure_columns(conn) == []
        after = len(conn.execute(text("SHOW COLUMNS FROM documents")).fetchall())
    assert after == before, "两次 ensure_columns 之间列数变了：幂等破了"


@pytest.mark.live
def test_default_user_exists_and_owns_the_baseline_documents(db):
    """spec 7.3 的第 5 条判据（旧数据归位 SQL 直查）搬进自动化：基线 13 行全归 default。

    13 是 documents 的**物理行数**（4 篇活 + 9 篇删块删到 is_active=0 的隐存行），不是
    `/api/health` 那个活文档计数——归户 SQL 是 `WHERE user_id IS NULL`，隐存行同样要归户。

    这条不成立就说明 lifespan 那次 run_migrations 没跑成——手动起服务时最容易漏。
    """
    from sqlalchemy import text

    from core.migrations import DEFAULT_IDENTIFIER

    with db.engine.connect() as conn:
        row = conn.execute(text(
            "SELECT id FROM users WHERE identifier = :i"), {"i": DEFAULT_IDENTIFIER}).fetchall()
        assert row, "默认用户行没建出来：迁移没跑或跑在 create_all 之前"
        default_id = row[0][0]
        owned = conn.execute(text(
            "SELECT COUNT(*) FROM documents WHERE user_id = :u"), {"u": default_id}).fetchone()[0]
        unowned = conn.execute(text(
            "SELECT COUNT(*) FROM documents WHERE user_id IS NULL")).fetchone()[0]
    assert unowned == 0, f"还有 {unowned} 篇文档无主，归户那步没做完"
    assert owned == 13, f"基线 13 行应全归 default，实得 {owned}"
```

> **2026-10-06 修订（上面第一条 live 测补索引那一半，见 Interfaces 处修订 ①）**：`test_migration_columns_are_present_and_the_second_pass_is_quiet` 里，紧接列的两次 `ensure_columns(conn) == []` 之后再加索引的三句——`assert migrations.index_exists(conn, "documents", "idx_documents_user_id")`、`assert migrations.ensure_indexes(conn) == []` 两次、以及 `SHOW INDEX FROM documents` 的行数在两次 `ensure_indexes` 前后相等。这是全计划里唯一**直接查已部署 schema**（而非 ORM 元数据）的索引判据。本机这一列和这一索引都是 Task 1 执行期提前落好的，所以首轮就应当全为真（`columns_added` 那格退化成 `[]`，见 Task 1 Step 9 处的修订）。

向量补戳的 live 判据放 `backend/tests/test_chroma_data.py`（那个文件已经是"在 tmp_path 副本上开库"的形态，抄现成的）：

```python
@pytest.mark.migration
def test_old_vectors_get_a_user_id_stamp_on_a_copy(tmp_path):
    """补戳的真证据：tmp 副本上跑一次 stamp_vector_owner，metadata 多一个键、文本没变。

    绝不在 Config.CHROMA_PERSIST_DIR 上跑：PersistentClient 会回写 chroma.sqlite3，
    和正在服务的 uvicorn 抢同一份文件（项目记忆：同时只跑得起一份）。
    """
    import chromadb
    from chromadb.config import Settings

    from core import migrations

    store = tmp_path / "chroma_db"
    shutil.copytree(Config.CHROMA_PERSIST_DIR, store)
    client = chromadb.PersistentClient(path=str(store),
                                       settings=Settings(anonymized_telemetry=False))
    parent = client.get_collection("parent_document")
    ids = parent.get()["ids"]
    before = {i: m for i, m in zip(ids, parent.get(ids=ids, include=["metadatas"])["metadatas"])}
    before_texts = parent.get(ids=ids, include=["documents"])["documents"]

    stamped = migrations.stamp_vector_owner(client, {"parent": ids, "child": []}, 1)
    assert stamped == len(ids)

    after = parent.get(ids=ids, include=["metadatas", "documents"])
    for vid, meta in zip(after["ids"], after["metadatas"]):
        assert meta["user_id"] == "1", f"{vid} 补戳没生效"
        # 合并写回的代价就是这条判据必须存在：原有键一个都不能丢
        assert all(meta.get(k) == v for k, v in before[vid].items())
    assert after["documents"] == before_texts, "补戳把向量文本改了：这不是迁移，是重新灌库"

    # 重跑退化成只读扫描
    assert migrations.stamp_vector_owner(client, {"parent": ids, "child": []}, 1) == 0
```

- [ ] **Step 8: 双门禁 + 提交**

```bash
cd backend && python -m pytest -q
cd backend && python -m pytest -m live -q
cd backend && python -m pytest -m migration -q
```
预期：默认门 `221 passed / 0 skipped / 1 deselected` 左右（Task 2 的 213 + 本 Task 的 6 条离线 + 2 条 live）；`-m live` 在原条数上 +2；`-m migration` **+1**（新那条向量补戳也带这个标记，从 1 条变 2 条）。**只抄汇总行**，且 `failed` 必须为 0。

这两条 live 判据都**要求服务先重启一次**（列和默认用户行是 lifespan 补的，不是测试自己建的）；先做 Step 8 末尾的手工确认，再跑 `-m live`，否则红的会是"前置条件缺失"，容易被误读成迁移逻辑错了。`test_chroma_data.py` 那条沿用文件里现成的 `shutil`/`Config`/`tmp_path` 形态，不需要新增导入。

```bash
cd D:/知识库平台-前后端分离 && git add backend/core/migrations.py backend/tests/test_migrations.py \
  backend/main.py backend/tests/test_live_database.py backend/tests/test_chroma_data.py
git status --short
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(backend): 启动期幂等迁移——补列、默认用户、旧数据归户、旧向量补戳（阶段一 Task 3）"
```

**手工确认一次真迁移**（起服务是唯一能验 lifespan 的途径，pytest 里 `create_app()` 不进 `with`）：
1. 重启**自己起的那一个** uvicorn（绝不启第二个）；
2. `curl http://localhost:8000/api/health` → 仍 `documents 9 / parent 11 / child 22`；
3. 日志里应出现一行 `迁移完成: {...}`，`columns_added` 首次是 `[('documents', 'user_id')]`、第二次起是 `[]`，`documents_claimed` 首次 9、之后 0。

> **2026-10-06 修订（第 3 条的本机预期）**：列和索引都已在 Task 1 执行期落到真实 MySQL（见 Task 1 Step 9 处的修订），所以本机这次重启的日志里 `columns_added: []`、`indexes_added: []`，**不要**期待首轮出现 `('documents', 'user_id')`——那条分支的活证已由 Task 3 的 `FakeConn` 单测（缺列/缺索引才发 DDL）与 Step 7 live 的"二次返回 `[]`"共同守住。本机唯一还活着的迁移证据是 `documents_claimed: 9 → 0` 与 `vectors_stamped`。字典键按修订 ① 是 5 个（`columns_added` / `indexes_added` / `default_user_id` / `documents_claimed` / `vectors_stamped`）。

> **2026-10-07 修订（上面两条的本机预期值，按重钉后的新基线）**
> 第 2 条按全局基线修订 ② 改判：`curl http://localhost:8000/api/health` 这次应当拿到 **`document_count: 4`** 与 **`vector_counts: {"parent": 4, "child": 10}`**（键名就是 `parent` / `child`，见 `core/vector_store.py:51-55`；`document_count` 走 `count_documents()`，只数 `is_active`，隐存那 9 行不在里面；`vector_counts` 才是物理计数）。
> 第 3 条的实数预期（2026-10-07 直查 MySQL 得到，不是推算）：**首轮** `documents_claimed: 13`（13 行全 `user_id IS NULL`，含 9 行隐存）、`vectors_stamped: 14`（4 个父块向量 + 10 个子块向量，`vector_id 非空` 的计数实测就是 4 与 10）；**次轮** `documents_claimed: 0`、`vectors_stamped: 0`。
> 这一格与 Step 3 那条顺序修订是**同一枚证据的两面**：按原文顺序（先归户 commit、后读 NULL 清单）首轮 `vectors_stamped` 会是 **0** 而不是 14，而这在纯逻辑判据里照不出来。所以本次手工确认**必须把日志原文抄进台账**，`vectors_stamped: 0` 首轮即视为失败，不要当成"这台机器不需要补戳"。

### Task 4: `documents` 侧的归属——写进去带上主人，读出来只给主人

**Files:**
- Modify: `backend/core/database.py`（`save_document`/`get_document`/`get_all_documents`/`search_parent_chunks`/`plan_chunk_deletion`/`delete_parent_chunk` 六个方法加归属，`_find_parent_chunk` 跟着改，新增 `owned_parent_ids`）
- Modify: `backend/core/vector_store.py`（`add_documents` 补 `user_id` 戳）
- Modify: `backend/api/documents.py`（4 个端点加 `Depends(get_current_user)`，把 `user.id` 传到每一层）
- Modify: `backend/tests/fakes.py`（`FakeUser` + `with_auth`，这是 spec 7.1 那 20+9 条端点测的统一落点）
- Modify: `backend/tests/test_api_documents.py`、`backend/tests/test_chunk_search.py`（假库签名 + `make_client`）
- Create: `backend/tests/test_ownership_isolation.py`
- Modify: `backend/tests/test_live_database.py`（32 处调用点带 `user_id`、`probe_user` 夹具、补上 Task 2 Step 6 暂缓的那条）

**Interfaces:**
- Consumes：`deps.get_current_user`（Task 2）、`Document.user_id`（Task 1）、`vector_ids_for_user`（Task 1）。

> **2026-10-06 修订（Task 1 落地后）：上面第三项是错的。** `vector_ids_for_user` 从未落地（Task 1 任务评审按死代码打回删除，见 Task 1 Interfaces 处的修订）。本 Task 实际消费的是 `Document.user_id`（Task 1）、`deps.get_current_user`（Task 2）与 `DatabaseManager` 上按 `user_id` 归属的那批方法；按用户取向量 id 的能力属于 Task 3 的 `vector_ids_without_owner`（原始连接、语义是"仍未归户"，不是"按用户"），本 Task 不调它。
- Produces：
  - `DatabaseManager.save_document(..., *, user_id)`、`get_document(doc_id, *, user_id)`、`get_all_documents(*, user_id)`、`search_parent_chunks(*, user_id, query="", suffix="", parent_ids=(), limit=50)`、`plan_chunk_deletion(document_id, parent_id, *, user_id)`、`delete_parent_chunk(document_id, parent_id, *, user_id)`、`owned_parent_ids(parent_ids, *, user_id) -> list[str]`
  - `VectorStore.add_documents(parent_docs, child_docs, document_id, *, user_id)`
  - `fakes.FakeUser(id, identifier, identifier_type, nickname, avatar)`、`fakes.with_auth(app, user=None)`
  - 4 个 documents 端点：**未登录 401 / 越权 404**

**这一 Task 的一句话主张**：归属不是靠"前端不给你别人的 id"保证的，是靠**每条 SQL 都带 `user_id`** 保证的（spec 3.3，决策 7 的主防线）。所以 `user_id` 一律做成 **keyword-only 且无默认值**——忘记传它会 `TypeError` 当场炸，而不是静默写出一行 `user_id IS NULL` 的文档，让它出现在所有人的候选池里。**这类"忘了就编译不过"的形状，是隔离唯一能长期活下来的写法。**

- [ ] **Step 1: 写失败的隔离判据（离线：转发 + 越权 404 + 缺令牌 401）**

创建 `backend/tests/test_ownership_isolation.py`：

```python
"""归属的服务端一侧（spec 3.3）。

离线判据只能证两件事：**端点把 user.id 传下去了**、**越权拿到 404**。
"甲的列表里没有乙的文档"这种真过滤 fake 演不出来，归 live 组（Step 7）。
"""
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from deps import get_current_user, get_db, get_doc_processor, get_vector_store
from fakes import FakeDocProcessor, FakeUser, FakeVectorStore, with_auth
from main import create_app

OWNER = 1
INTRUDER = 2


class OwnerAwareDB:
    """假库只做两件事：记下每次调用收到的 user_id，以及**按它过滤**。

    记下参数才能钉住"端点没漏传"；按它过滤才能钉住"漏传之后行为会怎么变"——
    两个都是判据，缺一个就会留下一类静默越权。
    """

    def __init__(self):
        self.calls = []                       # [(方法名, user_id)]
        self.doc_owner = OWNER
        self.rows = [SimpleNamespace(id=7, filename="甲.txt", chunk_count=1,
                                     created_at=datetime(2026, 10, 6))]

    def _record(self, name, user_id):
        self.calls.append((name, user_id))
        return user_id == self.doc_owner

    def save_document(self, filename, file_path, content, chunk_count=0, *, user_id):
        self._record("save_document", user_id)
        return 7

    def save_chunks(self, doc_id, parent_docs, child_docs, parent_ids, child_ids):
        pass

    def get_document(self, doc_id, *, user_id):
        if not self._record("get_document", user_id):
            return None
        return self.rows[0]

    def get_all_documents(self, *, user_id):
        self._record("get_all_documents", user_id)
        return list(self.rows) if user_id == self.doc_owner else []

    def search_parent_chunks(self, *, user_id, query="", suffix="", parent_ids=(), limit=50):
        self._record("search_parent_chunks", user_id)
        if user_id != self.doc_owner:
            return []
        return [SimpleNamespace(parent_id="甲.txt_parent_0", document_id=7,
                                content="正文", filename="甲.txt", child_count=2)]

    def plan_chunk_deletion(self, document_id, parent_id, *, user_id):
        if not self._record("plan_chunk_deletion", user_id):
            return None
        return {"document_id": document_id, "parent_id": parent_id,
                "parent_vector_id": "pv", "child_vector_ids": ["cv"]}

    def delete_parent_chunk(self, document_id, parent_id, *, user_id):
        self._record("delete_parent_chunk", user_id)
        return {"deleted_children": 1, "chunk_count": 0, "document_hidden": True}

    def owned_parent_ids(self, parent_ids, *, user_id):
        """Task 5 的问答白名单靠它：不是你的块就不出现在返回值里。

        口径与真库上那个方法逐字一致——按入参去重、别人的静默少回。
        """
        if not self._record("owned_parent_ids", user_id):
            return []
        return [pid for pid in dict.fromkeys(parent_ids) if pid == "甲.txt_parent_0"]

    def get_chat_history(self, session_id, limit=10):
        return []

    def delete_chat_history(self, session_id):
        return 0

    def delete_document(self, doc_id):
        return 1


class StampingVectorStore(FakeVectorStore):
    def __init__(self):
        super().__init__()
        self.stamped_with = []

    def add_documents(self, parent_docs, child_docs, document_id, *, user_id):
        self.stamped_with.append(user_id)
        return super().add_documents(parent_docs, child_docs, document_id)


def make_client(db, user=FakeUser(user_id=OWNER), vector_store=None, gate=True):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_doc_processor] = lambda: FakeDocProcessor()
    store = vector_store or StampingVectorStore()
    app.dependency_overrides[get_vector_store] = lambda: store
    # gate=False 时不覆盖 get_current_user——真依赖会去库里查令牌，这就是 401 判据的走法
    if gate:
        with_auth(app, user)
    return TestClient(app), store


def test_upload_stamps_the_owner_in_database_and_vectors():
    db = OwnerAwareDB()
    client, store = make_client(db)
    res = client.post("/api/documents", files={"file": ("甲.txt", "正文".encode("utf-8"), "text/plain")})
    assert res.status_code == 201
    assert ("save_document", OWNER) in db.calls
    assert store.stamped_with == [OWNER]


def test_list_and_chunks_forward_the_owner():
    db = OwnerAwareDB()
    client, _ = make_client(db, user=FakeUser(user_id=OWNER))
    assert client.get("/api/documents").status_code == 200
    assert client.get("/api/documents/chunks").status_code == 200
    assert ("get_all_documents", OWNER) in db.calls
    assert ("search_parent_chunks", OWNER) in db.calls

    other = OwnerAwareDB()
    client2, _ = make_client(other, user=FakeUser(user_id=INTRUDER))
    assert client2.get("/api/documents").json() == []
    assert client2.get("/api/documents/chunks").json() == []


def test_deleting_another_users_chunk_is_404_with_the_existing_line():
    """越权与不存在共用一句文案：区分它们等于承认"这块存在"。"""
    db = OwnerAwareDB()
    client, _ = make_client(db, user=FakeUser(user_id=INTRUDER))
    res = client.delete("/api/documents/7/chunks/甲.txt_parent_0")
    assert res.status_code == 404
    assert res.json() == {"detail": "文档块不存在或已被删除"}
    assert ("plan_chunk_deletion", INTRUDER) in db.calls


@pytest.mark.parametrize("method,path", [
    ("post", "/api/documents"),
    ("get", "/api/documents"),
    ("get", "/api/documents/chunks"),
    ("delete", "/api/documents/7/chunks/x_parent_0"),
])
def test_documents_endpoints_reject_a_missing_token(method, path):
    """spec 3.2 那张清单的前四条。Task 5 会把 chat/history 那四条并进来。"""
    client, _ = make_client(OwnerAwareDB(), gate=False)
    res = getattr(client, method)(path)
    assert res.status_code == 401
    assert res.json() == {"detail": "未登录或登录已过期"}
```

- [ ] **Step 2: 跑红**

```bash
cd backend && python -m pytest tests/test_ownership_isolation.py -q
```
预期：全部失败，且**第一批红是 `ImportError: cannot import name 'FakeUser'`**（Step 3 才加）。先补 fakes 再回来，红因会变成"端点没有 `user_id` 这个 kwarg"——那才是这条 Task 真正的起点。

- [ ] **Step 3: `tests/fakes.py` 加两件公共替身**

```python
class FakeUser:
    """认证依赖在端点测试里的最小替身。

    业务代码只读 `.id`（归属）与 `.nickname`/`.avatar`（出参），所以这里只给这几个字段：
    多给一个用不到的字段，就多一个"测试通过但真 ORM 行里没有它"的坑。
    """

    def __init__(self, user_id=1, identifier="probe@local", nickname="探针"):
        self.id = user_id
        self.identifier = identifier
        self.identifier_type = "email"
        self.nickname = nickname
        self.avatar = "auto"


def with_auth(app, user=None):
    """spec 7.1：各模块自己的 make_client 都要覆盖这一格，写成一函数免得五处各写各的。"""
    from deps import get_current_user

    app.dependency_overrides[get_current_user] = lambda: user or FakeUser()
    return app
```

同文件把 `FakeVectorStore.add_documents` 的签名跟上（**默认值让它能同时服务新旧两组判据**）：

```python
    def add_documents(self, parent_docs, child_docs, document_id, *, user_id=None):
        self.stamped_user = user_id
        return [f"p{i}" for i in range(len(parent_docs))], [f"c{i}" for i in range(len(child_docs))]
```

> `FakeVectorStore` 这一格是给 `test_api_documents.py` 那 20 条用的，所以 `user_id` 给默认值 `None`：Step 6 改完端点之后所有调用都会带真值，`None` 只存在于"端点漏传"这一种坏情况——而它正是 Step 6 那条判据要抓的东西。`test_ownership_isolation.py` 里那个 `StampingVectorStore` 不给默认值，是要在**类型层面**就要求传。

- [ ] **Step 4: `core/database.py` 六个方法带归属**

```python
    def save_document(self, filename, file_path, content, chunk_count=0, *, user_id):
        """保存文档主记录，返回doc_id

        user_id 做成 keyword-only 且无默认值：忘记传归属必须是 TypeError 当场炸，
        不能是"写出一行 user_id IS NULL，于是它出现在所有人的候选池里"。
        NULL 只属于迁移前的旧行（Task 3 会把它们归给默认用户）。
        """
        session = self.get_session()
        try:
            doc = Document(
                filename=filename,
                file_path=file_path,
                content=content,
                chunk_count=chunk_count,
                user_id=user_id
            )
            session.add(doc)
            session.commit()
            return doc.id
        finally:
            session.close()

    def get_all_documents(self, *, user_id):
        """当前用户的活动文档列表。原来那句 `filter(is_active == True)` 一个条件都没减，
        只是前面多了一道主人——列表类端点的隔离成本就是这样，一行 WHERE。"""
        session = self.get_session()
        try:
            return (session.query(Document)
                    .filter(Document.is_active == True, Document.user_id == user_id)
                    .all())
        finally:
            session.close()

    def get_document(self, doc_id, *, user_id):
        """按 id 取文档，但只取属于这个用户的。越权与不存在都回 None。

        不用 `session.get` 再看属性：那样写要多一次对象访问，而且把"先确认存在、再说没权限"
        的顺序带进了 SQL——404 的语义要求在**同一条** WHERE 里同时比 id 和主人。
        """
        session = self.get_session()
        try:
            return (session.query(Document)
                    .filter(Document.id == doc_id, Document.user_id == user_id)
                    .first())
        finally:
            session.close()
```

`_find_parent_chunk` 加一道 join（原注释里那句"单靠 parent_id 会把别人的块删掉"说的就是这件事，现在把主人变成查询条件的一部分）：

```python
    def _find_parent_chunk(self, session, document_id, parent_id, user_id):
        """定位父块要 (document_id, parent_id) 这一对，外加"这块的主人是你"。

        parent_id 由清洗后的文件名拼出来，同名文档能造出同样的字符串；而 user_id 这一道
        挡的是另一件事：拿着别人 document_id 的请求。两者都要，缺一不可。
        """
        return (session.query(ParentChunk)
                .join(Document, Document.id == ParentChunk.document_id)
                .filter(ParentChunk.document_id == document_id,
                        ParentChunk.parent_id == parent_id,
                        Document.user_id == user_id)
                .first())
```

`search_parent_chunks` 在已有的 `Document.is_active == True` 后面加一行；`plan_chunk_deletion` / `delete_parent_chunk` 加 `*, user_id` 并透传给 `_find_parent_chunk`（`delete_parent_chunk` 里那句 `session.get(Document, document_id)` 改成 `self._owned_document(session, document_id, user_id)` 的私有小助手，或直接在方法开头 `doc = session.query(Document).filter(Document.id == document_id, Document.user_id == user_id).first()`——**它本来就在同一个 session 里，不用新开一次查询**）：

```python
    def search_parent_chunks(self, *, user_id, query="", suffix="", parent_ids=(), limit=50):
        # 文档串里的三条规矩一条没变，只在 is_active 旁边补一句"还得是你的"
        ...
                .filter(Document.is_active == True, Document.user_id == user_id)
        ...
```

新增一条给 Task 5 用的白名单方法（放 `document_ids_for_parents` 旁边，两者形状一样、只是多一道归属）：

```python
    def owned_parent_ids(self, parent_ids, *, user_id):
        """父块白名单：只回"确实属于这个用户"的那些 id。

        按入参顺序去重、库里没有的静默少回——与 document_ids_for_parents 同一口径。
        端点拿它和原始列表比长度，少一个就说明有人递了别人的 parent_id，回 404。
        """
        ids = list(dict.fromkeys(parent_ids))
        if not ids:
            return []
        session = self.get_session()
        try:
            rows = (session.query(ParentChunk.parent_id)
                    .join(Document, Document.id == ParentChunk.document_id)
                    .filter(ParentChunk.parent_id.in_(ids), Document.user_id == user_id)
                    .all())
        finally:
            session.close()
        allowed = {r.parent_id for r in rows}
        return [pid for pid in ids if pid in allowed]
```

`delete_document(doc_id)` **不加归属**：它只服务两处——上传失败的自我回滚（那行刚由自己写）和 live 测试的清理。给它加 `user_id` 会让回滚代码多一条"删除失败因为查不到"的歧义路径，而那条路径不可能发生。这是一处**有意为之的不对称**，写在计划里是为了让下一轮读到的人不手痒去"补全"它。

- [ ] **Step 5: `core/vector_store.py` 写侧补戳**

```python
    def add_documents(self, parent_docs, child_docs, document_id, *, user_id):
        """添加文档到向量存储，顺手给每个向量打上主人。

        user_id 存成字符串：`document_id` 早就这么干了（下一行），两个键形态一致才不会出现
        "一个能等值比、一个不能"的坑（Chroma 的 where 是标量相等）。
        这一期只补戳、不做读侧过滤（spec 2.5 勘误）：parent_id 全库唯一，
        读侧那道 $and 在阶段一不是承重墙，等阶段二收窄召回池时一起接。
        """
        for doc in parent_docs + child_docs:
            doc.metadata['document_id'] = str(document_id)
            doc.metadata['user_id'] = str(user_id)
```

- [ ] **Step 6: `api/documents.py` 四个端点上门**

导入加两行：

```python
from deps import get_current_user, get_db, get_doc_processor, get_vector_store
```

四个端点各加 `user=Depends(get_current_user)`（**放在参数表最后**，FastAPI 的依赖注入顺序不影响行为，但放最后能让"这是新加的门"在 diff 里一眼可见），并把 `user.id` 传到每一层：

```python
@router.post("", status_code=201, response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    db=Depends(get_db),
    processor=Depends(get_doc_processor),
    vector_store=Depends(get_vector_store),
    user=Depends(get_current_user),
):
    ...
    doc_id = db.save_document(filename=filename, file_path="", content=content,
                              chunk_count=len(child_docs), user_id=user.id)
    ...
        parent_ids, child_ids = vector_store.add_documents(parent_docs, child_docs, doc_id,
                                                           user_id=user.id)
    ...
    saved = db.get_document(doc_id, user_id=user.id)
```

回滚三步（`delete_by_document_id` / `delete_by_ids` / `delete_document`）**一行都不改**：它们清的是刚由这个请求写出来的东西，谈不上越权。

```python
@router.get("", response_model=list[DocumentOut])
def list_documents(db=Depends(get_db), user=Depends(get_current_user)):
    return [... for d in db.get_all_documents(user_id=user.id)]


@router.get("/chunks", response_model=list[ChunkOut])
def list_chunks(query=..., suffix=..., parent_ids=..., limit=...,
                db=Depends(get_db), user=Depends(get_current_user)):
    rows = db.search_parent_chunks(user_id=user.id, query=query, suffix=suffix,
                                   parent_ids=list(dict.fromkeys(parent_ids)), limit=limit)
    ...


@router.delete("/{document_id}/chunks/{parent_id}", response_model=DocumentOut)
def delete_parent_chunk(document_id: int, parent_id: str,
                        db=Depends(get_db), vector_store=Depends(get_vector_store),
                        user=Depends(get_current_user)):
    plan = db.plan_chunk_deletion(document_id, parent_id, user_id=user.id)
    if plan is None:
        # 这一句现在盖三种情况：不存在、已删过、**别人的**。合起来正是 404 该有的样子
        raise HTTPException(status_code=404, detail="文档块不存在或已被删除")
    ...
    db.delete_parent_chunk(document_id, parent_id, user_id=user.id)
    saved = db.get_document(document_id, user_id=user.id)
```

跑 Step 1 的隔离文件：

```bash
cd backend && python -m pytest tests/test_ownership_isolation.py -q
```
预期：`7 passed`（3 条转发/越权 + 那条参数化展开成 4 条 401）。

- [ ] **Step 7: 既有 20 + 9 条端点测的连带改造（spec 7.1 那张表的落点）**

`tests/test_api_documents.py`：`RecordingDB` 的四个方法签名跟上（`save_document(..., *, user_id=None)`、`get_document(doc_id, *, user_id=None)`、`get_all_documents(*, user_id=None)`、`plan_chunk_deletion(document_id, parent_id, *, user_id=None)`、`delete_parent_chunk(document_id, parent_id, *, user_id=None)`），`make_client` 加一行覆盖并留一个 `user` 形参：

```python
from deps import get_current_user, get_db, get_doc_processor, get_vector_store
from fakes import FakeDocProcessor, FakeUser, FakeVectorStore, with_auth


def make_client(db, processor=None, vector_store=None, user=None):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_doc_processor] = lambda: processor or FakeDocProcessor()
    app.dependency_overrides[get_vector_store] = lambda: vector_store or FakeVectorStore()
    with_auth(app, user or FakeUser(user_id=1))
    return TestClient(app)
```

假库里 `user_id` 给默认值 `None` 的用意：那 20 条判据里凡是断言 `db.saved_docs` 的都不必改，只有**新加**的一条断言它收到真 id：

```python
def test_upload_records_the_owner_id_on_the_document_row():
    db = RecordingDB()
    make_client(db, user=FakeUser(user_id=77))
    ...   # 断言 db.saved_user_ids == [77]
```
（`RecordingDB.save_document` 里加 `self.saved_user_ids.append(user_id)`。）

`tests/test_chunk_search.py`：`ChunkSearchDB.search_parent_chunks` 加 `*, user_id=None` 并把它记进 `calls`，`make_client` 同样 `with_auth(app, FakeUser(user_id=9))`；`test_chunks_endpoint_forwards_defaults_and_returns_chunk_shape` 那条的断言改成把 `user_id` 一并比进去：

```python
    assert db.calls == [{"user_id": 9, "query": "", "suffix": "", "parent_ids": [], "limit": 50}]
```

```bash
cd backend && python -m pytest tests/test_api_documents.py tests/test_chunk_search.py -q
```
预期：`29 passed`（20 + 9），0 failed。红得最可能的一处：`RaisingDeleteDocumentDB` 与 `ChunkDB` 两个子类没跟上父类新 kwarg，报的是 `TypeError: got an unexpected keyword argument 'user_id'`。

> **2026-10-07 修订（Task 4 实跑改判）**：`29` 数的是**函数**，不是 pytest 收的**用例**——两个文件里带 parametrize 的用例展开后实跑 **49 passed**。本计划一律以工具汇总行为准，凡"函数数×"式预期都按此改判。

- [ ] **Step 8: live 组 32 处调用点 + 真隔离判据**

`tests/test_live_database.py` 的改造是**机械的**，但要点在两处结构：

1. 加一个模块级夹具，探针文档一律挂它，**不挂 default 用户**：

```python
@pytest.fixture(scope="module")
def probe_user(db):
    """live 判据自己的账号：与 default@local 分开，隔离才测得出来。

    口令现造现丢（不进 .env、不打印），users 表没有基线计数，留着这一行无害。
    """
    from core.security import hash_password

    tag = f"live-user-{new_tag()}"
    return db.create_user(identifier=f"{tag}@local", identifier_type="email",
                          nickname="探针账号", password_hash=hash_password(f"p-{tag}"))
```

2. 32 处调用点逐个补 `user_id=probe_user.id`（`get_document` / `get_all_documents` / `search_parent_chunks` / `plan_chunk_deletion` / `delete_parent_chunk` / `save_document`）。**只有** `test_default_user_exists_and_owns_the_baseline_documents` 与基线那两条不参与——它们查的就是 default 的行。

> **2026-10-07 修订（Task 4 实跑改判）**：那个"32"是估的，`test_live_database.py` 里真正带归属的调用点是 **60 处**，另加本 Task 新增的 2 条判据。这个数只当"改全了没有"的完整性核对，不是判据本身——真正的门是 `pytest -q` 里任何一处漏传都当场 `TypeError`。

补上 Task 2 Step 6 暂缓的那条（**它的签名这时才存在**）：

```python
def test_new_document_carries_its_owner(db, probe_user):
    """写入侧归属 + 读侧过滤一次跑完：别人拿同一个 id 也查不到。"""
    tag = f"own-{new_tag()}"
    doc_id = db.save_document(filename=f"{tag}.txt", file_path="", content="x",
                              chunk_count=0, user_id=probe_user.id)
    try:
        assert db.get_document(doc_id, user_id=probe_user.id).id == doc_id
        other = db.get_document(doc_id, user_id=probe_user.id + 99999)
        assert other is None, "越权取到了别人的文档：WHERE 里那道 user_id 没生效"
        assert doc_id in [d.id for d in db.get_all_documents(user_id=probe_user.id)]
        assert db.get_all_documents(user_id=probe_user.id + 99999) == [] or all(
            d.id != doc_id for d in db.get_all_documents(user_id=probe_user.id + 99999))
    finally:
        db.delete_document(doc_id)


def test_parent_whitelist_drops_foreign_owners(db, probe_user):
    """owned_parent_ids 是 Task 5 那道 404 的底座，所以它必须在真库上先站住。

    两条对照查询（spec 7.1 报数口径）：自己的 id 查得到、别人的查不到——单看"空结果"
    分不清"过滤生效"和"根本没这条行"。
    """
    from sqlalchemy import text

    from core.migrations import DEFAULT_IDENTIFIER

    with probe(db, f"whitelist-{new_tag()}.txt", ["甲"]) as (doc_id, pids):
        assert db.owned_parent_ids(pids, user_id=probe_user.id) == pids
        assert db.owned_parent_ids(pids, user_id=probe_user.id + 99999) == []

    # 反证：default 用户名下的 parent_id 对探针账号必须不可见。
    # 拿 id 只能走 search_parent_chunks——ORM 行在方法返回时 session 已关，
    # 这时访问 doc.parent_chunks 会抛 DetachedInstanceError（懒加载需要活的 session）。
    with db.engine.connect() as conn:
        default_id = conn.execute(text(
            "SELECT id FROM users WHERE identifier = :i"),
            {"i": DEFAULT_IDENTIFIER}).fetchone()[0]
    theirs = [r.parent_id for r in db.search_parent_chunks(user_id=default_id, limit=200)]
    assert theirs, "default 用户名下取不到任何父块：反证没有输入，这条判据等于没跑"
    assert db.owned_parent_ids(theirs, user_id=probe_user.id) == []
```

> `probe(...)` 现在不是上下文管理器。Step 8 顺手把它改成 `@contextmanager`（`yield (doc_id, parent_ids)` + `finally: db.delete_document(doc_id)`），两条新判据都要用它，且现有 5 处调用点本来就在 `try/finally` 里手删——改完那 5 处也一并变干净。**这一处改造会让文件里现存的 `db.delete_document(...)` 清理行减少，属预期。**

> **2026-10-06 修订（计划代码自身有洞，Task 4 落地时已补）**：上面这段没写 `probe` 的新形参，而本 Task 的 `save_document` 要求 `user_id` keyword-only 无默认值——**计划正文给出的 `probe(db, ...)` 调用点因此直接 `TypeError`**（现存调用点实测 **7 处**，不是上面说的"5 处"；本 Task 后共 8 处）。裁定：`probe` 改成 `probe(db, filename, blocks, *, user_id)`（必填，不给默认值，与"忘了就炸"这条 Task 主张同形），调用点传 `probe_user.id` 或 default 用户 id 按各判据要查的对象定。

```bash
cd backend && python -m pytest -m live -q
```
预期：在原条数上 **+2**，0 failed。基线三条（`/api/health` 与 `test_chroma_data.py`）必须仍是 9 / 11 / 22。

> **2026-10-07 修订（上面这行的预期值按新基线改判）**：旧 9/11/22 作废，本轮的基线形状是**活文档 4 / 父块 4 / 子块 10**（`test_chroma_data.py` 已按 `PARENT_COUNT = 4` / `CHILD_COUNT = 10` 重钉，它才是那条常驻的自动入口）。`/api/health` 那一格在 Task 1–7 按纪律**没有服务在跑**，`curl` 会拿到 Vite/代理的 502 或连接失败，不许把它当"基线被伤了"的证据；要看 health 的实数请留到 Task 8 重启之后。`-m live` 的当轮实数是 **14 passed / 2 skipped / 211 deselected**（`test_live_stream.py:34/:64` 那两条无服务时 skip），Task 4 加完两条应当是 **16 passed / 2 skipped**，且 `0 failed`。

> **2026-10-07 二次修订（Task 4 实跑改判）**：上面那个 16 是在 **Task 3 之前**量的，而 Task 3 自己就新增了 2 条 live（`documents_claimed` / 向量补戳），基数已经变 16。Task 4 的实测判据是 **18 passed / 2 skipped / 230 deselected，0 failed**。

- [ ] **Step 9: 全量门 + 提交**

```bash
cd backend && python -m pytest -q
```
预期：Task 3 之后的条数 + 本 Task 的 8 条离线 + 2 条 live，**0 failed**。只抄汇总行。

```bash
cd D:/知识库平台-前后端分离 && git add backend/core/database.py backend/core/vector_store.py \
  backend/api/documents.py backend/tests/fakes.py backend/tests/test_api_documents.py \
  backend/tests/test_chunk_search.py backend/tests/test_ownership_isolation.py \
  backend/tests/test_live_database.py
git status --short
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(backend): documents 侧按用户归属——六方法带 user_id、向量补主人戳、四端点上登录门（阶段一 Task 4）"
```

### Task 5: `chat` 与 `history` 上登录门，问答入参过白名单

**Files:**
- Modify: `backend/api/chat.py`（两个端点加 `get_current_user` + `get_db`，新增 `_require_owned_parents`）
- Modify: `backend/api/history.py`（两个端点加 `get_current_user`）
- Modify: `backend/tests/fakes.py`（`FakeOwnedParentsDB`：问答测的"全都属于你"假库）
- Modify: `backend/tests/test_api_chat.py`、`backend/tests/test_api_history.py`（`make_client` 各加两格覆盖）
- Modify: `backend/tests/test_ownership_isolation.py`（401 参数化 4 → 8；新增问答越权两条）
- Modify: `backend/tests/test_live_stream.py`（两条真 HTTP 流式测在头里带一枚真令牌）
- Modify: `backend/deps.py`（**原清单漏了这一格**：Step 5 交接的 ② 要求把 `get_current_user` 拆成"先取令牌再查库"，Task 4 已把这条记为 out-of-scope、落点定在本 Task；对应地要删掉测试假库里那枚 `get_user_by_token` 绕行桩）

**Interfaces:**
- Consumes：`deps.get_current_user`（Task 2）、`DatabaseManager.owned_parent_ids`（Task 4）。
- Produces：`api/chat._require_owned_parents(db, parent_ids, user) -> list[str]`；8 个业务端点全部要求 Bearer 令牌；`POST /api/chat` 与 `POST /api/chat/stream` 对别人的 `parent_id` 回 **404**。

**这一 Task 要显式说清的一件事**：`chat` 和 `chat_stream` 现在**不依赖 `get_db`**（只依赖 `get_rag_system`）。加归属校验必然要多一个 db 依赖——这不是啰嗦，是"问答链自己不知道谁是主人"这个事实的必然结果。而 `RAGSystem` 的四个方法**一个都不改**（`chat_with_documents(question, parent_ids, session_id)` 保持原样），因为它的重接与 `chat_history.user_id` 属同一批工作量，全部归阶段二（spec 2.2 勘误）。**门开在端点上，链子还是那条链子。**

- [ ] **Step 1: 先扩失败判据（8 端点 401 + 问答越权）**

`backend/tests/test_ownership_isolation.py`：把 Task 4 那条参数化换成完整的八条清单（spec 3.2 那张表逐条抄）：

```python
BUSINESS_ENDPOINTS = [
    ("post", "/api/documents"),
    ("get", "/api/documents"),
    ("get", "/api/documents/chunks"),
    ("delete", "/api/documents/7/chunks/x_parent_0"),
    ("post", "/api/chat"),
    ("post", "/api/chat/stream"),
    ("get", "/api/history/some-session"),
    ("delete", "/api/history/some-session"),
]


@pytest.mark.parametrize("method,path", BUSINESS_ENDPOINTS,
                         ids=[f"{m}-{p}" for m, p in BUSINESS_ENDPOINTS])
def test_every_business_endpoint_rejects_a_missing_token(method, path):
    """八条一个不漏：这条参数化就是 spec 3.2 那张清单的自动化形态。

    漏一条门的表现是"未登录也能查别人的历史"，而它不会让任何一条现有测变红——
    所以这里必须按清单数，不能按"改了几个文件"数。
    """
    client, _ = make_isolation_client(gate=False)
    payload = {"session_id": "s1", "question": "q"} if method == "post" else None
    res = getattr(client, method)(path, json=payload)
    assert res.status_code == 401, f"{method.upper()} {path} 没上门"
    assert res.json() == {"detail": "未登录或登录已过期"}


def test_health_stays_open():
    """/api/health 是运维探针，spec 3.2 明写不上门。

    这条看着像"没测东西"，其实测的是"没把门多加到 health 上"——
    它是项目记忆与现有判据里那条基线计数（活文档 4 / 父块 4 / 子块 10，2026-10-07 重钉）唯一的自动入口。
    health 依赖 get_config/get_db/get_vector_store 三格，make_isolation_client 全部覆盖，
    所以这里能硬断言 200，而不是"只要不是 401 就行"。
    """
    client, _ = make_isolation_client(gate=False)
    assert client.get("/api/health").status_code == 200


def test_asking_with_a_foreign_parent_id_is_404():
    db = OwnerAwareDB()
    client, _ = make_isolation_client(db, user=FakeUser(user_id=INTRUDER))
    res = client.post("/api/chat", json={
        "session_id": "s1", "question": "q", "parent_ids": ["甲.txt_parent_0"]})
    assert res.status_code == 404
    assert res.json() == {"detail": "文档块不存在或已被删除"}


def test_stream_endpoint_refuses_a_foreign_parent_id_before_the_first_frame():
    """流式端点必须在 meta 帧**之前**拒：一旦发出 200，HTTP 语义就让位给流协议了。

    这条判据的形状（404 + JSON detail，而不是 error 帧）就是"检查放在 StreamingResponse
    构造之前"的唯一证据——放错位置照样"能跑"，只是没人能从状态码看出来。
    """
    db = OwnerAwareDB()
    client, _ = make_isolation_client(db, user=FakeUser(user_id=INTRUDER))
    res = client.post("/api/chat/stream", json={
        "session_id": "s1", "question": "q", "parent_ids": ["甲.txt_parent_0"]})
    assert res.status_code == 404
    assert res.json() == {"detail": "文档块不存在或已被删除"}
```

> **2026-10-06 修订（上面这段代码在 Task 5 执行期改了一处，属计划代码缺陷）**：八条清单里有**五条**根本不该走 `json=`——httpx 0.28.1 的 `Client.get` 与 `Client.delete` **都没有 `json` 形参**（`inspect.signature` 实测：`json` 只出现在 `post` / `put` / `patch` / `request` 上），所以 `getattr(client, method)(path, json=payload)` 对 3 条 GET + 2 条 DELETE 共 **5 条臂**当场 `TypeError`。落地写法：**`client.request(method.upper(), path, json=payload)`**（`payload=None` 时 httpx 不带体，语义不变）。这不是风格差异，是照抄就跑不起来。**连带后果**：Step 2 那次"跑红"的头一批红因里，这 5 条是 `TypeError` 而不是 `200 == 401`，报数时要把两类红因分开写清，别把 `TypeError` 冒充"门没上"的证据。

> Task 4 里那个 `make_client` 名字在本 Task 之后要同时服务 documents 与 chat/history 两组路径，改成 **`make_isolation_client(db=None, user=FakeUser(user_id=OWNER), rag=None, gate=True)`**：`db` 缺省时给一个 `OwnerAwareDB()`，`rag` 缺省时给 `FakeRAG()`，并多覆盖 `get_rag_system` 与 `get_config` 两格（后者是给 `test_health_stays_open` 用的：`FakeConfig` 里那个 `CHROMA_PERSIST_DIR` 足够 health 拼出响应）。改名与补格都发生在 **Step 5**——Step 1 先按新名字写判据，这样红因始终是"东西不存在"，而不是"测试写了一半"。

> **2026-10-06 修订（开工前核过 `/api/health` 的真实取数）**：health 那一格读的是 `db.count_documents()` 与 `vector_store.collection_counts()`（`main.py:85-96`），**不是** `get_all_documents(user_id=...)`——`count_documents` 在 Task 4 里被有意留在"不加归属"那一侧。所以 `test_health_stays_open` 落地时，`OwnerAwareDB` **必须补一个 `count_documents()`**（返回 `len(self.rows)` 就够），否则这条判据红在 `AttributeError` 而不是红在"health 上门了"。`FakeVectorStore` 那边 `collection_counts` 已经有了，不用新加。

- [ ] **Step 2: 跑红**

```bash
cd backend && python -m pytest tests/test_ownership_isolation.py -q
```
预期：新增的 chat/history 四条 401 全红（那四个端点还没上门），两条越权红在"根本没 404，直接 200/500"。

- [ ] **Step 3: `api/chat.py` 上门 + 白名单**

```python
from deps import get_current_user, get_db, get_rag_system


def _require_owned_parents(db, parent_ids, user) -> list[str]:
    """问答允许池过白名单：别人的 parent_id 与不存在的 parent_id 一样，都是 404。

    放在端点而不是 RAGSystem：链子只管问答，"能不能问这几个块"是门口的事（spec 3.4 同款分工）。
    也比在链子里查更便宜——越权请求一次都不该打到 embedding 与 LLM 上。
    """
    if not parent_ids:
        return []
    owned = db.owned_parent_ids(parent_ids, user_id=user.id)
    if len(owned) != len(list(dict.fromkeys(parent_ids))):
        raise HTTPException(status_code=404, detail="文档块不存在或已被删除")
    return owned
```

两个端点各加两个依赖、并在最前面调它：

```python
@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest, db=Depends(get_db), rag=Depends(get_rag_system),
         user=Depends(get_current_user)):
    mode = mode_of(payload.parent_ids)
    if mode == "rag":
        _require_owned_parents(db, payload.parent_ids, user)   # ← 在碰 rag 之前
        ...


@router.post("/stream")
def chat_stream(payload: ChatRequest, db=Depends(get_db), rag=Depends(get_rag_system),
                user=Depends(get_current_user)):
    mode = mode_of(payload.parent_ids)
    if mode == "rag":
        _require_owned_parents(db, payload.parent_ids, user)   # ← 必须在 frames() 之外
    events = ...
```

`_require_owned_parents` 的返回值（`owned`）这一期**不往链子里传**——`RAGSystem` 的方法签名不变，它拿到的还是原始 `parent_ids`。这不是遗漏：校验已经发生，收窄入参集合只是少一次无谓比较，而那件事和阶段二的 `chat_history.user_id` 一起改才划算。**把这个不对称写进注释**，否则下一个读代码的人会以为白名单写了两遍。

- [ ] **Step 4: `api/history.py` 上门，但不加 user 过滤（并写清为什么）**

```python
@router.get("/{session_id}", response_model=list[HistoryMessage])
def get_history(session_id: str, limit: int = Query(50, ge=1, le=200),
                db=Depends(get_db), user=Depends(get_current_user)):
    """登录门有，user 过滤没有——阶段一的对话隔离靠两件事：
    ① session_id 由后端 uuid4() 铸造（Task 2），外人猜不到；
    ② 这四个端点要求 Bearer 令牌。
    真正的 chat_history.user_id 列与读写过滤在阶段二（spec 2.2 勘误：它和 RAGSystem
    四个方法、34 处调用点是同一批工作量，分两轮改同一个文件只会两次踩同一个坑）。
    """
```

`DELETE /api/history/{session_id}` 同样只加门。**这条注释是本轮最容易被人"顺手补全"的地方**——留着它是为了让阶段二的边界可见。

- [ ] **Step 5: 补齐 fakes 与两个既有测的 make_client**

`backend/tests/fakes.py` 追加：

```python
class FakeOwnedParentsDB:
    """问答测的最小假库：递给它的 parent_id 一律算"属于你"。

    存在的理由是 chat 端点多了一个 db 依赖——那 29 条测不该为此各自造库，
    而越权那条路径由 test_ownership_isolation.py 用会过滤的假库专门钉。
    """

    def __init__(self):
        self.calls = []

    def owned_parent_ids(self, parent_ids, *, user_id):
        self.calls.append((tuple(parent_ids), user_id))
        return list(dict.fromkeys(parent_ids))

    def get_chat_history(self, session_id, limit=10):
        return []

    def delete_chat_history(self, session_id):
        return 0
```

`tests/test_api_chat.py` 的 `make_client`：

```python
from deps import get_current_user, get_db, get_rag_system
from fakes import FakeOwnedParentsDB, FakeRAG, FakeUser, with_auth


def make_client(rag, db=None, user=None):
    app = create_app()
    app.dependency_overrides[get_rag_system] = lambda: rag
    # chat 端点现在真的会用到 db（越权白名单），漏这一格那 29 条会一起 500：
    # app.state.db 在测试里根本不存在
    app.dependency_overrides[get_db] = lambda: db or FakeOwnedParentsDB()
    with_auth(app, user or FakeUser())
    return TestClient(app)
```

`tests/test_api_history.py` 的 `make_client` 同样加 `with_auth(app, user or FakeUser())`（`HistoryDB` 已覆盖 `get_db`，不用新格子）。

> **2026-10-06 修订（Task 4 收口时交接到本 Task，两条都是硬要求）**
> ① 上面两处 `user or FakeUser()` 的回落默认是 **`user_id=1`**，而 Task 4 的评审发现 F12 刚证明"假用户的 id 与某处硬编码的 1 相同"会让**端点漏传归属**变得测不出来（`test_ownership_isolation.py` 已把 `OWNER`/`INTRUDER` 抬到 41/42）。所以本 Task 的两套 `make_client` 里，凡是要判"白名单/登录门确实拿到 `user.id`"的测，**必须显式传一个不等于 1、也不等于 41/42/9/77 的 user_id**（建议 chat 用 43、history 用 44），别依赖 `FakeUser()` 的默认值。
> ② `deps.py:44` 现在是 `db.get_user_by_token(hash_token(bearer_token(request)))`——CPython 先解析 `LOAD_METHOD` 再算实参，所以**假库少一个方法就会把"没令牌"变成 500 而不是 401**。本 Task 要把 chat/history 那四条并进 `test_documents_endpoints_reject_a_missing_token`，正是靠这条 401 判据吃饭。裁定：**在本 Task 内**把它拆成两行（先 `token = bearer_token(request)`，空令牌当场 `AuthError`，再查库），并**顺手删掉测试假库里那枚为绕过该问题而加的 `get_user_by_token`**——这样 401 由构造保证，不再依赖一次性变异证明。Task 4 的复评已把这条记为 out-of-scope，落点就是这里。

同文件补一条断言，钉住"白名单确实被调了"：

```python
def test_rag_question_passes_the_parent_pool_through_the_whitelist():
    db = FakeOwnedParentsDB()
    client = make_client(FakeRAG(), db=db, user=FakeUser(user_id=5))
    client.post("/api/chat", json={"session_id": "s1", "question": "q",
                                   "parent_ids": ["a.txt_parent_0"]})
    assert db.calls == [(("a.txt_parent_0",), 5)]
```

```bash
cd backend && python -m pytest tests/test_api_chat.py tests/test_api_history.py \
  tests/test_ownership_isolation.py -q
```
预期：三个文件分别约 `30`（`test_api_chat.py` 29 + 本 Step 新那条白名单断言）、`14`（`test_api_history.py`）、`14`（`test_ownership_isolation.py`：documents 3 + 8 条 401 参数化 + health 1 + 问答越权 2）。**只抄工具汇总行**，两处红因先看：`AttributeError: ... no attribute 'db'` 说明漏了 `get_db` 那格；`cannot import name 'with_auth'` 说明 fakes 没落盘。

- [ ] **Step 6: live 流式测带真令牌**

`backend/tests/test_live_stream.py` 的两条真 HTTP 测（`test_client_disconnect_mid_stream_leaves_no_rows`、`test_full_stream_persists_one_turn_and_frames_are_ordered`）在 `server` 夹具之后统一取一枚令牌。加一个模块级 helper：

```python
def login_token():
    """真服务上登录一个真账号，拿一枚真令牌。

    口令只从 Config.DEFAULT_USER_PASSWORD 读，**绝不打印**（项目记忆：`.env` 的键值
    不入日志、不进断言消息）。默认用户不可登录时这条 helper 直接 pytest.skip——
    那属于"运营者没设口令"的环境差异，不是代码坏了。
    """
    from config.config import Config
    from core.migrations import DEFAULT_IDENTIFIER

    if not Config.DEFAULT_USER_PASSWORD:
        pytest.skip("DEFAULT_USER_PASSWORD 未设置：默认用户只作归属锚点，无法登录")
    res = httpx.post(f"{BASE}/api/auth/login",
                     json={"identifier": DEFAULT_IDENTIFIER,
                           "password": Config.DEFAULT_USER_PASSWORD}, timeout=30)
    res.raise_for_status()
    return res.json()["token"]
```

两条测里所有对业务端点的请求补 `headers={"Authorization": f"Bearer {token}"}`（`client.stream(...)`、`client.get(f"{BASE}/api/history/{sid}")`、`httpx.delete(...)` 三处都要，共 6 处调用点）；**`httpx.get(f"{BASE}/api/health")` 那处不加**（它是"health 没上门"的活证据）。中文载荷仍走文件，不改成 shell 参数（cp936）。

```bash
cd backend && python -m pytest -m live -q
```
预期：`+0` 条（本 Task 只改现有两条 live 测，不新增），0 failed。这两条要真打到 LLM，耗时长属正常。

- [ ] **Step 7: 全量门 + 提交**

```bash
cd backend && python -m pytest -q
```
预期：在 Task 4 之后那条汇总数上 **+8**（401 参数化 4→8、`test_health_stays_open`、问答越权 2、白名单断言 1）。**别抄这里的加法式，只抄汇总行**；硬性要求仍是 0 failed、0 skipped（`login_token` 那条 skip 只在 `DEFAULT_USER_PASSWORD` 为空时出现，而 Step 6 之前必须先把 `.env` 那行设上）。

> **2026-10-06 修订（本 Task 开工前按 Global Constraints 的绿灯口径改判）**：上面那句"0 skipped"是 **Task 8 的口径**，在 Task 5 不可达——Task 1–7 期间按纪律 **:8000 上没有服务**（embedding 按进程加载，本机同时只准一份 uvicorn），而 Step 6 改的正是 `test_live_stream.py:34/:64` 这两条，它们由该文件的 `server` 夹具（`:22`）在无服务时 **skip**。所以本 Task 的正确绿灯是：**`0 failed` 硬性 + 恰好 2 条 skip，且必须是那两条**；`pytest -q` 期望 **256 passed / 2 skipped / 2 deselected**（248 + 8）。`login_token()` 引入的是**第三条** skip 的可能性（`DEFAULT_USER_PASSWORD` 为空），本机 `.env` 已设值（`grep -c "^DEFAULT_USER_PASSWORD=." = 1`），出现第三条就是回归，要当场查。Step 6 那两条真流式判据的实跑验证顺延到 Task 8。

```bash
cd D:/知识库平台-前后端分离 && git add backend/api/chat.py backend/api/history.py \
  backend/tests/fakes.py backend/tests/test_api_chat.py backend/tests/test_api_history.py \
  backend/tests/test_ownership_isolation.py backend/tests/test_live_stream.py
git status --short
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(backend): chat/history 上登录门，问答允许池过归属白名单（阶段一 Task 5）"
```

**后端到这里就齐了**：Task 1-5 完成后，`curl` 层面能验的东西全部可验（Task 8 的双端门禁会一次性走完）。前端三段（Task 6/7）只是把这套契约接到界面上。

### Task 6: 令牌的三条出口 + `useAuth`（界面还不动，先把"我是谁"送出去）

**Files:**
- Modify: `frontend/src/api/client.js`（模块级 `setAuthToken` + `authHeaders`，`request`/`postStream` 两处吃它；`request` 补 204 空响应体）
- Modify: `frontend/src/api/documents.js`（`uploadDocument` 的 XHR 补 `setRequestHeader`）
- Create: `frontend/src/api/auth.js`、`frontend/src/composables/useAuth.js`
- Create: `frontend/tests/useAuth.test.js`
- Modify: `frontend/tests/client.test.js`（Authorization 三条出口各一条 + 204 一条）、`frontend/tests/documents-api.test.js`（XHR 那条）
- Create: `frontend/tests/api-auth.test.js` — **2026-10-07 修订新增**（Task 6 评审指出 `api/auth.js` 零直接覆盖：`useAuth.test.js` 把整个模块 mock 掉了，所以"昵称留空就连键都不发"这条**承重**行为没人钉。它承重是因为 `backend/schemas/auth.py:37` 给 `nickname` 设了 `min_length=1`，前端多发一个 `''` 就是建号 422。两条就够：留空时请求体里**没有** `nickname` 键、填了就原样送到 `identifier_type` 这套 snake_case 契约里。）

**Interfaces:**
- Consumes：Task 2 的四个 `/api/auth/*` 端点（出参 `{token, user, session_id}` / `{user}`）。
- Produces：
  - `client.js`：`setAuthToken(token: string)`、`authHeaders(extra?) -> object`
  - `api/auth.js`：`register({identifierType, identifier, password, nickname})`、`login({identifier, password})`、`logout()`、`getMe()`
  - `composables/useAuth.js`：模块级 `user` ref + `authError` ref + `isLoggedIn` computed + `bootstrap()/signUp()/signIn()/signOut()/clearAuth()`
  - localStorage 新增键 `auth_token`（与既有 `session_id`、`selected_parent_ids` 并列，spec 5.3）

**为什么先做这一 Task 再做界面**：令牌注入是全项目**最容易漏且最难查**的一处——三条出口只有一条有现成的 headers 展开位（spec 5.6），漏掉的表征是"登录成功了，文档却传不上去"，看上去像后端坏了。这一 Task 用 vitest 把三条出口一次钉死，Task 7 的界面才能站在可信的网络层上写。

- [ ] **Step 1: 写失败判据（三条出口 + 204）**

`frontend/tests/client.test.js` 末尾追加一组：

```js
describe('Authorization 注入：三条出口一条都不能漏', () => {
  // 漏一条的表征是"登录了但那个功能 401"，而 401 在前端只回一句"未登录或登录已过期"，
  // 看的人第一反应是令牌过期了——真正的原因却是某个出口忘了带头。
  afterEach(() => setAuthToken(''))

  it('request 带上 Bearer 头', async () => {
    const calls = stubFetchWithCalls(jsonResponse({ ok: true }))
    setAuthToken('tok-abc')
    await request('/api/documents')
    expect(calls[0][1].headers.Authorization).toBe('Bearer tok-abc')
  })

  it('postStream 带上 Bearer 头（这里的 headers 原先是硬编码的）', async () => {
    const calls = []
    const { res } = streamResponse([frame('done', {})])
    global.fetch = vi.fn(async (path, opts) => { calls.push([path, opts]); return res })
    setAuthToken('tok-stream')
    await postStream('/api/chat/stream', {}, () => {})
    expect(calls[0][1].headers.Authorization).toBe('Bearer tok-stream')
  })

  it('没有令牌时一个 Authorization 头都不发', async () => {
    const calls = stubFetchWithCalls(jsonResponse({ ok: true }))
    setAuthToken('')
    await request('/api/documents')
    expect('Authorization' in calls[0][1].headers).toBe(false)
  })

  it('204 无响应体不走进 res.json()', async () => {
    // 登出端点回 204：空文本过 JSON.parse 会抛 SyntaxError，
    // 于是"登出成功"在界面上变成一条红色报错——这是这条判据唯一要防的事。
    global.fetch = vi.fn(async () => ({
      ok: true, status: 204, headers: { get: () => null },
      text: async () => '', json: async () => { throw new SyntaxError('Unexpected end of input') },
    }))
    await expect(request('/api/auth/logout', { method: 'POST' })).resolves.toBeNull()
  })
})
```

同文件顶部补 `setAuthToken` 的导入，并加一个把 fetch 调用记下来的小助手（现有 `stubFetch` 只换实现、不留参数）。**两处导入要一起补**：`client.test.js` 现有的 vitest 行是 `{ describe, expect, it, vi }`，没有 `afterEach`；`documents-api.test.js` 顶部要加 `import { setAuthToken } from '../src/api/client.js'` 与把 `uploadDocument` 并进它已有的 `../src/api/documents.js` 导入。

```js
import { afterEach, describe, expect, it, vi } from 'vitest'

import { detailFromText, postStream, request, setAuthToken } from '../src/api/client.js'

function stubFetchWithCalls(r) {
  const res = r && r.res !== undefined ? r.res : r
  const calls = []
  global.fetch = vi.fn(async (path, opts) => { calls.push([path, opts]); return res })
  return calls
}
```

`frontend/tests/documents-api.test.js` 追加一条（XHR 在 jsdom 里可造，桩件只需 `open/setRequestHeader/send` 三件）：

```js
it('上传用 XHR 也带上 Bearer 头——它是全项目唯一不走 client.js 的出口', async () => {
  const headers = {}
  global.XMLHttpRequest = class {
    constructor() { this.upload = {} }
    open() {}
    setRequestHeader(k, v) { headers[k] = v }
    send() {
      this.status = 201
      this.responseText = JSON.stringify({ id: 1, filename: 'a.txt', chunk_count: 1,
                                           created_at: '2026-10-06T12:00:00' })
      this.onload()
    }
  }
  setAuthToken('tok-xhr')
  await uploadDocument(new File(['x'], 'a.txt'))
  expect(headers.Authorization).toBe('Bearer tok-xhr')
})
```

- [ ] **Step 2: 跑红**

```bash
cd frontend && npm test
```
预期：新加的那组红在 `setAuthToken is not a function`（还没导出）。**这一步同时会暴露 `request` 里 `res.json()` 对 204 抛错**——那条判据先记着，Step 3 一起修。

- [ ] **Step 3: `client.js` 落模块级令牌与两处注入**

文件顶部（`detailFromText` 之前）加：

```js
// 令牌是全项目唯一的"我是谁"证据，而出口有三条（request / postStream / 上传的 XHR）。
// 做成模块级变量而不是让每个调用方自己传：传漏一次的表征是一整片 401，
// 而 401 在前端只有一句"未登录或登录已过期"，看的人只会去怀疑令牌过期了。
let authToken = ''

export function setAuthToken(token) {
  authToken = token || ''
}

export function authHeaders(extra = {}) {
  // 没令牌时一个键都不加：加了 `Authorization: Bearer ` 空值反而会让后端把坏格式判成缺凭证，
  // 两种成因共用一句文案是设计（spec 3.5），但请求本身没必要长得像攻击载荷。
  return authToken ? { Authorization: `Bearer ${authToken}`, ...extra } : { ...extra }
}
```

`request` 的 headers 那段改成：

```js
      headers: authHeaders({
        Accept: 'application/json',
        ...(isJson ? { 'Content-Type': 'application/json' } : {}),
        ...headers,
      }),
```

`postStream` 的硬编码 headers 改成：

```js
      headers: authHeaders({ 'Content-Type': 'application/json', Accept: 'text/event-stream' }),
```

`request` 的成功出口加 204 那条（放在 `if (!res.ok)` 之后、`return res.json()` 之前）：

```js
  // 204 No Content 没有响应体：res.json() 会在空文本上抛 SyntaxError，
  // 把"操作成功"变成一条报错。登出、后面的删档类端点都走这一格。
  if (res.status === 204) return null
```

`documents.js` 的 XHR 在 `xhr.open(...)` 之后补一行（**位置在 `send()` 之前，`open()` 之后**——`setRequestHeader` 在 open 之前调用会被浏览器忽略）：

```js
import { authHeaders, detailFromText, request } from './client.js'
...
    xhr.open('POST', '/api/documents')
    const auth = authHeaders()
    if (auth.Authorization) xhr.setRequestHeader('Authorization', auth.Authorization)
```

- [ ] **Step 4: 写 `api/auth.js`**

```js
// 四个认证端点的薄封装。字段名在这层从后端的 snake_case 翻成前端的 camelCase：
// 界面上 `identifierType` 读起来顺，而契约的真相（identifier_type）只留在这里一行。
import { request } from './client.js'

export function register({ identifierType, identifier, password, nickname }) {
  const body = { identifier_type: identifierType, identifier, password }
  // 昵称留空时连键都不发：后端的默认昵称靠 identifier 推（邮箱取 @ 前、手机取后四位），
  // 前端多发一个 null 就等于替后端决定了"不要默认值"。
  if (nickname) body.nickname = nickname
  return request('/api/auth/register', { method: 'POST', body })
}

export function login({ identifier, password }) {
  return request('/api/auth/login', { method: 'POST', body: { identifier, password } })
}

export function logout() {
  return request('/api/auth/logout', { method: 'POST' })
}

export function getMe() {
  return request('/api/auth/me')
}
```

- [ ] **Step 5: 写 `composables/useAuth.js`**

```js
import { computed, ref } from 'vue'

import { getMe, login as apiLogin, logout as apiLogout, register as apiRegister } from '../api/auth.js'
import { setAuthToken } from '../api/client.js'

const TOKEN_KEY = 'auth_token'
// 令牌原文是 secrets.token_urlsafe(32)，长度恒为 43；下限收到 32 只为挡掉
// DevTools 里手敲的 "1"、上个版本残留的 UUID 这类坏值（同 useSession 的 UUID_RE 口径）。
const TOKEN_RE = /^[A-Za-z0-9_-]{32,}$/

// 状态放模块级而不是函数内：App.vue、AuthPanel.vue 与 Task 7 的 .user-rail 都要读它，
// 而这个项目不引 Pinia（spec 5.1）。函数内各造 ref 的话，退出只清掉一份副本。
const user = ref(null)
const authError = ref('')
const authBusy = ref(false)

function readToken() {
  const raw = localStorage.getItem(TOKEN_KEY)
  return raw && TOKEN_RE.test(raw) ? raw : ''
}

function applySession(token, nextUser) {
  localStorage.setItem(TOKEN_KEY, token)
  setAuthToken(token)
  user.value = nextUser
  authError.value = ''
}

export function useAuth() {
  const isLoggedIn = computed(() => user.value !== null)

  async function bootstrap() {
    // 启动流程的第一拍（spec 5.2）：手上没令牌就一个请求都不发。
    // 返回真表示"确认已登录"，App.vue 只有在这个前提下才去跑 refresh/hydrate/restore。
    const token = readToken()
    if (!token) {
      setAuthToken('')
      return false
    }
    setAuthToken(token)
    try {
      const body = await getMe()
      user.value = body.user
      return true
    } catch {
      // 401、网络失败、代理宕机(502) 都走这里：清掉坏票静默落回登录页。
      // 不弹横幅——"你上次登录的票过期了"对用户没有可行动信息，只会让人以为服务坏了。
      clearAuth()
      return false
    }
  }

  async function signUp(payload) {
    authBusy.value = true
    try {
      const body = await apiRegister(payload)
      applySession(body.token, body.user)
      return body.session_id   // App.vue 拿它覆盖 localStorage 的 session_id（spec 5.3）
    } finally {
      authBusy.value = false
    }
  }

  async function signIn(payload) {
    authBusy.value = true
    try {
      const body = await apiLogin(payload)
      applySession(body.token, body.user)
      return body.session_id
    } finally {
      authBusy.value = false
    }
  }

  async function signOut() {
    try {
      await apiLogout()   // 204：request 那层的空响应体处理让它回 null，不是报错
    } finally {
      // 后端删不掉也算本地退出：令牌可能已经过期、服务可能正在重启，
      // 而这些都不该成为"我点了退出却还留在这个账号里"的理由。
      clearAuth()
    }
  }

  function clearAuth() {
    localStorage.removeItem(TOKEN_KEY)
    setAuthToken('')
    user.value = null
  }

  return { user, authError, authBusy, isLoggedIn, bootstrap, signUp, signIn, signOut, clearAuth }
}
```

> 三个返回值要分清：`user`/`authError`/`authBusy` 是**模块级**的同一个对象（组件之间必须同步），`bootstrap/signUp/...` 是无状态的方法。这是"没有 Pinia 的手工单例"，也是本仓既有 `useChunkSelection` 的做法的反面——那个 composable 里 `selectedChunks` 是函数内的 ref，因为它只被 App.vue 一处持有；这里三处要读，所以必须上移到模块作用域。**把这个区别写进注释，否则下一个人会照着 `useChunkSelection` 抄回函数内。**

> **2026-10-07 修订（Task 6 执行期发现：上面这段 `signOut` 与本 Step 之外那条测相互矛盾，裁定改这段代码，不是改测）**
> 上面写的是 `try { await apiLogout() } finally { clearAuth() }`——`finally` 只保证"清得掉"，**不保证"不上抛"**：后端一失败，`signOut()` 就把异常原样抛给调用方。而 Step 6 那条测的标题是"**后端登出失败也完成本地退出**"、正文是一句裸的 `await signOut()`，照上面这段写它**不可能绿**。实施者选择改测（`await expect(signOut()).rejects.toThrow('HTTP 502')`）而不是改这里，等于把一个真缺陷锁进了判据。裁定：**`signOut` 必须自己吃掉后端的失败**，三条理由都核过：
> ① spec（`docs/superpowers/specs/2026-10-06-user-auth-isolation-design.md:235`）明写"登出 → `auth_token` 与 `session_id` **一起清**"，而 Task 7 的 `handleSignOut` 是在 `await signOut()` **之后**才 `clearSession()`、才清 `documents`/`queue`/`messages`/`clearSelection()`。`signOut` 一抛，后面全部跳过；而 `v-if` 因为 `finally` 跑过照样翻回登录页——**没人会察觉**。后果是下一个在这台机器上登录的人，在 `enterWorkspace` 覆盖之前会瞥见上一个账号的文件名与对话，正是本阶段要关的那类跨用户残留。
> ② 登出时 401 是**常见路径**不是边角（令牌早过期的人点退出），502 是 uvicorn 重启时的常态（项目记忆：Vite 代理上游死了回 502 空响应体，不是网络失败）。
> ③ 本仓所有会改状态的 composable 动作都不上抛——`useChat.js:52/121/148` 一律把错误折进 `error.value` 再回布尔；`signOut` 不能是唯一的例外。
> "会抛"这个契约只属于 `signIn/signUp`，因为它们有 `authError` 这条文案出口；登出没有要渲染的消息。**落地形状**：在 `finally` 之前补一个空的 `catch`（吃掉即可，注释写清"后端删不掉令牌也算本地退出"），`clearAuth()` 仍留在 `finally`；Step 6 那条测**改回裸的** `await signOut()`，本地退出的两条断言就是它的牙。
> **同批另外两刀（都在本 Task 内，都很小）**：④ `bootstrap()` 的"没令牌"分支现在只 `setAuthToken('')`，既不清模块级 `user`、也不删 localStorage 里那枚形状不合格的残留值 → 让它直接走 `clearAuth()` 再 `return false`（七条测全绿），并把 Step 6"坏形状的本地令牌按没有处理"那条补一句 `expect(localStorage.getItem('auth_token')).toBe(null)`；⑤ `documents-api.test.js` 末尾那条 XHR 测留着 `authToken='tok-xhr'` 与被替换的 `global.XMLHttpRequest` 且**没有拆桩**——今天只因为它排在最后才无害，补 `setAuthToken('')` 与 `delete global.XMLHttpRequest` 收口。

- [ ] **Step 6: 写 `tests/useAuth.test.js`**

```js
// useAuth 的四条纪律：坏令牌构造不可达、bootstrap 只在真登录时放行、
// 退出无论后端回什么都算本地退出、拿到新会话就把令牌同时写进 localStorage 与网络层。
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/api/auth.js', () => ({
  register: vi.fn(), login: vi.fn(), logout: vi.fn(), getMe: vi.fn(),
}))

import { getMe, login, logout, register } from '../src/api/auth.js'
import { useAuth } from '../src/composables/useAuth.js'

const USER = { id: 3, identifier: 'a@b.com', identifier_type: 'email', nickname: '小明', avatar: 'auto' }

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
})

describe('useAuth', () => {
  it('没有令牌时 bootstrap 不发任何请求，也就不会打出一串 401 横幅', async () => {
    const { bootstrap } = useAuth()
    await expect(bootstrap()).resolves.toBe(false)
    expect(getMe).not.toHaveBeenCalled()
  })

  it('坏形状的本地令牌按没有处理（DevTools 里手敲的值不可达）', async () => {
    localStorage.setItem('auth_token', 'not-a-token')
    const { bootstrap } = useAuth()
    await expect(bootstrap()).resolves.toBe(false)
    expect(getMe).not.toHaveBeenCalled()
  })

  it('登录写入令牌、置好用户，并把后端铸造的 session_id 交回调用方', async () => {
    login.mockResolvedValue({ token: 'x'.repeat(43), user: USER, session_id: 'sid-from-server' })
    const { signIn, user, isLoggedIn } = useAuth()
    await expect(signIn({ identifier: 'a@b.com', password: 'hunter2-pass' }))
      .resolves.toBe('sid-from-server')
    expect(user.value).toEqual(USER)
    expect(isLoggedIn.value).toBe(true)
    expect(localStorage.getItem('auth_token')).toBe('x'.repeat(43))
  })

  it('bootstrap 拿到 200 才算登录成功', async () => {
    localStorage.setItem('auth_token', 'y'.repeat(43))
    getMe.mockResolvedValue({ user: USER })
    const { bootstrap, isLoggedIn } = useAuth()
    await expect(bootstrap()).resolves.toBe(true)
    expect(isLoggedIn.value).toBe(true)
  })

  it('bootstrap 失败静默清凭证：令牌过期不该变成界面上的一句红字', async () => {
    localStorage.setItem('auth_token', 'z'.repeat(43))
    getMe.mockRejectedValue(new Error('未登录或登录已过期'))
    const { bootstrap, isLoggedIn } = useAuth()
    await expect(bootstrap()).resolves.toBe(false)
    expect(isLoggedIn.value).toBe(false)
    expect(localStorage.getItem('auth_token')).toBe(null)
  })

  it('后端登出失败也完成本地退出（登出不是为了"服务端删了行"，是为了这台机器不再是你）', async () => {
    localStorage.setItem('auth_token', 'w'.repeat(43))
    getMe.mockResolvedValue({ user: USER })
    logout.mockRejectedValue(new Error('HTTP 502'))
    const { bootstrap, signOut, isLoggedIn } = useAuth()
    await bootstrap()
    await signOut()
    expect(isLoggedIn.value).toBe(false)
    expect(localStorage.getItem('auth_token')).toBe(null)
  })

  it('注册与登录都覆盖 localStorage 的令牌，不追加、不合并', async () => {
    register.mockResolvedValue({ token: 'r'.repeat(43), user: USER, session_id: 's1' })
    login.mockResolvedValue({ token: 'l'.repeat(43), user: USER, session_id: 's2' })
    const { signUp, signIn } = useAuth()
    await signUp({ identifierType: 'email', identifier: 'a@b.com', password: 'hunter2-pass' })
    expect(localStorage.getItem('auth_token')).toBe('r'.repeat(43))
    await signIn({ identifier: 'a@b.com', password: 'hunter2-pass' })
    expect(localStorage.getItem('auth_token')).toBe('l'.repeat(43))
  })
})
```

> **模块级状态在测试里的代价**：这七条测共享同一个 `user` ref，所以顺序敏感（前一条登录、后一条就得先 `bootstrap` 或 `clearAuth`）。这是"不引 Pinia"换来的复杂度，spec 5.1 已认。若某条测单独跑绿、全量跑红，先查上一条有没有把 `user` 留在登录态——**不要用 `vi.resetModules()` 逃避**，那会让"三处读同一个对象"这件事彻底测不到。

- [ ] **Step 7: 全绿 + 构建 + 提交**

```bash
cd frontend && npm test
cd frontend && npm run build
```
预期：`npm test` 从基线 **84 passed / 7 文件** 涨到约 **96 passed / 8 文件**（`client.test.js` +4、`documents-api.test.js` +1、`useAuth.test.js` +7，共 +12；以汇总行为准）。`npm run build` exit 0。**0 failed 是硬要求。**

> **2026-10-07 修订（Task 6 修正轮 1 的口径，覆盖上面那行的加法式）**
> ① **门禁基数变了**：多了 `api-auth.test.js` 那 2 条之后是 **98 passed / 9 文件**，`git add` 清单要**多这一格**（`frontend/tests/api-auth.test.js`）。修正轮若再加条数，仍以当轮汇总行为准，别抄这里的加法式。
> ② **评审的 Important（采纳）：本 Task 重写的那两行 headers，只钉了一半。** 现有判据只断 `Authorization`——把 `client.js` 里的 `Accept: 'application/json'` 或条件式的 `'Content-Type': 'application/json'` 整行删掉（或把 `request` 写成裸 `authHeaders()`），**全套 96 条照样绿**，因为此前没有任何一条测读过 `opts.headers` 的其它键。丢 `Content-Type` 的真实后果是 `POST /api/auth/login` 撞 422，症状正好是"登录了但登录用不了"——本 Task 存在的理由就是这个症状不该出现。补两行断言即可（放本 Task 新加的那组里，不新建测）：带体的请求断 `headers['Content-Type'] === 'application/json'`，`postStream` 那条断 `headers['Accept'] === 'text/event-stream'`。
> ③ 变异自证要跟着扩一条：临时删掉 `request` 里的 `'Content-Type'` 那半行，新断言必须当场红。

```bash
cd D:/知识库平台-前后端分离 && git add frontend/src/api/client.js frontend/src/api/documents.js \
  frontend/src/api/auth.js frontend/src/composables/useAuth.js \
  frontend/tests/client.test.js frontend/tests/documents-api.test.js frontend/tests/useAuth.test.js
git status --short
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(frontend): 令牌注入三条网络出口 + useAuth 与 api/auth（阶段一 Task 6）"
```

**这一步之后后端与网络层都齐了，界面上还看不出任何变化**——登录页与左下角那块是 Task 7。

### Task 7: 登录页与左下角的用户栏（界面上终于看得出来"我是谁"）

**Files:**
- Modify: `frontend/src/composables/useSession.js`（`sessionId` 上移到模块作用域，新增 `setSession` / `clearSession`）
- Create: `frontend/src/components/AuthPanel.vue`、`frontend/tests/AuthPanel.test.js`、`frontend/tests/useSession.test.js`
- Create: `frontend/tests/StatusBar.test.js`
- Create: `frontend/tests/App.auth-gate.test.js`（**2026-10-07 修订补**：Step 7 的整屏门禁 / 请求顺序 / 登出清键原本零自动化覆盖，判据设计见 Step 7 之后的修订块 ①）
- Modify: `frontend/src/components/StatusBar.vue`（`.session-chip` 与 `sessionId` prop 一起删）
- Modify: `frontend/src/App.vue`（整屏 `v-if` 门禁、`.session-debug` → `.user-rail`、登录/登出编排）
- Modify: `frontend/src/styles/layout.css`（新增 `.auth-*` 与 `.user-rail` 家族、删三条死规则、末尾补一个 ≤768 分支）

**Interfaces:**
- Consumes：Task 6 的 `useAuth()` → `{ user, authError, authBusy, isLoggedIn, bootstrap, signUp, signIn, signOut }`。**`signUp/signIn` 会抛**（内部只有 `try/finally`，没有 catch），所以调用方必须接住并把文案写进 `authError`。
  - **2026-10-07 修订（Task 6 修正轮 1 已改，本 Task 的读法跟着变）**：**`signOut` 不属于"会抛"那一档**——它在 `finally` 前多了一个吃掉后端失败的 `catch`（理由与三条证据见 Task 6 Step 5 后的修订块）。所以 `handleSignOut` 里裸的 `await signOut()` 是**安全**的，而它**后面那五句清理（`clearSession()` / `documents` / `queue` / `messages` / `clearSelection()`）是承重的**：spec 5.3 要求"登出把 `auth_token` 与 `session_id` 一起清"，靠的正是这几句跑得完。请把那一行的注释写成事实（"后端失败已在 `useAuth` 里吞掉，所以这里一定能清到"），**不要照抄计划代码块里那句 `// 令牌一定清得掉（Task 6 的 finally）`**——`finally` 保证的是清理发生，不是不抛。
  - **2026-10-07 修订（订正上面那行花括号）**：`useAuth()` 实际返回**九个**，上面漏了 `clearAuth`（`useAuth.js:106`）。但 App.vue **不该**解构它：登出的正确写法是 `await signOut()`，它内部的 `finally` 已经调过 `clearAuth()`；界面上直接调 `clearAuth` 等于只登出本地、不给后端删令牌的机会（阶段一没有别的用处，阶段二"改密码后旧令牌全失效"也用不到）。
- Produces：
  - `useSession()` → `{ sessionId, setSession(next) -> string, resetSession() -> string, clearSession() -> string }`，其中 `sessionId` 是**模块级同一个 ref**
  - `AuthPanel.vue`：props 无，emit `submit`，载荷 `{ mode: 'login'|'register', payload: { identifierType, identifier, password, nickname } }`
  - `StatusBar.vue`：props 只剩 `selectedCount`

> **这一段的三条纪律**（写坏了症状都很隐蔽，先立规矩再动手）：
> 1. **`sessionId` 必须上移到模块作用域。** 现在它建在 `useSession()` 函数里，App.vue 与 AuthPanel 各调一次就是两个 ref——后端铸造的 id 会写进 localStorage，而界面还在用上个账号那个。症状是"换了账号，历史却没换"，正好是需求 2 的反面。
> 2. **AuthPanel 不碰 API，只收表单。** 登录成功后的两拍（`setSession` → `enterWorkspace`）必须由 App.vue 同一处发起：让 AuthPanel 自己调 `signIn`，`isLoggedIn` 一变 `v-if` 就要卸载它，emit 与 watcher 的先后只能靠 Vue 调度器的 flush 时机解释；放在 App.vue 里则是直白的顺序代码，并且"hydrate 先于 restore"这条既有不变式（`onMounted` 里那句注释）原样保住。
> 3. **`isLoggedIn` 是每次调用现造的 computed，但它读的是模块级 `user`**——所以 App.vue 与 AuthPanel 各自 `useAuth()` 拿到的 `isLoggedIn` 永远同进同退。`authBusy`/`authError` 本来就是模块级 ref，谁写谁读都同步。

- [ ] **Step 1: 写 `useSession` 的失败测试**

创建 `frontend/tests/useSession.test.js`：

```js
// useSession 的三条契约：出厂值是合法 uuid、外部塞进来的坏值进不了请求 URL、
// 以及"多处调用拿到的是同一个 ref"。第三条是 Task 7 新加的能力（登录要把后端铸造的
// 对话 id 换进界面），前两条是把原本只写在注释里的话钉住。
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useSession } from '../src/composables/useSession.js'

const KEY = 'session_id'
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const GOOD = '3f2b1c00-1111-2222-3333-444455556666'

// 构造那一下的行为只能重新 import 来测：sessionId 的初值在模块加载时读一次 localStorage，
// 静态 import 会把它冻在第一个测试的时钟上。
// 这里用 resetModules 不是逃避——Task 6 告诫过的那条是"三处读同一个对象"，
// 而那件事由下面第 5 条测专门证，两边不冲突。
async function freshUseSession(seed) {
  localStorage.removeItem(KEY)
  if (seed !== undefined) localStorage.setItem(KEY, seed)
  vi.resetModules()
  const mod = await import('../src/composables/useSession.js')
  return mod.useSession()
}

describe('useSession', () => {
  beforeEach(() => localStorage.removeItem(KEY))

  it('没存过就造一个 uuid 并立刻落盘', async () => {
    const { sessionId } = await freshUseSession()
    expect(sessionId.value).toMatch(UUID_RE)
    expect(localStorage.getItem(KEY)).toBe(sessionId.value)
  })

  it('DevTools 里塞进来的坏值（含 "/"）当场作废并换成新 uuid', async () => {
    // 这个键会拼进 GET /api/history/${sessionId}：带 "/" 的值能把请求路径劈开，
    // 所以"由构造不可达"这条要在这一层守（Task 2 ruling I-2 的前端半边）
    const { sessionId } = await freshUseSession('../../etc/passwd')
    expect(sessionId.value).toMatch(UUID_RE)
    expect(localStorage.getItem(KEY)).toBe(sessionId.value)
  })

  it('setSession 同时改 ref 与 localStorage；坏形状换成 uuid 而不是原样写入', async () => {
    const { sessionId, setSession } = await freshUseSession()
    expect(setSession(GOOD)).toBe(GOOD)
    expect(sessionId.value).toBe(GOOD)
    expect(localStorage.getItem(KEY)).toBe(GOOD)

    const after = setSession('not-a-uuid')
    expect(after).toMatch(UUID_RE)
    expect(localStorage.getItem(KEY)).toBe(after)
  })

  it('resetSession 换出来的 id 与清空前不同（需求 2「重新登录就是新对话」的存储层判据）', async () => {
    const { sessionId, setSession, resetSession } = await freshUseSession()
    setSession(GOOD)
    const next = resetSession()
    expect(next).not.toBe(GOOD)
    expect(next).toMatch(UUID_RE)
    expect(localStorage.getItem(KEY)).toBe(next)
  })

  it('两次 useSession() 返回同一个 ref：登录写入的 id 界面立刻看得见', () => {
    const a = useSession()
    const b = useSession()
    expect(a.sessionId).toBe(b.sessionId)
    a.setSession(GOOD)
    expect(b.sessionId.value).toBe(GOOD)
  })

  it('clearSession 把键删掉，但 ref 仍是一个合法 uuid（登出后界面不许出现空 id）', async () => {
    const { sessionId, clearSession } = await freshUseSession()
    clearSession()
    expect(localStorage.getItem(KEY)).toBe(null)
    expect(sessionId.value).toMatch(UUID_RE)
  })
})
```

- [ ] **Step 2: 跑红**

```bash
cd frontend && npm test
```
预期：新增这 6 条红在 `setSession is not a function`（`useSession()` 目前只返回 `sessionId`/`resetSession`），第 5 条红在两个 ref 不是同一个。**其余文件必须照旧全绿**——这条文件不碰任何既有代码，红了说明测试自己写错了。

- [ ] **Step 3: 改造 `useSession.js`**

整文件替换为：

```js
import { ref } from 'vue'

const STORAGE_KEY = 'session_id'
// 只接受 UUID 形状：后端路由不匹配含 "/" 的 id，坏 id 由构造不可达（Task 2 ruling I-2）
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

// localStorage 里三个键（auth_token / session_id / selected_parent_ids）中这一个归这里管。
// 消息永不落本地，刷新后靠 GET /api/history 恢复（spec 五节）。
function validOrFresh(raw) {
  if (raw && UUID_RE.test(raw)) return raw
  const fresh = crypto.randomUUID()
  localStorage.setItem(STORAGE_KEY, fresh)
  return fresh
}

// ref 必须在模块作用域：Task 7 之后 App.vue 与 AuthPanel 都要读写它——
// 放函数里就是两个互不相干的副本，后端铸造的对话 id 落了盘却没进界面，
// 症状是"换了账号历史却没换"，正好是需求 2 的反面。
// （对照 useChunkSelection：那个的 ref 留在函数内，因为它只被 App.vue 一处持有。）
const sessionId = ref(validOrFresh(localStorage.getItem(STORAGE_KEY)))

export function useSession() {
  function persist(next) {
    // 外部塞进来的坏值一律换成 uuid，而不是原样落盘：
    // setSession 的入参来自 HTTP 响应，那已经是"不完全可信"的边界
    const safe = typeof next === 'string' && UUID_RE.test(next) ? next : crypto.randomUUID()
    sessionId.value = safe
    localStorage.setItem(STORAGE_KEY, safe)
    return safe
  }

  // 登录/注册成功时用后端 uuid4() 铸造的那个 id 覆盖本地（spec 5.3）：
  // 重新登录就是新对话，刷新不会走到这里所以对话不丢。
  function setSession(next) {
    return persist(next)
  }

  function resetSession() {
    // "清空对话"要换 id（与归档 app.py 等价）：旧 session 的历史已被 DELETE 清掉，
    // 换新 id 顺带避免"清空后立刻刷新"时和还在飞的请求抢同一个 session。
    return persist(crypto.randomUUID())
  }

  function clearSession() {
    // 登出时 auth_token 与 session_id 一起清（spec 5.3）。键删掉即可，
    // ref 仍留一个合法 uuid：界面此刻是登录页，不许出现空 id 这种半吊子状态。
    localStorage.removeItem(STORAGE_KEY)
    sessionId.value = crypto.randomUUID()
    return sessionId.value
  }

  return { sessionId, setSession, resetSession, clearSession }
}
```

> 原来的 `crypto.randomUUID()` 从"正常路径"降级为**离线兜底**（spec 5.3）：正常登录后 id 来自后端。这一点在注释里说清了，代码里它只剩两处调用——`validOrFresh` 的出厂值与 `resetSession`。

```bash
cd frontend && npm test tests/useSession.test.js
```
预期：`6 passed`。

- [ ] **Step 4: `StatusBar.vue` 去掉 session chip（连测试）**

先建 `frontend/tests/StatusBar.test.js`（这两条是整个改造里唯一能自动化的"不显示 session_id"守卫——需求 3 的后半句）：

```js
// 需求 3 说"不显示 session_id"。`.session-debug` 块删了，但 StatusBar 顶部那个
// 显示前 8 位的 chip 也在同一句话的账上（spec 5.4：留着等于把 id 从左下挪到了顶上）。
// 这条测就是为了让它别哪天被"顺手加回去"。
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import StatusBar from '../src/components/StatusBar.vue'

describe('StatusBar', () => {
  it('模式标签两态：选了块报数量，一个不选就是普通对话', () => {
    const rag = mount(StatusBar, { props: { selectedCount: 3 } })
    expect(rag.text()).toContain('知识库模式')
    expect(rag.text()).toContain('3')
    expect(mount(StatusBar, { props: { selectedCount: 0 } }).text()).toContain('普通对话模式')
  })

  it('界面上不出现 session 字样，也不再接 sessionId prop', () => {
    // 故意把 sessionId 传进去：删掉 prop 之后 Vue 只会把它当 attrs 忽略，
    // 于是"传了但没人读"这种残留在测里也照样绿——所以判据看的是文本而不是 prop 声明。
    const wrapper = mount(StatusBar, { props: { selectedCount: 0, sessionId: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee' } })
    expect(wrapper.find('.session-chip').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('session')
    expect(wrapper.text()).not.toContain('aaaaaaaa')
  })
})
```

```bash
cd frontend && npm test tests/StatusBar.test.js
```
预期：第 2 条红在 `.session-chip` 存在。改 `StatusBar.vue` 整文件为：

```vue
<script setup>
// 模式标签只看"选了几个文档块"，不看后端回传：选了块即 RAG（spec 6.2 parent_ids 为空即普通对话）。
// Task 7（需求 3）：session 前缀 chip 整块删，sessionId prop 也一起删——留着 prop
// 就等于 App.vue 还在传一个没人读的值，下一个人会以为界面上还有地方用它。
const props = defineProps({
  selectedCount: { type: Number, required: true },
})
</script>

<template>
  <div class="status-bar">
    <span v-if="props.selectedCount > 0" class="status-indicator status-rag">
      🔍 知识库模式（{{ props.selectedCount }} 个文档块）
    </span>
    <span v-else class="status-indicator status-normal">💬 普通对话模式</span>
  </div>
</template>
```

`.status-bar` 是 `justify-content: space-between`，只剩一个孩子后自然靠左，不用动 CSS。`computed` 那行 import 随 `shortSession` 一起删（留着是 unused import，build 不报错但 lint 口径脏）。

- [ ] **Step 5: 写 `AuthPanel` 的失败测试**

创建 `frontend/tests/AuthPanel.test.js`：

```js
// AuthPanel 只管两件事：tab 切换与"格式坏值不发请求"。
// 它不碰 API（登录成功后的 setSession 归 App.vue 编排），所以这里一个 fetch 桩都不需要。
import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import AuthPanel from '../src/components/AuthPanel.vue'
import { useAuth } from '../src/composables/useAuth.js'

const { authBusy, authError } = useAuth()

afterEach(() => {
  // useAuth 的状态是模块级的（没有 Pinia 的代价，Task 6 已记），
  // 上一条测把 authBusy 拨成 true 不还回去，下一条就莫名点不动提交按钮
  authBusy.value = false
  authError.value = ''
})

function fields(wrapper) {
  return {
    identifier: wrapper.findAll('input[type="text"]')[0],
    password: wrapper.find('input[type="password"]'),
    nickname: wrapper.findAll('input[type="text"]')[1],
    typeSelect: wrapper.find('select'),
    submit: wrapper.find('button[type="submit"]'),
  }
}

async function toRegister(wrapper) {
  await wrapper.findAll('.picker-tab')[1].trigger('click')
}

describe('AuthPanel：默认登录态', () => {
  it('只有账号与密码两个输入框，按钮写「登录」', () => {
    const { identifier, password, nickname, typeSelect, submit } = fields(mount(AuthPanel))
    expect(identifier.exists()).toBe(true)
    expect(password.exists()).toBe(true)
    expect(nickname).toBeUndefined()
    expect(typeSelect.exists()).toBe(false)
    expect(submit.text()).toBe('登录')
  })

  it('登录时邮箱归一小写、手机号原样（与后端 LoginIn 的分支同口径）', async () => {
    const wrapper = mount(AuthPanel)
    const { identifier, password, submit } = fields(wrapper)
    await identifier.setValue('A@B.com')
    await password.setValue('hunter2')
    await submit.trigger('click')
    expect(wrapper.emitted('submit')[0][0].payload.identifier).toBe('a@b.com')

    const phone = mount(AuthPanel)
    const pf = fields(phone)
    await pf.identifier.setValue('13800138000')
    await pf.password.setValue('hunter2')
    await pf.submit.trigger('click')
    expect(phone.emitted('submit')[0][0].mode).toBe('login')
    expect(phone.emitted('submit')[0][0].payload.identifier).toBe('13800138000')
  })
})

describe('AuthPanel：切到注册', () => {
  it('出现账号类型选择与昵称框，按钮写「注册并进入」', async () => {
    const wrapper = mount(AuthPanel)
    await toRegister(wrapper)
    const { nickname, typeSelect, submit } = fields(wrapper)
    expect(typeSelect.exists()).toBe(true)
    expect(nickname.exists()).toBe(true)
    expect(submit.text()).toBe('注册并进入')
  })

  it('合法邮箱注册：payload 带 identifierType 与已归一的 identifier', async () => {
    const wrapper = mount(AuthPanel)
    await toRegister(wrapper)
    const { identifier, password, nickname, submit } = fields(wrapper)
    await identifier.setValue('Me@Example.COM')
    await password.setValue('hunter2')
    await nickname.setValue('小明')
    await submit.trigger('click')
    expect(wrapper.emitted('submit')[0][0]).toEqual({
      mode: 'register',
      payload: { identifierType: 'email', identifier: 'me@example.com', password: 'hunter2', nickname: '小明' },
    })
  })

  it('选手机号时按手机号规则校验（1 开头 11 位）', async () => {
    const wrapper = mount(AuthPanel)
    await toRegister(wrapper)
    await wrapper.find('select').setValue('phone')
    const { identifier, password, submit } = fields(wrapper)
    await identifier.setValue('23800138000')
    await password.setValue('hunter2')
    await submit.trigger('click')
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.find('.picker-error').text()).toBe('手机号格式不正确')
  })
})

describe('AuthPanel：坏值不发请求', () => {
  it('坏邮箱 / 短密码各自出中文文案，点提交不 emit', async () => {
    // 坏值时按钮本身已被 fieldError 置成 disabled，这里的"不 emit"于是有两条腿：
    // disabled 挡掉事件、submit() 里的门禁再挡一次。不管测试库对 disabled 元素派发不派发事件，
    // 判据都成立——这正是想要的口径。
    const wrapper = mount(AuthPanel)
    const { identifier, password, submit } = fields(wrapper)
    await identifier.setValue('a@b')
    await password.setValue('hunter2')
    await submit.trigger('click')
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.find('.picker-error').text()).toBe('邮箱格式不正确')

    await identifier.setValue('a@b.com')
    await password.setValue('12345')
    await submit.trigger('click')
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.find('.picker-error').text()).toBe('密码至少 6 位')
  })

  it('authBusy 时按钮 disabled 且点不出第二次 emit', async () => {
    const wrapper = mount(AuthPanel)
    const { identifier, password, submit } = fields(wrapper)
    await identifier.setValue('a@b.com')
    await password.setValue('hunter2')
    authBusy.value = true
    // 必须等一次 flush：disabled 是渲染出来的属性，改了 ref 不重渲染就还是旧 DOM
    await wrapper.vm.$nextTick()
    expect(submit.attributes('disabled')).toBeDefined()
    await submit.trigger('click')
    expect(wrapper.emitted('submit')).toBeUndefined()

    authBusy.value = false
    await wrapper.vm.$nextTick()
    await submit.trigger('click')
    expect(wrapper.emitted('submit')).toHaveLength(1)
  })

  it('后端文案（authError）在字段本地合法时才显示，一旦判出坏值立刻让位', async () => {
    const wrapper = mount(AuthPanel)
    const { identifier, password } = fields(wrapper)
    authError.value = '账号或密码不正确'
    // 空表单时 fieldError 是「请填写账号」，它会压住后端文案——这是刻意的：
    // 连该填的都没填完，上一次失败的原因对当下没有帮助
    await identifier.setValue('a@b.com')
    await password.setValue('hunter2')
    expect(wrapper.find('.picker-error').text()).toBe('账号或密码不正确')

    await identifier.setValue('bad')
    expect(wrapper.find('.picker-error').text()).toBe('邮箱格式不正确')
  })
})
```

```bash
cd frontend && npm test tests/AuthPanel.test.js
```
预期：整个文件红在 `Failed to resolve import "../src/components/AuthPanel.vue"`（文件还不存在）。

> **2026-10-07 修订（执行期发现 Step 5 与 Step 6 自相矛盾，裁定"改断言、不改组件"）**：上面代码块里有**两条断言打在登录 tab**（`:a@b` → 「邮箱格式不正确」，以及 `bad` 让后端文案退位），而 Step 6 的 `fieldError` 只在 `mode.value === 'register'` 分支校验账号形状——照 Step 6 写实现，这两条必红；照这两条写实现，就得给登录分支补一个 Step 6 没有的形状校验。**执行期第一版选了后者，于是撞上一个真账号：**`core/migrations.py:19` 的 `DEFAULT_IDENTIFIER = "default@local"` 是启动期迁移**直接 INSERT 进 users 表**的（不走 `/api/auth/register`，所以从没受过 `EMAIL_RE` 的检验），而 `default@local` 的域名**没有点**，既过不了 `EMAIL_RE`（`schemas/auth.py:11` 要求 `.` + ≥2 位 TLD）也过不了 `PHONE_RE`。后端 `LoginIn`（`schemas/auth.py:50-55`）对登录**完全不验形状**，只 strip + 含 @ 才小写，所以这个账号在 API 上是能登录的、也是 Task 3 那 13 行旧文档的主人。前端一给它加本地形状校验，就等于**把界面唯一的旧数据入口关死**，而且症状是"邮箱格式不正确"这种把人往错处引的文案。
>
> **裁定：登录 tab 不校验账号形状**（与后端 `LoginIn` 同宽），Step 6 那版 register-only 的 `fieldError` 才是对的。两条断言按下面改，`AuthPanel.vue` 里执行期补的那个 `else if (!PHONE_RE && !EMAIL_RE) return '邮箱格式不正确'` 分支**要删掉**：
> - `坏邮箱 / 短密码各自出中文文案，点提交不 emit`：第一拍从"坏邮箱"换成**空账号**（`identifier.setValue('')` → 「请填写账号」），第二拍短密码不动。这样这条测仍然钉"本地坏值不发请求"，且不再依赖一个后端并不执行的形状判据。
> - `后端文案（authError）在字段本地合法时才显示，一旦判出坏值立刻让位`：把让位的那一拍从 `setValue('bad')` 换成**密码改成 `'123'`**（「密码至少 6 位」是登录 tab 也成立的本地判据），先"合法时显示后端文案"那一拍不动。
>
> 顺带订正 `3190` 那句注释："不管测试库对 disabled 元素派发不派发事件，判据都成立"——**只成立一半**。本机 jsdom 30.1.1 对 `isTrusted=false` 的 click **不执行按钮的激活行为**，所以 `submit.trigger('click')` 根本不会变成 submit 事件；真实浏览器里 `disabled` 那道 DOM 防线确实把点击吞了，但**编程派发**能绕过它，而当前测法从没验证过 `submit()` 内部那道门禁（Step 6 变异 E 全绿即为证据）。手势改打 `wrapper.find('form').trigger('submit')`（本仓既有口径，见 `frontend/tests/chunk-selection.test.js:105`），理由与代价见 Step 6 后的修订块。

- [ ] **Step 6: 写 `AuthPanel.vue`**

```vue
<script setup>
import { computed, reactive, ref, watch } from 'vue'

import { useAuth } from '../composables/useAuth.js'

// 与后端 schemas/auth.py 同一套口径（那边才是权威；改动要两边一起改）。
// 这里不是防线，只是让人少跑一趟网络：绕过界面直接打 /api/auth/register 照样 422。
const EMAIL_RE = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/
const PHONE_RE = /^1[3-9]\d{9}$/
const PASSWORD_MIN = 6
const PASSWORD_MAX = 64
const NICKNAME_MAX = 50 // 对齐 users.nickname 的 String(50)

const emit = defineEmits(['submit'])
// authBusy/authError 是模块级 ref：谁发起登录都是同一份忙态与文案，
// 所以这个组件既不需要 props，也不需要在 emit 之后自己收尾
const { authBusy, authError } = useAuth()

const mode = ref('login')
const form = reactive({ identifierType: 'email', identifier: '', password: '', nickname: '' })

// 切 tab 只清文案不清字段：同一个人往往两个 tab 用同一个邮箱，
// 清了字段就等于让"填错切回去看看"变成重打一遍
watch(mode, () => { authError.value = '' })

const fieldError = computed(() => {
  const identifier = form.identifier.trim()
  if (!identifier) return '请填写账号'
  if (mode.value === 'register') {
    if (form.identifierType === 'email') {
      if (!EMAIL_RE.test(identifier)) return '邮箱格式不正确'
    } else if (!PHONE_RE.test(identifier)) {
      return '手机号格式不正确'
    }
  }
  if (form.password.length < PASSWORD_MIN) return `密码至少 ${PASSWORD_MIN} 位`
  if (form.password.length > PASSWORD_MAX) return `密码最多 ${PASSWORD_MAX} 位`
  if (mode.value === 'register' && form.nickname.trim().length > NICKNAME_MAX) return `昵称最多 ${NICKNAME_MAX} 个字符`
  return ''
})

// 登录不锁类型：后端按有没有 @ 归一（LoginIn 只收 identifier + password）。
// 只有邮箱归一小写——照抄 normalize_identifier 的分支，否则"A@B.com 注册、a@b.com 登录"
// 这种"明明是同一个账号却说不存在"的错觉会在界面里生根。
function normalizedIdentifier() {
  const raw = form.identifier.trim()
  if (mode.value === 'login') return raw.includes('@') ? raw.toLowerCase() : raw
  return form.identifierType === 'email' ? raw.toLowerCase() : raw
}

function submit() {
  // 门禁两道：忙态防双击（第二次只会撞上 409），坏值防白跑一趟
  if (authBusy.value || fieldError.value) return
  emit('submit', {
    mode: mode.value,
    payload: {
      identifierType: form.identifierType,
      identifier: normalizedIdentifier(),
      password: form.password,
      nickname: form.nickname.trim(),
    },
  })
}
</script>

<template>
  <section class="auth-panel">
    <h1 class="auth-title">🔑 知识库平台</h1>

    <div class="picker-tabs">
      <button
        class="picker-tab"
        :class="{ 'picker-tab-active': mode === 'login' }"
        type="button"
        @click="mode = 'login'"
      >登录</button>
      <button
        class="picker-tab"
        :class="{ 'picker-tab-active': mode === 'register' }"
        type="button"
        @click="mode = 'register'"
      >注册</button>
    </div>

    <!-- 用 form + submit 而不是 button @click：回车就能登录，而回车点在输入框上
         是最常见的手势；@submit.prevent 保证不会把整页刷掉 -->
    <form class="auth-form" @submit.prevent="submit">
      <label class="auth-field">
        <span>账号</span>
        <input
          v-model="form.identifier"
          class="picker-input"
          type="text"
          autocomplete="username"
          :placeholder="mode === 'login' ? '邮箱或手机号' : '填邮箱或手机号'"
        />
      </label>

      <label v-if="mode === 'register'" class="auth-field">
        <span>账号类型</span>
        <select v-model="form.identifierType" class="picker-input">
          <option value="email">邮箱</option>
          <option value="phone">手机号</option>
        </select>
      </label>

      <label class="auth-field">
        <span>密码</span>
        <input
          v-model="form.password"
          class="picker-input"
          type="password"
          :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
          placeholder="至少 6 位"
        />
      </label>

      <label v-if="mode === 'register'" class="auth-field">
        <span>昵称（可留空）</span>
        <input v-model="form.nickname" class="picker-input" type="text" :maxlength="NICKNAME_MAX" placeholder="左下角显示的名字" />
      </label>

      <!-- 本地格式提示优先于后端上次的失败文案：已经知道这串不是邮箱时，
           再提"账号或密码不正确"只会把人往错的方向引 -->
      <p v-if="fieldError" class="picker-error">{{ fieldError }}</p>
      <p v-else-if="authError" class="picker-error">{{ authError }}</p>

      <button class="btn auth-submit" type="submit" :disabled="authBusy || !!fieldError">
        {{ authBusy ? (mode === 'login' ? '登录中…' : '注册中…') : (mode === 'login' ? '登录' : '注册并进入') }}
      </button>
      <p class="auth-hint">只校验格式，不发验证码；忘记密码暂无找回入口。</p>
    </form>
  </section>
</template>
```

> **tab 复用 `.picker-tabs` / `.picker-tab`**：候选池弹窗那套 tab 的形状就是这里要的，抄过来比新造一套 token 更省（G-4 的"颜色口径不增"也顺带守住）。`NICKNAME_MAX` 在模板里用 `:maxlength` 绑定，所以它必须是 `setup` 里暴露出来的常量——这也是它写成模块级 const 而不是硬编码 50 的原因。

```bash
cd frontend && npm test tests/AuthPanel.test.js
```
预期：`8 passed`。

> **2026-10-07 修订（执行期第二处偏离，裁定撤掉）**：执行期为了让 `submit.trigger('click')` 在 jsdom 里跑得通，给提交按钮加了 `@click.prevent="submit"`（`AuthPanel.vue:142`），并在生产 markup 里留了 7 行"jsdom 对 untrusted click 不执行激活行为"的环境说明（`:94-100`）。评审逐路径核过它在**真实浏览器里行为是对的**（点击：click → handler → `.prevent` 取消激活行为 → 表单不提交；回车：隐式提交就是对默认按钮派发 click，走的同一条；`requestSubmit()`：只走 `@submit.prevent`），但裁定**仍然撤掉**，三条理由：① 生产模板从此有**两个提交入口**，而"一次手势只 emit 一次"这条性质完全系于 `.prevent` 一个修饰符——把它删掉（真实浏览器里就是点一次登录发两次 POST，第二次撞 409），8 条测**全绿**，等于用一条没有判据守着的不变式换掉了原来的单入口；② 本仓既有口径是把提交手势打在 form 上（`frontend/tests/chunk-selection.test.js:105` 就是 `wrapper.find('form').trigger('submit')`），为测试环境改生产接线这件事在这里一开面就收不住；③ jsdom 下这条 `@click` 测的本来就不是"人点按钮"的手势（激活行为没跑），保真度没有提高，只是换了一条与浏览器不同的路径。**改法**：模板回到 Step 6 代码块的单一 `@submit.prevent="submit"`，测里把 `submit.trigger('click')` 全部换成 `wrapper.find('form').trigger('submit')`（tab 切换那两处仍是 `.picker-tab` 的 click，`submit.attributes('disabled')` 那句保留——它是 DOM 层防线的真判据），`:94-100` 那 7 行环境说明整段搬进测文件顶部的注释。**附带收益**：submit 事件绕过 `disabled` 直达 `submit()`，于是 `submit()` 里 `if (authBusy || fieldError) return` 这道内部门禁第一次有判据守着（变异 E 应当当场长出牙）；`toHaveLength(1)` 继续钉"不双发"。

- [ ] **Step 7: `App.vue` 接线——整屏门禁 + `.user-rail` + 登录/登出编排**

`<script setup>` 里**只替换 import 段到 `handleClear` 为止**这一段（下面给出）。**后面这四个函数原样保留、一个字都不要改**：`handleChunkDeleted`（删块后的三件事）、`handleSend`、`handleStop`、`dismissError`——模板还在引用它们，整段替换时漏掉就是 build 不报错、一点发送就白屏。

```js
import { computed, onMounted, ref } from 'vue'

import AuthPanel from './components/AuthPanel.vue'
import ChatHeader from './components/ChatHeader.vue'
import ChatInput from './components/ChatInput.vue'
import ChunkPickerModal from './components/ChunkPickerModal.vue'
import DocumentPanel from './components/DocumentPanel.vue'
import MessageList from './components/MessageList.vue'
import StatusBar from './components/StatusBar.vue'
import { useAuth } from './composables/useAuth.js'
import { useChat } from './composables/useChat.js'
import { useChunkSelection } from './composables/useChunkSelection.js'
import { useDocuments } from './composables/useDocuments.js'
import { useSession } from './composables/useSession.js'

// 五个 composable 在 App.vue 里显式接线，不引 Pinia/Vuex（spec 五节）
const { sessionId, setSession, resetSession, clearSession } = useSession()
const { user, authError, isLoggedIn, bootstrap, signUp, signIn, signOut } = useAuth()
const {
  documents, queue, listError, docCount,
  refresh, enqueue, retry, dismiss,
} = useDocuments()
const {
  selectedChunks, selectedParentIds, selectedCount, pickerOpen, selectionError,
  hydrate, toggle, remove, clearSelection,
} = useChunkSelection()
const { messages, pending, error, restore, send, clear, abortStream, markChunkDeleted } = useChat()

const question = ref('')
const clearing = ref(false)
// 宽屏侧栏常驻，panelOpen 只在 ≤768px 起作用
const panelOpen = ref(false)

// 改造前 onMounted 的三拍原样搬进这个函数：顺序是既有不变式，不许重排。
// hydrate 要打一枪 /api/documents/chunks：放在 restore 之前，
// 让"选中项已被剪掉"这件事先于历史渲染，错误横幅只剩最后一条真的。
async function enterWorkspace() {
  await refresh()
  await hydrate()
  await restore(sessionId.value)
}

onMounted(async () => {
  // 启动第一拍（spec 5.2）：手上没令牌就一个请求都不发，
  // 否则未登录的人一进站就撞一串 401 横幅。
  if (await bootstrap()) await enterWorkspace()
})

// 登录/注册成功后的两拍在这里，而不是 AuthPanel 里：
// AuthPanel 自己调 API 的话，isLoggedIn 一变 v-if 就要卸载它，
// emit 与后续动作的先后只能靠调度器 flush 时机解释——顺序代码放这儿最直白。
async function handleAuth({ mode, payload }) {
  authError.value = ''
  let sid
  try {
    // signUp/signIn 会抛（useAuth 内部只有 try/finally），文案统一落在 authError 上给 AuthPanel 显示
    sid = mode === 'register' ? await signUp(payload) : await signIn(payload)
  } catch (err) {
    authError.value = err.message
    return
  }
  setSession(sid)   // 后端铸造的对话 id 覆盖本地（spec 5.3）：重新登录就是新对话
  await enterWorkspace()
}

async function handleSignOut() {
  // 先掐掉在飞的流：不掐的话这条流会在登出之后把答案写进已经换人的界面，
  // 而 useChat 的 done 记账会让它名正言顺地留在屏上
  abortStream()
  await signOut()      // 令牌一定清得掉（Task 6 的 finally）
  clearSession()       // auth_token 与 session_id 一起清（spec 5.3）
  // 界面此刻换成登录页，但 App 实例还在、这些 ref 也还在：不清的话下一个人登录后
  // 会在 enterWorkspace 覆盖之前瞥见上一个账号的文件名。documents/queue/messages 都是
  // composable 返回的 ref，直接赋空数组就行；选中项必须走 clearSelection（它同时回写 localStorage）。
  documents.value = []
  queue.value = []
  messages.value = []
  clearSelection()
  error.value = ''
  pickerOpen.value = false
}

// 头像：`users.avatar` 这一期恒为 'auto'（预设表情的选择器随 SettingsModal 在阶段二接入），
// 所以这里只做昵称首字母；昵称为空才退回账号标识，再空才是 '我'。
const avatarChar = computed(() => {
  const name = (user.value?.nickname || user.value?.identifier || '').trim()
  return name ? name.charAt(0).toUpperCase() : '我'
})

async function handleClear() {
  // 没有 UI 库可借，destructive 操作用原生 confirm：误点一次就再也找不回来
  if (!window.confirm('确认清空当前会话的全部消息？会删除后端保存的历史，不可恢复。')) return
  clearing.value = true
  const ok = await clear(sessionId.value)
  if (ok) {
    // 与 app.py 的行为等价：清空后换一个新的 session_id（旧 id 已被 DELETE 清空）。
    // 需求 3 删掉了「换一个 session_id」那个调试按钮，但换 id 这个动作不能跟着删（spec 5.4）。
    resetSession()
    question.value = ''
    // 原先这一步靠 watch(sessionId) 重拉历史。那个 watch 整条删了（下面注释说明原因），
    // 所以这里显式补一次：界面==历史这条不变式不许等到下次刷新才成立。
    await restore(sessionId.value)
  }
  clearing.value = false
}
```

> **`watch(sessionId, (next) => restore(next))` 为什么整条删掉**：改造前它服务两个入口——调试按钮和"清空对话"。Task 7 之后改这个 ref 的地方变成了**三**处（登录 `setSession`、登出 `clearSession`、清空 `resetSession`），而这三处对"要不要重拉历史"的答案各不相同：登录后要（但必须排在 hydrate 之后，watch 抢在前面就破了不变式），登出后**绝不能**（没令牌，一拉就是一串 401 横幅打在登录页上）。一个 watch 承担不了三种语义，改成各调用点显式 `restore()`。

模板两处改动：

```html
<template>
  <!-- 需求 5 的门禁：未登录整屏只有登录页。DocumentPanel、上传按钮、聊天输入
       统统不渲染——比"渲染出来但禁用"更难漏（spec 5.1） -->
  <main v-if="!isLoggedIn" class="auth-screen">
    <AuthPanel @submit="handleAuth" />
  </main>

  <div v-else class="app-shell" :class="{ 'panel-open': panelOpen }">
    <!-- ……panel-toggle 与 DocumentPanel 两段照旧，一字不改…… -->
    <aside class="side-panel">
      <DocumentPanel
        :selected-chunks="selectedChunks"
        :selection-error="selectionError"
        :queue="queue"
        :list-error="listError"
        :doc-count="docCount"
        :clearing="clearing"
        @enqueue="enqueue"
        @retry="retry"
        @dismiss="dismiss"
        @open-picker="pickerOpen = true"
        @deselect-chunk="remove"
        @clear="handleClear"
      />
      <div class="side-panel-inner">
        <!-- 需求 3：`.session-debug` 整块删除（含 <code class="session-value"> 与
             「换一个 session_id」按钮），原位置换成 `.user-rail`。
             ⚙ 这一期是 disabled 的占位：设置弹窗（改昵称/密码/api_key）在阶段二，
             现在点出一个空白弹窗比点不动更糟。title 说明"什么时候有"。 -->
        <hr class="panel-hr" />
        <div class="user-rail">
          <span class="rail-avatar" aria-hidden="true">{{ avatarChar }}</span>
          <span class="rail-name" :title="user?.identifier">{{ user?.nickname }}</span>
          <button
            class="btn btn-ghost btn-small rail-settings"
            type="button"
            disabled
            title="设置项将在下一阶段开放"
            aria-label="打开设置"
          >⚙</button>
          <button class="btn btn-ghost btn-small rail-signout" type="button" @click="handleSignOut">退出登录</button>
        </div>
      </div>
    </aside>

    <main class="chat-main">
      <div class="chat-container">
        <ChatHeader />
        <div class="chat-body">
          <!-- StatusBar 不再收 :session-id（prop 已删，见 Step 4） -->
          <StatusBar :selected-count="selectedCount" />
          <!-- ……error-banner / MessageList / ChatInput / ChunkPickerModal 四段照旧…… -->
```

同时删掉两处现在没人用的东西：`import { watch }` 的 `watch`（改成 `import { computed, onMounted, ref } from 'vue'`，上面已给），以及 `useSession()` 解构里没再用的名字。**`.session-debug` 那段整块删干净**，包括它外面那层 `<hr class="panel-hr" />` 之后到 `</div>` 的全部内容——留着 `sessionId` 的唯一读点就没了，需求 3 才算真做完。

> **2026-10-07 修订（Step 7 执行后评审的三条补法，本 Task 内收）**：
> ① **新增 `frontend/tests/App.auth-gate.test.js`**。Step 7 整段原本零自动化覆盖——而这里是 spec 5.3"登出把 `auth_token` 与 `session_id` 一起清 + 界面不残留上一个账号的东西"在界面上的**唯一**实现处，跨账号残留又正是整条改造的主题；谁删掉 `documents.value = []` 或把 `clearSelection()` 挪到 `await signOut()` 之前，今天没有测会红、build 也不会红。补法要求**只 `vi.stubGlobal('fetch', …)` 一个按 URL 记账的假实现，不 mock 任何 composable**（mock 五个 composable 断言调用次数测的是 mock；读源码字符串做包含断言会在重构时挡住正确改写——两种都不要）：
> - 未登录（`localStorage.clear()` 后挂 `App` + `flushPromises`）：断 `.auth-screen` 在、`.user-rail` 不在，且记账里**一条非 `/api/auth/` 的请求都没有**——这条同时钉住整屏 `v-if` 门禁与"手上没令牌一个请求都不发"。
> - 带一枚合法形状的 `auth_token` 重挂：断 `/api/documents/chunks` 的请求**早于** `/api/history/`，把 `enterWorkspace()` 的 refresh → hydrate → restore 不变式从注释升级成判据。
> - 点 `.rail-signout`：断 `/api/auth/logout` 发过、`auth_token` 与 `session_id` 两个键都不在 localStorage、`.auth-screen` 回来。
> ② **`handleSignOut` 里补一行 `authError.value = ''`**。`clearAuth()`（`useAuth.js:100-104`）不清 `authError`，而 `useAuth.js` 不在本 Task 的 Files 里——但 App.vue 在，一行就在范围内。（量级我按代码重算过：登出时 `<AuthPanel>` 因 `v-if` 换分支整棵重挂，`mode`/`form` 是组件局部状态 → 空表单的「请填写账号」会压住后端文案，可见窗口只有"下一个人把账号密码填到本地合法、还没点提交"那一刻，所以是 Minor 而非数据问题。）
> ③ **`handleAuth` 里给 `await enterWorkspace()` 包 `try`**：登录已经成功（`user` 已置、令牌已落）之后若三拍里任何一拍 reject，用户停在**空白工作区**且无任何提示，只在控制台留一条 unhandled rejection。`refresh/hydrate/restore` 各自内部有 catch 所以现实概率低，但兜一句 `error.value = '工作台加载失败，请刷新重试'` 比让它裸着便宜。

- [ ] **Step 8: CSS（末尾追加，不动 L-1/L-2 那两块）**

`layout.css` 先**删三条已成死代码的规则**：`.session-debug`（第 24 行）、`.session-value`（第 25-31 行）、`.session-chip`（第 80 行）。然后在文件末尾追加：

```css
/* ---- 登录页与左下角用户栏（阶段一 Task 7）----
   颜色全部取现有 token：--grad-brand-135/--on-brand 是 .user-avatar 用过的同一对，
   面板底与边框沿用 .side-panel 的配方。G-4 的"variables.css 之外零色值字面量"口径不增。 */
.auth-screen { display: flex; align-items: center; justify-content: center; height: 100%; padding: 16px; }
.auth-panel {
  width: min(92vw, 420px);
  display: flex; flex-direction: column; gap: 12px;
  padding: 20px;
  background: var(--panel-bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: var(--shadow-panel);
}
.auth-title { font-size: 20px; font-weight: 600; }
.auth-form { display: flex; flex-direction: column; gap: 10px; }
.auth-field { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--text-muted); }
.auth-submit { margin-top: 4px; }
.auth-hint { font-size: 12px; color: var(--text-muted); }

.user-rail { display: flex; align-items: center; gap: 8px; font-size: 13px; }
/* 与消息气泡的 .user-avatar/.message-avatar 不是一回事，类名必须另起：
   那两个是 36px 的对话头像，这里是 28px 的账号位，同名会让 ≤768 的规则互相污染 */
.rail-avatar {
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  width: 28px; height: 28px; border-radius: 50%;
  background: var(--grad-brand-135); color: var(--on-brand); font-size: 14px;
}
/* 昵称上限 50 字，侧栏只有 320px：不截断就会把 ⚙ 和「退出登录」挤出面板（同 .queue-name 的老配方） */
.rail-name {
  flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-weight: 600;
}
.rail-settings, .rail-signout { flex-shrink: 0; }

/* 追加而不是改第 101 行那个 ≤768 分支：那块是 L-1/L-2/L-3 的根治现场，动它要重新量行高。
   .user-rail 在侧栏浮层内部，不是 app-shell 的 grid item，不会多出第三轨，
   所以这里只防两件小事：长昵称换行后按钮贴脸、375px 上面板内边距挤压。 */
@media (max-width: 768px) {
  .user-rail { flex-wrap: wrap; }
  .auth-panel { padding: 16px; }
}
```

`variables.css` 本次**不新增 token**（spec 5.8 允许把 `--avatar-*`、`--control-gap` 放进去，但这两样的真用户都在阶段二的 `.chat-controls`/`SettingsModal`；现在就加等于给 G-4 增加无人引用的键）。

跑 G-4 与死代码自查：

```bash
cd frontend && grep -rn "session-debug\|session-value\|session-chip" src/ ; echo "上面无输出、退出码 1 = 通过"
cd frontend && grep -nE "#[0-9a-fA-F]{3,8}|rgba?\(|hsl\(" src/App.vue src/components/AuthPanel.vue src/components/StatusBar.vue src/styles/layout.css ; echo "上面无输出、退出码 1 = G-4 通过"
```
两条都必须 0 命中。第二条尤其注意：新写的 `.rail-avatar` 若顺手写了 `#fff`，G-4 会在这里现原形。

- [ ] **Step 9: 全绿 + 构建 + 提交**

```bash
cd frontend && npm test
cd frontend && npm run build
```
预期：`npm test` 从 Task 6 后的约 **96 passed / 8 文件** 涨到约 **112 passed / 11 文件**（`useSession.test.js` +6、`StatusBar.test.js` +2、`AuthPanel.test.js` +8，共 +16；**以汇总行为准**）。`npm run build` exit 0。**0 failed 是硬要求。**

> **2026-10-07 修订（Task 6 收口后的实测基数）**：上一段那两个"约"都低了——Task 6 落地时 Step 7 之后又补了修正轮，`api-auth.test.js`（2 条）是新文件，所以真实基数是 **98 passed / 9 文件**（HEAD `0278350` 实测）。+16 这个加数仍然正确（三个新文件的 `it()` 数逐个数过：6 / 2 / 8），因此本 Task 的目标是 **114 passed / 12 文件**。差一两条不奇怪，**照旧以汇总行为准**，但报告里必须写"实跑得到的是多少"，不许抄这一行交差。
>
> **2026-10-07 再修订（修正轮 1 之后）**：执行期实跑到的就是 **114 passed / 12 文件**（`af0878c` 上控制器实测，与上一段的预测一致），但评审后本 Task 内又收了三条补法（见 Step 7 之后的修订块），其中 ① 是**新测试文件** `frontend/tests/App.auth-gate.test.js`（3 个 `it()`：未登录门禁、请求顺序、登出清键），所以门禁目标改成 **约 117 passed / 13 文件**——照旧只钉 `0 failed`，**数字抄当轮汇总行**。`AuthPanel.test.js` 的条数**不变**（Step 5 那次改的是同一个 `it()` 里的断言，不是加用例），8 条仍是 8 条。下面 `git add` 那段要**多这一格**，少加一个文件就等于把新测留在未追踪状态。

> **build 通过 ≠ 界面没问题**：这一段真正的验收（未登录不请求、左下角头像+昵称+⚙ 禁用、登录后进工作区、375px 下 rail 不塌）全在浏览器里，Task 8 Step 4 逐条打（主路是 browser-use，尺寸量测不好钉时才搬 Edge headless 探针）。这里不提前跑，是因为 `npm run dev` 起来之后与后端单实例的端口/进程纪律纠缠在一起（见 Global Constraints 的"只有一个 uvicorn"），一次性放在 Task 8 收口更省事。

```bash
cd D:/知识库平台-前后端分离 && git add frontend/src/App.vue frontend/src/components/AuthPanel.vue \
  frontend/src/components/StatusBar.vue frontend/src/composables/useSession.js \
  frontend/src/styles/layout.css \
  frontend/tests/AuthPanel.test.js frontend/tests/StatusBar.test.js frontend/tests/useSession.test.js
git status --short
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(frontend): 登录页整屏门禁 + 左下角用户栏，session_id 从界面消失（阶段一 Task 7）"
```

**到这一步，阶段一的"能登录、各看各的文档、界面上认得出是谁"就都在代码里了。** 剩下的全是验收：双端门禁、重启一个实例、live curl 与浏览器判据、spec 7.3 的 A/B 正证反证，以及台账——Task 8。

### Task 8: 双端门禁 + 真服务验收 + 台账（阶段一的完成定义在这里）

**Files:**
- Create → Delete: `backend/_probe_auth_isolation.py`（HTTP + SQL 判据脚本，跑完即 `rm`，**不入库**）
- Create → Delete（**仅当 browser-use 不好显式钉视口时才建**）: `frontend/probe-auth-rail.mjs`（Edge headless 尺寸量测探针，跑完即 `rm`）
- Create: `.superpowers/sdd/2026-10-06-user-auth-isolation-phase-1/progress.md`（ledger，`git add -f`）

> **本 Task 的三条纪律**
> 1. **只重启、绝不多起一个 uvicorn**（Global Constraints）。`core/*.py`、`api/*.py`、`main.py` 都改了，且没有热重载——现存那个 :8000 实例跑的是改造前的代码，**不重启的话本 Task 所有 live 判据都在测旧二进制**，绿灯是假的。
> 2. **基线 9 / 11 / 22 不许动**：探针一律用新文件名、新账号。探针文档由 A 在判据⑤当场删（登出之后就删不掉了），`finally` 只兜异常路径；UI 阶段那两枚账号与文档另有 Step 5 的清理块。`/api/health` 是全局物理计数，它是"我没伤到既有数据"的唯一常驻证据。
>    **2026-10-07 修订**：数字换成 **活文档 4 / 父块 4 / 子块 10**（`documents` 物理行 13，含 9 行隐存），"不许动"这条纪律本身不变——尤其 `deepseek简介.docx` 与 `baseline-a/b/c.txt` 这四篇的块一律不许删。同时改判后半句：`/api/health` **不是**全局物理计数，它的 `document_count` 只数 `is_active` 的 4 篇，隐存那 9 行它照不到；所以它是"没伤到**活**数据"的常驻证据，物理行那一半要靠 Step 5 的 `total_docs` SQL 并读。
> 3. **口令与令牌不入证据**：`DEFAULT_USER_PASSWORD` 只从 `Config` 读、脚本里只出现变量名；打印判据时令牌只打前 6 位（够定位即可，全库扫描的人不该从台账里再捡一枚票）。探针账号自己造的一次性口令（`probe-pass-123` / `ui-pass-123`）不在此列——它们只对两行即删的临时账号有效，写进计划是为了让 Step 5 能重新登录回收文档。

- [ ] **Step 1: 五条门（先跑，跑完再动服务）**

```bash
cd backend && python -m pytest -q
cd backend && python -m pytest -m live -q
cd backend && python -m pytest -m migration -q
cd frontend && npm test
cd frontend && npm run build
```

预期（**只抄工具汇总行**，下面的式子是量级参考，差一两条不算错、`failed` 非 0 才算错）：

| 门 | 基线 | 预期落在 | 涨的来源 |
|---|---|---|---|
| `pytest -q` | 176 passed / 0 skipped / 1 deselected | 约 **239** passed / **0 skipped** / 1 deselected | T1 +9、T2 +28、T3 +8、T4 +10（8 离线 + 2 live，与 Task 4 Step 9 同一式子）、T5 +8 |
| `pytest -m live -q` | 14 passed | 约 **20** passed | T2 +2、T3 +2、T4 +2；T5 只改现有两条不新增 |
| `pytest -m migration -q` | 1 passed | **2** passed | T3 的向量补戳副本判据 |
| `npm test` | 84 passed / 7 文件 | 约 **112** passed / 11 文件 | T6 +12、T7 +16 |
| `npm run build` | exit 0 | exit 0 | — |

**`0 skipped` 是硬要求**：`login_token()` 在 `DEFAULT_USER_PASSWORD` 为空时会 skip 掉两条 live 测——那意味着 Step 2 之后整段验收都在瞎跑。先 `grep -c "^DEFAULT_USER_PASSWORD=" backend/.env` 确认是 1（**只数键，不打印值**）。

- [ ] **Step 2: 重启我自起的 uvicorn，让新后端代码与 lifespan 迁移上线**

先核对归属再杀——`Get-CimInstance` 看 `CommandLine`，确认那个 PID 是本项目 `main:app` 的实例才动手；不是自己起的就停下来问用户，**绝不批量杀 python/node**：

```bash
netstat -ano | grep ":8000" | grep LISTENING
```
```powershell
Get-CimInstance Win32_Process -Filter "ProcessId = <那个PID>" | Select-Object ProcessId, CommandLine
Stop-Process -Id <那个PID>
```

然后只起一份（前台或后台都行，但全程只有这一份）：

```bash
cd backend && python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

启动日志里必须出现这两件事，缺一件就是迁移没接上：

1. `迁移完成: {...}`（`core/migrations.py` 的 `logger.info`，字典里 `columns_added` 首轮含 `('documents','user_id')`、`documents_assigned` 首轮为 9；**第二次重启应当是 `columns_added: []`、`documents_assigned: 0`**——幂等的活体证据）。

> **2026-10-06 修订（上面这条按仓库实际改判）**：字典键名是 **`documents_claimed`**（`core/migrations.py` 的 `run_migrations` 返回），`documents_assigned` 这个名称在本计划里从未落地过，别按它找。另外本机的那一列与 `idx_documents_user_id` 都在 Task 1 执行期就落到真实 MySQL 了（见 Task 1 Step 9 处的修订），所以**首轮**日志就应当是 `columns_added: []`、`indexes_added: []`——这条测的"首轮非空"预期在本机不可达，幂等的活体证据改由 `documents_claimed: 9 → 0`（第一次重启归户、第二次重启零行）提供。字典共 5 个键：`columns_added` / `indexes_added` / `default_user_id` / `documents_claimed` / `vectors_stamped`。

> **2026-10-07 修订（迁移首轮已被 Task 3 消费掉：Task 8 这一格只会是 0/0，别去复现首轮）**：真实首轮发生在 **Task 3 Step 8 的手工确认**，本机日志为 `{'columns_added': [], 'indexes_added': [], 'default_user_id': 30, 'documents_claimed': 13, 'vectors_stamped': 14}`，重启一次后 `documents_claimed: 0, vectors_stamped: 0`（这条原文已直查复核：`users` 1 行 id=30、`documents` 13 行全部 `user_id=30`、`user_id IS NULL` 0 行）。所以 **Task 8 的每一次重启都只能拿到 `documents_claimed: 0` / `vectors_stamped: 0`**，那不是"迁移没跑"，而是幂等已经生效；首轮那两格的证据**引台账里 Task 3 那条**，不许为了让日志重新出现 13 而去手工 `UPDATE documents SET user_id = NULL`——那等于删改既有数据（Global Constraints 第一条）。同一个状态也是默认门里 `test_live_database.py` 那两条归户断言（含 `owned == 13`）的前置条件：**没跑过一轮启动迁移的机器上，`python -m pytest -q` 会为前置条件而红**，与新代码无关，这条要在台账里写明。
2. 没有 `Traceback`、没有 `数据库连接失败`。

```bash
curl -s http://127.0.0.1:8000/api/health
```
预期：**`document_count: 4`、`vector_counts: {"parent": 4, "child": 10}`**（与重启前逐字相同）。
> **2026-10-07 修订**：原文这里写的是 `document_count: 9`、`parent_chunk_count: 11`、`child_chunk_count: 22`——两个数字随基线重钉作废（见 Global Constraints 处的 2026-10-07 修订），两个键名则**从来就不存在**：`/api/health` 只返回 `status` / `chroma_dir` / `document_count` / `vector_counts` 四个顶层键，向量那两格在 `vector_counts` 里面、键名是 `parent` / `child`（`main.py:84-89` + `core/vector_store.py:51-55`）。照原名取值会拿到 `None`，然后误判成"基线被伤了"。

- [ ] **Step 3: HTTP + SQL 判据（`_probe_auth_isolation.py`，含 spec 7.3 的 A/B 五步）**

创建 `backend/_probe_auth_isolation.py`（**跑完在 Step 6 删掉**）：

```python
"""阶段一的活体判据：登录门、令牌生命周期、归属隔离、迁移落库。

跑法（后端必须是 Step 2 重启过的那一份）：
    cd backend && PYTHONIOENCODING=utf-8 python _probe_auth_isolation.py
每条判据打一行 PASS/FAIL，任何 FAIL 直接 assert 退出（非 0 退出码）。
数据纪律：探针文档由 A 在判据⑤里当场删（登出后删不掉），finally 只兜异常路径；账号只按自己造的两个 identifier 删。
"""
import re
import time

import httpx
from sqlalchemy import create_engine, text

from config.config import Config
from core.migrations import DEFAULT_IDENTIFIER

BASE = "http://127.0.0.1:8000"
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
STAMP = int(time.time())
A = f"probe-a-{STAMP}@local.test"
B = f"probe-b-{STAMP}@local.test"
PWD = "probe-pass-123"
DOC = f"auth-probe-{STAMP}.txt"   # 全新文件名：parent_id 全库唯一，同名重传必撞（Global Constraints）

engine = create_engine(
    f"mysql+pymysql://{Config.MYSQL_USER}:{Config.MYSQL_PASSWORD}@{Config.MYSQL_HOST}"
    f":{Config.MYSQL_PORT}/{Config.MYSQL_DATABASE}?charset=utf8mb4"
)

checked = 0


def ok(name, cond, evidence=""):
    global checked
    checked += 1
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + ("" if cond else f"  :: {evidence}"))
    assert cond, name


def sql_one(stmt):
    with engine.connect() as conn:
        return conn.execute(text(stmt)).scalar()


client = httpx.Client(base_url=BASE, timeout=60)
doc_id = None
try:
    # ---------- ① 门：8 个业务端点无凭证一律 401，health 不上门 ----------
    GATES = [
        ("POST", "/api/documents"),
        ("GET", "/api/documents"),
        ("GET", "/api/documents/chunks"),
        ("DELETE", "/api/documents/1/chunks/x_parent_0"),
        ("POST", "/api/chat"),
        ("POST", "/api/chat/stream"),
        ("GET", "/api/history/any-session"),
        ("DELETE", "/api/history/any-session"),
    ]
    for method, path in GATES:
        r = client.request(method, path)
        # 401 必须先于 422：FastAPI 在解析请求体之前求解依赖，
        # 所以"没登录"永远不该以一个"参数不合法"的形式露面
        ok(f"{method} {path} 无凭证 → 401 同一句文案",
           r.status_code == 401 and r.json()["detail"] == "未登录或登录已过期",
           f"{r.status_code} {r.text[:120]}")
    ok("GET /api/health 仍公开", client.get("/api/health").status_code == 200)

    # ---------- ② 注册与登录（含防枚举、格式、重复） ----------
    reg = client.post("/api/auth/register",
                      json={"identifier_type": "email", "identifier": A, "password": PWD})
    ok("注册 A → 201 且一次给全 token/user/session_id",
       reg.status_code == 201 and set(reg.json()) == {"token", "user", "session_id"},
       reg.text[:200])
    sid_a = reg.json()["session_id"]
    ok("后端铸造的 session_id 是 uuid4 形状",
       bool(UUID_RE.match(sid_a)), sid_a)
    ok("默认昵称从邮箱 @ 前推出（没让用户自己想名字）",
       reg.json()["user"]["nickname"] == A.split("@")[0], reg.json()["user"])

    dup = client.post("/api/auth/register",
                      json={"identifier_type": "email", "identifier": A, "password": PWD})
    ok("重复注册 → 409「该账号已注册」",
       dup.status_code == 409 and dup.json()["detail"] == "该账号已注册", dup.text[:120])
    bad = client.post("/api/auth/register",
                      json={"identifier_type": "email", "identifier": "a@b", "password": PWD})
    ok("坏邮箱 → 422（格式校验的权威在服务端）", bad.status_code == 422, bad.text[:120])

    # 大小写归一：注册用的都是小写，登录时故意打全大写，仍应命中同一个账号
    upper = client.post("/api/auth/login",
                        json={"identifier": A.upper(), "password": PWD})
    ok("邮箱大小写归一：A@… 与 a@… 是同一个账号", upper.status_code == 200, upper.text[:120])
    token_a = upper.json()["token"]
    ok("重新登录就换一枚新票、一个新对话 id",
       upper.json()["token"] != reg.json()["token"]
       and upper.json()["session_id"] != sid_a,
       "两枚票/两个 id 应当都不同")

    wrong = client.post("/api/auth/login", json={"identifier": A, "password": "wrong-pass"})
    ghost = client.post("/api/auth/login", json={"identifier": f"no-{STAMP}@local.test", "password": PWD})
    ok("密码错与账号不存在：响应逐字节相同（不向外人交代账号存在性）",
       wrong.status_code == ghost.status_code == 401 and wrong.content == ghost.content,
       f"{wrong.text[:80]} vs {ghost.text[:80]}")

    client.post("/api/auth/register", json={"identifier_type": "email", "identifier": B, "password": PWD})
    login_b = client.post("/api/auth/login", json={"identifier": B, "password": PWD})
    token_b = login_b.json()["token"]

    ha = {"Authorization": f"Bearer {token_a}"}
    hb = {"Authorization": f"Bearer {token_b}"}

    me = client.get("/api/auth/me", headers=ha)
    ok("GET /me 只回 id/identifier/identifier_type/nickname/avatar 五键",
       me.status_code == 200 and set(me.json()["user"]) ==
       {"id", "identifier", "identifier_type", "nickname", "avatar"}, me.text[:200])
    ok("坏令牌 → 401 同一句文案",
       client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"}).status_code == 401)

    # ---------- ③ spec 7.3：正证 + 反证 ----------
    up = client.post("/api/documents", files={"file": (DOC, b"auth isolation probe body\n", "text/plain")},
                     headers=ha)
    ok("A 上传探针文档成功（带 Bearer 的 multipart 这条最险的出口）",
       up.status_code in (200, 201), up.text[:200])
    doc_id = up.json()["id"]
    ok("正证：A 的列表恰 1 篇", len(client.get("/api/documents", headers=ha).json()) == 1)
    ok("反证：B 的列表 0 篇（同一个库、同一套表，看不见别人的）",
       client.get("/api/documents", headers=hb).json() == [])

    # 越权问答：拿 default 名下真实存在的 parent_id 去问，必须是 404 而不是"空召回的正常回答"
    foreign = sql_one(
        "SELECT pc.parent_id FROM parent_chunks pc JOIN documents d ON pc.document_id = d.id "
        f"WHERE d.user_id = (SELECT id FROM users WHERE identifier = '{DEFAULT_IDENTIFIER}') LIMIT 1"
    )
    over = client.post("/api/chat",
                       json={"session_id": login_b.json()["session_id"],
                             "question": "探针：这段属于谁", "parent_ids": [foreign]},
                       headers=hb)
    ok("B 用别人的 parent_id 问答 → 404（越权与不存在同一格，不付费调模型）",
       over.status_code == 404 and over.json()["detail"] == "文档块不存在或已被删除",
       f"{over.status_code} {over.text[:120]} foreign={foreign}")

    # ---------- ④ 迁移落库（SQL 直查） ----------
    ok("documents.user_id 列已在",
       sql_one("SELECT COUNT(*) FROM information_schema.COLUMNS "
               "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'documents' "
               "AND COLUMN_NAME = 'user_id'") == 1)
    ok("旧数据 13 行全归默认用户（含 9 行 is_active=0 的隐存行，不是活文档数 4）",
       sql_one("SELECT COUNT(*) FROM documents WHERE user_id = "
               f"(SELECT id FROM users WHERE identifier = '{DEFAULT_IDENTIFIER}')") == 13)
    ok("无主文档 0 篇（重启前迁移已跑过一轮）",
       sql_one("SELECT COUNT(*) FROM documents WHERE user_id IS NULL") == 0)

    # ---------- ⑤ spec 7.3 第 3 步：A 自己删探针文档 ----------
    # 必须在这里删，不能留到 finally：下面⑥一登出，ha 这枚令牌就失效了，
    # 届时 DELETE 必回 401，探针文档永远留在共享库里（基线活文档 4 篇变 5 篇）。
    dele = client.delete(f"/api/documents/{doc_id}", headers=ha)
    ok("A 删除探针文档 → 2xx", dele.status_code in (200, 204), f"{dele.status_code} {dele.text[:120]}")
    ok("删后 A 的列表回 0 篇（spec 7.3 第 3 步）",
       client.get("/api/documents", headers=ha).json() == [])
    doc_id = None  # 已删干净，finally 不再补刀

    # ---------- ⑥ 登出即吊销 ----------
    out = client.post("/api/auth/logout", headers=ha)
    ok("登出 → 204 空体", out.status_code == 204 and out.text == "", out.text[:80])
    ok("登出后同一枚令牌立刻 401（库里那行已删，可吊销不是嘴上说说）",
       client.get("/api/documents", headers=ha).status_code == 401)
finally:
    # 探针数据清干净：文档走 API（连带向量与隐存标记都由后端决定），账号走 SQL。
    # 走到这里还留着 doc_id，说明 try 在中途就炸了（上传后没删成），而 A 的令牌很可能已失效
    # ——所以重新登录取一枚新票再删，别拿手里那枚旧的碰运气。
    if doc_id is not None:
        relogin = client.post("/api/auth/login",
                              json={"identifier": A, "password": PWD}).json()
        client.delete(f"/api/documents/{doc_id}",
                      headers={"Authorization": f"Bearer {relogin['token']}"})
    with engine.begin() as conn:
        # 先回读命中数再删：只删本轮自己造的两个 identifier，别的行一概不动
        n = conn.execute(text(f"SELECT COUNT(*) FROM users WHERE identifier IN ('{A}','{B}')")).scalar()
        if n == 2:
            conn.execute(text(
                "DELETE t FROM auth_tokens t JOIN users u ON t.user_id = u.id "
                f"WHERE u.identifier IN ('{A}','{B}')"))
            conn.execute(text(f"DELETE FROM users WHERE identifier IN ('{A}','{B}')"))
        else:
            print(f"[WARN] 探针账号命中 {n} 行（预期 2），跳过删除，请人工核对")
    print(f"清理完成：探针文档 {DOC} 已删，探针账号 {A} / {B} 已删（若上面没有 WARN）")

h = client.get("/api/health").json()
ok("收尾后基线回到新基线：活文档 4 / 父块向量 4 / 子块向量 10 / documents 物理行 13",
   (h.get("document_count"), (h.get("vector_counts") or {}).get("parent"),
    (h.get("vector_counts") or {}).get("child"),
    sql_one("SELECT COUNT(*) FROM documents")) == (4, 4, 10, 13), h)
print(f"\n全部判据通过：{checked} 条")
```

```bash
cd backend && PYTHONIOENCODING=utf-8 python _probe_auth_isolation.py
```

预期：末尾打印 **`全部判据通过：31 条`**（算式：① 组 8 条 401 门 + try 内其余 22 条 + 收尾基线 1 条），并打印"清理完成"，无 `WARN`。
**台账只抄这一行**，不要按 `ok(` 出现几次自己数——① 组那一处在 `for` 里，字面 1 条实发 8 条；这正是"判据条数说错"的老口子。
`PYTHONIOENCODING=utf-8` 不能省：脚本每条判据都 print 中文，Git Bash 下 stdout 按 cp936 编码会直接把整段输出打成乱码，看起来像脚本崩了。

> **两处刻意的设计，别当成疏漏**：
> - 探针账号只删自己造的两行（`n == 2` 才删）。多一步回读是因为 SQL 删错行是不可逆的，而"命中数不对就住手"是唯一便宜的保险。
> - 越权问答用**真实存在**的 `foreign` parent_id，判据才能钉在 404。拿一个不存在的 id 打出来的 404 证明不了归属过滤那半边（它证明的是"块不存在"），这正是 Global Constraints 里"返回空不等于过滤生效"的同一个坑。

- [ ] **Step 4: 浏览器判据（前端要在跑，`npm run dev`，视口显式设置并回读）**

先起 vite（后端 :8000 已在 Step 2 起着，只有这一份），再用 browser-use 打开 `http://127.0.0.1:5173`。**每条判据都要回读 `window.innerWidth` 并写进证据**——in-app 默认视口 754px 会掉进 `max-width:768` 断点，宽屏判据在 754px 上跑出来的"绿"是窄屏的绿。

`wide` 档（显式 1280×900，回读应为 1280）：

1. **未登录整屏只有登录页**：`document.querySelector('.app-shell')` 为 `null`、`.auth-panel` 存在；页面文本不含 `session`。
2. **未登录一个业务请求都不发**：`list_network_requests` 里除静态资源与 `/api/auth/*` 外无 `/api/documents`/`/api/history` 命中（spec 5.2 的第一拍）。
3. **坏值不发请求**：账号填 `a@b`、密码 6 位，点提交 → `.picker-error` 出「邮箱格式不正确」，网络面板**没有**新的 `/api/auth/register`。
4. **注册进工作区**：用 `probe-ui-<ts>@local.test` + 口令 `ui-pass-123` 注册 → `.app-shell` 出现、`.user-rail` 存在。口令写死是有原因的：阶段一前端**没有"删整篇文档"的入口**，Step 5 要用这枚账号重新登录、经 API 回收判据 9 上传的那篇探针文档，忘了口令就只能删库行。
5. **左下角三件套**：`.rail-avatar` 文本 = 昵称首字母（默认昵称是邮箱 @ 前的 `probe-ui-<ts>`，所以应当是 `P`）；`.rail-name` 文本 = 昵称；`.rail-settings` 有 `disabled` 且 `title` 原文是「设置项将在下一阶段开放」（用 `evaluate` 读属性，别只看外观）。
6. **session_id 从界面上消失**：`document.querySelectorAll('.session-debug, .session-value, .session-chip').length === 0`，且 `document.body.innerText` **不含** `localStorage.getItem('session_id')` 的值——这条是需求 3 的正身，只查 class 会漏掉"把 id 印在别处"。
7. **localStorage 三键的形状**：`auth_token` 长 43、`session_id` 是 uuid4、且 `session_id` **等于**注册响应里那个（不是本地自己造的）——需求 2 的活体证据。
8. **刷新不丢登录、不换对话**：`navigate` 重载同一 URL → 仍在 `.app-shell`（这条走的是 `/api/auth/me`，网络面板里应有且只有一枚 200）、`session_id` 值不变。
9. **上传探针文档**（新文件名 `ui-probe-<ts>.txt`）→ 面板文档数 1、`.metric` 显示 1。
10. **对话能打**：一个块都不选，发一句「你好」→ StatusBar 显示「💬 普通对话模式」、答案逐字上屏、`.error-banner` 不出现。（阶段一的边界：**登录了就能问**，走 `.env` 那把平台 key，别在这里找 409——409 是阶段二的验收点。）
11. **清空即换 id**（spec 5.4 的判据）：记下 `session_id` 值 → 点「🗑️ 清空对话」→ `browser-use` 的 `click` 会自动 accept 原生 `confirm`（已知怪癖，不必与它搏斗）→ 新的 `localStorage.session_id` **与清空前不同**，且消息区清空。
12. **登出干净**：点「退出登录」→ 回到 `.auth-panel`；`localStorage` 里 `auth_token` 与 `session_id` 两键都不在；`.side-panel` 与 `.chat-input` 节点数 0；**网络面板无 401**（登出后不该再打任何业务请求）。
13. **换账号反证**：用 `probe-ui2-<ts>@local.test` + 同一个口令 `ui-pass-123` 登录（先登出判据 4 那个账号）→ 文档数 0 篇、消息区为空（看不见上一个账号的探针文档）。两个账号都落在 `probe-ui%` 前缀下，Step 5 的清理才一条 LIKE 扫得完。
14. **零控制台错误**（`list_console_messages` 只允许 favicon 一类无害项）。

`narrow` 档（显式 375×800，回读 375）：

15. 未登录时 `.auth-panel` 的 `getBoundingClientRect()` 在 `[0, 375]` 内不越界，`width` = `round(375×0.92)`。
16. 登录后 `.app-shell` 仍是两轨（`grid-template-rows` 未多出第三轨，`.chat-messages` 的 `clientHeight <= scrollHeight` 且有界滚动容器特征照旧）——**这条守的是 L-1/L-2 那块根治**：新 DOM 若混进 grid item 就会在这里现原形。
17. `.user-rail` 在窄屏随侧栏浮层出现（先点「展开文档面板」）：`flex-wrap` 生效、`⚙` 与「退出登录」两按钮的 `right` 都在面板 `rect` 内不越界。
18. 窄屏零控制台错误。

> **已知观感（写进台账，不改代码）**：窄屏下头像/昵称/退出登录在侧栏浮层里，要先点「展开文档面板」才够得着。这是 spec 5.4"原位置"那句话的直接后果——`.user-rail` 跟着 `.session-debug` 搬，而 `≤768` 的侧栏本就是浮层。要挪进聊天栏底部属于界面改版，与阶段二 `SettingsModal` 一起谈更划算。

**尺寸/布局类判据（5、15、16、17）若 browser-use 的默认视口不好显式钉**，按项目记忆改用 Edge headless 探针：`cd frontend && npm install --no-save puppeteer-core`，`executablePath` 指本机 Edge，`page.setViewport({width, height})` 后**回读 `innerWidth` 再断言**，`browser.close()`（不是 `kill()`——`kill()` 会连 localStorage 一起丢，那会毁掉 7/8/11 三条判据的取证）。**验证完 `npm prune`，`package.json` / `package-lock.json` 必须零 diff。**

- [ ] **Step 5: 清场与基线核对**

**顺序不能反：先清场，再对基线。** `/api/health` 的 `document_count` 数的是活文档、`vector_counts` 数的是物理向量行，判据 9 那篇 UI 探针文档还在库里时打它，只会拿到一个吓人的 `document_count: 5` / `vector_counts.parent: 5` / `vector_counts.child` 大于 10（新基线是 **4 / 4 / 10**），然后怀疑错方向。

```bash
cd frontend && npm prune
cd frontend && npm ls --depth=0 | grep -c extraneous || true
git status --short          # 只应看到 ledger 那一条（未跟踪），package.json / lock 无 diff
```
然后手工删除两个临时件：`rm backend/_probe_auth_isolation.py frontend/probe-auth-rail.mjs`（**自己本轮造的东西，删之前确认已被判据引用过、结论已进台账**）。

**UI 阶段的残留必须先回收，否则基线必挂**。判据 9 经界面上传的 `ui-probe-<ts>.txt` 是**真文档**（真向量、真父子块），阶段一的界面里**没有"删整篇文档"的入口**（只有块级删除），所以只能用那两枚账号的口令重新登录、经 API 删。

```bash
cd backend && PYTHONIOENCODING=utf-8 python - <<'PY'
import httpx
from sqlalchemy import create_engine, text
from config.config import Config

# 只清 probe-ui% 前缀的账号（判据 4 / 13 造的），identifier 由 Step 4 现场记进台账
ids = ["probe-ui-<ts>@local.test", "probe-ui2-<ts>@local.test"]
PWD = "ui-pass-123"

with httpx.Client(base_url="http://127.0.0.1:8000", timeout=60) as c:
    for identifier in ids:
        r = c.post("/api/auth/login", json={"identifier": identifier, "password": PWD})
        if r.status_code != 200:
            print("skip login", identifier, r.status_code)
            continue
        h = {"Authorization": f"Bearer {r.json()['token']}"}
        for d in c.get("/api/documents", headers=h).json():
            print("delete doc", d["id"], d["filename"])
            print(" ->", c.delete(f"/api/documents/{d['id']}", headers=h).status_code)
        c.post("/api/auth/logout", headers=h)

engine = create_engine(
    f"mysql+pymysql://{Config.MYSQL_USER}:{Config.MYSQL_PASSWORD}@{Config.MYSQL_HOST}"
    f":{Config.MYSQL_PORT}/{Config.MYSQL_DATABASE}?charset=utf8mb4")
with engine.begin() as conn:
    rows = conn.execute(text(
        "SELECT id, identifier FROM users WHERE identifier LIKE 'probe-ui%@local.test'")).all()
    print("probe-ui rows to remove:", [r[1] for r in rows])
    for uid, _ in rows:
        conn.execute(text("DELETE FROM auth_tokens WHERE user_id = :u"), {"u": uid})
        conn.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})
PY
```

> 这段是**唯一一处允许写 SQL DELETE 的地方**（除 Step 3 探针脚本自己的 finally），且删的键只有 `users.id` / `auth_tokens.user_id` 两表，条件钉在 `LIKE 'probe-ui%@local.test'`。
> 先把要删的 `identifier` 打印出来再看一眼，然后才让它删——上一轮"回读命中数才动手"的规矩在这里同样适用。
> 文档必须先删、账号才能删：反过来的话那几行 `documents` 会留下指向已消失用户的 `user_id`，`unowned` 仍是 0（列非空），但谁都再也看不见它们，`/api/health` 的计数还照算——那是最难查的一种脏。

库侧收尾自查（**清场完成后**才跑；SQL 只读 + 一次 health）：

```bash
curl -s http://127.0.0.1:8000/api/health
cd backend && PYTHONIOENCODING=utf-8 python -c "
from sqlalchemy import create_engine, text
from config.config import Config
e = create_engine(f'mysql+pymysql://{Config.MYSQL_USER}:{Config.MYSQL_PASSWORD}@{Config.MYSQL_HOST}:{Config.MYSQL_PORT}/{Config.MYSQL_DATABASE}?charset=utf8mb4')
conn = e.connect()
print('active_docs', conn.execute(text('SELECT COUNT(*) FROM documents WHERE is_active=1')).scalar())
print('total_docs', conn.execute(text('SELECT COUNT(*) FROM documents')).scalar())
print('unowned', conn.execute(text('SELECT COUNT(*) FROM documents WHERE user_id IS NULL')).scalar())
print('probe_users_left', conn.execute(text(\"SELECT COUNT(*) FROM users WHERE identifier LIKE 'probe-%@local.test'\")).scalar())
print('total_users', conn.execute(text('SELECT COUNT(*) FROM users')).scalar())
"
```

> 标签一律 ASCII：`python -c "…"` 的字符串要经过 Git Bash 的参数传递，中文会被按 cp936 转一遍再交给解释器，打出来是乱码。
> 这里的**五个**词就是判据本身，乱码等于自断证据。
预期：`/api/health` **`document_count: 4` + `vector_counts: {"parent": 4, "child": 10}`**（与 Step 2 重启后逐字相同）、`active_docs` **4**、`total_docs` **13**、`unowned` **0**、`probe_users_left` **0**、`total_users` **1**（只剩默认用户）。
> **2026-10-07 修订（这一格的数字与那条 `total_docs`）**：原文写的是 health **9 / 11 / 22** 与 `active_docs` **9**，随基线重钉作废（见 Global Constraints 处的修订），而且 health 那三个键名原文就不存在。`total_docs` 这一行是本轮**新增**的第五个词：`document_count` / `active_docs` 数的是活文档 4，隐存那 9 行（`is_active=0`、块数 0）在界面上永远看不见，却同样要被迁移归户——只看 4 就无法证明"13 行都归了户、也没多出行"。所以 **4 与 13 必须并读**：`total_docs - active_docs == 9` 是这次重钉后共享库的形状，任何一边变大都要在台账里解释清楚是哪一篇。若 `total_users` 大于 1，把多出来那几行的 `identifier` 记进台账再决定删不删——**不要按 id 猜**。判据 4/13 那两个 UI 账号要靠上面那段清理块（先经 API 删文档、再 SQL 删账号）才算真清干净；阶段一**没有"删除账号"的端点**，也**没有"删整篇文档"的界面入口**，这两条都是设计选择，不是漏。

`chat_history` 这一轮**预期不留残留**：判据 11「清空即换 id」排在判据 10 之后，`DELETE /api/history/{旧 session}` 会把「你好」那一轮一起收走。若中途某条判据失败、留下一个没人认领的探针 session（自己造的 uuid，与既有会话不撞），记下它的 `session_id` 前 8 位进台账即可，**不必手工删行**——它是"当时跑到哪一步"的证据，删了反而说不清。

- [ ] **Step 6: 写 ledger 并提交**

创建 `.superpowers/sdd/2026-10-06-user-auth-isolation-phase-1/progress.md`（这个目录被忽略，提交要 `git add -f`）。按本仓既有台账的口径写，**必须有实数、必须有"当时怎么红的"**：

```markdown
# SDD ledger — plan: docs/superpowers/plans/2026-10-06-user-auth-isolation-phase-1.md

## 阶段一：用户注册登录 + 文档按用户隔离（2026-10-06）

- 提交清单：Task 1..7 各一条（7 个 short SHA 逐个列出，每条后面跟上当时的门禁实数），本条 ledger 是第 8 条。
- 五条门的实数：`pytest -q` = **N passed / 0 skipped / 1 deselected**（基线 176；**2026-10-07 无服务实跑 224 passed / 2 skipped / 1 deselected**，Task 8 这一轮服务在跑，那 2 条 `test_live_stream` 应当转为 pass ⇒ 预期 **226 / 0 / 1**）；
  `-m live` = **N passed**（基线 14）；`-m migration` = **2 passed**（基线 1）；
  `npm test` = **N passed / 11 文件**（基线 84/7）；`npm run build` exit 0（js/css 字节数照抄一轮）。
- 迁移：**首轮证据在 Task 3**（`documents_claimed: 13, vectors_stamped: 14`，日志原文见 Task 3 那一节）；Task 8 的重启只能拿到 `documents_claimed: 0, vectors_stamped: 0`，**把 Task 8 这一轮的原始日志贴一行并注明"首轮已被 Task 3 消费"**，不要为复现首轮去清 `user_id`。
  > 2026-10-06 修订：键名按仓库实为 `documents_claimed`（外加 `indexes_added`，共 5 键）；本机首轮 `columns_added: []`、`indexes_added: []`（列与索引在 Task 1 就落好了）。**照实抄日志**，不要为了对上原文去改历史——台账的价值在于它是量测，不是因为它对齐了计划。
  > 2026-10-07 修订：原文这两格写的是 `documents_assigned: 9`。键名按上面那条勘误，**数字**随基线重钉改成 **13**（= 4 活 + 9 隐存的物理行），`vectors_stamped` 的本机实数预期是 **14**（4 父块向量 + 10 子块向量，直查得来）。首轮就报 `vectors_stamped: 0` 说明 Step 3 那条顺序修订没落地，按失败处理。
- HTTP/SQL 判据：**照抄脚本末尾那一行 `全部判据通过：N 条`**（计划写就时 N = 31：① 组 for 循环实发 8 条 + try 内其余 22 条 + 收尾基线 1 条），
  逐档列关键条（401 先于 422、防枚举逐字节相同、A 1 篇 / B 0 篇、越权 404、default 拥有 13 行、A 删后回 0 篇、登出立刻 401）。
- 浏览器判据：**wide N/N、narrow N/N**（条数只抄探针输出的汇总行，不许凭印象——
  上一轮就发生过把 16/16 报成 13/13 的事）。视口回读值一并记（1280 / 375）。
- UI 阶段清场：两个 `probe-ui%` 账号已 SQL 删除、`ui-probe-<ts>.txt` 已经 API 删除，
  收尾自查五值照抄（`active_docs` / `total_docs` / `unowned` / `probe_users_left` / `total_users` = 4 / 13 / 0 / 0 / 1）。
- 红过的地方与为什么（这一节最值钱，别写成"一次通过"）：`make_client` 少覆盖一格导致整文件 500、
  `DetachedInstanceError` 那次的改判、`ensure_columns` 在 sqlite 上不可测（MEDIUMTEXT）改 inspect 表形、
  ……逐条写"症状 → 机制 → 判据怎么改"。
- 已知遗留（spec 7.4 三条 + 本轮新增四条）：跨用户同名上传撞 parent_id、改密码不吊销其它令牌、
  `identifier` 单列不做"同邮箱/同手机号是同一人"的关联识别；
  无找回密码、api_key 明文（阶段二才引入这一列）、窄屏 `.user-rail` 在侧栏浮层里、
  阶段一既没有"删除账号"的端点也没有"删整篇文档"的界面入口（Step 5 清场因此要走 API + SQL 两段）。
- 阶段二入口（别在阶段一里顺手做）：`users.api_key/base_url` + `user_models`、`llm_factory` 与两处单例、
  压缩器搬家、`chat_history.user_id` 与读侧 `$and`、409 门禁、SettingsModal、输入框两段式 + 模型下拉。
```

```bash
cd D:/知识库平台-前后端分离 && git add -f .superpowers/sdd/2026-10-06-user-auth-isolation-phase-1/progress.md
git status --short
git -c user.name="31439" -c user.email="31439@local" commit -m "docs(ledger): 用户认证与数据隔离阶段一落地——五条门实数、迁移两轮幂等、31 条 HTTP/SQL + 18 条浏览器判据"
```

- [ ] **Step 7: 交付给用户验收（不要自己宣布完成）**

台账提交后，把这三件事如实报给用户，等他/她决定下一步：

1. **阶段一做到了什么**（对应七条需求）：① 注册登录（只校验格式）✅、② `session_id` 由后端在登录时铸造、重新登录换新、刷新不换 ✅、③ 界面上 session_id 消失、左下角头像+昵称+⚙（**⚙ 是禁用占位**）✅、⑤ 未登录整屏只有登录页、文档按用户隔离 ✅、⑥⑦ **还没做**——api_key/路由配置与模型下拉属阶段二。
2. **两条必须点破的边界**（spec 8 的"能力边界"）：阶段一**任何登录用户都能对话**，走的是 `.env` 里那把平台 key，所以此时**不该**出现 409；额度是大家共用的一把。以及"改密码不影响其它已发令牌"是本轮遗留，不是 bug。
3. **执行方式的岔口**：如果接下来做阶段二，建议同一套 SDD 流程（子代理实施 + 独立评审）；如果先要一段"只有阶段一"的稳定期，那就停在这里，回滚只需退到本 Task 之前的提交——新列、新表、向量的 `user_id` 键都不需要动（spec 6 节的"回滚是真回滚"）。

---

## Self-Review 结论（写完计划后按 spec 逐条回扫）

- **spec 覆盖（第 8 节"阶段一"那一行的每一项都有 Task 认领）**：两张表 + `core/security.py` → Task 1；`api/auth.py` 四端点 + `deps.get_current_user` + `AuthError`→401 + CORS 加 `PUT` → Task 2；迁移 1/2/3/5/6（只 `documents.user_id` + 旧向量补戳）→ Task 3；8 个业务端点加登录门与 documents 侧归属过滤、向量写侧补 `user_id` → Task 4（documents/history 侧）+ Task 5（chat/history 侧 + 问答白名单）；前端 `useAuth` + `api/auth.js` + 三条出口令牌注入 → Task 6；`AuthPanel` + `.user-rail` + 删 `.session-debug`/`.session-chip` + "清空即换 id"留在 `handleClear` → Task 7；7.1 表里那 76 条端点测的 `make_client` 改造与 live 组的 `user_id`/令牌改造 → Task 4/5 各自的第一步；第 7 节验收 → Task 8。
- **阶段二没被顺手做掉**：`chat_history.user_id`、读侧 `$and` 过滤、`.env` 三键抄送默认用户、`llm_factory` 与两处单例拆除、压缩器搬家、`test_rag_system.py` 那 21 条、坑 9 的两条构造点判据、`SettingsModal`、模型下拉与 409 门禁——**本计划一个都不碰**，Task 8 Step 7 的第 3 项把它作为岔口交回用户。
- **占位符**：无 TBD/TODO；每个 Step 都给了可直接粘贴的实现或明确的命令 + 预期输出。
- **实数更正（计划期核过，与 spec 原文不同处以计划为准）**：① `test_live_stream.py` 真 HTTP 流式测是 **2 条**（spec 7.1 勘误块写 3 条）→ Task 5 按 2 条 / 6 处调用点落文；② 阶段一门禁的条数式子只给量级，**报数以汇总行为准**（Task 8 Step 1 那张表就是按这条口径写的）。
- **类型/命名一致性**：`user_id`（关键字参数，keyword-only 必填）与 `user.id`（ORM）不混用；`owned_parent_ids(parent_ids, *, user_id)`（Task 4）→ `_require_owned_parents(db, parent_ids, user)`（Task 5）；前端 `parent_ids`（请求体）/`parentId`（本地 id 集合）两套命名各守其位；`AuthPanel` 的 payload 用 camelCase（`identifierType`），`api/auth.js` 是唯一翻成 snake_case 的地方；`useSession` 的 `setSession`/`resetSession`/`clearSession` 三个动词各自对应 spec 5.3 的三句话，别互换。
- **最容易走偏的一处，再钉一遍**：Task 7 的 `sessionId` 一旦留在 `useSession()` 函数作用域内，登录时后端铸造的 id 就写不进界面用的那个 ref——需求 2 会静默失效。**Step 1 的第 5 条测（两次调用返回同一个 ref）就是这一处的守卫**，别为了少一条测把它删掉。
