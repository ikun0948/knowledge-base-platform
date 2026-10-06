# 用户注册登录与数据按用户隔离 — 设计

日期：2026-10-06
路径：architectural（新子系统，非 bounded 改动）
范围：需求 7 条一起谈，因为它们是同一个子系统的两面。**设计本文一份说清；实施计划分两份**——阶段一 = 账号与数据隔离（需求 1、2、3、5），阶段二 = 用户级模型配置与对话门禁（需求 4、6、7），每份能单独回退。

---

## 0. 需求原文与落点对照

| # | 用户原话（摘要） | 落点 | 阶段 |
|---|---|---|---|
| 1 | 做一个用户注册登录的功能，只用简单的邮箱或电话校验即可 | `api/auth.py` + `AuthPanel.vue` | 一 |
| 2 | 把 session_id 换成登录成功后生成的 session_id，重新登陆就生成一个新的 | 登录响应带 `session_id`；前端 localStorage 覆盖 | 一 |
| 3 | 不显示当前 session_id，左下角显示头像和名字，名字旁边一个设置按钮 | `App.vue:114-118` `.session-debug` 整块换成 `.user-rail` | 一 |
| 4 | 登录后可改头像、昵称、密码，配置大模型 api_key 与路由 | `SettingsModal.vue` + `PUT /api/auth/me*` | 二 |
| 5 | 只有登录后才能进行文档分割，显示的文档块按用户分割 | 全部 documents 端点加 `get_current_user` + 归属过滤 | 一 |
| 6 | 只有登录且配置了 api_key 与路由才能对话 | `require_llm_config(user)` → 409 | 二 |
| 7 | 输入框右下角把用户配好的模型名做成下拉，右边发送按钮 | `ChatInput.vue` 改两段式 + `.chat-controls` | 二 |

---

## 1. 已拍板的七项决策

1. **校验强度**：只校验格式（正则），**不发真验证码**、不接 SMTP/短信。零外部依赖。
2. **session 语义**：登录凭证与对话 id **拆开**。每次登录由后端新建一个对话 `session_id`；刷新页面不换（沿用 localStorage 现存值）；登出清掉。
3. **凭证形态**：**服务端会话表 + 不透明令牌**，库里只存令牌哈希，可登出可吊销，零新依赖（`secrets` + `hashlib`）。
4. **旧数据归属**：迁移时建**一个默认用户**，全部现有数据（documents 9 / parent_chunks 11 / child_chunks 22 / 若干历史）划到它名下。基线数字不动。默认用户**可登录**，初始口令来自 `.env` 新键（第 6 节）。
5. **头像形式**：**预设头像（首字母 / 几套表情），不做图片上传**。项目现状没有任何文件存储层（`documents.file_path` 恒为空串），开上传等于新开一个静态文件出口，不划算。
6. **模型下拉来源**：**用户自己维护模型名单**（一行一个，存 `user_models`），不去调远端 `GET /models`。
7. **隔离粒度**：**服务端硬归属校验 + 向量 metadata 补 `user_id` 戳**（软隔离）。不给每用户开独立 Chroma 集合。

---

## 2. 架构与数据模型

### 2.1 新增表

```
users
  id             Integer PK autoincrement
  identifier     String(255) NOT NULL unique      ← 邮箱或手机号原文（登录入口）
  identifier_type String(10) NOT NULL              ← 'email' | 'phone'
  nickname       String(50)  NOT NULL
  avatar         String(20)  NOT NULL              ← 预设标识，不是图片 URL
  password_hash  String(255) NOT NULL              ← 'pbkdf2_sha256$<迭代>$<盐>$<散列>'
  created_at     DateTime

auth_tokens
  id             Integer PK autoincrement
  user_id        Integer FK users.id NOT NULL
  token_hash     String(64) NOT NULL unique        ← SHA-256(令牌) 的 hex
  created_at     DateTime
  expires_at     DateTime
  索引：idx_tokens_user_id(user_id)

user_models
  id             Integer PK autoincrement
  user_id        Integer FK users.id NOT NULL
  name           String(100) NOT NULL
  is_default     Boolean default False
  约束：unique(user_id, name)
```

**为什么是 `identifier` 单列而不是 `email` / `phone` 两列**：两列各 nullable-unique 会让"同一手机号能注册两次"这类边界变得要靠额外约束兜，单列 + 类型列天然唯一。

