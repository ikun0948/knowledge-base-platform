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
| 测试数 | 基线 87（实测 grep 计数）；T1+7、T2+9、T3+4 → T3 末 107 | ✅(b3a6a95) 阶段三已统一修订计划文：:203 改实数 10、:500 改实数 15、:726 把"参考值"升为正式判据（零 failed + 记实数）并补记 127→128→129/2/1 实数链；"预测数一律参考值"自此不再依赖口头软化 |

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
- Task 3: implementer DONE_WITH_CONCERNS, commit 9612115。RED 4failed/35passed → 焦点 39 passed；全量 127 passed + known-red 1（brief 参考值 107 偏低，按裁定记实数）。brief 代码逐字可用，无笔误修正。
- 环境事故2：旧 uvicorn 的 watchfiles 监听失灵（编辑后 80 秒不热重载）。控制器停 b9dlt0wbh、重启为 b7uria781（任务实例 4648 已止），健康 200。此后各 Task 改完后端文件一律由控制器重启实例取信 reload，派发词照旧"勿杀勿起"。
- 控制器代补 Step 5 活体：51 项 → /api/chat 与 /api/chat/stream 均 422（JSON 体、无 `event:` 前缀，validation 先于生成器成立）；GET /api/history/sse-smoke-1 modes=[None,'rag',None,'normal']（rag/normal 派生实测在真数据上）。t3-live 未落库（422 挡在写前）；implementer 探测产生的 t3-probe 2 行已由其自行 DELETE 清零。
- Task 3: minor (deferred): L-4 记账面确认——legacy pre-2026-09-19 rag 行读作 normal，已有显式测试钉住（成本接受，阶段三若有迁移再收）。
- Task 3: fix round 1/5（1 addressed, 0 open；commits 9612115..fc32760；复审确认三条断言就位且非空洞，`"event:" not in body` 比同文件旧测更强）。
- Task 3: minor (deferred) 补录：M3-1 `document_ids=""` 假值面未钉（写侧不可能产出空串，加固候选）；M3-2 恰好 50 项接受边界未钉；M3-3 mode 计算早于使用一语句。修枝者自启过实例一事核实为误判：现 :8000 唯一监听 29184 = 控制器 b7uria781 的重载子进程，watchfiles 恢复正常（改测试即热重载），后续仍按计划"复用勿动"。
- Task 3: complete (commits de103d7..fc32760, review clean after 1 fix round)
- Task 4: implementer DONE, commit 2226ee0。探针①②③全过（references 第2帧钉住；AbortError 原样；帧距 70ms 渐进）；byte-exact 对 brief，Node 相对 URL shim 仅探针侧。
- Task 4: review Approved + 3 Important（全部 labeled plan-mandated，指向计划文 Task 4 代码块本身）。
- Ruling（I-1/I-2/I-3 合并裁决：修，不授权带病过账）: 评审者实证 my-try 把 onEvent 回调异常与 dispatch 帧解析异常都重新包装成"流式响应中断"（Task 5 将成为第一个被误导的调试会话）；AbortSignal.timeout 的 TimeoutError 在两阶段都落入误导文案（头前→"无法连接后端"，正是 G-2 反模式）；异常出口无 reader 归还，后端生成器对着无人读的 socket 续产。修法=收窄网络 try 只包 read()，dispatch/onEvent 移出其外原样上抛；abort 判定改 `signal?.aborted`（用户 cancel 与 timeout 同为调用方主动，都原样传播）；finally 归还 reader（EOF 时 cancel 为无害 no-op）。代价：postStream 契约微移——回调/解析异常不再被翻译——Task 5 派发词须带上；若误判，代价是 Task 5 里多一层 try 的返工，可逆。
- Task 4: minor (deferred): CRLF 全流静默零帧、EOF 尾缓冲丢弃、无 decode() flush、body:null 裸 TypeError、空 event 名派发 ''、abort 后同 chunk 缓冲帧继续派发（Task 5 若需硬停自查 signal.aborted）、未校验响应 content-type。
- Task 4: fix round 1/5（3 addressed, 0 open；commits 2226ee0..3c3ca5b；复审者用 stubbed fetch 18 断言独立复现 I-1/I-2/I-3 全关，且回归护栏 G/H 未破）。
- Task 4: 契约微移（复审者提示，必须带进 Task 5 派发词）: ① dispatch/onEvent 回调异常与帧解析异常现**原样上抛**，不再被翻译成"流式响应中断"；② `signal?.aborted` 判据意味着"抛错⇏网络错"，Task 5 的 AbortError 静默分支按 name==='AbortError' 判定仍成立（应用内唯一 abort 源是 AbortController）；③ finally cancel 不 await，无观测面。
- Task 4: complete (commits c05b626..3c3ca5b, review clean after 1 fix round)
- Task 5: implementer 分两棒——首棒 BLOCKED（vite :5173 死于后台任务 127 退码，遵守"勿动服务"正确）；控制器重启 vite=b8jvlzgln 后续棒 6/6 PASS 并提交 b7cc1ab（3 修改+typewriter 删除，diffstat +73/-90 恰为 brief 文件集）。
- Ruling（Step 4 判据自冲突，plan-mandated）: `sendChat\b` 宽 grep 必然命中 brief 自己在 chat.js:7 的注释。验收取代码面判据：`sendChat(` 与 `import .*sendChat` 零命中（实测 exit 1）。Task 6 静态总表沿用此判据（宽 grep 结果只作记档不作门禁）。
- Ruling（视口）: browser-use 无 resize 工具，6/6 在 innerWidth=542 移动路径完成；六项判据皆内容级（时序/顺序/cursor 数/一致性/Console），与视口无关；CSS 阶段二零改动，桌面宽屏回归列阶段三手测清单。记 deviation 不记缺陷。
- Task 5: review Approved（评审者逐字节重建核对 brief 三块全等，"立即"修复在案；三重命名风险核对：App.vue 解构无 finishTyping、MessageBubble 契约未动、typewriter 无其他引用者）。
- Task 5: minor (deferred): M5-1 error 帧 detail 若为空串会静默当成功（spec 保证不可达，阶段三加固候选：`if (fail !== '')` 或 'error' in events 标记位）；M5-2 done 分支无注释（brief 原文）。
- 环境事故3：vite 后台任务以 127 退出（npm 在任务尾 shell 解析失败），现象=端口无人监听。处置记录：控制器重启并双端口探活后才派浏览器棒；后续浏览器 Task 一律先探 :5173。
- Task 5: complete (commits baef88d..b7cc1ab, review clean)

