# 块级文档选择面板 设计文档（2026-10-04）

## 一、目标与范围

用户诉求（原话摘要）：把知识库文档区改成"只有一个『选择文档块』按钮 + 已选块列表"，点按钮弹窗，弹窗上方是搜索框（按名字和后缀搜已分割好的文档块），搜索框下方是分类（全部 / pdf / docx / txt），按选择显示文档块；只有被选中的块才显示在面板上；块卡片右上角有小红叉，点它取消选择并从面板移除。

现状是**文档粒度**：`DocumentPanel` 列出全部文档，`DocCard` 上的复选框勾出 `document_ids`，问答时把整篇文档交给检索器做元数据过滤。本次把粒度下移到**父块**，并把"列全部 + 勾选"换成"只看已选 + 弹窗挑选"。

范围内：
- 新只读端点 `GET /api/documents/chunks`（搜索 + 后缀分类 + 批量点查三合一）。
- 问答契约从 `document_ids` 换成 `parent_ids`；检索器按 `parent_id` 过滤子块向量集合。
- 前端新 `useChunkSelection` composable + `ChunkPickerModal` + `ChunkCard`；`DocumentPanel` 的知识库区重写。
- 选择持久化到 localStorage（只存 id）。

明确不做（YAGNI，均为分节确认时被否决的候选）：
- 子块粒度选择、块内容编辑、批量选择/批量删除。
- 上传后自动选中新文档的块（只回候选池）。
- 输入防抖搜索（改为回车/按钮提交）。
- 卡片复选框（只有红叉，点击卡片本身即切换）。
- 给 `chat_history` 加 `parent_ids` 列（反查得到 document_ids 即够用）。

## 二、承重事实（决定了方案形状，动手前先认这几条）

1. **检索读 Chroma，不读 MySQL。** `VectorStore.create_retriever(document_ids)`（core/vector_store.py:86）在 **child** 集合上加 `search_kwargs["filter"] = {"document_id": {"$in": [...]}}`，命中后由 `get_parent_documents` 按 metadata 里的 `parent_id` 回溯父块。
2. **子块向量已经带 `parent_id` 元数据**（core/document_processor.py:81 给每个 child_doc 写入），所以过滤条件换成 `{"parent_id": {"$in": [...]}}` **不需要重新灌库、不需要数据迁移**——现存 11 个父块 / 22 个子块的向量直接可用。
3. `parent_chunks.parent_id` 是 `String(100)` 且 **UNIQUE**（core/database.py:36），所以单个 `parent_id` 字符串就能唯一定位一个块，不需要 `(document_id, parent_id)` 那一对钥匙（那是删块端点为同名文档留的防御，见 database.py:210 的注释）。
4. `documents.is_active` 是软隐藏位，`get_all_documents()` 与 `count_documents()` 都已消费它；删块把某文档 `chunk_count` 打到 0 时会隐存它（delete_parent_chunk）。新端点必须只看活跃文档，否则会把已隐存文档的残块摆进弹窗。
5. `chat_history.document_ids` 是 `String(500)` 逗号拼接列，`mode_of()` 只按真假派生 rag/normal（schemas/chat.py:25），传 `list[str]` 与传 `list[int]` 行为一致，所以契约换形状不需要动它。
6. 50 项 × 9 位数字 + 49 个逗号 = 499 ≤ 500 是 M-e 定下的推导。换成 `parent_ids` 后，落库的仍是反查出来的 document_id（≤ 选中块数 ≤ 50 个），这个上界自动继承，不需要重新论证。
7. **路由顺序**：documents 路由当前只有 `POST ""`、`GET ""`、`DELETE "/{document_id}/chunks/{parent_id}"`。新增的 `GET "/chunks"` 与 `GET ""` 不冲突，但**今后若加 `GET /{document_id}`，必须把 `/chunks` 注册在它之前**，否则 "chunks" 会被当 path 参数吃掉。
8. 引用条上的 `deleted` 标记仍是客户端本地状态（上一功能留下的已知缺口，本次不扩大范围去修）。