**为什么 `user_models` 单独一张表**：要支持"增 / 删 / 设默认"三种行级操作，存成逗号串每次都得整串重写，并发下会互相覆盖。

### 2.2 改造现有表（只加列，不删不改类型）

```
documents     + user_id Integer FK users.id NULL   + 索引 idx_documents_user_id
chat_history  + user_id Integer FK users.id NULL   （session_id 列原样保留）
parent_chunks / child_chunks  ← 不加列
```

`parent_chunks` / `child_chunks` **不加归属列**：它们的归属永远能由 `document_id` join `documents.user_id` 得出。冗余一份就要负责两处一致，白担风险。

> **2026-10-06 计划期勘误（列的归属不变，落地阶段改了）**：`chat_history.user_id` 这一列的**写入与读取过滤**归**阶段二**，阶段一只加 `documents.user_id`。原因不是设计变卦，是接线成本：历史行的写入点全在 `RAGSystem` 的四个方法里（`normal_chat` / `chat_with_documents` 及两个流式版），要让它知道 `user_id` 就得给这四个方法加参数、连带改 34 处测试调用点；而阶段二的 `llm_factory` 改造**本来就要把这四个方法连同那 34 处重接一遍**。分两段各动一次，同一个文件动两轮、评审两遍，中间没有换来任何东西。
>
> 阶段一期间历史隔离靠什么：`session_id` 由后端在登录时 `uuid4()` 铸造（第 1 节决策 2），不可枚举、不随刷新变，跨用户撞上的概率与"猜中一个 uuid4"同级。阶段一给 `GET/DELETE /api/history/{session_id}` 上的**登录门**已经排除了匿名访问。

### 2.3 现有单例的拆与留

`app.state` 上 5 个 lifespan 单例（`main.py:42-47`）里：

- **留**：`config`、`db`、`doc_processor`、`vector_store`。embedding（0.6B，`vector_store.py:20-21`）与 Chroma client 绝不能按请求构造——`main.py:37-40` 那条注释写的就是这个教训。
- **拆**：`RAGSystem.__init__` 的 `self.llm`（`rag_system.py:27-33`）、`VectorStore.__init__` 的 `self.llm` 与 `self.compressor`（`vector_store.py:42-49`）。它们把"一个进程一套 key"写死了。
- **压缩器搬家**：`LLMChainExtractor` 从 `VectorStore` 移进 `RAGSystem`（请求内构造）。理由不是风格：压缩器攥着一个属于某用户的 LLM，攥在全库共享的向量层里就是东西放错了地方。搬完 `VectorStore` 只剩向量、检索、删除。

`ChatOpenAI(...)` 每次请求新建不心疼：构造只建对象，不发网络。

### 2.4 新增模块 `backend/core/llm_factory.py`

```python
@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str

def build_llm(cfg: LLMConfig, model: str, temperature: float) -> ChatOpenAI: ...
def build_compressor(cfg: LLMConfig, model: str): ...   # 内部 temperature 固定 0
```

答题链用 `temperature=0.7`、`streaming=True`（沿用 `rag_system.py:31-32` 现值），压缩链用 `temperature=0`（沿用 `vector_store.py:46` 现值）。

### 2.5 向量层的用户维度

- `add_documents`（`vector_store.py:75-84`）现在给每条文档补 `document_id` 戳；同一手法多补一个 `user_id`。
- `create_retriever`（`vector_store.py:86-96`）的过滤从 `{"parent_id": {"$in": [...]}}` 换成
  `{"$and": [{"user_id": "<id>"}, {"parent_id": {"$in": [...]}}]}`。
- 集合名仍是 `parent_document` / `child_document` 两个常量，`collection_counts()` 与 `/api/health` 的语义不变（**全局物理计数**）。

> **2026-10-06 计划期勘误（拆成两段落地）**：**写侧补戳**（`add_documents` 多打一个 `user_id`）+ 迁移补历史戳归**阶段一**；**读侧的 `$and` 过滤**归**阶段二**。
>
> 不是漏做：`parent_id` 全库唯一（`database.py:46`），而阶段一的问答入口已经先校验过"这些 `parent_id` 属于当前用户"（第 3.3 节），带 `$in` 的过滤条件本身就只可能命中他自己的子块——读侧 `$and` 在阶段一没有一层是承重墙，纯属纵深。等阶段二 `create_retriever` 因 `llm_factory` 必须改签名时一起加，才是顺路。

