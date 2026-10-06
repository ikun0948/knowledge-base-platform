# SDD ledger — plan: docs/superpowers/plans/2026-10-04-chunk-selection-panel.md

执行方式：控制器内联执行（未派发子代理），用户已放行 spec 审阅门与执行方式选择。
分支：master（本机无远端）。起点 be068d9（计划提交）。

## 门禁实数链

- 基线（Task 1 之前实测）：backend `python -m pytest -q` = 146 passed / 1 deselected / 1 warning（in 158s）；
  frontend `npm test` = 45 passed / 5 files；`npm run build` 绿。
- Task 1 完成（commit 70a1d98）：
  - `tests/test_chunk_search.py` = 15 passed（RED 先行为 12 failed / 4 passed；live 子组 RED 4 failed）。
  - `tests/test_live_database.py` = 11 passed（原 7 + 新 4）。
  - 默认门 `python -m pytest -q` = **163 passed, 2 skipped, 1 deselected, 1 warning in 27s**，零 failed。
    算式：146 + 15（test_chunk_search）+ 4（live db 新）= 165 = 163 passed + 2 skipped。
  - **2 skipped 不是本 Task 造成的**：`tests/test_live_stream.py:34/:64` 因本机 :8000 无监听
    （先前自起的 uvicorn 已死，`netstat` 只剩 TIME_WAIT）而 skip。Task 5 重启服务后应回到全绿。

## 执行期发现的计划缺陷（已回写计划文）

1. Step 9 代码把 `stmt.limit()` 放在分支里、`group_by()` 放在其后 —— SQLAlchemy 旧版 Query
   在已带 LIMIT 的语句上调 `group_by()` 直接抛 `InvalidRequestError`，live 组三条实测红。
   改为 filter → group_by/order_by → 仅非批量模式末尾追加 limit。
2. Step 11 路由顺序判据遍历 `app.routes` 取 `r.path` —— 本 FastAPI 版本把 `include_router`
   记成没有 `.path` 的 `_IncludedRouter`，实测 `AttributeError`。改读 `documents_router.routes`，
   并断言 `/chunks` 在任何含 `{` 的动态路由之前（比原"钉住 GET /{document_id} 不存在"更强）。
3. Step 8/14/15 的预期条数（3 条 / 13 passed / ≥146）与实数不符，已按实测口径改写。

## Task 2

- Task 2: commit 916e20d（`feat(backend)!`，破坏性契约改名）。
  - RED：`tests/test_api_chat.py` 16 failed / 13 passed；`tests/test_rag_system.py` 7 failed / 13 passed。
  - GREEN：`test_api_chat + test_rag_system + test_vector_store + test_schemas + test_live_stream`
    = 74 passed / 2 skipped；`test_live_database.py` = 12 passed。
  - 默认门 = **170 passed, 2 skipped, 1 deselected in 27s**，零 failed；migration 门 = **1 passed**
    （基线 documents 9 / parent_chunks 11 / child_chunks 22 未被探针污染，finally 清理生效）。
  - 条数算式：Task 1 末 165（含 2 skip）+ 7 = 172 = 170 passed + 2 skipped。
    净增：test_api_chat +1（28→29，非整数判据换成三条上界/兼容判据、M-e 那条被 overlong 吸收）、
    test_rag_system +3、test_vector_store +2、test_live_database +1。
  - 2 skipped 仍是 `test_live_stream.py:34/:64`（本机 :8000 无监听），与 Task 1 末同源，非本 Task 引入。

4. Step 9 的反查 live 判据写的是 `make_probe_doc(...)` —— Task 1 早已把它改成 `probe(db, filename, blocks)`
   （blocks 为 `{parent_id: 子块数}`）。执行时按定稿 helper 改写，并补 `new_tag()` 隔离：parent_id 在全库
   是唯一键，不带 tag 的重跑一旦残留就会撞锁并让顺序断言多吃一行。
5. Step 4 的 `RunnableGenerator(lambda _: [SimpleNamespace(...)])` 直接 TypeError——它只收生成器函数。
   改用本文件已有的 `stream_llm(["一", "二"])`，判据不变。
6. 计划漏了既有用例的整数池：`chat_with_documents("q", [7], "s1")` 一类共 14 处，第二参数换成
   parent_ids 后必须同时给 StubDb 补 `parents={"p0": 7}`，否则反查为空、`document_ids` 落成空串，
   那批断言 `"7"` 的用例全红得像"字段没接上"。执行时按 `parent()` 桩的默认 `parent_id="p0"` 统一改写。