## 三、后端契约

### 3.1 新端点 `GET /api/documents/chunks`

```
GET /api/documents/chunks?query=&suffix=&parent_ids=&limit=50
→ 200 list[ChunkOut]
```

| 参数 | 类型与校验 | 语义 |
| --- | --- | --- |
| `query` | `str = ""`，`max_length=100` | 同时匹配文件名和块内文本 |
| `suffix` | `Literal["", "pdf", "docx", "txt"] = ""` | 空串=全部；非空按文件名后缀等值过滤 |
| `parent_ids` | `list[str] = Query(default=[])`，元素 `min_length=1, max_length=100`，整表 `max_length=50`；URL 里写成重复键 `?parent_ids=a&parent_ids=b` | 批量点查模式，**给了它就优先**，`query`/`suffix`/`limit` 全部让位。用重复键而不是逗号拼接：`parent_id` 由清洗后的文件名拼出，文件名里的逗号是合法字符，逗号拼接会把一个真 id 静默拆成两个假 id，前端 hydrate 会把用户的选中抹掉 |
| `limit` | `int = Query(50, ge=1, le=200)` | 候选池单次上界，防把 3 万块灌进弹窗 |

响应 `ChunkOut`（schemas/documents.py 新增）：

| 字段 | 来源 |
| --- | --- |
| `parent_id` | `parent_chunks.parent_id` |
| `document_id` | `parent_chunks.document_id` |
| `filename` | JOIN `documents.filename` |
| `suffix` | 文件名最后一个点之后的部分，小写；无点则空串 |
| `snippet` | `parent_chunks.content` 压掉换行后按 `SNIPPET_LIMIT=80` 截断加 `...`，与 `_build_references` 同一口径（schemas/common.py:3） |
| `child_count` | 该父块名下子块数（一次 `COUNT ... GROUP BY`，不在循环里查） |

搜索实现要点：
- 条件为 `Document.filename LIKE :p OR ParentChunk.content LIKE :p`，且 **JOIN 只连 `Document.is_active == True`**。
- **必须转义 `%`、`_`、`\`**（LIKE 的元字符）。参数绑定挡住的是 SQL 注入，挡不住通配符语义——用户在搜索框里输入一个 `%` 不该拿到全部块。
- `parent_ids` 批量模式：入参已是 list，后端只做**去空串、按入参顺序去重**，走 `WHERE parent_id IN (...)`，不存在的 id 静默少返回（前端 hydrate 靠"少返回"来剪死 id）。超过 50 项由 `max_length=50` 判 422——前端 hydrate 不可能造出 51 项（读回时就截到 50），所以这里不需要"截断"这种第二套口径。

排序：`document_id ASC, parent_id ASC`。不用 `created_at`——同批上传的块时间戳相同，排序会漂。

错误处理：读端点不加 try。这与既有 `list_documents` 保持一致——SQLAlchemy 异常由兜底 handler 收成 500 `服务器内部错误`；写路径才需要策展文案（M2-7 的理由是流式端点要能给出"保存失败"的可行动提示，读路径失败没有别的动作可给）。校验失败走 FastAPI 的 422 数组 detail，前端 `detailFromText` 已会冠上"请求参数不合法："（M-j），后端不新增文案。

### 3.2 `ChatRequest` 换 `parent_ids`

```python
class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1)
    # 块级允许池：元素上界对齐 ParentChunk.parent_id 的 String(100)，与删块端点同源
    parent_ids: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        default_factory=list, max_length=50)
