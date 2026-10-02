# SDD ledger — plan: docs/superpowers/plans/2026-09-30-kb-platform-frontend.md

分支裁定: 沿用 feat/backend-split（前端计划 Global Constraints 明文"不新建分支"；后端阶段已终审收口，本分支现承载前端任务）。spec: docs/superpowers/specs/2026-09-30-kb-platform-frontend-backend-split-design.md 可达。

== 预检扫描（派 T1 前）==
| 任务对 | 产出 vs 消费 | 发现 |
| T1→T2 | /api 代理 ↔ client.js | 一致；npm scripts 只 dev/build/preview，与 T7 build 核对吻合 |
| T2→T4/T5 | api 签名 ↔ useDocuments/useChat 调用 | 逐字一致（uploadDocument onProgress、sendChat 入参、getHistory references\|null） |
| T3→T4/T5/T6 | CSS 类名契约 + 解构约定 ↔ 各组件 | 一致；T5 声明 .empty-hint 失去引用但明确留着不删（自洽） |
| T4→T6 | DocumentPanel props ↔ T6 增 clearing/emit | T6 给出的改后 props 块含 T4 全部既有 props，无缺失 |
| T5/T6 内部 | restore/clear 与 watch(sessionId) | 行为契约"DELETE 成功才 resetSession"与后端 DELETE 语义吻合 |
| 各任务自洽 | 环境冒烟 v24.15.0/11.12.1 | 控制者实测本机正是这两值，冒烟行成立 |
| 跨计划契约 | 计划契约行 vs 后端 D4/D5 后现实 | 空检索轮现在**会**落历史（D4），计划"200 保留/502 移除"调和逻辑与之相符；锚点已随 D5 纠偏 |
| 已知风险 | ChatRequest.document_ids 无界 vs 后端 String(500) | 前端照计划直发 selectedIds 不加界——阶段二后端加界；ledger 记档供终评引用，不派单改动 |
结论：无任务间冲突；一处环境事实复核通过；无需裁定改计划。工作区无既有 ledger（新建）。

Task 1: complete (commits `ebc1994`..`3ac0682`，review: Approved / Spec ✅ 零 Critical/Important；评审者独立证实：选择性合入零模板残留、代理 target 是 8000 全项目唯一出处、lockfile 为三声明依赖的干净 npm 闭包)
Task 1: minor (deferred→**T2 携带**): package.json/lock 的 name="tmp-app" 模板残留——并入 T2 首个提交：`npm pkg set name=kb-frontend && npm install --package-lock-only`（只改 package.json 会留下 lock 两处 name 不一致）
Task 1: minor (deferred→T7): "逐字节一致"的代理冒烟证据是结论不是观测——T7 构建冒烟时记录比较命令原始输出
Task 1: minor (deferred→T7): 浏览器级挂载未直接观测（headless 以 SFC-transform 证据替代）——T7 手测必须真开浏览器补上
Task 1: minor (deferred, 记档不改): frontend/.gitignore 的 !.vscode/extensions.json 被根 .gitignore 的 .vscode/ 目录屏蔽而失效——今天无害，留档

