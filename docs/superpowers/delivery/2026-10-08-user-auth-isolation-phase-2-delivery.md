# 阶段二交付文档 — 每用户大模型配置 · 历史归户 · 设置界面

- **日期**：2026-10-08
- **spec**：`docs/superpowers/specs/2026-10-06-user-auth-isolation-design.md`
- **计划**：`docs/superpowers/plans/2026-10-07-user-auth-isolation-phase-2.md`（12 个 Task，`cd7316d` + 三处预检/落地修订）
- **台账（过程证据，未入库）**：`.superpowers/sdd/2026-10-07-user-auth-isolation-phase-2/progress.md`
- **终态**：`master` HEAD `25bf2e2`（终审台账），代码末笔 `e60dcf4`；区间 `cd7316d..HEAD` = **36 笔 = 18 代码 + 18 文档**；无远端、未推送、未 amend、未 rebase。

---

## 一、结论

阶段二 12 个 Task 全部交付，全分支终审 **Approved（0 Critical / 0 Important 遗留）**。终审过程中发现并修掉**一个真缺陷**（带斜杠的模型名删不掉，见第五节），另落地两处注释/死代码修正。所有挂账逐条给了动词（已闭合／保持现状带理由／阶段三顺延带闭合动作），没有一条写「待定」。

## 二、门禁实数（2026-10-08 于 HEAD `25bf2e2` 重跑，逐条抄当轮汇总行）

| 门 | 命令（在对应目录下） | 实数 |
|---|---|---|
| 后端全量 | `python -m pytest -q` | `306 passed, 2 skipped, 2 deselected, 1 warning in 74.63s` |
| 后端离线门 | `python -m pytest -q -m "not live and not migration"` | `285 passed, 25 deselected, 1 warning in 65.36s` |
| 前端单测 | `npm test` | `Test Files 14 passed (14)` / `Tests 154 passed (154)`（7.87s） |
| 前端产物 | `npm run build` | exit 0：`index-CUrklGmJ.css 13.49 kB │ gzip 3.20 kB`、`index-DGgHp3J3.js 101.15 kB │ gzip 37.89 kB`、`✓ built in 350ms` |
| 样式三条 | layout.css 颜色字面量 / 组件内 `<style>` / `src` 里 `console.log\|debugger` | **0 / 0 / 0** |

三处诚实注脚：

1. 全量门的 **2 个 skip** 是 `-m live` 的两条流式测（本机此刻没有 uvicorn）；它们在 Task 12 的「服务在」那一档真跑过，实数 `23 passed / 286 deselected / 1 warning in 143.72s`，**且无一条 skip**。
2. 唯一的 **1 warning** 是既有噪声 `core/database.py:13` 的 `declarative_base()` MovedIn20Warning，阶段二没有触碰该行，不属本轮引入。
3. **上表是阶段二收口那一刻（HEAD `25bf2e2`）的快照，不是现状。** 阶段三 ①②③④ 逐条推进了判据数：写本文档时 HEAD `423a26a` 实测**后端全量 `323 passed / 2 skipped / 2 deselected`、离线门 `301 passed / 26 deselected`、live 整文件 `22 passed`**，前端仍 `154 passed`（阶段三 ④ 未碰前端，故 `npm test`/`build` 未重跑）。每条的增项与逐轮变异实数在 `.superpowers/sdd/2026-10-08-user-auth-isolation-phase-3/progress.md`，本表保留原值是为了不篡改历史轮次。

## 三、原始七条需求 → 交付位置与证据