## 中间态（Task 1/2 期间的记录，已被文末 Task 3 后的同名小节覆盖）

前端 `App.vue:71` 与 `useChat.js:58,80` 仍发 `document_ids`，后端已按"未知字段静默丢弃"处理 →
现在发上去等于空池，任何问答都走 normal 链。这是契约迁移的故意半程，Task 3 换 payload 键、
Task 4 换选择来源，两半合起来才可用；此状态不推送、不部署。

## Task 3

- Task 3: commit 99d67b4（`feat(frontend)`）+ 167ca98（`docs(plan)` 执行期回写）。
  - RED 三次到位：`listChunks is not a function` 4 failed；载荷键那条 1 failed | 49 passed
    （received 只有 `{session_id, question}`：`toEqual` 忽略 undefined 的旧键）；
    `useChunkSelection` 那条是**文件级红**——`Test Files 1 failed | 5 passed (6)`、`Tests 50 passed (50)`。
  - GREEN：前端门禁 = **60 passed (60)，6 个文件**，零 failed；`npm run build` exit 0
    （入口 js 78.56 kB，`useChunkSelection.js` 暂无组件引用，不进打包图，属预期）。
  - 条数算式：基线 45 + listChunks 4 + useChat 载荷键 1 + useChunkSelection 10 = **60**。
  - `App.vue` 一处未动（仍传 `document_ids`），本 Task 故意不碰：改它要先有块级选择来源，归 Task 4。

7. Step 3 的追加用例引用 `setStream(chat, [])` —— 本仓 `tests/useChat.test.js` 的流桩叫
   `scriptEvents`，且每条用例要自己 `const chat = useChat()`。照抄会 NameError 式红一轮。
8. Step 5 的预期写"FAIL — 找不到 useChunkSelection.js"，实测形态是**文件加载失败、一条都不收集**，
   汇总行仍显示 `Tests 50 passed (50)`：盯 `Test Files` 那行才看得见红。

## 中间态（已结清，保留作轨迹）

Task 3 末 `useChat.js` 的 payload 键已是 `parent_ids`，而 `App.vue` 仍传 `document_ids: selectedIds.value`
（整数文档 id 池）→ 后端按未知字段丢弃，等同空池走 normal 链。这是契约迁移的故意半程。
**闭合于 aba2887（Task 4）**：App.vue 的选择来源已换成 `useChunkSelection`，`handleSend` 发
`parent_ids: selectedParentIds.value`，面板/弹窗/红叉同批落地。全程未推送、未部署。

## Task 4

- Task 4: commit aba2887（`feat(frontend)`，DocCard 退役）+ 96321f1（`docs(plan)` 执行期回写）。
  - RED 两处形态：`ChunkCard.vue` 缺失是**文件级红**（`Test Files 1 failed | 6 passed (7)`、
    `Tests 60 passed (60)`，条数纹丝不动）；弹窗四条 DOM 判据首跑全红，但红得没道理——
    ① `await Promise.resolve()` 盖不住"mock promise + Vue 调度器"两级异步渲染，DOM 还是空的
    （统一换 `flushPromises()`）；② Esc 那条的后半是**假判据**：`unmount()` 把 VTU 的事件记录
    一起清了，`emitted()` 返回 undefined 让断言"看起来通过"。改成宿主组件（`h()` + `ref` +
    `nextTick`）用外部 `closed` 数组观察，卸载后再派一次 Escape 才真能证伪。
  - GREEN：前端门禁 = **75 passed (75)，7 个文件**，零 failed；`npm run build` exit 0。
  - 条数算式：Task 3 末 60 + ChunkCard 5 + ChunkPickerModal 10 = **75**。
  - 计划缺陷 9（已回写）：Step 2 把红叉写在卡片本体**之前** → `.chunk-card` 是横向 flex，
    实际渲染在**左上角**。DOM 顺序决定视觉位置，jsdom 不排版，五条单测全绿也照样看不见；
    本体在前、红叉在后才是右上角。
  - 计划缺陷 10（已回写）：Task 4 除了计划列的改动点，还有三处连带——DocumentPanel 的
    `documents` prop 失去消费者要摘、`.doc-name`/`.doc-meta` 两条只服务 DocCard 的样式随它退役、
    `--shadow-card-hover` 成死 token；另补"执行期第五处"：`handleRemoveChunk` 删块成功后要
    `remove(parentId)`，否则面板里留一张点不动的死卡。

