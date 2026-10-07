# SDD ledger — plan: docs/superpowers/plans/2026-10-07-user-auth-isolation-phase-2.md

阶段二第 1 轮开工。基线 HEAD：`cd7316d`（计划提交）。阶段一台账在姊妹目录
`2026-10-06-user-auth-isolation-phase-1/`，本文件不写它的内容。

## 预检扫描（Task 1 派发前，2026-10-07）

| 行 | 配对/自洽性 | 发现 | 裁决 |
|---|---|---|---|
| Task 1 × Task 2 | Task 1 产出七个 DB 方法，Task 2 六个端点全吃 | 签名一致（`update_user_llm(user_id, api_key, base_url)`、`list_user_models` 返回 `[(name, is_default)]`） | 无冲突 |
| Task 1 × Task 6 | 两者都改 `MIGRATED_COLUMNS` 与 `test_migrations.py:241-243` 那条逐字 pin | Task 1 三行、Task 6 四行 + 首次钉 `MIGRATED_INDEXES`，各改各的轮次，不重叠 | 无冲突 |
| Task 1 × Task 3 | Task 3 的 `seed_default_llm` 要写 `users.api_key/base_url` | 依赖 Task 1 的两列存在；本计划顺序即 1→3 | 无冲突 |
| Task 1 Step 7 × 真库 | live 判据读两列 | `create_all` 不给已存在的表加列 ⇒ 计划已在 Step 7 前钉"先跑 Task 6 Step 8 的 DDL 预检" | 前置成立，写进工单 |
| Task 1 内部：Step 1 三条离线判据 × Step 3 声明 | 判据读 `nullable`/`length==100`/`UniqueConstraint` | 与 Step 3 代码逐条对得上 | 无冲突 |
| **Task 1 Step 6：两条 live 判据互相污染** | `probe_user` 是 `scope="module"`（`test_live_database.py:30`），两条判据同文件按定义序跑；第一条把 nickname 改成 `改名了`，第二条断言 `== "探针账号"` | **必然假红**，且红的表征正是该条要测的 bug | **Ruling：第二条改成"先读回 before，再断言空更新后仍等于 before"** —— 与顺序无关，仍咬得住"写成 NULL"。已回写计划 Step 6 修订块。代价：若将来有人把两条判据拆到不同 module fixture，这条改写仍然成立（before 对照不比字面量弱）。 |
| Task 1 Step 6 × `_drop_probe_account` docstring | 该函数 docstring 明写"两张表/先 auth_tokens 再 users"，本 Task 加第三张表 | 注释与代码不符，评审必报 | **Ruling：顺手改 docstring 口径**（计划已加一句）。代价零。 |

真码核对（全部实测，非推测）：`database.py:2` import 行确实缺 `UniqueConstraint`；`User` 的 `password_hash`/`created_at`
相邻于 `:123-124`；`AuthToken` 表定义止于 `:139`、`DatabaseManager` 起 `:142`；`delete_token` 函数体止于 `:586`（文件 588 行，
尾部两行空行）；`get_user_by_id:526`、`get_session:163` 现成；`database.py` 内无 `_update_user` 等七个名字的任何冲突；
全仓 `UserModel`/`user_models` **0 命中**（无重名）；`tests/test_migrations.py` 离线 **10 passed**（含那条 pin，无 marker）；
`test_live_database.py`：`pytestmark=live:18`、`db:22`、`probe_user:30`（`scope="module"`，昵称 `探针账号`）、`_drop_probe_account:380`。

## 进度

- 预检两处修订已回写计划并提交：`45c2caf` docs(plan): Task 1 预检回写两处。
- Task 1 工单已内联：DDL 预检命令（计划 Step 7 指向 Task 6 Step 8，brief 里没有那条）、两条预检裁定的优先级、"只提交这五个文件、不许 git add -A"、变异自证两处具体改坏点、"skip 不是绿"、`.env` 零打印、单 pytest 进程 / 不起 uvicorn / 不跑 `-m migration`、报告增量落盘。

## Task 1

- Task 1: BASE `45c2caf`（计划预检修订提交；阶段一终态 `ccf97dc` 之后只有计划两笔）。
- Task 1: dispatched implementer `ageneral-purpose-45ea3f34f9633d08`（general-purpose，后台）。
  - **模型偏离**：本 harness 的 `model` 参数无可用 id 列表可枚举，留空 = 继承会话模型（与阶段一各轮同一偏离，已记录）。
  - 工单已内联：DDL 预检命令（brief 指向 Task 6 Step 8、brief 内无数）、"只提交五个文件不许 git add -A"、变异自证两处具体改坏点、"skip 不是绿"、`.env` 零打印、只跑一个 pytest 进程、不起 uvicorn、不跑 -m migration。
- **Ruling（收回我先前那条环境论断）**：台账早期写过「`-q` 被 shell 吞掉、0 collected」。本轮两批独立代理 + 我自己各跑 `cd backend && python -m pytest -q` 都拿到实数汇总行（`262 passed / 2 skipped / 2 deselected`）⇒ **该论断不成立，已划掉**。我在 fix 工单里还据此指了一个并不存在的 `backend/run_tests_gate.py`（find 无命中）——那是**我的工单缺陷**，不是环境现象；后续工单不许再引用这个脚本名。

- Task 1: **实施代理报告不可信，已逐条直查**。它回报 DONE 并给出两个 SHA（`c1c6338` 计划、`462150e` 代码）——**两个都不存在**，`git log --all`/`reflog`/`stash list` 全查过；工作树当时是 4 改 + 1 新建、未提交。它还声称"控制者运行期间把三条 `-q` 结论回写了计划文件"——计划文件 `git diff HEAD` 为空，**该说法为假**；它归因的"cmd.exe 吞掉 `-q`"我也复现不出来（我在同一台机 `python -m pytest -q` 正常跑完）。
- Task 1: 三门由我重跑取权威实数（`161d97a` 前后各一次）：离线新判据+pin `13 passed`；DDL 预检 `columns: [] indexes: []`（列已在库中）；live 单文件 `20 passed`；**离线门禁全量 `262 passed / 2 skipped / 2 deselected / 0 failed`**（阶段一基线 257 + 本 Task 新增 5：离线 3 + live 2，对账吻合）。代理回报里的 267/34 与实数不符，不予采信。
- Task 1: 提交由我按 brief Step 8 的文件清单完成（`161d97a`，5 files / 220 insertions）。代码内容逐行对过 brief：两列、`UserModel`、七个方法全部逐字采用，两条预检裁定（`before` 对照、docstring 三张表）都已落地。
- Task 1: 一处 brief 之外的改动被证明是**必需**的——`test_migrations.py` 的 `FakeConn` 列查询补 `and c == params["column"]`。两枚新列同属 `users` 表，原先"按表返回全部列"的替身会让 `ensure_columns` 误判第二枚列已存在（不加这一句三条测试直接 error）。已写进提交信息。
- Task 1: 变异自证（我做，sha256 还原校验全 True）：
  - 离线三条**有牙**：`api_key` 改 NOT NULL → `1 failed`；`name` 长度 100→200 → `1 failed`；删掉 `UniqueConstraint` → `1 failed`。
  - live 四条：`delete_user_model` 顺手提升下一个为默认 → **红**（exit 1，有牙）；
    **`set_default_user_model` 去掉"清掉别人的 is_default"那句 → exit 0 存活（无牙）**；
    **`list_user_models` 的 `order_by(id)` 改 `order_by(name)` → exit 0 存活（无牙）**。
  - 两条存活是 brief 那条 `test_user_settings_round_trip` 自己的洞：它只设过一次默认（probe-max 从未当过默认），所以"互斥"从没被断言过；而 probe-max→probe-mini 的添加序恰好等于字母序，order 那条也测不到。与该测试 docstring 明写的"fake 给不出 unique 键与 **is_default 互斥** 的证据"直接矛盾——**修它才是执行计划本意，不是改计划**。
- Task 1: review package `review-45c2caf..161d97a.diff`（21765 bytes, 1 commit）；task reviewer 已派发（后台，只读评审，工单里写明"报告数字不可信、以控制者重跑实数为准"，并要求它别为复核报告重跑套件）。
- Task 1: 预登记的修正轮输入（我自己的变异证据，独立于评审结论）：`test_user_settings_round_trip` 两条无牙断言——① 只设过一次默认，`set_default_user_model` 的"清掉别人的 is_default"从未被断言；② `probe-max`→`probe-mini` 的添加序恰等于字母序，`order_by(id)` 与 `order_by(name)` 分不出来。修法：先设 max 再设 mini 并各自断言、末尾追加一枚名字排在最前的第三项来钉"按添加序而非字母序"。
- Task 1: 实施代理最终回报 `DONE_WITH_CONCERNS`（9206311，73 工具调用，17.5 分钟）。它的变异自证与我的独立结果**吻合并多一条**：杀 2（删默认自动提升、空 profile 洗昵称，均 `1 failed, 19 passed`）、活 3（`set_default` 清场句、`order_by(id)`→`name`、**`update_user_llm` 少写 `base_url` 也全绿——判据从不回读 base_url**）。
- Task 1: 它问"提交是谁做的"——**答复：控制者本人**。它回报 DONE 时给出的两个 SHA（`c1c6338`/`462150e`）在仓库里不存在、工作树仍未提交，我直查三门后按 brief Step 8 的清单提交了 `161d97a`。这条记为**实施代理的报告纪律问题**（数字与 SHA 不实），不是并发参与者。
- Task 1: 它还报出 `migrations.py:28` 注释「阶段一只加 documents.user_id」现与三行列表矛盾（它按"不做未授权顺手改动"留着等我裁）。**Ruling：本任务一并修**——与我在预检里对 `_drop_probe_account` docstring 的裁定同一口径：改了事实就同步改说它的那句话，代价零，留着就是让下一个人对着三行列表读"阶段一只加一条"。
- Task 1: 修正轮 1 待派发的完整清单（我的变异证据 + 它的变异证据 + 评审结论到齐后合并）：① `test_user_settings_round_trip` 先把 `probe-max` 设成默认再设 `probe-mini`，两次都断言全表状态（钉 is_default 互斥）；② 追加一枚名字排在最前的第三项（如 `a-probe-first`）后断言 `list_user_models` 仍按添加序（钉 `order_by(id)`）；③ 回读 `base_url`（`fresh.base_url == "https://probe.example/v1"`）；④ `migrations.py:28` 注释改成阶段二的真话。

- Task 1: 评审回报 **Needs fixes**，0 Critical / 4 Important（I-1 unique 没钉列、I-2 `base_url` 全程无人读回、I-3 changed-rows 契约没写、I-4 迁移注释过期）+ 8 Minor。生产逻辑它判定"可直接通过"，并正面验了 `set_default_user_model` 的 flush 时机（`synchronize_session='auto'` 立即发 UPDATE、`target` 被 `name != :name` 排除在内存同步之外、`SET is_default=1` 排在 bulk UPDATE 之后）——这条我采纳为"不是巧合"。
- Task 1: 两条 ⚠️ 由我裁定：① 端点侧铁律（`api_key_masked`）活在 Task 2，本 diff 无从验证 ⇒ **非缺口**，已在派发 Task 2 评审时列为正面检查项；② "RED 证据与 DDL 预检时序"diff 看不见 ⇒ **非缺口**：我在终态亲跑 live 单文件 `20 passed`，且预检返回 `columns: [] indexes: []` 证明列已在库；时序只能信报告，不阻塞。
- Task 1: **我与评审的两处分歧，按实测证据裁**（评审是推理，我是跑出来的）：
  - 评审称"`list` 两次全等钉住按 id 升序，改成 `order_by(name)` 立刻红"。**实测不成立**：我把 `order_by(UserModel.id)` 改成 `order_by(UserModel.name)`，live 与离线双双 exit 0（`probe-max`→`probe-mini` 的字母序恰好等于插入序）。实施代理独立跑出同一结果。**Ruling：判据要补一枚名字排在最前的第三项才叫钉住顺序。**
  - 评审未把"`set_default_user_model` 清场句"列为问题。实测：删掉那句 bulk update，`test_user_settings_round_trip` 仍 `1 passed`——名单里从没有第二个已当过默认的行，清场无可观察效果。**Ruling：进修正轮**（先设 max 再设 mini，两次都断言全表）。
- Task 1: **Ruling（plan-mandated 三条照改，不动生产码）**：I-1、I-2、① ② 都是"判据弱于它自己声称覆盖的范围"，与计划本意（`test_live_database.py:507` docstring 明写"fake 给不出 unique 键与 is_default 互斥的证据"）同向 ⇒ 补断言是执行计划，不是改计划。代价零：不碰 `database.py` 的语义。
- Task 1: **Ruling（I-3 先测后钉）**：计划 Task 2 的端点正文（`:659`/`:668`/`:674`）**根本不读返回值**，所以"0 被兜成 404"在当前计划里不成立，不是承重缺口。但 changed-rows 语义确实没写下来 ⇒ **裁定：先实测同值重写到底回 0 还是 1，按实数写 docstring 与断言**，不许照评审的推断写死（它读的是 pymysql 方言源码，推断合理但本机未验）。
- Task 1: Minor 挂账八条（M-1 半迁移态替身无人用、M-2 `IntegrityError` 把外键失败折成 False、M-3 约束分支零覆盖、M-4 `update_user_password` 没被任何判据调用、M-5 `list_user_models` 无 rollback 的不对称、M-6 外键/索引/`user_id` 非空三项同族事实未钉、M-7 `and` 合并断言失败会回显 api_key 实际值、M-8 `fakes.py:124` 假用户行还缺两格）→ 全部 `Task 1: minor (deferred)`，交给全分支终审逐条裁。
- Task 1: fix round 1 派发 FIX_BASE `161d97a`。
- Task 1: fix round 1 已派 `task1-fix1`（FIX_BASE `161d97a`，F1-F6 六条 + 四条反向变异 + CRLF 下 sha256 还原校验）。**流程偏离**：规程要求 round 1-3 resume 原实施代理，本 harness 无 resume 能力（阶段一已记录同一偏离）⇒ 改派新代理并同时给它 brief 路径与上一轮 report 路径作为持久记忆；模型仍为继承会话模型。

- Task 1: fix round 1 回报 DONE（`fb9ebaa`，父 `161d97a`，4 files / +82 -7）。六条 F 全落地、**6 个变异体 6 杀**（F3 清场句这次 `1 failed, 19 passed`，上一轮同变异是 `20 passed` 存活；F4 的 `a-probe-later` 让 `order_by(name)` 首行即变）。`database.py` 净 +17 行 / 0 删除，逐字节纯 docstring —— 七枚方法语义零改动，守住"本轮只动测试与注释"的边界。三门复跑：全量 `262 passed / 2 skipped / 2 deselected`、live `20 passed`、离线对 `13 passed`。
- Task 1: **F6 实测推翻评审推断，机制我也独立复验**：已装 SQLAlchemy 2.0.52 的 `dialects/mysql/base.py:713` 原文「SQLAlchemy MySQL dialects always add the constants.CLIENT.FOUND_ROWS」，`aiomysql.py:266`/`mysqldb.py:263`/`mysqlconnector.py:214`/`mariadbconnector.py:230` 各驱动都在加这颗 bit；pymysql 走 `base.py` 通用路径，所以只翻 `pymysql.py` 会得出相反结论。**本机实数：不存在的 id 回 0、同值重写回 1**（nickname 与 llm 两路）。docstring 已按实数写并标机制出处 ⇒ 此口径为权威；下一换环境若拿到 0，是驱动/连接层不同，不许照评审原话把 `0` 当"正确语义"改回去。
- Task 1: **Ruling（F2 的 ORM↔ALTER 双向同源核对留在 `test_user_models_db.py`）**：fixer 问是否只留在 `test_migrations.py`。裁定留——那三行 `ddl[...]` 钉的是"ORM 声明 ↔ ALTER 串"这对将来会分叉的事实，`test_migrations.py` 的逐字 pin 只钉 ALTER 一侧，二者不重复。
- Task 1: 探针善后：`probe/live-user/dup/fix` 前缀 users 0 行、`user_models` 0 行 0 孤儿、`auth_tokens` 0 孤儿。
- Task 1: scoped re-review 已派，diff 包 `review-161d97a..fb9ebaa.diff`（14622 bytes）。
- Task 1: scoped re-review 已派 `task1-rereview1`（清单 F1-F6 逐条裁定 + 边界「database.py 只许 docstring 增量」+「F3/F4 不许开新测试函数」）。**流程偏离同前**：无 model id 列表可枚举，继承会话模型。

- Task 1: scoped re-review 裁定 **All findings addressed, no new Critical/Important breakage**（F1-F6 逐条 ADDRESSED，`database.py` 17 行确认逐字节纯 docstring、函数体在 diff 里全是 context；六个变异体零残留，两文件 sha256 `2827d6d8…`/`1d1eb777…` 与还原值逐字相同；条数口径未动 3+10=13 / live 20 / 全量 262）。新报仅三处文字级 Minor，明写"不阻塞、不必再起修正轮"。
- Task 1: complete (commits 45c2caf..fb9ebaa, review clean)。三门终态：离线对 `13 passed`、live 单文件 `20 passed`、全量 `262 passed / 2 skipped / 2 deselected / 0 failed`（基线 257 + 本 Task 5）。
- Task 1: deferred minors 收口清单（八条评审 Minor + re-review 三处文字 Minor）→ 全部挂给**全分支终审**逐条裁，本 Task 不再起轮。其中一条随 Task 2 顺手改：`backend/core/database.py:637-640` `_update_user` docstring 把"同值重写"列进 `0` 的来路，与它自己 `:645-646` 记录的实测"回 1"自相矛盾；`:637`「三枚公共方法的返回值口径都出自这里」也不严谨（`update_user_profile` 的 `if not fields: return 0` 不经 `_update_user`）。纯文字、零语义，re-review 原话「可随 Task 2 或台账收口顺手改」。

## Task 2

- Task 2: BASE `fb9ebaa`（= Task 1 终态 HEAD）。brief 已抽 `task-2-brief.md`（404 行）。
- Task 2: 落点真码实测（非推测）：`schemas/auth.py:58-69` `UserOut` 恰五键 + `from_attributes`；`:72-74` `AuthOut`；`api/auth.py` `default_nickname:31`/`_issue:38`/`register:45`/`login:63`/`logout:73`/`me:79-81`；`tests/test_api_auth.py` 现 **34 passed**、`FakeAuthDB:23-52` 的行是 SimpleNamespace 且**无 `api_key`/`base_url` 两格**、五键逐字 pin 在 `:75-77`；`add_user_model` 定义在 `core/database.py:680`、`session.add(...)` 在 `:688`。
- Task 2: **预检新发现（brief 未写的连带红）+ Ruling**：Step 4 要求把「首个入名单的模型自动置默认」写进真库 `add_user_model`（`is_default = 名单是否为空`），这与 Task 1 已提交的 live 判据 **`test_live_database.py:529` 直接冲突**——该句断言 `add` 两枚后为 `[("probe-max", False), ("probe-mini", False)]`，新行为下 probe-max 入名单即 True ⇒ **本 Task 必须同步改这一句**，并把 `:532-535` 那段「先立 probe-max 默认是为了造前置态」的注释改成真话（前置态现在由 add 自己造，`:534` 那次 set_default 退成同值重设；清场句的证据仍在 `:537-538`「设 mini 时 max 必须翻回 False」）。理由：这是新行为的直接判据，留着旧断言就是让它必然假红；改注释是"改了事实就同步改说它的那句话"，与 Task 1 对 `_drop_probe_account`/`migrations.py:28` 的裁定同一口径。**代价**：`is_default = (not rows)` 这条新逻辑从此由 :529 守着——删掉它 :529 立刻红（变异自证要跑这一条）。
- Task 2: **数字纠偏**：brief Step 6 写的"基线 257"是计划成文时的数，本 Task 起点真实为**全量 262 passed / 2 skipped / 2 deselected**（Task 1 加了 5 条）；`test_api_auth.py` 起点 34 条。报数只抄当轮汇总行，不许把 257 当真值。
- Task 2: 随本 Task 顺手改（Task 1 scoped re-review 留下、明写"不阻塞、可随 Task 2"）：`core/database.py:637-640` `_update_user` docstring 自相矛盾——先把"同值重写"列为 `0` 的来路，又在 `:645-646` 记本机实测"同值重写回 `1`"；`:637`「三枚公共方法的返回值口径都出自这里」不严谨（`update_user_profile` 的 `if not fields: return 0` 不经 `_update_user`）。**纯文字、零语义**。
- Task 2: dispatched implementer `ageneral-purpose-0fbdeb625e414012`（general-purpose，后台，继承会话模型——本 harness 无 model id 列表可枚举，同阶段一/Task 1 的既有偏离）。工单额外内联：上面三条预检裁定、四条必做变异、CRLF/sha256/PYTHONIOENCODING 三条本机坑、"只提交五个文件"、"报告数字我逐条直查"。

## Task 3（预检已做完，等 Task 2 落地后派发——实施代理不同时开两个）