| 你要的 | 落点 | 证据 |
|---|---|---|
| 注册/登录（邮箱·手机简单校验） | 阶段一 `api/auth.py` register/login + 正则校验（不发验证码） | 阶段一已收口；`tests/test_api_auth.py` |
| 登录态与 session_id 改造 | 令牌=登录凭证，`chat_history.session_id`=对话键，两者分离 | 判据 9（把 A 的 session_id 灌进 B 也读不到 A 的历史） |
| 左下角头像 + 昵称 + 设置入口 | `.user-rail` / `⚙` | Task 12 判据 1 |
| 改头像·昵称·密码 + 配 api_key 与路由 | `SettingsModal.vue` 四段 + 六个设置端点 | 判据 2/3/4 |
| 文档按用户隔离 | `documents.user_id` + 读侧 `$and` 收窄 + 端点归属校验（越权回 404） | 判据 8 |
| 登录后且配好 key 才能对话 | 三条 409 门禁 + 事前禁发 | 判据 6/7 |
| 输入框右下角模型下拉 + 发送按钮 | 输入区两段式 + `.model-select` | 判据 5/10 |

**Task 12 的 12 条浏览器判据全部 PASS**，在**真服务 + 真凭证**上跑（Edge headless，视口 1280/500/375 三档）。这 12 条是界面几何与文案层面的证据：掩码显示（`当前密钥：sk-****62do`、`leaksRawKey false`）、横幅换句与消失、Enter 也被挡、跨用户文档与历史不可见、窄屏 `flex-wrap`、两块浮层不压发送按钮。

## 四、使用时会遇到的十条「预期表征」（不是 bug）

1. **409 的第一句是「你的模型名单是空的」**，不是「没配 api_key」。`_llm_context` 的顺序是：先判名单空 → 再验载荷里的模型名 → 最后查凭证。别按文案去找 key。
2. **历史归户只在跑过迁移的库上发生**。没跑过的库里老行 `user_id` 仍是 NULL，表征是「升级后历史全空」而不是报错；真服务重启即自愈。本机真库已归户（`chat_rows_claimed = 43`、NULL 0 行）。
3. **令牌中途过期会直接落回登录页**（三条网络出口共用一处 401 处理）。这不是掉线 bug，是 Task 8 的设计。
4. **`api_key` 永不回填**：弹窗里只显示掩码，输入框是 `type=password` 且初始为空。保存后也拿不到原文。
5. **改密码不吊销其它设备的令牌**：会话表 30 天绝对过期，只有登出才删行。
6. **界面上选中的那枚模型就是实际发出去的那枚**：设置侧与问答侧共用 `schemas/auth.py:142 default_model_of` 这一个函数（全仓 `_default_of` 零命中），不可能分叉。
7. **未配置时是「事前禁发 + 紫横幅」**，两条路都堵（按钮 `:disabled` 与 `submit()` 门禁各一半）；真收到 409 时落红色横幅，且**前端不改写后端文案**（英文 detail 原文照抄在中文冠语之后）。
8. **`PASSWORD_MIN` 是 6 不是 8**（`schemas/auth.py:13`）。前端原有两处各写一份，阶段三第 ② 条（`ee117fd`）起只有 `frontend/src/constants.js` 一枚，且由 `backend/tests/test_frontend_constants.py` 钉住与后端逐字相同——不再依赖"记得两边一起改"。
9. **默认账号 `default@local` 的初始口令来自 `.env` 的 `DEFAULT_USER_PASSWORD`**；该键为空则这个账号只作归属锚点、不可登录。
10. **建议轮换 `DEFAULT_USER_PASSWORD`**：它在脱敏提交 `0b22116` 之前进过 git history，仓库文件现在 0 命中但历史可翻。

## 五、终审发现并修掉的真缺陷（`4c45e96`）

**症状**：带斜杠的模型名（OpenRouter 一类网关的 id 本身就是「厂商/模型」）**加得进去、永远删不掉**，只能改库。

**机制**：删除端点原本是 `DELETE /api/auth/me/models/{name}`，`{name}` 的默认正则是 `[^/]+`；而 `%2F` 在到达 ASGI 之前**就已经被解回 `/`**，所以两种写法都匹配不上 → 404。

**实测矩阵**（一次性探针：真 uvicorn :8000 + Vite 代理 :5173 两档，各打四种 URL；跑完即删、不入库）：

