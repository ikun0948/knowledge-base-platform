# 用户认证与数据隔离 · 阶段二 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把大模型出口交到用户手上——每人自带 api_key/路由/模型名单，历史按用户读写，未配置的人点发送拿到 409，界面上有设置弹窗与模型下拉。

**Architecture:** 后端新增 `core/llm_factory.py` 作为全项目唯一构造 `ChatOpenAI` 的地方；`RAGSystem` 的四个链方法各多**一个** `RunContext` 参数（key + model + user_id），两处进程级 LLM 单例随之拆除；压缩器从 `VectorStore` 搬进 `RAGSystem` 的请求内构造。前端新增 `SettingsModal.vue`、`ChatInput.vue` 改两段式，`client.js` 的错误对象带上 `status`，401/409 两条路径各有归宿。

**Tech Stack:** FastAPI + SQLAlchemy(MySQL) + ChromaDB + langchain-openai/langchain-classic；Vue 3 + Vite + Vitest(jsdom) + @vue/test-utils。零新依赖。

**Spec:** `docs/superpowers/specs/2026-10-06-user-auth-isolation-design.md`（已批准；阶段一 8-Task 已收口，终态 HEAD `ccf97dc`）。执行时计划与 spec 一起读。

---

## 0. 计划编号修正表（spec 里的数字在此更正，实施时以本表为准）

这些是 2026-10-07 在 `ccf97dc` 上实测出来的，不是推测。**报数只抄当轮汇总行**，别把本表的预估当实测交给台账。

| spec 原话 | 实测真相 |
|---|---|
| 7.1 基线「后端 `pytest -q` 176 passed / 1 deselected」 | 阶段一终态（台账 `4738fd3`/`ccf97dc` 重跑原文）= **257 passed / 2 skipped / 2 deselected / 0 failed**。176 是认证改造前的数，已死。配套口径：`-m live` 服务未起 **18 passed / 2 skipped**，服务起着 **20 passed / 241 deselected / 0 skipped**；`-m migration` **2 passed** |
| 7.1「走 TestClient 的端点测合计 76（chat 29 / documents 20 / history 14 / chunk_search 9 / error_model 4）」 | 实数是 **101**：`test_api_chat` **30**、`test_api_documents` **34**、`test_api_history` 14 ✅、`test_chunk_search` **15**、`test_error_model` **8** |
| 7.1 `test_rag_system.py` 21 | **21** ✅ |
| 7.1 `test_vector_store.py` 9 | **10** |
| 7.1 `test_live_stream.py` 3 | **2** |
| 7.1「前端 84 passed / 7 文件」 | **117 passed / 13 文件** |
| 7.1「`make_client` 定义 5 处」 | **6 处**（阶段一 Task 5 又加了一处） |
| 2.2/357「`RAGSystem` 四个方法 + 34 处调用点」 | 34 属实但**口径是测试触点**：21 处测试调用 + 9 处桩定义 + 4 处 `super()`；生产调用点只有 **4 处**（都在 `api/chat.py`）。另有 `save_chat_history` 生产调用点 **6 处**（全在 `rag_system.py`），spec 未计 |
| 3.6「CORS `allow_methods` 必须加 `PUT`」 | **已完成**（`main.py:69` 现有 `["GET","POST","PUT","DELETE"]`），阶段一 Task 2 顺手做的，本计划不再动 |
| 3.5「`STATUS_BY_ERROR` 从 4 项扩到 6 项」 | 现在已是 **5 项**（`AuthError` 已在表内，`main.py:30-36`）⇒ 阶段二只加 `NotConfiguredError` 一格：**5 → 6** |
| 2.3「`app.state` 上 5 个 lifespan 单例（`main.py:42-47`）」 | 实际在 **`main.py:46-57`**，那段行号漏了 `app.state.rag_system = RAGSystem(...)`（`:57`） |
| 5.8「新 token 进 `variables.css:43` 之后」 | `:43` 是 `}`。最后一个 token 是 `:42 --side-width` ⇒ 新 token 插在 **`:42` 与 `:43` 之间** |
| 7.1「`test_live_database.py` 的 32 处 DB 调用点要带 `user_id`」 | 该文件现有 **65** 处 `user_id=`（阶段一已接上大部分），阶段二的真改动是历史那三组方法签名 |
| 7.1「坑 9 的两条构造点判据改写为钉 `llm_factory`」 | 这两条现在是 `test_rag_system.py:357::test_answer_llm_takes_the_model_name_from_config` 与 `test_vector_store.py:144::test_compressor_llm_takes_the_model_name_from_config`，Task 4 改写、Task 5 才让生产路径真的改读 factory |
| （spec 未记） | `test_migrations.py:243` 逐字钉住 `MIGRATED_COLUMNS == [("documents","user_id","INTEGER")]` ⇒ **任何加列都必须同步改这条 pin**（Task 1、Task 6 各一次） |
| （spec 未记） | `test_api_auth.py:76-77` 逐字钉住 `user` 的五键字典 ⇒ `UserOut` 加字段会让它红（Task 2）；同文件 `FakeAuthDB` 造的行没有 `api_key/base_url` 属性，也得跟着补（Task 2） |
| （spec 未记） | `frontend/tests/ChatInput.test.js` **存在**（5 条）且四处用 `find('button')`/`findAll('button')`（`:15`、`:18`、`:43-45`、`:51`）⇒ 两段式布局必须先把这四处钉成类选择器（Task 10） |

## 0.1 五条阶段一顺延 advisory 的归属（用户已选「并入对应 Task 顺手做」）

| advisory | 落在 | 动作 |
|---|---|---|
| ① 迁移补戳崩溃窗口（`migrations.py:184-189`） | **Task 3** | 无主清单的判据从「文档 `user_id IS NULL`」换成「文档已有主人 + Chroma 里还没有戳」，让下次开机自愈 |
| ② 运行中 401 只弹横幅、不自动登出（`client.js:55`） | **Task 8** | `client.js` 认到 401 就通知一个单槽回调（`setUnauthorizedHandler`），**注册点在 `App.vue` 的 setup**（handler 要写的那批 ref 全在 App 层）；`useAuth` 这边只把 `clearAuth` 提到模块级好被外面拿到 |
| ③ hydrate 失败路径没有清 `selected_parent_ids` 的判据 | **Task 11** | `useChunkSelection.test.js` 加一条**钉档**：同一个 `it()` 里同时钉"hydrate 失败时本地池原样留着"与"`clearSelection()` 会写回 `[]`"——后者是登出清理的唯一动作，今天承重，别删 |
| ④ live 测登录不留登出，`auth_tokens` 无界增长（`test_live_stream.py:34-50`） | **Task 7** | 这两条本来要为「配 key」重写，顺手在 `finally` 里登出 |
| ⑤ `test_observability.py:16-17` 扫描清单写死 | **Task 12** | 两份写死清单（`SCANNED` + `SCANNED_DIRS`）整体换成 `rglob` 自动发现 + 排除集，并加一条"扫到了谁"的 must-cover 判据与 `>= 22` 下界防空集假绿 |

---

## 1. Global Constraints（每个 Task 的要求隐含包含本节）

- **中文文案**：所有面向用户的 `detail` 是中文；原始异常文本只进 `logger`，永不进响应体（spec 八节）。
- **零新依赖**：不装 bcrypt、不引 Pinia、不引 vue-router、不加 `<style>` 块（组件样式只进 `layout.css`）。
- **api_key 三条铁律**：明文入 MySQL（决策已记）、**任何端点都不返回原文**（只回 `api_key_masked`）、**任何日志与断言消息都不打印**（`test_observability.py` 的 print 门禁 + 人工核对）。
- **进程纪律**（本机环境）：同一时刻只跑一个 `uvicorn`；`pytest` 只跑一个进程（`backend/data/chroma_db` 是单实例锁）；离线门禁用 `python -m pytest -q`（`pytest.ini` 的 `addopts = -m "not migration"` 生效），需要显式选组时写 `-m "not live and not migration"`；**非必要不跑 `-m migration`**。
- **样式纪律**：G-4 = `variables.css` 之外颜色字面量 0 命中；≤768 断点不许塌行（`.chat-controls`、`.user-rail` 都要有窄屏分支）。
- **git 纪律**：不改 `user.name/user.email`，提交一律 `git -c user.name="31439" -c user.email="31439@local" commit -F <utf8文件>`；不 amend、不 push（无远端）、不 `--no-verify`；中文提交信息必须走 `-F` 文件（cp936），不走 shell 参数。
- **测试纪律**：每条判据先跑 RED 再实现；变异自证（把生产语句改坏必须红）在台账里记当轮实数；`wrapper.vm` 是断"卸载后看不见的状态"的唯一通道。
- **数字纪律**：计划里所有条数都是 2026-10-07 在 `ccf97dc` 上的实测或明确标注的「约」；台账只抄当轮汇总行。

## 2. 文件结构（谁创建 / 谁负责）

**后端**

| 文件 | 阶段二职责 | Task |
|---|---|---|
| `core/database.py` | `User` 加两列、新增 `UserModel` 表、七个账号设置类 DB 方法、历史三方法带 `user_id` | 1、6 |
| `core/migrations.py` | `MIGRATED_COLUMNS/INDEXES` 扩充、步骤 4（抄三键）、补戳窗口自愈、历史归户 | 1、3、6 |
| `core/llm_factory.py` | **新建**：`LLMConfig`/`RunContext`/`require_llm_config`/`build_llm`/`build_compressor`——全项目唯一构造 `ChatOpenAI` 的地方 | 4 |
| `core/rag_system.py` | 删 `self.llm` 与 `config` 形参、四个链方法各多一个 `ctx`、压缩器改为请求内构造 | 5、6 |
| `core/vector_store.py` | 删 `self.llm`/`self.compressor`、`create_retriever` 读侧 `$and` | 5 |
| `api/auth.py` | 六个设置类端点 + `_user_out` 投影 | 2 |
| `api/chat.py` | `_llm_context` 门禁（409）、`model_name` 解析、四处 rag 调用补 `ctx` | 7 |
| `api/history.py` | 两枚端点真的按 `user.id` 过滤 | 6 |
| `schemas/auth.py` | `UserOut` 加五键、`mask_api_key`、四个入参模型、`MODEL_NOT_IN_LIST`；Task 7 再补 `EMPTY_MODEL_LIST` | 2、7 |
| `schemas/chat.py` | `ChatRequest.model_name` | 7 |
| `exceptions.py` / `main.py` | `NotConfiguredError` / `STATUS_BY_ERROR` 5→6 / `run_migrations` 与 `RAGSystem` 构造点 | 3、5、7 |
| `tests/fakes.py` | `FakeRAG`/`FakeUser`/`FakeOwnedParentsDB` 跟签名 | 5、6、7 |

**前端**

| 文件 | 阶段二职责 | Task |
|---|---|---|
| `api/client.js` | `ApiError(msg, status)` + 401 回调 | 8 |
| `api/auth.js` | 六个 PUT/POST/DELETE 薄封装 | 8 |
| `api/documents.js` | 三处 `new Error` 改走 `httpError`（XHR 那条出口的 401 也要回调） | 8 |
| `composables/useAuth.js` | `clearAuth` 从函数体提到模块级、新增 `patchMe(nextUser)`（**401 回调不在这里注册**，见下一行 App.vue 的裁定） | 8 |
| `composables/useChat.js` | `send` 载荷加 `model_name` | 10 |
| `components/SettingsModal.vue` | **新建**：昵称/头像、改密码、api_key/路由、模型名单增删设默认 | 9 |
| `components/ChatInput.vue` | 两段式 + `.chat-controls` + `.model-select` + `allowSend` 门禁 | 10、11 |
| `App.vue` | `resetWorkspace()` 抽取 + 401 处理器注册点、`⚙` 解禁、弹窗挂载、头像预设、`modelOverride`/`currentModel` 接线、未配 key 横幅 | 8、9、10、11 |
| `styles/variables.css` / `layout.css` | 新 token 与三组样式 + ≤768 分支 | 9、10、11 |

## Task 1: `users.api_key` / `users.base_url` 两列 + `user_models` 表 + 七个 DB 方法

**Files:**
- Modify: `backend/core/database.py`（`User` 类 `:114-124`、`AuthToken` 之后 `:139`、`delete_token` 之后 `:586`、import 行 `:2`）
- Modify: `backend/core/migrations.py:30`（`MIGRATED_COLUMNS`）
- Test: `backend/tests/test_user_models_db.py`（新建，离线结构判据）
- Test: `backend/tests/test_live_database.py`（live 行为判据 + `_drop_probe_account:380-395` 补一张表）
- Test: `backend/tests/test_migrations.py:243`（`MIGRATED_COLUMNS` 那条逐字 pin 要跟着改）

**Interfaces:**
- Consumes: 无（本 Task 是阶段二第一块地基）
- Produces: `User.api_key`/`User.base_url`（可空 String）、`UserModel(user_id, name, is_default)`、`DatabaseManager.update_user_profile/update_user_password/update_user_llm/list_user_models/add_user_model/delete_user_model/set_default_user_model`。Task 2 的六个端点、Task 7 的 `_llm_context` 全吃这套。

- [ ] **Step 1: 写离线结构判据（先 RED）**

新建 `backend/tests/test_user_models_db.py`：

```python
"""阶段二两张账号侧结构的离线钉。

真库上的读写归 test_live_database.py（要 MySQL），这里只钉"形状本身"：
列可不可空、name 的长度上界、unique 键在不在——这三个都是**建表之后改不动**的事实，
错了就得删表重来，所以值得一条不连库的判据。
`Base.metadata` 是纯声明，导入它不开连接。
"""
from sqlalchemy import UniqueConstraint

from core.database import Base, User, UserModel


def test_user_llm_columns_exist_and_are_nullable():
    cols = Base.metadata.tables["users"].columns
    assert {"api_key", "base_url"} <= set(cols.keys())
    # 可空是硬要求：老库里已有账号还没配 key，NOT NULL 会让 ALTER 当场失败
    assert cols["api_key"].nullable is True and cols["base_url"].nullable is True


def test_user_model_table_shape():
    table = Base.metadata.tables["user_models"]
    assert table.columns["name"].type.length == 100      # 对齐 ChatRequest.model_name 的 1..100
    assert table.columns["is_default"].nullable is False  # 读侧 next(... if is_default) 不吃 None
    assert any(isinstance(c, UniqueConstraint) for c in table.constraints), \
        "没有 unique(user_id, name) 就能重复添加同一个模型，端点的 409 无从谈起"


def test_column_names_match_what_endpoints_read():
    # 名字是契约：拼错的列名在 MySQL 上是 1054 未知列，在 ORM 上是 AttributeError
    assert User.__tablename__ == "users"
    assert UserModel.__tablename__ == "user_models"
    assert [c.name for c in UserModel.__table__.primary_key.columns] == ["id"]
```

- [ ] **Step 2: 跑一次确认 RED**

Run: `cd backend && python -m pytest tests/test_user_models_db.py -q`
Expected: FAIL —`ImportError: cannot import name 'UserModel'`（先于任何断言发生，所以这一步不需要看断言文本）

- [ ] **Step 3: 声明两列与一张表**

`backend/core/database.py:2` 的 import 行补两个名字：

```python
from sqlalchemy import create_engine, func, Column, Integer, String, DateTime, Boolean, ForeignKey, Index, Text, UniqueConstraint
```

`User` 类（`:114-124`）在 `password_hash` 与 `created_at` 之间插两列：

```python
    password_hash = Column(String(255), nullable=False)
    # 每用户的大模型出口（spec 2.1）。明文入库是 spec 第 4 节记过的权衡：对称加密的主密钥
    # 只能躺在同一台机器的 .env 里，读盘的人两样都拿得到，等于只防"单独拖走数据库"。
    # 可空 = "还没配置"，它是 409 门禁的判据，不是缺省值。
    api_key = Column(String(255))
    base_url = Column(String(500))
    created_at = Column(DateTime, default=datetime.now)
```

`AuthToken` 之后（`:139` 后）新增：

```python
# 用户自己维护的模型名单（决策 6：不去调远端 GET /models）。
# 单独一张表而不是逗号串：要做"增 / 删 / 设默认"三种行级操作，整串重写会在并发下互相覆盖。
class UserModel(Base):
    __tablename__ = 'user_models'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    # 长度上界 100 与 ChatRequest.model_name、ParentChunk.parent_id 同源：
    # 三个地方三种上界，早晚有一个会把用户的输入切掉半截。
    name = Column(String(100), nullable=False)
    is_default = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint('user_id', 'name', name='uq_user_models_user_name'),
        Index('idx_user_models_user_id', 'user_id'),
    )
```

`MIGRATED_COLUMNS`（`core/migrations.py:30`）扩成三行：

```python
MIGRATED_COLUMNS = [
    ("documents", "user_id", "INTEGER"),
    ("users", "api_key", "VARCHAR(255)"),
    ("users", "base_url", "VARCHAR(500)"),
]
```

- [ ] **Step 4: 七个 DB 方法**

`backend/core/database.py` 顶部补 `from sqlalchemy.exc import IntegrityError`，在 `delete_token`（`:574-586`）之后追加：

```python
    # ---------- 账号设置与模型名单（spec 2.1/3.1 的阶段二部分）----------

    def update_user_profile(self, user_id, nickname=None, avatar=None) -> int:
        """只改传了的那一格，返回受影响行数。

        整行 UPDATE 而不是"读出来再写回去"：nickname 与 avatar 各自独立，
        读改写会让两个并发请求互相覆盖掉对方那一格。
        """
        fields = {}
        if nickname is not None:
            fields["nickname"] = nickname
        if avatar is not None:
            fields["avatar"] = avatar
        if not fields:
            return 0
        return self._update_user(User, user_id, fields)

    def update_user_password(self, user_id, password_hash) -> int:
        return self._update_user(User, user_id, {"password_hash": password_hash})

    def update_user_llm(self, user_id, api_key, base_url) -> int:
        """key 与路由一起写：分开两个端点会造出"有 key 没路由"这个必 401 上游的半套配置（spec 3.4）。"""
        return self._update_user(User, user_id, {"api_key": api_key, "base_url": base_url})

    def _update_user(self, model, user_id, fields: dict) -> int:
        session = self.get_session()
        try:
            updated = session.query(model).filter(model.id == user_id).update(fields)
            session.commit()
            return updated
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_user_models(self, user_id) -> list:
        """返回 [(name, is_default)]，按 id 升序 = 用户添加的顺序。

        "第一个"的口径必须钉住：spec 3.4 的"没有 default 就取名单第一个"是问答链的兜底，
        按 name 排会让它随字母序漂移，用户在界面上选中的和实际打出去的对不上。
        会话关闭前就展平成元组：别让调用方去摸已 detach 的 ORM 行（create_user 的 docstring 记过这个坑）。
        """
        session = self.get_session()
        try:
            rows = (session.query(UserModel).filter(UserModel.user_id == user_id)
                    .order_by(UserModel.id).all())
            return [(r.name, bool(r.is_default)) for r in rows]
        finally:
            session.close()

    def add_user_model(self, user_id, name) -> bool:
        """True = 新增；False = 名单里已经有了（端点据此回 409）。"""
        session = self.get_session()
        try:
            hit = session.query(UserModel.id).filter(UserModel.user_id == user_id,
                                                     UserModel.name == name).first()
            if hit:
                return False
            session.add(UserModel(user_id=user_id, name=name))
            session.commit()
            return True
        except IntegrityError:
            # 上面那次预查挡不住并发：两个请求同时"查不到"就同时插，unique 键才是唯一真相
            session.rollback()
            return False
        finally:
            session.close()

    def delete_user_model(self, user_id, name) -> int:
        """返回删掉的行数（0 = 名单里本来没这个名字）。

        **不**自动把下一个提成默认：spec 3.4 的解析规则自带"没有 default 就取名单第一个"，
        回落点在读取侧。写入侧再动一次默认会让"删掉默认"变成"悄悄换了个人"。
        """
        session = self.get_session()
        try:
            deleted = session.query(UserModel).filter(UserModel.user_id == user_id,
                                                      UserModel.name == name).delete()
            session.commit()
            return deleted
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def set_default_user_model(self, user_id, name) -> bool:
        """一事务内"清掉别人的 is_default + 立这一个"。

        分两次调用（先全清再立）会在两次之间留下"零个默认"或"两个默认"的中间态，
        而问答链正好读这个值决定用哪个模型。
        """
        session = self.get_session()
        try:
            target = session.query(UserModel).filter(UserModel.user_id == user_id,
                                                     UserModel.name == name).first()
            if target is None:
                return False
            (session.query(UserModel)
             .filter(UserModel.user_id == user_id, UserModel.name != name)
             .update({"is_default": False}))
            target.is_default = True
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
```

- [ ] **Step 5: 跑离线判据确认 GREEN + 改那条逐字 pin**

Run: `cd backend && python -m pytest tests/test_user_models_db.py tests/test_migrations.py -q`
Expected: `test_user_models_db` 全过；`test_migrations.py::test_default_identifier_is_the_one_the_spec_names` **红**（`MIGRATED_COLUMNS` 现在三行）。

把 `backend/tests/test_migrations.py:241-243` 改成（这条 pin 的价值就是"加列必须被人看见"）：

```python
def test_default_identifier_is_the_one_the_spec_names():
    assert migrations.DEFAULT_IDENTIFIER == "default@local"
    # 加列必须同步改这里：这条逐字 pin 的存在意义就是让"偷偷多一列"过一次评审
    assert migrations.MIGRATED_COLUMNS == [
        ("documents", "user_id", "INTEGER"),
        ("users", "api_key", "VARCHAR(255)"),
        ("users", "base_url", "VARCHAR(500)"),
    ]
```

- [ ] **Step 6: live 行为判据（真 MySQL）**

`backend/tests/test_live_database.py` 末尾追加一节（`pytestmark` 已是 `live`，`probe_user` fixture 现成）：

```python
def test_user_settings_round_trip(db, probe_user):
    """两列 + 名单四种行级操作在真库上的语义。fake 给不出 unique 键与 is_default 互斥的证据。"""
    assert db.update_user_profile(probe_user.id, nickname="改名了") == 1
    assert db.update_user_llm(probe_user.id, "sk-probe-abcdefg1234", "https://probe.example/v1") == 1
    fresh = db.get_user_by_id(probe_user.id)
    assert fresh.nickname == "改名了" and fresh.api_key == "sk-probe-abcdefg1234"

    assert db.add_user_model(probe_user.id, "probe-max") is True
    assert db.add_user_model(probe_user.id, "probe-max") is False      # unique 键那一条
    assert db.add_user_model(probe_user.id, "probe-mini") is True
    assert db.list_user_models(probe_user.id) == [("probe-max", False), ("probe-mini", False)]

    assert db.set_default_user_model(probe_user.id, "probe-mini") is True
    assert db.list_user_models(probe_user.id) == [("probe-max", False), ("probe-mini", True)]
    assert db.set_default_user_model(probe_user.id, "早没了") is False

    assert db.delete_user_model(probe_user.id, "probe-mini") == 1      # 删的是当前默认
    # 删默认不自动提升（写入侧不动别人的 is_default），读侧靠"没有 default 就取第一个"兜
    assert db.list_user_models(probe_user.id) == [("probe-max", False)]
    assert db.delete_user_model(probe_user.id, "probe-mini") == 0      # 幂等：第二次是 0 不是异常


def test_empty_profile_update_touches_nothing(db, probe_user):
    """两个字段都没传就该零副作用，而不是把昵称写成 NULL。"""
    before = db.get_user_by_id(probe_user.id).nickname
    assert before, "对照失去输入：探针账号昵称已是空值，这条绿不说明任何事"
    assert db.update_user_profile(probe_user.id) == 0
    assert db.get_user_by_id(probe_user.id).nickname == before
```

> **修订（2026-10-07 预检，覆盖本节原先写的 `== "探针账号"`）**：`probe_user` 是 `scope="module"`（`test_live_database.py:30`），两条新判据都追加在文件末尾 ⇒ 按定义顺序先跑 `test_user_settings_round_trip`，它已经把同一个账号的 nickname 改成 `改名了`。写死 `"探针账号"` 会**因为上一轮跑过而红**，且红得像"空更新把昵称洗掉了"——正好是本条要测的那个 bug 的表征。改成"读回改前的值再对照"：与顺序无关，仍然咬得住"写成 NULL"。

同文件 `_drop_probe_account`（`:380-395`）的清理补一张表——`user_models` 对 `users` 有外键，顺序照旧"先子后父"：

```python
    from core.database import AuthToken, User, UserModel

    session = db.get_session()
    try:
        session.query(AuthToken).filter(AuthToken.user_id == user_id).delete()
        session.query(UserModel).filter(UserModel.user_id == user_id).delete()
        session.query(User).filter(User.id == user_id).delete()
```

> 顺带改那句 docstring：`test_live_database.py:381` 现在写的是「先 auth_tokens 再 users」与「**这两张表**没有基线计数钉着」——三张表了。留着不改，下一个人对着三行删除读"这两张表"会以为多出来那行是别人漏删的孤儿清理。

- [ ] **Step 7: 跑 live 组**

Run: `cd backend && python -m pytest tests/test_live_database.py -q`（**只跑这一个进程，且确认没有别的 uvicorn 在跑**）
Expected: 全绿（含上一轮已有的条数）。若 MySQL 不可用会整组 skip——那就显式在台账记"本轮 live 未跑"，别报成绿。

> **跑之前先补一次 DDL**：本 Task 往**已存在**的 `users` 表加了 `api_key`/`base_url` 两列，而 `create_all` 只建新表、不给旧表加列 ⇒ 直接跑 live 会撞 `Unknown column 'users.api_key'`，那条红看着像代码坏了。先执行 **Task 6 Step 8** 里那句只发 `ensure_columns`/`ensure_indexes` 的预检命令（不开 Chroma、不打印凭证），再回来跑这一组。`user_models` 是新表，`create_all` 能建出来，不在这条依赖上。

- [ ] **Step 8: 提交**

```bash
git add backend/core/database.py backend/core/migrations.py backend/tests/test_user_models_db.py backend/tests/test_migrations.py backend/tests/test_live_database.py
git -c user.name="31439" -c user.email="31439@local" commit -F /tmp/fe2-task1.txt
```
提交信息（写进 utf-8 文件）：`feat(backend): users 两列 + user_models 表与七个设置类 DB 方法（阶段二 Task 1）`

---

## Task 2: 六个设置类端点 + `UserOut` 的五键扩展

**Files:**
- Modify: `backend/schemas/auth.py`（`UserOut:58-69` 之后加模型）
- Modify: `backend/api/auth.py`（`me:79-81` 之后追加，并改 `_issue`/`me` 的投影）
- Test: `backend/tests/test_api_auth.py`（34 条 → 约 48 条；`FakeAuthDB:23-52` 要补属性与方法；`:76-77` 那条逐字 pin 要改）

**Interfaces:**
- Consumes: Task 1 的 `User.api_key/base_url` 与七个 DB 方法
- Produces: `GET/PUT /api/auth/me`、`PUT /api/auth/me/password`、`PUT /api/auth/me/llm`、`POST|DELETE|PUT /api/auth/me/models*` 的响应形状；`UserOut` 的 `llm_configured`/`models`/`default_model` 被 Task 9 的 `SettingsModal` 与 Task 11 的横幅直接读；`mask_api_key` 被 Task 12 的验收判据引用。

- [ ] **Step 1: 写 RED（端点契约）**

`backend/tests/test_api_auth.py` 追加（沿用文件现成的 `make_client`，但 `FakeAuthDB` 要长出新格子，见 Step 2）：

```python
def _login_llm_client(identifier="a@b.com"):
    """注册并登录，返回 (client, db, token)。设置类端点都要带 Bearer 头。"""
    client, db = make_client()
    register(client, identifier=identifier)
    token = client.post("/api/auth/login", json={
        "identifier": identifier, "password": "hunter2-pass"}).json()["token"]
    return client, db, {"Authorization": f"Bearer {token}"}


def test_me_returns_the_five_new_keys_without_the_raw_key():
    client, db, headers = _login_llm_client()
    client.put("/api/auth/me/llm", json={"api_key": "sk-abcdef1234567890",
                                         "base_url": "https://vLLM.internal/v1"}, headers=headers)
    user = client.get("/api/auth/me", headers=headers).json()["user"]
    assert user["llm_configured"] is True
    assert user["llm_base_url"] == "https://vLLM.internal/v1"
    # 掩码口径（spec 3.1）：sk- 前缀 + 尾 4 位，中间一律 ****
    assert user["api_key_masked"] == "sk-****7890"
    assert "abcdef" not in client.get("/api/auth/me", headers=headers).text
    assert user["models"] == [] and user["default_model"] is None


def test_llm_config_requires_both_key_and_base_url():
    client, _, headers = _login_llm_client()
    assert client.put("/api/auth/me/llm", json={"api_key": "sk-x", "base_url": ""},
                      headers=headers).status_code == 422
    # 只填一半不算配置：llm_configured 必须 False，否则 409 门禁形同虚设
    assert client.get("/api/auth/me", headers=headers).json()["user"]["llm_configured"] is False


def test_profile_update_changes_nickname_and_avatar():
    client, _, headers = _login_llm_client()
    res = client.put("/api/auth/me", json={"nickname": "小明", "avatar": "🤖"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["user"]["nickname"] == "小明"
    assert res.json()["user"]["avatar"] == "🤖"
    # 预设白名单外的一律 422（Step 4 的 AVATARS 分支）：这列不是图片 URL，存进去前端渲染不出
    assert client.put("/api/auth/me", json={"avatar": "<script>"}, headers=headers).status_code == 422
    # 只传头像时昵称不许被清掉：update_user_profile 是"只改传了的格子"
    assert client.put("/api/auth/me", json={"avatar": "🦊"}, headers=headers
                      ).json()["user"]["nickname"] == "小明"
    # 空 body（两格都没传）不算更新：422 比 200 但什么都没变更诚实
    assert client.put("/api/auth/me", json={}, headers=headers).status_code == 422
    # 昵称上界 50 对齐 users.nickname 的 String(50)，超了必须 422 而不是被 MySQL 切掉
    assert client.put("/api/auth/me", json={"nickname": "字" * 51}, headers=headers).status_code == 422


def test_password_change_requires_the_old_one():
    client, db, headers = _login_llm_client()
    assert client.put("/api/auth/me/password", json={"old_password": "wrong-pass",
                                                     "new_password": "brand-new-pass"},
                      headers=headers).status_code == 401
    assert client.put("/api/auth/me/password", json={"old_password": "hunter2-pass",
                                                     "new_password": "brand-new-pass"},
                      headers=headers).status_code == 204
    assert client.post("/api/auth/login", json={"identifier": "a@b.com",
                                                 "password": "brand-new-pass"}).status_code == 200
    # 库里换的是哈希，且新哈希与旧的不是同一个串（盐必须重造）
    assert db.users[0].password_hash != "brand-new-pass"


def test_model_list_add_default_and_delete():
    client, _, headers = _login_llm_client()
    add = lambda name: client.post("/api/auth/me/models", json={"name": name}, headers=headers)
    assert add("qwen-max").json() == {"models": ["qwen-max"], "default_model": "qwen-max"}
    assert add("qwen-max").status_code == 409              # 重复添加
    assert add("qwen-turbo").json()["models"] == ["qwen-max", "qwen-turbo"]   # 添加顺序就是名单顺序
    # 第一个进来的人自动是默认：没有这一步的话用户配完 key 仍会撞"名单为空"以外的第三条 409
    assert client.put("/api/auth/me/models/default", json={"name": "qwen-turbo"},
                      headers=headers).json() == {"models": ["qwen-max", "qwen-turbo"],
                                                  "default_model": "qwen-turbo"}
    assert client.put("/api/auth/me/models/default", json={"name": "早删了"},
                      headers=headers).status_code == 409
    res = client.delete("/api/auth/me/models/qwen-turbo", headers=headers)
    assert res.json() == {"models": ["qwen-max"], "default_model": "qwen-max"}


def test_model_name_length_matches_the_column_and_chat_request():
    client, _, headers = _login_llm_client()
    assert client.post("/api/auth/me/models", json={"name": "x" * 101},
                       headers=headers).status_code == 422
    assert client.post("/api/auth/me/models", json={"name": ""}, headers=headers).status_code == 422


def test_settings_endpoints_are_all_behind_the_login_gate():
    client, _ = make_client()
    for method, path in [("PUT", "/api/auth/me"), ("PUT", "/api/auth/me/password"),
                         ("PUT", "/api/auth/me/llm"), ("POST", "/api/auth/me/models"),
                         ("DELETE", "/api/auth/me/models/x"), ("PUT", "/api/auth/me/models/default")]:
        res = client.request(method, path, json={})
        assert res.status_code == 401, f"{method} {path} 没上门：{res.status_code}"


def test_masking_never_echoes_a_short_key_back_as_its_own_tail():
    """短 key 的"尾 4 位"就是它自己：那时宁可只回前缀 + 一串星。"""
    from schemas.auth import mask_api_key
    assert mask_api_key("sk-abc") == "sk-****"
    assert mask_api_key("") == "" and mask_api_key(None) == ""
    assert mask_api_key("noplus-1234567890") == "****7890"     # 没有 sk- 前缀也照样只留尾 4
```