### 2.6 Config 的变动

`Config` 新增一个属性 `AUTH_TOKEN_TTL_DAYS`（`os.getenv(..., "30")`，与 `TOP_K` 同档的调参键）。

`DASHSCOPE_API_KEY` / `DASHSCOPE_BASE_URL` / `LLM_MODEL` 三键**降级为迁移种子**：只在首次建默认用户时抄给它，运行期问答链一律不再读（改读用户行）。三属性本身仍留在 `Config` 上，属性集钉（`test_config.py` 的 `SANCTIONED_ATTRS`）只需加 `AUTH_TOKEN_TTL_DAYS` 一项。

> **2026-10-06 计划期勘误（两处更正）**：
> 1. `SANCTIONED_ATTRS` 要加的是**两项**——`AUTH_TOKEN_TTL_DAYS` 与 `DEFAULT_USER_PASSWORD`（第 6 步默认用户口令来自 `.env`，必须过一个 Config 属性才拿得到，不能就地 `os.getenv`）。那句"只需加一项"写漏了。
> 2. "三键降级为迁移种子"这件事发生在**阶段二**：阶段一的问答链照旧直接读 `Config`（两处 `ChatOpenAI` 还没拆），所以阶段一结束时它们仍是运行期真值，不是种子。抄送给默认用户（第 6 节步骤 4）也随之归阶段二。

---

## 3. 后端 API

### 3.1 新 router `backend/api/auth.py`，前缀 `/api/auth`

| 端点 | 入参 | 出参 | 阶段 |
|---|---|---|---|
| `POST /register` | `identifier_type`、`identifier`、`password`、`nickname?` | 201 `{token, user, session_id}` | 一 |
| `POST /login` | `identifier`、`password` | 200 `{token, user, session_id}` | 一 |
| `POST /logout` | （当前令牌） | 204 | 一 |
| `GET /me` | （当前令牌） | `{user}` | 一（api_key_masked 与 models 阶段二补） |
| `PUT /me` | `nickname` / `avatar` | `{user}` | 二 |
| `PUT /me/password` | `old_password`、`new_password` | 204 | 二 |
| `PUT /me/llm` | `api_key`、`base_url` | `{user}` | 二 |
| `POST /me/models` / `DELETE /me/models/{name}` / `PUT /me/models/default` | `name` | `{models: [...]}` | 二 |

`user` 的响应形状（`schemas/auth.py` 的 `UserOut`）：`id`、`identifier`、`identifier_type`、`nickname`、`avatar`、`llm_configured: bool`、`llm_base_url`、`api_key_masked: str`、`models: [str]`、`default_model: str|null`。

阶段归属：前五项（`id`/`identifier`/`identifier_type`/`nickname`/`avatar`）是阶段一的形状；后五项要先有 `users.api_key`、`users.base_url` 两列和 `user_models` 表，随阶段二一起加。阶段一不多回空壳字段。

**`api_key_masked` 的口径**：`sk-` 前缀保留 + 尾 4 位，其余一律 `****`。原文**任何端点都不返回**、任何日志都不打印。

> **2026-10-06 计划期勘误**：原表里 `GET /me` 的出参写作 `{user, session_id_present}`，现改为只回 `{user}`。`session_id_present` 没有后端可判定的真相源——对话 id 只存在前端 localStorage（第 5.3 节），库里没有"当前会话"这一行，`GET /me` 无从知道前端手上有没有它；返回一个前端不能用来做任何决定的字段就是死契约。刷新路径照旧：`/me` 只验令牌，id 沿用本地值。

### 3.2 认证依赖

`deps.py` 新增 `get_current_user`：读 `Authorization: Bearer <token>` → SHA-256 → 查 `auth_tokens`（带 `expires_at > now()`）→ 拿 `user_id` 查 `users`。任一步失败 → **401**，不回"哪一步失败的"。

业务端点全部纳入：`documents`（4 个）、`chat`（2 个）、`history`（2 个）共 8 个端点加 `user = Depends(get_current_user)`。`/api/health` **不加**（它是运维探针，且现在 `test_health.py` 与记忆里的基线判据都靠它裸奔可达）。