Task 2: 汇报 DONE `8f02287`（6 files +97/-3，四文件与 brief 逐字节比对；真 Chromium CDP 契约核对；上传探针做完即用 D2 新加的 delete_by_document_id 清干净，基线复原 1 doc/2-7/仅 legacy 历史行；tmp-app→kb-frontend 改名已并入本提交）。
Task 2: 实施者上报的跨任务事实（评审过后随 T6 派单携带）: ① `/api/history/{id}` 对含 "/" 的 session_id 即使 %2F 编码也 404（Starlette 分段路由）——T6 restore 须把这种 404 当"无历史"；正常 UUID 不踩。② brief 两条 curl 在本机有坑：`<<< ""` 发的是换行字节（命中的是另一条 422）、`-d` 裸中文在 cp936 下假 400。
Task 2: complete (commits `6df5f16`..`8f02287`，review: Approved / Spec 全✅零 Critical；评审者独立机器复核四文件逐字节一致、改名三处同步、vite.config 未动、detailFromText 边界输入不抛)
Task 2: ruling (I-1, client.js:36-38 吞 AbortError 报"无法连接后端"): 裁决——不在 T2 修（四文件须与 brief 逐字节一致）；授权 **T5 派单**（第一个 signal 使用者）在 client.js catch 首行加 `if (err?.name === 'AbortError') throw err;`，作为计划修正案，ledger 此行为授权凭证；T5 评审时该偏离不再算违规。— why: 取消语义与断连语义必须分开，否则用户点停止会看到"后端没起" — cost if wrong: T5 漏改则取消按钮显示误导性文案，终评可补。
Task 2: ruling (I-2, client.js:40 丢掉状态码 → T6 只能字符串匹配 "Not Found" 区分坏 id 404 与接线 bug): 裁决——采纳评审者结构方案：**T3 useSession 从源头收口**，session_id 只允许 `crypto.randomUUID()` 形状（生成的只会是 UUID；从 localStorage 读回的旧值须过正则校验，不合格即丢弃重新生成），坏 id（含 "/"）由构造不可达；T6 仍保留"404 当无历史"的兜底，但派单注明：先另法验证路径接线（如 /api/health 探针 + 网络面板），再接"该会话没有历史"文案。— why: 处理不如消除；字符串匹配歧义是接线 bug 的藏身处的 — cost if wrong: 手工往 localStorage 塞的非法 id 会被静默换新会话（旧历史留在库里但前端不再引用）——可接受，记录于此。
Task 2: minor (deferred, 记档不改): #3 `{detail:[]}`/`{detail:""}` → 空 toast。当前后端所有 detail 出处均非空，纯潜伏；brief 修正案生效（见 I-1）时若顺手可加 `|| HTTP ${status}` 兜底，不强制。
Task 2: minor (deferred→阶段二候选): #4 client.js:41 `res.json()` 对空/HTML 200 体抛英文 SyntaxError；XHR 路径已处理（documents.js:22-24）而 fetch 路径未处理，不对称。今日所有 200 端点都回 JSON，潜伏。
Task 2: minor (deferred→**T4 派单携带**): #5 上传 100% 只代表"字节传完"，解析+向量化在服务器侧还要数秒（本地 0.6B embedding），进度条不得显示"完成"语义；`total===0`→NaN 实际不可达。#6 XHR 无 ontimeout/onabort，签名冻结故 T4 无取消手段——按现状接受。
Task 2: minor (deferred, 记档不改): #7 "uvicorn 已在 :8000 运行"提示是 dev-only 真相（生产同源部署后失真）；brief 逐字块，留。
Task 2: minor (deferred→**T6 派单携带**): #8 getHistory 的 limit 未校验，传 null 会成 `?limit=null`→422（可读懂，优雅降级）；T6 只传数字。
Task 2: minor (裁定接受): #9 T2 上传探针用后端自有删除函数清了库（超出 brief"不做清理"），证据充分予以追认；**基线纪律**：T4/T7 上传的文档**保留**，是 T7 手测清单的基线，不再做共享状态外科手术。
Task 2: 评审 ⚠️ 一项（注释行数：brief 块自带 2-3 行注释 vs 计划"一行以内"规则）——评审者裁定按逐字节规则实现者无错；终评若再问，以本条答复。