- [ ] **Step 2: 跑一次确认 RED**

Run: `cd backend && python -m pytest tests/test_api_auth.py -q`
Expected: FAIL（新条 405/404/断言失败），且**旧条 `test_register_returns_token_user_and_a_uuid_session` 也红**——`:76-77` 的逐字五键 pin 撞上新形状，这是预期连带，Step 5 一起改。

- [ ] **Step 3: schemas —— `UserOut` 与入参模型**

`backend/schemas/auth.py` 把 `UserOut`（`:58-69`）换成：

```python
def mask_api_key(raw: str | None) -> str:
    """`sk-` 前缀 + 尾 4 位，其余 `****`（spec 3.1）。原文离开这个函数就只有数据库里那一份。

    短值不露尾巴：key 只有 7 位时"尾 4 位"会把大半串还回去，掩码就成了提示。
    """
    if not raw:
        return ""
    head = "sk-" if raw.startswith("sk-") else ""
    body = raw[len(head):] if head else raw
    if len(body) <= 8:
        return f"{head}****"
    return f"{head}****{body[-4:]}"


class UserOut(BaseModel):
    """from_attributes 让它能直接吃 ORM 的 User 行。

    没有 password_hash 这个字段——少写一个字段比写一个"过滤掉敏感列"的逻辑可靠得多。
    api_key 同理不出现：这里只有 `api_key_masked`，掩码在 `_user_out` 里做。
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    identifier: str
    identifier_type: str
    nickname: str
    avatar: str
    # —— 阶段二新增：后五项没有一项能靠 from_attributes 从 User 行读出来，
    #    它们来自 users.api_key/base_url 与 user_models 表，由 api/auth.py 的 _user_out 组装。
    llm_configured: bool = False
    llm_base_url: str = ""
    api_key_masked: str = ""
    models: list[str] = Field(default_factory=list)
    default_model: str | None = None


class ProfileIn(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=50)
    avatar: str | None = Field(default=None, min_length=1, max_length=20)

    @model_validator(mode="after")
    def _at_least_one(self):
        # 空 body 回 422 而不是 200："我提交了设置，它说成功了，我刷新一看没变"最难查
        if self.nickname is None and self.avatar is None:
            raise ValueError("昵称与头像至少要改一样")
        return self


class PasswordIn(BaseModel):
    old_password: str = Field(min_length=1, max_length=64)
    new_password: str = Field(min_length=PASSWORD_MIN, max_length=64)


class LlmIn(BaseModel):
    # 上界对齐两列：String(255) / String(500)
    api_key: str = Field(min_length=8, max_length=255)
    base_url: str = Field(min_length=8, max_length=500)

    @field_validator("base_url")
    @classmethod
    def _looks_like_a_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not re.match(r"^https?://", value):
            raise ValueError("路由必须以 http:// 或 https:// 开头")
        return value


class ModelIn(BaseModel):
    # 1..100 与 user_models.name 的 String(100)、ChatRequest.model_name 三处同源
    name: str = Field(min_length=1, max_length=100)


class ModelsOut(BaseModel):
    models: list[str]
    default_model: str | None = None


# 设置端点（本 Task）与问答端点的模型解析（Task 7）要说同一句话，抄两遍迟早分叉
MODEL_NOT_IN_LIST = "模型不在你的名单里"
```
`import` 行补 `model_validator`：`from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator`。

> **计划级裁定（spec 未覆盖的两处）**：① `ModelsOut` 比 spec 3.1 的 `{models: [...]}` 多回一个 `default_model`——设默认之后前端不重新 `GET /me` 就得知道现在默认是谁，多一个键比多一次请求便宜；② 重复添加与"设一个不存在的默认"各回 409，文案是「该模型已在你的名单里」「模型不在你的名单里」（后者复用 spec 3.5 已有的那一句，不新造文案）。

- [ ] **Step 4: api —— 六个端点 + 投影**

`backend/api/auth.py`：`_issue`（`:38-42`）与 `me`（`:79-81`）改用同一个投影，并把 import 补全。

```python
from schemas.auth import (AuthOut, LlmIn, LoginIn, MeOut, MODEL_NOT_IN_LIST, ModelIn,
                          ModelsOut, PasswordIn, ProfileIn, RegisterIn, UserOut, mask_api_key)
```

`_issue` 的第三行与 `me` 端点里的 `UserOut.model_validate(user)` 都换成 `_user_out(db, user)`（`_issue` 已有 `db` 形参，不用改签名）：

```python
def _user_out(db, user) -> UserOut:
    """把"User 行 + user_models 表"折成 UserOut。全项目唯一组装点，别在端点里各拼一遍。

    `llm_configured` 要 key 与路由**同时**有值：只填一半的人问起来拿到的是上游 401，
    而我们连"你没配全"都说不出口——那不如在设置这一步就拦住（spec 3.4）。
    """
    rows = db.list_user_models(user.id)
    return UserOut(
        id=user.id, identifier=user.identifier, identifier_type=user.identifier_type,
        nickname=user.nickname, avatar=user.avatar,
        llm_configured=bool(user.api_key and user.base_url),
        llm_base_url=user.base_url or "",
        api_key_masked=mask_api_key(user.api_key),
        models=[name for name, _ in rows],
        default_model=next((name for name, is_default in rows if is_default), None),
    )
```

`me` 端点之后追加六个（全部 `user=Depends(get_current_user)`）：

```python
@router.put("/me", response_model=MeOut)
def update_me(payload: ProfileIn, db=Depends(get_db), user=Depends(get_current_user)):
    nickname = payload.nickname.strip() if payload.nickname is not None else None
    if payload.nickname is not None and not nickname:
        raise HTTPException(status_code=422, detail="昵称不能是空白")
    if payload.avatar is not None and payload.avatar not in AVATARS:
        # 头像走预设白名单（决策 5）：这一列不是图片 URL，随便存一串只会让
        # 前端渲染出一个空的 .rail-avatar
        raise HTTPException(status_code=422, detail="头像不在预设里")
    db.update_user_profile(user.id, nickname=nickname, avatar=payload.avatar)
    return MeOut(user=_user_out(db, _reload(db, user)))


@router.put("/me/password", status_code=204)
def update_password(payload: PasswordIn, db=Depends(get_db), user=Depends(get_current_user)):
    # 已经过 get_current_user 的门，这里回"原密码不正确"不泄露账号存在性，只防"捡到一枚还没过期的令牌"的人改密码
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=401, detail="原密码不正确")
    db.update_user_password(user.id, hash_password(payload.new_password))
    return None


@router.put("/me/llm", response_model=MeOut)
def update_llm(payload: LlmIn, db=Depends(get_db), user=Depends(get_current_user)):
    db.update_user_llm(user.id, payload.api_key.strip(), payload.base_url.strip())
    return MeOut(user=_user_out(db, _reload(db, user)))


@router.post("/me/models", response_model=ModelsOut)
def add_model(payload: ModelIn, db=Depends(get_db), user=Depends(get_current_user)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="模型名不能是空白")
    if not db.add_user_model(user.id, name):
        raise HTTPException(status_code=409, detail="该模型已在你的名单里")
    return _models_out(db, user)


@router.delete("/me/models/{name}", response_model=ModelsOut)
def remove_model(name: str, db=Depends(get_db), user=Depends(get_current_user)):
    db.delete_user_model(user.id, name)
    return _models_out(db, user)


@router.put("/me/models/default", response_model=ModelsOut)
def set_default_model(payload: ModelIn, db=Depends(get_db), user=Depends(get_current_user)):
    if not db.set_default_user_model(user.id, payload.name.strip()):
        raise HTTPException(status_code=409, detail=MODEL_NOT_IN_LIST)
    return _models_out(db, user)
```

配套三个小件（写在这一文件的端点之上）：

```python
# 预设头像（决策 5：不做图片上传，项目里没有文件存储层）。'auto' = 昵称首字母。
AVATARS = ("auto", "😀", "🤖", "🦊", "🐼", "🚀")


def _reload(db, user):
    """改完必须重新读一行：`user` 是 get_current_user 早先取出的快照，字段还是旧的。"""
    return db.get_user_by_id(user.id) or user


def _models_out(db, user) -> ModelsOut:
    rows = db.list_user_models(user.id)
    return ModelsOut(models=[name for name, _ in rows],
                     default_model=next((name for name, d in rows if d), None))
```

> **删掉默认那行之后 `default_model` 从哪来**：`set_default_user_model` 只在显式调用时改 `is_default`，删除不动别人的标记（Task 1 的 docstring 已记）。于是删掉默认后 `default_model` 会是 `None`，前端下拉仍显示名单第一项——这与 Task 7 `_llm_context` 的解析口径**必须一致**，两边都写"没有 default 就取 `list_user_models` 的第一项"。上面 `test_model_list_add_default_and_delete` 里那条断言（删除后 `default_model == "qwen-max"`）要求 **首个模型入名单时就自动置默认**，所以 `add_user_model` 里补一句：`is_default = (not self.list_user_models(user_id))`——第一个进名单的人就是默认，这是"用户只配了一个模型却能问成功"的唯一路径。

> ⚠️ 上面这段"add 时自动置默认"要落进 Task 1 的 `add_user_model`（Step 4 的代码块里 `session.add(UserModel(user_id=user_id, name=name))` 之前先数一下名单是否为空）；它同时让 spec 3.4 的"没有 default 就取第一个"退成纯兜底。**这是计划级新增行为，spec 未写，评审时按"必要补全"裁定。**

- [ ] **Step 5: 连带修 `FakeAuthDB` 与那条逐字 pin**

`backend/tests/test_api_auth.py:23-52` 的 `FakeAuthDB` 补格子（SimpleNamespace 没有新列就会 AttributeError，这是 fake 落后于 ORM 的经典表征）：

```python
    def create_user(self, identifier, identifier_type, nickname, password_hash, avatar="auto"):
        if any(u.identifier == identifier for u in self.users):
            raise IntegrityError("INSERT INTO users", {}, Exception("duplicate entry"))
        user = SimpleNamespace(id=self._next_id, identifier=identifier,
                               identifier_type=identifier_type, nickname=nickname,
                               avatar=avatar, password_hash=password_hash,
                               # 与 ORM 行同名同初值：新注册的人还没配 key
                               api_key=None, base_url=None)
        ...

    # ---------- 阶段二：设置类方法（与 DatabaseManager 同名同返回形状）----------

    def update_user_profile(self, user_id, nickname=None, avatar=None):
        user = self.get_user_by_id(user_id)
        if nickname is not None:
            user.nickname = nickname
        if avatar is not None:
            user.avatar = avatar
        return 1

    def update_user_password(self, user_id, password_hash):
        self.get_user_by_id(user_id).password_hash = password_hash
        return 1

    def update_user_llm(self, user_id, api_key, base_url):
        user = self.get_user_by_id(user_id)
        user.api_key, user.base_url = api_key, base_url
        return 1

    def get_user_by_id(self, user_id):
        return next((u for u in self.users if u.id == user_id), None)

    def list_user_models(self, user_id):
        return list(self.models.get(user_id, []))

    def add_user_model(self, user_id, name):
        rows = self.models.setdefault(user_id, [])
        if (name, False) in rows or (name, True) in rows:
            return False
        rows.append((name, not rows))     # 第一个自动成为默认
        return True

    def delete_user_model(self, user_id, name):
        rows = self.models.setdefault(user_id, [])
        before = len(rows)
        self.models[user_id] = [r for r in rows if r[0] != name]
        return before - len(self.models[user_id])

    def set_default_user_model(self, user_id, name):
        rows = self.models.setdefault(user_id, [])
        if not any(n == name for n, _ in rows):
            return False
        self.models[user_id] = [(n, n == name) for n, _ in rows]
        return True
```
`__init__` 里补 `self.models = {}`（`user_id -> [(name, is_default)]`）。

`test_register_returns_token_user_and_a_uuid_session`（`:76-77`）的字典换成十键：

```python
    assert body["user"] == {"id": 1, "identifier": "a@b.com", "identifier_type": "email",
                            "nickname": "a", "avatar": "auto", "llm_configured": False,
                            "llm_base_url": "", "api_key_masked": "", "models": [],
                            "default_model": None}
```
（同文件若还有逐字比 `user` 整字典的判据，一并补十键；跑一遍看红几处以实跑为准。）

- [ ] **Step 6: 跑离线门禁**

Run: `cd backend && python -m pytest -q`
Expected: 全绿；条数比基线 **257** 多约 13–14（以当轮汇总行为准）。

> **修订（2026-10-07，Task 2 预检 + 实跑回写）**，三处：
> ① **起点不是 257。** Task 1 已经加了 5 条，本 Task 开工时的全量实数是 **262 passed / 2 skipped / 2 deselected**，`test_api_auth.py` 起点 **34**。终态实数：**`test_api_auth.py` 43 passed / 全量 271 passed, 2 skipped, 2 deselected / live 单文件 20 passed（真跑无 skip）**，RED 阶段 `8 failed, 34 passed`。三门各带 1 warning，出处是既有 `core/database.py:13` 的 `declarative_base()` MovedIn20Warning，非本轮引入。
> ② **Step 4 的"首个模型自动置默认"会打断 Task 1 已提交的 live 判据，这一句 brief/计划正文没写。** `core/database.py` 的 `add_user_model` 加进 `is_default` 之后，`tests/test_live_database.py:529` 的 `[("probe-max", False), ("probe-mini", False)]` 必然红——新真值是 `[("probe-max", True), ("probe-mini", False)]`，而这一句从此就是那条新逻辑的直接判据。同时 `:532-535` 那段注释（"先立 probe-max 的唯一作用是把前置态造出来"）说的是假话了：前置态现在由 `add` 自己造，`set_default(probe-max)` 退成同值重设，清场句的证据只剩第二次设默认那一句。**改断言 + 改注释都属于执行本计划，不是改计划**（Step 7 的文件清单本来就含这个文件）。
> ③ `is_first` 的判空必须是**另一次不带 `name` 过滤**的查询。复用上面那次 `hit`（它按名字过滤）等于把"名单里没这个名字"当"名单是空的"，第二枚也会被标成默认、两个默认并存；实测这种退化**只有 live 红，离线全绿**（fake 自己用 `not rows` 算，口径不受影响）。

- [ ] **Step 7: 提交**

```bash
git add backend/schemas/auth.py backend/api/auth.py backend/tests/test_api_auth.py backend/core/database.py backend/tests/test_live_database.py
git -c user.name="31439" -c user.email="31439@local" commit -F /tmp/fe2-task2.txt
```
提交信息：`feat(backend): 六个设置类端点 + UserOut 十键（阶段二 Task 2）`

---

## Task 3: 迁移步骤 4（把 `.env` 三键抄给默认用户）+ 补戳崩溃窗口自愈（advisory ①）

**Files:**
- Modify: `backend/core/migrations.py`（`vector_ids_without_owner:128`、`stamp_vector_owner:145-174`、`run_migrations:177-194`）
- Modify: `backend/main.py:55-56`（`run_migrations` 改吃 `config`）
- Test: `backend/tests/test_migrations.py`（`FakeConn` 加分支、`:199` 那条顺序判据改写、新增约 4 条）
- Test: `backend/tests/test_chroma_data.py:97,108`（`stamp_vector_owner` 新形状，2 处）

**Interfaces:**
- Consumes: Task 1 的 `users.api_key/base_url` 列与 `user_models` 表
- Produces: `seed_default_llm(conn, user_id, api_key, base_url, model) -> dict`、`vectors_needing_owner(conn) -> {"parent": [(vid, uid)], "child": [...]}`、`stamp_vector_owner(client, vectors) -> int`、`run_migrations(engine, chroma_client, config) -> dict`（**第三个参数从 `password: str` 变成 `config`**）。Task 4 之后默认用户能直接对话就靠这里抄进去的 key。

- [ ] **Step 1: 写 RED**

`backend/tests/test_migrations.py` 追加（并把 `FakeConn.execute` 补上四个新分支，见 Step 3）：

```python
def test_seed_copies_the_three_env_keys_once():
    conn = FakeConn(user_rows=[(1, "default@local")])
    out = migrations.seed_default_llm(conn, 1, api_key="sk-from-env",
                                      base_url="https://dashscope/v1", model="qwen3.7-flash")
    assert out == {"llm_written": True, "model_added": True}
    assert conn.llm == {"user_id": 1, "api_key": "sk-from-env", "base_url": "https://dashscope/v1"}
    assert conn.user_models == [(1, "qwen3.7-flash", True)]     # 首个模型即默认


def test_seed_never_overwrites_a_key_the_user_set_himself():
    """幂等在这里的含义是"第二次什么都不写"：用户改过自己的 key，重启不该把 .env 的值盖回去。"""
    conn = FakeConn(user_rows=[(1, "default@local")])
    migrations.seed_default_llm(conn, 1, "sk-first", "https://a/v1", "m-one")
    second = migrations.seed_default_llm(conn, 1, "sk-second", "https://b/v1", "m-two")
    assert second == {"llm_written": False, "model_added": False}
    assert conn.llm["api_key"] == "sk-first"
    assert [n for _, n, _ in conn.user_models] == ["m-one"]     # 没追加第二个


def test_seed_does_nothing_when_env_has_no_key():
    conn = FakeConn(user_rows=[(1, "default@local")])
    assert migrations.seed_default_llm(conn, 1, None, None, "m") == {
        "llm_written": False, "model_added": False}
    assert conn.user_models == []      # 没有 key 却塞一个模型名 = 造一条必 409 的半套配置


def test_run_migrations_self_heals_a_crash_between_claim_and_stamp():
    """advisory ①：MySQL 已归户、Chroma 还没戳之间挂掉，下次开机必须把这批向量补上。

    阶段一的判据（`test_run_migrations_stamps_the_vectors_read_before_documents_are_claimed`）
    钉的是"清单在归户之前读"，正因为如此那次崩溃之后清单永远为空。这里换成
    "以文档现在的主人为准"：连跑两遍，第一遍归户+补戳，第二遍的 `get` 看到已戳就零写。
    """
    parent = FakeCollection({"pv1": {"document_id": "3"}, "pv2": {"document_id": "4"}})
    child = FakeCollection({"cv1": {"document_id": "5"}})
    engine = FakeEngine(FakeConn())
    first = migrations.run_migrations(engine, FakeChroma({"parent_document": parent,
                                                          "child_document": child}),
                                       FakeConfig())
    assert first["vectors_stamped"] == 3
    # 模拟崩在补戳之前：把 Chroma 的戳擦掉，documents 的 user_id 留着（MySQL 已经 commit 了）
    for item in parent.items.values():
        item.pop("user_id", None)
    child.items["cv1"].pop("user_id", None)
    second = migrations.run_migrations(engine, FakeChroma({"parent_document": parent,
                                                           "child_document": child}),
                                        FakeConfig())
    assert second["vectors_stamped"] == 3, "归户之后就不再有补戳清单——advisory ① 回来了"
    assert parent.items["pv1"] == {"document_id": "3", "user_id": "1"}


def test_stamp_uses_each_documents_own_owner():
    """每个向量按**自己文档**的主人补戳，不再假设"无主的都归默认用户"。"""
    parent = FakeCollection({"p1": {"document_id": "3"}, "p2": {"document_id": "4"}})
    client = FakeChroma({"parent_document": parent, "child_document": FakeCollection({})})
    stamped = migrations.stamp_vector_owner(
        client, {"parent": [("p1", 7), ("p2", 8)], "child": []})
    assert stamped == 2
    assert parent.items["p1"]["user_id"] == "7" and parent.items["p2"]["user_id"] == "8"
```

`FakeConfig`（同文件顶部，`run_migrations` 改吃 config 之后要有的东西）：

```python
class FakeConfig:
    """run_migrations 现在读 config 的四格：默认口令 + 迁移种子的三键。"""
    DEFAULT_USER_PASSWORD = "secret-pass"
    OPENAI_API_KEY = "sk-from-env"
    OPENAI_BASE_URL = "https://dashscope/v1"
    LLM_MODEL = "qwen3.7-flash"
```

- [ ] **Step 2: 跑一次确认 RED**

Run: `cd backend && python -m pytest tests/test_migrations.py -q`
Expected: FAIL —`AttributeError: module 'core.migrations' has no attribute 'seed_default_llm'`；`test_run_migrations_*` 那条旧判据也红（签名已变）。

- [ ] **Step 3: 实现**

`backend/core/migrations.py`：把 `vector_ids_without_owner`（`:128-143`）整体换成：

```python
def vectors_needing_owner(conn) -> dict:
    """补戳清单：**以文档现在的主人为准**，不再以"文档还没主人"为准（终审 advisory ①）。

    阶段一写的是 `WHERE d.user_id IS NULL`，于是 `backfill_documents` 提交之后、
    `stamp_vector_owner` 跑完之前挂掉 ⇒ 下次开机这条 SELECT 返回空集，那批向量**永远**补不上戳。
    换成"所有有主人的向量都进清单"，幂等就交给 Chroma 侧的"已戳就跳过"，崩溃窗口一次开机自愈。
    代价：每次开机多一次全量 id 的 `get()`（基线 11 父 + 22 子，只读 metadata）。
    """
    out = {"parent": [], "child": []}
    for key, table in (("parent", "parent_chunks"), ("child", "child_chunks")):
        rows = conn.execute(text(
            f"SELECT c.vector_id, d.user_id FROM {table} c "
            "JOIN documents d ON d.id = c.document_id "
            "WHERE c.vector_id IS NOT NULL AND c.vector_id <> '' AND d.user_id IS NOT NULL"
        )).fetchall()
        out[key] = [(r[0], r[1]) for r in rows]
    return out
```

`stamp_vector_owner`（`:145-174`）改收新形状、去掉 `user_id` 形参：

```python
def stamp_vector_owner(client, vectors: dict) -> int:
    """把 (向量 id, 主人) 补进 metadata。已戳的一律跳过，**哪怕戳的是别人**——
    迁移只补空，改归属不是它的活。

    仍不依赖"Chroma 的 update 只补提供的键"这个较新版本的语义（原注释的理由一字不改）：
    读回来合并写是最保守的做法，document_id/parent_id 一丢，召回与按文档清扫会同时坏掉。
    """
    from core.vector_store import COLLECTION_CHILD, COLLECTION_PARENT

    total = 0
    for name, rows in ((COLLECTION_PARENT, vectors["parent"]),
                       (COLLECTION_CHILD, vectors["child"])):
        if not rows:
            continue
        collection = client.get_collection(name)
        found = collection.get(ids=[vid for vid, _ in rows], include=["metadatas"])
        owner = {vid: uid for vid, uid in rows}
        to_update, metadatas = [], []
        for vid, meta in zip(found["ids"], found["metadatas"]):
            meta = meta or {}
            if meta.get("user_id") not in (None, ""):
                continue
            to_update.append(vid)
            metadatas.append({**meta, "user_id": str(owner[vid])})
        if to_update:
            collection.update(ids=to_update, metadatas=metadatas)
            total += len(to_update)
    return total
```

新增 `seed_default_llm`（放在 `backfill_documents` 之后）：

```python
def seed_default_llm(conn, user_id: int, api_key, base_url, model) -> dict:
    """迁移步骤 4（spec 6）：把 `.env` 的三键抄给默认用户——坑 9 成果的去向。

    两个返回值都要**可数**，幂等这条判据不能吃日志。
    只在默认用户手上还没有 key 时抄：运行期他改过配置，重启再把 `.env` 盖回去等于每次开机
    偷走一次用户的修改。`api_key` 与 `base_url` 必须同时有值才抄（半套配置只会撞上游 401）。
    """
    if not (api_key and base_url):
        return {"llm_written": False, "model_added": False}
    row = conn.execute(text("SELECT api_key FROM users WHERE id = :uid"), {"uid": user_id}).fetchall()
    if row and row[0][0]:
        return {"llm_written": False, "model_added": False}
    conn.execute(text("UPDATE users SET api_key = :k, base_url = :u WHERE id = :uid"),
                 {"k": api_key, "u": base_url, "uid": user_id})
    conn.commit()
    added = False
    if model:
        exists = conn.execute(text("SELECT id FROM user_models WHERE user_id = :uid AND name = :n"),
                              {"uid": user_id, "n": model}).fetchall()
        if not exists:
            conn.execute(text("INSERT INTO user_models (user_id, name, is_default) "
                              "VALUES (:uid, :n, 1)"), {"uid": user_id, "n": model})
            conn.commit()
            added = True
    return {"llm_written": True, "model_added": added}
```

`run_migrations`（`:177-194`）重写：

```python
def run_migrations(engine, chroma_client, config) -> dict:
    """lifespan 唯一入口。返回一份可直接进日志的汇总，不返回秘密（没有令牌、没有哈希、没有 api_key）。

    第三个参数从阶段一的 `password: str` 换成 `config`：步骤 4 要读三个种子键，
    再多加一个形参就是第五件要记顺序的事——`Config` 就在那儿，直接吃它。
    """
    with engine.connect() as conn:
        added = ensure_columns(conn)
        indexes = ensure_indexes(conn)   # 顺序硬要求：列还没加出来就建索引会当场炸
        user_id = ensure_default_user(conn, config.DEFAULT_USER_PASSWORD)
        docs = backfill_documents(conn, user_id)
        seed = seed_default_llm(conn, user_id, config.OPENAI_API_KEY,
                                config.OPENAI_BASE_URL, config.LLM_MODEL)
        # 补戳清单现在读的是"有主人的向量"，必须在归户之后：顺序一反，第一次开机就拿到空集
        pending = vectors_needing_owner(conn)
    # 补戳放在连接之外：Chroma 那边可能是一次几秒的只读扫描，别把 MySQL 连接摁在它上面
    vectors = stamp_vector_owner(chroma_client, pending)
    summary = {"columns_added": added, "indexes_added": indexes,
               "default_user_id": user_id, "documents_claimed": docs,
               "llm_seeded": seed["llm_written"], "model_seeded": seed["model_added"],
               "vectors_stamped": vectors}
    logger.info("迁移完成: %s", summary)   # summary 里没有 api_key：多一个键就多一次泄漏机会
    return summary
```

`backend/main.py:55-56` 换成：

```python
    run_migrations(app.state.db.engine, app.state.vector_store.chroma_client, config)
```

`FakeConn`（`tests/test_migrations.py:15-81`）要认四种新 SQL——在 `execute` 的分支表里插进去（顺序：先长前缀后短前缀，`SELECT API_KEY...` 必须在 `SELECT ID...` 之前命中）：

```python
        if head.startswith("SELECT API_KEY FROM USERS"):
            uid = params["uid"]
            for i, _ident in self.users:
                if i == uid:
                    return _Result([(self.llm.get("api_key"),)])
            return _Result([])
        if head.startswith("UPDATE USERS SET API_KEY"):
            self.llm = {"user_id": params["uid"], "api_key": params["k"], "base_url": params["u"]}
            self.executed.append(text)
            return _Result([])
        if head.startswith("SELECT ID FROM USER_MODELS"):
            rows = [1 for (u, n, _d) in self.user_models
                    if u == params["uid"] and n == params["n"]]
            return _Result(rows)
        if head.startswith("INSERT INTO USER_MODELS"):
            self.user_models.append((params["uid"], params["n"], True))   # SQL 里 is_default 写死 1
            return _Result([])
```
并在 `FakeConn.__init__` 补 `self.llm = {}` 与 `self.user_models = []`；把原来那句 `SELECT C.VECTOR_ID FROM` 分支改成返回 `(vid, user_id)` 两列、且条件取反（文档**已**归户才进清单）：

```python
        if head.startswith("SELECT C.VECTOR_ID FROM"):
            key = "parent" if "PARENT_CHUNKS" in head else "child"
            # 真 SQL 返回 (vector_id, d.user_id) 两列；这里的主人恒为 1，因为 FakeConn 只有一个用户
            return _Result([(vid, 1) for vid, doc_id in UNOWNED_VECTOR_ROWS[key].items()
                            if doc_id in self.owned_docs])
```
> 分支表的 `head` 是 `str(sql).strip().upper()`，所以前缀必须按**大写**写、且长前缀（`SELECT ID FROM USER_MODELS`）要排在短前缀（`SELECT ID FROM USERS`/`SELECT ID FROM DOCUMENTS`）能命中之前的位置——`startswith` 是互斥前缀，三条 `SELECT ID FROM …` 之间不会互相抢，但 `FakeConn` 里同名 `params` 键（`:uid`）会复用，别指望分支顺序替你做区分。

- [ ] **Step 4: 改写那条被推翻的顺序判据**

`tests/test_migrations.py:199-218` 的 `test_run_migrations_stamps_the_vectors_read_before_documents_are_claimed`：它的前提（"必须在归户之前读"）正是 advisory ① 的病根。函数名与内部断言一起换：