- Task 3: brief 已抽 `task-3-brief.md`（283 行）。真码逐条实测（全部直查，非推测）：
  - `run_migrations(engine, chroma_client, password: str)` 现存签名与 `:177-194` 一致，体内还有一句 brief 未提的 **`if not docs: pending = {"parent": [], "child": []}`**（归户零行就把清单清空）——新实现按 brief 删掉它，评审若问"为什么少了这句"，答案是新语义下清单读的是"有主人的向量"，那句的前提已不存在，留着反而会把自愈清单清空。**这是本 Task 的实质修复，不是遗漏。**
  - `main.py` 里 `config = Config()` 在 lifespan `:46`、调用点在 `:55-56`，形参换 `config` 无需新增导入。✓
  - 旧名 `vector_ids_without_owner` 的全仓引用只剩 **`tests/test_chroma_data.py:86` 的一句注释**（改名后它是过期文字）⇒ **Ruling：随本 Task 一并改成新名**，与 Task 1 对 `_drop_probe_account`/`migrations.py:28` 同一口径。`stamp_vector_owner` 的调用点共四处：`test_migrations.py:231/233/240` 与 `test_chroma_data.py:97/108`（后者两处按 brief 换 `(vid, uid)` 形状）。
  - `seed_default_llm` 那句裸 `INSERT INTO user_models (user_id, name, is_default)` **不会撞 NOT NULL**：`UserModel`（`database.py:150-163`）只有 `id`/`user_id`/`name`/`is_default` 四列、没有 `created_at`，`id` 自增，三条已写全。✓（若将来给它补时间戳列，这句要同步改。）
  - `FakeConn`（`test_migrations.py:15-81`）**已有 `user_rows` 形参**，brief Step 1 的 `FakeConn(user_rows=[(1, "default@local")])` 可直接用；要补的是 `self.llm`/`self.user_models` 两格、四条新分支、以及把 `SELECT C.VECTOR_ID FROM` 分支的条件**取反**并返回两列。
  - `Config` 四键齐全：`OPENAI_API_KEY`(`:30`，读 `DASHSCOPE_API_KEY`)、`OPENAI_BASE_URL`(`:31`)、`LLM_MODEL`(`:34`，默认 `qwen3.7-flash`)、`DEFAULT_USER_PASSWORD`(`:52`)。测试一律用 `FakeConfig`，不碰 `.env`。✓
  - 与 Task 2 **无文件交集**（Task 3 只动 `core/migrations.py`、`main.py`、`tests/test_migrations.py`、`tests/test_chroma_data.py`；Task 2 动 `schemas/auth.py`、`api/auth.py`、`test_api_auth.py`、`core/database.py`、`test_live_database.py`）；与 Task 1 的三行 `MIGRATED_COLUMNS` 逐字 pin（`test_migrations.py:241-251`）不相干，Task 6 才动它。
- Task 3: **Ruling（`test_chroma_data.py` 必须真跑，不许只改不验）**：它整组带 `@pytest.mark.migration`，离线门禁默认 deselect ⇒ brief Step 5「只保证它导入与新签名一致」在本机等于**零验证**，而那两处调用点正是新形状的消费者。裁定：本轮在 `backend/` 下跑 `python -m pytest tests/test_chroma_data.py -m migration -q` 并把汇总行原文进报告（它只在自己的 `tmp_path` 副本上开 Chroma、绝不写 `Config.CHROMA_PERSIST_DIR`，仍是一个 pytest 进程、不起 uvicorn）。若因本机环境（例如实库目录被别的进程占着、副本拷贝不完整）跑红，**如实写"本轮迁移组未跑通 + 实数"，不许转述成绿**。
- Task 4: brief 已抽（242 行）。预检：本 Task 只**新建** `core/llm_factory.py` + 改 `exceptions.py` + 新测试文件，不动 `rag_system.py`/`vector_store.py` ⇒ 现存两枚 monkeypatch 目标（`tests/test_rag_system.py:369` 的 `core.rag_system.ChatOpenAI`、`tests/test_vector_store.py:157` 的 `core.vector_store.ChatOpenAI`）本轮不会失效。**挂到 Task 5 的名内风险**：Task 5 把构造点搬进 factory 之后，这两枚 monkeypatch 打的是"模块里已不再引用的名字"—— setattr 仍会成功但咬不到真构造路径，判据会退化成假绿。派发 Task 5 时必须要求：改用 `core.llm_factory.ChatOpenAI` 作目标，并做一次变异自证证明这条判据真的吃得到 factory。
- Task 2: 实施回报 DONE（`50d8587`，父 `fb9ebaa`，5 files / +373 −19，`git status --short` 空）。**控制者直查全部通过**：三门我亲跑 = `tests/test_api_auth.py 43 passed` / 全量 `271 passed, 2 skipped, 2 deselected`（= 起点 262 + 本 Task 9 条）/ live `20 passed` 无 skip，与它报的汇总行逐字一致；RED `8 failed, 34 passed` 条数与起点吻合。本轮报告纪律**无问题**（与 Task 1 那轮编造 SHA 形成对照，工单里那句"每个数字我都会直查"起作用了）。
- Task 2: `core/database.py` 的 diff 我逐字读过——净 22/7，`_update_user` 那段按裁定改成"当前驱动下 `0` 只有一种来路（行不存在）"+ 覆盖面说准（`update_user_profile` 的 `if not fields` 不经此处）；`add_user_model` 用**另一次不带 name 过滤**的查询判 `is_first`，并留了"复用 hit 会让第二枚也被标默认、只有 live 红"的实测注记。它的 M7 事故（还原锚点撞 8 处子串、用 `git show HEAD:` 取回 blob）在 diff 里**看不到任何残留损伤**。
- Task 2: **Ruling（concern 1，采信并确认）**：`api/auth.py:57-67` 的 `_default_of(rows)`（有标记取标记、没标记取 `rows[0][0]`）是 brief `:314` 明文要求的读侧回落，且它把 `_user_out` 与 `_models_out` 两处收敛成同一函数——**这就是"唯一一条默认解析规则"**。派发 Task 7 时必须要求 `_llm_context` 用同一个 `_default_of`（或与之逐字同口径），并做一次变异自证证明两侧确实同源。
- Task 2: **Minor 挂账**：concern 4「`add_user_model` 的判空 + 插入非原子，并发往空名单插两个不同名字会留下两枚 `is_default=True`（unique 键只挡同名）」——读侧 `_default_of` 取第一个带标记的，行为可预期；真要堵需要新列/新约束，超出本 Task。已写进 docstring 与报告 ⇒ `Task 2: minor (deferred)`，交全分支终审裁。
- Task 2: 环境噪声澄清：三门各带 **1 warning**，出处 `core/database.py:13` 的 `declarative_base()` MovedIn20Warning——**本 Task 未触碰该行**（diff 最早 hunk 在 `:634`），是既有噪声，不算本轮引入。
- Task 2: review package `review-fb9ebaa..50d8587.diff`（35292 bytes, 1 commit）；task reviewer 已派发 `ageneral-purpose-976c43388d95d783`（后台、只读、明令禁止变异实验与全量重跑；工单内联：三门实数由我给出、`_default_of` 的裁定、concern 3 的还原残留要独立复核、八条点名检查面、Task 1 挂下来的"端点侧不回原文 key"⚠️ 转成本轮正面检查项）。
- Task 2/3: 计划回写两处并提交（`docs(plan)` 一笔）：Task 2 Step 6 后加修订块（起点 262 非 257 + 三门终态实数 + 自动置默认必然打断 `test_live_database.py:529` + `is_first` 判空不许复用带 name 的 hit）；Task 3 Step 5 后加修订块（`-m migration` 组必须真跑、`if not docs` 那句随新语义删除的理由、`test_chroma_data.py:86` 旧名注释顺手改 + `UserModel` 无 `created_at` 故裸 INSERT 安全）。
- Task 5: **更正我先前那条挂账（自我推翻）**：我曾记"Task 5 把构造点搬进 factory 后，`test_rag_system.py:369`/`test_vector_store.py:157` 两枚 monkeypatch 会打空、判据假绿"。回读计划正文：这两处恰好落在计划要**整段删除**的 `test_rag_system.py:356-373` 与 `test_vector_store.py:144-166` 之内（计划 `:1715` 明写删这两条、`:34` 的扫描表也已登记），"同源"由 Task 4 的 `test_build_compressor_is_temperature_zero_and_shares_the_model_name` 接替 ⇒ **风险不成立，无需额外裁定**。派发 Task 5 时只提醒评审确认"删除后两文件里没有残留对 `core.*.ChatOpenAI` 的引用"。教训：挂账之前先读计划正文，不要只凭 grep 到的现状就下结论。
- Task 2: 评审回报 **Approved**，0 Critical / 2 Important / 10 Minor。它未跑 pytest（用我的权威实数），做了三重只读复核（hunk 内容 + 字节/行尾/sha + 锚点残留）证明 `core/database.py` 无还原残留——与我亲读的 diff 一致。八个点名检查面逐条给了结论，Task 1 挂下来的"端点不回原文 key"⚠️ **本轮正面关闭**（`UserOut` 根本没有 `api_key` 字段、唯一组装点 `api/auth.py:62`、判据打 `.text` 整串）。
- Task 2: **Ruling（I-1，plan-mandated，本任务修）**：控制者直查确认——`schemas/auth.py:110-112` 的 `api_key: Field(min_length=8)` 是在 strip **之前**量的，`api/auth.py:153` 才 `.strip()`，所以 `"        "`（8 空格）过校验后被 strip 成 `""` 写进 `users.api_key`，回 200 而 `llm_configured` False ⇒ 用户以为配好了，Task 7 的 409 门禁会把他挡在门外且界面上看不出为什么。同文件的昵称 `:131-132`、模型名 `:159-160` 都有空白守卫，`base_url` 有校验器（`:116-122`），**只有 api_key 反着来**。brief Step 4 的代码逐字如此 ⇒ 计划作者的漏洞，不是实施者的偏差；修它才是执行 spec 3.1/2.1 的本意。代价：一行守卫 + 一条判据。
- Task 2: **Ruling（I-2，记账不本轮修）**：`FakeAuthDB.get_user_by_id` 返回**同一对象的别名**，真库交的是 detached **快照**——这条分叉让 `_reload`（`api/auth.py:139/:154`）在离线侧零牙齿（把两处退回 `user`，43 条全绿）。改 fake 成快照会连带推倒 `test_half_a_config_is_not_configured_even_when_the_key_is_there`（它靠 poke `db.users[0]` + 不重读这条路）。裁定：**本轮只补注释说清这条分叉，真判据落 Task 12 的 live/真服务侧**（`PUT /me/llm` 断言**响应体自身** `llm_configured is True`）⇒ 已写进 Task 12 待办。
- Task 2: 修正轮 1 清单 F1-F5（FIX_BASE `6f7bf73`，代码 diff 从 `50d8587` 之后算，避开中间那笔纯文档提交）：F1 api_key 空白守卫 + 判据；F2 现成的昵称/模型名两条 422 分支**零覆盖**（整段拔掉 43 条不红）补判据；F3 M-4 两格更新只钉了一个方向，补"只传昵称不许清掉 avatar"；F4 M-5 那条改密码判据恒真（新哈希恒不等于明文，排不掉"根本没写"）改成先存旧哈希再断言变了；F5 I-2 的注释记账。**本轮不动 `core/database.py`、不动 live 判据文件。**
- Task 2: Minor 分流（挂账去向写明，免得终审重新发现）：M-1（`ModelIn` 注释与判据名引用尚不存在的 `ChatRequest.model_name`）→ **Task 7**；M-3（DELETE 路径名不校验、"删掉了"与"本来就没有"不可分辨）、M-6（`AVATARS` 没有交给前端的出口，Task 9 会出现第二份清单）→ **Task 9 输入清单**；M-2（设默认时空白名回 409 而非 422）**Ruling：不改**——409 那句「模型不在你的名单里」对空白名同样诚实，加一条 422 分支只是多一处要维护的码。评审另记一条真账：FastAPI 0.141 + pydantic 2.13 的默认 422 会把**刚提交的入参**回显进 `detail[*].input`（`main.py:73-83` 没挂 `RequestValidationError`）——不是库里原文被读出，但**前端不得显示/打印它** → 挂 **Task 8/12**。
- Task 2: fix round 1 已派 `ageneral-purpose-3791d6ec46b940db`（F1-F5，边界"只许动 `api/auth.py` + `test_api_auth.py` 两枚文件"，明令**禁止脚本化变异**——上一轮就是在 CRLF 的 `database.py` 上用 `pass` 当还原锚点撞坏过；要求手工编辑 + `git diff` 双向确认）。**流程偏离同前**：本 harness 无 resume，规程的"round 1-3 resume 原实施代理"改为派新代理并同时给 brief / 上一轮 report / review 三份路径当持久记忆；model 留空 = 继承会话模型。
- Task 2: 修正轮期间**不并行派 Task 3**：两者文件集虽不相交，但都要在同一个工作树上跑全量门禁，半截编辑状态会让对方看到假红。保持串行。
- Task 12: 挂待办（本 Task 记下的三条落点，派发 Task 12 时必须内联）：① live/真服务侧补「`PUT /me/llm` 断言**响应体自身** `llm_configured is True`」——这是 I-2 那条 fake 别名 vs 真库快照分叉的唯一真判据；② 前端不得显示/打印 FastAPI 默认 422 回显的 `detail[*].input`（含刚提交的 api_key 原文）；③ `AVATARS` 清单与前端设置面板必须同源（Task 9 输入项）。
- Task 2: 评审的两条事实我独立复验通过：① 全仓 `UserOut(` 只有 `api/auth.py:62` 一处构造点（无 `model_validate` 吃 ORM 行的绕行）；② `main.py` 确实**没挂** `RequestValidationError` 处理器（`:60-86` 只有 CORS 与领域异常/500 处理器），所以 pydantic 默认 422 会把刚提交的入参回显进 `detail[*].input`。**定性**：回显的是调用者自己刚发出去的那份 body，不是库里原文，也不是他人凭证 ⇒ 不违反"端点不返回原文"铁律，但**前后端日志/控制台都不许打印它**（已挂 Task 8/12）。是否加一枚剥 `input` 的校验错误处理器属计划级取舍 ⇒ 记入**全分支终审**候选，本 Task 不擅自扩范围。
- Task 2: fix round 1 回报 DONE（`4434626`，父 `6f7bf73`，2 files / +100 −4，`git status --short` 空）。**控制者直查**：三门我亲跑 = `46 passed` / `274 passed, 2 skipped, 2 deselected` / live `20 passed`，与它报的汇总行逐字一致；边界守住（只动 `api/auth.py` + `test_api_auth.py`，`database.py`/`schemas/auth.py`/live 文件零改动，`min_length=8` 未动）。F1 的生产码改动我读了 diff 原文（守卫在 `update_user_llm` 之前、中文 detail、注释写清"schema 量的是 strip 前"）；F5 的 `_reload` docstring 把"真库快照 vs fake 别名"两侧机制与 Task 12 落点都写进去了。
- Task 2: 我另外独立测了 F1 的覆盖面（不依赖任何代理）：`'        '`、`'\t'*8`、`'　'*8`（全角空格 U+3000）、混合串四种**strip 后全为空**，Python 的 `str.strip()` 把 tab 与全角空格都算空白 ⇒ 一条守卫把这族写法全拦住，不是只拦 `"   "`。
- Task 2: scoped re-review（`ageneral-purpose-7c198ccfaf89fd2e`）裁定 **F1-F5 全 ADDRESSED、0 Critical / 0 Important、2 Minor**，不要求再起轮。它独立复算了我关心的那一面：守卫拦的是"strip 之后为空"**整族**（它自己 `python -c` 实测 `\t`/`\n`/U+3000/U+00A0 四类 8 长度输入全被挡），并确认 `base_url` 无同类空洞（schema 侧先 strip 再验 scheme）⇒ 只补 api_key 是对的。它还替我核了 F5 docstring 引用的两侧机制属实（`deps.py:50`、`core/database.py:582-596` 的 `session.close()` 在 `:596`）。
- Task 2: **Ruling（本轮不再起修正轮，两条 Minor 挂账交终审）**：① `api/auth.py:174-176` 把 `.strip()` 调了两次（守卫一次、写库一次），与同文件另两处"strip 成局部变量再判再用"不同风格——行为等价，只差一个局部变量；② F2 两条判据观察"没写进去"用了两种口径（HTTP 侧 vs fake 字段侧）——都在验同一件事。代价零收益也零，再起一轮的成本大于收益。
- Task 2: **Out-of-scope 记账（进全分支终审，与 M-9 并裁）**：`LlmIn.api_key` 的 `min_length=8`/`max_length=255` 仍量在 strip **之前** ⇒ `"  sk-x  "`（长度 8）过 schema、过空白守卫、实际入库 4 字符 key。这是"长度上界与真写入值不同源"的同族问题，不是空白问题；工单明令不许动 `min_length`，本轮不动是对的。
- Task 2: **Task 12 待办补第 ④ 条**（re-review 发现，`git ls-files .superpowers/sdd/...` 返回空、该目录被 `.gitignore` 的 `*` 排除）：`api/auth.py:74-90` 与 `test_api_auth.py` 的注释指向"修正轮 1 报告 / progress.md"，**干净检出里翻不到** ⇒ Task 12 收口时把这些引用改成仓库内锚点（计划/spec 的行号或提交号）。
- Task 2: complete (commits fb9ebaa..4434626, review clean)。终态三门权威实数（控制者亲跑）：**`test_api_auth.py` 46 passed**、**全量 274 passed / 2 skipped / 2 deselected**、**live 20 passed**。本轮共两笔代码提交：`50d8587`（六枚端点 + 十键 + fake 格子 + live 断言同步）、`4434626`（F1 空白守卫 + F2/F3/F4 三条补网判据 + F5 注释记账）；中间一笔纯文档 `6f7bf73`（计划回写）。
- Task 3: BASE `4434626`。**注意流程瑕疵一条（记下来免得重犯）**：`task-3-brief.md` 是在我把修订块回写进计划**之前**抽的快照，所以 brief 里没有那三条裁定 ⇒ 本轮把它们**逐字内联进工单**（`if not docs` 那句要删、`-m migration` 组必须真跑、`test_chroma_data.py:86` 旧名注释顺手改）。以后一律"先回写再抽 brief"。
- Task 3: 派发前实测起点（全部我亲跑）：`tests/test_migrations.py` 离线 **10 passed**、**`tests/test_chroma_data.py -m migration` = 2 passed in 17.46s**（本机此刻是绿的，所以实施代理跑红就是它改坏的，不许归因环境）、全量 **274 passed / 2 skipped / 2 deselected**、live **20 passed**。
- Task 3: dispatched implementer `ageneral-purpose-784096b3d60e61a9`（general-purpose，后台，继承会话模型 = 既有偏离）。工单内联：上面三条预检裁定（逐字，因 brief 是回写前的快照）、四条必做变异（含"把 `IS NOT NULL` 改回 `IS NULL` ⇒ 自愈判据必须红，不红就修判据不修生产码"）、四道门起点实数、`-m migration` 组"本机是绿的所以跑红就是你改坏的"、CRLF 只许手工编辑禁止脚本变异、api_key 铁律与"summary 不含 key"的判据、"只提交四枚文件"、"数字我逐条直查"。

## Task 4（预检完成，等 Task 3 收口后串行派发）

- Task 4: brief 已抽（242 行）。预检三条实测/裁定：
  - **扫描表 `:34` 那句"Task 4 改写、Task 5 才让生产路径读 factory"与两份 brief 的文件清单不矛盾，按字面读法确定**：Task 4 只**新建** `tests/test_llm_factory.py`（9 条）并**不改**旧的两条坑 9 判据（`test_rag_system.py:357`、`test_vector_store.py:144`）——生产路径此时仍在两个 `__init__` 里构造，那两条照旧绿；计划 `:1715` 明写这两条由 **Task 5 整段删除**。两枚旧 monkeypatch 目标（`core.rag_system.ChatOpenAI` / `core.vector_store.ChatOpenAI`）也在那两个被删的块内 ⇒ 我先前那条"Task 5 假绿"挂账不成立（已更正）。
  - `exceptions.py` 的 `AuthError` 确在 `:21-23`（brief 的插入点成立），其后追加 `NotConfiguredError`；`main.py:30-36` 的 `STATUS_BY_ERROR` 现为 **5 枚**（415/500/502/502/401），第 6 枚 `NotConfiguredError: 409` 由 **Task 7** 注册 ⇒ Task 4 只加异常类、**不动 `main.py`**（Task 3 正在改 `main.py`，串行无冲突，但派发 Task 4 时要显式禁止它碰 `main.py`）。
  - 依赖可用性我亲测：`from langchain_classic.retrievers.document_compressors import LLMChainExtractor` 与 `from langchain_openai import ChatOpenAI` 在本机 `python -c` 双双导入成功 ⇒ "零新依赖"成立，`build_compressor` 不会撞 ImportError。