这 8 个的完整清单（第 7.2/7.3 节"逐个打 401"就按这张表数，少一个就是漏一个门）：

1. `POST /api/documents`
2. `GET /api/documents`
3. `GET /api/documents/chunks`
4. `DELETE /api/documents/{document_id}/chunks/{parent_id}`
5. `POST /api/chat`
6. `POST /api/chat/stream`
7. `GET /api/history/{session_id}`
8. `DELETE /api/history/{session_id}`

### 3.3 归属校验（硬门）

所有按 id 取文档/块的入口，先确认 `documents.user_id == user.id`；不是就 **404**，复用现有文案「文档块不存在或已被删除」。列表类入口（`GET /api/documents`、`GET /api/documents/chunks`）加 `WHERE documents.user_id = :uid`。

**为什么是 404 不是 403**：403 等于向外人承认"这东西存在，只是你不该碰"。

### 3.4 对话门禁

chat 两个端点在碰 `rag` 之前先 `require_llm_config(user)`：缺 `api_key` 或缺 `base_url` → `NotConfiguredError` → 409。放在端点而不是 `RAGSystem`：`RAGSystem` 只管问答，"能不能问"是端点的事。

`ChatRequest` 新增可选字段 `model_name`（`str`，1..100）。规则：空 → 用该用户 `is_default` 的那个（没有 default 就取名单第一个）；非空 → 必须存在于该用户的 `user_models`，否则 409「模型不在你的名单里」。**不做静默回落**——回落会让"我明明选了 max 怎么答得这么笨"变成查不动的悬案。

### 3.5 错误码总表

`main.py:27-32` 的 `STATUS_BY_ERROR` 从 4 项扩到 6 项（加 `AuthError→401`、`NotConfiguredError→409`；越权不走异常表，端点直接 `HTTPException(404)`）。

| 情形 | 码 | 文案 |
|---|---|---|
| 无令牌 / 过期 / 坏令牌 | 401 | `未登录或登录已过期` |
| 账号不存在 **或** 密码错（同一响应） | 401 | `账号或密码不正确` |
| 注册时账号已占用 | 409 | `该账号已注册` |
| 格式坏、参数越界 | 422 | 走现有 `请求参数不合法：` 引导句 |
| 别人的文档 / 块 id | 404 | `文档块不存在或已被删除` |
| 已登录但没配 api_key 或路由 | 409 | `请先在设置里配置大模型的 api_key 与路由` |
| 模型名不在该用户名单 | 409 | `模型不在你的名单里` |

**登录失败为什么不分两种文案**：分开回等于把"哪些邮箱注册过"送给外人（账号枚举）。

### 3.6 连带改动（不能漏的账）

- `main.py:55-61` CORS `allow_methods` 现在只有 `["GET","POST","DELETE"]`，**必须加 `PUT`**。
- `parent_id` 全局唯一（`database.py:46`，由清洗后的文件名派生）⇒ **跨用户同名上传会撞唯一键**。本次不改这个事实，但归属校验会让它表现为"上传失败 500"。列为已知遗留，进第 7 节。

---

## 4. 密码与令牌（零新依赖）

- **口令哈希**：标准库 `hashlib.pbkdf2_hmac('sha256', pwd, salt, 390000)`，盐 `secrets.token_bytes(16)`，存成 `pbkdf2_sha256$390000$<盐 hex>$<散列 hex>`。比较用 `hmac.compare_digest`（防时序）。**不引入 bcrypt**——要装包，且 pbkdf2 把盐/迭代/慢哈希三个概念留在可读的代码里。
- **令牌**：`secrets.token_urlsafe(32)` 原文只在登录响应里出现一次；库里存 `sha256(token).hexdigest()`。TTL 30 天绝对过期（`Config.AUTH_TOKEN_TTL_DAYS`），不做滑动续期。登出 = 删该行；改密码**不**吊销其它令牌（列为遗留）。
- **api_key 明文存 MySQL**：对称加密要一个主密钥，而密钥只能放同一台机器的 `.env`，读盘的人两样都拿得到，等于只防"单独拖走数据库"这一种场景。本期取明文 + **永不回传**（只回 `api_key_masked`）+ **永不打印**。

---

## 5. 前端