```python
def test_run_migrations_stamps_after_documents_are_claimed():
    """清单读的是"有主人的向量"：归户必须在补戳之前，且崩溃之后能自愈（对照 Step 3 的新判据）。"""
    parent = FakeCollection({"pv1": {"document_id": "3"}, "pv2": {"document_id": "4"}})
    child = FakeCollection({"cv1": {"document_id": "5"}})
    client = FakeChroma({"parent_document": parent, "child_document": child})

    summary = migrations.run_migrations(FakeEngine(FakeConn()), client, FakeConfig())

    assert parent.requested == [["pv1", "pv2"]] and child.requested == [["cv1"]]
    assert parent.items["pv1"] == {"document_id": "3", "user_id": "1"}
    assert summary["vectors_stamped"] == 3
    assert summary["documents_claimed"] == 9
    assert summary["llm_seeded"] is True and summary["model_seeded"] is True
    assert "sk-from-env" not in str(summary)     # 汇总进日志：种子 key 绝不能在里面
```

`tests/test_migrations.py:221-238` 那两条（`stamp_merges_existing_metadata_and_skips_stamped` / `stamp_never_rewrites_a_foreign_users_vector`）与 `tests/test_chroma_data.py:97,108` 的调用点都换成新形状 `{"parent": [(vid, uid), ...], "child": []}`、去掉第三个实参。

- [ ] **Step 5: 跑离线门禁**

Run: `cd backend && python -m pytest -q`
Expected: 全绿（`-m "not migration"` 是默认；`test_chroma_data.py` 整组被 deselect，本轮不跑它，只保证它导入与新签名一致——真跑搬家守卫时按台账记实数）。

> **修订（2026-10-07，Task 3 预检裁定）**，三处：
> ① **`test_chroma_data.py` 本轮必须真跑，"只保证导入一致"在本机等于零验证。** 它整组带 `@pytest.mark.migration`，离线门禁默认 deselect，而那两处调用点（`:97`/`:108`）正是 `stamp_vector_owner` 新形状 `(vid, uid)` 的消费者——不跑就是把"签名改了但没人验过"留在树上。跑法：`cd backend && python -m pytest tests/test_chroma_data.py -m migration -q`。它只在 `tmp_path` 的 Chroma **副本**上开客户端、绝不写 `Config.CHROMA_PERSIST_DIR`，仍然是一个 pytest 进程、不起 uvicorn。**若因本机环境跑红（副本不完整等），如实记"本轮迁移组未跑通 + 实数"，不许转述成绿。**
> ② 现存 `run_migrations` 里有一句正文未提的 **`if not docs: pending = {"parent": [], "child": []}`**（归户零行就把清单清空）。新实现必须删掉它——新语义下清单读的是"**已**有主人的向量"，那句的前提已不存在，留着恰好会把 advisory ① 要修的自愈清单重新清空。评审若问"为什么少了一句"，答案在这里。
> ③ `tests/test_chroma_data.py:86` 的注释里还写着旧名 `vector_ids_without_owner`，改名后它是过期文字；与 `migrations.py` 顶部注释同一口径顺手改（纯文字）。另实测 `UserModel`（`database.py:150-163`）只有 `id`/`user_id`/`name`/`is_default` 四列、**没有 `created_at`**，所以 `seed_default_llm` 那句裸 `INSERT INTO user_models (user_id, name, is_default)` 不会撞 NOT NULL；将来若给这表补时间戳列，这句要同步改。

> **修订（2026-10-07，Task 3 实跑纠偏）**，本 Task 正文有三处事实已过期、一处口径需按现状读：
> ① Step 3 里那句「基线 **11 父 + 22 子**」作废。2026-10-07 重钉的活基线是 **4 父 + 10 子**（`tests/test_chroma_data.py:11-12` 的 `PARENT_COUNT`/`CHILD_COUNT`，且 `PARENT_IDS`/`CHILD_IDS` 长度一致；旧计数来自那批被删到 `chunk_count` 归零的文档）。生产码注释已按 4/10 写。
> ② Step 3 的 `stamp_vector_owner` 注释里「（**原注释一字不改**）」是自指——它引用的正是本 Task 要替换的那段注释，实施时按新语义重写，不作为约束。
> ③ Step 1 那条自愈判据的 docstring 说「第二遍的 `get` 看到已戳就**零写**」，与它自己的断言 `second["vectors_stamped"] == 3` 相反。**以断言为准**：补戳清单每次开机都重算，第二遍把擦掉的戳**重新补上 3 条**，这才是 advisory ① 要的自愈；"零写"只发生在 `stamp_vector_owner` 被重复调用而 metadata 未变时（由 `test_stamp_merges_existing_metadata_and_skips_stamped` 的最后一条断言钉住）。
> ④ Step 3 的 `FakeConn` 分支前缀照抄 `SELECT C.VECTOR_ID FROM` 会**永远不命中**：新 SQL 选了 `c.vector_id, d.user_id` 两列，整条串是 `SELECT c.vector_id, d.user_id FROM parent_chunks c …`，而 `head` 是**整条 SQL** 大写化后的串（不是列清单），`FROM` 前隔着 `, D.USER_ID`，于是 `startswith("SELECT C.VECTOR_ID FROM")` 恒假。实施时前缀放宽为 `SELECT C.VECTOR_ID`，并按 WHERE 里的条件（`D.USER_ID IS NOT NULL` 是否出现）决定收哪批行——这是让「生产码把 `IS NOT NULL` 写回 `IS NULL` 必须跑红」成立的必要条件。严重度交本轮评审裁定。

> **修订（2026-10-07，Task 3 评审修正轮 1）**，两处，均由任务评审查出（I-1 为 Important）：
> ① **Step 3 给的 `INSERT INTO user_models (…, is_default) VALUES (:uid, :n, 1)` 里 `is_default` 写死 1 是错的**，改为与 `core/database.py` 的 `add_user_model` 同口径：先探本用户的名单是否为空，空则 `is_default` 取 1、非空取 0（参数化成 `:d`，SQL 里不再出现字面量）。理由：本仓另两个写入点（`add_user_model` 的 `is_first`、`set_default_user_model` 的先清后立）都在维持"一个用户至多一枚默认"，`seed_default_llm` 是唯一绕开它的写入口；可达路径是"`.env` 无 key 时用户先自行加模型 → 之后补 `.env` 重启"，结果名单里两枚默认，读侧 `list_user_models`（按 id 升序）与 Task 7 的默认解析各自挑一枚。判据补一条："名单里已有一枚默认时，seed 只抄 key、不再立第二个默认"。**Task 12 的真服务验收要顺带确认默认用户名单里 `is_default=True` 恰好一枚。**
> ② **Step 1 的 `FakeConn` 补戳分支回的主人恒为 1，等于那列没牙**：生产码把 `vectors_needing_owner` 的 `r[1]` 写成恒 `1` 时四道门全绿，而在多用户真库上那是把别人的向量戳成默认用户的越权归属。改为按 `doc_id` 回不同主人（`100 + doc_id`），并在顺序判据里断言父块两枚拿到**不同**的 `user_id`；凡断言 `"user_id": "1"` 处按新映射改准。
> 另：`FakeConn` 的补戳分支加一句指名道姓的守卫（既读不出 `D.USER_ID IS NOT NULL` 也读不出 `D.USER_ID IS NULL` 时 `raise AssertionError`），让等价重写红得有名有姓；文件顶 docstring 与 `:91` 那句 `# SQL 里 is_default 写死 1` 同步改对。

- [ ] **Step 6: 提交**

```bash
git add backend/core/migrations.py backend/main.py backend/tests/test_migrations.py backend/tests/test_chroma_data.py
git -c user.name="31439" -c user.email="31439@local" commit -F /tmp/fe2-task3.txt
```
提交信息：`feat(migration): 步骤 4 抄三键给默认用户 + 补戳窗口自愈（阶段二 Task 3，收阶段一 advisory ①）`

## Task 4: `core/llm_factory.py` —— 全项目唯一的 LLM 构造点

**Files:**
- Create: `backend/core/llm_factory.py`
- Modify: `backend/exceptions.py`（`AuthError:21-23` 之后追加一个类）
- Test: `backend/tests/test_llm_factory.py`（新建，9 条）

**Interfaces:**
- Consumes: `langchain_openai.ChatOpenAI`、`langchain_classic.retrievers.document_compressors.LLMChainExtractor`（都已是既有依赖，零新包）、`exceptions.KnowledgeBaseError`
- Produces: `LLMConfig(api_key, base_url, model)`、`RunContext(user_id, llm)`、`llm_config_for(user, model) -> LLMConfig`（半套配置 raise `NotConfiguredError`）、`build_llm(ctx)`、`build_compressor(ctx)`、`NotConfiguredError`、`NOT_CONFIGURED`。Task 5 吃两个 build 函数与两个 dataclass；Task 7 吃 `llm_config_for` 与 `NotConfiguredError`。

- [ ] **Step 1: 写 RED**

新建 `backend/tests/test_llm_factory.py`：

```python
"""阶段二的全部理由压在这个模块：一次问答用**谁的** key、打**哪台**模型。

四条判据各挡一种坏法：
① 构造参数原样来自 ctx.llm —— 挡"忘了接用户行、又去读 Config"，那等于阶段一的形状原地不动；
② 答题 0.7 + streaming、压缩 0 且不流式 —— 挡"搬迁顺手把行为改了"（回归判据，不是新功能）；
③ 两个构造点吃同一枚 ctx.llm —— 坑 9 的新钉法。旧的两条判据（`test_rag_system.py:357`、
   `test_vector_store.py:144`）各看一个 `__init__`，谁都不表达"同源"；合成一条才真正钉住；
④ 半套配置当场拒绝 —— 有 key 没路由的请求会打到默认端点上，表征是一句看不懂的 401。
"""
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from core.llm_factory import (
    LLMConfig,
    NotConfiguredError,
    RunContext,
    build_compressor,
    build_llm,
    llm_config_for,
)
from exceptions import KnowledgeBaseError


def make_ctx(model="qwen-max", user_id=7):
    return RunContext(user_id=user_id,
                      llm=LLMConfig(api_key="sk-user-key", base_url="https://u.internal/v1", model=model))


def test_build_llm_uses_the_callers_own_credentials(monkeypatch):
    """api_key/base_url/model 三值只能来自 ctx.llm：这一格读 Config 就是阶段一没走完。"""
    seen = {}

    class Recorder:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr("core.llm_factory.ChatOpenAI", Recorder)
    build_llm(make_ctx())
    assert seen["api_key"] == "sk-user-key"
    assert seen["base_url"] == "https://u.internal/v1"
    assert seen["model"] == "qwen-max"


def test_build_llm_keeps_the_answer_chain_temperature_and_streaming(monkeypatch):
    """0.7 与 streaming=True 是 rag_system.py:31-32 的既有行为，搬迁不许顺手改。"""
    seen = {}

    class Recorder:
        def __init__(self, **kwargs):
            seen.update(kwargs)

    monkeypatch.setattr("core.llm_factory.ChatOpenAI", Recorder)
    build_llm(make_ctx())
    assert seen["temperature"] == 0.7
    assert seen["streaming"] is True


def test_build_compressor_is_temperature_zero_and_shares_the_model_name(monkeypatch):
    """压缩器不开流式（`vector_store.py:42-47` 的老形状就是 `temperature=0` 一个参数），
    模型名必须与答题同一个来源——坑 9 的历史事故正是这两处分叉。"""
    seen = {}
    extracted = {}

    class Recorder:
        def __init__(self, **kwargs):
            seen.update(kwargs)
            self.model = kwargs.get("model")

    monkeypatch.setattr("core.llm_factory.ChatOpenAI", Recorder)
    monkeypatch.setattr("core.llm_factory.LLMChainExtractor",
                        SimpleNamespace(from_llm=lambda llm: extracted.setdefault("llm", llm)))
    build_compressor(make_ctx(model="qwen-turbo"))

    assert seen["temperature"] == 0
    assert "streaming" not in seen, "压缩链不是逐字输出的，别顺手给它加流式"
    assert extracted["llm"].model == "qwen-turbo"


def test_llm_config_for_returns_the_three_values():
    user = SimpleNamespace(id=3, api_key="sk-live-key", base_url="https://vLLM.internal/v1")
    conf = llm_config_for(user, model="qwen-plus")
    assert (conf.api_key, conf.base_url, conf.model) == (
        "sk-live-key", "https://vLLM.internal/v1", "qwen-plus")


@pytest.mark.parametrize("api_key,base_url", [
    (None, "https://u/v1"),
    ("sk-key-abcdef", None),
    ("", "https://u/v1"),
    ("sk-key-abcdef", ""),
])
def test_llm_config_for_refuses_a_half_set(api_key, base_url):
    """只有 key 没有路由的请求会打到 OpenAI 官方端点，表征是一句看不懂的 401。"""
    user = SimpleNamespace(id=3, api_key=api_key, base_url=base_url)
    with pytest.raises(NotConfiguredError):
        llm_config_for(user, model="qwen-max")


def test_run_context_is_frozen():
    """链子里就地改 ctx 会污染同一次请求的后续步骤（四个方法共用一枚）。"""
    ctx = make_ctx()
    with pytest.raises(FrozenInstanceError):
        ctx.user_id = 9
    with pytest.raises(FrozenInstanceError):
        ctx.llm.model = "别的模型"


def test_not_configured_error_is_a_domain_error():
    """Task 7 靠 `STATUS_BY_ERROR` 把它翻成 409；不在 KnowledgeBaseError 家族里就只会落兜底 500。"""
    assert issubclass(NotConfiguredError, KnowledgeBaseError)
```

- [ ] **Step 2: 跑一次确认 RED**

Run: `cd backend && python -m pytest tests/test_llm_factory.py -q`
Expected: FAIL —`ModuleNotFoundError: No module named 'core.llm_factory'`（先于所有断言发生，这一步不用看断言文本）

- [ ] **Step 3: `exceptions.py` 加一格**

`backend/exceptions.py` 末尾（`AuthError` 之后）追加：

```python
class NotConfiguredError(KnowledgeBaseError):
    """409：账号本身没问题，是"这个账号还没具备问答的前提"——没配 key、没配路由、
    模型名单为空、点了个名单外的模型。四种成因共用一个类：它们对用户的指引都是
    "去设置里补齐"。状态码取 409 而不是 400，因为要改的是服务器上的资源状态（spec 3.4）。"""
```

> 本 Task **不动** `main.py` 的 `STATUS_BY_ERROR`：`test_error_model.py:104-108` 那条覆盖率判据比的是"表里的键集合 == 字面五个类"，多一个没进表的类不会红。接线归 Task 7（那里同时补探针路由），中间态里 `NotConfiguredError` 一个 raise site 都没有，行为零变化。

- [ ] **Step 4: 写 `core/llm_factory.py`**

```python
"""每用户一套 LLM 客户端：凭证从用户行读，不读 Config。

阶段一留下的形状是两枚进程级单例——`RAGSystem.__init__` 建一枚答题用、
`VectorStore.__init__` 再建一枚压缩用。坑 9 的教训（两处构造点早晚分叉）在阶段二
不能重演，所以这里收成全项目**唯一**的构造点，且每请求一次、用完即弃：
`ChatOpenAI(...)` 只是拼参数，不发网络请求，构造成本可以忽略（真连接发生在 invoke 时）。
"""
from dataclasses import dataclass

from langchain_classic.retrievers.document_compressors import LLMChainExtractor
from langchain_openai import ChatOpenAI

from exceptions import NotConfiguredError

# 409 的第一句文案，与设置弹窗（Task 9）的入口名一致——别改成 "前往 settings"。
NOT_CONFIGURED = "还没有配置大模型，请先在设置里填写 API Key 与路由"


@dataclass(frozen=True)
class LLMConfig:
    """一次问答要的三个值。frozen 本身有判据（`test_run_context_is_frozen`）。"""
    api_key: str
    base_url: str
    model: str


@dataclass(frozen=True)
class RunContext:
    """一次问答的"用谁的身份、打哪台模型"。Task 5 的四个链方法各收一枚。

    `user_id` 与 `llm` 必须同源、一起进来：分成两个参数的话就会出现"A 的身份配 B 的 key"，
    而那正是这套隔离唯一不该出现的形状（spec 2.3）。读侧过滤吃的就是这里的 `user_id`，
    所以这一格传错等于越权，不是"少一次比较"的小事。
    """
    user_id: int
    llm: LLMConfig


def llm_config_for(user, model: str) -> LLMConfig:
    """从用户行折成 LLMConfig，key 与路由缺一即拒。

    校验和组装写在同一个函数里而不是两步：分开了就会出现"检查过 api_key、
    组装时读的是另一份 base_url"，而这两格在同一行上，本来就该一起判。
    `model` 由调用方（Task 7 的 `_llm_context`）从模型名单里解析出来——工厂不知道名单。
    """
    if not (user.api_key and user.base_url):
        raise NotConfiguredError(NOT_CONFIGURED)
    return LLMConfig(api_key=user.api_key, base_url=user.base_url, model=model)


def build_llm(ctx: RunContext):
    """答题链：温度 0.7、开流式（原 `rag_system.py:27-33` 一字不动，只换凭证来源）。"""
    return ChatOpenAI(
        api_key=ctx.llm.api_key,
        base_url=ctx.llm.base_url,
        model=ctx.llm.model,
        temperature=0.7,
        streaming=True,
    )


def build_compressor(ctx: RunContext):
    """上下文压缩器：温度 0、不开流式（原 `vector_store.py:42-49`）。

    每请求新建而不是存成属性：`VectorStore` 是 lifespan 里的单例，
    把压缩器挂在它身上就等于让全平台共用一个人的 key——那正是本次要拆掉的东西。
    """
    llm = ChatOpenAI(
        api_key=ctx.llm.api_key,
        base_url=ctx.llm.base_url,
        model=ctx.llm.model,
        temperature=0,
    )
    return LLMChainExtractor.from_llm(llm)
```

- [ ] **Step 5: 跑离线门禁**

Run: `cd backend && python -m pytest -q`
Expected: 全绿；条数比 Task 3 之后多 **9**（以当轮汇总行为准，不预测总数）

- [ ] **Step 6: 提交**

```bash
git add backend/core/llm_factory.py backend/exceptions.py backend/tests/test_llm_factory.py
git -c user.name="31439" -c user.email="31439@local" commit -F /tmp/fe2-task4.txt
```
提交信息：`feat(llm): 每用户一套客户端的工厂 + NotConfiguredError（阶段二 Task 4，只建模块不接线）`

---

## Task 5: `RAGSystem` / `VectorStore` 改吃 `RunContext` + 读侧按用户收窄

阶段二最硬的一次原子改动：四个链方法签名、两个 core 单例的构造、`api/chat.py` 四处调用、34 处测试触点在同一个 Task 里一起改。拆开任何一半都会留下"跑不起来"或"漏过滤"的中间态。

**Files:**
- Modify: `backend/core/rag_system.py`（`__init__:21-41`、四个方法 `:47/:67/:144/:169`、检索读取 `:79/:81/:176/:178`、压缩读取 `:86/:179`、客户端使用 `:57/:112/:157/:209`）
- Modify: `backend/core/vector_store.py`（删 `:41-49`、`create_retriever:93-103`、`get_parent_documents:105-112`、`get_parent_documents_by_metadata:114-131`、import `:5-7`）
- Modify: `backend/api/chat.py`（import `:7`、`_ctx_from_config` 新增、四处 rag 调用 `:41/:50/:75/:79`、两个端点各加 `config=Depends(get_config)`）
- Modify: `backend/main.py:57`
- Test: `backend/tests/test_vector_store.py`（filter pin `:127-141`、回溯 pin `:106-123`、**删** `:144-166`）
- Test: `backend/tests/test_rag_system.py`（`build:65-77`、`StubVectorStore:48-62`、21 处调用、**删** `:356-373`）
- Test: `backend/tests/fakes.py`（`FakeConfig:1-2` 补三键、`FakeRAG:83-114` 四个签名）
- Test: `backend/tests/test_api_chat.py`（`make_client:12-19` 补 get_config 覆盖、5 处 def + 4 处 `super()`）
- Test: `backend/tests/test_llm_factory.py`（追加唯一构造点的结构判据）

**Interfaces:**
- Consumes: Task 4 的 `RunContext`、`LLMConfig`、`build_llm`、`build_compressor`
- Produces: `RAGSystem(db_manager, vector_store, llm_factory=build_llm, compressor_factory=build_compressor)`（**`config` 形参删除**）；`normal_chat(ctx, question, session_id)`、`chat_with_documents(ctx, question, parent_ids, session_id)`、`normal_chat_stream(ctx, question, session_id)`、`chat_with_documents_stream(ctx, question, parent_ids, session_id)`；`create_retriever(parent_ids, user_id)`、`get_parent_documents(child_docs, user_id)`。Task 6 在这四个方法里补落库归属，Task 7 把 ctx 的来源换成用户行。

- [ ] **Step 1: 写读侧过滤的 RED（只改 `test_vector_store.py`）**

`:127-141` 两条 pin 整段换成三条：

```python
def test_retriever_filters_by_pool_and_owner(store):
    """块级允许池 + 主人边界一起下。子块向量两个键都带（add_documents 与迁移补戳），
    所以收窄不需要重新灌库。"""
    store.config = SimpleNamespace(TOP_K=3)
    store.child_vectorstore.as_retriever = lambda search_kwargs: search_kwargs
    kwargs = store.create_retriever(["甲.txt_parent_0"], 7)
    assert kwargs["filter"] == {"$and": [{"parent_id": {"$in": ["甲.txt_parent_0"]}},
                                         {"user_id": {"$in": ["7"]}}]}
    assert kwargs["k"] == 6          # TOP_K * 2 的老规矩没被顺手改掉


def test_retriever_without_pool_still_filters_by_owner(store):
    """空池不等于无边：纯对话链根本不调它，一旦有人调（Task 7 之后可能有），
    漏掉 user_id 就是全库召回。"""
    store.config = SimpleNamespace(TOP_K=3)
    store.child_vectorstore.as_retriever = lambda search_kwargs: search_kwargs
    assert store.create_retriever([], 7)["filter"] == {"user_id": {"$in": ["7"]}}
    assert store.create_retriever(None, 7)["filter"] == {"user_id": {"$in": ["7"]}}


def test_owner_id_is_written_as_a_string_in_the_filter(store):
    """metadata 里存的是字符串（`add_documents:85-86` 与迁移补戳都写 `str(user_id)`）。
    这里传 int 就必须比出字符串：Chroma 的标量相等不做隐式转换，形态一错的表征是
    "永远召回零条"，而不是报错。"""
    store.config = SimpleNamespace(TOP_K=3)
    store.child_vectorstore.as_retriever = lambda search_kwargs: search_kwargs
    assert store.create_retriever([], 41)["filter"]["user_id"] == {"$in": ["41"]}
```

`:106-123` 那条回溯判据的桩要跟着新 `where` 形状改（否则它读的是已经不存在的顶层键）：

```python
def test_get_parent_documents_dedupes_shared_parent():
    """多个子块同属一个父块时只回溯一次（坑 7 的行为面，本次不优化查询次数，只锁语义）。
    回溯也带主人：parent_id 全库唯一只保证"找得回那一块"，不保证"那块是你的"。"""
    vs = VectorStore.__new__(VectorStore)
    calls = []

    class GetStub:
        def get(self, where=None, include=None):
            assert where == {"$and": [{"parent_id": "a_parent_0"}, {"user_id": "7"}]}, where
            calls.append(where["$and"][0]["parent_id"])
            return {"documents": [f"父内容:{where['parent_id']}"],
                    "metadatas": [{"parent_id": where["parent_id"]}]}

    vs.parent_vectorstore = GetStub()
    children = [
        type("D", (), {"metadata": {"parent_id": "a_parent_0"}})(),
        type("D", (), {"metadata": {"parent_id": "a_parent_0"}})(),
        type("D", (), {"page_content": "", "metadata": {}})(),
    ]
    parents = vs.get_parent_documents(children, 7)
    assert calls == ["a_parent_0"]
    assert len(parents) == 1
```

- [ ] **Step 2: 跑一次确认 RED**

Run: `cd backend && python -m pytest tests/test_vector_store.py -q`
Expected: 四条全红——旧 `create_retriever(parent_ids=None)` 多收一个位置参数是 `TypeError`；就算只改调用形状，旧返回的 `{"parent_id": ...}` 也不含 `$and`。**这两组必须先红**：补戳的判据在 `test_migrations.py` 里，读侧过滤此前一条会红的测都没有，正是 spec 2.5 勘误记下的那半笔账。

- [ ] **Step 3: 改 `core/vector_store.py`**

删 `:41-49`（`self.llm` 与 `self.compressor` 整段），import 里的 `ChatOpenAI`（`:5`）与 `LLMChainExtractor`（`:7`）一起删——本文件不再引用它们，留着就是 Step 7 结构判据的红灯。`chromadb`/`Chroma`/`HuggingFaceEmbeddings`/`Document` 四行照旧。

```python
    def create_retriever(self, parent_ids, user_id):
        """创建子文档检索器（只负责初始召回）。

        filter 里恒有 `user_id` 那一半：阶段一只补戳不收窄（`add_documents` 的 docstring
        记的就是这笔账），阶段二把它接上。存的形态是字符串——`add_documents` 与迁移补戳
        都写 `str(user_id)`，这里跟着 `str()` 才对得上（Chroma 的标量相等不做转换）。
        单条件时不套 `$and`：`{user_id: ...}` 是阶段一就在用的形状，少一层是一处少一个错。
        """
        conditions = []
        if parent_ids:
            # 允许池按父块收窄。子块向量本身就带 parent_id 元数据（document_processor.py:81），
            # 所以换过滤字段不需要重新灌库——现存集合里的向量直接可用。
            conditions.append({"parent_id": {"$in": list(parent_ids)}})
        conditions.append({"user_id": {"$in": [str(user_id)]}})
        search_kwargs = {"k": self.config.TOP_K * 2,
                         "filter": conditions[0] if len(conditions) == 1 else {"$and": conditions}}
        # 返回一个 LangChain 检索器对象
        return self.child_vectorstore.as_retriever(search_kwargs=search_kwargs)

    def get_parent_documents(self, child_docs, user_id):
        """根据子文档获取对应的父文档的parent_id"""
        parent_ids = set() # 集合去重，如: 多个子文档可能属于同一个父文档
        for doc in child_docs:
            if 'parent_id' in doc.metadata:
                parent_ids.add(doc.metadata['parent_id'])

        return self.get_parent_documents_by_metadata(list(parent_ids), user_id)

    def get_parent_documents_by_metadata(self, parent_ids, user_id):
        """回溯父块也带主人：子块已经按 user 筛过，理论上拿不到别人的 parent_id，
        但"理论上"在检索链里不等于边界——这里的 $and 是那道真正的墙。"""
        if not parent_ids:
            return []
        parent_docs = []
        for parent_id in parent_ids:
            try:
                results = self.parent_vectorstore.get(
                    where={"$and": [{"parent_id": parent_id}, {"user_id": str(user_id)}]},
                    include=["documents", "metadatas"],
                )
                if results["documents"]:
                    parent_docs.append(Document(
                        page_content=results["documents"][0],
                        metadata=results["metadatas"][0] or {},
                    ))
            except Exception as exc:
                logger.warning("获取父文档失败 parent_id=%s: %s", parent_id, exc)
        return parent_docs
```

- [ ] **Step 4: 改 `core/rag_system.py`**

`__init__`（`:21-41`）——`config` 形参与那段 `ChatOpenAI` 一起删（`self.config` 除构造 LLM 外没有任何别的用处，留着就是死字段）：

```python
    def __init__(self, db_manager, vector_store,
                 llm_factory=build_llm, compressor_factory=build_compressor):
        """两个工厂作为参数注入，为的是链级判据不依赖真 ChatOpenAI。

        测试传 `lambda ctx: 假可运行对象`，生产用默认值，而默认值只可能来自
        `core/llm_factory.py`（坑 9 的收口方式）。注入工厂而不是注入 llm 本身：
        一次请求里答题链与压缩器都要建客户端，且压缩器和答题共用同一枚 ctx；
        把客户端存成属性就等于把某个人的 key 冻在进程级单例上——那正是本次要拆的东西。
        """
        self.db_manager = db_manager
        self.vector_store = vector_store
        self.llm_factory = llm_factory
        self.compressor_factory = compressor_factory

        self.rag_prompt = ChatPromptTemplate.from_messages([... :35-41 原样不动 ...])
```

import 行：删 `from langchain_openai import ChatOpenAI`（`:7`），补 `from core.llm_factory import build_compressor, build_llm`。

四个方法逐处改动（其余行一字不动）：

| 位置 | 现在 | 改成 |
|---|---|---|
| `:47` | `def normal_chat(self, question, session_id):` | `def normal_chat(self, ctx, question, session_id):` |
| `:57` | `self.llm.invoke(...)` | `self.llm_factory(ctx).invoke(...)` |
| `:67` | `def chat_with_documents(self, question, parent_ids, session_id):` | `def chat_with_documents(self, ctx, question, parent_ids, session_id):` |
| `:79` | `create_retriever(parent_ids)` | `create_retriever(parent_ids, ctx.user_id)` |
| `:81` | `get_parent_documents(retrieved_docs)` | `get_parent_documents(retrieved_docs, ctx.user_id)` |
| `:86` | `self.vector_store.compressor.compress_documents(...)` | `self.compressor_factory(ctx).compress_documents(...)` |
| `:112` | `self.rag_prompt \| self.llm` | `self.rag_prompt \| self.llm_factory(ctx)` |
| `:144` | `def normal_chat_stream(self, question, session_id):` | `def normal_chat_stream(self, ctx, question, session_id):` |
| `:157` | `self.llm.stream(...)` | `self.llm_factory(ctx).stream(...)` |
| `:169` | `def chat_with_documents_stream(self, question, parent_ids, session_id):` | `def chat_with_documents_stream(self, ctx, question, parent_ids, session_id):` |
| `:176` | `create_retriever(parent_ids)` | `create_retriever(parent_ids, ctx.user_id)` |
| `:178` | `get_parent_documents(retrieved_docs)` | `get_parent_documents(retrieved_docs, ctx.user_id)` |
| `:179` | `self.vector_store.compressor.compress_documents(...)` | `self.compressor_factory(ctx).compress_documents(...)` |
| `:209` | `self.rag_prompt \| self.llm` | `self.rag_prompt \| self.llm_factory(ctx)` |

> 表里没列 `:49/:105/:148/:201` 的 `get_chat_history(session_id)` 与六处 `save_chat_history(...)`：那是 Task 6 的账，本 Task 不动。`self.llm_factory(ctx)` 在每个方法里只调**一次**、存进局部变量再用（`:57/:112/:157/:209` 各一处）——两枚客户端不改变行为，但会让"传错 ctx"多一个发生位置。

- [ ] **Step 5: 接 `api/chat.py` 与 `main.py:57`**

`api/chat.py` 的 import 换成两行：

```python
from core.llm_factory import LLMConfig, RunContext
from deps import get_config, get_current_user, get_db, get_rag_system
```

`_require_owned_parents` 之后追加过渡形态的 ctx 组装（Task 7 换掉函数体，签名不变）：