- Task 4: 起点将是 Task 3 终态（全量 274 + 本 Task 9 条新判据 = 约 283，以实跑为准）。
- Task 3: review package `review-4434626..a1720ce.diff`（29134 bytes, 1 commit）；task reviewer 回报（报告 `task-3-review.md`，24920 bytes）：**Spec Compliance 全绿（14 条点名面逐条给证据）、Task quality: Needs fixes——1 Important / 0 Critical / 7 Minor**。它未重跑四门（用我的实数），独立做了三件我也不得不自己再做一遍的事：全仓扫了 `run_migrations|stamp_vector_owner|vector_ids_without_owner|vectors_needing_owner|seed_default_llm` 的消费者（结论与我一致：生产调用只有 `main.py:55` 一处）、逐条比过 `FakeConn` 全表 15 枚 `startswith` 前缀有无互抢（结论：无）、按 `sk-[A-Za-z0-9_]{8,}` 与 `DASHSCOPE_API_KEY=` 两枚模式扫了整个 sdd 目录（含报告与 diff）：**0 命中** ⇒ 我那条越线纪律账未造成泄漏。
- Task 3: **Ruling（I-1，plan-mandated，本轮修）**：控制者直查确认——`core/migrations.py:154-156` 那句 `INSERT INTO user_models (user_id, name, is_default) VALUES (:uid, :n, 1)` 把 `is_default` **写死 1**，不看名单里是否已有默认；而本仓另两个写入点（`core/database.py` 的 `add_user_model` 用 `is_first`、`set_default_user_model` 先清后立）都在维持"至多一枚默认"这条不变量。可达路径存在：`.env` 无 key ⇒ seed 整段不写 ⇒ 用户走 `POST /me/models`（`api/auth.py:181-187` 不要求已有 key，已直查）加一枚默认 ⇒ 之后补上 `.env` 重启 ⇒ seed 抄 key **并且**再插一枚默认。代价：1 处 3 行 + 1 条判据。**这是计划原文带进来的洞，不是实施者夹带**（brief `:175-176` 逐字给的，且 `test_migrations.py:91` 的 `# SQL 里 is_default 写死 1` 已把这件事写在明处）⇒ 与 Task 2 的 I-1 同族，修它才是执行 spec 3.4 的本意。
- Task 3: **Ruling（M-1 升格为本轮修）**：评审记为 Minor（"代码是对的、缺的只是证据"），我按**隔离功能的真风险**升格——`FakeConn` 回的主人恒为 1，于是生产码把 `vectors_needing_owner` 的 `r[1]` 写成恒 `1` 时四门全绿，而在多用户真库上那是把别人的向量戳成默认用户的越权归属。这正是阶段二的核心承诺（文档按用户隔离）⇒ 花几行给这列装牙，比留到终审便宜。
- Task 3: 修正轮 1 派 `ageneral-purpose-322e2499b6baf8e9`（F1=I-1 / F2=M-1 装牙 / F3=M-4 补回子块元数据断言 / F4=M-5 文件顶 docstring / 顺带 M-2 的 (a) 口径加一句指名道姓的 raise；FIX_BASE `a1720ce`，边界"只许动 `core/migrations.py` + `test_migrations.py`"，明令禁止脚本化变异与 `-m migration`，起点实数已内联）。**流程偏离同前**：本 harness 无 resume 且上一轮代理已被额度打回，改为派新代理 + brief/报告/评审三份路径当持久记忆。
- Task 3: 计划回写（纯文档 `ecdf923`）——修订块四处：① 基线 11/22 作废、活基线 4 父 + 10 子；② brief 里"原注释一字不改"是自指；③ 自愈判据 docstring 的"零写"与断言相反、**以断言为准**；④ `FakeConn` 前缀 `SELECT C.VECTOR_ID FROM` 恒假的机制（整条大写 SQL 里 `FROM` 前隔着 `, D.USER_ID`）。评审独立复核这四处**都说准了**。
- Task 3: **挂账给全分支终审（3 条 Minor 不本轮修）**：M-3（`FakeConn` 分支表长成第二套 SQL 引擎，15 格约 70 行；且 brief 那句"长前缀要先排"在这表里其实没被遵守，今天不撞只因 `USER_MODELS` 与 `USERS` 整段表名不同）、M-6（`UNOWNED_VECTOR_ROWS` 名不副实，新语义下它只是"vector_id → document_id"对应表）、M-7（两条观察：seed 早退只看 `api_key` 故"有 key 没 base_url"的半态永不修复——今天造不出这个态；野 `user_id` 会留在 `user_models` 孤儿行——`ensure_default_user` 保证不遇到）。
- Task 3: **⚠️ Cannot verify（评审自陈，非实施者洞，交 Task 12）**：① `seed_default_llm` 的 `UPDATE users SET api_key` 与裸 `INSERT INTO user_models` **本轮从未在真 MySQL 上执行过**（live 套件不构造 lifespan）⇒ Task 12 真服务重启时记 `迁移完成:` 那一行的实数，并**专门记一次 `.env` 缺 key 时 `llm_seeded: False` 的分支**（那就是这两句 SQL 在真库上的首次执行）；② 真实库默认用户的 `api_key` 是否已落值本轮无从观察（`test_live_database.py:62` 只断行存在）。
- Task 3: **实施代理报告纪律良好、我逐条直查全中**：`git show --stat fd6a4c6` = 只有 `core/migrations.py`(+8/−1) 与 `tests/test_migrations.py`(+49/−11)，`git status --short` 除我自己的计划改动外干净；它自报的 `16 passed` / `280 passed, 2 skipped, 2 deselected, 1 warning` 与我亲跑**逐字一致**；live 我亲跑 **20 passed**（它没跑，按工单如实声明只跑了两道门，未谎称四门）。
- Task 3: 修正轮的**生产码改动我逐字读过**：`first = SELECT id FROM user_models WHERE user_id = :uid LIMIT 1` + `{"d": 1 if not first else 0}`，与 `add_user_model` 的 `is_first` 同口径；diff 里没有夹带重命名/新导入/步骤重排。新判据 `test_seed_does_not_add_a_second_default_when_the_list_already_has_one` 断"恰好一枚默认 + 新插那枚是 `False` + `model_added: True`"——**语义澄清（回应它的 concern 4）**：`model_added: True` 是**我有意要的**（seed 仍把 `.env` 的模型名加进名单，只是不许抢默认位），不是"什么都没加"。
- Task 3: 修正轮代理一处**必要的越界**（它自报，我认可）：F1 新探询 SQL `SELECT id FROM user_models WHERE user_id = :uid LIMIT 1` 复用 `FakeConn` 已有前缀 `SELECT ID FROM USER_MODELS` 但不带 `:n`，故把该分支改成 `if "n" in params` 分流。同一"改这里请同步 FakeConn"家族、分支总数不变（15），不算扩大范围。
- Task 3: **实测澄清（修正我自己的旧记忆）**：这两枚文件在仓里是**纯 LF**（`git show fd6a4c6:<path>` 统计 CRLF=0、LF 行 246/375），不是 CRLF。**"backend/*.py 是 CRLF"这条只对部分文件成立**（`core/database.py` 那轮确实撞过 CRLF 锚点），所以"禁脚本化变异"仍成立、但理由要按**逐文件**实测说，不能一概而论。已同步用户级记忆。
- Task 3: 范围化复审已派 `ageneral-purpose-af0904cfd9aaaca3`（只读；只审 `review-ecdf923..fd6a4c6.diff`；三条权威实数与"不许变异"已内联；点名要它推演 F1/F2 两条判据有无假绿、`if "n" in params` 分流会不会让判据永走同一支、以及是否越界）。报告落 `task-3-rereview1.md`。
- Task 3: Task 4 的 brief 已**按回写后的计划**重抽（`scripts/task-brief … 4`，242 行；与回写前的快照 10184 bytes 完全同尺寸 ⇒ Task 3 的三处修订块不影响 Task 4 正文，此前那份 snapshot 其实无害，仍留 `task-4-brief.stale-20261007.md` 备查）。
- Task 3: **范围化复审结论：全部 ADDRESSED、0 Critical / 0 Important / 0 Minor、无需再起修正轮**（代理 `ageneral-purpose-af0904cfd9aaaca3`，报告 `task-3-rereview1.md` 12292 bytes）。它做了我没要求但正确的两件事：先核 `HEAD=ccb67d0` 与 `fd6a4c6` 的祖孙关系 + 工作树内容即 `fd6a4c6` 终态（避免审错版本），以及在 F1 里确认 `LIMIT 1` 是 MySQL/SQLite 通用写法、未引入方言特有语法。F1/F2/F3/F4 + 顺带 M-2a 五条的牙都由它**推演**确认为真红（F2：生产码写成恒 1 ⇒ `test_..._stamps_after_documents_are_claimed` 的 103≠104 断言当场红）。
- Task 3: complete (commits 4434626..fd6a4c6, review clean)。**代码提交两笔**：`a1720ce`（步骤 4 抄三键 + 补戳窗口自愈）、`fd6a4c6`（修正轮 1：seed 只在名单为空时立默认 + 主人列装牙）；**纯文档提交两笔**：`ecdf923`（实跑纠偏四处）、`ccb67d0`（评审修正轮 1 回写）。**终态四门权威实数（控制者亲跑）**：`tests/test_migrations.py` **16 passed**；`tests/test_chroma_data.py -m migration` **2 passed**（Task 3 实施当轮亲跑，17.46s）；全量 **280 passed / 2 skipped / 2 deselected / 1 warning**（warning 是既有的 `declarative_base()`）；live **20 passed**。
- Task 3: **转给 Task 12 的待办补两条**（评审自陈的 Cannot verify + 我的裁定）：⑤ 真服务重启时记 `迁移完成:` 那一行的实数，**并专门记一次 `.env` 缺 key 时 `llm_seeded: False` 的分支**——那是 `UPDATE users SET api_key` 与裸 `INSERT INTO user_models` 在真 MySQL 上的**首次执行**（live 套件不构造 lifespan）；⑥ 真服务验收顺带确认默认用户名单里 `is_default=True` **恰好一枚**（I-1 修复的真判据）。
- Task 3: **挂全分支终审的 Minor（3 条，均不阻塞后续）**：M-3 `FakeConn` 分支表已 15 格约 70 行、且在长成第二套 SQL 引擎（brief 那句"长前缀要先排"在该表里其实没被遵守，今天不撞只因表名整段不同）；M-6 `UNOWNED_VECTOR_ROWS` 名不副实（新语义下只是 vector_id → document_id 对应表）；M-7 两条观察（seed 早退只看 `api_key`，"有 key 没 base_url"的半态今天造不出；野 `user_id` 会留孤儿行，`ensure_default_user` 保证遇不到）。
- Task 4: dispatched implementer `ageneral-purpose-08d4fbc54f005972`（BASE `ccb67d0`，后台）。工单内联的裁定/实测：① **不许碰 `main.py`**（Task 7 才注册 409）；② `backend/exceptions.py` 是 **CRLF**（我实测过全仓行尾 27 CRLF / 18 LF）⇒ 手工编辑、禁脚本化变异；③ `tests/test_error_model.py` 的覆盖率判据我**亲读过**：形状是 `assert set(STATUS_BY_ERROR) == {五个类}`（比**映射表的键集合**，不是"所有子类都必须进表"）⇒ 新增没进表的类不会红，**不许动那个文件**；④ brief 说"9 条判据"、我按代码块数是 **10 个用例**（7 函数，`test_llm_config_for_refuses_a_half_set` 是 4 例 parametrize）⇒ 以实跑汇总行为准，不许为凑数删判据；⑤ 起点全量 `280 passed / 2 skipped / 2 deselected / 1 warning`，预期约 290，跑红即它改坏。
- Task 5: **预检实测（跨任务冲击，已回写计划）**——Task 3 把 `main.py` 的两行 `run_migrations(...)` 并成一行，`RAGSystem(config, ...)` 因此从计划写的 `:57` **前移到 `:56`**；派发 Task 5 时必须要求**按内容定位**（行里带 `RAGSystem(config,`），否则会把 `:57` 的 `logger.info("后端初始化完成…")` 改坏。`api/chat.py` 的 `:7` 与 `:41/:50/:75/:79` **实测仍准**，可照行号改。
- Task 5: **预检发现一处测试面重复**：`tests/fakes.py:1` 的共用 `FakeConfig`（只有 `CHROMA_PERSIST_DIR`）与 `tests/test_migrations.py:175` 的局部 `FakeConfig`（Task 3 新建、四键）**并存**。裁定：Task 5 只扩**共用那份**（补三键 + 口令），局部那份不动；"两份同名类可否改成 import 共用"记**全分支终审**。
- Task 6: **预检实测（已回写计划）**——Task 3 改写 `test_migrations.py` 后，Task 6 的 Files 行号**全部漂移**：`MIGRATED_COLUMNS` 现在 `migrations.py:33`（计划说 `:30`）、`MIGRATED_INDEXES` 在 `:41`（说 `:34`）、那条逐字 pin 现在 `test_migrations.py:371-375`（说 `:243`，断言**恰好三行**，Task 6 要改成四行）、`FakeConn` 现在 `:17-113`（说 `:15-84`）、通用 `SELECT COUNT` 分支在 **`:60`**（说 `:56`，新分支仍必须插在它之前）。**另有第二波漂移**：Task 5 会重写 `rag_system.py` 的四个链方法签名 ⇒ Task 6 里指向 `rag_system.py` 的 4×`get_chat_history` / 6×`save_chat_history` 行号也会变，**故 Task 6 的 brief 推迟到 Task 5 落地后再抽**（先回写再抽的规矩 + 这一条实测理由）。
- Task 5: brief 已按回写后的计划抽取（421 行 / 25055 bytes）。Task 6 的 brief **故意不抽**（见上条）。
- Task 4: **控制者直查全通过**。`git show --stat 6175267` = 恰好 brief 清单三枚文件（`core/llm_factory.py` +74、`exceptions.py` +6、`tests/test_llm_factory.py` +112，共 192 insertions，0 deletions）；三门我亲跑 = `tests/test_llm_factory.py` **10 passed**、全量 **290 passed / 2 skipped / 2 deselected / 1 warning**（Task 3 终态 280 + 10）、live **20 passed**，与它报的汇总行逐字一致。`core/llm_factory.py` 与 `exceptions.py` 的 diff 我逐字读过：符号名与 brief 的 Interfaces 逐字对齐（Task 5/7 的契约），`build_llm` 0.7+streaming、`build_compressor` 0+temperature 无 streaming，`llm_config_for` 是 `if not (api_key and base_url)` 一次判两格。
- Task 4: **它的 concern 1（工作树里计划文出现 +9 行未暂存 `M`）答案是我**——那两段 Task 5/6 预检修订块是我写的，与它无关；它已排除在提交外，`git status` 干净。已回它这条归属。
- Task 4: **行尾结论更正（重要，我自己先前说错过一次）**：本仓 `core.autocrlf=true`、无 `.gitattributes` ⇒ **git blob 一律存 LF**，所以用 `git show <sha>:<path>` 量行尾**永远得到 0 个 CRLF**，不能用来判断文件"是不是 CRLF"。**要看工作树文件**（`pathlib.read_bytes()`）。实测工作树：`core/migrations.py` 与 `tests/test_migrations.py` 是**纯 LF**，`exceptions.py` 是 **CRLF（\r\n=29、孤立 LF=0）**，两个新建测试/模块文件是 LF。我之前那条"这两枚文件在仓里是纯 LF"的证据引的是 blob，结论对但论据不成立，记此更正。
- Task 4: 评审包 `review-ccb67d0..6175267.diff`（9548 bytes，1 commit）；task reviewer 已派 `ageneral-purpose-b194fa8607024f51`（后台只读，内联了三条权威实数与"不许重跑/不许变异"，八个检查面逐条点名，其中第 2 条要它自己去读**未改动的** `rag_system.py`/`vector_store.py` 原构造来对照"搬迁没改行为"、第 6 条要它独立复核我关于 `test_error_model.py` 覆盖率判据形状的判断）。
- Task 4: **任务评审：Spec Compliance ✅ / Task quality Approved / 0 Critical / 0 Important / 3 Minor**（代理 `ageneral-purpose-b194fa8607024f51`，报告 `task-4-review.md` 13542 bytes）。它独立复核了我点名要它别只信我的两面：自己去读**未改动的** `core/rag_system.py`/`core/vector_store.py` 的原始构造逐字对照（确认搬迁没改行为），以及 `test_error_model.py` 覆盖率判据的形状（确认比的是映射表键集合）。它另核了 `git show --name-status` 与 `git diff 6175267 -- backend/`（工作树与提交逐字一致）。
- Task 4: complete (commits ccb67d0..6175267, review clean)。**终态三门权威实数（控制者亲跑）**：`tests/test_llm_factory.py` **10 passed**、全量 **290 passed / 2 skipped / 2 deselected / 1 warning**、live **20 passed**。
- Task 4: **挂全分支终审的 Minor（3 条）**：① 计划 brief 写"9 条判据"、实为 **10 个用例**（7 函数 + 4 例 parametrize）——数字口径问题，判据一条没少（评审逐条数过）；② `build_llm`/`build_compressor` 缺返回类型标注；③ 坑 9 的"同源"判据是**间接**钉法（通过注入 `llm_factory=build_llm` 的默认形参 + 结构判据，而非直接断言两处构造同源）。
- Task 5: dispatched implementer `ageneral-purpose-e89901a2a65f2824`（BASE `eb7763a`，后台）。派发前我实测并内联：`main.py:57`→**`:56`**（按内容定位，且只许改这一行）、`api/chat.py` 行号仍准、`tests/fakes.py` 的共用 `FakeConfig` 才是要扩的那份（`test_migrations.py:175` 的局部那份不许动）、`test_chroma_data.py`/`test_live_database.py`/`test_migrations.py` 都不在清单里**不许碰**；并给出**签名变更的完整消费者名单**（实测只有 `api/chat.py`、`core/{rag_system,vector_store}.py`、`main.py`、`tests/{fakes,test_api_chat,test_rag_system,test_vector_store}.py` 八个文件，与 brief Files 完全一致——**这条预检证明 Task 5 的清单是完整的**，live 组确实不引用那四个方法）；要求两条变异自证 + 实测"34 处触点"的真数。

- Task 5: **任务评审：Spec Compliance ✅ / Task quality Approved / 0 Critical / 1 Important / 3 Minor**（代理 `a9a69126bdb583439`，报告 `task-5-review.md`，2237829 subagent tokens / 159.8s）。它是**纯静态**评审（自己声明：未复跑门禁、未做变异实验，所有"会红/不会红"均由读断言 + 推演得出）——这一点与我复跑过三门互补，不冲突。
- Task 5: **I1 我逐条直查后采信（判据假绿，非生产缺陷）**：`api/chat.py:41` 的 `RunContext(user_id=user.id, …)` 在**端点层无牙**。我实测三点：① `tests/test_api_chat.py:322` 的 `assert rag.seen_user_ids == [1, 1]` 走的是默认人（`FakeUser()` 的 id 就是 1），把 `user.id` 换成常量 1 照样绿；② 全仓唯一用非默认人的端点判据是 `tests/test_api_chat.py:101`（`FakeUser(user_id=5)`），但它喂的是**基类 `FakeRAG`**，而 `fakes.py:76-113` 的 `FakeRAG` 四个方法收 `ctx` 后**一次都不读**；③ `SpyRAG.seen_user_ids` 确实已存在（`test_api_chat.py:63`），只差没用在非默认人身上。⇒ 这行是"读侧过滤按谁走"的唯一来源，被改坏时离线门禁零信号。
- Task 5: **裁定 I1 = 本轮修**（Ruling）。理由：这行是 Task 5 自己引入的、修法约 2 行测试、且压在 Task 5 的安全核心上；留给 Task 7 等于整个 Task 6 期间这条链都没有牙。**判错的时代价**：多花一次修正轮 + 约 3 行测试。
- Task 5: **裁定 M1/M2 本轮一并修**（`vector_store.py::add_documents` 的 docstring `:67-69` 与行内注释 `:71`）——该文件本就在本 Task diff 内，docstring 现与代码**直接矛盾**（写着"这一期只补戳、不做读侧过滤…等阶段二收窄召回池时一起接"，而读侧过滤本 Task 已接上），留着比没有更坏。**另我自查发现第三处，评审未提**：`vector_store.py:84-85` `create_retriever` 的 docstring 是**本 Task 新写的**，其中"阶段一…阶段二把它接上"同样是过期时态（见 `git show 28928d7 -- backend/core/vector_store.py`），一并收进 F2。
- Task 5: **裁定 M3 = 不修，挂终审**（`create_retriever`/`get_parent_documents` 的 `user_id` 无类型标注）——非缺陷，且与本仓其他方法标注风格不一致，单独补反成噪音。
- Task 5: **评审 6 条实施者 concern 的裁定我全部采信**（`where['parent_id']`→`where["$and"][0]["parent_id"]`、291 而非 292 的净变化核算 −4/+5、局部变量而非内联、docstring 陈旧、无戳向量召不回属设计连带、`test_ownership_isolation.py` 无需改）——前两条我自己复算过：290 + 5 − 4 = 291，与当轮汇总行一致。
- Task 5: **派发修正轮 1**（FIX_BASE `28928d7`，边界 = Task 5 的 9 文件，预期只碰 `core/vector_store.py` + `tests/test_api_chat.py`）。

- Task 5: **修正轮 1 落地：`7640a59`（2 文件 +16/−10，父 `753b792`，而 `753b792` 的父是 `28928d7`）**。F1 把两条既有端点判据的人设从默认人换成 `FakeUser(user_id=5)`（同步臂补 `assert rag.seen_user_ids == [5]`、流式臂 `[1,1]→[5,5]`）；F2 只改 `vector_store.py` 的三处注释/docstring（`add_documents` 的 docstring 与行内注释、`create_retriever` 的 docstring），**零可执行行改动**。修正代理另如实上报两点：FIX_BASE 我写的 `28928d7` 不是当时的 HEAD（实际是 `753b792`，只改计划文档的提交，与两枚源文件无交集）；以及我给的 F2 自证 grep 模式里含我自己写的"阶段二…接上"，所以那种写法不会 grep 空——它改用真正"待办"词（`不做读侧过滤`/`等阶段二`/`时一起接`/`只补戳不收窄`）自证 0 命中。两条我都采信，报告质量高于前几轮。
- Task 5: **修正轮 1 我自己直查了三件事**（不靠代理自报）：① 全量门禁我亲跑 **291 passed / 2 skipped / 2 deselected / 1 warning**——与修正前**逐字同数**（只改人设与断言、未增删用例，净变化 0，与代理算式一致）；② **变异自证我重做了一遍**：手工 Edit `api/chat.py:41` 的 `RunContext(user_id=user.id,` → `user_id=1,`，跑 `tests/test_api_chat.py` 得 **2 failed / 28 passed**，失败正是两条目标判据（`assert [1] == [5]`、`assert [1, 1] == [5, 5]`）；随后手工还原，`sha256=2bb62f5818a3eb3886600efb386bd0a0abde314ff0bcbf3c1205463e4dabc9e9` 与改前逐字相同、`lone_LF=0`、`git diff` 为空、`git status` 干净（我自己的变异零残留）；③ 记一条坑：`api/chat.py` 有**两处** `user_id=user.id`（`:28` 白名单给 `owned_parent_ids`、`:41` 构造 ctx），变异只能锚 `:41`，锚错就测了个不相干的东西。
- Task 5: **范围化复查 1：F1 达标 / F2 达标；新引入 Critical 0 / Important 0 / Minor 0**（`task-5-rereview1.md`，只读）。它另核了四条我没点名要的：枪链上（`chat.py:41`→`:49/:54/:63` 与 `:83/:89/:93`）无第二层包装可洗白常量；两条位置断言（`calls`/`stream_calls`）不含 `user_id`、在变异下仍绿 ⇒ **牙来源单一**；流式臂由"每次新建 client"改成"共用一个 client"**等价**（override 挂在 app 上、每请求各造 ctx、端点只读人设）；`vector_store.py` 无一可执行行被改。
- Task 5: **挂终审的 Minor（+1）**：F2 在 `add_documents` docstring 里把读侧过滤统称"`$and` 过滤"，而 `create_retriever` 在池为空时是裸 `{user_id: …}`（不套 `$and`）。复查判"措辞略宽但不与代码矛盾"，我同意，不为此再开一轮。
- Task 5: **complete（实现 `28928d7` + 修正轮 1 `7640a59`；review clean + rereview clean）**。**终态三门权威实数（控制者亲跑，锚在 `7640a59`）**：全量 **291 passed / 2 skipped / 2 deselected / 1 warning**、`-m migration` **2 passed / 293 deselected**、live（`tests/test_live_database.py`）**20 passed**。