### 5.1 不引入 vue-router

`main.js:7` 直挂 `#app`，`package.json` 运行时依赖只有 `vue`。登录态用条件渲染：`user` 为空 → 整屏 `<AuthPanel>`；非空 → 现有 `.app-shell`。**未登录时 `DocumentPanel` 和上传按钮根本不渲染**——比"渲染出来但禁用"更难漏。

### 5.2 启动流程（改 `App.vue:32-38` 的 `onMounted`）

```
读 localStorage 的 auth_token
  ├─ 有 → GET /api/auth/me
  │        ├─ 200 → 设 user → 再 refresh() / hydrate() / restore(sessionId)
  │        └─ 401 → 清 token，静默落回登录页（不弹横幅）
  └─ 无 → 直接渲染登录页，一个请求都不发
```

`refresh/hydrate/restore` 三步**必须在"确认已登录"之后**，否则未登录时会打出一串 401 横幅。

### 5.3 session_id 的确切语义（需求 2）

- 注册/登录 → 后端 `uuid4()` 造对话 id 随响应返回 → 前端**覆盖** localStorage 的旧值 ⇒ 重新登录就是新对话。
- 刷新 → `GET /me` 只验令牌、**不发新 id**，前端用现存 id 恢复历史 ⇒ 刷新不丢对话。
- 登出 → `auth_token` 与 `session_id` 一起清。
- `useSession.js` 保留：`crypto.randomUUID()` 只作**离线兜底**（正常路径 id 来自后端）。localStorage 三个键：`auth_token`、`session_id`、`selected_parent_ids`。

### 5.4 左下角（需求 3）

`App.vue:114-118` 的 `.session-debug` 块整块删除（含 `<code class="session-value">` 与"换一个 session_id"按钮）。原位置 `.user-rail`：头像 + 昵称 + ⚙ 设置按钮（`aria-label="打开设置"`）。

**但"换一个新的 session_id"这个能力不能跟着按钮一起删**。`App.vue:50` 的注释写明现有行为与归档 `app.py` 等价：**清空对话后会换一个新 id**。按钮没了，这个换 id 的动作必须留在 `handleClear`（或 `useAuth.clearHistory`）里，否则"清空对话"会退化成"清空但不换 id"，与归档行为不一致，而且旧 `chat_history` 行还挂在同一个 id 上——将来任何"重新拉历史"的路径都会把刚清空的对话捞回来。判据：清空后 `localStorage.session_id` 的值必须与清空前不同，且不等于历史里任何一条的 id。

`StatusBar.vue:19` 那个显示 session 前 8 位的 `.session-chip` **一并去掉**——否则 session_id 只是从左下挪到了顶上，等于没删。

### 5.5 新组件

| 文件 | 职责 |
|---|---|
| `composables/useAuth.js` | token/user 读写、login/register/logout/patchMe、401 静默清 |
| `api/auth.js` | 第 3.1 节端点的薄封装 |
| `components/AuthPanel.vue` | 登录/注册二合一（tab 切换），前端先拦一道格式 |
| `components/SettingsModal.vue` | 复用 `.picker-backdrop` / `.picker-modal` 骨架：昵称+头像、改密码、api_key/base_url、模型名单增删设默认 |

### 5.6 令牌的注入落点（三条网络出口，只有一条现成有注入位）

- `client.js:28-32` `request()` 的 headers 展开位 → 改成**模块级 `setAuthToken(token)` 统一注入**（不让每个调用方自己记得传，传漏了就是一片 401）。
- `client.js:48-56` `postStream` 的 headers 是硬编码 → 同样吃 `setAuthToken`。
- `documents.js:35` `uploadDocument` 走 **XMLHttpRequest**，压根没调 `setRequestHeader` → 补 `xhr.setRequestHeader('Authorization', ...)`。**这条最险**：它是全项目唯一不走 `client.js` 的出口，漏掉的表现就是"登录了、文档却传不上去"。

### 5.7 输入框（需求 7）

`.chat-input` 从「textarea + 按钮同一行」改成**两段**：textarea 在上，`.chat-controls` 在下、右对齐放 `<select class="model-select">` + 发送按钮（`pending` 时仍是「⏹ 停止生成」，`ChatInput.vue:37-38` 的逻辑现成复用）。

