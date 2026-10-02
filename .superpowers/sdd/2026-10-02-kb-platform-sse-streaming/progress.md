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

## Task 1

- Task 1: implementer DONE_WITH_CONCERNS, commit 34975e0, focused 17/17（RED 先行 7 failed/10 passed），全量 114 passed + 1 known-red。
- Ruling（concern 1）: `tests/test_chroma_data.py` 钉的是搬家时计数 2/7，现库 11/22 为阶段一摄入的正常增长——先于本 diff 就红，与流式无关。阶段二不动它；Task 6 收口时把钉值更新为当时实测并在测试注释写明"再上传需重钉"。
- Ruling（concern 2）: pytest 收集基线实为 108（台账 87 是 `^def test` 计数，漏了 parametrize 展开）。计划里"预期 N passed"一律降为参考值；判据改为"零 failed（除上述 known-red）+ 报告记实数"。
- Task 1: minor (deferred): brief Step 2 文案"既有 15 个 PASS"应为 10（Step 4 的 10+7=17 才是准数）。
- Task 1: review Approved（零 Critical/零 Important；实现与 brief 逐字一致经评审者字符串比对证实；GREEN 复核 17 passed）。
- Task 1: ⚠️ 处置 3 条：① brief"既有 15"= 计划文案笔误，已裁（见上）；② `_build_references`/`get_chat_history` 在生成器 try 外抛原生异常——裁定由 Task 2 端点的 `except Exception → 泛化 error 帧（不 str(exc) 原文）`承接，写进 Task 2 派发词；③ 端到端断连（Starlette 关迭代器）TestClient 难以干净模拟——裁定接受"单元层 gen.close() + Task 5 浏览器断流手测"两段证据链，Task 6 记档。
- Task 1: minor (deferred)（评审者 7 条择要，终审再 triage）：流式 used_chunks 只钉了开头（可加 round-trip 断言）；normal 链 LLM 中途失败分支无测试；中途失败测试未验证"已产出事件后才 raise"时序；流/非流约 15 行重复（回退安全授权，阶段二后合并候选）。
- Task 1: complete (commits b0a142e..34975e0, review clean)
- Task 2: implementer DONE_WITH_CONCERNS, commit f6e5629。RED 9failed/15passed(404) → 焦点 41 passed；全量 123 passed + known-red 1。
- 环境事故与处置：:8000/:5173 后台实例随会话重启丢失（implementer 撞 connection refused 是实情）。控制器重启 uvicorn(b9dlt0wbh) 与 vite(b2wdmahiw) 各一实例（非双开），并由控制器补跑 Step 6 活体冒烟：normal 链 meta→token…中文可读；rag 链(69) meta→references(第2帧,先于一切token)→token…→done，data 全单行 JSON。冒烟会话 sse-smoke-1 落库 2 轮，属预期。
- Ruling（concern 2）: brief 两处测试代码笔误系计划缺陷——① `post_stream(Boom())` 少了 TestClient 包装；② Boom 若按 call-time 抛则异常落在 frames() try 之外，测试永红。实现者改为生成器形态（与真 rag_system 一致：调用只造 generator，raise 发生在迭代期）并包 stream_client，语义钉住了本条线要考的 `except Exception → 泛化帧`。授权成立；"call-time raise 不再被测"无生产对应物（generator function 调用不执行 body），接受。
- Task 2: minor (deferred): `_sse` 沿用 brief 的 `default=str`（会静默字符串化意外载荷）——终审再裁是否收紧。
- Task 2: review Approved（零 Critical/零 Important；评审者复跑 test_api_chat 24 passed，旧 15 断言零改动核实；非流端点 diff 内全为上下文行）。
- Task 2: ⚠️ 处置：逐帧不缓冲=控制器活体冒烟已证（裁定③）；断连穿路由=裁定②既定。评审者补核 Starlette 1.6.0 iterate_in_threadpool 无显式 close——引用计数兜底，语义仍"不落库"，确定性化并入 Minor 8。
- Task 2: minor (deferred)（终审 triage）：M2-1 `default=str` 掩盖形状跑偏；M2-2 else 当 token 可改显式 elif+raise；M2-3 Cache-Control 头无断言；M2-4 422 零帧断言偏弱（应 `"event:" not in body`）；M2-5 spy 测试未钉 200；M2-6 normal 桩缺耗尽后抛分支；M2-7 生产流式路径 StorageError 不可达（DB 层抛原始 sqlalchemy 异常→泛化帧；如需恢复策展文案语义应在 database.save_chat_history 包 StorageError——涉及非流 500 语义，留终审裁决）；M2-8 断连清理确定性（try/finally close 或 async generator）与 threadpool 每帧占 worker 的多用户含义。
- Task 2: complete (commits d2727de..f6e5629, review clean)