```python
def _ctx_from_config(user, config) -> RunContext:
    """Task 5 的过渡形态：凭证仍来自 `.env`（行为一字不变），但 `user_id` 已经是当前用户。

    这一格不是占位——读侧过滤（`create_retriever`/`get_parent_documents`）吃的就是
    `ctx.user_id`，传错就是越权。Task 7 把凭证来源换成用户行、在这里加三条 409，
    所以四个 rag 调用点的形状从本 Task 起不再变化。
    """
    return RunContext(user_id=user.id, llm=LLMConfig(
        api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_BASE_URL, model=config.LLM_MODEL))
```

两个端点各加 `config=Depends(get_config)`（位置在 `user=Depends(get_current_user)` 之后），四处调用补首参：

```python
@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest, db=Depends(get_db), rag=Depends(get_rag_system),
         user=Depends(get_current_user), config=Depends(get_config)):
    """parent_ids 为空即普通对话，用 mode 回传实际走了哪条链（spec 6.2）。"""
    ctx = _ctx_from_config(user, config)
    mode = mode_of(payload.parent_ids)
    if mode == "rag":
        _require_owned_parents(db, payload.parent_ids, user)   # ← 在碰 rag 之前
        try:
            answer, references = rag.chat_with_documents(
                ctx, payload.question, payload.parent_ids, payload.session_id
            )
        ...
    else:
        try:
            answer = rag.normal_chat(ctx, payload.question, payload.session_id)
```

`chat_stream` 里 `ctx = _ctx_from_config(user, config)` 与 `mode = ...` 同样落在 `:70` 之前、也就是 `frames()` 之外（与 `:72-73` 那条注释同一条理由：状态码一旦锁定就再也回不去 409）；两处 stream 调用补 `ctx`。`main.py:57`：

```python
    app.state.rag_system = RAGSystem(app.state.db, app.state.vector_store)
```

- [ ] **Step 6: 接 34 处测试触点（清单逐条）**

34 = 21 处 `test_rag_system.py` 调用 + 9 处桩定义（`fakes.py` 4 + `test_api_chat.py` 5）+ 4 处 `super()`；另有 4 处生产调用点在 `api/chat.py`（Step 5 已接）。

**`tests/fakes.py`**：`FakeConfig` 补三键、`FakeRAG` 四个 def 加 `ctx` 首参（体内不用它）。

```python
class FakeConfig:
    CHROMA_PERSIST_DIR = "fake://chroma"
    # Task 5 的过渡 ctx 组装要读这三格（`api/chat.py::_ctx_from_config`）。
    # 值故意与真 .env 不同：判据看的是"传下去了"，不是"传对了什么"。
    OPENAI_API_KEY = "sk-fake"
    OPENAI_BASE_URL = "https://fake/v1"
    LLM_MODEL = "fake-model"
```

```python
    def chat_with_documents(self, ctx, question, parent_ids, session_id): ...
    def normal_chat(self, ctx, question, session_id): ...
    def chat_with_documents_stream(self, ctx, question, parent_ids, session_id): ...
    def normal_chat_stream(self, ctx, question, session_id): ...
```

**`tests/test_api_chat.py`**：`make_client`（`:12-19`）补一格覆盖——`app.state.config` 在测试里不存在，漏了就是那 30 条一起 500：

```python
    app.dependency_overrides[get_config] = lambda: FakeConfig()
```

（`:3` 之后 import 补 `get_config`（来自 `deps`）与 `FakeConfig`（来自 `fakes`）；`stream_client:218` 复用 `make_client`，不用改。）

5 处 def 加 `ctx` 首参、4 处 `super()` 传 `ctx`；两个 Spy 各记一笔 `ctx.user_id`。下面只给类体的形状：`Boom`（`:274`）与 `SpyStreamRAG`（`:297`）实测是**定义在测试函数体内的局部类**（缩进四格），落笔时保持它们原来的位置与缩进，别顺手提到模块级——那不是本 Task 的改动面，提上去还会让后面所有行号引用失效。

```python
class SpyRAG(FakeRAG):
    def chat_with_documents(self, ctx, question, parent_ids, session_id):
        self.calls.append(("rag", question, list(parent_ids), session_id))
        self.seen_user_ids.append(ctx.user_id)
        return super().chat_with_documents(ctx, question, parent_ids, session_id)

    def normal_chat(self, ctx, question, session_id):
        self.calls.append(("normal", question, session_id))
        self.seen_user_ids.append(ctx.user_id)
        return super().normal_chat(ctx, question, session_id)


class Boom(FakeRAG):                          # :274
    def chat_with_documents_stream(self, ctx, q, ids, sid):
        raise RuntimeError("OperationalError(2003): 密码 hunter2 @ 127.0.0.1:3306")
        yield  # 永不执行；仅这一行让上面的 raise 落在迭代期


class SpyStreamRAG(FakeRAG):                   # :297
    def chat_with_documents_stream(self, ctx, question, parent_ids, session_id):
        self.stream_calls.append(("rag", question, list(parent_ids), session_id))
        self.seen_user_ids.append(ctx.user_id)
        return super().chat_with_documents_stream(ctx, question, parent_ids, session_id)

    def normal_chat_stream(self, ctx, question, session_id):
        self.stream_calls.append(("normal", question, session_id))
        self.seen_user_ids.append(ctx.user_id)
        return super().normal_chat_stream(ctx, question, session_id)
```

`SpyRAG.__init__`/`SpyStreamRAG.__init__` 里补 `self.seen_user_ids = []`。`test_stream_payload_is_forwarded_in_the_right_positions`（`:296-314`，实测只发两次 `post_stream`：一 rag 一 normal）末尾补一条 ctx 判据：

```python
    assert rag.seen_user_ids == [1, 1], "ctx 传错 = 读侧过滤按别人的边界走"
```

> 这一条不新增测，只加一行断言，因为 `FakeUser(user_id=1)` 是这个文件的默认人；`test_api_chat.py:97` 那条 `FakeUser(user_id=5)` 走的是越权路径，已经在钉同一件事。

**`tests/test_rag_system.py`**：`build()`（`:65-77`）换成注入两个工厂，`StubVectorStore`（`:48-62`）删 `compressed` 形参与 `self.compressor`、两个方法签名对齐实现，并在文件顶部加两个 import 与一枚共用 ctx：

```python
from core.llm_factory import LLMConfig, RunContext

# 四个方法各收一枚 ctx，测试里的最小替身。人设为 1：与 fakes.FakeUser 的默认 id 对齐。
CTX = RunContext(user_id=1, llm=LLMConfig(api_key="sk-t", base_url="https://t/v1", model="m"))


class StubVectorStore:
    def __init__(self, parent_docs, retriever_error=None):
        self.parent_docs = parent_docs
        self.retriever_error = retriever_error

    def create_retriever(self, parent_ids, user_id):
        if self.retriever_error:
            raise self.retriever_error
        return SimpleNamespace(invoke=lambda q: ["child"])

    def get_parent_documents(self, retrieved, user_id):
        return self.parent_docs


def build(db, vs, llm, compressed=None):
    """绕开 __init__：真构造会建 ChatOpenAI 客户端。

    阶段二之后 llm 不再挂在 RAGSystem 身上，而是 `llm_factory(ctx)` 的返回值——
    所以这里注入的是工厂。`llm` 形参名保持不变，`compressed` 从 StubVectorStore 搬到这里，
    21 处调用因此只需要补 ctx 首参，别处不动。
    """
    rag = RAGSystem.__new__(RAGSystem)
    rag.db_manager = db
    rag.vector_store = vs
    rag.llm_factory = lambda ctx: llm
    rag.compressor_factory = lambda ctx: SimpleNamespace(
        compress_documents=lambda docs, q: (compressed if compressed is not None else docs))
    rag.rag_prompt = ChatPromptTemplate.from_messages([
        ("system", "上下文信息:\n{context}"),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{question}"),
    ])
    return rag
```

21 处调用逐处补 `CTX` 首参。形态一律是 `rag.normal_chat(CTX, "你好", "s1")`；`:291/:300/:341` 那三条是 `build(...).normal_chat_stream(...)` 内联式，同样只补首参。`:134/:141` 两条是 `build(db, vs, ok_llm()).chat_with_documents(...)`，也一样。

新增一条（Task 5 唯一的隔离行为面）：

```python
def test_retrieval_and_backtrack_ask_with_the_context_user_id():
    """读侧过滤的主人只能来自 ctx。假检索器不真过滤，所以把 `ctx.user_id` 改成常量、
    改成 1、或者整段漏传，其余判据照旧绿——只有这条会红。"""
    seen = []

    class SpyVS(StubVectorStore):
        def create_retriever(self, parent_ids, user_id):
            seen.append(("retriever", parent_ids, user_id))
            return super().create_retriever(parent_ids, user_id)

        def get_parent_documents(self, retrieved, user_id):
            seen.append(("parents", None, user_id))
            return super().get_parent_documents(retrieved, user_id)

    db = StubDb(filenames={7: "甲.txt"}, parents={"p0": 7})
    rag = build(db, SpyVS([parent()]), ok_llm())
    rag.chat_with_documents(RunContext(user_id=42,
                                       llm=LLMConfig("sk", "https://x/v1", "m")), "q", ["p0"], "s1")

    assert seen == [("retriever", ["p0"], 42), ("parents", None, 42)]
```

- [ ] **Step 7: 删两条退役 pin + 补"唯一构造点"结构判据**

删 `tests/test_rag_system.py:356-373`（节标题注释 `# --- 坑 9 ---` 与 `test_answer_llm_takes_the_model_name_from_config`）和 `tests/test_vector_store.py:144-166`（`test_compressor_llm_takes_the_model_name_from_config`）。两处 `__init__` 里的 `ChatOpenAI` 已被删除，判据失去对象；"同源"这一条已由 Task 4 的 `test_build_compressor_is_temperature_zero_and_shares_the_model_name` 接替。

`tests/test_llm_factory.py` 末尾追加：