| 路由形状 | `a%2Fb` | `a/b` | 解出的名字 |
|---|---|---|---|
| `{name}`（改前） | **404** | **404** | — |
| `{name:path}`（改后） | 200 | 200 | `a/b` |

**关键一点**：离线 `TestClient` 与真 uvicorn 行为**完全一致**，所以这条回归能住离线门而不必只留在 live 组。判据 = `tests/test_api_auth.py::test_a_model_name_with_a_slash_is_still_deletable`；RED 用改前路由实跑（`1 failed, 46 deselected`，理由 `assert 404 == 200`），GREEN 后整文件 `47 passed`。

另两笔终审修正：`a145f65` 把两处指向「被 `.gitignore` 排除的台账报告」的注释改成仓库内锚点（干净检出里翻不到的引用等于没有），并把条数纠成本轮实测的 47；`e60dcf4` 删掉 `App.vue:158` 里永不执行的 `?? '我'` 兜底。

## 六、安全面结论

- **端点不回原文 key**：全仓 `UserOut(` 只有 `api/auth.py:50` 一处构造点（没有 `model_validate` 吃 ORM 行的绕行），`UserOut` 十键里只有 `api_key_masked`，**根本没有 `api_key` 字段**。
- **口令哈希与令牌**：库里存 SHA-256，令牌 `secrets.token_urlsafe` + 库里只存哈希，无 JWT、无 Cookie。
- **越权不泄露存在性**：不属于你的块/文档一律 404，不回 403。
- **一条仍开着的 advisory**：FastAPI 默认 422 会把刚提交的入参回显进 `detail[*].input`（`main.py:60-86` 没挂 `RequestValidationError` 处理器）。回显的是调用者自己刚发出去的那份 body，不是库里原文 ⇒ 不违反铁律；前端 `detailFromText` 只在**缺 `msg` 时**才降级为整项 `JSON.stringify`（`client.js:32`），而 pydantic 的 item 恒带 `msg` ⇒ 今天不外印。**但那条 fallback 是明文 key 出现在界面上的唯一通道**，前端任何日志/控制台都不许打印它。见阶段三第 ⑦ 条。

## 七、挂账裁决摘要（完整表在台账「全分支终审」一节）

- **Task 1**：M-1/M-2/M-5 **保持现状**（理由已记）；M-3/M-4/M-7/M-8 **已闭合**；M-6 **顺延**（外键族，见阶段三 ④）。
- **Task 2**：concern 4（并发可留两枚默认）**保持现状 + 顺延** ⑤；I-2（fake 别名 vs 真库快照 ⇒ `_reload` 离线无牙）**已裁定并留痕**——本轮重跑变异：两处 `_reload` 退回后 `tests/test_api_auth.py` **47 passed 零红**，真判据是 Task 12 判据 4；M-1 **已闭合**（Task 7 补了 `ChatRequest.model_name`）；M-2/M-3 **保持现状**；M-6 **顺延** ②。
- **Task 3**：M-3/M-6/M-7 **保持现状**；给 Task 12 的 ⑤⑥ **部分兑现**——缺 key 的 `llm_seeded: False` 分支至今没在真 `.env` 上跑过（那要把 `.env` 改坏再改回，风险大于收益），**如实记为缺口** → 阶段三 ⑥。
- **Task 4/5/6**：数字口径与类型标注类 **保持现状**；两枚同名 `FakeConfig` → ③；`ChatHistory.user_id` 的 FK 只在新建库存在 → ④（**③④ 均已闭合**，④ 的收口口径见第八节第 4 条）。
- **Task 8 M-A**（`%2F`）**已闭合** —— 本条从「未验」变成实测并修在生产路由上，是本轮最有价值的一条。M-C（`ApiError.status` 取值域）**保持现状**：界面层不按 `err.status` 分支（Task 11 的裁定就是不按状态码改写文案）。
- **Task 9/10/11**：`?? '我'` **已闭合**；其余（弹窗只在 setup 回填、`.settings-*` 复用 `.picker-*` 底座、八条 R 裁定）**保持现状/维持**，Task 12 的判据 11/12 已把相关 rect 量过。