## 阶段二收口（Task 6 · 全链路终验 + 构建冒烟 + 台账，2026-10-02）

控制器实例 uvicorn b7uria781(:8000)、vite b8jvlzgln(:5173) 全程复用，未杀未起。本 Task 只验证与记账，**不做分支集成**（集成走 finishing-a-development-branch 三选一菜单，归控制器/用户）。

### 五个 Task 提交范围与评审结论（读自本台账）
- Task 1 `b0a142e..34975e0`：review Approved（零 Critical/零 Important）。
- Task 2 `d2727de..f6e5629`：review Approved（评审复跑 test_api_chat 24 passed）。
- Task 3 `de103d7..fc32760`：review Approved after 1 fix round（422 测试补钉零 SSE 帧）。
- Task 4 `c05b626..3c3ca5b`：review Approved + 3 Important（全 plan-mandated，合并裁决=修）after 1 fix round。
- Task 5 `baef88d..b7cc1ab`：review Approved（宽 grep 判据裁定 + 视口 542 记 deviation）。

### Step 1 后端全量（实测计数，非抄预期）
- 改钉前 `1 failed, 127 passed`（总 128；红项唯一 = test_chroma_data 搬家守卫钉值 2/7 vs live 11/22）。
- Step 1.5 重钉后全量复跑 `128 passed`（零 failed；1 warning = SQLAlchemy declarative_base 弃用，与流式无关）。brief "107" 是计划参考值，按 Task 1 裁定记实数。

### Step 1.5 chroma 重钉（新增，另立提交 c4bc753）
- 权威值 live `GET /api/health`：`document_count 9`、`vector_counts {parent:11, child:22}`；父 11/子 22 全集 ids 从 tmp 副本读出，**真库零写、零上传**。
- 原迁移 2 父 + 7 子**全部仍是现集合子集**（搬家守卫使命达成后重钉）；计数与两套 ids 同步重钉（否则 line 39-44 全等断言仍红）。测试加中文注释「计数为 2026-10-02 阶段二收口实测，后续再上传文档需重钉」；顺带删去失实的"/api/health 共用这两个常量"一句（test_health 走 FakeVectorStore，与此无关，未动）。单文件复跑 `1 passed`。