```python
def test_factory_is_the_only_client_construction_site():
    """坑 9 的语法级收口：全后端只有 llm_factory.py 里出现 `ChatOpenAI(`。

    行为面已由上面几条钉住，这里防的是"有人图省事在端点或链子里再 new 一枚"——
    阶段一的第二处（vector_store 那枚压缩 LLM）当初就是这么长出来的。
    扫源码不扫行为，是因为多一处构造点未必改变任何返回值，只会悄悄分叉。
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    hits = sorted(p.name for p in root.rglob("*.py")
                  if "tests" not in p.parts and "ChatOpenAI(" in p.read_text(encoding="utf-8"))
    assert hits == ["llm_factory.py"]
```

- [ ] **Step 8: 跑离线门禁（一个 pytest 进程、不起 uvicorn、不带 `-m migration`）**

Run: `cd backend && python -m pytest -q`
Expected: 全绿。相对 Task 4 之后 **−2**（删两条退役 pin）**+4**（三条 retriever filter + 一条 ctx 主人判据）。实跑若发现 `test_ownership_isolation.py` 红：那个文件的 `make_isolation_client:133` 已覆盖 `get_config`，用的是同一个 `FakeConfig`，不该红；真红了就是它的假 rag/假库签名落后一步，按 Step 6 的形状补齐，别改实现迁就假对象。

- [ ] **Step 9: 提交**

```bash
git add backend/core/rag_system.py backend/core/vector_store.py backend/api/chat.py backend/main.py backend/tests/fakes.py backend/tests/test_api_chat.py backend/tests/test_rag_system.py backend/tests/test_vector_store.py backend/tests/test_llm_factory.py backend/tests/test_ownership_isolation.py
git -c user.name="31439" -c user.email="31439@local" commit -F /tmp/fe2-task5.txt
```
提交信息：`refactor(rag): 链方法吃 RunContext + 读侧按 user_id 收窄（阶段二 Task 5，坑 9 收成单一构造点）`

> **交付时必说的一条连带**：`$and` 生效后，**没被补过 `user_id` 戳的向量一律召不回来**（表征是"上传成功但问答空召回"，不是报错）。依赖两件事：① Task 3 的迁移补戳已跑过（含崩溃自愈）；② 灌库路径 `add_documents` 一直带 `user_id`。Task 12 的验收判据里有一条专门看这个。

## Task 6: `chat_history.user_id` —— 历史读写按主人收窄

spec 2.2 勘误点名的"同一批工作量"的另一半：Task 5 把 ctx 灌进了签名，本 Task 往那签名里灌真归属。四读六写 + 两枚端点 + 一次迁移归户必须一个 Task 收完——先落写侧就是"存进去读不出"（NULL 行不满足任何 `user_id = ?`），先落读侧就是"历史凭空蒸发"。

**Files:**
- Modify: `backend/core/database.py`（`ChatHistory:92-108` 加列与索引、三方法 `:451/:463/:483`）
- Modify: `backend/core/migrations.py`（`MIGRATED_COLUMNS:30` 三行→四行、`MIGRATED_INDEXES:34` 加一行、新增 `backfill_chat_history`、`run_migrations` 加一步）
- Modify: `backend/core/rag_system.py`（4 处 `get_chat_history:49/:105/:148/:201`、6 处 `save_chat_history:62/:93/:120/:165/:186/:219`）
- Modify: `backend/api/history.py`（`:35`、`:48`，并改掉 `:28-33` 与 `:47` 那两段"阶段二再做"的注释）
- Test: `backend/tests/test_migrations.py`（`:243` 那条逐字 pin + `FakeConn` + 一条新判据）
- Test: `backend/tests/test_rag_system.py`（`StubDb:29`、三处整字典比较 `:98/:153-159/:295`、一条新判据）
- Test: `backend/tests/test_api_history.py`（`HistoryDB:28/:32`、两条既有断言、一条新判据、`make_client:40-41` 的注释）
- Test: `backend/tests/fakes.py`（`FakeOwnedParentsDB:27/:30`）
- Test: `backend/tests/test_ownership_isolation.py`（`:87/:90`）
- Test: `backend/tests/test_error_model.py`（`:154` 那处**位置参数**调用）
- Test: `backend/tests/test_live_database.py`（`:123-136`、`:150-158` 共 11 处调用 + 一条新跨用户判据）

**Interfaces:**
- Consumes: Task 5 的 `ctx`（`ctx.user_id` 是这里唯一的主人来源）、Task 1/3 的迁移骨架
- Produces: `get_chat_history(session_id, *, user_id, limit=10)`、`save_chat_history(session_id, user_message, assistant_message, document_ids=None, used_chunks=None, *, user_id)`、`delete_chat_history(session_id, *, user_id)`（三枚都**强制关键字**）、`backfill_chat_history(conn, user_id) -> int`、`summary["chat_rows_claimed"]`。Task 7 不改这套签名。

- [ ] **Step 1: 写迁移侧的 RED**

`tests/test_migrations.py` 的 `FakeConn`（`:15-84`）先长出一格状态和两条分支。⚠️ **分支必须插在通用 `SELECT COUNT`（`:56`）之前**——`startswith("SELECT COUNT")` 会先吃掉 `SELECT COUNT(*) FROM chat_history ...`，插在后面就是那条通用分支拿到错的行数（这是 `FakeConn` 的 first-match 规矩，Task 3 的 `SELECT API_KEY...` 同一条理由）：

```python
    def __init__(self, existing_columns=(), user_rows=(), owned_doc_ids=(),
                 existing_indexes=(), chat_unowned=3):
        ...
        self.chat_unowned = chat_unowned            # user_id IS NULL 的历史行数
```

```python
        if head.startswith("SELECT COUNT(*) FROM CHAT_HISTORY"):
            return _Result([(self.chat_unowned,)])
        if head.startswith("UPDATE CHAT_HISTORY"):
            self.executed.append(text)
            self.chat_unowned = 0                   # 归户之后不再有 NULL 行：重跑零副作用
            return _Result([])
```

新判据（放在 `backfill_documents` 那组之后）：

```python
def test_backfill_chat_history_claims_unowned_rows_only():
    """老历史全归默认用户：改造前这套系统是单人使用的，行里除了 session_id 没有别的归属证据。

    钉两件事：① 只捡 NULL 行（第二次跑零 UPDATE，与 backfill_documents 同一条幂等纪律）；
    ② 归户发生在计数之后——返回的数字来自 COUNT，不是 UPDATE 的 rowcount，
    因为 SQLAlchemy 的 Connection.rowcount 在假连接上根本没有，且真库上"改了几行"
    与"看到几行无主"本该相等，用后者反而能把不一致暴露出来。
    """
    conn = FakeConn(chat_unowned=3)
    assert migrations.backfill_chat_history(conn, 1) == 3
    assert conn.chat_unowned == 0
    assert any("UPDATE CHAT_HISTORY" in sql.upper() for sql in conn.executed)

    idle = FakeConn(chat_unowned=0)
    assert migrations.backfill_chat_history(idle, 1) == 0
    assert not any("UPDATE CHAT_HISTORY" in sql.upper() for sql in idle.executed)
```

`test_default_identifier_is_the_one_the_spec_names`（`:241-243`）里那条逐字 pin 从 Task 1 的三行扩到四行，并补上 `MIGRATED_INDEXES`（此前无人钉，本次起它也会变长）：

```python
    assert migrations.MIGRATED_COLUMNS == [
        ("documents", "user_id", "INTEGER"),
        ("users", "api_key", "VARCHAR(255)"),
        ("users", "base_url", "VARCHAR(500)"),
        ("chat_history", "user_id", "INTEGER"),
    ]
    assert migrations.MIGRATED_INDEXES == [
        ("documents", "user_id", "idx_documents_user_id"),
        ("chat_history", "user_id", "idx_chat_history_user_id"),
    ]
```

Task 3 改写过的那条 `test_run_migrations_stamps_after_documents_are_claimed` 末尾补一行 `assert summary["chat_rows_claimed"] == 3`（`FakeConn` 缺省就带 3 行无主历史）。

- [ ] **Step 2: 跑一次确认 RED**

Run: `cd backend && python -m pytest tests/test_migrations.py -q`
Expected: 三条红——`AttributeError: module 'core.migrations' has no attribute 'backfill_chat_history'`、pin 的两条列表不等、`KeyError: 'chat_rows_claimed'`。

- [ ] **Step 3: 改 `core/database.py` 的表与三方法**

`ChatHistory`（`:92-108`）加一列一条索引（口径逐字照 `Document:35-38`——`nullable=True` 是必须的：`NOT NULL` 的 ALTER 在已有数据的表上直接失败，而"先落地再归户"正是迁移的全部打法）：

```python
    created_at = Column(DateTime, default=datetime.now)
    # 阶段二才有的归属列。裸 DDL（migrations.add_column）不会加出外键约束，
    # 这里的 ForeignKey 只为 create_all 与关系可读服务——documents.user_id 从阶段一起就是同一状态。
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)

    # 索引
    __table_args__ = (
        Index('ix_chat_history_session_id_created_at', 'session_id', 'created_at'),
        Index('idx_chat_history_user_id', 'user_id'),
        ...原有注释行保持...
    )
```

三个方法（`:451-493`）整体替换：

```python
    # 获取历史聊天记录
    def get_chat_history(self, session_id, *, user_id, limit=10):
        """读侧的 user_id 不是优化，是边界：session_id 由后端 uuid4() 铸造只让它**难猜**，
        而难猜从来不是访问控制（spec 2.2 的原话）。加列之前这句话没处落地，加列之后漏掉就是漏洞。
        """
        session = self.get_session()
        try:
            chats = session.query(ChatHistory).filter(
                ChatHistory.session_id == session_id,
                ChatHistory.user_id == user_id,
            ).order_by(ChatHistory.id.desc()).limit(limit).all()
            return list(reversed(chats))
        finally:
            session.close()

    # 保存历史聊天记录
    def save_chat_history(self, session_id, user_message, assistant_message,
                          document_ids=None, used_chunks=None, *, user_id):
        """user_id 必填且强制关键字：漏传不是"这行暂时没主人"，是这一轮**永远读不回来**
        （NULL 不满足任何 `user_id = ?`）。位置参数会让十个调用点各自有机会漏，
        关键字参数让漏传在导入期就 TypeError。
        """
        session = self.get_session()
        try:
            chat = ChatHistory(
                session_id=session_id,
                user_message=user_message,
                assistant_message=assistant_message,
                document_ids=document_ids,
                used_chunks=used_chunks,
                user_id=user_id,
            )
            session.add(chat)
            session.commit()
        except Exception as e:
            session.rollback()
            # M2-7/M-b：裸 sqlalchemy 异常直上会让流式端点只能兜成"服务器内部错误"，
            # 策展文案永远不可达；这里收成领域异常，回滚与异常链都不丢
            raise StorageError("保存对话历史失败，请稍后重试") from e
        finally:
            session.close()

    def delete_chat_history(self, session_id, *, user_id):
        session = self.get_session()
        try:
            deleted = session.query(ChatHistory).filter(
                ChatHistory.session_id == session_id,
                ChatHistory.user_id == user_id,
            ).delete()
            session.commit()
            return deleted
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
```

- [ ] **Step 4: 迁移侧加一步**

`MIGRATED_COLUMNS`（`:30`）追加 `("chat_history", "user_id", "INTEGER")`、`MIGRATED_INDEXES`（`:34`）追加 `("chat_history", "user_id", "idx_chat_history_user_id")`（Task 1 Step 3 那两个列表各多一行，`ensure_columns`/`ensure_indexes` 的循环不用动）。

`backfill_chat_history` 放在 `backfill_documents`（`:117-125`）之后：

```python
def backfill_chat_history(conn, user_id: int) -> int:
    """老历史整批归默认用户：改造前只有一的人在用，行里没有任何别的归属线索。

    为什么不学 documents 那边先 SELECT 一份清单：documents 的清单是给向量补戳用的
    （第二份存储在 Chroma），chat_history 只有 MySQL 一份，读行数只为让日志会说人话。
    """
    count = conn.execute(
        text("SELECT COUNT(*) FROM chat_history WHERE user_id IS NULL")).fetchall()[0][0]
    if not count:
        return 0
    conn.execute(text("UPDATE chat_history SET user_id = :uid WHERE user_id IS NULL"),
                 {"uid": user_id})
    conn.commit()
    return count
```

`run_migrations`（Task 3 之后的版本）里插一步——位置在 `backfill_documents` 之后、`seed_default_llm` 之前，`summary` 多一个键：

```python
        docs = backfill_documents(conn, user_id)
        chats = backfill_chat_history(conn, user_id)
        ...
    summary = {"columns_added": added, "indexes_added": indexes,
               "default_user_id": user_id, "documents_claimed": docs,
               "chat_rows_claimed": chats,
               "llm_seeded": seed["llm_written"], "model_seeded": seed["model_added"],
               "vectors_stamped": vectors}
```

- [ ] **Step 5: 链子里十个调用点补 `user_id=ctx.user_id`**

四个方法各读一次、共 4 读 + 6 写，全部只加一个关键字参数（`ctx` 已在 Task 5 成为首参，别在这里重新推导主人从哪来）：

| 位置 | 现在 | 加什么 |
|---|---|---|
| `:49` `normal_chat` | `get_chat_history(session_id)` | `, user_id=ctx.user_id` |
| `:62` `normal_chat` | `save_chat_history(session_id=..., user_message=..., assistant_message=...)` | `, user_id=ctx.user_id` |
| `:93` `chat_with_documents`（空检索分支） | 五键齐全 | `, user_id=ctx.user_id` |
| `:105` `chat_with_documents` | `get_chat_history(session_id)` | `, user_id=ctx.user_id` |
| `:120` `chat_with_documents` | 五键齐全 | `, user_id=ctx.user_id` |
| `:148` `normal_chat_stream` | `get_chat_history(session_id)` | `, user_id=ctx.user_id` |
| `:165` `normal_chat_stream` | 三键 | `, user_id=ctx.user_id` |
| `:186` `chat_with_documents_stream`（空检索分支） | 五键齐全 | `, user_id=ctx.user_id` |
| `:201` `chat_with_documents_stream` | `get_chat_history(session_id)` | `, user_id=ctx.user_id` |
| `:219` `chat_with_documents_stream` | 五键齐全 | `, user_id=ctx.user_id` |

- [ ] **Step 6: 两枚历史端点真的按主人读写**

`api/history.py`：`:35` → `db.get_chat_history(session_id, limit=limit, user_id=user.id)`；`:48` → `db.delete_chat_history(session_id, user_id=user.id)`。`get_history` 那段 docstring（`:28-33`）整段换成已经兑现的口径，`clear_history` 上面那句"只上门、不加 user 过滤"（`:47`）一起删——留着比没有更坏，下一个人会照着它写出第三处：

```python
    """读写都按 user.id 收窄（阶段二 Task 6）：登录门只证明"有人"，user_id 才证明"是谁"。

    session_id 由后端 uuid4() 铸造，猜中它是小概率，但"难猜"不是访问控制（spec 2.2）：
    令牌泄漏、日志里躺着的 id、浏览器历史都能把 id 交出去，而 chat_history 是全库共享的一张表。
    """
```

`api/chat.py:21-23` 里那句"得和阶段二的 `chat_history.user_id`、RAGSystem 重接一起改才划算"已过期（那两件事本 Task 就完了），删掉这三句、保留前面"校验发生在门口"的理由。

- [ ] **Step 7: 测试连带触点（逐条，别靠跑出来再说）**

| 文件:行 | 改动 |
|---|---|
| `tests/fakes.py:27` | `def get_chat_history(self, session_id, *, user_id, limit=10):` |
| `tests/fakes.py:30` | `def delete_chat_history(self, session_id, *, user_id):` |
| `tests/test_api_history.py:28-34` | 两个桩改签名，记账形状换成 `self.history_calls.append((session_id, limit, user_id))`、`self.cleared_with = (session_id, user_id)` |
| `tests/test_api_history.py:40-41` | `make_client` 的注释里"阶段一没有按 user 过滤历史的判据"已过期，改写成"阶段二起 user.id 会被读进两条 SQL" |
| `tests/test_api_history.py:101/:105` | `db.history_calls == [("s42", 50, 1)]`、`[("s42", 200, 1)]`（`FakeUser` 默认 id=1） |
| `tests/test_api_history.py:73` | `db.cleared_with == ("s1", 1)` |
| `tests/test_ownership_isolation.py:87/:90` | 与 `fakes.py` 同形加 `*, user_id` |
| `tests/test_rag_system.py:29` | `def get_chat_history(self, session_id, *, user_id, limit=10):`（`:44` 的 `save_chat_history(**kwargs)` 形状不用改） |
| `tests/test_rag_system.py:98/:153-159/:295` | 三处**整字典比较**各补一个键 `"user_id": 1`（`CTX` 的人设 id）——这三条是最容易漏的：加键不改值，逐字比较当场红 |
| `tests/test_error_model.py:154` | `mgr.save_chat_history("s1", "问", "答", user_id=1)`（这一处是**位置参数**调用，漏了就 `TypeError: missing keyword-only 'user_id'`） |
| `tests/test_live_database.py:121-136` | `test_used_chunks_round_trips_through_json(db)` → `(db, probe_user)`，6 处调用各补 `user_id=probe_user.id` |
| `tests/test_live_database.py:139-158` | `test_emoji_survives_the_history_round_trip(db)` 同上，5 处调用 |

> ⚠️ 三条 live 组的既有坑，写在这里省一次往返：① `FakeOwnedParentsDB.owned_parent_ids` 把调用记进 `self.calls`，而 `test_api_chat.py:101` 逐字比较 `db.calls`——**`list_user_models`（Task 7 加）绝不能往 `calls` 里记**，本 Task 的历史方法同理，要记就另开一个列表。② `get_chat_history` 在假库里返回 `[]` 还是返回行都不构成隔离证据，判据只钉"参数传了没有"，真过滤的证据在 live 组。③ live 组要求 `chat_history.user_id` **已经 ALTER 出来**：`create_all` 不会给已存在的表加列，只有 lifespan 的迁移会。所以跑 `-m live` 之前先按 Step 8 补一次 DDL。

- [ ] **Step 8: 先补 DDL，再跑 live 组**

```bash
cd backend && python -c "
from config.config import Config
from core.database import DatabaseManager
from core.migrations import ensure_columns, ensure_indexes
db = DatabaseManager(Config())
with db.engine.connect() as conn:
    print('columns:', ensure_columns(conn), 'indexes:', ensure_indexes(conn))
"
```
只发 DDL、不碰 Chroma（不开第二个 chroma 进程）、不打印任何凭证。Task 1 与 Task 3 加过的列/索引在这一句里一起补齐——**Task 1 的 live 判据也依赖这一句**，本轮把它补在 Task 1 Step 7 之前执行。

Run: `cd backend && python -m pytest tests/test_live_database.py -q`
Expected: 全绿。MySQL 连不上会整组 skip——台账里记"本轮 live 未跑"，不许报成绿。

新判据（同文件末尾追加）：

```python
def test_chat_history_is_invisible_to_another_user(db):
    """跨用户证据只能来自真库：fake 那三枚桩不真过滤，WHERE 少写一句在它们身上照样绿。

    A 写得进、读得出；B 读回空、删掉 0 行。B 的删除返回 0 而不是 1 是本条的牙——
    "GET 加了过滤、DELETE 忘了"是这类改造最常见的半截交付。
    """
    from core.security import hash_password

    a = db.create_user(identifier=f"hist-a-{new_tag()}@local", identifier_type="email",
                       nickname="甲", password_hash=hash_password("p-a"))
    b = db.create_user(identifier=f"hist-b-{new_tag()}@local", identifier_type="email",
                       nickname="乙", password_hash=hash_password("p-b"))
    sid = f"probe-shared-{new_tag()}"
    try:
        db.save_chat_history(session_id=sid, user_message="甲的问", assistant_message="甲的答",
                             user_id=a.id)
        assert [r.user_message for r in db.get_chat_history(sid, user_id=a.id)] == ["甲的问"]
        assert db.get_chat_history(sid, user_id=b.id) == []
        assert db.delete_chat_history(sid, user_id=b.id) == 0
    finally:
        # 先删行再删账号：真库上 create_all 会把 chat_history.user_id 的 FK 约束建出来，
        # 留着引用行就删不掉 users 那一行（AssertionError 中途抛出时也走这里）
        db.delete_chat_history(sid, user_id=a.id)
        _drop_probe_account(db, a.id)
        _drop_probe_account(db, b.id)
```

- [ ] **Step 9: 新离线判据三条 + 跑门禁**

`tests/test_api_history.py`：

```python
def test_history_reads_and_deletes_carry_the_logged_in_user_id():
    """登录门只证明"有人"，user.id 才证明"是谁"。这两格漏传一个，
    拿到别人 session_id 的人就能读走整段历史——uuid 难猜不是边界（spec 2.2）。"""
    db = HistoryDB([])
    make_client(db, user=FakeUser(user_id=99)).get("/api/history/s7")
    assert db.history_calls == [("s7", 50, 99)]

    db = HistoryDB([])
    make_client(db, user=FakeUser(user_id=99)).delete("/api/history/s7")
    assert db.cleared_with == ("s7", 99)
```

`tests/test_rag_system.py`：

```python
def test_history_read_and_write_carry_the_context_user_id():
    """历史的主人只能来自 ctx。假库不真过滤，把 `ctx.user_id` 写成常量 1 或者整段漏传，
    其余 21 条照旧绿——只有这条会红（`CTX` 是人设 1，所以这里另造一枚 42）。"""
    seen = []

    class SpyDb(StubDb):
        def get_chat_history(self, session_id, *, user_id, limit=10):
            seen.append(user_id)
            return super().get_chat_history(session_id, user_id=user_id, limit=limit)

    db = SpyDb(filenames={7: "甲.txt"}, parents={"p0": 7})
    rag = build(db, StubVectorStore([parent()]), ok_llm("答"))
    rag.chat_with_documents(RunContext(user_id=42, llm=LLMConfig("sk", "https://x/v1", "m")),
                            "q", ["p0"], "s1")

    assert seen == [42]                    # rag 链读历史一次（:105 那一枪）
    assert db.saved[0]["user_id"] == 42    # 和写一次
```

Run: `cd backend && python -m pytest -q`
Expected: 全绿。相对 Task 5 之后 **+3**（`test_migrations` 1 + `test_api_history` 1 + `test_rag_system` 1），live 组 **+1**。红在 `DetachedInstanceError` 或 `Unknown column 'chat_history.user_id'` 的话，先回 Step 8 那句 DDL。

- [ ] **Step 10: 提交**

```bash
git add backend/core/database.py backend/core/migrations.py backend/core/rag_system.py backend/api/history.py backend/api/chat.py backend/tests/test_migrations.py backend/tests/test_rag_system.py backend/tests/test_api_history.py backend/tests/test_ownership_isolation.py backend/tests/fakes.py backend/tests/test_error_model.py backend/tests/test_live_database.py
git -c user.name="31439" -c user.email="31439@local" commit -F /tmp/fe2-task6.txt
```
提交信息：`feat(history): chat_history 加 user_id 并按主人读写（阶段二 Task 6，历史归户 + 跨用户不可见）`

> **交付时必说的一条连带**：归户只发生在**跑过迁移**的库上。没跑过的库里老行 `user_id` 仍是 NULL ⇒ 谁都读不到自己的旧历史（表征是"升级之后历史全空"，不是报错）。真服务重启即自愈；只跑 pytest 的话按 Step 8 那句补 DDL + 再跑一次 `backfill_chat_history`。

---

## Task 7: 问答端点吃用户自己的凭证 + 三条 409 门禁（含 advisory ④）

阶段二真正"翻转行为"的一枪：Task 5 的过渡形态（`_ctx_from_config` 读 `.env`）在本 Task 换成读用户行，`NotConfiguredError` 随后进中央映射表拿到 409。签名从 Task 5 起就没再动过，所以这一步只替换一个函数的体与一处依赖注入，四个 rag 调用点零改动。

**Files:**
- Modify: `backend/schemas/chat.py`（`ChatRequest:9-16` 加 `model_name`）
- Modify: `backend/schemas/auth.py`（`MODEL_NOT_IN_LIST:602` 之后加 `EMPTY_MODEL_LIST`）
- Modify: `backend/api/chat.py`（`_ctx_from_config` → `_llm_context`、两个端点的 `config` 依赖撤掉、四处调用不动）
- Modify: `backend/main.py`（`STATUS_BY_ERROR:30-36` 5→6、import 补 `NotConfiguredError`）
- Modify: `backend/tests/fakes.py`（`FakeUser:117-129` 补两格、`FakeOwnedParentsDB` 加 `list_user_models`、`FakeConfig` 撤掉 Task 5 的三键）
- Modify: `backend/tests/test_api_chat.py`（撤 `get_config` 覆盖、两个 Spy 记 `seen_llm`、新判据一节）
- Modify: `backend/tests/test_ownership_isolation.py`（`OwnerAwareDB` 加 `list_user_models`）
- Modify: `backend/tests/test_error_model.py`（探针 dep + 路由 + `CENTRAL_MAP` + 覆盖率 pin）
- Modify: `backend/tests/test_live_stream.py`（advisory ④ 登出 + 一枚 409 环境差异守卫）

**Interfaces:**
- Consumes: Task 4 的 `llm_config_for`/`NotConfiguredError`/`RunContext`、Task 1 的 `list_user_models`、Task 2 的 `MODEL_NOT_IN_LIST`、Task 5 的四个 ctx 签名
- Produces: `_llm_context(db, user, model_name) -> RunContext`、`ChatRequest.model_name`、`STATUS_BY_ERROR[NotConfiguredError] == 409`、`EMPTY_MODEL_LIST`。Task 10 的前端下拉把选中的模型名塞进 `model_name`；Task 11 的横幅吃 `llm_configured` + `models.length`。

- [ ] **Step 1: 写 409 门禁与"翻转"的 RED**

`backend/tests/test_api_chat.py` 末尾追加一节。先给两枚共用工件（`SpyRAG` 已在 `:55`，这里给它补 `seen_llm`；`SpyStreamRAG` 在 `:297` 那条测函数**内部**，同样补）：

```python
# --- 阶段二 Task 7：每用户凭证 + 三条 409 ---

PAYLOAD = {"session_id": "s1", "question": "q", "parent_ids": []}


def configured_db(models=(("qwen-max", True), ("qwen-turbo", False))):
    """默认给两枚：一枚带 is_default，一枚不带——这样"取默认"和"默认缺失取第一个"
    两条解析路径各有输入，而忘传 models 的测不会意外走进空名单分支。"""
    db = FakeOwnedParentsDB()
    db.user_models = list(models)
    return db


def test_the_callers_own_credentials_reach_the_chain():
    """本 Task 的全部理由压在这一条：ctx 里的 key/路由/模型来自 users 行，不再来自 .env。

    Task 5 的过渡形态会把 FakeConfig 那三键（sk-fake / https://fake/v1 / fake-model）传下去，
    这条当场红——它就是"过渡形态不许留在生产里"的哨兵，也是变异自证最省牙的一条：
    把 `_llm_context` 换回 `_ctx_from_config` 只红这一条。
    """
    rag = SpyRAG(answer="答", refs=[])
    make_client(rag, db=configured_db()).post("/api/chat", json=PAYLOAD)
    assert rag.seen_llm == [("sk-fake-user", "https://fake-user/v1", "qwen-max")]


@pytest.mark.parametrize("path", ["/api/chat", "/api/chat/stream"])
def test_a_user_without_credentials_gets_409_and_the_chain_never_runs(path):
    """spec 3.5 的那道门：没配 key 的人点发送，拿到的必须是 409 + 一句能行动的中文，
    而且一次都不许打到 LLM 上（打上去 = 用别人的钱 + 上游一句看不懂的 401）。

    两条路径都得钉：流式端点忘了做门禁时状态码会锁死在 200，失败只能落进 error 帧，
    那时前端看到的是一句"大模型调用失败"而不是"你去设置里填 key"。
    """
    rag = SpyRAG()
    user = FakeUser(api_key=None, base_url=None)
    res = make_client(rag, db=configured_db(), user=user).post(path, json=PAYLOAD)
    assert res.status_code == 409, res.text
    assert res.json() == {"detail": NOT_CONFIGURED}
    assert rag.calls == [] and rag.stream_calls == []


def test_an_empty_model_list_gets_its_own_409_text():
    """有 key 没模型：这不是"没配好 key"，文案得说清缺的是哪一格，否则用户会回去反复填 key。"""
    rag = SpyRAG()
    res = make_client(rag, db=configured_db(models=())).post("/api/chat", json=PAYLOAD)
    assert res.status_code == 409
    assert res.json() == {"detail": EMPTY_MODEL_LIST}
    assert rag.calls == []


def test_a_model_outside_the_list_is_409_with_the_settings_wording():
    """下拉里被人手改过的模型名、或别的账号的模型名：与 `PUT /me/models/default` 说同一句话。"""
    res = make_client(SpyRAG(), db=configured_db()).post(
        "/api/chat", json={**PAYLOAD, "model_name": "gpt-9"})
    assert res.status_code == 409
    assert res.json() == {"detail": MODEL_NOT_IN_LIST}


def test_the_default_model_wins_when_the_payload_names_none():
    rag = SpyRAG(answer="答", refs=[])
    make_client(rag, db=configured_db()).post("/api/chat", json=PAYLOAD)
    assert rag.seen_llm[0][2] == "qwen-max"          # is_default 那一枚


def test_the_first_model_is_the_fallback_when_none_is_default():
    """删掉默认行之后 `default_model` 是 None（Task 2 的裁定），问答侧必须同一口径，
    否则设置里显示有模型、发送却 409。"""
    rag = SpyRAG(answer="答", refs=[])
    make_client(rag, db=configured_db(models=(("m-a", False), ("m-b", False)))).post(
        "/api/chat", json=PAYLOAD)
    assert rag.seen_llm[0][2] == "m-a"


def test_an_explicit_model_name_reaches_the_chain():
    rag = SpyRAG(answer="答", refs=[])
    make_client(rag, db=configured_db()).post("/api/chat", json={**PAYLOAD, "model_name": "qwen-turbo"})
    assert rag.seen_llm[0][2] == "qwen-turbo"
```

新增 7 条函数、collected **+8**（`parametrize` 那条占 2）。Spy 的两处补记（`__init__` 里 `self.seen_llm = []`、`self.stream_calls = []` 已存在）：

```python
class SpyRAG(FakeRAG):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calls = []
        self.seen_llm = []

    def chat_with_documents(self, ctx, question, parent_ids, session_id):
        self.calls.append(("rag", question, list(parent_ids), session_id))
        self.seen_user_ids.append(ctx.user_id)
        self.seen_llm.append((ctx.llm.api_key, ctx.llm.base_url, ctx.llm.model))
        return super().chat_with_documents(ctx, question, parent_ids, session_id)
    # normal_chat 同形
```

文件顶部 import 补三件：`from core.llm_factory import NOT_CONFIGURED`、`from schemas.auth import EMPTY_MODEL_LIST, MODEL_NOT_IN_LIST`。`SpyStreamRAG` 里补同样一行 `seen_llm.append(...)`，并在既有那条 `test_stream_payload_is_forwarded_in_the_right_positions` 末尾（Task 5 已补 `seen_user_ids`，注意它一共两次 `post_stream` ⇒ **两枚**元素）追加：

```python
    assert rag.seen_llm == [("sk-fake-user", "https://fake-user/v1", "qwen-max")] * 2
```

- [ ] **Step 2: 跑一次确认 RED**

Run: `cd backend && python -m pytest tests/test_api_chat.py -q`
Expected: 新条全红（`FakeUser` 没有 `api_key` 属性是 `AttributeError`；`_ctx_from_config` 仍在读 config 所以翻转那条红在值；409 三条现在拿到 200）。旧条若同时红在 `TypeError: FakeOwnedParentsDB has no attribute 'list_user_models'`，属预期连带，Step 4 一起补。

- [ ] **Step 3: 中央映射加那一格**

`main.py`：import 行补 `NotConfiguredError`，表从五格变六格（`test_error_model.py` 的覆盖率 pin 会在 Step 5 同步，中间态跑门禁会红——Step 3/5 之间不要单独提交）：

```python
STATUS_BY_ERROR = {
    UnsupportedDocumentType: 415,
    StorageError: 500,
    RetrievalError: 502,
    LLMError: 502,
    AuthError: 401,
    # spec 3.5 的问答门禁：账号状态没到"能问"的程度。数字选 409 而不是 400/403——
    # 请求本身合法、令牌也有效，冲突的是资源状态（没配 key），客户端修正配置后重发同一请求就能成功。
    NotConfiguredError: 409,
}
```

`backend/exceptions.py` 里 `NotConfiguredError` 已由 Task 4 定义，**不动 STATUS_BY_ERROR 之外**的任何东西（Task 4 特意留到本 Task 才接线，中间态没有任何 raise site）。

- [ ] **Step 4: 端点侧换掉过渡形态**

`schemas/chat.py` 的 `ChatRequest` 加一字段：

```python
    # 用户自带模型名：不在他的名单里就 409（api/chat.py::_llm_context），空着走他的默认模型。
    # 上界 100 与 user_models.name / ModelIn 同源（Task 2 已记这笔账）。
    model_name: str | None = Field(default=None, min_length=1, max_length=100)
```

`schemas/auth.py` 在 `MODEL_NOT_IN_LIST` 之后补一句（两枚常量放同一文件，是因为设置端点与问答端点必须说同一句话）：

```python
EMPTY_MODEL_LIST = "你的模型名单是空的，请先在设置里添加一个模型"
```

`api/chat.py`：把 Task 5 的 `_ctx_from_config` **整函数替换**为下面这枚（函数名换掉，但四个 rag 调用点与两个端点里 `ctx = ...` 那一行的位置一个字都不动——仍在 `mode=` 之前、`frames()` 之外）：

```python
def _llm_context(db, user, model_name) -> RunContext:
    """把"这个人的行 + 他点的那枚模型"折成一次问答的 ctx。三条 409 全在这函数里发。

    凭证那一格不在这里重复检查：`llm_config_for` 是本仓唯一知道"什么算配好了"的地方，
    两处各写一遍迟早分叉（Task 4 的半套配置判据也归它）。

    顺序上先解析模型、后验凭证，代价是"没 key 也没模型"的人先拿到"名单是空的"。
    可接受：界面上那条横幅（Task 11）在发送之前就按 `llm_configured` + `models.length`
    说清了缺哪一格，这枚 409 只是给过期标签页和裸 API 客户端的兜底。
    """
    rows = db.list_user_models(user.id)
    names = [name for name, _ in rows]
    if not names:
        raise NotConfiguredError(EMPTY_MODEL_LIST)
    if model_name and model_name not in names:
        # 这不是"账号没配好"，是这次请求的载荷不对：走 HTTPException，与 add_model 的 409 同形
        raise HTTPException(status_code=409, detail=MODEL_NOT_IN_LIST)
    model = model_name or next((n for n, is_default in rows if is_default), names[0])
    return RunContext(user_id=user.id, llm=llm_config_for(user, model))
```

import 行随之变化：删 `LLMConfig`（不再手工拼）、`get_config`（两个端点撤掉 `config=Depends(get_config)` 形参），补 `from core.llm_factory import RunContext, llm_config_for, NOT_CONFIGURED`、`from exceptions import NotConfiguredError`、`from schemas.auth import EMPTY_MODEL_LIST, MODEL_NOT_IN_LIST`。

> `NOT_CONFIGURED` 在这里只被**测试** import（生产路径由 `llm_config_for` 内部 raise），所以 `api/chat.py` 不 import 它——别为一句文案留一个未使用的 import。

- [ ] **Step 5: fake 侧三处连带（漏一处就是 30 条一起 409）**

`tests/fakes.py`：

```python
class FakeUser:
    """认证依赖在端点测试里的最小替身。

    业务代码只读 `.id`（归属）与 `.nickname`/`.avatar`（出参），阶段二起 `api/chat.py::_llm_context`
    还读 `.api_key`/`.base_url`（凭证）。缺省给一对假凭证而不是 None：问答测有 30 条，
    每条都要 200 才有意义，"没配 key" 那条路径自己传 None。
    """

    def __init__(self, user_id=1, identifier="probe@local", nickname="探针",
                 api_key="sk-fake-user", base_url="https://fake-user/v1"):
        ...
        self.api_key = api_key
        self.base_url = base_url
```

```python
class FakeOwnedParentsDB:
    ...
    def list_user_models(self, user_id):
        """默认一枚带 default：30 条 chat 测要能过 `_llm_context` 的名单检查。

        绝不往 self.calls 里记——`test_api_chat.py:101` 逐字比较那一份，
        多记一笔就把"白名单收到正确的 user_id"那条判据撞红。
        """
        return self.user_models if self.user_models is not None else [("fake-model", True)]
```
`__init__` 补 `self.user_models = None`（`configured_db()` 直接塞列表覆盖它）。`FakeConfig` 撤掉 Task 5 补的三键，`test_api_chat.py::make_client` 撤掉 `app.dependency_overrides[get_config]` 那行与对应 import——过渡形态的残件一律拆干净，"写了没人读"的字段在本仓是负资产（`FakeVectorStore.stamped_user` 的注释记过同一笔账）。

`tests/test_ownership_isolation.py` 的 `OwnerAwareDB` 加同一格（`self.user_models = [("fake-model", True)]` + `list_user_models` 返回它），否则那两条越权判据红在 409 而不是 404。

`tests/test_error_model.py` 四处加一格（探针 dep、路由、`CENTRAL_MAP`、覆盖率 pin 的集合）：

```python
def not_configured_dep():
    """见 unsupported_type_dep。"""


@probe_router.get("/not-configured")
def probe_not_configured(_=Depends(not_configured_dep)):
    return {"unreachable": True}


    (not_configured_dep, "/api/probe/not-configured", NotConfiguredError("还没有配置大模型，请先在设置里填写 API Key 与路由"), 409),
```
覆盖率 pin 改成 `{UnsupportedDocumentType, StorageError, RetrievalError, LLMError, AuthError, NotConfiguredError}`，import 行补 `NotConfiguredError`（从 `exceptions`）。⚠️ 文案在这里**抄一份字面量而不是 import `NOT_CONFIGURED`**：这条测钉的是"这一类配这一个数字"，把常量名接进中央映射的断言里会让 Task 4 的文案改动牵连错误模型测。

- [ ] **Step 6: advisory ④ —— live 测登出，顺带认下 409 这种环境差异**

`tests/test_live_stream.py`：`login_token()`（`:34-50`）只登录不登出，每轮在 `auth_tokens` 留一枚 30 天有效的行（阶段一终审记的那笔数据卫生账）。加一枚 contextmanager，两条测（`:60`、`:92`）的 `token = login_token()` 换成 `with logged_in() as token:`——既有 `try/finally` 留在里面，删历史那一枪先跑、登出后跑（同一枚令牌，顺序不能反）：

```python
@contextmanager
def logged_in():
    """登录 → yield 令牌 → 无论如何登出：advisory ④（阶段一终审的数据卫生账）。

    库内只存 SHA-256，残留行不可被利用，但每轮重跑攒的是永久垃圾。
    finally 里再抛错会盖掉判据本身的红，所以登出的失败只当噪声吞掉。
    """
    token = login_token()
    try:
        yield token
    finally:
        with contextlib.suppress(Exception):
            httpx.post(f"{BASE}/api/auth/logout", timeout=10,
                       headers={"Authorization": f"Bearer {token}"})
```
（文件顶部补 `import contextlib`、`from contextlib import contextmanager`——两者都要，`suppress` 是函数、`contextmanager` 是装饰器。）

阶段二起这两条还多一种**环境差异**：默认用户没配 key/模型时 `/api/chat/stream` 回 409（Task 3 的种子只在 `.env` 三键齐全时写入），旧判据 `assert res.status_code == 200` 会把它当代码坏。在两处 `as res:` 之后、`assert res.status_code == 200` 之前各插一句：

```python
                if res.status_code == 409:
                    pytest.skip(f"默认用户还没配 key/模型（阶段二门禁）：{res.read().decode('utf-8', 'replace')}")
```
`res.read()` 只能在进入流之前调一次——它就在这句话的位置，不在迭代里。

- [ ] **Step 7: 跑门禁（离线 + live）**

Run: `cd backend && python -m pytest -q`
Expected: 全绿。相对 Task 6 之后 **+8**（7 条新函数，其中一条 `parametrize` 占 2）+1（错误模型测的 parametrize 多一格）= **+9**；撤掉的东西不减条数。
Run: `cd backend && python -m pytest tests/test_live_stream.py -q`（需要真服务在 :8000；没起就整组 skip，台账记"未跑"）
Expected: 2 passed，且 `auth_tokens` 里这两轮的行人已不见（`SELECT COUNT(*) FROM auth_tokens WHERE user_id = <默认用户 id>` 手查一次，只读、不打印令牌）。

- [ ] **Step 8: 提交**

```bash
git add backend/schemas/chat.py backend/schemas/auth.py backend/api/chat.py backend/main.py backend/tests/fakes.py backend/tests/test_api_chat.py backend/tests/test_ownership_isolation.py backend/tests/test_error_model.py backend/tests/test_live_stream.py
git -c user.name="31439" -c user.email="31439@local" commit -F /tmp/fe2-task7.txt
```
提交信息：`feat(chat): 问答吃用户自己的 key 与模型 + 三条 409 门禁（阶段二 Task 7，含 advisory ④ live 登出）`

> **交付时必说的两句**：① 从本 Task 起，**没在设置里配好 key/路由/模型的用户一发提问就收 409**（前端横幅在 Task 11 才补，所以 Task 8-10 期间界面会把这句 409 当红横幅显示——文案本身已是中文可行动句，不算坏中间态）；② 默认用户靠 Task 3 的种子步骤自动获得 `.env` 那三键，**老 `.env` 少了 `LLM_MODEL` 的人只会拿到 key 和路由、名单是空的**，第一条 409 就是「名单是空的」——这不是回归，是种子条件没满足。

---

## Task 8: 前端的错误带状态码 + 六个设置封装 + 运行中 401 自动落回登录页（advisory ②）

**Files**
- Modify: `frontend/src/api/client.js`、`frontend/src/api/documents.js`、`frontend/src/api/auth.js`、`frontend/src/composables/useAuth.js`、`frontend/src/App.vue`
- Test: `frontend/tests/client.test.js`、`frontend/tests/documents-api.test.js`、`frontend/tests/api-auth.test.js`、`frontend/tests/useAuth.test.js`、`frontend/tests/App.auth-gate.test.js`

**Consumes:** Task 2 的六个端点形状（`MeOut` 的 `{user}` / `ModelsOut` 的 `{models, default_model}` / 204 的空体）。
**Produces:** `ApiError(message, status)`、`setUnauthorizedHandler()`、`httpError()`、`api/auth.js` 的六个新封装、`useAuth().patchMe()`、`App.vue` 的 `resetWorkspace()`。Task 9 的 `SettingsModal` 只调本 Task 的封装；Task 10 的下拉只读 `patchMe` 之后的 `user.models`；Task 11 的 409 分支只读 `err.status`。

> **为什么状态码非要有不可**：Task 11 要把"未配置"（409）和"网络断了"（0）和"票过期"（401）分开处置。今天 `client.js` 把七种失败压成一句 `Error.message`，界面上只剩"弹横幅 / 不弹"两个选项，`bootstrap()` 那句"401、网络失败、代理宕机都走这里"就是这个塌缩的产物。`status` 一进来，三条路径才各自有归宿。

- [ ] **Step 1: RED —— client.js 的五条新判据**

`frontend/tests/client.test.js` 末尾追加一节。桩函数复用文件里现成的 `jsonResponse` / `stubFetch` / `streamResponse`（`:23-58`），不新造第三种形状。

```js
describe('ApiError：状态码与 401 通知（阶段二 Task 8 + advisory ②）', () => {
  afterEach(() => {
    delete global.fetch
    setUnauthorizedHandler(null)   // 单槽：不清就会把上一个 it() 的闭包留给下一个
  })

  it('非 2xx 的错误对象带真状态码，文案仍是 detail 原文（extends Error 是硬要求）', async () => {
    stubFetch(jsonResponse({ detail: '会话不存在' }, 404))
    const err = await request('/api/history/x').catch((e) => e)
    expect(err).toBeInstanceOf(Error)          // 既有 6 条 rejects.toThrow(文案) 只认 Error 的 message
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(404)
    expect(err.message).toBe('会话不存在')
  })

  it('网络层失败没有响应，状态码是 0 而不是 undefined', async () => {
    global.fetch = vi.fn(async () => { throw new TypeError('Failed to fetch') })
    const err = await request('/api/anything').catch((e) => e)
    expect(err.status).toBe(0)
    expect(err.message).toBe('无法连接后端，请确认 uvicorn 已在 :8000 运行')
  })

  it('流开始前的 409 在 HTTP 阶段就把状态码交出来（Task 11 的地基）', async () => {
    stubFetch(jsonResponse({ detail: '你的模型名单是空的，请先在设置里添加一个模型' }, 409))
    const err = await postStream('/api/chat/stream', {}, () => {}).catch((e) => e)
    expect([err.status, err.message]).toEqual([409, '你的模型名单是空的，请先在设置里添加一个模型'])
  })

  it('401 触发回调、403 不触发；三条出口都算（request / postStream / XHR）', async () => {
    const seen = []
    setUnauthorizedHandler(() => seen.push('cleared'))
    stubFetch(jsonResponse({ detail: '未登录或登录已过期' }, 401))
    await expect(request('/api/documents')).rejects.toBeInstanceOf(ApiError)
    stubFetch(jsonResponse({ detail: '权限不够' }, 403))
    await expect(request('/api/documents')).rejects.toBeInstanceOf(ApiError)
    expect(seen).toEqual(['cleared'])           // 恰好一次：403 不许蹭
  })

  it('回调自己抛错时，原始那句 detail 照样上抛（回调坏了不许顶掉真错误）', async () => {
    setUnauthorizedHandler(() => { throw new TypeError('回调写坏了') })
    stubFetch(jsonResponse({ detail: '未登录或登录已过期' }, 401))
    await expect(request('/api/documents')).rejects.toThrow('未登录或登录已过期')
  })
})
```

import 行补 `ApiError, setUnauthorizedHandler`（`client.js` 的导出面从此有七个名字：`setAuthToken` / `authHeaders` / `detailFromText` / `ApiError` / `setUnauthorizedHandler` / `httpError` / `request` / `postStream`）。

Run: `cd frontend && npx vitest run tests/client.test.js`
Expected: 新增五条里除"403 不触发"那种天然成立的之外都红（`ApiError is not a function` / `setUnauthorizedHandler is not a function`）。**记下当轮汇总行**。

- [ ] **Step 2: 实现 client.js —— 一个构造点 + 一个回调槽**

在 `detailFromText`（`:20-35`）之后、`request`（`:37`）之前插入：

```js
// ApiError：前端唯一需要的"带状态码的错误"。三条 HTTP 出口（request / postStream / 上传的 XHR）
// 共用它，`status = 0` 表示"手上根本没有响应"——网络层失败、流读到一半断、帧解析失败。
// 必须 extends Error：既有 21 条 client.test.js 判据里有一串 rejects.toThrow(文案)，
// 它只读 message；换成普通对象会让那串全红，而红的理由是"测法"不是"行为"。
export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

// advisory ②：运行中撞 401（票在会话中途过期）以前只弹一句横幅，界面还停在"已登录"，
// 用户对着一个必然再 401 的输入框反复点发送。这一格把"该登出"交给界面层决定——
// client.js 不认识 user、不认识 localStorage，它只负责"认出 401"和"喊一声"。
// 单槽不是列表：全项目只有 App.vue 一个订阅者，多个订阅者要先有真实需求。
let onUnauthorized = null

export function setUnauthorizedHandler(handler) {
  onUnauthorized = typeof handler === 'function' ? handler : null
}

function notifyUnauthorized(status) {
  if (status !== 401) return
  // 回调抛错不许盖掉原错误：横幅上该出现的是后端那句 detail，不是一句 TypeError
  try {
    onUnauthorized?.()
  } catch {
    /* 静默：这一格失败给不出可行动的中文，而 401 的文案已经在路上 */
  }
}

// HTTP 状态引起的错误只有一个构造点。三条出口各自 new 一遍的坏法是
// "同一个 401 在两个入口两种文案"——detailFromText 的注释早就为这件事写过一次。
export function httpError(text, status) {
  notifyUnauthorized(status)
  return new ApiError(detailFromText(text, status), status)
}
```

**七处替换点（`client.js` 的 `new Error` 实测 7 处，逐处给状态码，不许漏）**

| 行 | 原文 | 改成 | `status` |
|---|---|---|---|
| `:53` | `throw new Error('无法连接后端，请确认 uvicorn 已在 :8000 运行')` | `throw new ApiError('无法连接后端，请确认 uvicorn 已在 :8000 运行')` | 0（默认） |
| `:55` | `throw new Error(detailFromText(await res.text(), res.status))` | `throw httpError(await res.text(), res.status)` | 真状态码 |
| `:77` | 同 `:53`（postStream 的 fetch 失败） | 同 `:53` | 0 |
| `:81` | `throw new Error(detailFromText(await res.text(), res.status))` | `throw httpError(await res.text(), res.status)` | **409 走这一格** |
| `:86` | `throw new Error('响应不是 SSE 事件流，请检查代理配置')` | `throw new ApiError('响应不是 SSE 事件流，请检查代理配置', res.status)` | 200（照实填，见下） |
| `:100` | `throw new Error('流式响应中断，请重试')` | `throw new ApiError('流式响应中断，请重试')` | 0 |
| `:132` | `throw new Error('流式帧解析失败，请重试')` | `throw new ApiError('流式帧解析失败，请重试')` | 0 |

> `:86` 填的是 200：那句话的成因（反代缓冲、200 落地 HTML 错误页）确实带着一枚成功的响应。填 0 会把它谎报成"连不上"，填 200 才是事实。`:132` 在 `dispatch()` 里，那个函数手上只有帧文本、没有 response，只能 0。
>
> `:76` 与 `:99` 那两句 `if (signal?.aborted) throw err` **一个字都不动**——G-2 的约定是"用户自己取消的原样上抛"，包成 `ApiError` 就等于给它安一个假状态码。这两处是"10 处站点里唯一不替换的两处"，评审若数出 8 处请以此为准（口径：10 处 = `client.js` 7 + `documents.js` 3，本表覆盖 7 处的**构造**，abort 那两行不是构造点）。

- [ ] **Step 3: documents.js 的三处（上传那条 XHR 出口）**

import 行从 `import { authHeaders, detailFromText, request } from './client.js'` 改成：

```js
import { ApiError, authHeaders, httpError, request } from './client.js'
```

`detailFromText` 在这层被 `httpError` 取代——**必须一起删掉旧 import**，留着就是一句死引用（`documents.js` 只有这一处用它）。

| 行 | 改成 | `status` |
|---|---|---|
| `:48` | ``reject(new ApiError(`上传成功但响应不是 JSON（HTTP ${xhr.status}）`, xhr.status))`` | 真状态码（2xx，照实填） |
| `:51` | ``reject(httpError(xhr.responseText, xhr.status))`` | 真状态码；**401 也在这里通知**（上传中途票过期是该自动登出的典型现场） |
| `:54` | `reject(new ApiError('无法连接后端，上传中断'))` | 0 |

`frontend/tests/documents-api.test.js` 新增两条（放在 `:90` 那条 XHR 测之后，同一个 describe 之外新起一节）：

```js
describe('上传的失败出口也带状态码（Task 8）', () => {
  // jsdom 本来就有 XMLHttpRequest，这里换掉必须在 afterEach 里**还原**而不是 delete。
  // （阶段一终审已就 `delete global.XMLHttpRequest` 的措辞纠过一次：delete 是移除，不是还原。）
  const RealXHR = global.XMLHttpRequest

  afterEach(() => {
    global.XMLHttpRequest = RealXHR
    setUnauthorizedHandler(null)
  })

  it('XHR 的非 2xx 失败回 ApiError，状态码来自 xhr.status', async () => {
    let captured
    global.XMLHttpRequest = class {
      constructor() { captured = this; this.upload = {}; this.headers = {} }
      open() {}
      setRequestHeader(k, v) { this.headers[k] = v }
      send() {}
    }
    const file = { name: 'a.txt' }
    const p = uploadDocument(file)
    captured.status = 415
    captured.responseText = JSON.stringify({ detail: '只支持 txt / pdf / docx' })
    captured.onload()
    const err = await p.catch((e) => e)
    expect([err.status, err.message]).toEqual([415, '只支持 txt / pdf / docx'])
  })

  it('上传撞 401 同样触发登出回调（三条出口一条都不能漏）', async () => {
    let captured, hits = 0
    setUnauthorizedHandler(() => { hits += 1 })
    global.XMLHttpRequest = class {
      constructor() { captured = this; this.upload = {} }
      open() {} setRequestHeader() {} send() {}
    }
    const p = uploadDocument({ name: 'a.txt' })
    captured.status = 401
    captured.responseText = JSON.stringify({ detail: '未登录或登录已过期' })
    captured.onload()
    await expect(p).rejects.toBeInstanceOf(ApiError)
    expect(hits).toBe(1)
  })
})
```

import 行补 `ApiError, setUnauthorizedHandler`（该文件现在从 `client.js` 只拿 `setAuthToken`）。

- [ ] **Step 4: api/auth.js —— 六个设置封装 + 四条判据**

`frontend/src/api/auth.js` 末尾追加（**六个都从 `request` 走，`authHeaders` 那一层不用管——阶段一 Task 6 已经把令牌收进 `request`**）：

```js
// —— 阶段二：六个设置端点。这层仍然只做两件事：camelCase → snake_case 的字段翻译、路径拼装。
//    不碰组件状态、不吞错误、不写 localStorage：返回值就是后端响应体
//    （`{user}` / `{models, default_model}` / 204 的 null），谁调用谁负责安置它。

export function updateProfile({ nickname, avatar }) {
  // 与 register 同一条规矩：留空的字段连键都不发。ProfileIn 要求"昵称与头像至少改一样"，
  // 而 nickname 的 min_length=1——多发一个 '' 不是"清空"，是 422。
  const body = {}
  if (nickname) body.nickname = nickname
  if (avatar) body.avatar = avatar
  return request('/api/auth/me', { method: 'PUT', body })
}

export function updatePassword({ oldPassword, newPassword }) {
  // 204：request 那一格回 null。调用方只能靠"没抛错"判成功，拿不到任何回执。
  return request('/api/auth/me/password', {
    method: 'PUT',
    body: { old_password: oldPassword, new_password: newPassword },
  })
}

export function updateLlmConfig({ apiKey, baseUrl }) {
  return request('/api/auth/me/llm', { method: 'PUT', body: { api_key: apiKey, base_url: baseUrl } })
}

export function addModel(name) {
  return request('/api/auth/me/models', { method: 'POST', body: { name } })
}

export function removeModel(name) {
  // 模型名是用户手打的（"qwen 2.5/coder" 这种带空格与斜杠的真存在）。不编码就会把一段路径
  // 劈成两段，坏法是 404「模型不在你的名单里」而不是 422——那句话这时候是假的。
  return request(`/api/auth/me/models/${encodeURIComponent(name)}`, { method: 'DELETE' })
}

export function setDefaultModel(name) {
  return request('/api/auth/me/models/default', { method: 'PUT', body: { name } })
}
```

`frontend/tests/api-auth.test.js` 新增一节（**沿用该文件既有的 `vi.mock('../src/api/client.js', () => ({ request: vi.fn() }))` 桩**，读 `request` 手上的 `body` 对象而不是 fetch 的 JSON 串——理由是那文件开头三段注释，别改道）：

```js
describe('api/auth.js 的六个设置封装（Task 8）', () => {
  it('updateProfile 只发非空字段，且发的是后端的下划线端点与 PUT', async () => {
    await updateProfile({ nickname: '  小明  ', avatar: '' })
    const [path, opts] = request.mock.calls[0]
    expect([path, opts.method]).toEqual(['/api/auth/me', 'PUT'])
    // 不 trim：清洗是后端的事（api/auth.py 的 update_me 自己 strip 并拦空白）。
    // 前端先 trim 会让"我只改了空格"这条 422 判据在界面上消失。
    expect(opts.body).toEqual({ nickname: '  小明  ' })
  })

  it('updatePassword 的两个键名翻成下划线，204 不需要回执', async () => {
    await updatePassword({ oldPassword: 'old-pass', newPassword: 'new-pass' })
    const [path, opts] = request.mock.calls[0]
    expect([path, opts.method]).toEqual(['/api/auth/me/password', 'PUT'])
    expect(opts.body).toEqual({ old_password: 'old-pass', new_password: 'new-pass' })
  })

  it('updateLlmConfig 的键名是 api_key / base_url（这一处最容易被顺手写成 camelCase）', async () => {
    await updateLlmConfig({ apiKey: 'sk-abcdef1234567890', baseUrl: 'https://vLLM.internal/v1' })
    expect(request.mock.calls[0][1].body).toEqual({
      api_key: 'sk-abcdef1234567890', base_url: 'https://vLLM.internal/v1',
    })
  })

  it('removeModel 编码路径段，setDefaultModel 打到 /default 且 body 只剩 name', async () => {
    await removeModel('qwen 2.5/coder')
    const [path] = request.mock.calls[0]
    expect(path).not.toContain(' ')
    expect(path.startsWith('/api/auth/me/models/qwen%202.5%2Fcoder')).toBe(true)
    await setDefaultModel('qwen-max')
    expect([request.mock.calls[1][0], request.mock.calls[1][1].body])
      .toEqual(['/api/auth/me/models/default', { name: 'qwen-max' }])
  })
})
```

> **带 `/` 的模型名是已知窄口，不是本 Task 的 bug**：`encodeURIComponent` 送出 `%2F`，Starlette 会把它当一段路径收进来（路由的 `[^/]+` 匹配的是编码后的串）。但若某天 Vite 代理或线上 nginx 归一化 `%2F`，删除就会 404。Task 12 的浏览器判据里手测一次带斜杠的模型名，失败就**记进台账当已知边界**，不许改道成 query 参数（后端路由 `DELETE /me/models/{name}` 已在 Task 2 钉死）。

- [ ] **Step 5: useAuth —— `clearAuth` 提到模块级 + `patchMe`**

`clearAuth` 现在是 `useAuth()` **函数内**的声明（`:100-104`）。它只碰模块级的 `TOKEN_KEY` / `setAuthToken` / `user`，所以提到模块级零风险；不提的后果是：以后任何模块作用域的注册语句拿到的都是一个不存在的名字。

把 `:100-104` 那五行从函数体内**移出**到 `useAuth()` 之后（函数体末尾的 `return` 照旧带上 `clearAuth`，调用面不变），然后追加：

```js
export function useAuth() {
  // ……（bootstrap / signUp / signIn / signOut 原样）……

  function patchMe(nextUser) {
    // 设置保存成功后用后端回的整行**整体覆盖**，不在本地拼半份：
    // 只改 nickname 一个键的话，api_key_masked、default_model 这些"只有后端知道"的字段
    // 就留在上一次的值上，界面上会出现"改名成功但头像还是旧的"这种真假混合的刷新。
    if (nextUser) user.value = nextUser
  }

  return { user, authError, authBusy, isLoggedIn, bootstrap, signUp, signIn, signOut, clearAuth, patchMe }
}
```

`frontend/tests/useAuth.test.js` 新增两条。**该文件 `:6-8` 的 `vi.mock('../src/api/auth.js')` factory 保持四个键**——本 Task 没有往 `useAuth.js` 里新增任何对 `api/auth.js` 的 import（六个封装归 `SettingsModal`，Task 9）。
> ⚠️ 记一条给未来的连带规矩：`vi.mock` 的 factory 是**整体替换模块**，以后往 `useAuth.js` 里加任何 `api/auth.js` 的新封装，这个 factory 必须同步补键，否则拿到的是 `undefined`，红的理由是 mock 落后不是行为坏了。

```js
  it('patchMe 用后端回的整行覆盖 user，传空值时一个字段都不动', () => {
    getMe.mockResolvedValue({ user: USER })
    localStorage.setItem('auth_token', 'p'.repeat(43))
    const { bootstrap, patchMe, user } = useAuth()
    return bootstrap().then(() => {
      patchMe({ ...USER, nickname: '改名了', models: ['qwen-max'] })
      expect(user.value.nickname).toBe('改名了')
      expect(user.value.models).toEqual(['qwen-max'])
      patchMe(null)          // 204 那类端点回 null：不许把 user 抹成 null
      expect(user.value.nickname).toBe('改名了')
    })
  })

  it('clearAuth 是模块级的同一份：两次 useAuth() 调用共享它（401 回调要的就是这件事）', () => {
    getMe.mockResolvedValue({ user: USER })
    localStorage.setItem('auth_token', 'q'.repeat(43))
    return useAuth().bootstrap().then(() => {
      localStorage.setItem('auth_token', 'r'.repeat(43))
      useAuth().clearAuth()   // 换一个调用方
      expect(useAuth().isLoggedIn.value).toBe(false)
      expect(localStorage.getItem('auth_token')).toBe(null)
    })
  })
```

- [ ] **Step 6: App.vue —— `resetWorkspace()` 抽出来，401 与登出共用**

`handleSignOut`（`:73-91`）的清理组现在是"点退出"独享的。advisory ② 要的自动登出走的是另一条触发路径（网络层认到 401），清理动作**必须完全一致**——否则"退出清得干净、票过期清不干净"就是最难查的那种不对称。

抽出 `resetWorkspace`，两个调用方共用：

```js
function resetWorkspace() {
  // 界面此刻换成登录页，但 App 实例还在、这些 ref 也还在：不清的话下一个人登录后
  // 会在 enterWorkspace 覆盖之前瞥见上一个账号的文件名。documents/queue/messages 都是
  // composable 返回的 ref，直接赋空数组就行；选中项必须走 clearSelection（它同时回写 localStorage）。
  clearSession()
  // authError 不在 clearAuth() 的账上（那边只清令牌与 user），而登出后整屏换成登录页：
  // 这里清的是上一次登录尝试留下的文案，别让它盖到下一个人的空表单。
  authError.value = ''
  documents.value = []
  queue.value = []
  messages.value = []
  clearSelection()
  error.value = ''
  pickerOpen.value = false
}

async function handleSignOut() {
  // 先掐掉在飞的流：不掐的话这条流会在登出之后把答案写进已经换人的界面，
  // 而 useChat 的 done 记账会让它名正言顺地留在屏上
  abortStream()
  await signOut()      // 后端失败已在 useAuth 里被 catch 吞掉，所以这里一定走到下面的清理
  resetWorkspace()
}

// advisory ②：运行中撞 401（票在会话中途过期）自动落回登录页，清理与点「退出登录」一字不差。
// 这里**不发** /api/auth/logout：票已经死了，那一枪只会再触发一次 401 回调，形成环。
// 也不弹横幅——文案的归宿由调用失败的那条链路自己决定（useChat.send 写 error、
// useDocuments.refresh 写 listError），本函数只负责"这家机器不再是你"。
function handleSessionLost() {
  abortStream()
  clearAuth()          // 这一句是"整屏落回登录页"的唯一开关（v-if 的 isLoggedIn 靠它）
  resetWorkspace()
}

// 注册在 App 的 setup 里而不是 useAuth 的模块作用域：handler 要写的那批 ref
// 全都活在这一层（documents/queue/messages/pickerOpen/…）。
// onBeforeUnmount 摘掉：测试里 App 会被反复挂载，留着上一个实例的闭包
// 会让下一个 it() 的 401 写进一棵已经不存在的树——那种红查起来像"测坏了"。
onMounted(() => setUnauthorizedHandler(handleSessionLost))
onBeforeUnmount(() => setUnauthorizedHandler(null))
```

`import { computed, onBeforeUnmount, onMounted, ref } from 'vue'` 补 `onBeforeUnmount`；`import { setUnauthorizedHandler } from './api/client.js'` 新增一行；`useAuth()` 的解构（`:19`）补 `clearAuth`。

> **重入是必然的，`resetWorkspace` 必须幂等**：`enterWorkspace()` 的三拍（refresh → hydrate → restore）都可能各自撞 401，每撞一次回调就跑一遍 `handleSessionLost`。里面全是"赋空值/`removeItem`"，第二遍相对第一遍零可观测差异——下面那条判据里的"只有一个账号态"就是这个意思，别为它加去重标志。

`frontend/tests/App.auth-gate.test.js` 新增一条（放在既有的三条之后；**该文件现有 3 条 `it()`**，本 Task 加到 4 条）。它必须走该文件既有的口径：**只 stub `fetch`，不 mock 任何 composable**。

```js
  it('运行中撞 401：整屏落回登录页，清理与点退出那条一字不差，且不发 logout', async () => {
    // 把 documents 那一枪改成 401（其余照旧 200）：bootstrap 的 /api/auth/me 先成功，
    // 于是"已经在工作区里"这个前置条件成立，401 是会话中途来的——正是 advisory ② 的场景。
    seedLoggedIn()
    const route = ROUTES.find((r) => r.prefix === '/api/documents')
    const original = [route.status, route.body]
    route.status = 401
    route.body = { detail: '未登录或登录已过期' }
    try {
      const app = await mountApp()
      expect(app.find('.auth-screen').exists()).toBe(true)     // 整屏落回，不是"渲染但禁用"
      expect(app.find('.user-rail').exists()).toBe(false)
      // 三个键一起清（与点退出那条同一组判据）
      expect(localStorage.getItem('auth_token')).toBe(null)
      expect(localStorage.getItem('session_id')).toBe(null)
      expect(localStorage.getItem('selected_parent_ids')).toBe('[]')
      // vm 层：DOM 此时已整棵卸载，屏上没有残留可断——这条口径见本文件 :183-190 那段注释
      expect({ docs: app.vm.documents.length, msgs: app.vm.messages.length })
        .toEqual({ docs: 0, msgs: 0 })
      // 判据的另一半：自动登出**不许**补发 logout（那一枪必再 401，回调就成了环）
      expect(calls.filter((c) => c.url.startsWith('/api/auth/logout'))).toEqual([])
    } finally {
      [route.status, route.body] = original
    }
  })
```

> `ROUTES`（`:47-53`）是模块级常量数组，改元素再还原是这条测唯一可行的注入方式——别换成 `vi.stubGlobal` 重写 fetch，那会绕过真实的 `client.js`，`status`/回调这两个本 Task 的交付物就都没被测到。

- [ ] **Step 7: 全量门禁**

Run: `cd frontend && npm test`
Expected: 全绿。**基线核对**：阶段一终态是 `117 passed / 13 文件`（`2026-10-07` 实测），本 Task 设计上新增 **14 条**（`client.test.js` 5、`documents-api.test.js` 2、`api-auth.test.js` 4、`useAuth.test.js` 2、`App.auth-gate.test.js` 1）⇒ 汇总行应为 **131 passed**。不符就以当轮汇总行为准、把差异记进台账（`docs/superpowers/plans/` 里这份计划用 `>` 修订块回写），**不许改测凑数**。

变异自证三条（台账记实数）：① 把 `httpError` 里的 `notifyUnauthorized(status)` 删掉 → 那条 401 测与"运行中撞 401"整条红；② 把 `:81` 换回 `new Error(...)` → `status` 断言红；③ 把 `handleSessionLost` 里的 `clearAuth()` 删掉 → `.auth-screen` 那句红（工作区还在），证明"落回登录页"确实只由它开关。

- [ ] **Step 8: 提交**

```bash
git add frontend/src/api/client.js frontend/src/api/documents.js frontend/src/api/auth.js frontend/src/composables/useAuth.js frontend/src/App.vue frontend/tests/client.test.js frontend/tests/documents-api.test.js frontend/tests/api-auth.test.js frontend/tests/useAuth.test.js frontend/tests/App.auth-gate.test.js
git -c user.name="31439" -c user.email="31439@local" commit -F /tmp/fe2-task8.txt
```
提交信息：`feat(frontend): ApiError 带状态码 + 六个设置封装 + 运行中 401 自动登出（阶段二 Task 8，含 advisory ②）`

> **交付时必说**：本 Task 之后，`bootstrap()` 那条"401 也静默清凭证"的路径与本 Task 的回调**重叠**了（一次过期票会跑两遍 `clearAuth`）。这是刻意的：`bootstrap` 的 catch 不知道也不该知道状态码，回调不知道那是启动期还是运行期。幂等让重叠无害，去重要引入一个"是不是启动期"的判断，代价大于收益。

---

## Task 9: `SettingsModal.vue` —— 四段设置弹窗 + ⚙ 解禁

**Files**
- Create: `frontend/src/components/SettingsModal.vue`
- Modify: `frontend/src/App.vue`（`⚙` 解禁、挂载弹窗、`railAvatar`）、`frontend/src/styles/layout.css`（追加一节，**不新增 `<style>` 块**）
- Test: `frontend/tests/SettingsModal.test.js`（**新建文件 ⇒ 前端测试文件数 13 → 14**）

**Consumes:** Task 8 的六个封装 + `patchMe`；Task 2 的 `UserOut` 十键（`llm_configured` / `llm_base_url` / `api_key_masked` / `models` / `default_model`）与 `ModelsOut`。
**Produces:** `SettingsModal` 组件（`props: 无`，`emits: ['close']`）、`App.vue` 的 `settingsOpen`、`.settings-*` 类名。Task 11 的横幅靠 `settingsOpen` 打开这个弹窗；Task 10 的下拉靠本 Task 写进 `user.models` 的名单。

- [ ] **Step 1: RED —— SettingsModal.test.js 建文件，八条判据**

新文件用 `vi.mock('../src/api/auth.js')` **整体替换**该模块（Task 8 已把 factory 的规矩写清：列全六个新名字，否则拿到 `undefined`）。`user` 是 `useAuth` 的模块级 ref，测试直接写它——这是本仓唯一能"以已登录身份挂载弹窗"的做法（`App.auth-gate.test.js:155-164` 的 `vm` 通道在这里不适用，因为弹窗不是 App 的子组件的 setupState）。

```js
// SettingsModal 的四段各自把三件事钉死：发出去的字段名、成功之后 user 怎么变、
// api_key 原文在界面上出现过没有。第三件是全局铁律（决策 5 + spec 3.1），所以它有独立判据。
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/api/auth.js', () => ({
  updateProfile: vi.fn(), updatePassword: vi.fn(), updateLlmConfig: vi.fn(),
  addModel: vi.fn(), removeModel: vi.fn(), setDefaultModel: vi.fn(),
}))

import { addModel, removeModel, setDefaultModel, updateLlmConfig, updatePassword, updateProfile }
  from '../src/api/auth.js'
import { flushPromises, mount } from '@vue/test-utils'    // 判据本体都等 promise，不用 nextTick

import SettingsModal from '../src/components/SettingsModal.vue'
import { ApiError } from '../src/api/client.js'          // 判据 #3/#6 要造带状态码的错误
import { useAuth } from '../src/composables/useAuth.js'

const ME = {
  id: 1, identifier: 'a@b.com', identifier_type: 'email', nickname: '小明', avatar: 'auto',
  llm_configured: true, llm_base_url: 'https://fake/v1', api_key_masked: 'sk-****7890',
  models: ['qwen-max'], default_model: 'qwen-max',
}

function mountModal() {
  useAuth().user.value = { ...ME }
  return mount(SettingsModal)
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  useAuth().clearAuth()
  updateProfile.mockResolvedValue({ user: { ...ME, nickname: '改名了' } })
  updatePassword.mockResolvedValue(null)                    // 204
  updateLlmConfig.mockResolvedValue({ user: { ...ME, api_key_masked: 'sk-****9999' } })
  addModel.mockResolvedValue({ models: ['qwen-max', 'qwen-turbo'], default_model: 'qwen-max' })
  removeModel.mockResolvedValue({ models: ['qwen-max'], default_model: 'qwen-max' })
  setDefaultModel.mockResolvedValue({ models: ['qwen-max', 'qwen-turbo'], default_model: 'qwen-turbo' })
})
```

八条 `it()`（逐条给判据本体，别写成"渲染正常"那种空壳）：

1. **昵称保存只把非空字段交给 `updateProfile`，成功后 `user` 整行被后端回执覆盖**
   ```js
   const w = mountModal()
   await w.find('.settings-nickname-input').setValue('  改名了  ')
   await w.find('.settings-profile-save').trigger('click')
   await flushPromises()
   expect(updateProfile).toHaveBeenCalledWith({ nickname: '  改名了  ', avatar: 'auto' })
   expect(useAuth().user.value.nickname).toBe('改名了')   // trim 是后端做的，前端照抄回执
   ```
   变体：`setValue('   ')`（纯空白）⇒ `updateProfile` **一次都不调**，`.settings-profile-error` 出"昵称不能是空白"。（本地拦一句的理由写进注释：后端会回 422，但那句话在弹窗里读起来像"我没打上字"。）
2. **api_key 的输入框是 `type="password"`，且保存后整屏文本里搜不到原文**（三条铁律的界面侧唯一守卫）
   ```js
   const w = mountModal()
   await w.find('.settings-apikey-input').setValue('sk-abcdef1234567890')
   await w.find('.settings-llm-save').trigger('click')
   await flushPromises()
   expect(w.find('.settings-apikey-input').attributes('type')).toBe('password')
   expect(w.text()).not.toContain('sk-abcdef1234567890')   // 原文绝不上屏
   expect(w.find('.settings-masked').text()).toContain('sk-****9999')
   expect(w.find('.settings-apikey-input').element.value).toBe('')  // 提交即从状态里抹掉
   ```
3. **`updateLlmConfig` 失败：`user` 一行不变，错误只落在 `.settings-llm-error`**
   `updateLlmConfig.mockRejectedValue(new ApiError('路由必须以 http:// 或 https:// 开头', 422))`（`ApiError` 从 `../src/api/client.js` import，判据要的就是"带状态码的那种错误"这一形状）⇒
   ```js
   expect(useAuth().user.value.api_key_masked).toBe('sk-****7890')   // 失败不许长得像成功
   expect(w.find('.settings-masked').text()).toContain('sk-****7890')
   expect(w.find('.settings-llm-error').text()).toContain('路由必须以 http:// 或 https:// 开头')
   expect(w.find('.settings-profile-error').exists()).toBe(false)    // 也别串到隔壁两段
   ```
4. **改密码的两道本地门禁 + 204 之后清空表单**：`newPassword` 只有 5 位（< 后端的 `PASSWORD_MIN = 6`）⇒ `updatePassword` **一次都不调**、`.settings-password-error` 出"新密码至少 6 位"；新旧填成同一个串 ⇒ 同样不调、文案"新密码不能和原密码相同"；`mockResolvedValue(null)` 走成功 ⇒ 两个输入框的 `element.value` 都是 `''`。
   > **没有"确认新密码"那一格**（弹窗里就多打一遍的收益不抵一次字段错位）：所以本地门禁是「长度」与「不许和旧的相同」两条，第三条「两次输入一致」是有意不做的。判据别去凑那条——凑出来的测会钉住一个不存在的输入框。
   > 清空这条是安全判据：204 没有任何回执可显示，不清的话两个明文密码就留在 DOM 里等下一个坐到电脑前的人（F12 一眼）。
5. **加模型：`addModel` 成功后名单渲染出两项，且 `default_model` 照抄后端回执**（`ModelsOut` 不是整行 user ⇒ 弹窗必须把两个键**合并**进 `user`，别的键保持原值——判据：加完之后 `user.value.api_key_masked` 仍是 `'sk-****7890'`）。
6. **重复添加撞 409：错误行出现、名单一条不减**（后端那句「该模型已在你的名单里」原样上屏）。
7. **删除当前默认：`removeModel` 的回执 `default_model` 是新单项** ⇒ `.settings-model-row` 上"默认"标记落在它身上（钉"读侧没有 default 就取第一个"这条口径在界面上同样成立）。
8. **关闭三态**：点遮罩 ⇒ `emitted('close')`；Escape ⇒ 同；点弹窗内部（`.settings-panel`）⇒ **不关**。抄 `ChunkPickerModal.vue:72-79` 的两个函数，判据也要抄那边缺的那一条（弹窗内点击误关是老病根）。

Run: `cd frontend && npx vitest run tests/SettingsModal.test.js`
Expected: 整文件红（组件不存在，`Failed to resolve` / 无法 import）。记下当轮汇总行。

- [ ] **Step 2: 实现 SettingsModal.vue**

```vue
<script setup>
import { onMounted, onUnmounted, reactive, ref } from 'vue'

import {
  addModel, removeModel, setDefaultModel, updateLlmConfig, updatePassword, updateProfile,
} from '../api/auth.js'
import { useAuth } from '../composables/useAuth.js'

const emit = defineEmits(['close'])

// 直接吃 useAuth() 的模块级单例，不从 App.vue 往下传 props：
// 设置弹窗改的就是"当前这个人"，传一层会让 user 出现两份真相——
// 这个项目不引 Pinia（spec 5.1），代价就是组件要么自己 import composable，要么当纯展示件。
// 本弹窗有写动作，所以走 import。
const { user, patchMe } = useAuth()

// 预设头像：与 backend/api/auth.py 的 AVATARS 同源（Task 2）。改动必须两处一起，
// 漏一处的表征是"界面能选出一个后端必拒 422 的值"。'auto' 不是图片，是"用昵称首字母"的编码。
const AVATARS = ['auto', '😀', '🤖', '🦊', '🐼', '🚀']
const AVATAR_LABELS = { auto: '昵称首字母', '😀': '笑脸', '🤖': '机器人', '🦊': '狐狸', '🐼': '熊猫', '🚀': '火箭' }

// 口令长度门槛：实测 `backend/schemas/auth.py:13` 是 `PASSWORD_MIN = 6`，
// `frontend/src/components/AuthPanel.vue:14` 也早已本地写死 6（同一个口径，后端是权威）。
// 这里再抄一次是第三处副本——项目没有跨端共享常量层，改后端下限必须三处一起改，
// 漏一处的表征是"注册能过、改密码被本地拦"或反过来。数值不许自创。
const PASSWORD_MIN = 6

// 回填只发生在 setup 这一次：弹窗每次都是 v-if 新挂载的（见 App.vue），
// 所以"打开时看到的就是当前值"由挂载时机保证，不需要 watch user。
const profile = reactive({ nickname: user.value?.nickname ?? '', avatar: user.value?.avatar ?? 'auto' })
const password = reactive({ oldPassword: '', newPassword: '' })
// baseUrl 回填（它是可明文显示的），apiKey **永远不回填**：库里那串不该回到输入框里。
const llm = reactive({ apiKey: '', baseUrl: user.value?.llm_base_url ?? '' })
const modelDraft = ref('')

// 四段各一个错误位：改密码失败不该把模型名单也标红。全局那条 error 属于聊天链路
// （useChat 持有、挂在聊天框上方），借它会把设置错误显示到一个已经滚动看不见的地方。
const profileError = ref('')
const passwordError = ref('')
const llmError = ref('')
const modelsError = ref('')
// 同时只让一个动作在飞：四个保存按钮共用它。连点两次「添加模型」会让后端先 409 再成功，
// 名单顺序取决于两个请求谁先落地——那是最难复现的一种乱。
const busy = ref('')

async function run(kind, action, onOk) {
  busy.value = kind
  try {
    onOk(await action())
    if (kind === 'password') {
      // 成功之后清空表单：204 没有回执，不清的话两个明文密码就留在 DOM 里等下一个人
      password.oldPassword = ''
      password.newPassword = ''
    }
  } catch (err) {
    setKindError(kind, err.message)
  } finally {
    busy.value = ''
  }
}

function setKindError(kind, text) {
  if (kind === 'profile') profileError.value = text
  else if (kind === 'password') passwordError.value = text
  else if (kind === 'llm') llmError.value = text
  else modelsError.value = text
}

function saveProfile() {
  if (!profile.nickname.trim()) {
    // 本地先拦一句：后端会回 422（min_length=1 + strip 后拦空白），但那句在弹窗里
    // 读起来像"我没打上字"。发出去一次再懂，代价比这句话大。
    profileError.value = '昵称不能是空白'
    return
  }
  // 值原样送出，trim 只在本地判空时用：清洗是 api/auth.py 的事，前端抢先改会分叉
  return run('profile', () => updateProfile({ nickname: profile.nickname, avatar: profile.avatar }),
             (res) => patchMe(res.user))
}

function savePassword() {
  if (password.newPassword.length < PASSWORD_MIN) {
    passwordError.value = `新密码至少 ${PASSWORD_MIN} 位`   // 见文件顶部：与后端 6 同源，不许自创
    return
  }
  if (password.oldPassword === password.newPassword) {
    passwordError.value = '新密码不能和原密码相同'
    return
  }
  return run('password', () => updatePassword({ ...password }), () => { passwordError.value = '' })
}

function saveLlm() {
  if (!llm.apiKey.trim() || !llm.baseUrl.trim()) {
    llmError.value = 'api_key 与路由都要填，只填一半后端会拒'
    return
  }
  return run('llm', () => updateLlmConfig({ apiKey: llm.apiKey, baseUrl: llm.baseUrl }), (res) => {
    llm.apiKey = ''        // 提交成功立刻从组件状态里抹掉（错误路径故意不清：让用户能改完直接重试）
    patchMe(res.user)
  })
}

function applyModels(out) {
  // 三个模型端点回的是 ModelsOut（只有名单与默认），不是整行 user：就地合并这两个键，
  // 别的键（api_key_masked 那些"只有后端知道"的值）保持上一次回执。
  patchMe({ ...user.value, models: out.models, default_model: out.default_model })
}

function submitModel() {
  const name = modelDraft.value.trim()
  if (!name) {
    modelsError.value = '模型名不能是空白'
    return
  }
  return run('model-add', () => addModel(name), (out) => {
    modelDraft.value = ''
    applyModels(out)
  })
}

function dropModel(name) {
  return run(`model-drop:${name}`, () => removeModel(name), applyModels)
}

function makeDefault(name) {
  return run(`model-default:${name}`, () => setDefaultModel(name), applyModels)
}

function onKeydown(event) {
  if (event.key === 'Escape') emit('close')
}

function onBackdrop(event) {
  // target===currentTarget 才关：从内容区冒泡上来的点击不是"点空白"（ChunkPickerModal 同规矩）
  if (event.target === event.currentTarget) emit('close')
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>
```

模板骨架（**类名与判据逐字对齐**，样式外壳直接借 `.picker-backdrop` / `.picker-modal` 两个既有类——同一对遮罩与面板，`z-index: 4` 与 `66vh` 已被文档块弹窗验证过，别新造一套）：

```vue
<template>
  <div class="picker-backdrop settings-backdrop" @click="onBackdrop">
    <div class="picker-modal settings-panel" role="dialog" aria-modal="true" aria-label="账号设置">
      <header class="picker-header">
        <h3 class="picker-title">⚙ 账号设置</h3>
        <button class="picker-close" type="button" aria-label="关闭" title="关闭" @click="emit('close')">✕</button>
      </header>

      <div class="settings-body">
        <section class="settings-section">
          <h4 class="settings-heading">昵称与头像</h4>
          <input class="settings-input settings-nickname-input" type="text" maxlength="50"
                 aria-label="昵称" v-model="profile.nickname" />
          <div class="settings-avatars">
            <button v-for="item in AVATARS" :key="item" type="button" class="settings-avatar"
                    :class="{ 'settings-avatar-active': profile.avatar === item }"
                    :aria-label="AVATAR_LABELS[item]" :title="AVATAR_LABELS[item]"
                    @click="profile.avatar = item">{{ item === 'auto' ? 'A' : item }}</button>
          </div>
          <p v-if="profileError" class="settings-error settings-profile-error">⚠️ {{ profileError }}</p>
          <button class="btn btn-small settings-profile-save" type="button"
                  :disabled="busy !== ''" @click="saveProfile">保存资料</button>
        </section>

        <section class="settings-section">
          <h4 class="settings-heading">修改密码</h4>
          <input class="settings-input" type="password" aria-label="原密码"
                 autocomplete="current-password" v-model="password.oldPassword" />
          <input class="settings-input" type="password" aria-label="新密码"
                 autocomplete="new-password" v-model="password.newPassword" />
          <p class="settings-hint">新密码至少 {{ PASSWORD_MIN }} 位。改密码不会让其它设备掉线（已知遗留，spec 7.4）。</p>
          <p v-if="passwordError" class="settings-error settings-password-error">⚠️ {{ passwordError }}</p>
          <button class="btn btn-small settings-password-save" type="button"
                  :disabled="busy !== ''" @click="savePassword">修改密码</button>
        </section>

        <section class="settings-section">
          <h4 class="settings-heading">大模型凭证</h4>
          <p class="settings-masked">当前密钥：<code>{{ user?.api_key_masked || '未配置' }}</code></p>
          <input class="settings-input settings-apikey-input" type="password" aria-label="api_key"
                 autocomplete="off" placeholder="sk-…" v-model="llm.apiKey" />
          <input class="settings-input settings-baseurl-input" type="text" aria-label="base_url"
                 placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1" v-model="llm.baseUrl" />
          <p v-if="llmError" class="settings-error settings-llm-error">⚠️ {{ llmError }}</p>
          <button class="btn btn-small settings-llm-save" type="button"
                  :disabled="busy !== ''" @click="saveLlm">保存凭证</button>
        </section>

        <section class="settings-section">
          <h4 class="settings-heading">模型名单</h4>
          <ul v-if="user?.models?.length" class="settings-models">
            <li v-for="name in user.models" :key="name" class="settings-model-row">
              <span class="settings-model-name">{{ name }}</span>
              <span v-if="name === user.default_model" class="settings-default">默认</span>
              <button class="btn btn-ghost btn-small settings-model-default" type="button"
                      :disabled="busy !== '' || name === user.default_model"
                      @click="makeDefault(name)">设为默认</button>
              <button class="btn btn-ghost btn-small settings-model-drop" type="button"
                      :disabled="busy !== ''" @click="dropModel(name)">删除</button>
            </li>
          </ul>
          <p v-else class="settings-hint">名单是空的——没有模型可选，问答会直接返回 409。</p>
          <form class="settings-add-model" @submit.prevent="submitModel">
            <input class="settings-input settings-model-input" type="text" maxlength="100"
                   aria-label="新模型名" placeholder="例如 qwen-max" v-model="modelDraft" />
            <button class="btn btn-small settings-model-add" type="submit"
                    :disabled="busy !== ''">添加</button>
          </form>
          <p v-if="modelsError" class="settings-error settings-models-error">⚠️ {{ modelsError }}</p>
        </section>
      </div>
    </div>
  </div>
</template>
```

> **`maxlength` 三处都是列宽的镜像**：昵称 50（`users.nickname` String(50)）、模型名 100（`user_models.name` String(100)，与 Task 7 的 `ChatRequest.model_name` 同源）。它只是"少打一次 422"的体贴，**不是**校验的唯一防线——后端那三道仍是权威，判据 #1 的空白变体就是绕开 `maxlength` 走的。

- [ ] **Step 3: layout.css 追加一节（外壳零新样式，只补内部行）**

追加在 `.user-rail` 那一节之后（文件末尾），全部颜色取现有 token：

```css
/* ---- 阶段二 Task 9：设置弹窗 ----
   外壳照抄 .picker-backdrop / .picker-modal（遮罩、66vh、两列 grid 都已被文档块弹窗验过），
   这里只补内部的纵向排布与四个小件。G-4 口径：本块一个颜色字面量都不写。 */
.settings-body {
  flex: 1; min-height: 0; overflow-y: auto;
  display: flex; flex-direction: column; gap: 14px; padding-right: 2px;
}
.settings-section { display: flex; flex-direction: column; gap: 8px; }
.settings-heading { margin: 0; font-size: 14px; color: var(--text-muted); }
.settings-input {
  padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-card);
  background: var(--panel-bg); color: var(--text-main); font-size: 13px;
}
.settings-input:focus { outline: 2px solid var(--focus-ring); border-color: var(--brand-1); }
.settings-avatars { display: flex; gap: 6px; flex-wrap: wrap; }
.settings-avatar {
  width: 32px; height: 32px; padding: 0; cursor: pointer;
  border: 1px solid var(--border); border-radius: 50%;
  background: var(--panel-bg); color: var(--text-main); font-size: 16px; line-height: 1;
}
.settings-avatar-active { border-color: var(--brand-1); background: var(--status-rag-bg); }
.settings-error { font-size: 13px; color: var(--fail-fg); }
.settings-hint { font-size: 12px; color: var(--text-muted); }
.settings-masked { font-size: 13px; color: var(--text-muted); }
.settings-models { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 6px; }
.settings-model-row { display: flex; align-items: center; gap: 8px; font-size: 13px; }
/* 名单项名字可能长到吃掉整行（模型名上界 100 字）：不 min-width:0 就会把两个按钮挤出弹窗 */
.settings-model-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.settings-default {
  flex-shrink: 0; padding: 1px 8px; border-radius: var(--radius-pill);
  background: var(--status-normal-bg); color: var(--status-normal-fg); font-size: 12px;
}
.settings-add-model { display: flex; gap: 8px; }
.settings-add-model .settings-input { flex: 1; min-width: 0; }

@media (max-width: 768px) {
  /* 窄屏上"名字 + 默认 + 设为默认 + 删除"一行四件，375px 必塌：让按钮组换行到第二行 */
  .settings-model-row { flex-wrap: wrap; }
  .settings-avatar { width: 28px; height: 28px; font-size: 14px; }
}
```

- [ ] **Step 4: App.vue —— ⚙ 解禁、挂载、`avatarChar` 换成 `railAvatar`**

1. `import SettingsModal from './components/SettingsModal.vue'`（跟着既有组件的 import 组，`:4-10` 那段）。
2. 新增 `const settingsOpen = ref(false)`（放在 `panelOpen` 旁边，`:33` 之后）。
3. `:182-183` 那两句"⚙ 这一期是 disabled 的占位 / 现在点出一个空白弹窗比点不动更糟"是阶段一留的过期说明，删掉——但**注释块的闭合 `-->` 在 183 行末尾，必须留下**（这段注释从 `:179` 的 `<!-- 需求 3：…` 起、只在 183 行收；连 `-->` 一起删模板就语法错误）。删完 `:179-183` 应当是：
   ```html
   <!-- 需求 3：原先这里的「session_id 调试区」整块删除（那行的 <code> 展示与
        「换一个 session_id」按钮一起走），原位置换成 `.user-rail`——sessionId 在界面上
        只剩读的地方，没有显示的地方；换 id 的动作留在 handleClear 里。 -->
   ```
   `:188-194` 的按钮改成：
   ```html
   <button class="btn btn-ghost btn-small rail-settings"
           type="button" title="账号设置" aria-label="打开设置"
           @click="settingsOpen = true">⚙</button>
   ```
4. `resetWorkspace()`（Task 8 抽出）里补一行 `settingsOpen.value = false`——**登出与 401 自动登出都要关掉弹窗**，否则票过期后弹窗还挂在登录页上（它是 `.app-shell` 的子树，`v-if` 会连它一起卸载，但 `settingsOpen` 这个 ref 活着，下一个人登录就立刻看见上一个账号开着半截的表单）。补完再跑 Task 8 那条 401 测：`.auth-screen` 断言照旧成立，新增 `expect(app.vm.settingsOpen).toBe(false)`。
5. `avatarChar`（`:95-98`）改名 `railAvatar` 并接住这一列真值：
   ```js
   // 头像这一列现在有两个来源（Task 9 起了选择器）：'auto' = 昵称首字母，预设表情直接照抄。
   // 取"首字母"用 Array.from 而不是 charAt(0)：emoji 是一个代理对，charAt 会切出半个、
   // 渲染成乱码方块（阶段一顺延清单 M-4 说的就是这类半字符）。
   const railAvatar = computed(() => {
     const avatar = user.value?.avatar
     if (avatar && avatar !== 'auto') return Array.from(avatar)[0] ?? '我'
     const name = (user.value?.nickname || user.value?.identifier || '').trim()
     return name ? Array.from(name)[0].toUpperCase() : '我'
   })
   ```
   模板 `:186` 的 `{{ avatarChar }}` 改 `{{ railAvatar }}`。
6. 弹窗挂载在 `.chat-body` 里、`<ChunkPickerModal>` 之后（`v-if="settingsOpen"` + `@close="settingsOpen = false"`）。**位置和文档块弹窗一致**：`position: fixed` 让它脱离 grid 流，这件事已被 `.picker-backdrop` 在同一位置验证过——挂到 `.app-shell` 的直接子级去会重新引入"多出一轨"的疑问（`layout.css` 的 L-1/L-2 注释就是为此写的）。

- [ ] **Step 5: App 层的两条判据（追加进 `App.auth-gate.test.js`）**

该文件从 Task 8 的 **4 条** `it()` 变 **6 条**。两条都留在 App 层而不是弹窗层，理由分别是：① 开合的接线在 `App.vue`（`settingsOpen`），`⚙` 解禁本身就是这一层的交付物；② 渲染 `.rail-avatar` 的是 `App.vue` 的模板，`SettingsModal` 里没有这个节点，组件级测无法覆盖 `railAvatar` 那条 computed。

```js
  it('⚙ 点得开、弹窗能关，且退出后不再留着上一个账号的表单', async () => {
    seedLoggedIn()
    const app = await mountApp()
    // 前置事实：⚙ 不再是 disabled（阶段一那条 disabled 是"点出空白弹窗更糟"的占位）
    const gear = app.find('.rail-settings')
    expect(gear.attributes('disabled')).toBeUndefined()
    expect(app.find('.settings-panel').exists()).toBe(false)

    await gear.trigger('click')
    expect(app.find('.settings-panel').exists()).toBe(true)
    // 弹窗里此刻是**这个人**的资料（回填来自模块级 user，不是空表单）
    expect(app.find('.settings-nickname-input').element.value).toBe('小明')

    // Task 9 的关键接线：开着弹窗登出，ref 必须跟着归位
    await app.find('.rail-signout').trigger('click')
    await flushPromises()
    expect(app.vm.settingsOpen).toBe(false)
    expect(app.find('.settings-panel').exists()).toBe(false)
  })

  it('头像列的三种值都渲染得出来：auto 取昵称首字母、预设表情是整枚、空昵称退回标识首字母', async () => {
    const { user } = useAuth()
    seedLoggedIn()
    const app = await mountApp()                        // me 回的是 ME.user（avatar: 'auto'）
    expect(app.find('.rail-avatar').text()).toBe('小')  // 昵称「小明」的首字母，中文不需要 toUpperCase
    user.value = { ...user.value, avatar: '🤖' }
    expect(app.find('.rail-avatar').text()).toBe('🤖')   // 整枚，不是半个代理对
    user.value = { ...user.value, avatar: 'auto', nickname: '', identifier: 'z@b.com' }
    expect(app.find('.rail-avatar').text()).toBe('Z')
  })
```
> ⚠️ 这条测**依赖 `ME.user` 的形状**：Task 8 之前该文件的 `ME` 是五键（`:36`），本 Task 之后 `.rail-avatar`/弹窗回填都要读 `models`/`api_key_masked`，所以 Step 5 的**第一句动作**就是把 `ME.user` 扩成十键（形状见 spec 3.1 与 Task 2 的 `UserOut`）。十键的最终版由 Task 11 定稿（它要再加"未配置"变体），本 Task 先扩到十键即可，别在两个 Task 里各改一半。

- [ ] **Step 6: 全量门禁 + 样式门禁**

```bash
cd frontend && npm test && npm run build
# G-4：variables.css 之外零颜色字面量（本 Task 新增 12 条规则，全用 var(--)）
grep -rn "#[0-9a-fA-F]\{3,8\}\b\|rgba(\|rgb(" src/styles/layout.css | grep -v "var(" | wc -l
```
Expected: 三条都绿。`npm test` 汇总行 = Task 8 的实数 + **10 条**（`SettingsModal.test.js` 8 + `App.auth-gate.test.js` 2）；文件数 **14**（新增 `SettingsModal.test.js`）。⚠️ Step 5 第二条 emoji 测里的 `user.value = {...}` 是**直接写模块级 ref**，它会留给下一个 `it()`——该文件既有口径是"每条 `it()` 自己建立前置条件"（`:19-21`），`seedLoggedIn()` + `mountApp()` 会重新走 `bootstrap()` 用 `ME.user` 覆盖 `user`，所以顺序不敏感；**别在 `beforeEach` 里加 `user.value = null` 之外的补偿逻辑**。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/components/SettingsModal.vue frontend/src/App.vue frontend/src/styles/layout.css frontend/tests/SettingsModal.test.js frontend/tests/App.auth-gate.test.js
git -c user.name="31439" -c user.email="31439@local" commit -F /tmp/fe2-task9.txt
```
提交信息：`feat(frontend): SettingsModal 四段设置弹窗 + ⚙ 解禁 + 头像预设（阶段二 Task 9）`

> **交付时必说两句**：① 弹窗里的 api_key 输入框**永不回填**（后端只给 `api_key_masked`），保存后立刻从组件状态抹掉——所以"我只改路由不想重打 key"这件事做不到，必须重贴一次全文。这是决策 5 + spec 3.1 的直接后果，不是遗漏。② 改密码**不吊销**其它令牌（spec 7.4 已知遗留）：另一台机器上那枚票还能用到 30 天 TTL，界面上那句提示就是为这件事写的，不许在实现时顺手删。

---

## Task 10: `ChatInput.vue` 两段式 + 模型下拉 + `model_name` 接到发送链路

**Files**
- Modify: `frontend/src/components/ChatInput.vue`、`frontend/src/App.vue`、`frontend/src/composables/useChat.js`、`frontend/src/styles/variables.css`、`frontend/src/styles/layout.css`
- Test: `frontend/tests/ChatInput.test.js`、`frontend/tests/useChat.test.js`、`frontend/tests/App.auth-gate.test.js`

**Consumes:** Task 2/9 写进 `user.models` 与 `user.default_model` 的名单；Task 7 的 `ChatRequest.model_name`（1..100，可选）。
**Produces:** `.chat-controls` / `.model-select` / `.chat-send` / `.chat-stop` 四个类名、`--control-gap` token、`send({..., model_name})` 这条载荷。Task 11 往 `ChatInput` 上再加一个 `allowSend` prop（**本 Task 不加**：一次改动对应一个行为，两轮的 diff 各自可读）。

> **prop 名字不能叫 `model`**（spec 5.8 点名）：`v-model` 的隐式 prop 是 `modelValue`，而 `model*` 这一族前缀归 Vue 自己用；组件里再开一个 `model` 会让下一个读代码的人以为 `:model` 也是双向绑定，于是"选中模型"这件事在某次改写后悄悄变成只传不回。命名用 `selectedModel` + `update:selectedModel`，输入框那一路继续用 `modelValue`，两族并存但互不冒充。

- [ ] **Step 1: 先把既有四处 `find('button')` 钉成类选择器（纯测试 + 加类名，行为零变化）**

`ChatInput.test.js` 现有 **5 条**判据，四处靠按钮位置定位：`:15`、`:18`、`:43-44`、`:51`（`find('button')` / `findAll('button')`）。今天只有两个按钮且 `v-if`/`v-else` 互斥，所以 `find('button')` 恰好命中要的那个——**这是巧合不是契约**：本 Task 之后 `.chat-controls` 里多一个 `<select>`（它不是按钮，`findAll('button')` 长度仍是 1，`:44` 那条侥幸不会被破），但任何一个后续改动往控件行加第三个按钮都会让这四处**静默改指另一个按钮**，判据照绿、测的却是别的东西。所以先把它们钉死：

- `:15` → `wrapper.find('.chat-send')`
- `:18` → `wrapper.find('.chat-send')`
- `:43-44` → `wrapper.findAll('.chat-controls button')` + `expect(buttons).toHaveLength(1)`（**保留**"只有这一个按钮"这一句：它是停止态互斥的判据本体）
- `:51` → `wrapper.find('.chat-stop')`

同轮给组件的两个按钮加类名（`:37` 的停止按钮 → `class="btn btn-stop chat-stop"`，`:38` 的发送按钮 → `class="btn chat-send"`）。**加类名不改结构与行为**，所以这一步可以与测试改动放在同一轮，跑完全量应当还是 **117 passed**（Task 8/9 之后的实数）。这一步之后 Step 2 的 RED 才是"新行为"的红。

Run: `cd frontend && npm test`
Expected: 全绿，条数与上一轮一致（这一步一条判据都不新增）。

- [ ] **Step 2: RED —— 四条新判据（两段结构 / option 逐项 / 改选 emit / 空名单与 pending 的禁用）**

`ChatInput.test.js` 末尾追加一节。`mountInput` 工厂（`:8-10`）已经只传 `modelValue`，新 prop 全有默认值 ⇒ 既有 5 条不会因为新 prop 红。

```js
describe('ChatInput：两段式与模型下拉（Task 10）', () => {
  it('结构是两段：textarea 独占第一行，控件行的最后一个子节点才是发送按钮', () => {
    const w = mountInput({ modelValue: 'q', models: ['qwen-max'], selectedModel: 'qwen-max' })
    const kids = w.find('.chat-input').element.children
    expect(kids[0].className).toContain('chat-textarea')
    expect(kids[1].className).toContain('chat-controls')
    // 右对齐是 CSS 的事（justify-content），DOM 顺序只保证"下拉在按钮左边"这一件事
    const controls = w.findAll('.chat-controls > *')
    expect(controls.map((c) => c.classes()[0])).toEqual(['model-select', 'chat-send'])
  })

  it('下拉的 option 逐个来自 models，值与文本都是模型名原样（含空格与中文）', () => {
    const w = mountInput({ modelValue: 'q', selectedModel: 'qwen 2.5/coder',
                           models: ['qwen 2.5/coder', '千问-max'] })
    const options = w.findAll('.model-select option')
    expect(options.map((o) => o.text())).toEqual(['qwen 2.5/coder', '千问-max'])
    expect(options.map((o) => o.element.value)).toEqual(['qwen 2.5/coder', '千问-max'])
    expect(w.find('.model-select').element.value).toBe('qwen 2.5/coder')
  })

  it('改选模型 emit update:selectedModel，值是新选中的那个名字（不是下标）', async () => {
    const w = mountInput({ modelValue: 'q', selectedModel: 'a', models: ['a', 'b'] })
    await w.find('.model-select').setValue('b')
    expect(w.emitted('update:selectedModel')).toEqual([['b']])
    // 下拉的 change 绝不能顺手把 send 也发出去（用户只是想换个模型）
    expect(w.emitted('send')).toBeUndefined()
  })

  it('名单为空 / 正在生成 两种情况下下拉都被禁用', () => {
    const empty = mountInput({ modelValue: 'q' })          // models 默认 () => []
    expect(empty.findAll('.model-select option')).toHaveLength(1)
    expect(empty.find('.model-select option').element.value).toBe('')
    expect(empty.find('.model-select').text()).toContain('名单为空')
    expect(empty.find('.model-select').attributes('disabled')).toBeDefined()

    const busy = mountInput({ modelValue: 'q', pending: true, models: ['a'] })
    expect(busy.find('.model-select').attributes('disabled')).toBeDefined()
  })
})
```

Run: `cd frontend && npx vitest run tests/ChatInput.test.js`
Expected: 新增四条全红（`.model-select` / `.chat-controls` 不存在）。**记下当轮汇总行**。

- [ ] **Step 3: 实现 ChatInput.vue（整文件替换）**

```vue
<script setup>
const props = defineProps({
  modelValue: { type: String, required: true },
  pending: { type: Boolean, default: false },
  // 名单来自 user.models（Task 2 的 _user_out 给，Task 9 的 SettingsModal 改）。
  // 数组类 prop 的 default 必须是工厂函数：写死 [] 会让所有实例共享同一个引用。
  models: { type: Array, default: () => [] },
  selectedModel: { type: String, default: '' },
})
// update:selectedModel 与 update:modelValue 是两条独立的双向口，别混：
// 前者改"这一轮用哪个模型"，后者改"要发什么话"。
const emit = defineEmits(['update:modelValue', 'update:selectedModel', 'send', 'stop'])

function onInput(event) {
  emit('update:modelValue', event.target.value)
}

function onModelChange(event) {
  // 交出去的是 option 的 value（模型名本身），不是下标：下标会随名单增删漂移。
  emit('update:selectedModel', event.target.value)
}

function submit() {
  if (props.pending || !props.modelValue.trim()) return
  emit('send', props.modelValue.trim())
}

function onKeydown(event) {
  // 原 st.chat_input 就是回车发送；Shift+Enter 留给人工换行
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    submit()
  }
}
</script>