```

- `document_ids` 字段**直接删除**（不留兼容 shim：本项目唯一客户端就是自家前端，同仓同部署，加了就是永远没人删的死字段）。
- 老客户端若仍发 `document_ids`：Pydantic 默认忽略未知字段 → `parent_ids` 为空 → 变成普通对话而非 422。这是有意的取舍，写进测试钉住，不静默。
- `/api/chat` 与 `/api/chat/stream` 共用这一契约，`mode_of(payload.parent_ids)` 原样可用。

### 3.3 检索与落库

- `create_retriever(parent_ids=None)`：`search_kwargs["filter"] = {"parent_id": {"$in": list(parent_ids)}}`。参数名与调用点同步改，`None`/空列表仍然不加过滤条件（纯对话链根本不调它）。
- `RAGSystem.chat_with_documents(question, parent_ids, session_id)` 与流式版同理。落库前先反查：新增 `DatabaseManager.document_ids_for_parents(parent_ids) -> list[int]`——单次 `SELECT DISTINCT document_id FROM parent_chunks WHERE parent_id IN (...)`，**按入参顺序去重**，只返回库里真实存在的行；`rag_system` 用 `",".join(map(str, doc_ids))` 写 `chat_history.document_ids`。
  - 为什么历史列继续存 document_ids：`mode_of` 派生与 `_build_references` 的 filename 补全都吃它，加一列 `parent_ids` 是第二份真相且没人读。
- 反查结果为空（选中的块在这期间全被删了）→ `document_ids` 落成空串，但 mode 仍是 `rag`（过滤条件照旧带上那批死 id，召回必然 0 条）→ 走既有的 `EMPTY_RETRIEVAL_ANSWER` 分支，并补一条 `logger.warning("选中的文档块已全部失效: %s", parent_ids)`。不新增错误码：这一轮的答案是真话，不是故障。

### 3.4 后端验收判据

- `GET /api/documents/chunks`：空库返回 `[]`；`query` 命中文件名 / 命中块内文本 / 两者都不命中；`query="%"` 因转义而不返回全部；`suffix=pdf|docx|txt` 各自只留对应后缀、非法后缀 422；`limit=0` 与 `limit=201` 各 422；`parent_ids` 批量模式优先于 `query`、未知 id 静默少返回、51 项 422、**含逗号的 parent_id 原样往返**（这是重复键写法的回归锚）；`is_active=False` 的文档不出现在任何模式下；`snippet` 在第 80 字符截断并带 `...`；`child_count` 正确。
- `ChatRequest`：51 项 422、空串元素 422、101 字符元素 422、`document_ids` 被忽略（→ normal）。
- `create_retriever(["a.txt_parent_0"])` 的 `search_kwargs["filter"]` 逐字等于 `{"parent_id": {"$in": ["a.txt_parent_0"]}}`。
- `document_ids_for_parents` 的顺序、去重、少返回三条各有断言。
- live 组（`-m live`）补一条真库 smoke：默认基线下 `GET /api/documents/chunks` 返回非空、每条含 `parent_id`/`filename`/`child_count≥1`。

## 四、前端设计

### 4.1 数据流

```
localStorage("selected_parent_ids")
        │ hydrate()：只拿 id 去问后端
        ▼
GET /api/documents/chunks?parent_ids=a,b,c   ← 后端没返回的 id 就地剪掉（块已删/已隐存）
        ▼
useChunkSelection.selectedChunks ──► DocumentPanel(已选块 + 红叉) / ChunkPickerModal(候选池)
        │
        └─► send({ session_id, question, parent_ids })  ──► SSE