`ChatInput` 新增 props `models: Array`、`selectedModel: String` 与 emit `update:selectedModel`。**不能叫 `model`**——`modelValue` 已被 textarea 占了，撞名会以难查的方式互相覆盖。

未登录但没配 api_key：输入框上方一条横幅「还没有配置大模型，先去设置里填 api_key 与路由」+ 发送按钮禁用。后端 409 是权威兜底，前端这条只让人少摔一跤。

### 5.8 样式（守 G-4：`variables.css` 之外颜色字面量必须 0 命中）

新 token（`--avatar-*`、`--control-gap` 等）一律进 `variables.css:43` 之后；`.user-rail`、`.chat-controls`、`.model-select`、`.auth-panel` 进 `layout.css`。≤768 断点（`layout.css:101-124`、`:295-301`）要为 `.chat-controls` 与 `.user-rail` 补分支，避免重演"行高未中和"那类塌行。

---

## 6. 迁移与回滚

新增 `backend/core/migrations.py`，在 `database.py:117-119` 的 `create_all` 之后调用。`Base.metadata.create_all` **只建新表、不给已有表加列**，所以加列必须自己来。

顺序（每一步幂等）：

1. 建表（`users` / `auth_tokens` / `user_models`）——`create_all` 覆盖。
2. 查 `information_schema.COLUMNS`，缺列才 `ALTER TABLE ADD COLUMN`（MySQL 没有 `ADD COLUMN IF NOT EXISTS` 写法，只能"先查再改"）。
3. 若 `users` 为空：建默认用户 `identifier='default@local'`、`identifier_type='email'`、`nickname='默认用户'`，口令取 `Config.DEFAULT_USER_PASSWORD`（`.env` 新键；**为空则该账号不可登录**，只作数据归属锚点）。
4. 把 `.env` 的 `DASHSCOPE_API_KEY` / `DASHSCOPE_BASE_URL` / `LLM_MODEL` 抄给默认用户（存进它的 llm 配置与 `user_models` 一行）——这是坑 9 成果的去向：`Config.LLM_MODEL` 从"运行期读的值"降级为"迁移种子"。
5. `UPDATE documents SET user_id=<default> WHERE user_id IS NULL`；`chat_history` 同理。
6. 旧向量补戳：从 `parent_chunks.vector_id` / `child_chunks.vector_id` 读 id 清单（这两列存的就是 Chroma 的 id，2026-10-04 已 live 验过：用它删向量计数如实下降），然后 `collection.update(ids=..., metadatas=[{"user_id": <default>}]*n)`。**只改 metadata，不重新嵌入、不搬家。**

> **2026-10-06 计划期勘误（阶段归属与调用位置）**：
> - 阶段一实际执行的是 **1、2（只加 `documents.user_id`）、3、5（只 `documents`）、6**；步骤 4（抄三键）与步骤 2/5 的 `chat_history` 部分归阶段二，理由见 2.2 与 2.6 的同一批勘误。
> - 步骤 6 必须**先 `get` 出现有 metadata 再合并写回**（`{**existing, "user_id": str(uid)}`），并把已有正确 `user_id` 的向量跳过。Chroma 的 `update` 只补提供的键是较新版本的语义，不依赖它——读回来合并写才是最保守的做法，跳过已戳的又让"每次开机都重跑"变成一次只读扫描。
> - **调用位置钉在 `lifespan`**（`main.py:42-47` 那段里，`VectorStore` 之后、`RAGSystem` 之前），不挂在 `DatabaseManager.init_database` 里：`test_observability.py:50` 钉死了"init 只发 `engine` + `create_all` 两次调用"，把 ALTER 塞进 init 会让那条测试红；更重要的是步骤 6 需要 `vector_store`，而它在 `db` 之后才构造。

**回滚是真回滚**：新列留着不 `DROP`、新表留着不删、向量多出的 `user_id` 键旧代码根本不读。代码退到上一个提交即可运行。默认用户账号留着无害。

`.env.example` 同步加 `DEFAULT_USER_PASSWORD`（附一行中文注释），真实值不入库。

---

## 7. 测试与验收

### 7.1 现有测试的连带成本（实数，不粉饰）

现在基线：后端 `pytest -q` **176 passed / 1 deselected**，前端 **84 passed / 7 文件**，`npm run build` exit 0。