<template>
  <div class="chat-input">
    <textarea
      class="chat-textarea"
      rows="2"
      placeholder="💬 输入你的问题…"
      :value="props.modelValue"
      :disabled="props.pending"
      @input="onInput"
      @keydown="onKeydown"
    ></textarea>
    <div class="chat-controls">
      <select
        class="model-select"
        aria-label="本轮使用的模型"
        :value="props.selectedModel"
        :disabled="props.pending || props.models.length === 0"
        @change="onModelChange"
      >
        <!-- 空名单也要有一个 option：否则 :value 指向一个不存在的 option，
             select 自己会显示成"空白"，看起来像控件坏了而不是"你没配模型" -->
        <option v-if="props.models.length === 0" value="">（名单为空，先去设置加一个）</option>
        <option v-for="name in props.models" :key="name" :value="name">{{ name }}</option>
      </select>
      <button v-if="props.pending" class="btn btn-stop chat-stop" type="button" @click="emit('stop')">⏹ 停止生成</button>
      <button v-else class="btn chat-send" type="button" :disabled="!props.modelValue.trim()" @click="submit">发送</button>
    </div>
  </div>
</template>
```

> **pending 时下拉也禁用**：在飞的那一轮用的模型名已经发出去了，此时改下拉会让"下一条消息的模型"和"屏上正在生成的那条气泡"不是一个，而气泡上不显示模型名——用户只会觉得"我换了模型它还在用旧的答"。textarea 在这态下本来就被禁用，整行一起冻结才自洽。

- [ ] **Step 4: 样式（一个 token + 改一条既有规则 + 追加一节）**

`variables.css`：新 token 插在 `:42 --side-width` 与 `:43 }` 之间（**spec 5.8 说的"`:43` 之后"指的是 `}`，见 §0 表第 12 行**）：

```css
  /* 输入区控件行的间距：下拉与发送按钮之间。写进 token 是为了 ≤768 分支只用改它，
     不必在两条规则里各抄一遍 8px（spec 5.8 点名的 --control-gap） */
  --control-gap: 8px;