### Step 2 活体手测（打 :8000，原文）
- POST /api/chat（heredoc --data-binary 规避 GBK body，session t6-check）：`HTTP_CODE=200` `CTYPE=application/json`，body `{"answer":"你好！有什么我可以帮你的吗？","references":[],"mode":"normal"}`——回退路径存活，真实落库 1 行 normal（预期副作用）。
- POST /api/chat/stream 51 项：`status 422` `ctype application/json` `has_event_colon False`，body `{"detail":[{"type":"too_long","loc":["body","document_ids"],...}]}`——G-1 上界在流开始**前**拦截，零 SSE 帧。

### Step 3 静态把关（逐条实测 exit）
- v-html/innerHTML → EXIT=1 ✓；sendChat( → EXIT=1 ✓；import .*sendChat**\b**（精确词边界）→ EXIT=1 ✓；后端地址 127.0.0.1:8000|localhost:8000 → EXIT=1 ✓。
- ⚠️ 台账原语 `import .*sendChat`（**无词边界**）实测 EXIT=0，命中 `useChat.js:3 import { sendChatStream }`——是**新**流式符号误报，非旧 sendChat 残留；已用词边界式钉死"旧 sendChat 无任何 import"。宽 grep（typewriter|startTypewriter|fullText|finishTyping|sendChat\b）仅命中 `chat.js:7` 解释性注释（Task 5 裁定：记档非门禁）→ typewriter 删除彻底。
- 颜色字面量两度量分开报：brief Step-3 原命令（glob 含 variables.css）实测 **17** unique hex（16 枚在受许 token 文件 variables.css，`.vue`/App.vue 侧 **0**）；"≤11 / T7 基线 11 处"是**另一度量**=variables.css 之外的颜色字面出现次数（hex+rgba）实测仍 **11**（base.css:27,34,36 + layout.css:41,48,66,138,171,172,211,223）。`git log master..HEAD -- frontend/src/styles` **空** → 阶段二零改 CSS，两度量皆与阶段一逐字相等、无增长；17≠11 系命令 glob 口径差异，非回归。G-4 仍是阶段三 token 收敛项。

### Step 4 构建冒烟
- `rm -rf dist && npm run build`：`vite v8.3.2` 30 modules transformed，`✓ built in 158ms`，**exit 0**；构建后 `git status` **干净**，`frontend/.gitignore:11 dist` 经 `git check-ignore` 证实不入库。

### 阶段二数据面（chat_history 新增，记档）
- Task 2 活体 `sse-smoke-1` 2 轮；Task 4 探针 `t4-probe-normal/rag/rag-payload/errframe` 各 1 行（净 4），`t4-probe-abort/abort-pre/422/timeout` 全 0 行；Task 5 探针 `t5-live-normal-20261002120929`(2)、`t5-live-rag-20261002120929`(2)，`t5-live-abort-*`/`t5-live-seed-*`/`t5-curl-probe` 全 0；Task 3 `t3-live` 未落库（422 挡写前）、`t3-probe` 2 行自清；Task 6 `t6-check` 1 行 normal（51 项 stream 0 行）。净增以实测记于各 Task 报告。
- **断流不落半截验证会话 id**：`t4-probe-abort`（收 3 帧仍 0 行，后端生成器 close）+ `t5-live-abort-20261002120929`（前端 abort → GET /api/history rows=0，异常落 save 前）—— Task 1 裁定③"单元 gen.close() + 浏览器断流"两段链至此闭合。

### L-4 legacy 记档
- 会话 `0a6e5ed2…`（pre-2026-09-19 老 rag 行）刷新后按设计显示"💬 自由对话"（mode 派生 normal），非缺陷；Task 3 显式测试已钉住该记账面，阶段三若有历史迁移再收。

### 阶段三候选（备查，本阶段不做）
✅(51e7ca7) L-1/L-2/L-3 移动端适配（≤768 行高中和 + 侧栏 fixed 浮层 + toggle 移 DOM 首位；Edge headless 375×800 RED/GREEN 量化互证：toggle 25370→10、侧栏 2px→560px、msgs 有界 513<25120 文档 scrollTop 恒 0；宽屏 1280 不回归。附带收益：量测改用 puppeteer-core+Edge --no-save，绕开 in-app 浏览器无 surface 与 754px 上限）。剩余：✅(822437b) 停止生成按钮（已交付，见终审遗留节销账行）；✅(5e1c9de) G-4 颜色 tokens 化（variables.css 外字面量 11→0；新增 --on-brand/--shadow-btn-hover/--focus-ring，白底复用 --panel-bg；**17/11 双度量就此废弃**，唯一口径判据 = `grep -rnE '#[0-9a-fA-F]{3,8}\b|rgba?\(' frontend/src --include='*.css' --include='*.vue' --include='*.js' | grep -v 'styles/variables.css'` 期望 0 命中，variables.css 本体豁免）；✅(52ec28c/47f31af) M-F2 ReferenceList docLabel 内联重复（docLabel 收双形状 `doc.id ?? doc.document_id`，ReferenceList 改 import 唯一出处；TDD：document_id 形状用例先 RED 返 `#undefined`，GREEN 后 npm test 33→36）；✅(52ec28c/47f31af) M-F3 handleSend 忽略 emit 载荷（改 `handleSend(text)` 直接用 ChatInput 已 trim 的载荷，数据流单向，失败回填也用载荷）；✅(52ec28c 零代码销账) M5-1 error 帧 detail 空串边界（经核阶段二修复波已闭合：useChat `errored` 标记位 + 空 detail 兜底文案 '流式响应出错，请重试'，且 vitest useChat.test.js 已钉该用例，本项无需改动）；✅(b3a6a95) 计划文失实预期值与 grep 口径统一修订（三类：Task 1/2 Step 的"既有 15/14 PASS"→实数 10/15；Task 3 全量行判据升格 + 127→128→129/2/1 实数链；Task 5/6 静态把关两条命令口径改为可满足——颜色 0 命中与 `sendChat(` 调用面边界，并给 :27、"前端没有测试框架"、阶段三候选四处补交付注记）；✅(afa9158) M2-7/M-b 生产流式路径 StorageError 可达（`database.save_chat_history` 把裸 sqlalchemy 异常包成 `StorageError("保存对话历史失败，请稍后重试")`，rollback 与 `__cause__` 链都留；流式给策展 error 帧、非流由中央映射给 500 同文案。单测先 RED=RuntimeError 非 StorageError，全量门 136→137）；✅(e1a3034/见下"阶段三收尾"节) 桌面宽屏浏览器回归清单已实跑（Edge headless 1280×800 / 1920×1080 / 1024×768 三档 × 八判据全 PASS，零代码缺陷；顺带 375 档与 pending 双态交互复验）。

### 收口判定
后端 128 全绿 + 回退 200 + 上界 422 零帧 + 断流不落 + typewriter 彻底移除 + 构建 exit 0 + dist 不入库 + CSS 零改动 → 阶段二 SSE 流式 **可交付**。遗留两处为台账/命令口径层面（颜色度量、sendChat 无边界 grep），非代码缺陷。✅(b3a6a95) 两处均已收口：颜色判据改 G-4 唯一口径（`grep -v styles/variables.css` 后 0 命中，旧命令恒返 17 已废弃）；`sendChat\b` → `sendChat(` 带调用面边界（旧写法撞 `api/chat.js` 的"非流版 sendChat 已删除"史注，致"退出码 1"永不可满足；改后实测 ①②③ 退出码全 1）。
- Task 6: complete (commit c4bc753 test 重钉 + 本 docs 收口台账；全链路终验通过)
- Task 6 review: Approved（零 Critical/零 Important；评审独立复跑 test_chroma_data 1 passed，实证重钉与 live 快照全等；代码域 grep 门禁经评审核实确实 exit 1）
- Task 6 minor(deferred): M6-1 全量 1 warning=SQLAlchemy declarative_base 弃用（预存在，未进阶段三清单，本行补记移交）；M6-2 报告/台账"line 39-44"叙述随重钉漂移（实际断言在 :63-68）；M6-3 台账颜色行 17/11 表述偏压缩（报告正文已展开）。✅(b3a6a95) 就此消解——17/11 双度量已废弃，唯一口径 = Task 6 Step 3 那条命令 0 命中。

## 全分支终审与修复波（2026-10-02）

终审包 `review-d2ce465..0ce68e8.diff`（20 commits）。裁决 **With fixes**：零 Critical、两条 Important、若干 Minor；四条 ledger 裁定（signal.aborted 替换、Boom 生成器化、grep 判据、chroma 重钉）经终审**对码核实**均已落地。

### 修复波（一次，commits f8b0fe9 / 1cfdf7b / 19981a9）
- I-1 `done` 哨兵：useChat 认 `ended`，EOF-without-done → 撤泡 + '流式响应意外中断，请重试' + false；client.js 增 content-type `text/event-stream` 守卫（中文报错）。探针 RED 16/26→GREEN 26/26（stub fetch，零真实后端）。
- I-2 并发上限注释：chat.py:59 一行（同步生成器经 threadpool，≈40 并发流上限；措辞"占一个 worker"略强于机制实况——token 是按 next() 借还，因 next() 阻塞在 LLM 读上才近似全程占用，Minor nit 不改）。
- M-a stream 侧 used_chunks 全等 round-trip 断言（与非流 :112-116 镜像）；M-c `errored` 布尔+空 detail 兜底文案；M-d 静默分支改 `signal.aborted`（G-2 对称）；M-f 422 零帧判据收紧为 `"event:" not in`。
- M-h pytest addopts=`-m "not migration"`：默认 127 passed + 1 deselected；`-m migration` 显式 1 passed。
- 复审 **All ADDRESSED，零新 Critical/Important**。新 Minor 两条入册：① 命令行显式 `-m` 会整体覆盖 addopts（阶段一文档门禁 `-m "not live"` 仍会跑搬家守卫——非回归，预存在行为，阶段三知会）；② I-2 注释措辞 nit（同上）。

### 终审 M-i 修正（本台账原文失实，已改）
"计划文三处预期值已修正后入库"不实：仅 :726 带零-failed 软化，:203/:500 旧值未改文。Pre-flight 表已改口径；阶段三写计划前统一修订计划文 + 颜色 glob 口径（M6-3/G-4）。✅(b3a6a95) 已兑现，实际修订范围：:203→10、:500→15、:726 判据升格为"零 failed + 记实数"并补 127→128→129/2/1 链；Task 6 Step 3 第四条颜色命令替换为 G-4 唯一口径（旧式 `grep -rEoh ... src/styles/*.css` 恒返 17——把 variables.css 本体算进去了，17/11 双度量废弃）；`sendChat\b`→`sendChat(`；另订正"全局约束·CSS 纪律"的 11 处豁免与"前端没有测试框架"两句的时效、Task 5 Step 4 与 Task 6 Step 3 两处 `sendChat\b`、文末"阶段三候选"四项交付注记（修订一律以 `> 2026-10-03 阶段三修订` 引用块留痕，不抹原文）。

### 终审遗留（阶段三入口项/记档）
- ✅(9160196) 前端无测试运行器，SSE 客户端契约仅靠 git-ignored 探针背书——阶段三若动 useChat 需先落 in-repo 回归（终审 Out-of-Scope ①）。→ vitest+jsdom+@vue/test-utils 落地，33 条：client 六出口/useChat 状态机/ChatInput 双态，变异抽检钉活。
- ✅(afa9158) M-b StorageError 分支生产不可达 → 随 M2-7 在 `save_chat_history` 包裹收口；✅(ec65329) M-e 50 项上界不防超长整数溢出 String(500)（计划级缺口，加 ge/digit 界）；✅(e1a3034) M-g **拆两半处置**：`X-Accel-Buffering: no` 已随头断言落地（顺带闭 M2-3 Cache-Control 无断言），**心跳帧按裁定不做**——只在网关有 idle 超时时才有意义，为不存在的环境加复杂度违反 YAGNI，代码注释已记此由；✅(5d8d15f) M-j 422 英文 msg 进中文 UI → 前端唯一文案出口 `detailFromText` 冠"请求参数不合法："引导句、英文原文照抄在后（后端契约与 curl 消费者不动；翻译会漂、丢弃等于藏 bug）；✅(5bf4bd2) mode 判定三处复制 → `schemas.chat.mode_of()` 收成唯一判据（非流/流式按 mode 分支，历史行沿用）；✅(547a79f) 断流证明链自动化为 @pytest.mark.live 脚本测试（终审建议 3）；✅(822437b) 停止生成按钮**不可盲用 removeTurn**——done 前已落库窗口期撤泡会显示丢失已持久化轮次，停止后应重取历史（建议 2，重要设计告诫。→ 已按 handleStop=abort+restore 重拉落地）。
- 数据面：修复波零落库（探针全 stub fetch）；`-m migration` 只读校验。

### 分支终态
HEAD=19981a9；后端默认门 127 passed/1 deselected + migration 显式 1 passed；前端 build exit 0；工作区干净。模型说明沿用：全部派发继承会话模型。

## 阶段三收尾（2026-10-03）：入口项清零 + 桌面宽屏回归实跑

清单来源：阶段二 Task 5 视口 542 deviation 欠下的"宽屏没实跑过"这笔账。工具链：Edge headless
（`puppeteer-core` 走 `--no-save`）+ vite :5173 + **复用现存 uvicorn :8000**（不新起第二实例，1455 红线不触），
长历史会话 `feec926f-6ddb-44a3-9025-4543faa63ceb`。八判据 × 三档全 PASS，**零代码缺陷**：

| 判据 | 1280×800 | 1920×1080 | 1024×768 |
|---|---|---|---|
| `.app-shell` 行模板已中和（单行有界） | 768px | 1048px | 736px |
| `.chat-messages` 有界滚动 client/scroll | 538/14491 | 818/14491 | 506/17950 |
| 滚到底（scrollTop+client ≥ scroll−2px） | ✓ | ✓ | ✓ |
| 页面不滚（scrollY / scrollingElement 高） | 0 / 800 | 0 / 1080 | 0 / 768 |
| 无横向溢出（scrollWidth−innerWidth） | 0 | 0 | 0 |
| 历史恢复：`.message` 数 == `GET /api/history` 长度 | 12 == 12 | 12 == 12 | 12 == 12 |
| 侧栏常驻 / toggle 隐藏（rect 宽） | 320 / 0 | 320 / 0 | 320 / 0 |
| 发送键在视口内 bottom、前景色 token 生效 | 772≤800、rgb(255,255,255) | 1052≤1080 | 740≤768 |

交互与移动端复验（同一探针，1280×800 / 375×800）：
- 新会话 `02307b8c…` 发一条：pending 期只有"⏹ 停止生成"且 textarea 禁用；error 帧到 → 横幅"⚠️ 大模型调用失败，请稍后重试"+关闭按钮、停止键消失、气泡撤到只剩空态占位（`.message` 计 1 = MessageList 的"暂无消息"占位，不是残留半截），`GET /api/history` 该会话 **0 行**——"宁可不写"守住了。
- 文档卡勾选可逆：点一次 `.doc-card-checked` = 1，再点 = 0。
- 375×800 不回归：toggle 在 top 10 可见，点开 `.panel-open` 浮层 560px 全在视口（top 56 / bottom 616），`.chat-main` 行高 743 未被压，msgs 513 有界，scrollY 恒 0。
- 探针坑（记给下一次）：`toggle.click()` 后必须等两帧再量——Vue 未重渲染 + `display:none` 的 rect 全零，首版量到 panelH=0 是假阴性。

**证据边界（别夸大）**：`X-Accel-Buffering: no` 目前只有 TestClient 断言。现存 :8000 实例跑的是本批改动前的代码且无 --reload，
活服务复验要等它自然重启；本轮不新起实例（[[env-second-uvicorn-1455]]）。同理，配额未充值前逐字流的观感无法实跑，只有帧序断言背书。

**阶段三终态**：候选与终审遗留入口项**全部处置完毕**（13 项交付：822437b / 547a79f / ec65329 / 9160196 / 51e7ca7 / 5e1c9de / 52ec28c / b3a6a95 / 5bf4bd2 / afa9158 / e1a3034 / 5d8d15f + 本节的宽屏回归实跑）。
其中 M-g 的**心跳帧按裁定不做**（无网关即无 idle 超时，为不存在的环境加复杂度）。其余各 Task 行里的 `minor (deferred)`
（M2-1~M2-6、M2-8、M6-1、M6-2 等）仍是 parked 账，不在阶段三清单，动它们要单独立项。
门禁基线：后端默认 `pytest -q` **138 passed / 2 skipped / 1 deselected**（+ `-m migration` 显式 1 passed）；
前端 `npm test` **37 passed**；`npm run build` exit 0；颜色字面量口径判据 0 命中；四条静态把关退出码全 1。