## Task 5

- 五条门实数（清场后复跑，代码自 aba2887 未再改动）：
  - backend 默认门 `python -m pytest -q` = **172 passed, 1 deselected, 0 skipped**，零 failed。
    与 Task 2 末的 `170 passed / 2 skipped` 同总量 172：那两条 `test_live_stream` 的 skip
    是 :8000 无监听，本轮起服务后自动转绿，**不是测试数变化**。
  - backend live 门 `-m live` = **14 passed**；migration 门 `-m migration` = **1 passed**
    （跑前跑后各查一次，基线 documents 9 / parent_chunks 11 / child_chunks 22 未被改动）。
  - frontend `npm test` = **75 passed (75) / 7 files**；`npm run build` exit 0
    （js 85.07 kB / gzip 32.95 kB——比 Task 3 的 78.56 kB 大，因为块级选择这条链此时才被组件引用、进打包图；css 9.99 kB）。
  - G-4 颜色收口：`grep -rn --include=*.css --include=*.vue -E "#hex|rgba?(|hsla?(" src/` 去掉
    `styles/variables.css` 自身 = **0 命中**。
  - 服务：只自起一个 uvicorn（PID 20712，:8000），vite（PID 17828，:5173）沿用；收尾只杀这两个 PID。
- 端点直连证据（`query=%` 的第一级）：全池 **11** 行；`%` → **1**（`deepseek简介.docx_parent_0`
  正文里真有一个字面 `%`）；`%%` → **0**；`_` → **0**；`suffix=exe` → 422。未转义时 `%`/`_`
  都会把 11 行全捞回来，所以"1 与 0"就是转义生效的证据（计划旧文钉 `[]`，已改判为条数对照）。
- 浏览器十判据（puppeteer-core + 本机 Edge headless，`--no-save`）：三阶段共 **21 条判据全 PASS**。
  - `ui` 12/12，`innerWidth` 回读 **1280**（900 高）：J1 面板两节标题 + `docCards:0`/`checkboxes:0`；
    J2 遮罩 `z-index:4` + `elementFromPoint` 命中的就是搜索框本身 + 初始 11 行；
    J3a `deepseek` 2 行且都含该词；J3b 切 DOCX 2 行全 `.docx`；J3c 切回「全部」`全部#0` 仍 2 行
    （关键词仍是 deepseek，分类只收窄）；J3d `%` → 1 / `_` → 0 vs 全量 11（第二级证据，与 curl 一致）；
    J3e `知识库平台` 命中 `rag.txt_parent_0`+`rag2.txt_parent_0`（块内正文命中）；J3f `第三份` 命中 `third.txt_parent_0`；
    J4 面板 2 卡 + StatusBar `🔍 知识库模式（2 个文档块）` + `stored` 就是 `[rag, third]` 那个顺序；
    J9 红叉 `title=取消选择这个文档块`/`aria=取消选择`/文本 `✕`，整块侧栏文本里**没有**"删除"二字；
    J5 点红叉剩 1 → **reload 后仍是 1**，`stored=["rag.txt_parent_0"]`、badge 1、状态栏（1 个文档块）；
    J10 控制台零错误。
  - `chat` 4/4（同 1280 宽）：J6 `rag.txt_parent_0` 在池 → mode `📚 知识库检索`、引用 `📎 rag.txt(#71)`、
    答案讲"子块召回后回溯父块"（父块回溯证据）；J7 改问 third.txt 独有内容 → **references 帧为 `[]`**、
    答案不含"串行/上传队列"；J8 取消全部选择 → StatusBar `💬 普通对话模式`、`stored=[]`、
    mode `💬 自由对话`、零引用；J10 零错误。
  - `narrow` 5/5，`innerWidth` 回读 **375**（800 高）：侧栏默认 `display:none`（rect 0×0）；展开后
    `position:fixed`/`z:3`，弹窗 `z:4` 且 `elementFromPoint` 命中 `picker-input`，modal 宽 345 不越视口；
    红叉 rect `x=319 / cardRight=348 / cardTop=282 / y=289`（右上角）；关弹窗后点 ✕ + reload 仍是 1 块。
  - **J7 的机制修正（值得记住）**：实测帧是 `meta mode=rag` → `references []` → 模型自己的 token，
    不是 `EMPTY_RETRIEVAL_ANSWER`。池内只剩 rag 时带 `$in` 过滤的相似度检索**一定**返回最近的那条子块，
    `parent_docs` 非空 ⇒ 不进空召回分支；压缩器再按相关度阈值把它滤成 `compressed_docs=[]`
    ⇒ 引用空、上下文空串。这是**既有行为**（`VectorStore.compressor`），本功能没碰它。
  - 探针三处接线坑全部回写计划文（triple-click 选不中致关键词累加、窄屏必须先 Esc 关弹窗才点得到面板 ✕、
    分类标签按文字而非索引定位）；判据本身一条没改。