| 影响面 | 条数 | 性质 |
|---|---|---|
| 走 TestClient 的端点测（chat 29 / documents 20 / history 14 / chunk_search 9 / error_model 4） | 76 | 全撞 401。缓解：各模块**自己的** `make_client()`（共 6 个函数，不是 76 个测试）默认覆盖 `get_current_user`，`tests/fakes.py` 加 `FakeUser` |
| `test_rag_system.py` | 21 | `build()` 里手工塞 `rag.llm` 的接线要改（LLM 不再挂在实例上） |
| `test_vector_store.py` | 9 | 压缩器搬走，桩件的 `compressor` 属性跟着改 |
| `test_config.py::SANCTIONED_ATTRS` | 1 | 加 `AUTH_TOKEN_TTL_DAYS`（外加 `DEFAULT_USER_PASSWORD` 若进 Config） |
| 坑 9 的两条构造点判据 | 2 | 改写为钉 `llm_factory` 入参（上一轮交付物的直接连带，非回归） |
| `-m live` 组 | 14 | 改成"先注册 live 用户 → 配 key（值从 `.env` 读，永不打印）→ 再聊" |

> **2026-10-06 计划期更正（这张表按阶段重切，实数已核）**：
> - **阶段一不碰 `test_rag_system.py`**（那 21 条）、也不碰坑 9 的两条构造点判据——它们都系在 `llm_factory` 上，属阶段二。
> - 阶段一对 live 组的真改动是另一件事：`test_live_database.py` 的 **32 处** DB 调用点要带 `user_id`（`save_document` / `get_document` / `search_parent_chunks` 等写读都进了归属参数），`test_live_stream.py` 的 **3 条**真 HTTP 流式测要在头里带一枚真令牌（登录 `default@local`，口令取 `Config.DEFAULT_USER_PASSWORD`，永不打印）。
> - `SANCTIONED_ATTRS` 加 **两项**（`AUTH_TOKEN_TTL_DAYS`、`DEFAULT_USER_PASSWORD`）。
> - `test_error_model.py::test_central_map_covers_every_domain_error_class` 那条"异常表一格不漏"的钉，阶段一要从 4 项改 5 项（加 `AuthError`）。
> - `make_client` 的**定义**实测是 **5 处**（`test_api_chat` / `test_api_documents` / `test_api_history` / `test_chunk_search` / `test_health`），其中 `test_health` 那条不需要动（`/api/health` 不上门）；上表原写"6 个"是把 `test_error_model.py` 的 `probe_app()` 数了进去，那个探针路由不依赖 `get_current_user`，同样不用动。

### 7.2 新增测试

- `test_api_auth.py`（约 18 条）：注册成功 / 邮箱与手机号格式各档坏值 / 重复注册 409 / 登录成功 / 密码错 401 / 账号不存在与密码错**响应逐字节相同** / 坏令牌 401 / 过期令牌 401 / 登出后同令牌立刻 401 / `GET /me` 不回 api_key 原文 / 改密码要旧密码 / `api_key_masked` 形状 / 名单增删与设默认。
- `test_ownership_isolation.py`（约 8 条）：A 的列表不含 B 的文档；A 用 B 的 `parent_id` 问答得 404；A 删 B 的块得 404；**不带 Authorization 逐个打 8 个业务端点都 401**（参数化）；带 `user_id` 的 Chroma 过滤确实生效（假向量库断言 filter 形状）。
- `test_llm_factory.py`（约 6 条）：`build_llm` 吃的 api_key/base_url/model 来自用户行而非 Config；压缩器 temperature=0、答题 0.7；两处的 model 同源。
- `test_migrations.py`（约 5 条）：连跑两遍结果一致（幂等）；旧行归默认用户；向量补戳后 metadata 有 `user_id` 且向量文本未变；`DEFAULT_USER_PASSWORD` 为空时该账号不可登录。
- 前端新增约 20 条：`useAuth.test.js`、`AuthPanel.test.js`、`SettingsModal.test.js`、`ChatInput.test.js` 扩（选中模型随 send 上抛、`selectedModel` 与 `modelValue` 不撞名）；**`client.test.js` 加"Authorization 头自动带上"断言**（三条出口漏一条的守卫）。

### 7.3 基线自证清白（不碰共享库）

判据不登录默认用户，而是**注册两个一次性新用户 A / B**：

