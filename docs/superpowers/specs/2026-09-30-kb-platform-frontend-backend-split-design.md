# 知识库平台：前后端分离改造设计

> 项目路径：`D:\AI-python\知识库平台`
> 设计日期：2026-09-30
> 状态：已与用户逐节确认，待用户复核本文
> 前置阅读：`知识库平台开发文档.md`（第一～七节；本文引用的"坑 N"均指其第七节编号）

---

## 一、目标与非目标

**目标**

1. 把 Streamlit 单体（`app.py` 同时承担 UI 与业务流程）拆成两个独立进程：FastAPI 只提供 HTTP 接口，Vue 3 只负责界面与交互。
2. 能力等价迁移：文档入库、RAG 问答、普通对话、会话历史、清空对话——迁移后现有三条主线能力一条不少。
3. 顺手修掉本次改造会真实踩到的 5 个问题（详见第七节），不做大范围重构。
4. 补齐工程基建：`requirements.txt`、`.env.example`、`pytest`（当前三者全无）。

**非目标**（明确排除，避免范围蔓延）

- 不做多会话列表 / 会话切换（对应开发文档第八节第 4 条方向）。
- 不做用户鉴权、租户隔离。
- 不做文档删除 / 重新索引 / 版本化（`is_active` 仍保持"设计了但没人置为 False"的状态，另立任务）。
- 不换 embedding 模型、不改检索策略（混合检索、rerank 均不做）。**注意：换 embedding 模型必须重建 Chroma 集合**，本次不碰这个雷。
- 不做 Markdown 渲染。

---

## 二、已确认的五个决策

| # | 决策 | 选项 | 理由 |
|---|---|---|---|
| 1 | 前端形态 | Vue 3 + Vite 工程化（非 CDN 免构建） | 行业标准，后续加路由/构建产物顺 |
| 2 | 输出方式 | 分两步：先 `POST /api/chat` 普通接口打通全链路，再加 SSE 真流式 | 普通接口可测、可回退；SSE 是增量而非前置依赖 |
| 3 | 改造范围 | 拆分 + 顺带修高危 1/2/3 与坑 6 + 补 `used_chunks` 写入 | 这几处不修会以"新接口的 bug"形式暴露，排查时与"原本就有坑"混淆 |
| 4 | 会话契约 | 前端持有 `session_id`（localStorage）+ 后端提供历史查询/清除接口 | 单一真相在后端，localStorage 只存 id |
| 5 | 目录布局 | 同仓 `backend/` + `frontend/` + `legacy_streamlit/`，Streamlit 归档不删 | 保留可对照的旧实现，回退成本低 |

---

## 三、进程拓扑

```
开发期
  浏览器 ── http://localhost:5173 ──▶ Vite dev server
                                          │  server.proxy: /api → http://127.0.0.1:8000
                                          ▼
                                       uvicorn (backend/main.py)  :8000
                                          │
                    ┌─────────────────────┼──────────────────────┐
                    ▼                     ▼                      ▼
                 MySQL:mydb      Chroma(本地持久化)        DashScope LLM
                                backend/data/chroma_db    qwen（OpenAI 协议）
                                          ▲
                                本地 embedding 模型（0.6B，进程启动时加载一次）
```

- 前端所有请求走 `/api/...` 相对路径 → 浏览器视角同源，开发期不碰 CORS。
- 后端仍装 `CORSMiddleware`，白名单只放 `http://localhost:5173`，作为"直接打开 dist / 换端口"的兜底。
- 生产期：`npm run build` → `frontend/dist`，交给任意静态服务器；本文不设计 FastAPI 托管 dist（会把两种部署模式混在一起，增加"接口 404 还是页面 404"的歧义）。

---

## 四、目录结构