```

`layout.css` 的 `.chat-input`（`:266-273`）从横排改竖排——**这条规则只有 `ChatInput.vue` 一处使用**（实测 `grep -rn "chat-input" src/` 命中组件与 `layout.css` 两处），所以原地改是安全的：

```css
.chat-input {
  display: flex;
  flex-direction: column;      /* 两段式：输入区独占一行，控件行在下方右对齐 */
  align-items: stretch;
  gap: 8px;
  padding: 12px 20px;
  background: var(--panel-bg);
  border-top: 1px solid var(--border);
}
```

追加在 Task 9 那一节之后：

```css
/* ---- 阶段二 Task 10：输入区控件行与模型下拉 ---- */
.chat-controls {
  display: flex; align-items: center; justify-content: flex-end;
  gap: var(--control-gap);
}
.model-select {
  max-width: 45%; padding: 7px 10px; cursor: pointer;
  border: 1px solid var(--border); border-radius: var(--radius-card);
  background: var(--panel-bg); color: var(--text-main); font-size: 13px;
}
.model-select:focus { outline: 2px solid var(--focus-ring); border-color: var(--brand-1); }
.model-select:disabled { opacity: 0.6; cursor: not-allowed; }

@media (max-width: 768px) {
  /* 375px 上"下拉 + 发送"两个控件：不放开收缩就会撑破 .chat-input 的左右内边距
     （塌行这件事在 .picker-results 与 .user-rail 上都栽过一次，这次提前挡） */
  .chat-controls { flex-wrap: wrap; }
  .model-select { flex: 1; min-width: 0; max-width: none; }
  .chat-send, .chat-stop { flex-shrink: 0; }
}
```

> `max-width: 45%` 是宽屏档：模型名可以长到 100 字（Task 2 的上界），不限宽就会把发送按钮推到 `.chat-main` 的边界外。`<select>` 对超长文本自己截断，不需要 `text-overflow`。

- [ ] **Step 5: App.vue 接线 + useChat 载荷加 `model_name`**

`App.vue` 在 `question`（`:30`）附近加三行与一个 computed，并把 `handleSend`（`:129-135`）的载荷补一个字段：

```js
// 模型下拉的选中值。名单里没有它时 currentModel 会自动回落（见下），
// 所以这里只表达"这个人显式选过谁"，不承载默认值判断。
const modelOverride = ref('')

// 解析口径必须与后端 Task 7 的 _llm_context 逐字一致：显式选过 → 后端给的默认 → 名单第一项。
// 三档少一档，界面上显示的那个模型和实际发出去的就不是同一个——
// 那种坏法的表征是"我明明选了 qwen-turbo，账单却是 qwen-max"，查起来最费时间。
const currentModel = computed(() => {
  const opts = user.value?.models ?? []
  if (modelOverride.value && opts.includes(modelOverride.value)) return modelOverride.value
  return user.value?.default_model ?? opts[0] ?? ''
})
```

```html
<ChatInput v-model="question" :pending="pending"
           :models="user?.models ?? []" :selected-model="currentModel"
           @update:selected-model="modelOverride = $event"
           @send="handleSend" @stop="handleStop" />