## 八、阶段三开工单（明确不在阶段二范围，每条给「要闭合得做什么」）

1. ~~`LlmIn.api_key`/`base_url` 的长度界量在 **strip 之前**~~ ⇒ **已闭合（2026-10-08，`de8499d`）**：两格的 `min_length/max_length` 从 `Field` 搬进 `field_validator`，strip 完再量并返回洗净值；补了三条判据（靠空白凑够 8 位的 key 现在 422 且不写库、正好 255/500 位的合法值不再因为多贴空格被拒）。台账见 `.superpowers/sdd/2026-10-08-user-auth-isolation-phase-3/progress.md`。
2. ~~前后端枚举清单没有单一出口：`AVATARS` 两份（`api/auth.py:27` / `SettingsModal.vue:19`）、`PASSWORD_MIN` 三份（`schemas/auth.py:13` / `AuthPanel.vue:14` / `SettingsModal.vue:25`）~~ ⇒ **已闭合（2026-10-08，`ee117fd`）**：走的是"前端集中 constants + 判据钉住"那条路（否决 options 端点——它要进认证白名单、要给同步表单加异步态、首屏仍需一份兜底副本，那正是本条要消灭的东西）。七枚镜像字面量收进 `frontend/src/constants.js`（第 7 枚是此前只以 `maxlength="100"` 形态存在的模型名上界），新增 `backend/tests/test_frontend_constants.py` 直读两端源码钉四件事：只许一枚模块声明、镜像值与后端权威值逐字相同、头像与标签同枚覆盖、模板属性里不许写死数字（顺带消灭 `AuthPanel.vue:119`「至少 6 位」与两处 `maxlength`）。判据放 pytest 而非 vitest：改后端不改镜像、或改镜像不改后端，都在**同一道后端门**上红。台账见 `.superpowers/sdd/2026-10-08-user-auth-isolation-phase-3/progress.md`。
3. ~~两枚同名 `FakeConfig`（`tests/fakes.py:1` 与 `tests/test_migrations.py:182`）~~ ⇒ **已闭合（2026-10-08，`bcc0296` + 补正 `d89bb29`）**：本条要求的前置检查实测**答案是"依赖成立"**——`core/migrations.py:252-256` 要读四格（默认口令 + `.env` 三键），而 `fakes.py` 那枚只有 `CHROMA_PERSIST_DIR`，所以**合并这条路被实测否掉**（合了要么缺一格，要么把阶段二 Task 7 刚删掉的"写了没人读"三键塞回交付面）。缺陷随之收窄成"重名"这一件事：迁移那枚改名 `MigrationConfig`，并新增 `backend/tests/test_test_doubles.py` 用 AST 钉住**模块顶层 `Fake*` 类名唯一**（口径边界如实记：函数体内的局部同名不在射程内——那种合法同名实测存在，是 `test_llm_factory.py` 35/50/66 行的三枚 `Recorder`，作用域互不重叠；判据的扫描面因此从 `ast.walk` 收窄为 `tree.body`，正反两轮实测确认该抓的一条没漏、不该抓的一条没误伤）。台账见 `.superpowers/sdd/2026-10-08-user-auth-isolation-phase-3/progress.md`。
4. ~~`ChatHistory.user_id` / `documents.user_id` 的外键**只存在于新建库** ⇒ 做任何「注销账号」功能之前必须先补 FK 或显式级联删行，否则老库留孤儿~~ ⇒ **已闭合（2026-10-08，`423a26a`）**：补了 FK，且**刻意不做级联**。三条设计都钉成了判据——① `ensure_foreign_keys` 按 **(表, 列)** 问 `information_schema.KEY_COLUMN_USAGE`，不按约束名问（`create_all` 建的那枚叫 `documents_ibfk_1`，按名字查会在每个新库上再叠一枚重复外键，InnoDB 对不同名不拦且安静收下）；② 排在 `ensure_indexes` **之后**（列上没有可用索引时 InnoDB 会自建一枚、名字就是约束名，我们那枚再补一次 ⇒ 同列两枚，没人报错只多付写放大）；③ **不写 `ON DELETE`**（MySQL 默认 RESTRICT）——级联删得掉 MySQL 行、删不掉 Chroma 里的向量，"行没了、向量还能被召回"正是本仓一路在防的脏数据面；要删就走应用层两头删。原条目给的"或显式级联删行"这条路**被否决并写进判据**（`test_ensure_foreign_keys_never_cascades_at_the_mysql_level`）。「注销账号」从此被 MySQL 拦在 errno 1451 上，孤儿行产生不了。**预检量到计划外的一面并改了真数据**：`chat_history` 43 行的 `user_id` 全是 **1**，而 `users` 只剩 30（`default@local`）与 338——默认账号被重铸过、id 从 1 漂到 30，`backfill_chat_history` 只捡 `IS NULL` 的行，这 43 行从此读不到也删不掉；带着孤儿去 `ADD CONSTRAINT`，MySQL 回 **errno 1452**，而 `run_migrations` 挂在 lifespan 且不兜异常 ⇒ 症状是"整台后端起不来"。经使用者拍板走「先归户再建 FK」：新增 `reclaim_orphaned_owners`（先 `COUNT` 再 `UPDATE`，不拿 rowcount 当证据——本仓方言硬带 `CLIENT_FOUND_ROWS`，同值重写照样回 1），排在 `ensure_foreign_keys` 之前。**真实数据改动：43 行 `chat_history.user_id` 由 1 改为 30**（回滚 SQL 记在台账）。落库后实测：两张表各**一枚**外键、**0** 孤儿、`user_id` 列上各**只一枚**索引。判据：单测 +7、live +1（RESTRICT 行为面：探针账号自己造自己删，`default@local` 一次都不出现在 DELETE 里）+ live 那格「第二遍零 ALTER」扩到外键与孤儿（纪律：**先读 `information_schema` 确认 lifespan 已建好，才敢调那两步验幂等**——测试不许在共享库上发 ALTER/UPDATE）。十二轮变异自证、逐轮条数与还原 sha 见台账 `.superpowers/sdd/2026-10-08-user-auth-isolation-phase-3/progress.md`。
5. ~~`user_models`「至多一枚默认」靠应用层两步（判空 + 清场）⇒ 并发插入可留两枚默认；要堵得加唯一约束（MySQL 无部分索引，需生成列或应用级锁）~~ ⇒ **已闭合（2026-10-08，`e0ecfe1`）**：堵在**引擎**上，不选应用级锁。MySQL 没有部分索引，所以守卫落在一枚生成列上——`default_guard INT GENERATED ALWAYS AS (CASE WHEN is_default THEN user_id ELSE NULL END) STORED` + `CREATE UNIQUE INDEX uq_user_models_single_default ON user_models (default_guard)`；唯一索引**不管 NULL**，于是"同一人任意多枚非默认"与"每人至多一枚默认"同时成立。新库由 `create_all` 按 ORM 声明建（`Computed(..., persisted=True)`），已部署库由 `ensure_single_default_guard` 补，四步各查各的、重跑交白卷：**数重复 → 降掉除 `MIN(id)` 之外 → 补生成列 → 建唯一索引**。两处顺序是 scratch 表实测钉出来的，反了不是报错而是**整台后端起不来**（`run_migrations` 挂在 lifespan 且不兜异常，`main.py:59`）：① `ALTER … ADD COLUMN … STORED` 在**已经带着两枚默认**的数据上照样成功（两行都算出同一个 guard，此刻还没有索引管它），紧接着的 `CREATE UNIQUE INDEX` 才回 1062 ⇒ 去重必须早于建索引；② 列必须早于索引。存在性用**严格口径**问（`information_schema.COLUMNS` 带 `GENERATION_EXPRESSION <> ''`）——同名**普通列**被当成"守卫已建好"的后果是**静默的零约束**（那列由应用自己写，不写就整列 NULL，索引正好不管 NULL），比没有索引更糟；表达式全文不能逐字比（MySQL 存成小写 + 反引号），那半由 `SINGLE_DEFAULT_GUARD_EXPR` 与 ORM 声明**同源**钉住（`core/database.py` 从 `core/migrations.py` 导入）。清单给的"应用级锁"这条路**被否决**：本表写入方已有三处（`add_user_model` / `set_default_user_model` / 迁移的 `seed_default_llm`），锁要求每个写入方都自觉拿同一把。另外看着更"原子"的那条捷径 `SET is_default = (name = :t)` **实测否决**——同一份数据，目标 id 排在现任之前回 1062、之后成功，顺序依赖的约束不是约束。**顺带堵掉 ⑤ 自己会引入的谎**：`add_user_model` 原先把所有 `IntegrityError` 都回 False，端点据此回 409「该模型已在你的名单里」；守卫键一进来，"名单里根本没这个名字"也会撞键（另一事务刚立默认、这里 `is_first` 读旧快照），那句话就变成没人能查下去的假话——现在回滚后再查一次名字分流：真在名单里 ⇒ 409，不在 ⇒ 补插成非默认 ⇒ 收下。**真库 `mydb` 已落库**（`default_guard` 实测 `STORED GENERATED`、唯一索引只盖它一列、多默认用户 0、行数与默认数未变，`duplicates_cleared: 0` ⇒ **本条不改任何用户数据**，没有 ④ 那样的归户）。判据：单测 +8（迁移 6 + 形状 2）、live +2（一条问**引擎本身**收不收第二枚默认——INSERT 与 UPDATE 提升都回 1062 且消息里带着索引名；一条用 `_StaleSnapshot` 按 SQL 文本只 spoof 判空那次查询，把撞守卫键的窗口变成确定性可复现，并断言钩子恰好命中一次否则算空跑）。八轮变异逐轮一条红，真开机一遍拿到 `kb.migrations` 的 summary 原文（`single_default_guard` 三格全白卷）；逐轮条数、五条 Ruling 与挂账（索引侧的严格口径、重试嵌套分支、`set_default` 输家的 500）见台账 `.superpowers/sdd/2026-10-08-user-auth-isolation-phase-3/progress.md`。
6. ~~迁移的「缺 key 半态」分支（`llm_seeded: False`）从未在真 `.env` 上跑过 ⇒ 闭合需要一个能临时改 `.env` 的受控窗口。⑤ 那轮真开机拿到的 `llm_seeded: False` 不算这条的进展：两条早退回的是同一个值，日志与返回值都分不出来~~ ⇒ **已闭合（2026-10-08，`6a327ca`）**：走的是使用者裁定的**「不动 `.env`，改判据」**这条路（把 `.env` 改坏再改回需要一台"崩一次就起不来"的后端——`run_migrations` 挂在 lifespan 且不兜异常，风险大于收益）。第一步先把两条早退变成**可分辨**：`seed_default_llm` 的三条出口各带一枚常量 `reason`（`env_incomplete` / `already_configured` / `seeded`），`run_migrations` 的 summary 新增 `seed_reason` 把它带进开机日志；两格布尔的**名字与口径一个字未动**，这条不是改语义，是给已经存在的三条路各挂一块牌子。第二步让「缺 key 半态」在**离线门**上有一次真判据：注入 `IncompleteEnvConfig`（只抹 `OPENAI_API_KEY`，`base_url` 与模型名留着——半套配置才是本机最容易出现的形态），一次证两件事，那一遍**什么都没写**（`users` 的两列不动、`user_models` 也不塞模型名）且 summary **报得出走了哪条**。判据 +3（`test_migrations.py` 30→33；其中一条用 `caplog` 按 logger 名收三遍开机日志，钉"两遍 no-seed 的布尔逐格相同、只有 `seed_reason` 分开它们"，并钉整段日志不许出现 key），另**有意改写**四处既有的"整枚字典相等"断言（新增一格必然改写它们，两格布尔的期望没动）。七轮变异：M1 两条早退同名、M2 「已有 key」的守卫永不为真、M3 summary 不接线、M4 `and`→`or`（半套配置照抄，且**既有那条"两枚全缺"的判据照常绿**——"只缺一枚"这一半牙齿是新增那格给的）、M5 写成功那格误标、M6 `reason` 拼进库里的 key（`test_boot_log` 实测红在凭证不外印那一条断言）、M7 对照组只换字典键序 ⇒ 33 全绿（判据钉的是值不是形状）。**真开机一遍**（Temp 里的 log config，仓库代码零改动）拿到 `'llm_seeded': False, …, 'seed_reason': 'already_configured'`——⑤ 那轮只能靠读源码推断的这一格，现在是日志里读出的事实。**两处边界如实记**：真 `.env` 上"缺键"那半本机至今没跑过（证据换成离线判据）；「写了 key 但没加模型」的两支因（`LLM_MODEL` 为空 / 名单已有同名）没有各自报名。台账见 `.superpowers/sdd/2026-10-08-user-auth-isolation-phase-3/progress.md`。
7. 422 的 `detail[*].input` 回显，前端只靠 `client.js:32` 那条 fallback 挡着 ⇒ 要闭合就在 fallback 里剥掉 `input` 键（代价：削弱「原文是唯一的排错线索」，属产品取舍）。
8. 视口/交互的真浏览器回归是**一次性脚本**（探针全文附在阶段二台账下方留档；`puppeteer-core` 等 25 枚 `--no-save` 装进来的包已于 2026-10-08 `npm prune` 清掉，复验 `154 passed` + build 绿、产物 hash 未变 ⇒ 它们不是真依赖，做这条要重新装）⇒ 没有常驻测试，下次改布局要重新造轮子。