- 本轮写入的 `chat_history`：chat 阶段自起 session（前缀 `ccca57e5`）3 轮、curl 诊断 session
  `probe-j7-diagnose-0001` 1 轮。都是探针自己的 UUID，属正常业务写入，不删。
- 清理：`probe-chunk-panel.mjs` 已 `rm`；`npm prune` 后 `npm ls --depth=0 | grep -c extraneous` = **0**、
  `node_modules` 里 grep puppeteer 无残留；`package.json` / `package-lock.json` 全程 `git status` 无 diff。

=== 块级文档选择面板（2026-10-04）===

- 交付：后端 `GET /api/documents/chunks`（70a1d98）+ 问答契约 `document_ids → parent_ids`（916e20d）
  + 前端 `listChunks`/`useChunkSelection`（99d67b4）+ 面板与候选池弹窗（aba2887）。
- 五条门：backend 默认 172 passed/1 deselected/0 skipped、live 14、migration 1、
  frontend 75 passed/7 files、build exit 0 + G-4 grep 0。
- 十判据（拆成 21 条实测判据）全 PASS，宽窄两档 `innerWidth` 1280 / 375 原始值已回读。
- `query=%` 两级证据：curl（11 全量 / `%` 1 / `%%` 0 / `_` 0）与 UI（同一组数）互证 LIKE 转义。
- 已知遗留四条（spec 六节，不进实现）：① 引用条上的 `deleted` 态不持久化，刷新后死块引用消失；
  ② 已删块要下一次 hydrate 才被剪掉（唯一例外是本轮补的"本地删块即时摘选"）；
  ③ 搜索无防抖（体量十几个父块，纯浪费；真要加得先有分页）；④ 弹窗结果不分页，`limit=50` 一次拿满。
- 顺手记一条环境事实：同一时刻本机只能跑一份 uvicorn（embedding 模型按进程加载，os error 1455），
  所以 Task 5 全程共用 PID 20712 那一个实例。

## 2026-10-06 追加：块级面板四项改造（bounded 路径，不出 spec/计划文）

- 需求四条与定稿口径（用户逐条确认）：① 弹窗结果一排两张、要美观；② 弹窗尺寸固定、
  切到空分类不许缩，高度按当前值缩 1/5；③ 卡片只显示名字，正文改鼠标悬浮显示；
  ④ 删除文档块从消息引用条搬进弹窗，每行一个删除按钮。
  **第 ② 条中途改过一次**：我先按"缩小 5 分之 1"落笔成"放大 2 倍"（164vh），被纠正后
  按"当前值 → 目标值 + 算式"回读（82vh → 66vh，宽 min(92vw,560px) 不动）才定稿。
  第 ④ 条用户明确选了"移除消息引用条上的删除入口，删除只留弹窗"。
- RED（11 条先跑红）：`11 failed / 73 passed (84)`。红全在预期位置——卡片新口径 9 条里的新判据、
  弹窗删除闭环 5 条（`Cannot call trigger on an empty DOMWrapper` 就是"按钮还不存在"）、
  引用条退役 2 条（`expected [...] to have a length of +0 but got 1` 就是旧按钮还挂着）。
