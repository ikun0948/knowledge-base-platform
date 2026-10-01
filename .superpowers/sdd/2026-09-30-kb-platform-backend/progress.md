# SDD ledger — plan: docs/superpowers/plans/2026-09-30-kb-platform-backend.md
spec: docs/superpowers/specs/2026-09-30-kb-platform-frontend-backend-split-design.md
branch: feat/backend-split (created from master @ 7849e66; baseline of pre-refactor code = 3e28870)
workspace: .superpowers/sdd/2026-09-30-kb-platform-backend/

## Setup rulings

Ruling: 在原目录新建 feature 分支 `feat/backend-split`，**不用 git worktree 隔离** — 本计划的验证步骤依赖绝对路径（`backend/.env`、`backend/data/chroma_db`、`D:\python\python.exe` 全局解释器、`D:/AI-python/.env` 共用配置），worktree 里 `.env` 与 Chroma 数据是 gitignored 的，复制过去等于每次重新造基线 — 代价：分支与主目录共享文件，若用户此刻手动跑 Streamlit 会看到中间态文件；缓解：计划走"复制不改原文件"策略，根目录 `app.py`/`core/`/`config/` 全程不动。

Ruling: 模型选择不可用（本会话 Agent 工具无 `model` 参数）— 所有子代理继承会话模型，不做分层选型 — 代价：机械转写型任务无法降到更便宜的档位。

## Pre-flight scan（任务间共享文件/接口）

| Task 对 | 共享物 | 发现 | 裁定 |
|---|---|---|---|
| T1 ↔ T3/T4/T5/T6/T7 | `backend/core/*.py`（T1 复制进来，后续各自 Modify） | T1 复制的是**未修版本**（含坑 1、吞异常、Streamlit 签名）。各 Task 的 Modify 段落都以"当前文件内容"为前提写增量代码，顺序 1→3→4→5→6→7 与计划的 Task 编号一致 | 无需改动。派单时明确告知 implementer：只改自己 Task 列出的文件，其它 Task 的补丁不存在，不要顺手改 |
| T3 ↔ T7 ↔ T8 | `backend/main.py`（T3 建、T7 挂 documents router、T8 挂 chat/history router） | 同一文件三次修改，T7/T8 都用 `app.include_router(...)` 追加 | 无需改动。派单时提醒：不要重写 create_app，只追加一行 include_router |
| T3 ↔ T5 | `backend/core/vector_store.py`（T3 加集合名常量 + `collection_counts()`，T5 加 `delete_by_ids` + 改 print） | 两处不同方法，无签名冲突 | 无需改动 |
| T3 ↔ T6 ↔ T7 | `backend/core/database.py`（T3 加 `count_documents()` + 修坑 1；T6 加 `get_filenames_by_ids`/`delete_chat_history`；T7 加 `get_document`/`delete_document`） | 纯追加，且 T7 的 Files 段确实列了 `get_document`（早前自检补过的缺陷） | 无需改动 |
| T3 ↔ T7 ↔ T8 | `backend/tests/fakes.py`（T3 建）+ `RecordingDB`（T7 自建局部类） | T7 测试自带 `RecordingDB`，不改 fakes.py；`FakeVectorStore.delete_by_ids` 在 T3 已定义并记录调用，T7 断言 `store.deleted == (["p0"],["c0"])` 依赖它 | 派 T3 时须确认 fakes 里 `delete_by_ids` 把入参记到 `self.deleted`，T7 才能直接复用 |
| T6 ↔ T7 | `Reference` 形状（T6 定义，T7 上传响应用） | T6 的 `_build_references` 与 T7 的文档列表来自不同源，但 T7 不用 Reference | 无需改动 |
| T9 ↔ 全部 | `python -m pytest tests` 默认收集 live 测试 | `pytest.ini` 只注册 marker，**没有** `addopts = -m "not live"`；而 T9 的 Produces 声称"无 MySQL 环境下自动跳过" | 裁定：live 测试用连接探测 + `pytest.skip` 实现自动跳过（不引入 addopts，避免"跑全量却静默漏掉 live"）；同时保留 `-m "not live"` 与 `-m live` 两条显式命令 |
| T2 ↔ T10 | `backend/data/`、`legacy_streamlit/core` | 均为 gitignored / 复制产物，提交内容只有测试与 README | 无需改动 |
| T1 ↔ 全局 | 提交清单 `git add ... .gitignore` | `.gitignore` 已在基线里且本 Task 不改它，`git add` 是无害 no-op | 无需改动 |