1. A 上传探针文档（唯一新文件名）→ A 文档列表 1 篇、B 列表 0 篇；
2. A 用 B 的 `parent_id` 问答 → 404；
3. 删掉 A 的探针，A 回 0 篇；
4. `/api/health` 全程 **9 / 11 / 22** 不动（它是全局物理计数）；
5. 旧数据归位用 SQL 直查：`SELECT COUNT(*) FROM documents WHERE user_id=<default>` = 9。

正证（新用户看得见自己的）+ 反证（新用户看不见别人的、全局数不变）都有，才算隔离成立。

浏览器 live 判据另列约 12 条（登录页渲染、未登录不请求、左下角头像+昵称+⚙、设置弹窗改昵称、api_key 只显示 masked、模型下拉列出选项且能选中、未配 key 时发送禁用并出 409 文案、窄屏 375×800 下 `.chat-controls` 不塌、零控制台错误）。视口要显式设置并回读原始值（headless 默认 754px 会掉进 `max-width:768` 断点）。

### 7.4 已知遗留（写进 spec 就收，不进本轮实现）

1. 跨用户同名文件上传仍撞 `parent_id` 唯一键（第 3.6 节），改造后表现为上传失败。
2. 改密码不吊销其它已发令牌。
3. `users.identifier` 用单列存邮箱或手机号，"同一邮箱与同一手机号被两个人分别注册"这种关联识别不做。
4. 无找回密码（要真发邮件，第 1 节已排除）。
5. api_key 明文存库（第 4 节权衡已记）。

---

## 8. 分阶段交付

**阶段一（先做，能独立上线）**：`users` / `auth_tokens` 两张表、`core/security.py`（pbkdf2 与不透明令牌）、`api/auth.py` 的 register/login/logout/me、`deps.get_current_user`、`exceptions.AuthError`→401、8 个业务端点加登录门、`documents` 侧的归属列与归属过滤（上传/列表/候选池/删块/问答入参校验）、向量写侧补戳、迁移 1/2/3/5/6（只 `documents.user_id` + 旧向量戳）、CORS 加 `PUT`、前端 `useAuth` + `AuthPanel` + `.user-rail`（删 `.session-debug` 与 `.session-chip`，但"清空即换 id"的动作留在 `handleClear`）、三条出口的令牌注入、第 7.1 表里那 76 条端点测的 `make_client()` 改造与 live 组的 `user_id`/令牌改造。

**阶段二（接着做，依赖阶段一的 user 上下文）**：`users.api_key` / `users.base_url` 两列 + `user_models` 表与设置类端点（PUT /me、/me/password、/me/llm、名单增删）、`chat_history.user_id` 列与历史读写过滤（连带 `RAGSystem` 四个方法与 34 处调用点）、迁移步骤 4（把 `.env` 三键抄给默认用户）、`llm_factory` 与两处单例拆除、压缩器搬家、`create_retriever` 的读侧 `$and` 用户过滤、`ChatRequest.model_name` 与 409 门禁、`SettingsModal`、输入框两段式 + 模型下拉、未配 key 的禁用横幅。

拆得开的理由：阶段一交付后"多人各管各的文档"就成立，问答链仍直读 `.env` 那把平台 key（阶段一的迁移**不**抄 key，见 2.6 勘误），所以**任何**登录用户都能问、也都花在同一把 key 的额度上；阶段二才把模型配置交到用户手上。任一段出问题只回退那一段。

**两段各自的能力边界（验收时别判错）**：

- **阶段一结束时**：登录用户**就能对话**，走的是 `.env` 那把平台 key（两处单例还没拆）。此时任何用户的问题都会花在同一把 key 的额度上——这是刻意的中间态，不是漏了门禁。
- **阶段二上线的那一刻起**：问答改读用户自带的 key，**没配过的用户点发送会开始收到 409**「请先在设置里配置大模型的 api_key 与路由」。这条"从能聊变成不能聊"的行为翻转就是阶段二的验收点之一，必须有判据钉住（老用户在阶段二后首次进入要能在界面上看到"去设置"的指引，否则会以为服务坏了）。
- 阶段一的 live 判据里"对话成功"这条在**任何**登录用户身上都能打；阶段二之后就要改成只在**配好 key 的用户**身上打。