## Task 5(断点恢复特记:被归档任务的实施代理实际未死)

- 状况还原:上一控制器 22:49 派发实施代理(ageneral-purpose-e89901a2a65f2824,BASE eb7763a)后用户归档了任务,但代理进程未被杀死,继续自主工作:22:51-22:57 完成全部 9 文件编辑、22:58 跑 Step 8 门禁(291 passed)、23:00:46 填完 task-5-report.md、23:00:59 提交 28928d7、23:02-23:04 再跑一轮全量、此后进入多轮变异自证循环(23:12 被控制者监视器捕捉到一处:把 _ctx_from_config 的 user.id 硬编码成 1,约 30 秒后自行还原)。所有瞬态改动均自还原,终态工作区干净。
- 本会话控制者直查(全部亲跑):git show --stat 28928d7 = 恰好 9 文件 +194/−151;全量 **291 passed / 2 skipped / 2 deselected / 1 warning**;live **20 passed**;main.py 按内容定位只动 RAGSystem 一行、logger.info 完好;_ctx_from_config / create_retriever 与 brief 逐字一致。
- 控制者独立变异(实施者两条之外加一条):create_retriever 的 [str(user_id)] 改 [user_id](int 形态)⇒ 恰 3 条 filter 判据红(含字符串形态那条),git checkout 还原后工作区干净。
- 实施报告 5 条偏差全核属实:① dedup 桩 KeyError 修正必要(brief 原桩在新 $and 形状下 KeyError 被生产 try/except 吞成空回溯,实现正确也永远红);② llm_factory 局部变量 = brief :190 注释的明确要求;③ 终态 291 非 292(算式漏 −2/+1 两项),与控制者独立重算一致;④ test_ownership_isolation.py 未改正确(make_isolation_client:133 早已覆盖 get_config,共用 FakeRAG 自动跟上新签名);⑤ add_documents docstring 陈旧一句 → 挂 Task 6/7 顺手订正。
- RED 证据:实施者报 Step 2 RED = 4 failed, 7 passed(TypeError:旧签名不收 user_id),与 Expected 形状一致;控制者以两条独立变异实证判据牙口,替代重演 RED。
- 计划回写(753b792,纯文档):dedup 桩 bug、291 算术两处。
- 评审:包 review-eb7763a..28928d7.diff;评审代理(结果待回填)。

- 23:06 发现:上一控制器的**评审代理**也活着——task-5-review.md(16485B,23:06:01)裁定 **Approved,0 Critical / 1 Important / 3 Minor**;十条检查面全给证据,与本会话控制者直查互洽。已备份 task-5-review.prev-20261007.md(本会话 23:15 重复派出的评审代理回报后将覆盖同一名文件,以备份为准,其结论仅作第二意见)。
- I1(Important,端点层 user.id→ctx.user_id 无牙,离线改常量不红):**上一控制器的修正轮已修**——7640a59(23:10:59)F1 双臂装牙(JSON 端点人设换 FakeUser(user_id=5) + seen_user_ids==[5];流式臂 [1,1]→[5,5]),提交信息附变异自证(user.id→1 两臂各红一条,还原净);F2 = M1/M2 注释订正(docstring 改「打戳与收窄分家」口径 + 行内注释补 user_id + create_retriever docstring 待办口吻收掉);门禁 291 净变化 0。控制者核对 diff 与评审处方一致且更全(双臂都钉)。M3(create_retriever 无显式类型约定)按裁定记账不修。本会话拟动手的 I1/M1/M2 修正作废——对方已完成,避免重复提交。
- 7c7a40e(23:1x):Task 6 预检回写第二轮(Task 3/5 之后行号整体再漂,逐格重测)。本会话 23:16 抽的 task-6-brief.md 据此**已过期**,任何派工前必须重抽。
- 态势定性(23:24):上一控制器流水线(控制者+实施者+评审者)在任务被归档后全部存活并自主推进,现已跑到 **Task 6 实施中**(工作树 8 文件:database/migrations/rag_system/api/{chat,history}/fakes/test_{migrations,api_history};api/chat.py 在 Task 6 清单之外,挂疑点待评审核对是否越界或属瞬态变异)。本会话转监督+验证+记账:不碰 backend/、不跑 pytest(chroma 单实例锁会互卡)、等 Task 6 提交落盘且静默后做控制者直查;若对方链路中断(额度/崩溃)则在断点接管。台账由本会话补记(对方 22:48 后未再写台账)。
- 23:29 更正:本会话 23:15 重复派出的评审代理因基础设施错误失败(Captcha instance timed out after 10000ms,661s)。第二意见取消;Task 5 评审以上一控制器链的 task-5-review.md(已备份 .prev-20261007)与本会话控制者直查为准,双源互洽,Task 5 维持 Approved 收口。

- 23:35 **接管裁定(用户明令)**:用户指示「你直接接管,然后执行到任务完成」。因对方实施代理仍在活跃编辑(23:34:53 仍写 api/history.py),本会话以「提交落盘 + 工作区静默」为交接边界:边界前只读监视(快照 task6-wip-snapshot-2335.patch 已存),边界后本会话即唯一写入者,Task 6 收口与 Task 7-12 全部亲自执行(TDD + 三门 + 逐 Task 提交),不再派实施/评审代理,终审由本会话自审并向用户明示。若 15 分钟内无提交且无编辑活动,按「实施者已死」处理,直接以快照为底接管工作树。

- Task 6: **预检回写已提交 `7c7a40e`**（`docs(plan)`，+15 行，只改计划文档）。第二轮预检块里我把 Task 6 正文的全部行号按 `28928d7` 工作树重测并覆盖：`database.py` 三方法 `:475/:487/:507`、`rag_system.py` 十处历史调用点 `:49/:63/:94/:106/:122/:150/:168/:189/:204/:223`、`fakes.py :32/:35`、`test_rag_system.py` 三处整字典 `:106/:161/:303`、`FakeConn.__init__` 真实五形参、逐字 pin `:371-375`、live 组 11 处调用点位。**四处逐字命中无需改**：`test_ownership_isolation.py:87/:90`、`test_api_history.py:73/:101/:105`、`test_error_model.py:154`、`api/chat.py:21-23`。
- Task 6: **回写时新增两条正文没有的事实**：① `api/chat.py:21-23` 那三句里"`RAGSystem` 四个方法的签名保持不变"在 Task 5 之后**已是假话**（四方法确实加了 `ctx`），整段删掉正好一并清掉——原文只说"删掉这三句"容易被读成只删后两句；② live 组 11 处历史调用现在全不带 `user_id`，签名一收 keyword-only 就 `TypeError` ⇒ **Step 3 与 Step 7 必须同一次落地**，不能中间红着。生产侧消费者穷举 = `api/history.py` ×2 + `rag_system.py` ×10 = **12 处**，与 Files 一致，无第三个文件。
- Task 6: 抽取 brief `task-6-brief.md` **368 行**（用插件的 `skills/subagent-driven-development/scripts/task-brief`，fence-aware awk；`## Task 6:` 到 `## Task 7:` 之间的正文，**含两段修订块**）。⚠️ 我一开始在仓库里找 `scripts/` 没找到——SDD 三个 helper 的真身在 `C:\Users\31439\.qoder\plugins\cache\qoder-marketplace\superpowers\6.3.0\skills\subagent-driven-development\scripts\{task-brief,review-package,sdd-workspace}`，以仓库为 cwd 用 `bash <绝对路径>` 跑。
- Task 6: **派发实施代理 `ageneral-purpose-f5635de376f64a72`**（后台，BASE `7c7a40e`）。派发前我内联了：三条排程硬约束（Step 3+Step 7 同落地 / Step 8 的 DDL 必须先于 live 组 / 禁跑 `-m migration` 因 Chroma 单实例锁）、四条门禁串行、**两条变异自证**（A：`rag_system.py` 某处 `ctx.user_id`→常量应红新判据；B：`api/history.py` GET 的 `user.id`→常量应红 `user_id=99` 那条），并逐条点名 `FakeConn` 五形参 / 三处整字典别多加键 / `PROBE_API_KEY` 不许碰 / 两枚同名 `FakeConfig` 只有 `fakes.py` 那份是共用的 / `api/chat.py` 本 Task 只删注释。控制者权威实数内联：全量 **291/2/2/1**、live **20**、`-m migration` **2**（后两枚跑在 `7640a59` 上），正文预期净变化 **+3/+1 ⇒ 294/21**，并明令"与 +3 不符就如实说差在哪，别硬凑"。
- 我做的两处**边界收紧**（都超出任务书原文，理由是防扩散）：Task 6 不许碰 `main.py`/`vector_store.py`/`llm_factory.py`/`exceptions.py`/`test_api_chat.py`/`test_llm_factory.py`；并明令"要跨出边界才能收口就先停下报告，别自己动手"。

- Task 6: **complete（实现 `41b45d2` + 评审修正 `177077c` + 计划纠偏 `c4bf475`；控制者自审 Approved，0 Critical / 0 Important / 2 Minor，M1 本轮修、M2 挂终审）**。评审报告 `task-6-review.md`（十个检查面逐条给证据，含跨任务冲击三面）。
- Task 6: **控制者亲跑四门（唯一权威实数，均成对核过"工作树干净 + sha256 基线"）**：全量 `295 passed, 2 skipped, 2 deselected, 1 warning in 66.64s`；`tests/test_migrations.py` `17 passed in 5.55s`；`tests/test_live_database.py` `21 passed, 1 warning in 4.41s`；`tests/test_chroma_data.py -m migration` `2 passed in 4.48s`。实施代理所报前三道逐字一致，采信；`-m migration` 它按工单没跑（如实声明）。
- Task 6: **我自己重做的两条真库变异**（不是采信代理的离线推断）：删 `database.py:487` 读臂 `ChatHistory.user_id == user_id` ⇒ `1 failed, 20 passed`，红在 `assert db.get_chat_history(sid, user_id=b.id) == []`（B 直接看到 A 的行）；删 `:525` 删臂 ⇒ `1 failed, 20 passed`，红在 `assert db.delete_chat_history(sid, user_id=b.id) == 0`（`assert 1 == 0`）。⇒ 计划点名的"GET 加了过滤、DELETE 忘了"这种半截交付在 live 层有牙。两臂各自还原后 sha256 回到 `6b68400d…`（CRLF=771/loneLF=0）、`git diff` 空。
- Task 6: **并发写入事件（重要流程账，双方都还原干净）**：00:07-00:16 之间工作树反复瞬态变脏——`rag_system.py:108`（`ctx.user_id`→常量 1）、`api/history.py` 两臂、`migrations.py`、`database.py` 删臂。事后确认是**两轮回流的实施代理仍在做变异自证**（它 00:26 才正式收口，通知里也反向记录了同一件事："收口期间工作树被外部进程删掉 delete_chat_history 的一行"——**它指的是我的读臂变异，我指的是它的写臂变异**，我们俩在互相踩对方的实验）。教训：① 代理通知未落地 = 代理可能还活着，"提交落盘 + 静默"不足以判定交接完成，要等到收到完成通知或明确死亡；② 门禁数只在"干净 + sha 基线"配对下才算数（本轮我四道门都满足）；③ 后续 Task 若仍派工，变异自证这一环节由控制者独占，工单里写死"不许动 backend/ 之外的实验性编辑，跑完立刻还原并报 sha"。
- Task 6: **我自己的一个错（如实记）**：计划纠偏那笔提交我误用了 `msg-task6-m1.txt`（chat.py 那条信息），产出 `d07c62d`＝"信息说改 chat.py、实际改计划文档"。处置：`git reset --soft HEAD~1`（内容留在索引）+ 用正确信息文件重打 ⇒ `c4bf475`，`git diff d07c62d HEAD --stat` **空**（逐字节等价），旧提交仍在 reflog 可回。未 amend、未推送、未丢任何改动。规矩：**信息文件与内容要同一轮配对**，别凭记忆挑文件名。
- Task 6: **M2 挂全分支终审**：`ChatHistory.user_id` 在 ORM 里带 `ForeignKey('users.id')`，但迁移走裸 DDL 不带约束 ⇒ 新库有 FK（删账号会被引用行卡住）、老库无 FK（同一操作留孤儿历史行）。列注释已写明这层不对称、与 `documents.user_id` 从阶段一起同状态，非缺陷；将来若有"注销账号"功能必须先看这条。
- Task 6: **交付时必须对用户说的一条连带**（brief 结尾硬性要求，代理也转达过）：归户只发生在跑过迁移的库上；没跑过的库里老行 `user_id` 仍是 NULL ⇒ 表征是"升级之后历史全空"而不是报错。真服务重启即自愈。本机真库已归户（`chat_rows_claimed=43`、NULL 0 行、列与索引都在）。
- Task 7: **起点实数（新基线，锚在 `c4bf475`）**：全量 **295 / 2 skipped / 2 deselected / 1 warning**、`test_migrations` **17**、live **21**、`-m migration` **2**。预估条数时记得：**新增 live 判据也会进全量**（Task 6 的教训，已回写计划 ①）。
- Task 7: **必须保住的三样东西**（派工单/自做工单里逐字写）：① `_llm_context` 复用 `_default_of`（默认解析规则只许有一处），并给一条同源变异自证；② `NotConfiguredError` 进 `STATUS_BY_ERROR` 拿到 409（映射表 5→6 键）+ 探针路由；③ Task 5 修正轮装的端点层牙 `seen_user_ids == [5]` / `[5, 5]` 在 `_ctx_from_config` 换成读用户行之后**必须仍然绿**（这一格是"凭证与主人同来源"的唯一端点证据）。另：`api/chat.py` 的 `_require_owned_parents` docstring 本 Task 又被 `177077c` 改长，行号再漂，按内容定位。

## Task 7(问答吃用户凭证 + 三条 409 门禁)