Task 3: complete (commits `37b57de`..`baddb06`，review: Approved / Spec 22✅ 4⚠️ 0❌ 零 Critical；评审者独立复核：7/8 文件与 brief 逐字节全等、唯一偏离严格等于授权范围、类名 29/29、token 28 个无悬空 var()、全仓零 <style> 块、:8000 仍唯一出处、Step 9 七项原始观测与 CSS 推导自洽；并独立证实正则与后端 uuid4 历史行兼容——不会孤儿化已有会话)
Task 3: ruling (评审 I-1, 颜色字面值约束 vs brief 自带 6 处: base.css:27,34,36 + layout.css:41,48,66): 裁决——约束文面收窄为「组件内不得有颜色字面值；variables.css 之外不得**新增**字面值」，brief 逐字块自带的 6 处豁免、不另派收口（改动会破逐字规格并牵连 T4/T5 的 diff 基线）；终评以此条认定合规。— cost if wrong: 样式统一性欠账，阶段二 token 化。
Task 3: ruling (评审 I-2, panel-toggle 移动端可及性 → **T7 派单携带**): brief 散文「贴右上角」与其自带 CSS 矛盾，实测 ≤768px 按钮独占整行、排聊天区下方（rect x:10 y:559 w:680）；T5 消息区变长后可能掉出首屏。**任何修法（position:fixed / 移进 .chat-container 头部 / justify-self:start）都构成对 brief CSS 的偏离，T7 动手前须先拿到控制者授权**；本行即预授权候选清单，非授权本身。
Task 3: minor (deferred, 记档不改): M-1 `UUID_RE` 带 /i 会放行大写十六进制；与"= randomUUID 形状"严格口径差半档，现状无害（仍不含 "/"）。收紧需授权。
Task 3: 修正案原文补录（评审 M-2）: `/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i`——终评直接 diff useSession.js 用这行。
Task 3: minor (归因纠正，评审 M-3): button 的 inline-flex→flex 是 CSS Display 规范对 grid item 的 blockification，跨引擎一致，非 Chrome/Edge UA 怪癖——T7 勿当环境差异排查。
Task 3: minor (deferred→**T7 派单携带**): M-4 报告用「工作树 vs HEAD」空 diff 证明保护文件未动是弱证据，T7 一律用范围 diff（BASE..HEAD）；M-7 顺手补 `http://127.0.0.1:5173` 观测一条。
Task 3: minor (deferred→**T5/T6 派单携带**): M-6 `useSession()` 每次调用返回**独立** ref，无共享状态——子组件绝不再调一次 useSession()，必须继续由 App.vue 传入 sessionId（resetSession 同理只此一家）。
Task 3: 过程知识 (deferred→**T7 派单携带**): headless/小窗默认 innerWidth 754px 已落入 max-width:768 断点，宽屏四项会被正确 CSS 判为失败（T3 首轮即误判）——宽屏项必须显式视口 ≥769（本次 1280×900），报告保留 viewport 原始值。