```
知识库平台/
├── backend/
│   ├── main.py                     # create_app() + lifespan + 异常处理器
│   ├── api/
│   │   ├── documents.py            # POST /api/documents、GET /api/documents
│   │   ├── chat.py                 # POST /api/chat（阶段二加 /api/chat/stream）
│   │   └── history.py              # GET/DELETE /api/history/{session_id}
│   ├── schemas/
│   │   ├── common.py               # Reference、ChatMode 等共用模型
│   │   ├── documents.py
│   │   └── chat.py
│   ├── core/                       # ← 现有 4 个模块复制入，逻辑不变，只改 import 与第七节的修补
│   │   ├── database.py
│   │   ├── document_processor.py
│   │   ├── vector_store.py
│   │   └── rag_system.py
│   ├── config/config.py            # ← 复制入，.env 定位与 cwd 无关（见 7.1）
│   ├── .env                        # 真实配置（不入库）；模板见下一行
│   ├── .env.example                # 只写键名与注释，不含任何真实值
│   ├── data/chroma_db/             # ← 现有向量数据 copy 进来
│   ├── deps.py                     # app.state 单例 → 依赖注入函数
│   └── tests/
│       ├── test_document_processor.py
│       ├── test_vector_store.py
│       └── test_api.py
├── frontend/                       # 见第五节
├── legacy_streamlit/               # app.py、streamlit页面.py、.streamlit/ + config/core 冻结副本（见 7.2）
├── docs/superpowers/specs/
├── requirements.txt
└── 知识库平台开发文档.md            # 保留，并在文末追加指向本文的链接
```

`core/` 四个模块原本不认识 Streamlit（唯一的耦合是 `document_processor.load_document` 吃 `st.UploadedFile`），所以复制一份出来改造的代价很低——这是既有分层的回报。复制而非移动的理由见 7.2。

---

## 五、前端结构

```
frontend/
├── index.html
├── vite.config.js               # server.proxy: {"/api": {target: "http://127.0.0.1:8000", changeOrigin: true}}
└── src/
    ├── main.js
    ├── App.vue                  # 两栏布局：DocumentPanel（左）/ ChatPanel（右）；≤768px 侧栏可折叠
    ├── api/
    │   ├── client.js            # 唯一的 fetch 封装：JSON 序列化、!res.ok → throw Error(detail)
    │   ├── documents.js         # uploadDocument(file, onProgress) / listDocuments()
    │   ├── chat.js              # sendChat(payload)；阶段二加 sendChatStream(payload, handlers)
    │   └── history.js           # getHistory(sessionId) / clearHistory(sessionId)
    ├── composables/
    │   ├── useSession.js        # localStorage 取 session_id，无则 crypto.randomUUID()
    │   ├── useDocuments.js      # 文档列表、上传队列（每文件独立 pending/ok/fail + 重试）、selectedIds
    │   └── useChat.js           # messages[]、send()、pending、打字机驱动
    ├── components/
    │   ├── ChatHeader.vue  StatusBar.vue  MessageList.vue  MessageBubble.vue
    │   ├── ReferenceList.vue  ChatInput.vue
    │   └── DocumentPanel.vue  FileUploader.vue  DocCard.vue
    ├── utils/typewriter.js      # 从 app.py 搬来的分词逐字逻辑，正则保持 `[A-Za-z0-9]+|\s+|.`
    └── styles/
        ├── variables.css        # --brand-1:#667eea --brand-2:#764ba2 --bubble-user/--bubble-assistant
        ├── base.css             # reset + 字体 + 打字机 @keyframes blink
        └── layout.css           # 两栏栅格 + 响应式断点
```

**状态管理：不装 Pinia/Vuex。** 跨组件共享的只有"勾选了哪些文档"和"当前 session_id"，三个 composable 在 `App.vue` 里显式传参足够。引入状态库会把学习成本花在工具而非数据流上。

**消息持久化：前端不存消息。** `localStorage` 只存 `session_id`；刷新页面后由 `GET /api/history/{session_id}` 恢复（含引用片段）。双写必然不一致，后端是真相；代价是后端不可用时看不到历史，已知并接受。

**CSS 迁移取舍**：`.message`/`.doc-card`/`.status-indicator`/打字机动画等聊天相关规则有效迁移；`app.py` 里 `[data-testid="stSidebar"]`、`stChatInput`、`stMainBlockContainer` 那批覆盖规则是 Streamlit DOM 专有，全部丢弃。

---

## 六、后端 API 契约

**约定：不加统一响应壳。** 成功直接返回资源本身，失败用 HTTP 状态码 + FastAPI 默认 `{"detail": "..."}`。前端只需一条规则：`!res.ok` 则读 `detail` 弹提示。

### 6.1 端点表