扫描结论：无阻塞冲突，两处需在派单时携带提示（fakes 的 `delete_by_ids` 记录、T9 自动跳过语义）。

Ruling: 会话无法 resume 已完成的子代理（Agent 工具无 resume/model 参数），因此修复轮次一律派**全新 implementer + 完整修复说明**，不依赖原实现者的记忆 — 代价：修复者需要重读 brief 才能对齐既有写法。

## Task 1 循环记录

- implementer DONE_WITH_CONCERNS @ `533e78c`（偏差：把 `backend/api/__init__.py`、`backend/schemas/__init__.py` 一并提交，评审认定正确且必要）
- reviewer: 代码本身 Approved 级（复制字节一致、12 键契约、.env 按文件位置定位、绝对路径守卫实测有效），但 **Task quality: Needs fixes** — Important 1 条：`test_config.py` 两个测试对其 docstring 声称的行为是**惰性的**（`monkeypatch.chdir` 时模块已导入、`Path(Config.CHROMA_PERSIST_DIR).is_absolute()` 与守卫是同一表达式，删掉守卫测试仍绿）
- Ruling: 这是计划自带测试代码的缺陷，与 spec 无冲突（spec 7.1 只要求"配置来源与 cwd 无关"，实现已满足），改测试不改生产代码 → 修复轮 1。同时带上两条零风险 Minor（`_chroma` 泄漏进类命名空间；键完全缺失时报错文案指向"必须绝对路径"而非"键缺失"）。`load_dotenv` 不加 `override=True` **保持原状**（与 legacy 一致，且属有意取舍）。
- 已知后续影响：`backend/core/database.py` 导入时会发 `MovedIn20Warning`（verbatim 复制，本计划不改），Task 3 起 pytest 输出会带这一行——不是回归。

## Task 进度

Task 1: complete — commits `533e78c` (impl) + `4b0f750` (fix round 1) — review: Needs fixes → re-review round 1 "All findings addressed, no new Critical/Important breakage"
  遗留 3 条 Minor（已备案，交最终评审复看）：
  - `test_config.py:66` 严格解包 3 行 stdout，未来 import 期任何额外输出会变成 ValueError 而非断言失败
  - `_child_env` 只剥 `CHROMA_PERSIST_DIR`，临时树 `.env` 的控制力弱于其 docstring 暗示
  - `test_config.py:72-77` 依赖 gitignored 的 `backend/.env` 存在，新克隆未跑 Step 6 会红（有意的 CI 依赖）
  另有：无测试**正向**断言 `CHROMA_PERSIST_DIR` 绝对（改为由 import 期守卫兜住）；`conftest.py` 的 `sys.path.insert(0, backend)` 与根 `config/` 存在遮蔽风险 → Task 3+ 注意。

## Relocation ruling (2026-10-01)

Ruling: 工程整体迁移到独立目录 `D:\知识库平台-前后端分离`（backend/ + frontend/ 两个文件夹），基线提交 `9224c69`。本 ledger 与 `docs/` 下的 spec、计划均以新路径为准；`backend/.env` 的 `CHROMA_PERSIST_DIR=D:/知识库平台-前后端分离/backend/data/chroma_db`。原项目 `D:\AI-python\知识库平台` 从此**只读**，充当 legacy Streamlit 档案（随时 `streamlit run app.py` 对照），不再往里提交任何东西。迁移校验：新位置 `python -m pytest tests` 8/8 通过。共用资源不变：解释器 `D:\python\python.exe` (3.12.3)、`D:/AI-python/.env` 只作键值来源不再被读取。

Task 2: complete (原仓库 commits `d72a054`..`e80f758`，含 fix round 1；迁移后于新位置复跑 pytest 8/8 复验)

Ruling (2026-10-01 修订): 新会话 Agent 工具虽有 `model` 参数，但本机无法枚举合法模型档位，盲传 ID 有派单失败风险 — 继续全部子代理继承会话模型 — 代价：机械转写型任务无法降档省钱。

Task 3 implementer 预检（派 T9 时必须携带）：计划约 1710 行让 Task 9 "Create" 只含 `live` marker 的 pytest.ini，会丢掉现有 `migration` marker — 裁定：T9 改为**合并**（保留 migration + live 两个 marker），不得整文件重建。