Task 4: complete (commits `f4d04d6`..`73f728b`，review: Approved / Spec 零偏离——5 文件 HEAD blob 与 brief 围栏块逐字节全等、layout.css 纯末尾追加(+46/−0)、App.vue 改动面严格等于 brief 指定、13 保护文件 blob 哈希全同、19 类全落位全引用、docLabel 全仓唯一出处；Step 8 七项 5✅2⚠️，两条 ⚠️ 均为 brief 预期 vs 真实环境冲突而非实现问题；评审者给出代码级铁证并做了跨轨时间线核算)
Task 4: 基线更新: documents 4 行（#1 legacy、#69 comp.txt、#71 rag.txt、#72 third.txt，autoincr 吃掉 70/73）、Chroma parent 5 / child 10。此为 **T7 手测基线**，后续任务上传物继续保留。
Task 4: ruling (评审 I-P1, T7 判据 2 与基线唯一键冲突): T7「依次上传 comp.txt、rag.txt 两条都 ✅」在现基线下必 500——判据 2 改写为上传**新文件名**（如 comp2.txt/rag2.txt，内容同 brief）；判据 5（自然撞 500 显示 detail 原文）改由「重传同名 comp.txt」提供场景。T7 派单带此改后判据。
Task 4: ruling (评审 I-P2, 断后端中文文案不可达——机制由评审者钉死): vite 8.3.2 代理上游连不上时 **dev server 自己发 502 空体**（node_modules/vite .../node.js:19740 `proxy.on("error") → writeHead(502)`），于是 xhr.onload/fetch 都拿到响应，`detailFromText("",502)`→`HTTP 502`；`xhr.onerror` 与 client.js 的中文 catch 分支在「代理活、后端死」拓扑**永不触发**。裁定：文案预期改写为「断后端 → dev 拓扑下 `HTTP 502` + 队列红底失败行/错误条；中文文案仅在直连 :8000（不经代理）时可达」——**适用于 T5 验证第 7 项与 T7 判据**，随派单携带；api/ 与 vite.config 维持冻结，不得为凑文案改码。
Task 4: ruling (顾虑②, 同名重传 500): 后端事实核实为真（document_processor.py:72 parent_id=f"{filename}_parent_{i}" + database.py:34 unique，键不含 document_id → 同名二次上传必 1062 → 补偿链回滚干净 → StorageError→500）。裁定：**后端已知限制，前端按现状显示 500 detail 原文即正确行为**，T4 不该有作为；前端侧防护归阶段二议题（ledger 记档，T7 判据 5 覆盖展示面）。
Task 4: ruling (顾虑③, 串行证据): 评审者跨轨核算通过（DOM 至多一行上传中 + POST/响应严格串行 + 每个 201 后紧跟 GET refresh；313ms 服务耗时与 125ms 采样窗吻合）——串行判据 PASS，"三行变 ok"未达成为②环境原因。
Task 4: 修正案改挂 (T2 ruling I-1 之 T5 部分作废): T5 brief 通篇**不使用 signal/AbortError**（停止生成按钮不存在，pending 只覆盖网络往返）——AbortError 一行修正案**不随 T5 落地**，client.js 在本分支保持全冻结；挂点改为「第一个 signal 使用者（SSE 阶段二）」，若终评前仍无 signal 使用则记阶段二项。— why: YAGNI，不为不可达路径开冻结面偏离 — cost if wrong: 无（该路径本分支不可触发）。
Task 4: minor (deferred, 记档): M-4 FileUploader.vue:10,15 `inputEl` 死代码（brief 逐字规格自带）——终评引用本条认定非实施者责任。
Task 4: minor (deferred→T7): M-5 构建冒烟前先 `rm -rf frontend/dist`（T4 实施者留下的 dist/ 已被 gitignore，但旧 bundle 哈希会干扰判读）。
Task 4: 报告表述纠正（评审 M-1/M-2/M-3，代码零牵连）: layout.css 追加实测 前缀 3177 + 分隔空行 + 块 1712 字符（总 4890，报告引文"1711"漂移）；App.vue 解构 10 个返回值（非 11，docLabel 未解构且 brief 块本就如此）；"17 类"计数出自派单摘要非 brief 原文。