- GREEN 实现要点：
  - `ChunkCard`：卡面 `文件名 #块序号`，序号从 `parent_id` 尾部 `_parent_(\d+)$` 取，取不到就退纯文件名
    （绝不能显示 `#undefined`）；正文/块 id/子块数搬进 `.chunk-card-body` 的原生 `title`。
    新增 `deletable`/`deleting` props 与 `.chunk-delete`（`@click.stop`；DOM 里仍必须是第二个孩子才落右上角）。
  - `ChunkPickerModal`：自己调 `deleteChunk(document_id, parent_id)`，原生 confirm 先于任何请求；
    成功 → 本地剔行 + `emit('chunk-deleted', 整块)`；失败 → 只写错误位、一行不减；
    `deletingId` 期间按钮 `disabled`（连点第二下必然 404，界面却会显示"删除失败"而数据早没了）。
  - **错误位从 v-else-if 链里拆出来**：原写法"删除失败"会把整个结果列表藏掉，行都看不见了还怎么重试。
  - `App.vue`：`handleRemoveChunk` 与 `deleteChunk` import 退役，改接 `@chunk-deleted`
    → `markChunkDeleted` + `remove(parentId)` + `refresh()`；三跳 `remove-chunk` 链路
    （ReferenceList / MessageBubble / MessageList 的 `defineEmits` 与模板监听）全部拆掉，
    引用条只留 `deleted` 压暗。
  - CSS：`.picker-results` 换 `repeat(2, minmax(0,1fr))` + `align-content: start`
    （`1fr` 的最小尺寸是 auto，不写 `minmax(0,…)` 一个长文件名就能把另一列挤出弹窗；
    不写 `align-content` 则 stretch 把每行拉满固定高度）；`.picker-modal` 由 `max-height: 82vh`
    改 `height: 66vh; max-height: calc(100dvh - 24px)`；结果区删掉 `max-height: 60vh`，
    改由 `flex: 1; min-height: 0` 在固定高度里界内有界滚动；≤768 退一列；
    `.chunk-snippet` / `.chunk-meta` 退役，`.chunk-delete` 定位规则从引用条搬进卡片家族。
- 门禁实数：frontend **84 passed / 7 files**（75 → 84：新增 11 条、退役 3 条改判 3 条）、
  `npm run build` exit 0（js 85.42 kB / gzip 33.10 kB，css 10.16 kB / gzip 2.75 kB）、
  G-4 grep **0 命中**。后端本轮零改动，未重跑 pytest。
- 浏览器判据 **35 条全 PASS**（Edge headless + `puppeteer-core --no-save`，探针 `probe-chunk-panel.mjs` 跑完即删）：
  - `ui` 1280×900（回读 1280）**16/16**：弹窗 594px = `round(900×0.66)`、宽 560px；两列网格、
    首行两卡 `top=292` 相同、`left 377/644`、等宽 257px；卡面 `deepseek简介.docx #0` 不含正文，
    `.chunk-snippet/.chunk-meta` 节点数 0，title 才带正文+块 id+子块数；12 张卡 12 个 🗑 0 个红叉；
    **零命中 594→594、切空分类 594→594**（第 ② 条的正身）；面板卡片 0 个删除按钮；零控制台错误。
  - `chat` 1280×900 **12/12**：选中探针块后面板 `selected=1 removes=1 deletes=0`；引用条 `deletes=0`
    且这一轮确实引用 `picker-probe.txt(#395)`；弹窗点 🗑 走了原生 confirm（消息原文含"不可恢复"），
    成功后该行立刻消失且 `.picker-error` 为空；选择池归零；引用条保留并标灰"已删除（之前的答案仍然引用它）"；
    `/api/health` 回到 **9 / 11 / 22**，`picker-probe.txt` 从文档列表隐存（`is_active=false`）；零控制台错误。
  - `narrow` 375×800（回读 375）**7/7**：退一列、卡片竖排（`left=32` 相同、`top 275→326`）、
    高 528px = 66vh、宽 345px = 92vw、弹窗 rect `15→360` 不越界；零控制台错误。
  - **探针接线新增两条**：① 正文搬进 title 后按可见文本已经找不到 `parent_id`，卡片定位改按 `title` 匹配；
    ② `parent_id` 全库唯一 ⇒ 同名探针文档**不能重传**（ui 阶段跑完它还在库里），加 `ensureProbe` 先查后传。
  - 我一度把 `ui` 报成 13/13，回转录核到原始 stdout 才定：**16/16**。判据条数要说就说得实。
- 本轮写入的 `chat_history`：chat 阶段自起 session 1 轮（探针块问答）。探针文档已删并隐存，基线未动。
- 清理：`probe-chunk-panel.mjs` 与临时 `_uitail.txt` 已 `rm`；`npm prune` 后 extraneous = 0、
  `node_modules/@puppeteer` 那个空 scope 目录手动删掉；`package.json` / `package-lock.json` 零 diff。
- 收尾遗留（本轮新增，不进实现）：① 弹窗删除后引用条的 `deleted` 态仍不持久化（旧遗留①的同一件事，
  触发点换了不影响结论）；② `#块序号` 只在 `parent_id` 形如 `…_parent_N` 时给出，
  历史脏数据退成纯文件名后同文档多块会在卡面上撞名（靠 title 才能分辨）。