Task 3: complete (commits `50ba699`..`2f058ea`，review: Approved / Spec ✅，偏差 conftest.py +3 行经评审裁定成立)
Task 3: minor (deferred): 异常映射与兜底 handler 无测试钉住（建议后续补一个 UnsupportedDocumentType→415 用例）
Task 3: minor (deferred): 报告 §6.3 关于 TestClient 兜底 500 的说法不准确（raise_server_exceptions=True 会再抛），**派 T8 时携带**：断言兜底 500 需 `TestClient(app, raise_server_exceptions=False)`
Task 3: minor (deferred): conftest TESTS_DIR 插在 sys.path[0]（今天无遮蔽，未来非 test_ 模块同名会顶掉真模块）
Task 3: minor (deferred): lifespan 无 teardown，--reload 每次泄漏连接池
Task 3: minor (deferred): collection_counts 注解 `-> dict`（计划自身不一致，非实现缺陷）
Task 3: minor (deferred): fakes 预支 T4/T5 签名（load_document(filename, raw_bytes) / delete_by_ids），**派 T4/T5 时携带**：参数名必须与 fakes.py 一致，否则测试绿而真接口断

Task 4: complete (commits `c25f3c4`..`d850d72`，review: Approved / Spec ✅；`partial(TextLoader, encoding="utf-8")` 偏差经评审独立复现裁定成立——legacy 本就钉 UTF-8，spec 迁移等价性**要求**保留该钉法)
Task 4: minor (deferred): Interfaces 行 `-> list[Document]` 未落实，`Document` 成死导入（plan-mandated 二选一，Follow Step 3）
Task 4: minor (deferred): 写临时文件本身失败时不 unlink（delete=False 在 try 外）；Task 7 传真 bytes，可达面仅调用方 bug
Task 4: minor (deferred): 空 .txt 静默切出 0 块无异常——**派 T7 时携带**：端点需决定是否 400
Task 4: minor (deferred): 大写后缀 `.TXT` 现在能过（legacy 拒绝）——行为超集，记入等价清单
Task 4: minor (deferred): `loader_cls` 对 txt 实为 partial 工厂，名不副实
Task 4: minor (deferred): SUPPORTED_SUFFIXES 与 LOADER_BY_SUFFIX 键双真相（plan-mandated）——**派 T7 时携带**：import 复用而非再抄

Task 5 预检（派 T6 时携带）：T5 implementer 实测 brief "print 全转完" 说法与树不符——现存 5 处 live print：`core/database.py:106,108`（无主）与 `core/rag_system.py:67,87,114`（brief 划归 T6）。T6 派单需明确 rag_system 3 处的归属，并裁定 database 2 处（默认：保持原状，非本计划清单）。

Task 5: review Approved 但 1 条 Important [plan-mandated]：`test_delete_with_empty_lists_touches_nothing` 的 StubCollection 只记 ids 不记调用，删掉 `if parent_ids:` 守卫测试仍绿。Ruling: 修测试不修生产码（守卫本身正确在位）——StubCollection 加 `self.calls` 计数并断言空列表时 0 次调用；这是对 brief 逐字测试块的一处授权偏离，不改生产签名，T7/T8 断言面不受影响 → 修复轮 1/5。
Task 5: ruling(归属): `core/database.py:106,108` 两处无主 print 划归 **Task 9** 转 module logger（spec 八节"6 处 print"含它们在；不转则 §8 清零验收在 T9/T10 静默失败）。派 T9 时携带。

Task 5: complete (commits `6a64e1e`..`0f2e2e0`，impl `d0f24df` + fix round 1/5 `0f2e2e0`；复核：All findings addressed, no new breakage，复核者并独立验证子守卫变异也红)
Task 5: minor (deferred): 路由测试只断 deleted 未断 calls==1（已被守卫结构蕴含）
Task 5: minor (deferred): `delete_by_ids` 无失败信号（delete 返回 None 不校验命中数）——**派 T7/T8 回滚编排时携带**：别把它当成"已验证删除"