Task 5: complete (commits `5e699df`..`35bada3`，首派崩溃后 fresh 重派成功；review: Approved / Spec 逐条全绿代码级偏离 0——8/8 围栏块 blob 级逐字相等、layout.css 单 hunk +74/−0 append-only、14 冻结文件哈希相等、v-html 零命中、Step 10 八项按裁定 2/6/7 改写判据全过；打字机与 app.py:343-347 语义逐行核对一致)
Task 5: 基线更新: documents 5 行（+#74 xss.txt，brief Step 10 明文要求）、Chroma parent 6 / child 11。T7 手测基线随之更新。
Task 5: ruling (I-1 长答案滚动 no-op——**根因翻案**): 实施者归因（.chat-messages 缺 min-height:0）被评审者证伪为不充分——overflow-y:auto 使其自动最小尺寸本来就是 0，补 min-height:0 是 0→0 no-op；真根因在 `.app-shell` 隐式 auto 行 + `.chat-main` 未中和最小尺寸，内容超可用高度时 max-height:100% 解析在已撑高的行上。**授权 Task 7 末尾追加**（不破 append-only）：`@media (min-width:769px){ .app-shell{grid-template-rows:minmax(0,1fr);} .chat-main{min-height:0;} }`；兜底（仅当判据①仍不成立）：追加 `.chat-body{overflow:hidden}`。归属裁定：brief 自带缺陷，T5 零扣分，实施者"保留逐字+移交证据"是唯一合规处置。
Task 5: ruling (I-2, T7 滚动判据只写在 375px 分支): 采纳评审者量化判据替换——≥1500 字真调 LLM 答案放完后，1440/1280/900 三档视口各验：① .chat-messages clientH<scrollH ② scrollTop 写后读回>0≈scrollH-clientH ③ .chat-input bottom≤innerHeight ④ elementFromPoint(输入框中心)命中 chat-textarea ⑤ 放字中途 cursors=1、Console 零 error/warning。随 T7 派单下发。
Task 5: ruling (M-2, 刷新后来源标签消失——HistoryMessage 无 mode 字段): 裁定**接受为阶段一限制**，T7 判据 4 明写「来源标签不在刷新等价验收范围」；给 chat_history 加 mode 列归阶段二后端议题，记档。
Task 5: minor (deferred→T7): M-4 snippet 末尾 `...` 截断分支从未被观测——T7 需上传一个含 ≥80 字符块的新文档（新文件名，防撞名 500；上传物按纪律保留）再用 curl /api/history 逐字对照。M-1 emoji 代理项对半切（join 无损、SSE 日删 typewriter.js，记档不改）。M-6 typewriter stop() 的卸载路径无人注册（App 单例常驻无泄漏，记档）。M-5 报告头部状态字未回收与 :248 笔误（文档卫生，代码零牵连）。
Task 5: 流程裁定: 自报"提交提前于部分验证"与"辅助脚本误用 query-param 历史路径"经评审者独立证实不影响验收（范围单提交、blob 仍逐字）——追认，崩后抗崩溃纪律有效。