## 九、已知验证缺口（如实记）

- 12 条判据只用了**本机 Edge headless**：没有跨浏览器；375 档是**视口模拟**不是设备模拟，真触屏 `touch` 行为未验。
- **并发未量**：两个标签页同时改名单只有 Task 10 的补偿测，界面侧没有。
- **默认用户那档没有在界面上手验**（只以 live ④ 组身份出现）。
- 浮层 backdrop 点击关闭与 Esc 关闭在真浏览器的表现未量（jsdom 判据有）。
- 判据 4/5 与 live ④ 组烧的是**真实配额**（2 次界面问答 + 23 条 live 里的真流式往返），本轮终审**没有重跑 live**（改动只碰那枚路由与两处注释/一行死代码，`grep "me/models" tests/test_live_*.py` 0 命中 ⇒ live 组无消费者）。

## 十、流程偏离（必须向用户明示）

按 2026-10-07 23:35 的指令「你直接接管,然后执行到任务完成」：**Task 6 收口 + Task 7-12 全部由控制者一人执行**——自己 TDD、自己跑三门、逐 Task 提交，**没有派实施代理，也没有派评审代理**，本文档所属的**终审是作者自审**，不具备独立评审的对抗性。这与 `superpowers:subagent-driven-development` 的标准流程不同，是裁定而非遗漏。阶段二的 Task 1-5 仍有独立的实施/评审/修正轮，其结论可交叉引用。