Task 6: complete (commits `e884cef`..`dec7c10`，review: Approved / Spec ✅ 零 Critical/Important；Step 7 探针偏离被评审加码确认——brief 探针依赖尚未存在的 POST /api/documents，且会破坏 migration 基线)
Task 6: minor (deferred): rag 历史窗口 [-5:]/[-3:] 与消息顺序无断言（ok_llm 丢输入）——**派 T8 时携带**：端点依赖该顺序
Task 6: minor (deferred): get_filenames_by_ids 无调用次数锁（N+1 靠自觉）
Task 6: minor (deferred): 两个新 DB 方法真实 SQL 零自动覆盖，delete_chat_history 至今无调用方——**T9 建议补 live 测试或提交探针脚本**
Task 6: minor (deferred, plan-mandated): _build_references 用 d.metadata["document_id"] 直接取键，坏数据会在成功生成后 KeyError→500 且丢历史
Task 6: minor (deferred, plan-mandated): snippet 实为 SNIPPET_LIMIT+3（"..." 在切片后追加）——**派 T8/前端时携带**，前端按 83 或自适应省略号处理
Task 6: minor (deferred): 领域异常把原始 exc 文本透进 detail（泄露内部信息）——归 T9 注入面回归范围，派 T9 时携带

Task 7: review Approved；1 条 plan bug 坐实（brief 的回滚断言与 fakes append 语义不可兼容，测试侧修法经评审独立确认）+ 2 条 Important [plan-mandated]：
  (A) 补偿调用无守卫（delete_by_ids 抛则行不删；delete_document 抛则幽灵状态且裸异常逃逸）——Ruling: spec 坑 3 的原话就是"500 必须可信地表示整件事没发生"，补偿自身裸奔直接违背该目标，且修法被限制在 api/documents.py:49-51 三行范围内 → **进修复轮 1/5**：每步补偿各自 try/记日志，最终仍抛 StorageError。
  (B) add_documents 半途失败（父集合已写、子集合失败）时 ids 仍为 []，补偿删不到已写父向量——Ruling: 真缺陷但修复需要 store 侧渐进式 id API（计划未预留该表面，spec 十二节本就有"入库任务化"遗留项），**parked（deferred, real）**：交最终评审与用户决定是否单开任务。

Task 7: minor (deferred): MAX_UPLOAD_BYTES 注释言过其实（Starlette 解析期已落盘/进内存，守卫只约束管线留存）；且 20MB > MEDIUMTEXT 16MiB 上限，17-20MB txt 会以裸 500 出场——改读 file.size 或收小常量
Task 7: minor (deferred): 201 响应体未证明来自 DB（RecordingDB 返回值与请求字面量同值）——给 stub 返回可区分值即可钉死
Task 7: minor (deferred): 补偿顺序（先向量后行）无测试钉——修复合入时看能否顺带钉住
Task 7: minor (deferred): 端点 basename 清洗无提交测试且与 document_processor 重复（Windows 反斜杠只在一侧处理）——**归 T9 注入面回归**
Task 7: minor (deferred): get_document 返回 None 会在提交成功后 AttributeError→500
Task 7: parked (deferred, real): 图片型 PDF（零块非空）以 500 出场而非 422/201，spec 6.1 未覆盖此形态——最终评审/用户定夺

Task 7: complete (commits `bb71106`..`cdc0b70`，impl `67cc454` + fix round 1/5 `cdc0b70`；复核：All findings addressed, no new Critical/Important；brief 断言与 fakes 不兼容的 plan bug 修法获独立确认)
Task 7: minor (deferred): 双补偿同败时 detail 仍说「已回滚」（裁定保持原消息，真相在日志）；候选改法：rollback_ok 旗标或改文案——交最终评审定夺
Task 7: minor (deferred): 缺"两步同时失败"合并用例（逻辑已被两个分立用例蕴含）

Task 8: review 结论 Approved / Spec ✅，但 1 条 Important [plan-mandated]：`api/chat.py` 两处 `except KnowledgeBaseError` 过宽——StorageError 也在其下，未来聊天链抛 StorageError 会被就地改写成 502，劫持 main.py STATUS_BY_ERROR 的中央映射（该映射注释明示"别在函数里临场决定"）。且变异测试显示整个 try/except 删掉仍绿（中央 handler 同样产出 502+str(exc)），即冗余+未被钉死。
Task 8: ruling: 采评审给的修法一——两处 except 收窄为 `(RetrievalError, LLMError)`，保留 logger.warning 与"失败不写历史"注释（零 wire 变化，不删日志）；补一个端点级注入测试：FakeRAG 抛 StorageError → 响应 500（经中央映射），钉死"聊天端点不吞其他领域错误"。brief 逐字代码与此冲突，以 spec 六节错误语义单一真相为准 → **进修复轮 1/5**。