| 方法 | 路径 | 请求 | 成功 | 主要失败 |
|---|---|---|---|---|
| GET | `/api/health` | — | `{status:"ok", chroma_dir, document_count, vector_counts:{parent, child}}` | 500 |
| POST | `/api/documents` | multipart，**单文件**字段 `file` | `201 {id, filename, chunk_count, created_at}` | 415 类型不支持 / 422 空文件 / 500 入库失败（已回滚） |
| GET | `/api/documents` | — | `[{id, filename, chunk_count, created_at}]` | — |
| POST | `/api/chat` | `{session_id, question, document_ids:[int]}` | `{answer, references:[{document_id, parent_id, filename, snippet}], mode:"rag"\|"normal"}` | 422 参数缺失 / 502 检索或 LLM 失败 |
| GET | `/api/history/{session_id}` | `?limit=50`（默认 50，上限 200） | `[{role, content, references, created_at}]` | — |
| DELETE | `/api/history/{session_id}` | — | `{cleared: n}` | — |

阶段二新增：`POST /api/chat/stream`（见 6.4）。

### 6.2 三个选择的理由

1. **上传单文件端点，不做批量。** 收 `files[]` 就得回答"第 2 个失败时第 1 个算什么"（207？部分成功语义？）。改由前端 `for` 循环逐个 `fetch`，天然获得每个文件独立的进度、失败与重试；代价是 N 次请求，此处可接受。
2. **`document_ids: []` 即普通对话，用 `mode` 回传实际走了哪条链。** 不拆 `/api/chat/normal` 与 `/api/chat/rag`——它们是同一件事的两种参数，拆开会让前端维护两套错误处理。
3. **历史接口把 `chat_history` 的一行展开成两条消息**（`user` + `assistant`），而不是原样返回数据库行。前端拿到的形状与实时发送时一致，`MessageList` 不需要区分"来自历史的"和"来自本次会话的"。

### 6.3 引用片段的数据来源

`references` 来自 `chat_with_documents` 压缩后的父文档列表。为让前端能显示"来源属于哪个文件"，每条 reference 需带 `filename`——由 `document_id` 回查 `documents` 表得到（一次 `IN` 查询，不做 N+1）。同一个结构体既作为 `POST /api/chat` 响应的一部分，也序列化进 `chat_history.used_chunks`，两处形状必须完全一致，否则实时渲染和历史渲染会分叉。

### 6.4 阶段二：SSE 契约（本次只设计，实现排在打通全链路之后）

- 端点 `POST /api/chat/stream`，前端用 `fetch` + `ReadableStream` 读（`EventSource` 只支持 GET，无法带 body）。
- 帧协议（每条 `event:` 一个类型，`data:` 为 JSON）：

| 事件 | 时机 | payload |
|---|---|---|
| `meta` | 立即先发 | `{mode, session_id}` — 让前端在等待期间就能切状态标签 |
| `references` | 检索+压缩完成 | `[{document_id, parent_id, filename, snippet}]` — 引用先于答案出现 |
| `token` | 每个 LLM chunk | `{text}` |
| `done` | 正常结束且历史已写 | `{}` |
| `error` | 中途失败 | `{detail}` — 之后流关闭 |

- 实现要点：`rag_system` 增加 `chat_with_documents_stream()`（`llm.stream()` 版），写历史放在生成完成后；生成中途断流时**不写半截历史**（宁可不写，也不写进 `chat_history` 一条残缺答案污染后续上下文）。
- 收益：首字延迟从"检索 + 压缩 + 生成"降到"检索 + 压缩"。`LLMChainExtractor` 的 N 次 LLM 调用仍在这段等待里，前端靠先发 `meta` + 引用帧填充。

---

## 七、本次顺带修的 5 个问题