缓解措施：终审的七条承重断言全部**重新直查**（`UserOut` 唯一构造点、`default_model_of` 唯一解析函数、`chat_history` 三臂都带 `user_id`、`STATUS_BY_ERROR` 六键含 `NotConfiguredError: 409`、裸 `print` 与 `console.log` 归零、`_llm_context` 的三条 409 顺序、`_reload` 离线无牙重验）；本文档第二节的三门实数是**在 HEAD `25bf2e2` 上刚刚重跑的**，不是引用历史轮次的报告。

自审过程中也记下一次控制者自己的事故：还原变异时使用 `allow_multiple`，预期命中 2 处、实际命中 3 处（`GET /me` 那句本来就不带 `_reload`），靠 `sha256sum` 与基线不符 + `git diff` 露出的多余 hunk 才抓出来。教训：涉及变异还原时**先 grep 计数**，并一律以 sha/diff 为准，不以记忆为准。

## 十一、如何复现验收

```bash
# 后端（同一时刻只跑一个 pytest 进程；不要起第二个 uvicorn，Chroma 是单实例锁）
cd backend
python -m pytest -q                                    # 期望 336 passed / 2 skipped / 2 deselected
python -m pytest -q -m "not live and not migration"     # 期望 312 passed / 28 deselected

# 前端
cd frontend
npm test                                               # 期望 Test Files 14 / Tests 154
npm run build                                          # 期望 exit 0

# live 组需要真库（MySQL），流式那两条还需要真服务：先起 uvicorn（只起一份），再
python -m pytest -q tests/test_live_database.py         # 期望 24 passed（阶段三 ⑤ 实跑数，⑥ 未新增 live 判据）
python -m pytest -q -m live                            # ⑥ 这轮实跑 24 passed / 2 skipped / 314 deselected；
                                                       # 那 2 条 skip 是 `test_live_stream.py` 的流式判据——
                                                       # 跑这一组时 :8000 上没有服务，按"没服务就 skip"的既有
                                                       # 惯例跳过而不是假绿；本轮只起过一次服务，且只为读迁移
                                                       # summary（验完按 CommandLine 核对后停进程），没有重跑流式组，
                                                       # 不填没量过的数
```

