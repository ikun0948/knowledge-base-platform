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