Task 8: review 通过项备案：response_model 走 ChatResponse 的裁定 1 成立（wire 形状被 test_reference_serializes_to_exactly_the_spec_fields + live 钉死）；main.py 严格 append-only（+2 import +2 include_router）；migration 基线未污染（TestClient 非上下文管理器）。
Task 8: minor (deferred): `schemas/chat.py` 的 `mode: str` 未用 `Literal["rag","normal"]`——schema 边界不拒脏值，仅靠两条断言兜底。
Task 8: minor (deferred, **前端计划必携带**): history 的 user 消息 wire 上是 `references: null`（brief DTO 与测试都钉了 null，spec 6.1 未言明）——前端 MessageList 必须 `msg.references ?? []`，直接 `.length` 会在 user 行抛错。
Task 8: minor (deferred): 422 detail 双形态（chat=FastAPI 数组、documents=字符串）——归 T9/T10 统一裁定，非本任务引入。
Task 8: minor (deferred): "502 失败不写历史"靠构造保证（端点无 get_db、rag_system 在 save 前 raise）+ live 证据，无自动测试钉——T9 注入面回归可顺带在 rag_system 层补一条。

前端计划（另一份计划，spec 十一节第 6-7 步）：`docs/superpowers/plans/2026-09-30-kb-platform-frontend.md` 已写完并提交 `cf66d7a`（2086 行，7 Task / 58 步，起草代理为分段增量写盘重派版）。起草代理留下的 5 处「以后端 Task 8 实现为准」悬置标注已随 Task 8 落地全部改写为实测事实（chat 收窄后的错误接管面、history user 行 references:null 且 restore 已 `?? []` 归一）。待用户审阅后才开前端 SDD 执行。

Task 8: complete (commits `bbbbd43`..`912a88d`，impl `6ee5adc` + fix round 1/5 `912a88d`；复核：All findings addressed, no new breakage。复核者独立确认：detail 断言可区分中央 handler 与兜底 500、FakeRAG 双方法注入、StorageError 在 core/ 零抛出点、无基线污染)
Task 8: minor (residual, ruling-inherent): 收窄后的两处 try/except 唯一独占行为只剩 logger.warning，删整块仍绿（中央映射同样 502+str(exc)）——是裁定选择保留日志，非回归。
Task 8: minor (carried→T9): rag_system 在域错误包装之外直接调 get/save_chat_history（rag_system.py:44,56,77），MySQL 故障落兜底 500 且答案丢失——归 T9 注入面范围一并裁定。

Task 9: 派单 BASE `2ccc952`，brief 115 行。随派单结转的裁定：(1) pytest.ini 已存在且双 marker 齐——MERGE 不 Create；(2) database.py:106,108 print→logger 归本任务；(3) detail 泄露（中央 handler str(exc)）由实施者择最小改法或如实裁定可接受；(4) 文件名清洗回归测试补 api 层；(5) mode→Literal 收编；(6) live 组须自清理、跑两遍不破 migration 基线。裁定：rag_system 历史调用不被域错误包装（T8 复核结转）OUT OF SCOPE，留最终评审。

Task 10 预裁定（派单时携带）：brief Step 2 的"从本仓根 cp app.py/config/core/.streamlit 进 legacy_streamlit/"不成立——迁移后本仓根从未有过这些文件（原件在 D:/AI-python/知识库平台，且 2026-10-01 迁移裁定已确立**原目录即活体归档**，只读不改）。Ruling: Step 2 取消（再做物理拷贝=第三份真相，违 spec 7.2"最多两份"精神）；改为 legacy_streamlit/README.md 做**指路碑**（指向 D:/AI-python/知识库平台 的活体归档 + 坑 1/2/3/6 修复状态），Step 3 文档指针照做（其"坑已修复"行正是本任务该留的痕），Step 4 提交物相应为 README + 开发文档两处。若用户终审时希望物理冻结副本入库，可单独补一次 cp——不做也不损失任何 spec 判据。

Task 9: complete (commits `2ccc952`..`becf535`，review: Approved / Spec ✅ 零 Critical/Important，一次过无修复轮。评审者独立复核：全异常面 str(exc)→detail 路径枚举、posix 非空转探针、live 组不触 Chroma、migration 基线不可漂移）
Task 9: ruling: 8 条 Minor 不进修复轮（均测试加固/既有健壮性）；其中值得终评后一并处理的：#1 posix 模拟可静默空转（fixture 内补一句 assert documents_api.os.path is posixpath）、#4 >255 字符文件名在回滚 try 之外撞 String(255)→兜底 500（预存在，非泄露）、#6 live 测试红时探针行残留、#7 live skip 捕 Exception 过宽会掩真回归。归**最终评审后的单次修复 dispatch**候选清单。