上两行后端期望是**阶段三 ⑥（`6a327ca`）**之后的实数；阶段二收口那轮跑在 `25bf2e2`，同两条命令的实数是
`306 passed / 2 skipped / 2 deselected` 与 `285 passed / 25 deselected`（见第二节表格，历史值不追改）。
增项逐条记在阶段三台账里：① +3、② +5、③ +1、④ +7 单测 +1 live、⑤ +8 单测（迁移 6 + 形状 2）+2 live、
⑥ +3 单测（`test_migrations.py` 30→33；另**有意改写**四处既有的"整枚字典相等"断言，两格布尔口径未动）。

**验收隔离数据时不要改库**：造「未配 key」「名单为空」两档只能走设置端点（清 `api_key` / 逐条删模型），改库会同时破坏 Task 3 的补戳证据与库内基线（活文档 4 / 父块 4 / 子块 10、`chat_history` 43 行）。探针账号一律挂自己的 `probe_user`，用完即删。

## 十二、代码交付清单（18 笔，按落地顺序）

| Task | 实现 | 修正轮/补充 |
|---|---|---|
| 1 DB 层 | `161d97a` | `fb9ebaa` |
| 2 六个设置端点 | `50d8587` | `4434626` |
| 3 迁移步骤 4 + 补戳自愈 | `a1720ce` | `fd6a4c6` |
| 4 `llm_factory` 单一构造点 | `6175267` | — |
| 5 链方法吃 `RunContext` + 读侧收窄 | `28928d7` | `7640a59` |
| 6 历史归户 | `41b45d2` | — |
| 7 问答吃用户凭证 + 三条 409 | `869360b` | — |
| 8 前端错误带状态码 + 设置封装 + 401 登出 | `da641fa` | — |
| 9 `SettingsModal` 四段弹窗 | `6f920c3` | — |
| 10 输入区两段式 + 模型下拉 | `74eaf62` | — |
| 11 未配置横幅 + 发送禁用 + 409 归宿 | `7a1aa8e` | — |
| 12 观测扫描面自动发现 | `6ffff74` | — |
| 终审 | `4c45e96`（路由必修） | `e60dcf4`（死代码） |

**一处记录更正**：`6f920c3` 的提交信息里指控「计划 Step 1 少写 `src/`」**是错的**，真相是控制者自己的抄写错误。引用该提交时按更正后的口径。