| 编号 | 问题 | 修法 | 为什么本次必须修 |
|---|---|---|---|
| 坑 1 | `default=datetime.now()`（4 张表，类定义时求值一次）→ 所有记录时间戳都是进程启动那一刻 | 改为 `default=datetime.now`（传函数引用） | 前端要显示上传时间，不修就是显示假时间，排错时误导。**限定**：只影响此后新写入的行，库里已有的记录仍是假的启动时刻，不会自动修正 |
| 坑 2 | `CHROMA_PERSIST_DIR=../core/chroma_db` 相对 cwd；换启动目录 = 静默换库 | `.env` 写绝对路径 `D:/知识库平台-前后端分离/backend/data/chroma_db`，并 copy 现有 1.2M 数据过去（原 `D:\AI-python\langchain框架\core\chroma_db` 保留不动） | `uvicorn` 一启动 cwd 就变，不修立刻表现为"向量库凭空消失"。实施时实测：旧库真实位置是 `langchain框架/core/chroma_db`（`../core/chroma_db` 只有从 `langchain框架` 下启动才命中），其 metadata `parent_id: deepseek简介.docx_parent_0/_1`、`document_id: '1'` 与 MySQL 逐条对应 |
| 坑 3 | MySQL 与 Chroma 无事务：向量已写、块记录写失败 → 检索命中却回溯不到父块 | `save_chunks` 抛异常时补偿：`vector_store.delete_by_ids(parent_ids + child_ids)` + 删除刚插入的 `documents` 行，再抛 `HTTPException(500)`。**注意 `delete_by_ids` 现在不存在，是本次在 `VectorStore` 新增的方法**（按 ids 从对应集合删） | 上传从函数调用变成 HTTP 接口后，500 必须是可信的"整件事没发生" |
| 坑 6 | 检索到的文档内容直接拼进 HTML（`unsafe_allow_html=True`），含 `<` 即破坏结构 | Vue 用 `{{ }}` 文本插值 + `white-space: pre-wrap`，**全程不出现 `v-html`** | 拆分顺带解决；将来若要 Markdown 必须 `marked` + `DOMPurify` 成对引入 |
| 新增（原 16 条未记） | `rag_system` 两个方法 `except` 后**把错误文本当答案返回**，于是 `"RAG对话出错: ..."` 被写进 `chat_history` 并作为后续对话上下文喂给 LLM | `rag_system` 不再吞异常，改为抛出；`api/chat.py` 捕获后转 `502`，**且不写历史** | 前端会把这串红字当成正常答案显示，且污染上下文——这是数据正确性问题，不是显示问题 |

`used_chunks` 补写：`save_chat_history(..., used_chunks=json.dumps(refs, ensure_ascii=False))`，读取时 `json.loads`。约 10 行，顺带就是把坑 4 的 `str(dict)` 写法用对。

### 7.1 配置来源（坑 2 的具体落法）

现状：`config.py` 里是无参 `load_dotenv()`，python-dotenv 从调用文件所在目录逐级向上找，实际命中的是 `D:\AI-python\.env`——那个文件同时服务同目录下的 `code01`/`code02`/`code03` 等其它脚本，属于**跨项目共用文件**。

本次规定：后端只读 `知识库平台/backend/.env`，定位方式写成"`config.py` 自身位置的上一级"，**与 cwd 无关**（这样从任何目录 `uvicorn` 起来读的都是同一个文件）。内容从共用 `.env` 复制本项目需要的键（`DASHSCOPE_API_KEY`、`DASHSCOPE_BASE_URL`、`LOCAL_MODEL_PATH`、`MYSQL_*`、`CHROMA_PERSIST_DIR`、`CHUNK_SIZE`、`CHUNK_OVERLAP`、`TOP_K`），其中 `CHROMA_PERSIST_DIR` 写成绝对路径指向 `backend/data/chroma_db`。

共用 `D:\AI-python\.env` **不改也不删**，以免影响其它项目；密钥因此在本项目内有一份副本，这是"配置来源确定"换来的代价，`.env.example` 里注明这一约定。

### 7.2 legacy 副本规则

把 `config/`、`core/` **移动**进 `backend/` 会让 `legacy_streamlit/app.py` 的 import 全部断掉——"归档不删、留着对照行为"就落空了；而这个项目**目前不是 git 仓库**，没有提交历史可回退。因此本次采用**复制**：

```
legacy_streamlit/
├── app.py  streamlit页面.py  .streamlit/
├── config/config.py          # 冻结副本
└── core/*.py                 # 冻结副本（含未修的时间戳默认值等原状）
backend/
├── config/  core/            # 唯一演进的真相
```

规则：`legacy_streamlit/` 下的副本**冻结**，只为"手测时对照行为"和"读旧实现"存在，任何修改只进 `backend/`。阶段一验收通过后，由用户决定是否删除该目录。

同时建议在动手改造前先 `git init` 并提交一次改造前状态——本次改造包含大量文件移动与删除，有提交历史才有真正的回退手段。（此动作需用户确认，非本次设计自带。）

