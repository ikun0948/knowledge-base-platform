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