```

```js
async function handleSend(text) {
  if (!text || pending.value) return
  question.value = ''
  const ok = await send({ session_id: sessionId.value, question: text,
                          parent_ids: selectedParentIds.value, model_name: currentModel.value })
  // 后端失败时不写历史，本地那两条也已经撤掉；把问题还给输入框，别让用户重打
  if (!ok) question.value = text
}
```

`resetWorkspace()`（Task 8）里补一行 `modelOverride.value = ''`，理由与 `settingsOpen` 同一条：ref 活着而 `user` 已经换人，上一个账号的选中项会在下一个人**恰好也有同名模型**时被静默继承。

`useChat.js` 的 `send` 签名加第四个字段，载荷按"空值连键都不发"组：

```js
  async function send({ session_id, question, parent_ids, model_name }) {
    ...
    const payload = { session_id, question, parent_ids }
    // 空模型名连键都不发（同 api/auth.js 的 register 那条规矩）：后端 ChatRequest 的
    // min_length=1 会把 '' 判成 422，而那句话在界面上读起来像"我没打错任何参数"。
    // 不发键 = 让后端走它自己的解析（默认项 → 第一项，Task 7），这是正路不是兜底。
    if (model_name) payload.model_name = model_name
    await sendChatStream(payload, (event, data) => { ... }, { signal })
```

- [ ] **Step 6: 载荷判据（useChat 一条扩写 + 一条新增；App 层一条新增）**

`useChat.test.js:52-58` 那条"载荷里的池子字段叫 parent_ids"**原地扩写**成四键（它钉的就是"字段名对不对"，模型名进来了就得一起钉）：

```js
  it('载荷里的池子字段叫 parent_ids，模型字段叫 model_name', async () => {
    scriptEvents([['token', { text: 'x' }], DONE])
    const chat = useChat()
    await chat.send({ session_id: 's1', question: 'q', parent_ids: ['甲.txt_parent_0'], model_name: 'qwen-turbo' })
    expect(sendChatStream.mock.calls[0][0]).toEqual({
      session_id: 's1', question: 'q', parent_ids: ['甲.txt_parent_0'], model_name: 'qwen-turbo',
    })
  })
```

新增一条钉"空值不发键"：

```js
  it('没有选中模型时载荷里连 model_name 这个键都没有（空串会被后端判成 422）', async () => {
    scriptEvents([['token', { text: 'x' }], DONE])
    const chat = useChat()
    await chat.send({ session_id: 's1', question: 'q', parent_ids: [], model_name: '' })
    expect('model_name' in sendChatStream.mock.calls[0][0]).toBe(false)
  })
```
> 记一条环境事实免得有人误判红绿：vitest 的 `toEqual` **忽略值为 `undefined` 的键**，所以上面那条必须断"键在不在"，不能指望 `toEqual({session_id, question, parent_ids})` 去挡 `model_name: undefined`——那样写会永久绿。这条口径与 `api-auth.test.js:31` 的注释是同一件事。

`App.auth-gate.test.js` 新增一条（该文件从 Task 9 的 **6 条**变 **7 条**）。它要的是"用户在下拉里换了模型，发出去的载荷真的跟着变了"这条完整链路（`ChatInput` → `App` → `useChat` → `client`），只有 App 层测得到：

```js
  it('下拉换模型 → 发出去的载荷跟着换（App 到网络层是一条链，分段测各自看不见它）', async () => {
    seedLoggedIn()
    const app = await mountApp()
    // 桩只记了 url 与 method，这条判据需要 body：给记账多加一个字段（加法，既有断言不受影响）
    const select = app.find('.model-select')
    expect(select.findAll('option').map((o) => o.element.value)).toEqual(['qwen-max', 'qwen-turbo'])
    await select.setValue('qwen-turbo')
    await app.find('.chat-textarea').setValue('营收多少')
    await app.find('.chat-send').trigger('click')
    await flushPromises()
    const chatCall = calls.find((c) => c.url === '/api/chat/stream')
    expect(JSON.parse(chatCall.body).model_name).toBe('qwen-turbo')
    // 顺带钉住另一个键：池子还是那个池子，模型名不该把 parent_ids 顶掉
    expect(JSON.parse(chatCall.body).parent_ids).toEqual(['手册.pdf_parent_0'])
  })
```

两处配套改动：① 记账处（`:79`）改成 `calls.push({ url, method: init.method ?? 'GET', body: init.body })`；② 该测的 `/api/chat/stream` 在桩里回的是 `application/json`，`postStream` 必然在 content-type 那一格抛"响应不是 SSE 事件流"——**这不影响判据**：fetch 已经发生并记账，抛错发生在其后，且 `useChat.send` 的 catch 会把横幅写成那句、撤掉两条气泡。测的只是载荷，不是流。

- [ ] **Step 7: 全量门禁 + 样式门禁**

```bash
cd frontend && npm test && npm run build
grep -rn "#[0-9a-fA-F]\{3,8\}\b\|rgba(\|rgb(" src/styles/layout.css src/styles/variables.css | grep -v "var(" | wc -l
```
Expected: 全绿。新增 **6 条**（`ChatInput.test.js` 4、`useChat.test.js` 1 新（另 1 条为扩写，条数不变）、`App.auth-gate.test.js` 1）；文件数不变（14）。G-4 那条 grep 必须 **0 命中**（口径：`variables.css` 自己的 token 定义也算命中就整体排除它，两处之一命中都要改——本 Task 在 `layout.css` 新写的 5 条规则一个颜色字面量都不该有）。

变异自证两条：① 把 `currentModel` 的 `opts.includes(modelOverride.value)` 那半删掉 → App 层那条测红（换模型不再生效）；② 把 `useChat` 的 `if (model_name)` 改成无条件 `payload.model_name = model_name` → "键都没有"那条测红。

- [ ] **Step 8: 提交**

```bash
git add frontend/src/components/ChatInput.vue frontend/src/App.vue frontend/src/composables/useChat.js frontend/src/styles/variables.css frontend/src/styles/layout.css frontend/tests/ChatInput.test.js frontend/tests/useChat.test.js frontend/tests/App.auth-gate.test.js
git -c user.name="31439" -c user.email="31439@local" commit -F /tmp/fe2-task10.txt
```
提交信息：`feat(frontend): 输入区两段式 + 模型下拉，model_name 接到发送链路（阶段二 Task 10）`

---

## Task 11: 未配置的横幅 + 发送禁用 + 409 的归宿 + advisory ③

**Files**
- Modify: `frontend/src/App.vue`（`setupProblem` + 横幅 + `:allow-send`）、`frontend/src/components/ChatInput.vue`（新 prop `allowSend`）
- Modify: `frontend/src/styles/layout.css`（`.setup-banner`）
- Test: `frontend/tests/App.auth-gate.test.js`（`ME` 十键最终版 + 三条新判据）、`frontend/tests/ChatInput.test.js`（1 条）、`frontend/tests/useChat.test.js`（1 条 **钉档**）、`frontend/tests/useChunkSelection.test.js`（1 条 **钉档** = advisory ③）

**Consumes:** Task 2 的 `llm_configured` / `models`，Task 7 的三条 409 文案（`NotConfiguredError` 那两句 + `MODEL_NOT_IN_LIST`），Task 8 的 `ApiError.status`，Task 9 的 `settingsOpen`。
**Produces:** `.setup-banner` / `.setup-open` / `.chat-input[allowSend]`。Task 12 的浏览器判据直接用这几个类名。

- [ ] **Step 1: 把 `ME` 抽成 `meUser(over)` builder 并加"未配置"变体（测试基建，先跑一轮确认没踢翻既有 7 条）**

`App.auth-gate.test.js:36` 的 `ME` 在 Task 9 已经扩成十键（那轮只要求"形状对"，`models` 给了一项）。本 Task 起横幅/门禁用它做前置条件，而且要造"未配置"的变体，所以动作是**把它抽成 `meUser(over)` builder**（十键保持不变、`models` 升成两项）：

```js
// 十键 = backend/schemas/auth.py 的 UserOut（阶段二 Task 2 扩了后五项）。
// 少一项的表征不是红，是"读 undefined 走了 falsy 分支"——横幅会永远不出现，那条判据假绿。
function meUser(over = {}) {
  return { id: 1, identifier: 'a@b.com', identifier_type: 'email', nickname: '小明', avatar: 'auto',
           llm_configured: true, llm_base_url: 'https://fake/v1', api_key_masked: 'sk-****7890',
           models: ['qwen-max', 'qwen-turbo'], default_model: 'qwen-max', ...over }
}
const ME = { user: meUser() }
```
> `models` 给**两项**、`default_model` 给一项：Task 10 那条下拉测需要两个可选项才能证明"换得动"。改完之后先跑一次全量——既有 7 条里唯一会读 `models` 的是 Task 10 那条，它现在有了真名单；其余各条不碰这些键。

- [ ] **Step 2: RED —— App 层三条判据**

```js
  it('没配 key：横幅在输入区上方、文案点名 api_key，且发送被禁用（输入框有字也一样禁）', async () => {
    seedLoggedIn()
    const route = ROUTES.find((r) => r.prefix === '/api/auth/me')
    const original = route.body
    route.body = { user: meUser({ llm_configured: false, api_key_masked: '', llm_base_url: '', models: [] }) }
    try {
      const app = await mountApp()
      expect(app.find('.setup-banner').exists()).toBe(true)
      expect(app.find('.setup-banner').text()).toContain('api_key')
      await app.find('.chat-textarea').setValue('你好')
      expect(app.find('.chat-send').attributes('disabled')).toBeDefined()
      // 判据的另一半：Enter 这条路也被同一条门挡住（禁用只挡住了按钮）
      await app.find('.chat-textarea').trigger('keydown', { key: 'Enter' })
      expect(calls.filter((c) => c.url === '/api/chat/stream')).toEqual([])
    } finally { route.body = original }
  })

  it('凭证齐了但名单为空：横幅换成"名单是空的"那句（两句不许合成一句）', async () => {
    seedLoggedIn()
    const route = ROUTES.find((r) => r.prefix === '/api/auth/me')
    const original = route.body
    route.body = { user: meUser({ models: [], default_model: null }) }
    try {
      const app = await mountApp()
      expect(app.find('.setup-banner').text()).toContain('名单是空的')
      expect(app.find('.setup-banner').text()).not.toContain('api_key')
    } finally { route.body = original }
  })

  it('点横幅上的「去设置」把弹窗打开；配齐之后横幅消失、发送恢复可点', async () => {
    seedLoggedIn()
    const route = ROUTES.find((r) => r.prefix === '/api/auth/me')
    const original = route.body
    route.body = { user: meUser({ llm_configured: false, models: [] }) }
    try {
      const app = await mountApp()
      await app.find('.setup-open').trigger('click')
      expect(app.find('.settings-panel').exists()).toBe(true)
      await app.find('.picker-close').trigger('click')      // 关掉弹窗，横幅还在（配置没变）
      expect(app.find('.setup-banner').exists()).toBe(true)

      // 同一次挂载里把 /me 换回"配齐"：模拟在设置里填完之后的 rehydrate
      route.body = { user: meUser() }
      await useAuth().bootstrap()
      await flushPromises()
      expect(app.find('.setup-banner').exists()).toBe(false)
      await app.find('.chat-textarea').setValue('你好')
      expect(app.find('.chat-send').attributes('disabled')).toBeUndefined()
    } finally { route.body = original }
  })
```

`ChatInput.test.js` 加一条（`allowSend` 的门禁本体）：

```js
  it('allowSend=false：有字但发送按钮仍禁用，且 Enter 也发不出 send', async () => {
    const w = mountInput({ modelValue: '你好', allowSend: false, models: ['a'], selectedModel: 'a' })
    expect(w.find('.chat-send').attributes('disabled')).toBeDefined()
    await w.find('.chat-textarea').trigger('keydown', { key: 'Enter' })
    expect(w.emitted('send')).toBeUndefined()
  })
```

Run: `cd frontend && npx vitest run tests/App.auth-gate.test.js tests/ChatInput.test.js`
Expected: 三条 App + 一条 ChatInput 全红。

- [ ] **Step 3: 实现 —— App 的两道门合成一句人话，ChatInput 多一个 prop**

`App.vue`（`currentModel` 附近）：

```js
// spec 3.4 的"登录后且配好 key 才能对话"在后端是两条门（Task 7：NotConfiguredError 与
// 空名单各一句 409 文案）。界面上**分两次说**会变成"修好一个又冒出一个"，
// 所以这里合成一个 computed：一句、一个出口（去设置），修好了两句一起消失。
const setupProblem = computed(() => {
  if (!isLoggedIn.value) return ''            // 登录门由整屏 v-if 管，这里不该再抢一句
  if (!user.value?.llm_configured) return '还没有配置大模型的 api_key 与路由，点「去设置」填好就能对话'
  if (!user.value?.models?.length) return '模型名单是空的，请先在设置里添加一个模型'
  return ''
})
```

模板里 `<MessageList>` 与 `<ChatInput>` 之间插入（**位置在输入框正上方**：它挡住的就是发送，横幅离发送越远越像一句无关公告）：

```html
<p v-if="setupProblem" class="setup-banner">
  <span>⚠️ {{ setupProblem }}</span>
  <button class="btn btn-ghost btn-small setup-open" type="button" @click="settingsOpen = true">去设置</button>
</p>
```

`ChatInput` 的调用点补 `:allow-send="setupProblem === ''"`；组件里加 prop 并接两处（**这就是"禁用按钮 + Enter 也禁"的两条路**，少一条就是漏一面）：

```js
  allowSend: { type: Boolean, default: true },   // 默认 true：既有 5+4 条测都不传它，行为照旧
```
```js
function submit() {
  if (props.pending || !props.allowSend || !props.modelValue.trim()) return
  emit('send', props.modelValue.trim())
}
```
```html
<button v-else class="btn chat-send" type="button"
        :disabled="!props.allowSend || !props.modelValue.trim()" @click="submit">发送</button>
```

`layout.css` 追加（底色借现有的紫色档，**不新增颜色 token**，G-4 命中数不变）：

```css
/* ---- 阶段二 Task 11：未配置横幅 ----
   与 .error-banner 同一配方但不同色：红色档属于"出错了"，这一条是"还差一步配置"，
   两者混在一个颜色里会让用户把指引当故障。--status-normal-* 是那对现成的紫。 */
.setup-banner {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  margin: 0 20px; padding: 8px 12px;
  border: 1px solid var(--border); border-radius: var(--radius-card);
  background: var(--status-normal-bg); color: var(--status-normal-fg); font-size: 13px;
}
.setup-open { flex-shrink: 0; }

@media (max-width: 768px) {
  .setup-banner { margin: 0 12px; flex-wrap: wrap; }
}
```

- [ ] **Step 4: 409 的归宿 —— 裁定 + 两条钉档判据（今天即绿，不许伪报成 RED）**

> **裁定（spec 3.4/3.5 未覆盖，计划级定）**：
> 1. **409 只可能从 HTTP-before-stream 来**，所以前端永远拿得到 `err.status`。理由：Task 7 的三条 409（`NotConfiguredError`、`MODEL_NOT_IN_LIST`、`EMPTY_MODEL_LIST`）都在 `_llm_context` 里抛，而 `_llm_context` 的调用点在 `api/chat.py:74` 的守卫位置——**在 `frames()` 之外、`StreamingResponse` 构造之前**（阶段二 Task 2 就把校验钉在流开始之前，`test_more_than_50_parent_ids_is_422` 那条"零 SSE 帧、纯 JSON"的判据是它的既有同族）。SSE 的 `error` 帧只会装 rag 链内部的 `RetrievalError` / `LLMError` / `StorageError`，那三种到不了 409。
> 2. **`useChat` 不按 status 分支**：横幅文案直接用后端那句 `err.message`（`client.js` 的 `detailFromText` 已经把 `detail` 原样取出）。再包一层等于两句中文打架，而 Task 7 的文案是按"可行动"写的。
> 3. **409 之后不自动重取 `/api/auth/me`**：`setupProblem` 的正确性由 Task 9 的 `patchMe` 保证（在设置里改完必然刷新到位）。409 只发生在"半途被管理员改了库""另一个标签页删了模型"这类罕见场景，为它多打一枪换不到新事实，还会把"我刚刚明明配好了"这句话变成一次无解释的加载。
> 4. 于是 409 的唯一界面归宿就是**既有那条红色 `error` 横幅**（`App.vue:206-209`）。Task 11 只补紫色横幅做**事前**拦截，红色横幅继续承担**事后**兜底。

`useChat.test.js` 加一条（**钉档：这条在今天就应该绿**——Task 7 之后 `postStream` 抛 `ApiError(409)`，`send` 的 catch 走 `error.value = err.message` + `removeTurn`，全是既有代码。它的价值是"未来有人按 status 加分支时挡住他改错方向"，台账里记成 **pin 不是 RED**）：

```js
  it('409 的归宿：横幅就是后端那句中文，本地两条气泡一起撤（钉档，不是新行为）', async () => {
    sendChatStream.mockRejectedValue(new ApiError('你的模型名单是空的，请先在设置里添加一个模型', 409))
    const chat = useChat()
    await expect(chat.send({ session_id: 's1', question: 'q', parent_ids: [], model_name: '' }))
      .resolves.toBe(false)
    expect(chat.messages.value).toEqual([])
    expect(chat.error.value).toBe('你的模型名单是空的，请先在设置里添加一个模型')
  })
```

- [ ] **Step 5: advisory ③ —— hydrate 失败路径的本地键判据（钉档）**

`useChunkSelection.js:53-56` 的 catch 故意**不**清空本地选中池（"一次网络失败不该把面板清空"），于是 `selected_parent_ids` 原样留在 localStorage。这件事今天只有注释担保。加一条钉档（**今天即绿**）：

```js
  it('hydrate 失败：本地池一个键都不清，只说错误（一次网络抖动不许抹掉用户的选中项）', async () => {
    localStorage.setItem('selected_parent_ids', JSON.stringify(['活_p_0', '死_p_1']))
    listChunks.mockRejectedValue(new ApiError('无法连接后端，请确认 uvicorn 已在 :8000 运行', 0))
    const sel = useChunkSelection()
    await sel.hydrate()
    expect(sel.selectionError.value).toContain('无法连接后端')
    expect(sel.selectedChunks.value).toEqual([])                 // 内存里没建起来
    // 判据本体：localStorage **原样**，既不回写空数组也不剪枝
    expect(JSON.parse(localStorage.getItem('selected_parent_ids'))).toEqual(['活_p_0', '死_p_1'])
    // 清它的唯一入口是 clearSelection()——阶段一终审明写"今天承重别删"：
    // 它是登出/401 自动登出时把上一个账号的选中池抹掉的唯一动作（App.vue 的 resetWorkspace 调它）
    sel.clearSelection()
    expect(localStorage.getItem('selected_parent_ids')).toBe('[]')
  })
```

> 后半句 `clearSelection()` 是这条判据的另一半：它把"失败路径不清"与"登出路径必清"钉在同一个 `it()` 里，这样将来有人把 `clearSelection()` 从 `resetWorkspace` 里删掉时，会先看见这里红，而不是等到跨用户残留才被发现。

- [ ] **Step 6: 全量门禁 + 样式门禁**

```bash
cd frontend && npm test && npm run build
grep -rn "#[0-9a-fA-F]\{3,8\}\b\|rgba(\|rgb(" src/styles/layout.css | grep -v "var(" | wc -l
```
Expected: 全绿。新增 **6 条**（`App.auth-gate.test.js` 3、`ChatInput.test.js` 1、`useChat.test.js` 1 pin、`useChunkSelection.test.js` 1 pin）；其中 2 条是**钉档**（今天即绿），台账必须照实记，不许写成"RED→GREEN"。

变异自证三条：① 把 `submit()` 里的 `!props.allowSend` 删掉 → ChatInput 那条的 Enter 半句红；② 只删按钮的 `:disabled="!props.allowSend …"` 半句 → 前半句红、后半句仍绿（证明两条路各有牙）；③ 把 `setupProblem` 的第二个 `if` 删掉（名单为空也说 api_key 那句）→ App 层第二条红。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/App.vue frontend/src/components/ChatInput.vue frontend/src/styles/layout.css frontend/tests/App.auth-gate.test.js frontend/tests/ChatInput.test.js frontend/tests/useChat.test.js frontend/tests/useChunkSelection.test.js
git -c user.name="31439" -c user.email="31439@local" commit -F /tmp/fe2-task11.txt
```
提交信息：`feat(frontend): 未配置横幅 + 发送禁用 + 409 归宿与两条钉档（阶段二 Task 11，含 advisory ③）`

---

## Task 12: 双端门禁 + 真服务/浏览器验收 + 台账 + advisory ⑤

**Files**
- Modify: `backend/tests/test_observability.py`（advisory ⑤：扫描清单改自动发现）
- Create: `.superpowers/sdd/2026-10-07-user-auth-isolation-phase-2/progress.md`（台账，SDD 工作流的既有位置，**不是** `docs/` 下的新文档）
- Temp: `frontend/tmp-layout-probe.mjs`（Edge headless 探针脚本，**用完即删**，`git status` 必须干净）

**Consumes:** Task 1-11 的全部交付物。
**Produces:** 阶段二的收口证据（三门实数 + 12 条浏览器判据 + 台账）。没有代码交付物，只有证据。

- [ ] **Step 1: advisory ⑤ —— `test_observability.py` 的扫描面从写死清单改成自动发现**

`tests/test_observability.py:15-17` 现在是：

```python
SCANNED = ["main.py", "deps.py", "exceptions.py"]
SCANNED_DIRS = ["api", "core", "schemas", "config"]
```

两份清单都是"人记得改才有效"。阶段二没往 `backend/` 加新目录（只加了 `core/llm_factory.py`），所以今天恰好还没漏——**但漏的方式是静默的**：新目录里的 `print` 会一路绿到上线。改成：

```python
# advisory ⑤（阶段一终审顺延清单第 5 条）：原先 SCANNED + SCANNED_DIRS 两份写死的清单
# 要求"加目录的人记得同时加这里"，那不是门禁。改成自动发现 backend 下所有 *.py。
# 排除三处：tests（测试里合法地 print 过、且它不是交付物）、__pycache__ 与 data（都不是源码）。
EXCLUDED_DIRS = {"tests", "__pycache__", "data", ".venv"}


def _backend_py_files():
    return sorted(
        path for path in BACKEND_DIR.rglob("*.py")
        if not any(part in EXCLUDED_DIRS for part in path.relative_to(BACKEND_DIR).parts)
    )
```

`test_backend_sources_have_no_bare_print` 换成用它，并加**两条**防"空集给的绿"：

```python
def test_backend_sources_have_no_bare_print():
    files = _backend_py_files()
    # 下界而不是等号：新增文件不该让门禁红，但"某天 rglob 一个都没找到"必须是红的。
    # 2026-10-07 实测 22 个（阶段二 Task 4 加 core/llm_factory.py 之后是 23），故下界取 22。
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
```

> **顺序**：先跑一次 RED（`assert len(files) >= 999` 之类，只为证明这两条判据真的在数文件、不是空转），改回 `>= 22` 再跑 GREEN；台账记当轮实数。**这条测的是扫描器本身，不是 print**——它在 Task 4 之后才会因为 `core/llm_factory.py` 而变化，本 Task 只需确认 `must in rels` 八项全过。

Run: `cd backend && python -m pytest tests/test_observability.py -q`
Expected: 全绿（含既有两条 logger 判据）。

- [ ] **Step 2: 后端三门（一个进程、一个 pytest、不起 uvicorn 时才能跑前两条）**

```bash
cd backend && python -m pytest -q                                   # 离线门禁（addopts 已排 migration）
cd backend && python -m pytest -q -m "not live and not migration"   # 同口径的显式版，写全两个 not
cd backend && python -m pytest -q -m live                          # 需要真 MySQL；服务不在就整组 skip
```

**基线（阶段一终态实测，权威口径来自 ledger）**：`257 passed / 2 skipped / 2 deselected`（`-m live` 有服务时 `20 passed / 0 skipped`，服务不在 `18 passed / 2 skipped`）。与 §0 表第一行同一条口径。阶段二 Task 1-11 设计上新增的后端判据条数（Task 1 +2 离线 +2 live、Task 3 +约4、Task 4 +约6、Task 5 +约10、Task 6 +3 离线 +1 live、Task 7 +8）只是量级参考，都写在各 Task 的 Step 里，**台账只抄当轮汇总行的实数**，不许用"基线 + 增量"推算出来的数字交差。

若 `-m live` 组里出现 `Unknown column 'chat_history.user_id'` / `no such table: user_models`：**先跑 Task 6 Step 8 那句 DDL 预检**（`create_all` 不给已存在的表加列），别按代码坏了去查。跑法见那一节，只发 `ensure_columns` / `ensure_indexes`，不碰 Chroma、不打印凭证。

- [ ] **Step 3: 前端两门 + 三条样式门禁**

```bash
cd frontend && npm test
cd frontend && npm run build
grep -rn "#[0-9a-fA-F]\{3,8\}\b\|rgba(\|rgb(" src/styles/layout.css | grep -v "var(" | wc -l
grep -rn "<style" src/components/ src/App.vue | wc -l
grep -rn "console\.log\|debugger" src/ | wc -l
```
Expected: `npm test` 全绿（基线 117 + Task 8 的 14 + Task 9 的 10 + Task 10 的 6 + Task 11 的 6 = **153**，文件数 **14**；⚠️ 这个和只是对账用，台账写当轮汇总行实数）；`build` exit 0；后三条 grep 分别 **0 / 0 / 0**。

- [ ] **Step 4: 起真服务（一份，只一份）**

1. 先确认 `:8000` 空着：`powershell -NoProfile -Command "Get-Process python -ErrorAction SilentlyContinue | Select-Object Id,StartTime,CommandLine | Format-List"`（**归属不明的进程不要杀**；`tasklist //FI` 在本机 Git Bash 会报 UNC path，别用）。
2. 端口确实空着才起：`cd backend && python -m uvicorn main:app --host 127.0.0.1 --port 8000`（后台跑）。embedding 按进程加载，**同一时刻只准一个 uvicorn**（本机既有约束）。
3. 前端：`cd frontend && npm run dev`（后台跑，Vite 代理把 `/api` 打到 `:8000`）。
4. `curl` 探一次 `/api/health`（中文载荷若要走 POST 必须写文件，cp936）。**服务是自起的，验收完要收口**（连 `npm run dev` 的父进程一起停）。

- [ ] **Step 5: 浏览器判据 12 条（Edge headless 探针；视口显式设置并回读）**

用本机 Edge + `puppeteer-core --no-save`（既有做法：`npm i --no-save puppeteer-core` 只进 `node_modules`，**`package.json` 必须零 diff**）。脚本 `frontend/tmp-layout-probe.mjs`，跑完 `rm`，并把脚本内容贴进台账而不是留在仓库里。

**视口纪律**：headless 默认视口 754px 会掉进 `max-width:768` 断点——每一档都要 `await page.setViewport({width, height})` **之后回读** `await page.evaluate(() => innerWidth)` 并打印，三档各自的回读值进台账。

| # | 视口 | 判据（选择器逐字取自 Task 9/10/11） |
|---|---|---|
| 1 | 1280×900 | 登录页 → 注册新用户（邮箱 + 口令 ≥6 位，对齐后端 `PASSWORD_MIN = 6`）→ 进工作区，`.user-rail` 在、`.rail-avatar` 是昵称首字母 |
| 2 | 1280×900 | 点 `.rail-settings` → `.settings-panel` 出现；`.settings-apikey-input` 的 `type` 是 `password`，整页 `document.body.innerText` **搜不到**贴进去的 key 原文（只出 `.settings-masked` 的 `sk-****…`） |
| 3 | 1280×900 | 在 `.settings-model-input` 加 `qwen-max` → 名单渲染一行且带 `.settings-default`；再点"删除" → `.settings-model-row` 归零、`.settings-hint` 出"名单是空的" |
| 4 | 1280×900 | 重开弹窗：填 `.settings-apikey-input` + `.settings-baseurl-input` → 保存 → `.settings-masked` 变新掩码、`.setup-banner` **当场消失**（`patchMe` 的链路） |
| 5 | 1280×900 | 名单加两个模型 → `.model-select` 两个 option、`.chat-send` 恢复可点；选第二个模型发一句"你好" → `.chat-messages` 里出现答案气泡（`MessageList.vue:40` 那棵树，**没有 `.chat-history` 这个类**），且 `.error-banner` 不在 |
| 6 | 1280×900 | **未配 key 的门**：另注册第二个账号（不配任何东西）→ `.setup-banner` 在、文案含 `api_key`、`.chat-send` disabled；点 `.setup-open` → `.settings-panel` 开 |
| 7 | 1280×900 | 409 兜底：把模型全删光后硬发一句（DevTools 里绕过 disabled，或直接 `fetch('/api/chat/stream', …)`）→ 红色 `.error-banner` 显示的正是后端那句中文 |
| 8 | 1280×900 | 文档隔离：A 上传一篇探针文档（唯一新文件名）→ A 的 `.metric` 写"📊 文档数 1"、打开候选池 `.picker-results` 能看见它；登出（`.rail-signout`）→ 登录 B → B 的 `.metric` 是"📊 文档数 0"、`.picker-results` 里没有那个文件名（**界面上没有 `.doc-item` 这个东西**，文档列表在阶段二之后的界面里也不出现，可观测面只有 `.metric` 与候选池） |
| 9 | 1280×900 | 历史隔离：A 问一轮 → 登出 → B 登录 → `.chat-messages` 里没有 A 的答案（`chat_history.user_id` 的界面侧证据；DB 侧已有 Task 6 的 live 判据） |
| 10 | 375×800 | `.chat-controls` 不塌：`document.querySelector('.chat-input').scrollWidth <= innerWidth`，且 `.model-select` 与 `.chat-send` 的 `getBoundingClientRect()` 都在视口内 |
| 11 | 375×800 | `.setup-banner` 与 `.settings-model-row` 各自 `scrollWidth <= innerWidth`（后者是"名字+默认+两个按钮"四件那一行，Task 9 加了 `flex-wrap` 就为这一条） |
| 12 | 500×900 | 中间档：`.picker-backdrop` 与 `.settings-panel` 都不遮在聊天按钮之下（阶段一记过一次"窄屏浮层遮住聊天按钮"）；`window.__probe` 回读 `innerWidth === 500` |

**控制台纪律**：每条判据跑完打印 `console` 与 `pageerror` 计数，第 12 条要求**零 error**（`warning` 可以留着但要逐条写进台账说明是什么）。

> **探针的三个已知怪癖**（本机踩过，写在这里省一次排查）：`edge.kill()` 会丢 localStorage ⇒ 每个视口档都重新登录，别指望跨档保会话；jsdom/原生 `confirm` 在 headless 里被自动 accept ⇒ 判据 8 的上传步骤会直接过；按钮定位一律用类名，`textContent` 匹配"发送"会因为 Task 11 的 disabled 文案变化而失配。

- [ ] **Step 6: 台账（`.superpowers/sdd/2026-10-07-user-auth-isolation-phase-2/progress.md`）**

每个 Task 一段，逐条记：**实跑的汇总行原文**、变异自证的红/绿与改动内容、计划与实跑的偏差（用 `> 修订块` 回写进本计划文件，且必须落在 ` ``` ` 围栏**之外**）、`git log --oneline -1` 的 SHA、当轮的偏离（比如"独立评审计数不可用 → 顺序执行"这类）。五条 advisory 逐条销账，各写清落在哪个 Task 的哪个 commit。挂账清单照阶段一的格式：本轮发现但不在阶段二范围内的（如 `%2F` 的代理归一化风险、`--no-save` 装进 `node_modules` 的 puppeteer-core 残留）一条条列出来，不许只写"无"。

- [ ] **Step 7: 提交台账（与 advisory ⑤ 分两笔，代码和文档各一笔）**

```bash
git add backend/tests/test_observability.py
git -c user.name="31439" -c user.email="31439@local" commit -F /tmp/fe2-task12-a.txt
# 信息：test(observability): print 扫描面改成自动发现 + 覆盖率判据（阶段二 Task 12，advisory ⑤）
git add .superpowers/sdd/2026-10-07-user-auth-isolation-phase-2/progress.md docs/superpowers/plans/2026-10-07-user-auth-isolation-phase-2.md
git -c user.name="31439" -c user.email="31439@local" commit -F /tmp/fe2-task12-b.txt
# 信息：docs(ledger): 阶段二收口——三门实数、12 条浏览器判据、五条 advisory 销账
```
提交前 `git status` 必须只看见这两个路径；`frontend/tmp-layout-probe.mjs` 与 `frontend/node_modules` 里的 `puppeteer-core` 都不该出现在 `package.json` / `package-lock.json` 的 diff 里（出现了就 `git checkout -- package.json package-lock.json`？⚠️ **不许**——`--no-save` 装法本就不该改这两个文件，真改了就是环境问题，先查为什么改了再决定，别用 restore 掩盖）。

- [ ] **Step 8: 交付时必须说的两句**

1. **建议轮换 `DEFAULT_USER_PASSWORD`**：Task 3 把 `.env` 的 `DASHSCOPE_API_KEY` / `DASHSCOPE_BASE_URL` / `LLM_MODEL` 三键抄给了默认用户，而默认用户的口令来自这一枚 `.env` 键。它一旦被提交进过版本库或被多人知道，"平台 owner"的身份就等于公开。轮换只在 `.env` 里改，重启后新口令生效（迁移只在 `users` 为空时才建默认用户，不会覆盖已有行）。
2. **阶段二起，未配 key 的用户开始收 409**：这是"从能聊变成不能聊"的**预期翻转**（spec 8 节明写它是验收点之一），不是回归。特别注意默认用户也一样：`DASHSCOPE_API_KEY`/`DASHSCOPE_BASE_URL` 缺任一枚时，Task 3 的 `seed_default_llm` 走的是 `{"llm_written": False, "model_added": False}`（没有 key 却塞一个模型名 = 造一条必 409 的半套配置），名单因此是空的；而 Task 7 的 `_llm_context` **先判名单空、后验凭证**，所以第一条 409 是「你的模型名单是空的」而不是「没配 api_key」——别按文案去找 key。（`LLM_MODEL` 这一键不会缺：`config.py:34` 有默认值。）⇒ **部署前确认 `.env` 的 key 与路由两键齐**，或登录后在设置里把模型加进名单并自带 key。

---

> **阶段二不做的事**（评审时按此裁定，别当遗漏）：不做 api_key 的加密存储（决策 5 已记明文入 MySQL 的权衡）、不做找回密码（spec 7.4）、**不给 `.env` 的 `DASHSCOPE_API_KEY`/`DASHSCOPE_BASE_URL` 加启动期必填校验**（实测 `config/config.py:30-31` 是裸 `os.getenv`，缺键拿到的是 `None` 而不是报错；`:34` 的 `LLM_MODEL` 还带默认值 `qwen3.7-flash`。阶段二的语义是"平台自带的 key 只是默认用户的种子"，Task 3 的 `seed_default_llm` 已经为 `None` 写了分支，各用户没种子也能在设置里自带 key——把这两键改成缺键即炸会让"没配 .env 也能起步"的部署当场起不动，属于第三段工作）、不给 `SettingsModal` 加图片上传（项目里没有文件存储层）、不做令牌滑动续期。