**不动的部分**：坑 4（`json_metadata` 存 `repr`）、坑 5（同名文档 dict 键冲突——前端用 `{filename}(#{id})` 已天然规避）、坑 7（N 次 `where` 查询）、坑 8（`parent_id` 长度 100）、**坑 9 的模型名（本次不动，仍硬编码在 `vector_store.py:38` 与 `rag_system.py:17` 两处）**、坑 10（删除文档）均保持原状，在第十二节留清单。本次对配置的唯一实质改动是坑 2 的 `CHROMA_PERSIST_DIR` 路径（见 7.1），不新增其它键。

---

## 八、错误处理与日志

- `main.py` 注册一个全局 `Exception` handler：未知异常记 `logger.exception` 并返回 `500 {"detail": "服务器内部错误"}`（不把堆栈透给前端）。
- 领域异常分层：`DocumentTypeNotSupportedError` → 415、`RetrievalError`/`LLMError` → 502、`ValidationException` → 422。
- `print` → `logging`：现有 `core/` 里 6 处 `print`（数据库连接成功、临时文件路径、最终检索上下文等）。保留信息量，改成模块级 logger；日志级别由 `uvicorn --log-level` 控制，**不新增配置键**（与第七节末尾的约定一致）。
- **单例必须在启动期完成**：`lifespan` 里依次构造 `Config → DatabaseManager → DocumentProcessor → VectorStore → RAGSystem` 挂到 `app.state`。`VectorStore` 会加载本地 0.6B embedding 模型，若每个请求 new 一次服务必然被打死（这正是原来 `@st.cache_resource` 承担的职责）。MySQL 连不上时 `lifespan` 直接抛 → 进程不启动，而不是"能起来但每个请求都 500"。
- 请求处理函数通过 `deps.py` 的 `Depends(get_rag_system)` 等取单例，**测试里用 `app.dependency_overrides` 换成假对象**，因此 pytest 不需要 MySQL、Chroma 和真实 API key。

---

## 九、测试策略

| 层 | 内容 | 依赖 |
|---|---|---|
| 纯函数 | `create_parent_child_chunks`：parent_id 命名 `{fileName}_parent_{i}`、child 的 `parent_id` 能否对上、空文档/单字符文档不越界 | 仅需 langchain splitters |
| 纯逻辑 | `get_parent_documents`：多个子块属于同一父块时 `parent_ids` 去重、metadata 缺 `parent_id` 不抛 | mock `parent_vectorstore.get` |
| schema | `Reference` 序列化/反序列化形状稳定；`used_chunks` 往返一致 | 无 |
| API | `TestClient` + `dependency_overrides`：上传 415/422/500 路径、`document_ids:[]` 走 normal、历史把一行 DB 行展开成两条消息、错误响应体是 `{"detail": ...}` | 无外部服务 |
| 回滚 | monkeypatch 让 `save_chunks` 抛异常 → 断言响应 500、假 `vector_store.delete_by_ids` 被调用且收到刚写入的 id 列表、`documents` 行被删（验坑 3 补偿路径；手测无法稳定触发，必须自动化） | 无外部服务 |
| 契约 | 前端 `api/client.js` 抛的 `Error.message` 等于后端 `detail`（人工对照一次即可，不引入前端测试框架） | — |

**不做**：前端单测框架（本次不引 Vitest）、真实 LLM 的集成测试（不确定且花钱）。端到端验证靠手测清单（第十节）。

---

## 十、运行方式与验收

```bash
# 后端（沿用现有项目外 venv：D:/AI-python/.venv）
cd D:/知识库平台-前后端分离/backend
D:/AI-python/.venv/Scripts/python.exe -m uvicorn main:app --reload --port 8000

# 前端
cd D:/知识库平台-前后端分离/frontend
npm install && npm run dev      # http://localhost:5173
```

手测清单（迁移等价性的判据）：

