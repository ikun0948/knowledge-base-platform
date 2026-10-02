# SDD ledger — plan: docs/superpowers/plans/2026-10-02-kb-platform-sse-streaming.md

分支：feat/sse-stream（自 master @ d2ce465 切出，基线 80fb1aa 之后的计划提交）
Global Constraints 来源：计划文头 + spec 6.4/6.3/11 节；spec 可达（docs/superpowers/specs/2026-09-30-kb-platform-frontend-backend-split-design.md）。

## Pre-flight 扫描（控制器，Task 派发前）

| 配对 | 生产 vs 消费 | 结论 |
|---|---|---|
| T1↔T2 | T1 产 `("token", str)` / `("references", list[Reference])`；T2 端点对 token 包 `{"text": data}`、对 references 做 `[r.model_dump()]` 展平 | 一致，无需裁决 |
| T2↔T4 | T2 帧名 meta/references/token/done/error 与 data 形状；T4 dispatch 按 `event:` 行解析、Task 4 探针实测帧序 | 一致；T4 探针③会向 chat_history 写入 `t4-probe-*` 会话行——预期副作用，收口台账记数 |
| T3↔T5 | T3 产 HistoryMessage.mode（assistant 行 rag/normal，user 行 null）；T5 restore 消费 `row.mode ?? null` | 一致 |
| T4↔T5 | T4 保留 sendChat（构建不炸）；T5 与调用方切换同提交删除 | 一致 |
| T5↔T6 | T5 git rm typewriter；T6 grep 零残留 + 构建冒烟 | 一致 |
| T2/T4 环境 | 编辑后端文件触发现存 uvicorn --reload 重启（同进程位，不是第二实例）；计划已写"瞬时 502 等 3 秒" | 合规（1455 红线不触） |
| 测试数 | 基线 87（实测 grep 计数）；T1+7、T2+9、T3+4 → T3 末 107 | 计划文三处预期值已修正后入库 |

裁定：扫描无阻断冲突；无 plan-vs-rubric 缺陷（无空断言、无逻辑块复制）。

模型说明：本 harness 的 Agent model 参数无可靠可枚举 ID，按 Qoder 集成规则记录为**继承会话模型**（所有派发同样处理，不再逐条重复）。