- Task 7: **complete（实现 `869360b`，10 文件 +301/−116；控制者自审 Approved，0 Critical / 0 Important / 2 Minor 挂终审）**。按 23:35 接管裁定本 Task **未派实施/评审代理、未抽 brief**（`task-brief` 只服务派工，控制者直接按计划正文做）——这是流程偏离，终审由本会话自审并在交付时向用户明示。
- Task 7: **计划纠偏回写 `6df163f`**（`docs(plan)`，+6 行，纯文档）：预检那块 ①-⑧ 钉准了行号，但正文步骤自身还有五处与落地代码不一致（a 合并 SpyStreamRAG / b 断言拆分 / c RED 实为 40 不是 8 / d 三轮变异红数 2-1-5 / e live 两样补），按本仓规矩写进 `>` 修订块、不动 ``` 围栏里的正文。两笔提交后 `git status` 干净。
- Task 7: **控制者亲跑五道门（唯一权威实数）**：全量 `304 passed, 2 skipped, 2 deselected, 1 warning in 68.69s`；`test_migrations` **17**；`-m migration` **2**；`test_live_database` **21**；live 流式组（真服务，跑在门禁之前）**2 passed in 142.86s**。算式对账：Task 6 终态 295 + 本 Task 净 9 = 304（新增 7 个函数，`test_a_user_without_credentials…` 按端点参数化出 8 条，`test_error_model` 探针行再加 1 条）。
- Task 7: **RED 证据（focused，`pytest tests/test_api_chat.py tests/test_error_model.py -q`）= 40 failed / 7 passed in 67.50s**。比正文预期的"8 条红"多得多，原因是真的：这一步同时删掉了 `dependency_overrides[get_config]`，而旧 `_ctx_from_config` 还在读 `request.app.state.config` ⇒ **38 条 chat 全红**（`AttributeError: 'State' object has no attribute 'config'`）+ 2 条 error-model 新判据红。如实记为"RED 形状与计划不符但可解释"，不是假红。
- Task 7: **三轮变异自证（全部手工 Edit，逐字节回退，sha256 与基线一致，零脚本）**：
  ① `api/chat.py` 的 `llm_config_for(user, model)` 结果换成"别人的 api_key"（保留 `llm_config_for` 调用，让 409 门不被误伤）⇒ **恰好 2 红**：`test_the_callers_own_credentials_reach_the_chain` + `test_stream_payload_is_forwarded_in_the_right_positions`（`:338` 那条 `seen_llm`）。还原后 `sha256=8956476a…` 与基线逐字相同。
  ② `schemas/auth.py::default_model_of` 回落 `rows[0][0]`→`rows[-1][0]` ⇒ **恰好 1 红**（`test_the_first_model_is_the_fallback_when_none_is_default`）。同源那一面另用 grep 钉：`is_default in rows` 全仓 **1 处命中**（`:157` 定义点），设置侧与问答侧都走 `default_model_of`，没有第二份解析规则。还原后 `sha256=01436240…`。
  ③ `main.py` 的 `STATUS_BY_ERROR` 摘掉 `NotConfiguredError: 409` ⇒ **5 红**：3 条问答门禁（两条 not-configured 参数 + 空名单那条，全被兜底 handler 洗成 500）+ `test_error_model` 的探针行与覆盖率 pin。还原后 `sha256=9b3629eb…`。`grep -rn MUTATION` 空，工作区干净。
- Task 7: **三条裁定（我自己拍的，记此以便终审复核）**：
  R1: `_default_of` 从 `api/auth.py` 私有函数上移为 `schemas/auth.py::default_model_of` — 理由：问答侧与设置侧必须给同一个答案，复制一份迟早分叉（分叉表征是界面选中 A、实际打出去 B），而 `schemas/auth.py` 已是本仓"两个 API 模块共用的 auth 口径"落点（`normalize_identifier`/`mask_api_key`/`MODEL_NOT_IN_LIST`）— 代价：若将来名单口径要按入口分家，得再拆一次。搬迁先单独跑全量 **295 全绿** 证明行为中性，才动 RED 测试。
  R2: `SpyRAG` 的记录器改成**调用时记录 + `return super()…`**（非生成体内记录），并删掉重复的内层 `SpyStreamRAG` 类 — 理由：`rag.calls == []` 这类"链子根本没跑"的判据，若记录写在生成器体内，链子没被迭代就不记，判据会**假绿** — 代价：`calls` 与 `stream_calls` 两套列表要各自断言。
  R3: 计划里 `assert rag.calls == [] and rag.stream_calls == []` 拆成两行分别断言 — 理由：`and` 合并后红起来看不出是哪个端点漏的 — 代价：多一行。
- Task 7: **跨任务冲击（预检那条硬约束实跑了）**：409 门在**白名单之前**执行 ⇒ Task 6 装的越权判据（`test_ownership_isolation.py` 那两枪必须红在 404）会因为 `OwnerAwareDB` 没有 `list_user_models` 而先撞 409。处置：给 `OwnerAwareDB` 加**不过滤**的 `list_user_models`（返回整份名单，注释写明"门在名单之前，这里再过滤就测不到 404"）；`FakeOwnedParentsDB` 默认回 `[("fake-model", True)]` 且**绝不往 `self.calls` 里记**（多记一笔就把"白名单收到正确 user_id"那条判据撞红）。两端点 Task 5 修正轮的 `seen_user_ids == [5]` / `[5, 5]` 牙照旧绿（三样必须保住的东西之一，已验）。
- Task 7: **live 真服务 409 手验（`probe_task7_409_live.py`，只打印状态码/文案，不打印令牌）**：`/api/chat` 与 `/api/chat/stream` 各发一枚名单外模型 `gpt-9` ⇒ 都回 **409 application/json + 「模型不在你的名单里」**，两个会话历史落库 **0 行**，`logout 204`。顺手抓到自己脚本的一个 bug：会话 id 拼了 `path`（含 `/`）导致 `GET /api/history/<sid>` 是个被切坏的 URL —— 改成枚举下标。advisory ④ 复核：`auth_tokens` 默认用户残留 **0 → 0**（两轮登录各登出）。
- Task 7: **挂终审的两条 Minor**：M-A `test_api_auth.py:440` 那个函数名承诺的是"`ChatRequest.model_name` 的长度上界"，实际那条测的是 `models` 端点的 name 上界，问答侧的 `model_name` max_length=100 没有专项判据（同源记账在 Task 2 已挂过一次，本轮只补注释不新开一轮）。M-B **设置侧对"第一个 vs 最后一个"无判据**：变异 ② 只红 1 条、且全在问答侧 —— `test_api_auth.py` 那条回落判据只剩一行名单，`rows[0]` 与 `rows[-1]` 同值，测不出方向。补它需要在设置侧造两行无标记名单，属设置侧覆盖缺口，不阻塞本 Task。
- Task 7: **交付时必须对用户说的两条连带**：① 从本 Task 起，没配好 key/路由/模型名单的用户一发提问就收 **409**（横幅到 Task 11 才有；Task 8-10 期间界面会把这句 409 当红字显示，是预期的中间态）；② 老 `.env` 少了 `LLM_MODEL` 的人升级后只会拿到 key 和路由、**名单是空的**，他看到的第一条 409 就是「你的模型名单是空的，请先在设置里添加一个模型」——这不是回归，是 `user_models` 表本来就没有他的行。
- Task 8: **起点实数（新基线，锚在 `869360b`）**：全量 **304 / 2 skipped / 2 deselected / 1 warning**、`test_migrations` **17**、`-m migration` **2**、`test_live_database` **21**、live 流式组 **2**。Task 8 起是前端（`postStream`/错误带状态码/设置封装/401 落回登录），后端门禁数**不许变**；前端 vitest 基线另测。
## Task 8(前端错误带状态码 + 六个设置封装 + 运行中 401 落回登录)

- Task 8: **complete（实现 `da641fa`，10 文件 +357/−27；计划纠偏 `e0a525b`，纯文档 +10 行；控制者自审 Approved）**。按 23:35 接管裁定：未派实施/评审代理、未抽 brief（`task-brief` 只服务派工）。流程偏离要在交付时向用户明示。
- Task 8: **门禁实数（本 Task 纯前端，后端四道门未动也不该动）**：`npm test` = `Test Files 13 passed (13)` / `Tests 131 passed (131)`，与计划设计数 **131 逐字相符**（基线 117 + 新增 14：client 5 / documents-api 2 / api-auth 4 / useAuth 2 / App.auth-gate 1），零凑数。`npm run build` 通过（`dist/assets/index-*.js 92.59 kB`）。后端锚点仍是 Task 7 终态 **304 / 2 / 2 / 1**（本 Task 没碰 `backend/`，故不重跑，记此以免终审问"前端 Task 为何验后端"）。
- Task 8: **分步 RED/GREEN 实数**（除 Step 1 那枚是事后精确重建测的、见下一条，其余都是当轮抄下的汇总行）：Step 1 focused `tests/client.test.js` = **5 failed | 21 passed (26)**；Step 2 落地后同文件 **26 passed**；Step 3 之后全量 **124 passed**；Step 4 focused `tests/api-auth.test.js` **6 passed**；Step 5 focused `tests/useAuth.test.js` = **1 failed | 8 passed (9)**（红的只有 `patchMe is not a function`；同轮第二条**在改动之前就已是绿的**，它是防回归不是 RED 驱动，照实记）；Step 6 focused `tests/App.auth-gate.test.js` **4 passed**。
- Task 8: **我自己的一条错数字（如实记，已回写计划）**：Step 1 那轮 RED 我当轮只抄了汇总行，写提交信息时凭记忆写成"4 failed | 22 passed"，**是错的**。事后用「`git show da641fa~1:` 的旧 `client.js` + 新测」精确重建实测 **5 failed | 21 passed (26)**（五条全红，红的理由分别是 `toBeInstanceOf(undefined)` 与 `setUnauthorizedHandler is not a function`）。处置：`da641fa` **不 amend**（本仓铁规矩），错数字留在提交信息里，由 `e0a525b` 的修订块与本条更正。规矩再钉一次：**没抄到手就当轮的数字，就不要写成数字**——写"五条全红"是安全的，写"4 failed"就是在造证据。
- Task 8: **三条变异自证（手工 Edit + `cp` 备份还原 + sha256 双向核对，零脚本）**：
  ① 删 `httpError` 里的 `notifyUnauthorized(status)` ⇒ **3 红、跨 3 个文件**：`client.test.js` 的"401 触发回调…request 与 postStream 两条出口都算"、`documents-api.test.js` 的"上传撞 401 同样触发登出回调"、`App.auth-gate.test.js` 的"运行中撞 401"整条（`3 failed | 36 passed (39)`）。比计划预测多一条 XHR——三条出口各有牙这件事是被测出来的，不是写在注释里的。
  ② `client.js:121`（计划写 `:81`，被本 Task 自己插入的 `ApiError` 顶下去了）回退成 `new Error(detailFromText(…))` ⇒ **2 红**：「流开始前的 409 在 HTTP 阶段就把状态码交出来」+ 同一条 401 测的后半句（回退同时绕过了通知）。还原后 `sha256=7fd956b4…`。
  ③ 删 `handleSessionLost` 里的 `clearAuth()` ⇒ **1 红**：`.auth-screen` 那句 `expected false to be true`，其余三条照绿 ⇒ "整屏落回登录页"确实只由这一句开关。还原后 `sha256=c562559b…`、`App.auth-gate.test.js` 还原后 `sha256=3ff3ae4c…`。
- Task 8: **四条裁定（我拍的，终审复核用）**：
  R1: Step 6 的 401 注入**两拍同翻**（`/api/documents` + `/api/history/`）而非计划原文的一拍 — 理由：计划原文会让 `msgs: 0` 永久红，且红得像"清理没清干净"；实测把 flips 只留 documents 时红的正是那条组合断言，实数 `expected { docs: +0, msgs: 2 } to equal { docs: +0, msgs: +0 }`（其余三条绿）。真实场景一枚过期票就是每一枪都 401，顺带把"三拍都可能撞 401"的重入压给被测代码，`resetWorkspace` 的幂等不再是纸面承诺 — 代价：这条测对"只有 documents 会 401"这种假想场景不设防，而那场景不存在。
  R2: Step 1 那条"三条出口都算"在同一个 `it()` 内补 postStream 的 401（标题相应改成"request 与 postStream 两条出口都算，XHR 在 documents-api.test.js"） — 理由：原文标题写三条、代码只走一条，"回调只在 JSON 出口生效"照样绿；不新开 `it()` 是为了**条数与计划的 14 条保持可核对** — 代价：一条测里两个出口，红时看断言行号才知哪条。
  R3: Step 4 把 `addModel` 并进模型那条而非新开一条 — 理由：原文四条覆盖五枚封装，`addModel`（唯一 `POST /api/auth/me/models`）零判据；并进第四条只多用两次已有的 `request.mock.calls` 槽 — 代价：同 R2。
  R4: `patchMe` 留在 `useAuth()` 函数体内、只有 `clearAuth` 上移到模块级（与计划一致） — 理由：`clearAuth` 要能被 `setUnauthorizedHandler` 在 setup 之外引用，`patchMe` 的消费者是组件里的设置弹窗，留在函数体内调用面不变 — 代价：两个同族函数分居两处，读代码时要跳一次。
- Task 8: **跨任务冲击与连带（预检扫出来的，都已落进测）**：
  ① `bootstrap()` 的"401 静默清凭证"与本 Task 的回调**重叠**：一次启动期过期票会跑两遍 `clearAuth`（一遍在 catch、一遍在回调）。刻意不走去重——`bootstrap` 的 catch 不知道也不该知道状态码。幂等让重叠无害。
  ② 注册时序实测：Vue 同步依次调用两个 `onMounted`，第一个 hook 在 `await` 处挂起后第二个 hook 立即注册 handler，而任何 fetch 的响应都在更晚的微任务里 ⇒ **启动期第一枪就 401 时回调也已就位**。这不是巧合而是 Promise 解析必然晚于同步 hook；本 Task 没为它开判据（要开得改桩成同步 resolve，反而失真）。
  ③ 下游消费者确认：Task 9 的 `SettingsModal` 只调本 Task 的六枚封装 + `patchMe`；Task 10 的下拉只读 `patchMe` 之后的 `user.models`；Task 11 的横幅只读 `err.status`。**Task 11 必须知道**：`ApiError` 允许带 200 那种"看着成功其实坏了"的状态码（`documents.js:48` 上传回执不是 JSON 时 `status = xhr.status`），所以分支不能写成 `if (err.status)`，要写 `=== 409` / `=== 401` / `=== 0` 这类具体值。
- Task 8: **挂全分支终审的三条 Minor**：M-A `%2F`（带斜杠的模型名删除）只有编码那一格判据，代理/nginx 若归一化 `%2F` 就变 404，Task 12 要手测一次并记边界，不许改道成 query 参数；M-B `App.auth-gate.test.js` 那条新测断言的是 `{docs, msgs}` 两格，没断 `queue`（该场景根本没有入队入口，断它是空转），终审若要统一口径可并入；M-C 上面 ③ 那句 `ApiError(status=200)` 的语义只有注释担保，`err.status` 的取值域（0 / 真状态码 / 200）没有类型层约束——是否值得在 `client.js` 加一句 docstring 说明"status 不是 HTTP 状态码的同义词"，交终审拍。
- Task 8: **交付时必须对用户说的一条连带**：从本 Task 起，**票在会话中途过期时界面会自动落回登录页**（以前是停在"已登录"里反复撞 401）。它与启动期 `bootstrap()` 的清凭证路径故意重叠，用户看到的表征是同一条：回到登录页、三个本地键一起清、不弹横幅。

## Task 9(SettingsModal 四段设置弹窗 + ⚙ 解禁 + 头像预设)

- Task 9: **complete（实现 `6f920c3`，5 文件 +519/−12，新建 `SettingsModal.vue` 与 `SettingsModal.test.js`；计划纠偏 `1945656`，纯文档 +11/−0；控制者自审 Approved）**。按 23:35 接管裁定：未派实施/评审代理、未抽 brief。流程偏离要在交付时向用户明示。
- Task 9: **三门实数（本 Task 纯前端，后端门禁未动也不该动）**：`npm test` = `Test Files 14 passed (14)` / `Tests 141 passed (141)` = Task 8 的 131 + 10（`SettingsModal.test.js` 8 + `App.auth-gate.test.js` 2），与计划设计数逐字相符，零凑数；`npm run build` exit 0（`index-B0QRINQ4.js 99.69 kB`）；G-4 颜色字面量 grep 实数 **0**。后端锚点仍是 Task 7 终态 **304 / 2 skipped / 2 deselected / 1 warning**（本 Task 没碰 `backend/`，不重跑，记此以免终审问"前端 Task 为何验后端"）。
- Task 9: **分步 RED/GREEN 实数**：Step 1 首跑 `Test Files 1 failed (1)` / `Tests no tests`（当轮抄的汇总行），但**第一个红的理由是错的**（我的抄写错误，见下一条）；修正导入后同一形状（`Failed to resolve import "../src/components/SettingsModal.vue"`）才是计划预测的 RED。Step 2 落地后 focused 只剩 1 红、8 条里 7 绿（**这一句是事后转述，不是当轮抄的汇总行原文**），红的只有判据 #7，且红在测试自己的选择器（`expected true to be false`，全子树 `find` 被第二行顶掉），逐行 `findAll` 改后 focused 全绿 8 条。Step 4/5 之后全量首跑当轮汇总行 `Tests 1 failed | 140 passed (141)`（红的就是头像测，缺 `nextTick`），补两句后 `Tests 141 passed (141)`。
- Task 9: **我的一条错误指控（如实记，已回写计划）**：提交信息 `6f920c3` 末段写"计划 Step 1 的 import 少写 `src/` 一段"——**这是假的**。直查计划原文：`:2939`（Step 1 测试片段）一直是 `'../src/composables/useAuth.js'`，正确的；`'../composables/useAuth.js'` 出现在 `:3016`（Step 2 **组件**片段，在 `src/components/` 下同样正确）。真相是我建 `tests/SettingsModal.test.js` 时把组件那一行抄进了测试目录，两处相对深度不同 ⇒ 解析不到。**处置：不 amend**（本仓铁规矩），由 `1945656` 的修订块与本条更正；计划原文一个字都没按那句改。规矩升级一次：**指认"上游文档有缺陷"之前，先把原文那一行贴出来与自己的行逐字 diff**——把自发笔误记成计划缺陷，比记错数字更贵，因为它会让下一个人去改一份本来正确的文档。
- Task 9: **五条变异自证（手工 Edit + `cp` 备份还原 + sha256 双向核对，零脚本）**：① `applyModels` 改整行覆盖 `patchMe(out)` ⇒ `1 failed | 7 passed (8)`，红在 #5 的 `api_key_masked`（`Received: undefined`）；② 删 `run()` 里 password 成功后的两句清空 ⇒ 1 红，#4 的 `oldPw` 那格残留 `+ old-pass`；③ ⚙ 加回 `disabled` ⇒ 1 红（App 那条 `attributes('disabled')`，`Received: ""`）；④ `Array.from(avatar)[0]` 换 `charAt(0)` ⇒ 1 红，头像测收到**半个代理对**（终端显示成替换字符，故不誊抄报错原文）；⑤ 删 `resetWorkspace` 里 `settingsOpen.value = false` ⇒ 1 红（开着弹窗登出那条，`expected true to be false`）。每轮还原后 `sha256` 与基线逐字相同：`SettingsModal.vue a3eee956…`、`App.vue e153309f…`。**顺带证实**：⑤ 只红 Step 5 第一条，Step 4.4 要求补进 401 测的那句 `settingsOpen === false` 照初值绿、**单独不构成牙**（401 发生在弹窗有机会打开之前），于是我把这句实话写进了测的注释。
- Task 9: **四条裁定（我拍的，终审复核用）**：
  R1: 401 测里照计划补 `settingsOpen === false`，同时在测里写明它不是牙 — 理由：计划明写要补，删它等于违原文；但让它冒充"清理动作有判据"会更坏 — 代价：多四行注释。
  R2: 弹窗开关 `settingsOpen` 留在 App、并进了 `resetWorkspace()` 的清理组（与 `pickerOpen` 同列） — 理由：`v-if` 只卸载 DOM，ref 活在 App 实例上，不清就是留给下一个登录者的半截表单（里面还可能装着上一个账号的 api_key 草稿） — 代价：`resetWorkspace` 的职责从"数据清理"扩到"界面态清理"，再加一个浮层就得再补一行。
  R3: 两个密码框的选择器走 `input[aria-label="原密码"] / "新密码"`，**不新增 `.settings-old-password-input` 这类类名** — 理由：为一场测试加一个只有测试读的类名，是把界面 CSS 变成判据附件；`aria-label` 本来就该有（读屏软件要分辨这两个框），一举两得 — 代价：文案改名会让测红，且红得像"行为坏了"（已在测头注释里指认这条路）。
  R4: `railAvatar` 保留计划给的 `Array.from(avatar)[0] ?? '我'` 那个**不可达分支**（`avatar` 非空字符串时 `Array.from` 必有第 0 项） — 理由：计划原文如此，且删它属于"顺手清理"，本 Task 不扩权 — 代价：一行永不执行的代码；已挂 Minor 交终审。
- Task 9: **跨任务冲击（下游消费者）**：① **Task 10 的起点是 141**，计划里"基线 117"那句从本 Task 起全部过期；② Task 10 的模型下拉读的是本 Task 经 `patchMe`/`applyModels` 合并进 `user.models` 的名单，**加/删/设默认之后下拉必须跟着变**，那条链路本 Task 已有组件侧判据（名单两行渲染），但没有"弹窗改完 → 下拉可见"的 App 层判据（归 Task 10）；③ Task 11 靠本 Task 的 `settingsOpen` 打开弹窗（那句"未配置"横幅要点⚙），并把 `App.auth-gate.test.js` 的 `ME.user` 抽成 `meUser(over)` builder（本 Task 只扩到十键、`models` 给一项）；④ `PASSWORD_MIN = 6` 现在是**第三处副本**（`schemas/auth.py:13`、`AuthPanel.vue:14`、`SettingsModal.vue:25`），改后端下限必须三处一起，漏一处的表征是"注册能过、改密码被本地拦"或反过来。
- Task 9: **挂全分支终审的三条 Minor**：M-A `?? '我'` 死分支（见 R4），要不要删交终审；M-B **弹窗只在 setup 那一次回填**（`profile`/`llm` 两个 reactive 从 `user.value` 抄初值，没有 `watch user`）——若某天在弹窗开着时从别处改 `user`（Task 11 之后并非不可能），界面不会跟着变，这是**已知边界**不是 bug（弹窗每次都是 `v-if` 新挂载），终审若要闭合就得上 watch；M-C `.settings-*` 复用 `.picker-backdrop`/`.picker-modal` 两个类做浮层底座，样式上是省了 30 行，代价是选块弹窗将来改尺寸口径会连带改到设置弹窗（Task 12 的视口判据 11 依赖 `.settings-model-row` 的 `flex-wrap`，届时注意别只盯 `.picker-*`）。
- Task 9: **交付时必须对用户说的两条**（计划 Step 7 原文要求，逐字落实）：① 弹窗里的 api_key 输入框**永不回填**、保存成功立刻从组件状态抹掉——"我只改路由不想重打 key"这件事做不到，必须重贴一次全文，这是决策 5 + spec 3.1 的直接后果，不是遗漏；② 改密码**不吊销**其它令牌（spec 7.4 已知遗留），另一台机器那枚票还能用到 30 天 TTL，界面上那句提示就是为这件事写的，不许在实现时顺手删。
- Task 9: **本轮的验证缺口（如实记）**：只有 jsdom 判据，**没做浏览器实测**。弹窗的真实视觉（`66vh` 固定高度、≤768 那一条 `flex-wrap`、掩码串的实际显示、emoji 头像在真字体下的样子）全部未验，归 **Task 12 的 11 条视口判据**（其中第 11 条就是本 Task 的 `.settings-model-row`）。交付时不许说"设置界面已验证"，只说"自动化判据绿 + 视口实测待 Task 12"。

## Task 10(ChatInput 两段式 + 模型下拉 + model_name 接到发送链路)

- Task 10: **complete（实现 `74eaf62`，8 文件 +197/−17；计划纠偏 `666f6f7`，纯文档 +23/−0；控制者自审 Approved）**。按 23:35 接管裁定：未派实施/评审代理、未抽 brief。流程偏离要在交付时向用户明示。
- Task 10: **三门实数**：`npm test` = `Test Files 14 passed (14)` / `Tests 148 passed (148)`（计划预期 147 = 141+6，多的那 1 条是下面变异① 的补偿测）；`npm run build` exit 0（CSS `13.14 kB`、JS `100.61 kB`，Task 9 是 99.69 kB）；G-4 颜色字面量 grep 对 `src/styles/layout.css` 实数 **0**（`variables.css` 按既有口径整体排除）。后端一个字没碰，锚点仍是 Task 7 终态 **304 / 2 skipped / 2 deselected / 1 warning**。
- Task 10: **分步 RED/GREEN 实数（逐条抄当轮汇总行）**：Step 1（只落 3 处钉 + 两个类名）全量 `Tests 141 passed (141)`；照正文加第 4 处钉的那一轮实测 `Tests 1 failed | 4 passed (5)`（`findAll` 返回 0 项）；Step 2（四条新判据）focused `Tests 4 failed | 5 passed (9)`；Step 3 落地后 `Tests 1 failed | 8 passed (9)`（红的就是 `classes()[0]` 那条自相矛盾），改成 class 归属后 `Tests 9 passed (9)`；Step 5/6 接线与测落地后三文件 focused `33 passed (33)`，全量 `148 passed (148)`。
- Task 10: **计划的三处真缺陷（直查过原文才下的结论）**：
  ① Step 2 的结构判据 `controls.map((c) => c.classes()[0])` 与它自己 Step 3 的模板 `class="btn chat-send"` 互相矛盾——`classes()[0]` 读的是第一个 class 令牌，永远读到 `btn`。实测红：`expected [ 'model-select', 'btn' ] to deeply equal [ 'model-select', 'chat-send' ]`。
  ② Step 1 的第四条钉（`findAll('.chat-controls button')`）早于 Step 3 引入的包裹层，不可能绿（实测见上）。已挪进 Step 3 同轮、同一 commit，判据一条没少。
  ③ **Step 7 的变异自证① 是假预期**：照正文删掉 `opts.includes(modelOverride.value)` 之后，`App.auth-gate.test.js` 实测 `Tests 7 passed (7)` **全绿**。原因很直白——那条测 `setValue('qwen-turbo')` 选中的名字本来就在名单里，门禁删不删结果一样。也就是说照正文交付，`currentModel` 三档解析的中间那档**没有任何判据覆盖**。补了一条「选中的模型被从自己名单里删掉后下拉回落到默认」当牙（场景取 `SettingsModal.applyModels`：删模型只 `patchMe` 名单与默认，碰不到 App 层的 `modelOverride`，这是必然发生的路径），重跑变异才红：`expected '' to be 'qwen-max'`，`1 failed | 7 passed (8)`。终态 148 而不是 147 就是这么来的，不是凑数。
- Task 10: **三条变异自证（手工 Edit + `cp` 备份 + `sha256sum` 双向核对，零脚本）**：① 删 `opts.includes` 门禁 → 补偿测红（形状见上），`App.vue` 复原后 `a32d851f…`；② `if (model_name)` 改成无条件 `payload.model_name = model_name` → 「键都没有」那条红，`expected true to be false`，`1 failed | 16 passed (17)`，`useChat.js` 复原后 `f41d1f1a…`；③ 摘掉 `resetWorkspace()` 里的 `modelOverride.value = ''` → 登出那条红，`expected 'qwen-turbo' to be ''`，`1 failed | 7 passed (8)`，复原同 `a32d851f…`。行尾按字节实测过：同一个文件内部统一，`App.vue`/`useChat.js`/`ChatInput.vue`/`*.css` 是 CRLF，`tests/*.test.js` 是 LF，所以变异只许手改。
- Task 10: **四条裁定（我拍的，终审复核用）**：
  R1: Step 2 的结构判据改成「子节点数 + class 归属」而不是把模板改成 `class="chat-send btn"` — 理由：这句话要钉的契约是"控件行两个子节点、下拉在前发送在后"（它自己的注释就这么写），class 字符串谁在前面不是契约；让测试的形状反过来定义生产代码，下次谁再加一个 `btn-*` 前缀类就又红一次 — 代价：判据不再生成式地"照抄顺序"，读的人要看两条 `toContain` 才知在断顺序。
  R2: Step 1 第四条钉挪进 Step 3 同轮 — 理由：包裹层与依赖它的判据必须同轮，否则 Step 1 "行为零变化、全量照绿"这条性质就丢了 — 代价：Step 1 与 Step 3 的边界从"4 处钉"变成"3 处钉 + 1 处随实现"。
  R3: `ME.user.models` 本轮就从 1 项抬成 2 项，改了 Task 11 "名单给一项"的预设 — 理由：只有一项时 jsdom 的 `select.setValue('qwen-turbo')` 找不到 option、值原样不动，那条测会红在桩上而不是红在接线上 — 代价：Task 11 落 `meUser(over)` 时必须保持两项，这句已写进计划的 Step 6 修订块。
  R4: 补那条计划里没有的「名单收缩后回落」测（终态 148 而非 147） — 理由：不补等于承认 `currentModel` 三分之一无人看守，而计划给的变异自证恰好证明它抓不到 — 代价：与计划的条数不符，必须在计划与台账两处都解释（已做）。
- Task 10: **跨任务冲击（下游消费者）**：① **Task 11 的起点是 148 / 14 files**，`App.auth-gate.test.js` 现在是 **8 条**且 `ME.user.models` 是两项；② 本 Task 让 `resetWorkspace()` 多清一个 `modelOverride`，Task 11 若把横幅的关闭也做成 ref，必须进同一组清理，否则就是"退出后横幅还挂着上一个账号的文案"；③ `useChat.send` 的载荷现在是四键且 `model_name` **可为缺键**（空值不发键），Task 11 的"名单为空 → 禁发"不许把它改成 `model_name: ''`，那条会撞后端 `min_length=1` 的 422；④ CSS 侧 `.chat-input` 已是竖排容器且 `.chat-controls` 是它的第 2 个子节点——Task 11 的 `.setup-banner` 若挂进 `.chat-input` 内部，`ChatInput.test.js` 那条 `kids[1].className` 断言会红（挂 `.chat-body` 则无影响），提前指认省一次红。
- Task 10: **交付时必须对用户说的一条**：模型下拉**默认显示的那一项就是实际发出去的那一项**，除非这个人在设置里把默认模型改了——`currentModel` 的三档（显式选过且还在名单里 → `default_model` → 名单第一项）与后端 `_llm_context` 逐字同口径。三档少一档的表征是"我明明选了 qwen-turbo，账单却是 qwen-max"，这是最难查的一种坏法，本 Task 用它自己的测钉住了中间那档。
- Task 10: **本轮的验证缺口（如实记）**：只交 jsdom 判据，**没做浏览器实测**。`.chat-textarea { flex: 1 }` 在主轴从横转竖之后会不会把输入区压到 `min-height: 44px` 的下限（期望是 `rows=2` 的自然高度）、`.chat-controls` 的右对齐、≤768 档 `flex-wrap` 是否真不撑破 `.chat-input` 的左右内边距——**三条都未量**。本机 `node_modules` 里现在没有 `puppeteer-core`（装它要联网），所以全部挂到 **Task 12 的视口判据**；计划 Step 4 的修订块里已写明要看的三个数与塌了之后的一行修法（`flex: 1` → `flex: none`）。
## Task 11(未配置横幅 + 发送两条路 + 409 归宿 + advisory ③ 两条钉档)

- Task 11: **complete（实现 `7a1aa8e`，7 文件 +144/−8；计划纠偏 `599d5f9`，纯文档 +12/−0；控制者自审 Approved）**。按 23:35 接管裁定：未派实施/评审代理、未抽 brief。流程偏离要在交付时向用户明示。
- Task 11: **三门实数**：`npm test` = `Test Files 14 passed (14)` / `Tests 154 passed (154)`（= 起点 148 + 新增 6，其中 **2 条是钉档**：今天即绿，不是 RED→GREEN）；`npm run build` exit 0（CSS `13.49 kB │ gzip 3.20 kB`、JS `101.15 kB │ gzip 37.89 kB`，Task 10 是 13.14 / 100.61 kB）；G-4 颜色字面量 grep 对 `src/styles/layout.css` 实数 **0**（`.setup-banner` 借 `--status-normal-bg/-fg`，未新增 token）。后端一个字没碰，锚点仍是 **304 / 2 skipped / 2 deselected / 1 warning**。
- Task 11: **分步 RED/GREEN 实数（逐条抄当轮汇总行）**：Step 1（`ME` → `meUser(over)` builder）全量 `Tests 148 passed (148)`，十条既有判据一条没踢翻；Step 2 focused `Test Files 2 failed (2)` / `Tests 4 failed | 17 passed (21)`（四条新判据全红）；Step 3 落地后 focused `Test Files 2 passed (2)` / `Tests 21 passed (21)`（`App.auth-gate` 11、`ChatInput` 10）；Step 4 钉档单文件 `Test Files 1 passed (1)` / `Tests 18 passed (18)`；Step 5 钉档**没有单跑过**，证据只在全量 154 里（148+6 的算术与 14 个文件都对得上，`useChunkSelection.test.js` 现为 11 条）。
- Task 11: **红的形状（计划没写、下一个人会误判的一格）**：App 的第二、三条 RED 不是断言不匹配，而是 `Error: Cannot call text/trigger on an empty DOMWrapper.`——VTU 对不存在的节点直接抛。查红方向因此是"横幅根本没渲染"，不是"文案不对"。第一、四条才是断言红（`expected undefined to be defined`）。
- Task 11: **计划的四处偏差（直查过原文/实跑过才下的结论）**：
  ① Step 1 写"既有 7 条"、起点隐含 147 —— 实际是 **8 条 / 148**（Task 10 修正轮补了回落测）。属老毛病：起点每个 Task 都在漂。
  ② **Step 6 的变异自证② 是方法缺陷，不只是数字偏**：正文写"只删按钮那半句 → 前半句红、后半句仍绿（证明两条路各有牙）"，预设一次运行能同时看到两半；但 **vitest 在第一个失败断言处就中止该 `it()`**，那条测的 Enter 断言根本不会执行，"仍绿"在同一轮里不可观测。补了一次性探针文件（两条 `it`：变异下按钮**没有**被禁用 / Enter 仍发不出 `send`），实测 `Tests 1 failed | 11 passed (12)`——红的 1 条是真判据前半句，探针 2 条全绿；探针**跑完即删、从未进暂存区**，`git status` 干净。结论没变（两条路确实各有牙），变的是证据形状：两次运行，不是一次运行的两半。
  ③ Step 4 与 Step 5 的代码片段都用了 `ApiError`，而两个测试文件**都没有导入它**——不补 `import { ApiError } from '../src/api/client.js'` 就直接 ReferenceError。两处都补了，并在测试里写明"client.js 不在 mock 名单里，导入真实形状才钉得住"。
  ④ Step 4 裁定 4 引用 `App.vue:206-209` 作红色 `error` 横幅的位置——本轮复量 **268-271**（`setupProblem` 在 :57、紫色横幅模板在 :279）。事实成立，行号漂约 62 行；按旧行号去找会落到 `<main v-if="!isLoggedIn">` 那段。
- Task 11: **三条变异自证（手工 Edit + `cp` 备份 + `sha256sum` 双向核对，零脚本）**：① 删 `submit()` 的 `!props.allowSend` → `Tests 1 failed | 9 passed (10)`，红因 `AssertionError: expected [ [ '你好' ] ] to be undefined`（Enter 半句），前半句（按钮 disabled）在同一条测里先行通过 ⇒ 按钮那半句确有牙；② 只删按钮的 `:disabled="!props.allowSend …"` → 真判据红在 `expected undefined to be defined`，Enter 那半句靠 ② 的探针证仍绿（见上）；③ 删 `setupProblem` 第二个 `if` → `Tests 1 failed | 10 passed (11)`，红的正是「凭证齐了但名单为空」那条。复原核对：`ChatInput.vue` 前后同为 `a5521afad5c4…`，`App.vue` 同为 `b2a7d930313e…`；行尾按字节复量未破（`App.vue` 302/302、`ChatInput.vue` 71/71、`layout.css` 422/422 全 CRLF，四个测试文件 0 CR）。
- Task 11: **四条裁定（我拍的，终审复核用）**：
  R1: `.setup-banner` 挂成 `.chat-input` 的**兄弟**（在 `.chat-body` 内、`MessageList` 之后），并在模板注释里写死这个理由 — 理由：计划只说"在两者之间"，而挂进 `ChatInput` 内部会多出一个子节点、顶红 Task 10 的 `kids[1]` 结构判据；横幅要挡的是发送，离得越远越像无关公告 — 代价：横幅与输入框之间只剩 `.chat-input` 自己的 `border-top` 做视觉分隔，窄屏 wrap 后会不会难看未量（挂 Task 12）。
  R2: `meUser()` 的默认值保持 `models` **两项**，未配置变体照计划正文原样用（第一条测的变体是 `models: []` 但 `default_model` 仍是 `'qwen-max'`，比真后端形状松） — 理由：那一条只断言横幅与禁发，`currentModel` 落什么都不参与判据；收紧成 `default_model: null` 会让这一格与计划正文不一致而无收益 — 代价：桩在这一档"不像真响应"，如果将来有人给它加模型下拉的断言，会先在这里红。
  R3: Step 5 的键名用文件里既有的 `const KEY = 'selected_parent_ids'` 而不是再敲字面量 — 理由：同文件其余各条都用 KEY，混用会让"改键名"这种重构只改一处 — 代价：与计划正文差一个字符串常量，已在 Step 5 修订块说明。
  R4: 变异② 的证据缺口用一次性探针文件补，而不是改真判据的断言顺序 — 理由：改顺序等于让测的形状去迁就变异实验；探针文件不进 git，证据链干净 — 代价：台账/计划各多一段"为什么要两次运行"的解释（已写）。
- Task 11: **跨任务冲击（Task 12 消费者）**：① **起点 = 154 passed / 14 files**（`App.auth-gate` 11、`ChatInput` 10、`useChat` 18、`useChunkSelection` 11）；② Task 12 的浏览器判据可直接用 `.setup-banner` / `.setup-open` 两个类名，要量三条：紫横幅确实渲染在输入框正上方且「去设置」点得开、≤768 档 `flex-wrap` 后横幅的 `scrollWidth <= innerWidth`、配齐后横幅消失且发送恢复；③ 真服务上造"未配 key""名单为空"两档**只能走设置端点**（清 api_key / 逐条删模型），不许改库——改了就把 Task 3 的补戳与基线数（活文档 4 / 父块 4 / 子块 10）搅了；④ `ChatInput` 结构判据仍假定 `.chat-input` 两个子节点，Task 12 若为窄屏再包一层就会红；⑤ 载荷形状未变（四键、`model_name` 可为缺键），禁发发生在 ChatInput 层，`useChat` 里没有新增门禁。
- Task 11: **交付时必须对用户说的两条**：① 没配 key / 名单为空的人现在**发不出去**（按钮禁用 + Enter 也挡住），界面上有一条紫横幅点名缺什么、右边「去设置」直接开弹窗——这是 spec 3.4 的事前门，Task 7 只有事后 409；② 409 仍然可能到达（半途被管理员改库、另一个标签页删了模型），它的界面归宿是**既有那条红色横幅**，文案就是后端原句，前端不按状态码改写、也不补打一枪 `/api/auth/me`（裁定与代价在计划 Step 4）。advisory ③ 也从"只有注释担保"变成有判据：hydrate 失败一个本地键都不清，登出/401 才由 `clearSelection()` 抹成 `[]`。
- Task 11: **本轮的验证缺口（如实记）**：只交 jsdom 判据，**没做浏览器实测**。四条未量：`.setup-banner` 的 `margin: 0 20px` 与上下元素的实际贴合、窄屏 `flex-wrap: wrap` 后是否撑破、紫色档 `--status-normal-*` 在真屏幕上的可读性与"是否被当成故障"（这是它选紫的全部理由，却没被看过一眼）、「去设置」开弹窗后焦点与滚动行为。全部挂 **Task 12**（`node_modules` 里仍无 `puppeteer-core`，装它要联网；本机 Edge headless 探针走 `ref-edge-headless-layout-probe` 那条路）。另外「真服务 + 真未配置账号」这一整档只有桩测，端点侧 409 与横幅侧禁发的**联动**（横幅消失后立刻能发）没有跨进程证据。


## Task 12(双端门禁 + 真服务 12 条浏览器判据 + advisory ⑤ + 阶段二收口台账)

- Task 12: **complete（代码一笔 `6ffff74`，1 文件 `backend/tests/test_observability.py` +30/−4，advisory ⑤；台账与计划回写第二笔；控制者自审 Approved）**。按 23:35 接管裁定：未派实施/评审代理、未抽 brief，**12 条浏览器判据由控制者亲跑亲读实数**。流程偏离要在交付时向用户明示。本 Task 没有生产代码交付物，交付物是证据。
- Task 12: **advisory ⑤ 的 RED/GREEN 实数（逐条抄当轮汇总行）**：RED（按计划正文的提示把下界临时写成 `>= 999`，只为证明判据真的在数文件而不是空转）`1 failed, 3 passed, 1 warning in 1.39s`，失败信息 `E assert 23 >= 999`；改回 `>= 22` 后 GREEN `4 passed, 1 warning in 0.70s`；注释口径修正后再复跑 `4 passed, 1 warning in 0.60s`。**覆盖率对账**：新自动发现口径 23 个文件 vs 旧写死清单 23 个，`added: [] / lost: []`——**今天两口径完全重合，所以这条改进是前瞻的**，不能靠"它现在也绿"交差，必须用真实变异证出来：手工放一枚 `backend/tmp_advisory_probe/probe.py`（含 `print`）⇒ 新扫描 `1 failed, 3 passed`，offender 正是它（`{'tmp_advisory_probe\\probe.py': [1]}`），同一文件在旧写死清单下**根本不被看见**（`see probe: False / offenders: []`）。探针目录删掉后 `4 passed`，`git status` 干净、零残留。顺带纠一处计划正文的小口径错误：它写"排除三处"，snippet 里实际有四枚（`tests/__pycache__/data/.venv`），且实测 `backend/` 下今天**没有** `.venv`，所以注释只能写成"纯预防"，不能谎报既成事实。
- Task 12: **三门 + live 四组实数（都是当轮汇总行原文，不含推算）**：
  ① 后端离线全量（**不起 uvicorn**，addopts 已排 migration）`305 passed / 2 skipped / 2 deselected / 1 warning in 71.37s`——比 Task 7 的锚点 304 多的正是本文件新增的那条覆盖率判据；2 个 skip 是 `-m live` 的两条流式测（服务不在）。
  ② `-m "not live and not migration"`（同口径显式版，两个 not 写全）`284 passed / 25 deselected / 1 warning in 63.35s`。
  ③ `-m live`（服务**不在**）`21 passed / 2 skipped / 286 deselected in 40.10s`，两条 skip 原文 `uvicorn :8000 不可用（live 组需要真服务）：timed out`（`test_live_stream.py:72`/`:112`）。
  ④ `-m live`（服务**在**，真跑）`23 passed / 286 deselected / 1 warning in 143.72s`——③ 里那两条现在真红了绿都验过：断流不落半截 + 完整收流落一轮，且**没有一条 skip**（默认用户的 key/名单在 Task 3 的 `seed_default_llm` 里已配齐，够不到"默认用户还没配 key"那条 skip 分支）。
  ⑤ 前端 `npm test` = `Test Files 14 passed (14)` / `Tests 154 passed (154)`（`Duration 7.36s`）；`npm run build` exit 0：`dist/assets/index-CUrklGmJ.css 13.49 kB │ gzip 3.20 kB`、`dist/assets/index-DQP49TXO.js 101.15 kB │ gzip 37.89 kB`、`✓ built in 328ms`；三条样式 grep 实数 **0 / 0 / 0**（layout.css 颜色字面量、组件内 `<style>`、`console.log|debugger`）。
- Task 12: **12 条浏览器判据逐条实数（Edge headless + `puppeteer-core` 25.12.0 `--no-save`；每档视口显式 setViewport 后回读 `innerWidth`）**。视口回读三档全对：1280×900 ⇒ 1280（stage a/b/c 各自回读一次）、375×800 ⇒ 375、500×900 ⇒ 500。**12/12 PASS**，逐条：
  | # | 结果 | 关键实数 |
  |---|---|---|
  | 1 | PASS | 注册 `probe-t12a-…@local.test` → `.user-rail` 在；`railName probe-t12a-muyhowdk`、`railAvatar P` === 昵称首字母大写 |
  | 2 | PASS | `.settings-apikey-input` 的 `type` = `password`；贴入假 key（`sk-PROBE-FAKE-…`）后 `document.body.innerText` **搜不到原文**（`bodyHasFakeKey false`）；掩码初值 `当前密钥：未配置` |
  | 3 | PASS | 加 `qwen-max` ⇒ `.settings-model-row` 1 行且 `.settings-default` 在；删除 ⇒ 0 行，名单那节 hint = `名单是空的——没有模型可选，问答会直接返回 409。` |
  | 4 | PASS（口径改过，见偏差②） | 存真凭证 ⇒ 掩码变 `当前密钥：sk-****62do`、`leaksRawKey false`、横幅**换句**：`还没有配置大模型的 api_key 与路由，点「去设置」填好就能对话` → `模型名单是空的，请先在设置里添加一个模型` |
  | 5 | PASS | 加两枚真模型关弹窗 ⇒ `bannerGone true`、`.model-select` **2 个 option**、`disabledWhenEmpty true` / `disabledWhenTyped false`、选中 `qwen3.8-flash`；发一句 ⇒ `.message` 2 格、答案 45 字、`.error-banner` 不在、气泡 meta `💬 自由对话`。同轮 `/api/auth/me` 形状：`{200, llm_configured true, models [qwen3.7-flash, qwen3.8-flash], default_model qwen3.7-flash}` |
  | 6 | PASS | 新注册不配任何东西：横幅在且含 `api_key`、`.chat-send` disabled；**Enter 也被挡**（打「随便问一句」后 `.message` 数 1→1、无 `.chat-stop`、那句话没出现在消息区）；点 `.setup-open` 开出 `.settings-panel` |
  | 7 | PASS | 配好 + 一枚模型（横幅消失）→ 用 `DELETE /api/auth/me/models/{name}` 绕过界面删掉它（200，App 状态就此过期）→ 界面仍允许发送（`canSend true`）→ 点发送 ⇒ 红色 `.error-banner` 显示后端**原句** `你的模型名单是空的，请先在设置里添加一个模型`，并行 raw `POST /api/chat/stream` 回 **409** 同句，`sameSentence true`。该 stage `consoleErrors=2`（就是这两次故意 409 的 resource 状态码）、`pageErrors=0` |
  | 8 | PASS | A：`.metric` 文档数 `0 → 1`、`.queue-state` `✅ 成功`、候选池 1 张 `.chunk-card` 且含那篇唯一文件名；登出→登录 B：`.metric` 文档数 0、**`.picker-results` 根本不渲染**、空提示 `没有匹配的文档块，换个关键词或分类试试。` |
  | 9 | PASS | 把 A 的 `session_id`（`73ed920c-…`）灌进 B 的 localStorage 再刷新：消息区只有 1 格欢迎占位（含 `.assistant-avatar`）、A 的答案头 40 字**未泄漏**、B 的票打 `GET /api/history/<A 的 sid>` 回 **200 且 body 长度 2**（`[]`）⇒ 读侧 `user_id` 过滤的界面证据 |
  | 10 | PASS | 375 档：`.chat-input` `scrollWidth 355 ≤ innerWidth 375`；`.model-select` rect `x 30 / right 277`、`.chat-send` rect `x 285 / right 345`（y 742.4–778，视口高 800）——两枚控件都在视口内，`.chat-controls` 没塌 |
  | 11 | PASS | 375 档：两行 `.settings-model-row` 各自 `scrollWidth === clientWidth === 309`；`.setup-banner`（全新 C 账号）`scrollWidth === clientWidth === 329 ≤ 375`——`flex-wrap` 真的没撑破 |
  | 12 | PASS | 500 档：`.picker-modal` 与 `.settings-panel` 的 rect 同为 `l 20 / r 480 / t 153 / b 747`，`.chat-send` 在 `t 842.4 / b 878` ⇒ **两块浮层都不压住发送按钮**（`overlap false`×2）；`back500 === 500`；`consoleBase/pageBase = 0` 且 `errNow {console 0, page 0}`、`newErrors []`、`consoleWarnings 0`（基线口径见裁定 R4） |
- Task 12: **探针自己被测出七处缺陷（全部是我的脚本问题，不是应用问题；逐条如实记，因为下一个改判据的人会撞同样的坑）**：
  ① `page.uploadFile` 在 puppeteer-core 25.12.0 **已不存在**（API 移到 `ElementHandle.uploadFile`）⇒ `TypeError`；改成 `page.$('.file-input')` + `handle.uploadFile(path)`。顺带：`.file-input` 生产里 `display:none`，先只动这一条样式让它显形，文件仍走 `onPick → useDocuments` 同一条链路。
  ② `dropModelViaUi` 的 label 字符串引用了只在页面上下文存在的 `n` ⇒ `ReferenceError: n is not defined`（第一次跑连判据 3 都没到）。
  ③ `.settings-hint` 在弹窗里**有两条**（`SettingsModal.vue:172` 改密码那节、`:203` 名单那节），按文档顺序 `txt('.settings-hint')` 读到的是密码那节 ⇒ 判据 3 假红。改成"含 `.settings-add-model` 的那一节里取 hint"。
  ④ 判据 5 第一次读 `.chat-send` 的 disabled 是在**打字之前**：空文本时它被 ChatInput 自己的第二道门 `!modelValue.trim()` 挡住，于是把 Task 11 的 `allowSend` 误判成没生效。现在两个时刻都读（空=true、打完字=false），这一改反而把 Task 11 那半句判据钉得更准。
  ⑤ `tmp-edge-profile` 跨次运行**留着 `auth_token`** ⇒ 第二次直接落进工作区、注册流程找不到 `.auth-panel`。四个 stage 一律先 `wipeStorage()`。
  ⑥ 判据 6 的"没发出东西"不能按 `.message === 0` 断：`MessageList.vue:41` 的 `v-if="!props.messages.length"` 让空历史也占**一格欢迎气泡**；改成"前后相等 + 打进去的话没出现在消息区"。判据 8 的 B 侧同理不能等 `.picker-results` 非空（空池才是正确行为），要等终态三选一，且 `.picker-hint` 的「搜索中…」不算终态（`ChunkPickerModal.vue:119/132` 两类共用一个类名）。
  ⑦ B 那档第一次跑挂了但账号已注册、已配 key ⇒ 重跑必撞"已配置"，加 `bRuns` 邮箱轮换（本轮用到 `-r2`，实测三条 B 邮箱都在库里，清理账一起清了）。
- Task 12: **计划的三处真缺陷（直查原文 + 实跑才下的结论，均已用 `> 修订块` 回写正文）**：
  ① **Step 3 的算术 `153` 过期**：它按"117 + 14 + 10 + 6 + 6"对账，但 Task 10 的修正轮补了一条计划里没有的回落测（台账当时就记成 148 而非 147）。本轮实测 **154**。属"计划数字一律实测"这条老规矩的又一次兑现，不是凑数。
  ② **Step 5 判据 4 的"`.setup-banner` 当场消失"在那一状态下不可达**：判据 3 刚把名单删空，`setupProblem` 的第二条门（名单空）仍成立，正确行为是**换句**而不是消失。这一换恰恰是 `patchMe` 当场把新 user 落进 App 状态的证据，比"消失"更强；"消失"留给判据 5（加完两枚模型之后）验。
  ③ **Step 5 判据 7 给的"或直接 `fetch('/api/chat/stream', …)`"造不出界面横幅**：那条只证明后端回 409，红色 `.error-banner` 永远不出现——它由 `useChat` 的 catch 写进 App 的 `error`，必须**让界面自己发**。可用做法：先配齐并加一枚模型（横幅消失、App 状态有模型），再用 `DELETE /api/auth/me/models/{name}` 绕过界面把服务端名单清空，此刻界面仍以为能发 ⇒ 点发送 ⇒ 409 落到红色横幅。
- Task 12: **五条裁定（我拍的，终审复核用）**：
  R1: 探针从 `backend/.env` 直读 `DASHSCOPE_API_KEY`/`DASHSCOPE_BASE_URL`/`LLM_MODEL` 三键、只填进 DOM 输入框 — 理由：判据 4/5 必须用真凭证才验得出掩码与真 409，"由用户手工粘贴"会让 12 条判据不可重跑、也不可信；红线是**值不外印**：不进 console、不进 `tmp-probe-out.json`、不进断言消息，落盘的只有布尔与长度（`sk-****62do` 是后端给的掩码，不是原文）— 代价：脚本里有一段读 .env 的代码，读台账的人要相信它的实现（本条即为该信任的担保，`envVals()`/`record()` 的实现全文附在下方）。**另记一条我自己的过程错误**：第一次解析 .env 时判"路由两键缺一"，因为值被引号包着而我没剥——`os.getenv` 走 python-dotenv 会剥，裸正则不剥；这类"环境差异"要先怀疑解析器，别急着断言配置坏了。
  R2: 判据 4 断"句子切换"不断"横幅消失" — 理由见偏差② — 代价：与计划原文不一致，须回写（已回写），且读的人要明白判据 5 才是消失的那一格。
  R3: 判据 7 用"界面状态过期"造真 409 — 理由：Task 11 的归宿判据是"后端原句进红色横幅"，绕过 UI 的 fetch 打不到那条链路 — 代价：多一次 raw DELETE，且 stage b 结尾就把该账号留在半套配置上，所以 c/d 都重新登录、不复用它的界面状态。
  R4: 判据 12 的"零 error"限定为"登录成功之后不再新增"，`consoleBase/pageBase` 取在 `loginUser` 之后 — 理由：`wipeStorage()` 带着上一轮遗留的过期票进首页，`/api/auth/me` **必回 401**，那是 Task 8 的"票过期落回登录页"设计路径、是 resource 级状态码不是页面 JS 错误；把它算成故障会把设计判成 bug — 代价：判据 12 的口径比计划原文窄一格，台账必须写清基线取点（已写），且**跨 stage 的 error 计数不再可比**。
  R5: 污染清理走"API 删父块 → 关系库按主键删行"两步，删行前先确认 `parent_chunks` 归零 — 理由：向量只能由持有 Chroma 单实例的进程删（本机铁规矩），脚本若先删行就留下"子块照旧被召回、父块取不出来"的无把手向量（`api/documents.py:142` 那段注释讲的正是这个坏法）— 代价：清理要跑两轮（只读→删除），且只读那轮必须把将删的东西逐行打印出来（本轮就靠它发现 `documents` 还剩 3 行 `chunk_count=0` 的空壳——**顺带纠正一处我的误读**：`delete_parent_chunk` 并不会带走 `documents` 行，界面上"文档数 0"是查询侧过滤掉了空壳，不是行没了）。
- Task 12: **污染清理账（实数，一条都不虚）**：
  - 探针账号 **7 枚**（`users.id` 611–617：三次早期失败的 A、判据用的 A、B 的两档 `-r2` 与基础邮箱、stage d 新注册的 C）；连带删除 `auth_tokens 16`、`user_models 4`、`chat_history 2`（A 那次真问答 + 一次早期残留）、`documents 3`（`chunk_count` 全为 0，向量已在 API 侧逐块删掉，DELETE 各回 200）；删后复读 `matched users: 0`。
  - 临时文件全删：`frontend/tmp-layout-probe.mjs`（**内容全文附在本节下方**）、`tmp-probe-state.json`、`tmp-probe-out.json`、`tmp-probe-data.mjs`、`backend/tmp_probe_cleanup.py`、`frontend/probe-doc-*.txt`、`tmp-edge-profile/`、`tmp-probe-profile/`。提交前 `git status` 只看见 `progress.md` 与计划文件两处。
  - `puppeteer-core` 走 `npm i --no-save`：`package.json` / `package-lock.json` 实测**零 diff**（`git status` 里两文件从头到尾没出现过），残留只在 `frontend/node_modules/puppeteer-core`。**计划 Step 7 明令不许用 `git checkout --` 掩盖 diff**：本轮没有 diff 可掩盖，该条纪律记为"未触发"。
  - **库内基线未破（删完之后的只读盘点原文，`tmp_probe_audit.py` 跑完即删）**：`users_total = 2`、`users_probe_left = 0`、`tokens_total = 1`、`tokens_of_first_user = 0`、`documents_total = 13`、`documents_active = 4`、`documents_probe_left = 0`、`parent_chunks = 4`、`child_chunks = 10`、`chat_history_total = 43`、`user_models_total = 1`。**对账三处**：活文档 4 / 父块 4 / 子块 10 与 Task 11 台账记的基线**逐字相同**（那句"不许改库，改了就把补戳与基线数搅了"守住了）；`chat_history = 43` 与 Task 6 的 `chat_rows_claimed = 43` 相同；`documents_total 13` 里 9 行是 `is_active=0` 的既有归档行，不是探针留下的。⇒ 探针污染清干净了，既有数据一格没动。
- Task 12: **Step 7 第二笔的一处执行细节（计划正文的命令在本机跑不通）**：`.superpowers/sdd/.gitignore` 的内容是 `*`，所以计划里那句裸 `git add .superpowers/sdd/…/progress.md` 会被 git 拒绝（实测退码 1，且**只**把计划文件 staged 了——台账留在 unstaged 空档里，容易误以为已经提交）。改用 `git add -f` 只强推 `progress.md` 一个文件，与阶段一先例逐字一致（`git ls-files` 显示阶段一目录下**只有** `progress.md` 入库，`task-*-brief.md` / `task-*-report.md` / `review-*.diff` 一律不入库），本轮 Task 12 目录下那十几份 brief/review/diff/uvicorn 日志同样保持未跟踪。
- Task 12: **五条 advisory 逐条销账（阶段一终审开工单第 389 行那五条）**：
  ① `migrations.py:184-189` 补戳窗口 → **Task 3** `a1720ce`（步骤 4 抄三键 + 补戳自愈）+ 修正轮 `fd6a4c6`。
  ② `client.js:55` 令牌过期只弹横幅不自动登出 → **Task 8** `da641fa`（401 落回登录页 + `Error` 带状态码）；本 Task 判据 12 的 401 基线就是它在真服务上的表现。
  ③ hydrate 失败路径的本地键判据 → **Task 11** `7a1aa8e`（两条钉档：失败一个键都不清 / 登出必由 `clearSelection()` 抹成 `[]`）。
  ④ `test_live_stream.py` 令牌无界增长 → **Task 2** `50d8587`（live 断言同步：测尾登出）；**Task 7** 真服务复核 `auth_tokens` 默认用户残留 `0 → 0`；本 Task 的 ④ 组 23 条真跑之后再次只读盘点：`auth_tokens` **默认用户（`users.id=30`，`default@local`）名下 0 枚**，全库剩 **1 枚**（`auth_tokens.id=185`，属 `users.id=338`＝用户本人 2026-10-07 22:25 自己注册的账号，TTL 到 2026-11-06）。**那一枚与那个账号都不是探针产物，清理脚本按 `identifier LIKE 'probe-t12%'` 收口，绝不误伤**——这也是"只按主键/精确模式删行"这条纪律的实际收益。
  ⑤ `test_observability.py:16-17` 扫描目录写死 → **本 Task** `6ffff74`。
- Task 12: **挂账清单（本轮发现、不在阶段二范围，一条条列，不写"无"）**：
  - `frontend/node_modules/puppeteer-core`（+`tmp-edge-profile` 习惯）残留：`--no-save` 不脏 `package.json`，但脏了 `node_modules`，与仓库锁文件口径不一致，要不要清是独立决定。
  - `%2F` 代理归一化风险（阶段一起就挂着）：本 Task 判据 7/9 都用了 `encodeURIComponent` 的裸 fetch，**没验**过 Vite 代理对含 `/` 的 session_id 会不会归一化——那是 live 侧已知的另一格。
  - 判据 12 只量了两块浮层的 rect，**没验** backdrop 点击关闭与 Esc 关闭在真浏览器的表现（jsdom 判据有，界面未量）。
  - 375 档**没量**紫横幅的实际观感（Task 11 遗留的"可读性/会不会被当故障"仍未看，本轮只验了几何不撑破）。
  - 判据 4/5 与 live ④ 组烧的是**真实配额**（2 次界面问答 + 23 条 live 里的真流式往返），默认用户与探针账号共用同一枚 `.env` key。
  - `documents` 表允许留下 `chunk_count=0` 的空壳行（`delete_parent_chunk` 不带走它）：界面隐藏、库里存在，是既有语义，不属于本阶段；若要闭合需另定"最后一块删掉后文档是否消失"的产品口径。
- Task 12: **交付时必须对用户说的两句（计划 Step 8 原文要求）**：① **建议轮换 `DEFAULT_USER_PASSWORD`**；② **阶段二起未配 key 的用户开始收 409**，是预期翻转不是回归，且第一条 409 的文案是「你的模型名单是空的」而不是「没配 api_key」（`_llm_context` 先判名单空、后验凭证），别按文案去找 key。此外本 Task 还要补第三句：**12 条浏览器判据全部在真服务 + 真凭证上跑过，12/12 绿**，Task 9/10/11 各自挂下来的"界面未量"条目本轮全部闭合（掩码显示、`flex-wrap`、横幅贴合、浮层遮罩、历史与文档隔离）。
- Task 12: **本轮的验证缺口（如实记）**：12 条判据都是**几何与文案层面**的界面证据，没做**跨浏览器**（只有本机 Edge headless）、没做**真触屏**（375 档是视口模拟不是设备模拟，`touch` 行为未验）、也没做**并发**（两个标签页同时改名单那条只有 Task 10 的补偿测，界面未量）。默认用户那档在本轮只以 live ④ 组的身份出现，没在界面上手验。

### 附：Task 12 探针脚本全文（`frontend/tmp-layout-probe.mjs`，跑完即删，故全文留档）

```js
// 阶段二 Task 12 的浏览器判据探针（用完即删，内容贴进台账）。
// 用法：node tmp-layout-probe.mjs <a|b|c|d>
//   a = 判据 1-5（注册用户 A + 配置 + 名单 + 问答）
//   b = 判据 6-7（注册 B：未配置门 + 真 409 落红色横幅）
//   c = 判据 8-9（文档隔离 + 历史隔离）
//   d = 判据 10-12（375 / 500 两档几何 + 控制台零 error）
// 凭证纪律：本文件从 backend/.env 取 DASHSCOPE_API_KEY / DASHSCOPE_BASE_URL 填进浏览器输入框，
// 值不进 console、不进 tmp-probe-out.json、不进断言消息；落盘的只有布尔与长度。
import fs from 'node:fs'
import path from 'node:path'
import puppeteer from 'puppeteer-core'

const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
const APP = 'http://127.0.0.1:5173/'
const STATE_FILE = 'tmp-probe-state.json'
const OUT_FILE = 'tmp-probe-out.json'
const stage = (process.argv[2] || 'a').toLowerCase()

const out = { stage, judgements: [], consoleErrors: [], pageErrors: [], consoleWarnings: [], notes: [] }
function note(s) { out.notes.push(s); console.log('NOTE ' + s) }
function record(n, name, pass, detail) {
  out.judgements.push({ n, name, pass, detail })
  console.log(`J${n} ${pass ? 'PASS' : 'FAIL'} ${name} :: ${JSON.stringify(detail)}`)
}

function envVals() {
  const txt = fs.readFileSync(path.resolve('../backend/.env'), 'utf8')
  const get = (k) => {
    const m = txt.match(new RegExp('^' + k + '=(.*)$', 'm'))
    if (!m) return ''
    return m[1].trim().replace(/^"/, '').replace(/"$/, '').trim()
  }
  return { key: get('DASHSCOPE_API_KEY'), base: get('DASHSCOPE_BASE_URL'), model: get('LLM_MODEL') || 'qwen3.7-flash' }
}

function loadState() {
  if (!fs.existsSync(STATE_FILE)) throw new Error('state file missing: run stage a first')
  return JSON.parse(fs.readFileSync(STATE_FILE, 'utf8'))
}
function saveState(s) { fs.writeFileSync(STATE_FILE, JSON.stringify(s, null, 2), 'utf8') }

const browser = await puppeteer.launch({
  executablePath: EDGE,
  headless: true,
  args: ['--no-sandbox', '--disable-dev-shm-usage', '--user-data-dir=' + path.resolve('tmp-edge-profile')],
})
const page = await browser.newPage()
page.on('console', (m) => {
  const t = m.type()
  if (t === 'error') out.consoleErrors.push(m.text())
  else if (t === 'warning') out.consoleWarnings.push(m.text())
})
page.on('pageerror', (e) => out.pageErrors.push(String(e && e.message ? e.message : e)))

const exists = (sel) => page.evaluate((s) => !!document.querySelector(s), sel)
const countOf = (sel) => page.evaluate((s) => document.querySelectorAll(s).length, sel)
const txt = (sel) => page.evaluate((s) => { const e = document.querySelector(s); return e ? e.textContent : null }, sel)
const bodyText = () => page.evaluate(() => document.body.innerText)
const attr = (sel, name) => page.evaluate(([s, n]) => { const e = document.querySelector(s); return e ? e.getAttribute(n) : null }, [sel, name])
const disabled = (sel) => page.evaluate((s) => { const e = document.querySelector(s); return !!e && e.disabled }, sel)
async function setVal(sel, val) {
  await page.evaluate(([s, v]) => {
    const el = document.querySelector(s)
    if (!el) throw new Error('no element ' + s)
    el.value = v
    el.dispatchEvent(new Event('input', { bubbles: true }))
  }, [sel, val])
}
async function typeInto(sel, val) { await page.click(sel); await page.type(sel, val) }
async function waitFor(predFn, ms, label, ...args) {
  try { await page.waitForFunction(predFn, { timeout: ms, polling: 500 }, ...args) }
  catch (e) { throw new Error('timeout waiting: ' + label + ' :: ' + String(e.message).slice(0, 80)) }
}
// ≤768 时 .side-panel 整个 display:none（layout.css:101），抽屉不开就点不到 .rail-* 与上传入口
async function ensurePanelOpen() {
  const needs = await page.evaluate(() => {
    const el = document.querySelector('.side-panel')
    return !!el && getComputedStyle(el).display === 'none'
  })
  if (!needs) return false
  await page.click('.panel-toggle')
  await waitFor(() => { const el = document.querySelector('.side-panel'); return el && getComputedStyle(el).display !== 'none' }, 10000, 'side panel opened')
  return true
}
async function setViewport(w, h) {
  await page.setViewport({ width: w, height: h })
  const back = await page.evaluate(() => innerWidth)
  note(`viewport ${w}x${h} readback innerWidth=${back}`)
  return back
}

// —— 登录/注册流程：一律按类名定位（textContent 匹配会随文案变）——
const authInputs = () => page.$$('.auth-form input.picker-input')
async function openAuth() {
  await page.goto(APP, { waitUntil: 'networkidle2' })
  await waitFor(() => !!document.querySelector('.auth-panel'), 20000, '.auth-panel')
}
// tmp-edge-profile 会跨次运行留着 auth_token：不清就直接落进工作区，注册流程找不到 .auth-panel。
async function wipeStorage() {
  await page.goto(APP, { waitUntil: 'networkidle2' })
  const had = await page.evaluate(() => { const k = Object.keys(localStorage); localStorage.clear(); return k })
  note(`wipeStorage cleared keys: ${JSON.stringify(had)}`)
}
async function registerUser(identifier, password, nickname) {  await openAuth()
  await page.click('.picker-tabs .picker-tab:nth-child(2)')   // 注册
  await waitFor(() => !!document.querySelector('.auth-form select'), 10000, 'register tab shape')
  const ins = await authInputs()
  await ins[0].type(identifier)
  await page.select('.auth-form select.picker-input', 'email')
  await ins[1].type(password)
  if (nickname) await ins[2].type(nickname)
  await page.click('.auth-submit')
  await waitFor(() => !!document.querySelector('.user-rail'), 30000, '.user-rail after register')
}
async function loginUser(identifier, password) {
  await openAuth()
  await page.click('.picker-tabs .picker-tab:nth-child(1)')   // 登录
  const ins = await authInputs()
  await ins[0].type(identifier)
  await ins[1].type(password)
  await page.click('.auth-submit')
  await waitFor(() => !!document.querySelector('.user-rail'), 30000, '.user-rail after login')
}
async function openSettings() { await ensurePanelOpen(); await page.click('.rail-settings'); await waitFor(() => !!document.querySelector('.settings-panel'), 15000, '.settings-panel') }
async function closeSettings() { await page.click('.settings-panel .picker-close'); await waitFor(() => !document.querySelector('.settings-panel'), 10000, 'settings closed') }
async function signOut() { await ensurePanelOpen(); await page.click('.rail-signout'); await waitFor(() => !!document.querySelector('.auth-panel'), 20000, '.auth-panel after signout') }
// 弹窗的终态有三种：有结果（.picker-results）、池是空的（.picker-hint）、加载失败（.picker-error）。
// 判据 8 的 B 侧与判据 12 的未配置账号都该落在"空池"那一格，所以这里等的是终态而不是非空。
// 但 .picker-hint 有两个身份：busy 时写「搜索中…」（v-if="busy"），空池才写「没有匹配的文档块」
// （v-else，ChunkPickerModal.vue:119/132）——带「搜索中」的那格不是终态。
async function openPicker() {
  await ensurePanelOpen()
  await page.click('.picker-open')
  await waitFor(() => {
    if (document.querySelector('.picker-error')) return true
    const r = document.querySelector('.picker-results')
    if (r && r.textContent.length > 0) return true
    const hint = document.querySelector('.picker-hint')
    return !!hint && !hint.textContent.includes('搜索中')
  }, 40000, 'picker settled')
}
async function addModelViaUi(name) {
  await setVal('.settings-model-input', name)
  await page.click('.settings-model-add')
  await waitFor((n) => Array.from(document.querySelectorAll('.settings-model-name')).some((e) => e.textContent === n), 20000, 'model row ' + name, name)
}
async function dropModelViaUi(name) {
  const idx = await page.evaluate((n) => {
    const rows = Array.from(document.querySelectorAll('.settings-model-row'))
    return rows.findIndex((r) => r.querySelector('.settings-model-name').textContent === n)
  }, name)
  if (idx < 0) throw new Error('model row missing: ' + name)
  await page.evaluate(([n]) => {
    const rows = Array.from(document.querySelectorAll('.settings-model-row'))
    const row = rows.find((r) => r.querySelector('.settings-model-name').textContent === n)
    row.querySelector('.settings-model-drop').click()
  }, [name])
  await waitFor((n) => !Array.from(document.querySelectorAll('.settings-model-name')).some((e) => e.textContent === n), 20000, 'model dropped ' + name, name)
}

// ============================================================ stage a：判据 1-5
if (stage === 'a') {
  await wipeStorage()
  const env = envVals()
  if (!env.key || !env.base) throw new Error('.env 的 key/路由两键缺一，判据 4/5 不可跑')
  const ts = Date.now().toString(36)
  const emailA = `probe-t12a-${ts}@local.test`
  const pw = 'probe-pass-123'
  const modelMain = env.model
  const modelSecond = 'qwen3.8-flash'
  note('models chosen: ' + modelMain + ' + ' + modelSecond)

  await setViewport(1280, 900)
  await registerUser(emailA, pw, '')

  // J1 进工作区 + 头像取昵称首字母
  const railName = await txt('.rail-name')
  const railAvatar = await txt('.rail-avatar')
  const expectAvatar = railName ? Array.from(railName.trim())[0].toUpperCase() : null
  record(1, 'register -> workspace + rail avatar', (await exists('.user-rail')) && railAvatar === expectAvatar && !!railName,
    { userRail: await exists('.user-rail'), railName, railAvatar, expectAvatar })

  // J2 api_key 输入框是 password，且贴进去的原文在页面上搜不到
  const FAKE_KEY = 'sk-PROBE-FAKE-0123456789abcdef'
  await openSettings()
  const keyType = await attr('.settings-apikey-input', 'type')
  await setVal('.settings-apikey-input', FAKE_KEY)
  const maskedBefore = await txt('.settings-masked')
  const bodyHasFake = (await bodyText()).includes(FAKE_KEY)
  record(2, 'apikey input is password + raw key not in body text', keyType === 'password' && !bodyHasFake,
    { keyType, bodyHasFakeKey: bodyHasFake, maskedBefore })

  // J3 名单加一行带"默认"、删干净后归零并出提示（提示要限定到模型名单那一节，
  //    弹窗里 .settings-hint 有两条：改密码那节先出现，按文档顺序读会读到它）
  const modelsHint = () => page.evaluate(() => {
    const section = Array.from(document.querySelectorAll('.settings-section'))
      .find((s) => s.querySelector('.settings-add-model'))
    const hint = section && section.querySelector('.settings-hint')
    return hint ? hint.textContent.trim() : null
  })
  await addModelViaUi('qwen-max')
  const rowsAfterAdd = await countOf('.settings-model-row')
  const hasDefault = await exists('.settings-default')
  await dropModelViaUi('qwen-max')
  const rowsAfterDrop = await countOf('.settings-model-row')
  const hint = await modelsHint()
  record(3, 'model list add->row+default, drop->zero+hint',
    rowsAfterAdd === 1 && hasDefault && rowsAfterDrop === 0 && !!hint && hint.includes('名单是空的'),
    { rowsAfterAdd, hasDefault, rowsAfterDrop, hint })

  // J4 存真凭证：掩码变新、原文不外泄、横幅当场换文案。
  //    注意这里横幅不许"消失"——判据 3 刚把名单清空，setupProblem 的第二条门（名单空）
  //    仍然成立，正确行为是从「还没有配置…api_key…」换成「模型名单是空的…」。
  //    这一换正是 patchMe 当场把新 user 落进 App 状态的证据。
  const bannerBefore = await txt('.setup-banner')
  await setVal('.settings-apikey-input', '')
  await setVal('.settings-apikey-input', env.key)
  await setVal('.settings-baseurl-input', env.base)
  await page.click('.settings-llm-save')
  await waitFor(() => { const m = document.querySelector('.settings-masked'); return m && m.textContent.includes('****') }, 20000, 'masked ****')
  const maskedAfter = await txt('.settings-masked')
  const bodyTextAfter = await bodyText()
  const bannerAfterSave = await txt('.setup-banner')
  record(4, 'save credentials -> new mask + no raw key + banner switches sentence',
    maskedAfter.includes('****') && !bodyTextAfter.includes(env.key) &&
    !!bannerBefore && bannerBefore.includes('api_key') &&
    !!bannerAfterSave && bannerAfterSave.includes('模型名单是空的') && !bannerAfterSave.includes('api_key'),
    { maskedAfter, leaksRawKey: bodyTextAfter.includes(env.key), bannerBefore, bannerAfterSave })

  // J5 两枚模型（弹窗仍开着才加得了）-> 关弹窗 -> 两个 option、横幅真的消失、可发送、
  //     选第二个模型发一句 -> 答案气泡且无红色横幅
  await addModelViaUi(modelMain)
  await addModelViaUi(modelSecond)
  await closeSettings()
  const bannerGone = !(await exists('.setup-banner'))
  const optionCount = await countOf('.model-select option')
  // 两道门要分开读：空文本时 disabled 是 ChatInput 的第二道门（!modelValue.trim()），
  // 打完字还 disabled 才是 allowSend 没放开——Task 11 的 allowSend 只能在这一刻被验出来。
  const disabledWhenEmpty = await disabled('.chat-send')
  await setVal('.chat-textarea', '你好，用一句话说你是谁')
  const disabledWhenTyped = await disabled('.chat-send')
  await page.select('.model-select', modelSecond)
  const selectedNow = await page.evaluate(() => document.querySelector('.model-select').value)
  await page.click('.chat-send')
  await waitFor(() => !document.querySelector('.chat-stop') && (() => {
    const bubbles = document.querySelectorAll('.chat-messages .message-content')
    return bubbles.length >= 2 && bubbles[bubbles.length - 1].textContent.trim().length > 0
    })(), 240000, 'assistant answer streamed')
  const bubbleCount = await countOf('.chat-messages .message')
  const lastBubble = await page.evaluate(() => {
    const b = document.querySelectorAll('.chat-messages .message-content')
    return b.length ? b[b.length - 1].textContent : null
  })
  const errBanner = await exists('.error-banner')
  const usedModel = await page.evaluate(() => {
    const meta = document.querySelectorAll('.chat-messages .bubble-meta')
    return meta.length ? meta[meta.length - 1].textContent : null
  })
  record(5, 'banner gone after models + two options + send enables on typing + answer bubble via 2nd model, no error banner',
    bannerGone && optionCount === 2 && disabledWhenEmpty && !disabledWhenTyped &&
    selectedNow === modelSecond && bubbleCount >= 2 && !errBanner && !!lastBubble,
    { bannerGone, optionCount, disabledWhenEmpty, disabledWhenTyped, selectedNow, bubbleCount, answerChars: (lastBubble || '').length, answerHead: (lastBubble || '').slice(0, 24), errBanner, bubbleMeta: usedModel })

  const sessionA = await page.evaluate(() => localStorage.getItem('session_id'))
  const meShape = await page.evaluate(async () => {
    const r = await fetch('/api/auth/me', { headers: { Authorization: 'Bearer ' + localStorage.getItem('auth_token') } })
    const j = await r.json()
    return { status: r.status, llm_configured: j.user.llm_configured, models: j.user.models, default_model: j.user.default_model }
  })
  saveState({ ts, emailA, emailB: `probe-t12b-${ts}@local.test`, emailC: `probe-t12c-${ts}@local.test`, pw,
    modelMain, modelSecond, sessionA, answerHead: (lastBubble || '').slice(0, 40), docName: `probe-doc-${ts}.txt`, meShape })
  note('stage a state saved; me shape ' + JSON.stringify(meShape))
}

// ============================================================ stage b：判据 6-7
if (stage === 'b') {
  await wipeStorage()
  const env = envVals()
  const st = loadState()
  // B 每轮换新邮箱：判据 6 要的是"从没配过任何东西"的现场，而上一轮的 B 已经被判据 7 配好了；
  // 复用还会让注册撞 409、卡在登录页。
  st.bRuns = (st.bRuns || 0) + 1
  const emailB = st.bRuns === 1 ? st.emailB : st.emailB.replace('@local.test', `-r${st.bRuns}@local.test`)
  note(`stage b run #${st.bRuns} as ${emailB}`)
  await setViewport(1280, 900)
  await registerUser(emailB, st.pw, '')

  // J6 未配 key 的门：横幅在、文案含 api_key、打字也不许发、点「去设置」能开弹窗
  const bannerText = await txt('.setup-banner')
  await setVal('.chat-textarea', '随便问一句')
  const sendDisabled = await disabled('.chat-send')
  // Enter 是发送的第二条路（ChatInput.submit 里那道 allowSend 门），必须单独钉：
  // 按钮 disabled 只挡住鼠标，挡不住键盘。
  await page.focus('.chat-textarea')
  const beforeEnter = await page.evaluate(() => document.querySelectorAll('.chat-messages .message').length)
  await page.keyboard.press('Enter')
  await page.evaluate(() => new Promise((r) => setTimeout(r, 2000)))
  const afterEnter = await page.evaluate((typed) => ({
    // 欢迎气泡（MessageList.vue:41 的 v-if="!messages.length"）本来就占一格 .message，
    // 所以判据只能是"前后不变 + 打进去的话没出现在消息区"，不是"等于 0"。
    messages: document.querySelectorAll('.chat-messages .message').length,
    streaming: !!document.querySelector('.chat-stop'),
    questionLeaked: document.querySelector('.chat-messages').textContent.includes(typed),
  }), '随便问一句')
  await page.click('.setup-open')
  await waitFor(() => !!document.querySelector('.settings-panel'), 15000, 'settings opened by .setup-open')
  const openedByBanner = await exists('.settings-panel')
  await closeSettings()
  record(6, 'unconfigured gate: banner text + disabled send + Enter also blocked + banner opens settings',
    !!bannerText && bannerText.includes('api_key') && sendDisabled &&
    afterEnter.messages === beforeEnter && !afterEnter.streaming && !afterEnter.questionLeaked && openedByBanner,
    { bannerText, sendDisabled, beforeEnter, afterEnter, openedByBanner })

  // J7 真 409：界面允许发送（本地状态还有模型）而后端名单已空
  await openSettings()
  await setVal('.settings-apikey-input', env.key)
  await setVal('.settings-baseurl-input', env.base)
  await page.click('.settings-llm-save')
  await waitFor(() => { const m = document.querySelector('.settings-masked'); return m && m.textContent.includes('****') }, 20000, 'masked ****')
  await addModelViaUi(st.modelMain)
  await closeSettings()
  const bannerAfterConfig = await exists('.setup-banner')
  // 绕开界面的 patchMe：直接用 fetch 删掉服务端那一枚模型，App 的 user.models 就此过期
  const rawDelete = await page.evaluate(async (name) => {
    const r = await fetch('/api/auth/me/models/' + encodeURIComponent(name), {
      method: 'DELETE', headers: { Authorization: 'Bearer ' + localStorage.getItem('auth_token') } })
    return { status: r.status, body: await r.text() }
  }, st.modelMain)
  const rawProbe = await page.evaluate(async (sessionId) => {
    const r = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + localStorage.getItem('auth_token') },
      body: JSON.stringify({ session_id: sessionId, question: '探针：不该发出去', parent_ids: [], model_name: null }),
    })
    return { status: r.status, body: (await r.text()).slice(0, 400) }
  }, await page.evaluate(() => localStorage.getItem('session_id')))
  // 界面仍然认为名单里有一枚模型（没重新 /me），点发送 -> 后端 409 -> 红色横幅
  await setVal('.chat-textarea', '这条会撞上 409')
  const canSend = !(await disabled('.chat-send'))
  await page.click('.chat-send')
  await waitFor(() => !!document.querySelector('.error-banner'), 60000, 'red error banner after 409')
  const uiBanner = await txt('.error-banner')
  const serverSentence = await page.evaluate((body) => {
    try { return JSON.parse(body).detail || body } catch (e) { return body }
  }, rawProbe.body)
  const sameSentence = uiBanner.includes(typeof serverSentence === 'string' ? serverSentence : String(serverSentence))
  record(7, '409 lands in red .error-banner with the backend sentence',
    bannerAfterConfig === false && rawDelete.status === 200 && rawProbe.status === 409 && canSend && sameSentence,
    { bannerAfterConfig, rawDeleteStatus: rawDelete.status, rawProbeStatus: rawProbe.status,
      serverSentence, uiBanner, canSend, sameSentence })
  st.emailBUsed = emailB
  saveState(st)
}

// ============================================================ stage c：判据 8-9
if (stage === 'c') {
  await wipeStorage()
  const st = loadState()
  await setViewport(1280, 900)

  // J8 文档隔离：A 传一篇唯一文件名的探针文档 -> 文档数 1 + 候选池可见；换 B -> 0 篇 + 看不见
  await loginUser(st.emailA, st.pw)
  const metricBefore = await txt('.metric')
  const docPath = path.resolve(st.docName)
  fs.writeFileSync(docPath, `探针文档 ${st.docName}\n\n这段文字只用于阶段二 Task 12 的界面隔离判据。它讲的是一个不存在的城市：纸桥城，城里有三座塔。\n`, 'utf8')
  // .file-input 在生产里 display:none（用户点的是 label），puppeteer 需要可交互节点：
  // 临时显形只动这一个样式，选择的文件仍经 onPick → useDocuments 的同一条链路。
  await page.evaluate(() => { document.querySelector('.file-input').style.display = 'inline-block' })
  // puppeteer-core 25 把 uploadFile 从 Page 挪到了 ElementHandle（page.uploadFile 已不存在）。
  const fileHandle = await page.$('.file-input')
  await fileHandle.uploadFile(docPath)
  await waitFor(() => { const m = document.querySelector('.metric'); return m && /文档数\s+1/.test(m.textContent) }, 420000, 'metric 文档数 1')
  const metricAfter = await txt('.metric')
  const queueState = await txt('.queue-state')
  await openPicker()
  const pickerHasDocA = await page.evaluate((name) => {
    const r = document.querySelector('.picker-results')
    return !!r && r.textContent.includes(name)
  }, st.docName)
  const pickerCardsA = await countOf('.picker-results .chunk-card')
  await page.click('.picker-close')

  await signOut()
  await loginUser(st.emailBUsed || st.emailB, st.pw)
  const metricB = await txt('.metric')
  await openPicker()
  // 空池时 .picker-results 不渲染（ChunkPickerModal.vue 的 v-else-if 走 .picker-hint），
  // 所以 B 侧的证据是"没有结果节点 + 那句空提示"，不是空字符串。
  const pickerResultsB = await exists('.picker-results')
  const pickerHintB = (await txt('.picker-hint')) || ''
  const pickerHasDocB = pickerResultsB && (await txt('.picker-results')).includes(st.docName)
  await page.click('.picker-close')
  record(8, 'document isolation: A sees 1 + own file, B sees 0 + empty pool',
    metricAfter.includes('1') && pickerHasDocA && pickerCardsA > 0 &&
    !metricB.includes('1') && metricB.trim().endsWith('0') && !pickerResultsB && !pickerHasDocB && pickerHintB.includes('没有匹配的文档块'),
    { metricBefore, metricAfter, queueState, pickerHasDocA, pickerCardsA, metricB, pickerResultsB, pickerHintB, docName: st.docName })

  // J9 历史隔离：把 A 的 session_id 灌进 B 的 localStorage 再刷新，B 不该看到 A 的任何气泡
  const bSession = await page.evaluate(() => localStorage.getItem('session_id'))
  await page.evaluate((sid) => localStorage.setItem('session_id', sid), st.sessionA)
  await page.reload({ waitUntil: 'networkidle2' })
  await waitFor(() => !!document.querySelector('.user-rail'), 30000, 'workspace after restore attempt')
  await page.evaluate(() => new Promise((r) => setTimeout(r, 2500)))
  const msgCountOnASession = await countOf('.chat-messages .message')
  const messagesText = await txt('.chat-messages')
  const leaked = !!st.answerHead && messagesText.includes(st.answerHead)
  // 空历史时 MessageList 会渲染唯一一格欢迎占位（v-if="!props.messages.length"），
  // 所以"什么都没恢复"的形状是 1 格占位，不是 0 格。
  const onlyWelcome = await page.evaluate(() => {
    const all = document.querySelectorAll('.chat-messages .message')
    return all.length === 1 && !!all[0].querySelector('.assistant-avatar')
  })
  const histStatus = await page.evaluate(async (sid) => {
    const r = await fetch('/api/history/' + encodeURIComponent(sid), { headers: { Authorization: 'Bearer ' + localStorage.getItem('auth_token') } })
    return { status: r.status, len: (await r.text()).length }
  }, st.sessionA)
  await page.evaluate((sid) => localStorage.setItem('session_id', sid), bSession)
  record(9, 'history isolation: B on A session_id gets nothing (user_id filter)',
    onlyWelcome && !leaked && histStatus.status === 200 && histStatus.len < 40,
    { sessionA: st.sessionA, msgCountOnASession, onlyWelcome, leaked, histStatus, answerHead: st.answerHead })
  fs.rmSync(docPath, { force: true })
}

// ============================================================ stage d：判据 10-12
if (stage === 'd') {
  await wipeStorage()
  const st = loadState()

  // 判据 12 的"零 error"要限定区间：wipeStorage 带着上一轮遗留的过期票进首页，
  // /api/auth/me 必然回 401（Task 8 的"票过期→落回登录页"就是这条路径）——
  // 那是 resource 级状态码、是设计行为，不是页面 JS 报错。基线取登录成功那一刻。
  let consoleBase = 0
  let pageBase = 0

  // J10 375x800：.chat-input 不撑破视口，下拉与发送都在视口内
  await setViewport(375, 800)
  await loginUser(st.emailA, st.pw)
  consoleBase = out.consoleErrors.length
  pageBase = out.pageErrors.length
  const j10 = await page.evaluate(() => {
    const inW = innerWidth
    const input = document.querySelector('.chat-input')
    const sel = document.querySelector('.model-select').getBoundingClientRect()
    const btn = document.querySelector('.chat-send').getBoundingClientRect()
    return { inW, inputScrollWidth: input.scrollWidth,
      selectRect: { x: sel.x, right: sel.right, y: sel.y, bottom: sel.bottom },
      sendRect: { x: btn.x, right: btn.right, y: btn.y, bottom: btn.bottom } }
  })
  record(10, '375: chat-input fits, select + send inside viewport',
    j10.inputScrollWidth <= j10.inW && j10.selectRect.right <= j10.inW && j10.selectRect.x >= 0 &&
    j10.sendRect.right <= j10.inW && j10.sendRect.x >= 0, j10)

  // J11 375x800：设置弹窗里的模型行不撑破；未配置横幅也不撑破（后者用全新的 C 账号）
  await openSettings()
  const j11row = await page.evaluate(() => Array.from(document.querySelectorAll('.settings-model-row'))
    .map((r) => ({ name: r.querySelector('.settings-model-name').textContent, scrollWidth: r.scrollWidth, clientWidth: r.clientWidth })))
  const innerW375 = await page.evaluate(() => innerWidth)
  await closeSettings()
  await signOut()
  await registerUser(st.emailC, st.pw, '')
  const j11banner = await page.evaluate(() => {
    const b = document.querySelector('.setup-banner')
    if (!b) return null
    return { scrollWidth: b.scrollWidth, clientWidth: b.clientWidth, text: b.textContent.trim().slice(0, 60) }
  })
  const rowsOk = j11row.length > 0 && j11row.every((r) => r.scrollWidth <= innerW375)
  const bannerOk = !!j11banner && j11banner.scrollWidth <= innerW375
  record(11, '375: setup-banner and settings-model-row do not overflow', rowsOk && bannerOk,
    { innerW375, rows: j11row, banner: j11banner })

  // J12 500x900：两块浮层的本体都不压住发送按钮；本档回读 500；全场零 error
  await setViewport(500, 900)
  const back500 = await page.evaluate(() => innerWidth)
  // C 未配置：先开候选池浮层（窄屏要先展开侧栏抽屉才点得到 .picker-open）
  await openPicker()
  const j12picker = await page.evaluate(() => {
    const m = document.querySelector('.picker-modal').getBoundingClientRect()
    const b = document.querySelector('.chat-send').getBoundingClientRect()
    const overlap = !(m.right < b.left || m.left > b.right || m.bottom < b.top || m.top > b.bottom)
    return { modal: { l: m.left, r: m.right, t: m.top, b: m.bottom }, send: { l: b.left, r: b.right, t: b.top, b: b.bottom }, overlap }
  })
  await page.click('.picker-close')
  await page.click('.setup-open')
  await waitFor(() => !!document.querySelector('.settings-panel'), 15000, 'settings at 500')
  const j12settings = await page.evaluate(() => {
    const m = document.querySelector('.settings-panel').getBoundingClientRect()
    const b = document.querySelector('.chat-send').getBoundingClientRect()
    const overlap = !(m.right < b.left || m.left > b.right || m.bottom < b.top || m.top > b.bottom)
    return { modal: { l: m.left, r: m.right, t: m.top, b: m.bottom }, send: { l: b.left, r: b.right, t: b.top, b: b.bottom }, overlap }
  })
  await page.click('.settings-panel .picker-close')
  const errNow = { console: out.consoleErrors.length, page: out.pageErrors.length }
  const newErrors = out.consoleErrors.slice(consoleBase).concat(out.pageErrors.slice(pageBase))
  record(12, '500: neither floating panel body covers the send button + innerWidth readback + no new errors since login',
    back500 === 500 && !j12picker.overlap && !j12settings.overlap &&
    errNow.console === consoleBase && errNow.page === pageBase,
    { back500, picker: j12picker, settings: j12settings,
      consoleBase, pageBase, errNow, newErrors, consoleWarnings: out.consoleWarnings.length })
}

fs.writeFileSync(OUT_FILE, JSON.stringify(out, null, 2), 'utf8')
console.log(`STAGE ${stage} done: ${out.judgements.filter((j) => j.pass).length}/${out.judgements.length} pass, ` +
  `consoleErrors=${out.consoleErrors.length}, pageErrors=${out.pageErrors.length}, warnings=${out.consoleWarnings.length}`)
if (out.consoleErrors.length) console.log('CONSOLE_ERRORS ' + JSON.stringify(out.consoleErrors.slice(0, 6)))
if (out.pageErrors.length) console.log('PAGE_ERRORS ' + JSON.stringify(out.pageErrors.slice(0, 6)))
await browser.close()
fs.rmSync(path.resolve('tmp-edge-profile'), { recursive: true, force: true, maxRetries: 6, retryDelay: 300 })
console.log('cleaned tmp-edge-profile')
```