Task 6: complete (commits `eaafb0b`..`02210c0`，review: Approved 无需返工 / Spec 全绿零代码偏离——5/5 围栏块 HEAD blob 级逐字独立复验、行为契约三则（DELETE 成功才 resetSession / false 不动消息与 sid / 取消零请求）毫秒级原始证据、clearing 无 finally 等价性由 useChat.clear 返回路径证成、29 文件全树比对仅 2 行哈希不同；Step 4 九项原始观测齐备)
Task 6: ruling (评审 I-1, 报告把 NULL 引用边界挂错样本): 被验会话 66fa9c8f… 是今天的 normal/空检索轮（NULL 由**当前代码**仍在写，rag_system.py:62/:85-90），不是 2026-09-19 改造前行；结论仍成立且覆盖更牢。记档边界第 3 条改述为「NULL 由 normal/空检索路径与改造前行共同覆盖」；**T7 派单**：用真 2026-09-19 会话 `0a6e5ed2…`（UUID 形状）手工换 id 刷新，钉死改造前老行路径。
Task 6: 平台事实 (随 T7 硬约束): 本机 commit limit 吃紧——第二个 uvicorn 实例因 embedding 模型再加载实测 os error 1455 startup failed（评审者核 traceback 与 vector_store.py:21 归因可信）。**T7 不得起双后端**；复用现存自起服务：uvicorn --reload PID 22432（:8000）、vite dev PID 6044（:5173），非死勿杀；「断后端」子项**引用 T6 报告判 PASS**，不重演杀进程。CDP `edge.kill()` 有 localStorage 不落盘怪癖：每程 reload 前显式 setItem 目标 sid（T6 顾虑②）。
Task 6: minor (记档): M-1 逐字脚本"三个代码块"应为 4 围栏块+import 共 5 例（断言覆盖全，措辞错）；M-2 报告 PID 账 15740→17764→22432 链条未交代 + 一次 taskkill 被 Git Bash 展开吞参；M-3 brief/database.py:224 行号漂移（实际 :233）；M-4 竞态记档——DELETE 在飞时"换一个 session_id"调试按钮仍可点，代价属"界面永远等于后端真相"同族，brief 块冻结不改。
Task 6: 基线更新: chat_history 13 行/8 会话（T6 真实问答按不清库纪律保留）。documents 5/parent 6/child 11 不变。
Task 5: 现场记录——首个实施代理执行错误崩溃（902k tokens/12 tool uses，无提交无报告），残件（useChat/MessageList/MessageBubble/ReferenceList/ChatInput/typewriter + layout.css 改动）已挪 task-5-crash-leftovers/，工作树复原 44bf3ba；重派携带：报告增量写盘 + 上下文节俭两条抗崩溃纪律。
Task 7: 现场记录——首派代理随上次会话终止而静默（报告 22:38 后 17.5h 无更新、无提交、工作树干净；重启会话后 :8000/:5173 均已消失）。已完成部分保留在 task-7-report.md（340 行：头部+12 条改写判据清单、Step 0/2/3、判据 2-6 全 PASS，含 long.txt #77 观测到 `...` 截断分支、真 2026-09-19 会话 0a6e5ed2 换 id 恢复、xss #74 零弹窗）。重派携带：续写同一份报告，已 PASS 项不重演；剩余 Step 1 三视口×5 点滚动与响应式、Step 5 app.py 16 行对照、Console 洁净合成、Step 6 收尾（有改动才提交，禁空提交）。服务由控制方重启（uvicorn :8000 + vite :5173 后台任务），仍禁双后端。
Task 7: complete (commits `bc21bfe`..`7d7776f`，两棒接力：首派静默后 fresh 续写完成 Step 1/4补格/5/6；review: Approved 零 Critical 零 Important——P1 改动面 9/0 仅 layout.css 且与授权串逐字等价、append-only hunk 证实、api/ 四文件三处哈希全等、静态把关复跑 1/1/1；P2 抽 13 处日志逐字命中、app.py 锚点全落点、三档五点数字交叉自洽、修复前判据①确为 false 授权合法触发；P3 两棒边界 +17 行偏移与「前任 340 行」精确闭合，判据 2-6 一字未改)
Task 7: 授权修法执行记录: 判据①修复前 false → 末尾追加 `@media(min-width:769px){.app-shell{grid-template-rows:minmax(0,1fr);}.chat-main{min-height:0}}` → 三档 ①-⑤ 全 PASS；兜底 .chat-body{overflow:hidden} 未动用。滚动根因翻案（Task 5 I-1）至此实证闭环。
Task 7: 基线更新: documents 9 行（+#78 wide.txt，Step 1 唯一一次上传，按纪律保留）、chat_history 25 行/10 会话、主测量会话 feec926f…（6 行↔界面 12 条）。
Task 7: ruling (评审 M-1 当代闭环): Step 3 构建证据原产自 10-01 源码树、未覆盖授权 CSS——评审者已在当前 HEAD 用临时 outDir 代跑：零 error/warning、JS md5 与前任产物相同、CSS 7367→7458B 且产物内仅授权两条声明无夹带。**阶段一构建冒烟对最终树成立**，无需返工。M-2/M-3/M-4/M-5 为报告卫生项（追加 17 行致内部行号引用陈旧、状态行未回收、:394 一处数字串档），记档不返工；阶段二派单引用 T7 报告行号时须 +17 或以本节为准。
Task 7: 遗留移交阶段二 (L-1~L-11 全量见 task-7-report.md 末表): 移动端 panel-toggle 掉出首屏 + ≤768 侧栏塌 2px + ≤768 消息区非有界滚动（同族根因=行高未中和，修法构成 brief 偏离需授权）；chat_history 加 mode 列；同名重传唯一键；方法学三条（edge.kill localStorage、confirm 死锁须不 await 派发、GBK 控制台字数虚增）。