```

新 `frontend/src/composables/useChunkSelection.js`：

| 成员 | 行为 |
| --- | --- |
| `selectedChunks: ref([])` | 存活 `ChunkOut` 形状对象数组，顺序=点选顺序 |
| `pickerOpen: ref(false)` | 弹窗开关 |
| `selectionError: ref('')` | 上限拒绝 / hydrate 失败的文案出口 |
| `hydrate()` | 读 localStorage → 有 id 则 `listChunks({ parentIds })` → **用返回结果重建**（后端没给的就是死了，剪掉并回写）；空值直接清空本地；请求失败时只落 `selectionError`，保留已有集合，不让面板炸掉 |
| `toggle(chunk)` | 在集合里就移除，否则追加；追加前查 50 上界，超了给中文文案且**不发请求** |
| `remove(parentId)` | 红叉入口 |
| `selectedParentIds` / `selectedCount` | computed，供发送载荷与 StatusBar |
| `clearSelection()` | 集合与 localStorage 一起清 |

持久化只存 id 数组（`JSON.stringify(parentIds)`），绝不存快照对象——快照会在块被删/改名后说谎。这与 `useSession.js` 的"坏值构造不可达"同族：读回 localStorage 时逐条要求非空字符串、去重、截到 50，任何一条不合格就整体丢弃换新，不给脏值进请求 URL 的机会。

`App.vue` 接线：`onMounted` 里 `await refresh()` 之后 `await hydrate()`（refresh 拉文档数，hydrate 拉选中块，两者互不依赖但顺序固定以便错误横幅只留最后一条）。`handleSend` 的载荷键改 `parent_ids`。`useChat.send` 的解构与出参键同步改名（useChat.js:58, 80）。

### 4.2 组件

`DocumentPanel.vue` 知识库区重写：
- `🧩 已选文档块` 标题 + 右侧 `➕ 选择文档块` 按钮（emit `open-picker`）。
- 已选块用 `ChunkCard` 渲染；空态文案"还没有选择文档块，点上方按钮挑几块。"，hint 改"一个块都不选就是普通对话。"
- 保留 `FileUploader`、`📊 文档数 N`、`🗑️ 清空对话`。
- **删掉**全部文档列表与 `DocCard.vue`，连带 `useDocuments` 里的 `selectedIds` / `toggleSelect`（没有消费方就删干净，不留兼容出口）。`documents` / `docCount` / `refresh` 保留（文档数与"有没有文档"仍在用）。

`ChunkPickerModal.vue`（新）：
- 遮罩 `position: fixed; inset: 0; z-index: 4`——必须高于 ≤768 侧栏浮层的 `z-index: 3`（L-3 的直接推论），否则窄屏下弹窗被面板盖住、按钮点不到，这是本项目踩过的同一个坑。
- 顶部搜索框 + `搜索` 按钮 + 清空；**Enter 或点按钮才提交，无输入防抖**。
- 搜索框下方四枚分类按钮：全部 / pdf / docx / txt（当前分类高亮）。切换分类用**当前关键词**立即重查。
- 结果列表：`max-height: 60vh; overflow-y: auto`（有界滚动，L-2 同族要求），每条 `ChunkCard`，已选中的显示"已选"角标；点卡片即 toggle，因此选中/取消在同一处都只需点一次。
- `selectionError` 顶在弹窗内（不是全局横幅：错在弹窗里就该在弹窗里说）。
- 关闭：`✕` 按钮 / `Esc` / 点遮罩空白。弹窗不缓存结果，每次打开都重新查（面板要的是真值）。

`ChunkCard.vue`（新）：
- 第一行 `docLabel(chunk)` = `文件名(#document_id)`——复用 useDocuments.js 的 `docLabel`（它已同时吃 `id` 与 `document_id` 两种形状，M-F2 收口的唯一出处，不再造第二个格式实现）。`docLabel` **继续留在 useDocuments.js 原位不搬家**：它是 M-F2 钉下的唯一出处、`ReferenceList` 也在吃，为了"面板不再列文档"去搬文件纯属 churn，只会让下次找唯一出处的人扑空。
- 第二行 `snippet`，第三行 `块 {parent_id} · {child_count} 个子块`。
- 右上角红 `✕`：`aria-label="取消选择"`、`title="取消选择这个文档块"`。**必须与引用条上的 🗑（删除文档块）文案不同**——一个是本地取消选择、不发请求，一个不可逆删除向量库数据，混了会让人以为点了就丢数据。
- `removable` prop 控制红叉是否出现（面板里显示，弹窗里不显示，弹窗用角标）。

`StatusBar.vue`：`（N 个文档）` → `（N 个文档块）`，来源换成 `selectedCount`（useChunkSelection）。

样式只进 `frontend/src/styles/layout.css`，颜色一律用 `variables.css` 里的 token——G-4 口径：`variables.css` 之外颜色字面量必须 0 命中，验收时跑那条判据命令。

### 4.3 前端验收判据（vitest）

- `useChunkSelection.test.js`：hydrate 剪掉后端未返回的 id 并回写 localStorage；localStorage 只存 id 数组不存对象；脏值（非字符串/空串/超 50）读回时被丢弃；第 51 次 toggle 被拒且 `selectionError` 有中文文案；`remove` 后持久化同步。
- `chunk-picker.test.js`：回车/按钮调 `listChunks` 且带上 `query` 与 `suffix`；切换分类用当前关键词重查；点卡片 emit toggle；`✕` 与 Esc 与遮罩点击都关弹窗；红叉 emit remove 且**不 emit** toggle（同一卡片上两个动作不能双触发）。
- 既有测试的连带改动：`useChat.test.js` 载荷键换 `parent_ids`；`reference-list.test.js` 的三跳链路测试不动（它吃的是删块链，与本次无关但必须继续全绿）。
- `documents-api.test.js` 增 `listChunks` 的 URL 拼接断言：与 3.1 一致用**重复键**（`?parent_ids=a&parent_ids=b`），并钉住中文关键词与含逗号的 `parent_id` 各自被编码成什么——逗号在 query 里是合法字符、不需要转义，正因为如此它才会把逗号拼接的方案静默拆坏，这条断言是选中项"刷新后蒸发"的唯一防线。

## 五、门禁与联调

**门禁**（每步改完都跑，报实数）：
- 后端 `python -m pytest -q`（当前基线 146 passed / 0 skipped / 1 deselected，改完允许变多，不允许 failed）、`-m migration` 仍 1 passed。
- 前端 `npm test`（当前基线 45 passed）、`npm run build` exit 0。
- G-4 颜色字面量判据命令 0 命中。

**Live 联调**（改完后端必须重启我自起的 uvicorn，否则新代码不上线；服务实例只用自己起的那一个，绝不第二个）：
1. 视口显式 1280×900（宽屏）+ 375×800（窄屏）各跑一遍，报告回读 `innerWidth` 原始值。
2. 弹窗：搜 `deepseek` 命中 → 切 `docx` 只剩 docx → 切 `全部` 回来。
3. 选 2 块 → 面板只显示这 2 块 → StatusBar 显示"（2 个文档块）"。
4. 红叉取消 1 块 → 面板剩 1 块 → **刷新页面仍是 1 块**（localStorage 真生效）。
5. 就着选中的那块问一个只在那块里能答的问题 → RAG 出答案且引用带 `parent_id`；改问只在**未选中**块里的内容 → 拿到 `EMPTY_RETRIEVAL_ANSWER`（这一条是"允许池真收窄了召回"的唯一活体证据，光看 UI 不算）。
6. 取消全部选择 → 普通对话（meta 帧 mode=normal、无 references 帧）。
7. 收尾：把 localStorage 恢复原值，不删任何业务数据；结束后回到基线 documents 9 / parent_chunks 11 / child_chunks 22，`/api/health` 对上。

## 六、已知遗留（写明不修）

- 引用条的 `deleted` 仍是本地状态，刷新后复活成可点按钮、点了 404（上一功能留下的缺口，本次不扩范围）。
- 已选块在别处被删后，同一会话内要到下次 hydrate（刷新）才剪；本轮发送撞上时表现为空召回文案，不崩。
- 搜索无防抖：每次回车一次请求。当前数据量（11 块）下不是问题，真到几千块再谈。
- 弹窗一次最多 50 条候选、无分页；块数上去后要加分页或无限滚动。