1. `/api/health` 返回 `ok`，其中 `vector_counts.parent / .child` 与搬家前旧集合的计数完全一致（copy 前先记录一次旧目录的两个 `collection.count()`）→ 这一步才真正证明"Chroma 搬家没搬丢"，`document_count` 只证明 MySQL 侧对得上。
2. 上传一个 txt + 一个 pdf + 一个不支持的 `.exe`：前两个 201、第三个 415；列表出现两条，时间戳是"刚刚"而不是进程启动时刻（验坑 1）。
3. 勾选该 pdf 提问一个答案在文中的问题 → `mode:"rag"`，气泡下方有引用片段；不勾选 → `mode:"normal"`。
4. 刷新页面 → 历史消息与引用片段都还在（验 `used_chunks`）。
5. 坑 3 的回滚**主要靠 pytest 验**（monkeypatch 让 `save_chunks` 抛异常，断言响应 500、`GET /api/documents` 无此条、Chroma 集合计数不变）；手测时如果自然遇到入库失败，再做同样的对照。注意"图片型 PDF 切出空子块"并不会必然触发异常，不能当失败注入手段。
6. 文档里放一段 `<script>alert(1)</script>` 文本，引用它能被检索到 → 页面按纯文本显示、不执行（验坑 6）。

阶段二（SSE）的验收：Network 面板可见 `event: references` 早于第一个 `event: token`；断网中途 → 收到 `error` 帧，且刷新后该轮残缺问答不在历史里。

---

## 十一、迁移执行顺序（供实施计划展开）

> 本次实施计划的范围是**阶段一（第 0～7 步）**。第 8 步（SSE）在阶段一验收清单全绿后另起一份 writing-plans，两份计划各自有自己的 spec 复核点。

0. （建议，需用户确认）`git init` + 提交改造前状态，作为后续大量文件复制/删除的回退保险。
1. 建 `backend/` 骨架，把 `core/`、`config/` **复制**入内并修 import（原目录保留）；补 `requirements.txt`、`backend/.env.example`，并按 7.1 创建 `backend/.env`。
2. 修坑 1、坑 2（含 Chroma 数据 copy 到 `backend/data/chroma_db`），起 `uvicorn` 用 `/api/health` 验证"数据没丢"。
3. 写 `deps.py` + `lifespan` 单例装配，把 `load_document` 签名改成 `(filename, raw_bytes)`。
4. 实现 `documents.py`（含坑 3 回滚）→ pytest。
5. 实现 `chat.py`（含 `rag_system` 不再吞异常、`used_chunks` 写入）+ `history.py` → pytest。
6. `npm create vite` 起前端，接 `api/client.js`，逐组件迁移 UI 与 CSS。
7. 全链路手测清单 1-6 通过 → 把根目录的 `app.py`、`streamlit页面.py`、`.streamlit/` 以及**原始的** `config/`、`core/` 一起挪进 `legacy_streamlit/`，让它自包含（`streamlit run` 从该目录内启动即可，`sys.path[0]` 就是它自己），副本冻结。第 1～6 步期间这些原文件一直留在根目录不动，所以任何时刻最多只有"原始 + backend 副本"两份，不会出现三份真相。是否最终删除 `legacy_streamlit/` 由用户另行决定。
8. 阶段二：SSE 端点 + 前端流式读取，并**删除 `utils/typewriter.js`**（不能两套逐字逻辑并存：前端自己逐字、后端又推 token，会让"显示的字数"和"真实的字数"脱节）。

**依赖安装注意**：Python 环境是跨项目共用的 `D:/AI-python/.venv`，装 FastAPI 相关包时只新增（`fastapi`、`uvicorn`、`python-multipart`、`pytest`、`httpx`），**不升级**已有的 langchain / chromadb / sqlalchemy 等，以免破坏同 venv 下的其它脚本；`requirements.txt` 用 `>=` 下界而非钉死上界，并在文件头注明这一约束。

**回退**：阶段一期间原 `app.py` 与 `config/`、`core/` 始终留在原位且未被修改（因为走的是复制），`streamlit run app.py` 全程可用，只需 `CHROMA_PERSIST_DIR` 仍指向旧目录即可对照；第 8 步失败可退回第 7 步末状态，普通接口路径完整保留。

---

## 十二、遗留清单（本次明确不做）

坑 4、7、8、10，以及：文档删除/重新索引、多会话、混合检索、把 `LLMChainExtractor` 换成 reranker、入库任务化（后台 worker + 进度）、`documents.content` 与子块冗余存储、依赖版本混代（`langchain-classic` 的 `LLMChainExtractor` 是升级时第一个会消失的）。
