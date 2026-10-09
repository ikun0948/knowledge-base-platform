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
   **现状（HEAD `e1f4d45`，阶段三 ①–⑧ 与 ② 的补账全部闭合后，本轮实测）**：后端全量 `337 passed / 2 skipped / 2 deselected / 1 warning`
   （那 2 条 skip 仍是需要本机 uvicorn 的流式判据；**live 组含在这一遍里**，`test_live_database.py` 单文件的 24 条是 ⑤ 轮的量、本轮未单文件重跑），
   后端离线门 `313 passed / 28 deselected`，前端 jsdom `158 passed / 14 files`，
   `npm run build` → `index-CKhscz7G.js` + `index-CUrklGmJ.css`，浏览器门 21 条需两份服务（本轮未跑）。
   **现状（HEAD `35e9498`，追加特性「注销账号」三条闭口全部闭合，2026-10-09 本轮实测）**：后端全量
   `345 passed / 2 skipped / 2 deselected`，离线门 `320 passed / 29 deselected`，live 单文件 `25 passed`，
   前端 jsdom `162 passed / 14 files`，`npm run build` → `index-CrrLaEBX.js` + `index-C4mVDwWj.css`，
   浏览器门 `21 passed / 1 file`（本轮**起了两份服务实跑**，跑完按 CommandLine 核对后停干净；
   条数未变 ⇒ 注销没有新增浏览器判据，理由见第八节第 9 条与第九节）。旧那一段保留原值，是为了不篡改历史轮次。

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
| **注销账号（原始七条之外的追加需求）** | `POST /api/auth/deactivate`（三道门 + 两头删）+ `SettingsModal.vue` 第五节危险区 + `database.delete_user_cascade` | 第八节第 9 条：19 轮变异逐轮条数在台账，六张门实数见第二节末段 |

**Task 12 的 12 条浏览器判据全部 PASS**，在**真服务 + 真凭证**上跑（Edge headless，视口 1280/500/375 三档）。这 12 条是界面几何与文案层面的证据：掩码显示（`当前密钥：sk-****62do`、`leaksRawKey false`）、横幅换句与消失、Enter 也被挡、跨用户文档与历史不可见、窄屏 `flex-wrap`、两块浮层不压发送按钮。

## 四、使用时会遇到的十一条「预期表征」（不是 bug）

1. **409 的第一句是「你的模型名单是空的」**，不是「没配 api_key」。`_llm_context` 的顺序是：先判名单空 → 再验载荷里的模型名 → 最后查凭证。别按文案去找 key。
2. **历史归户只在跑过迁移的库上发生**。没跑过的库里老行 `user_id` 仍是 NULL，表征是「升级后历史全空」而不是报错；真服务重启即自愈。本机真库已归户（`chat_rows_claimed = 43`、NULL 0 行）。
3. **令牌中途过期会直接落回登录页**（三条网络出口共用一处 401 处理）。这不是掉线 bug，是 Task 8 的设计。
4. **`api_key` 永不回填**：弹窗里只显示掩码，输入框是 `type=password` 且初始为空。保存后也拿不到原文。
5. **改密码不吊销其它设备的令牌**：会话表 30 天绝对过期，只有登出才删行。
6. **界面上选中的那枚模型就是实际发出去的那枚**：设置侧与问答侧共用 `schemas/auth.py:142 default_model_of` 这一个函数（全仓 `_default_of` 零命中），不可能分叉。
7. **未配置时是「事前禁发 + 紫横幅」**，两条路都堵（按钮 `:disabled` 与 `submit()` 门禁各一半）；真收到 409 时落红色横幅，且**前端不改写后端文案**（英文 detail 原文照抄在中文冠语之后）。
8. **`PASSWORD_MIN` 是 6 不是 8**（`schemas/auth.py:13`）。前端原有两处各写一份，阶段三第 ② 条（`ee117fd`）起只有 `frontend/src/constants.js` 一枚，且由 `backend/tests/test_frontend_constants.py` 钉住与后端逐字相同——不再依赖"记得两边一起改"。**② 的补账（`e1f4d45`）后这枚文件共九枚镜像 / 六道判据**：问答契约 `parent_ids` 的两枚界（`MAX_ID_CHARS=100` / `MAX_SELECTED_CHUNKS=50`）与 `model_name` 的界也进了同一出口，前端不再留本地副本。
9. **默认账号 `default@local` 的初始口令来自 `.env` 的 `DEFAULT_USER_PASSWORD`**；该键为空则这个账号只作归属锚点、不可登录。
10. **建议轮换 `DEFAULT_USER_PASSWORD`**：它在脱敏提交 `0b22116` 之前进过 git history，仓库文件现在 0 命中但历史可翻。
11. **注销是硬删，且界面上要过两格**：原密码 + 手打「确认注销」四个字，两格都过按钮才亮（少任何一格都是禁用态，不是点下去报错）。
    口令错 ⇒ 401「原密码不正确」，且**两头一次都没被调用**；默认账号 `default@local` ⇒ 409「默认账号不能注销」（口令门在它之前，
    所以错口令那次拿到的是 401 而不是 409——那句话不替你确认账号能不能删）。成功后整屏落回登录页、**不发** `/logout`
    （票已经随账号没了，那一枪只会撞 401 形成环），MySQL 与 Chroma 两头一起抹，**不可恢复、没有回收站**。

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
- **一条 advisory 已收口（阶段三 ⑦，`74d11b8`）**：FastAPI 默认 422 会把刚提交的入参回显进 `detail[*].input`（`main.py:65-86` 只挂领域异常与 500 兜底，没挂 `RequestValidationError` 处理器）。回显的是调用者自己刚发出去的那份 body，不是库里原文 ⇒ 不违反铁律；原先前端只在**缺 `msg` 时**才降级为整项 `JSON.stringify`（旧 `client.js:32`），那条 fallback 是明文 key 出现在界面上的**唯一通道**。**现在这道闸改成白名单**：数组 detail 只准 `msg`（非空字符串）、`type`、`loc` 上屏，`input` 与 `ctx` 一律不进文案（`validationItemText`），三条网络出口共用 `httpError` 故一起受保护；判据 +4、九轮变异见第八节第 7 条与阶段三台账。**仍然如实记的边界**：这一闸只挡"上界面"——422 响应体里 `input` 那一格照旧存在，devtools、反向代理访问日志、直连 API 的消费者都还能看到明文 key；要连那一面一起堵得在后端挂 `RequestValidationError` 处理器，本条未做。另：前端任何日志/控制台仍不许打印它。

## 七、挂账裁决摘要（完整表在台账「全分支终审」一节）

- **Task 1**：M-1/M-2/M-5 **保持现状**（理由已记）；M-3/M-4/M-7/M-8 **已闭合**；M-6 **顺延**（外键族，见阶段三 ④）。
- **Task 2**：concern 4（并发可留两枚默认）**保持现状 + 顺延** ⑤；I-2（fake 别名 vs 真库快照 ⇒ `_reload` 离线无牙）**已裁定并留痕**——本轮重跑变异：两处 `_reload` 退回后 `tests/test_api_auth.py` **47 passed 零红**，真判据是 Task 12 判据 4；M-1 **已闭合**（Task 7 补了 `ChatRequest.model_name`）；M-2/M-3 **保持现状**；M-6 **顺延** ②。
- **Task 3**：M-3/M-6/M-7 **保持现状**；给 Task 12 的 ⑤⑥ **部分兑现**——缺 key 的 `llm_seeded: False` 分支至今没在真 `.env` 上跑过（那要把 `.env` 改坏再改回，风险大于收益），**如实记为缺口** → 阶段三 ⑥。
- **Task 4/5/6**：数字口径与类型标注类 **保持现状**；两枚同名 `FakeConfig` → ③；`ChatHistory.user_id` 的 FK 只在新建库存在 → ④（**③④ 均已闭合**，④ 的收口口径见第八节第 4 条）。
- **Task 8 M-A**（`%2F`）**已闭合** —— 本条从「未验」变成实测并修在生产路由上，是本轮最有价值的一条。M-C（`ApiError.status` 取值域）**保持现状**：界面层不按 `err.status` 分支（Task 11 的裁定就是不按状态码改写文案）。
- **Task 9/10/11**：`?? '我'` **已闭合**；其余（弹窗只在 setup 回填、`.settings-*` 复用 `.picker-*` 底座、八条 R 裁定）**保持现状/维持**，Task 12 的判据 11/12 已把相关 rect 量过。

## 八、阶段三开工单（明确不在阶段二范围，每条给「要闭合得做什么」）

1. ~~`LlmIn.api_key`/`base_url` 的长度界量在 **strip 之前**~~ ⇒ **已闭合（2026-10-08，`de8499d`）**：两格的 `min_length/max_length` 从 `Field` 搬进 `field_validator`，strip 完再量并返回洗净值；补了三条判据（靠空白凑够 8 位的 key 现在 422 且不写库、正好 255/500 位的合法值不再因为多贴空格被拒）。台账见 `.superpowers/sdd/2026-10-08-user-auth-isolation-phase-3/progress.md`。
2. ~~前后端枚举清单没有单一出口：`AVATARS` 两份（`api/auth.py:27` / `SettingsModal.vue:19`）、`PASSWORD_MIN` 三份（`schemas/auth.py:13` / `AuthPanel.vue:14` / `SettingsModal.vue:25`）~~ ⇒ **已闭合（2026-10-08，`ee117fd`）**：走的是"前端集中 constants + 判据钉住"那条路（否决 options 端点——它要进认证白名单、要给同步表单加异步态、首屏仍需一份兜底副本，那正是本条要消灭的东西）。七枚镜像字面量收进 `frontend/src/constants.js`（第 7 枚是此前只以 `maxlength="100"` 形态存在的模型名上界），新增 `backend/tests/test_frontend_constants.py` 直读两端源码钉四件事：只许一枚模块声明、镜像值与后端权威值逐字相同、头像与标签同枚覆盖、模板属性里不许写死数字（顺带消灭 `AuthPanel.vue:119`「至少 6 位」与两处 `maxlength`）。判据放 pytest 而非 vitest：改后端不改镜像、或改镜像不改后端，都在**同一道后端门**上红。
   **② 收口时留的两格账 ⇒ 补账已闭合（2026-10-08，`e1f4d45`）**：问答契约 `schemas/chat.py` 的三格界此前没有跨端判据。
   预检实测两件事决定了做法——① `parent_ids` 的**两枚界写在两行上**（元素界在 `Annotated[str, Field(...)]` 里、
   列表界在外层 `Field(default_factory=list, max_length=50)`），② 那套按行匹配的 `_py_field_maxes` 看不见续行 ⇒
   补一条按**括号深度**切整条声明的切片器（`_py_statement` + `_py_two_bounds`），两枚界**按位置归属**（以深度 0 的
   ` = Field(` 分半、每半必须恰好一枚）而不是按多重集，否则"两枚界对调"这种最坏情形会全绿；
   ② `MODEL_NAME_MAX` 虽已在镜像集里但只钉了 `auth.py` 那一头，同一条 chat 请求里的 `model_name` 界无人核对。
   前端那两枚本地常量（`useChunkSelection.js:6/:7`，注释还写着"对齐 String(100)"，把**契约界**与**存储宽度**混为
   一件事）收进同一出口 ⇒ 镜像集 **七枚 → 九枚**、判据 **五条 → 六条**；改名/移动的冲击面实测只有一处
   （`useChunkSelection.test.js:10` 的 import）。**刻意不并进来两格**（理由钉进了那条判据的 docstring，不只留在台账）：
   `ParentChunk.parent_id = Column(String(100))` 是存储宽度、合法的改法是加宽列而契约留 100；`session_id` 的 100
   前端没有对应的输入框（它来自 `GET /me`）⇒ 准入条件是"前端真有一处要用这个数字"。RED 实跑 `2 failed, 4 passed`，
   八轮变异（6 轮各红 1 条 / 1 轮注释对照组全绿 / 1 轮打在接线面：`constants.js` 改 51 ⇒ jsdom `2 failed, 156 passed`，
   证明那枚常量真是被 composable 用的那一枚）；**用户可见面无行为变化**（100/50 两个数字原值搬家，文案由插值生成）。
   后端全量 `336 → 337`、离线 `312 → 313`、jsdom 仍 158、build 产物**换 hash**（`index-CWg0-YgN.js` → `index-CKhscz7G.js`，
   本轮生产码真改了，与 ⑦⑧ 的"hash 未变"不同）。台账见 `.superpowers/sdd/2026-10-08-user-auth-isolation-phase-3/progress.md`。
3. ~~两枚同名 `FakeConfig`（`tests/fakes.py:1` 与 `tests/test_migrations.py:182`）~~ ⇒ **已闭合（2026-10-08，`bcc0296` + 补正 `d89bb29`）**：本条要求的前置检查实测**答案是"依赖成立"**——`core/migrations.py:252-256` 要读四格（默认口令 + `.env` 三键），而 `fakes.py` 那枚只有 `CHROMA_PERSIST_DIR`，所以**合并这条路被实测否掉**（合了要么缺一格，要么把阶段二 Task 7 刚删掉的"写了没人读"三键塞回交付面）。缺陷随之收窄成"重名"这一件事：迁移那枚改名 `MigrationConfig`，并新增 `backend/tests/test_test_doubles.py` 用 AST 钉住**模块顶层 `Fake*` 类名唯一**（口径边界如实记：函数体内的局部同名不在射程内——那种合法同名实测存在，是 `test_llm_factory.py` 35/50/66 行的三枚 `Recorder`，作用域互不重叠；判据的扫描面因此从 `ast.walk` 收窄为 `tree.body`，正反两轮实测确认该抓的一条没漏、不该抓的一条没误伤）。台账见 `.superpowers/sdd/2026-10-08-user-auth-isolation-phase-3/progress.md`。
4. ~~`ChatHistory.user_id` / `documents.user_id` 的外键**只存在于新建库** ⇒ 做任何「注销账号」功能之前必须先补 FK 或显式级联删行，否则老库留孤儿~~ ⇒ **已闭合（2026-10-08，`423a26a`）**：补了 FK，且**刻意不做级联**。三条设计都钉成了判据——① `ensure_foreign_keys` 按 **(表, 列)** 问 `information_schema.KEY_COLUMN_USAGE`，不按约束名问（`create_all` 建的那枚叫 `documents_ibfk_1`，按名字查会在每个新库上再叠一枚重复外键，InnoDB 对不同名不拦且安静收下）；② 排在 `ensure_indexes` **之后**（列上没有可用索引时 InnoDB 会自建一枚、名字就是约束名，我们那枚再补一次 ⇒ 同列两枚，没人报错只多付写放大）；③ **不写 `ON DELETE`**（MySQL 默认 RESTRICT）——级联删得掉 MySQL 行、删不掉 Chroma 里的向量，"行没了、向量还能被召回"正是本仓一路在防的脏数据面；要删就走应用层两头删。原条目给的"或显式级联删行"这条路**被否决并写进判据**（`test_ensure_foreign_keys_never_cascades_at_the_mysql_level`）。「注销账号」从此被 MySQL 拦在 errno 1451 上，孤儿行产生不了。**预检量到计划外的一面并改了真数据**：`chat_history` 43 行的 `user_id` 全是 **1**，而 `users` 只剩 30（`default@local`）与 338——默认账号被重铸过、id 从 1 漂到 30，`backfill_chat_history` 只捡 `IS NULL` 的行，这 43 行从此读不到也删不掉；带着孤儿去 `ADD CONSTRAINT`，MySQL 回 **errno 1452**，而 `run_migrations` 挂在 lifespan 且不兜异常 ⇒ 症状是"整台后端起不来"。经使用者拍板走「先归户再建 FK」：新增 `reclaim_orphaned_owners`（先 `COUNT` 再 `UPDATE`，不拿 rowcount 当证据——本仓方言硬带 `CLIENT_FOUND_ROWS`，同值重写照样回 1），排在 `ensure_foreign_keys` 之前。**真实数据改动：43 行 `chat_history.user_id` 由 1 改为 30**（回滚 SQL 记在台账）。落库后实测：两张表各**一枚**外键、**0** 孤儿、`user_id` 列上各**只一枚**索引。判据：单测 +7、live +1（RESTRICT 行为面：探针账号自己造自己删，`default@local` 一次都不出现在 DELETE 里）+ live 那格「第二遍零 ALTER」扩到外键与孤儿（纪律：**先读 `information_schema` 确认 lifespan 已建好，才敢调那两步验幂等**——测试不许在共享库上发 ALTER/UPDATE）。十二轮变异自证、逐轮条数与还原 sha 见台账 `.superpowers/sdd/2026-10-08-user-auth-isolation-phase-3/progress.md`。
5. ~~`user_models`「至多一枚默认」靠应用层两步（判空 + 清场）⇒ 并发插入可留两枚默认；要堵得加唯一约束（MySQL 无部分索引，需生成列或应用级锁）~~ ⇒ **已闭合（2026-10-08，`e0ecfe1`）**：堵在**引擎**上，不选应用级锁。MySQL 没有部分索引，所以守卫落在一枚生成列上——`default_guard INT GENERATED ALWAYS AS (CASE WHEN is_default THEN user_id ELSE NULL END) STORED` + `CREATE UNIQUE INDEX uq_user_models_single_default ON user_models (default_guard)`；唯一索引**不管 NULL**，于是"同一人任意多枚非默认"与"每人至多一枚默认"同时成立。新库由 `create_all` 按 ORM 声明建（`Computed(..., persisted=True)`），已部署库由 `ensure_single_default_guard` 补，四步各查各的、重跑交白卷：**数重复 → 降掉除 `MIN(id)` 之外 → 补生成列 → 建唯一索引**。两处顺序是 scratch 表实测钉出来的，反了不是报错而是**整台后端起不来**（`run_migrations` 挂在 lifespan 且不兜异常，`main.py:59`）：① `ALTER … ADD COLUMN … STORED` 在**已经带着两枚默认**的数据上照样成功（两行都算出同一个 guard，此刻还没有索引管它），紧接着的 `CREATE UNIQUE INDEX` 才回 1062 ⇒ 去重必须早于建索引；② 列必须早于索引。存在性用**严格口径**问（`information_schema.COLUMNS` 带 `GENERATION_EXPRESSION <> ''`）——同名**普通列**被当成"守卫已建好"的后果是**静默的零约束**（那列由应用自己写，不写就整列 NULL，索引正好不管 NULL），比没有索引更糟；表达式全文不能逐字比（MySQL 存成小写 + 反引号），那半由 `SINGLE_DEFAULT_GUARD_EXPR` 与 ORM 声明**同源**钉住（`core/database.py` 从 `core/migrations.py` 导入）。清单给的"应用级锁"这条路**被否决**：本表写入方已有三处（`add_user_model` / `set_default_user_model` / 迁移的 `seed_default_llm`），锁要求每个写入方都自觉拿同一把。另外看着更"原子"的那条捷径 `SET is_default = (name = :t)` **实测否决**——同一份数据，目标 id 排在现任之前回 1062、之后成功，顺序依赖的约束不是约束。**顺带堵掉 ⑤ 自己会引入的谎**：`add_user_model` 原先把所有 `IntegrityError` 都回 False，端点据此回 409「该模型已在你的名单里」；守卫键一进来，"名单里根本没这个名字"也会撞键（另一事务刚立默认、这里 `is_first` 读旧快照），那句话就变成没人能查下去的假话——现在回滚后再查一次名字分流：真在名单里 ⇒ 409，不在 ⇒ 补插成非默认 ⇒ 收下。**真库 `mydb` 已落库**（`default_guard` 实测 `STORED GENERATED`、唯一索引只盖它一列、多默认用户 0、行数与默认数未变，`duplicates_cleared: 0` ⇒ **本条不改任何用户数据**，没有 ④ 那样的归户）。判据：单测 +8（迁移 6 + 形状 2）、live +2（一条问**引擎本身**收不收第二枚默认——INSERT 与 UPDATE 提升都回 1062 且消息里带着索引名；一条用 `_StaleSnapshot` 按 SQL 文本只 spoof 判空那次查询，把撞守卫键的窗口变成确定性可复现，并断言钩子恰好命中一次否则算空跑）。八轮变异逐轮一条红，真开机一遍拿到 `kb.migrations` 的 summary 原文（`single_default_guard` 三格全白卷）；逐轮条数、五条 Ruling 与挂账（索引侧的严格口径、重试嵌套分支、`set_default` 输家的 500）见台账 `.superpowers/sdd/2026-10-08-user-auth-isolation-phase-3/progress.md`。
6. ~~迁移的「缺 key 半态」分支（`llm_seeded: False`）从未在真 `.env` 上跑过 ⇒ 闭合需要一个能临时改 `.env` 的受控窗口。⑤ 那轮真开机拿到的 `llm_seeded: False` 不算这条的进展：两条早退回的是同一个值，日志与返回值都分不出来~~ ⇒ **已闭合（2026-10-08，`6a327ca`）**：走的是使用者裁定的**「不动 `.env`，改判据」**这条路（把 `.env` 改坏再改回需要一台"崩一次就起不来"的后端——`run_migrations` 挂在 lifespan 且不兜异常，风险大于收益）。第一步先把两条早退变成**可分辨**：`seed_default_llm` 的三条出口各带一枚常量 `reason`（`env_incomplete` / `already_configured` / `seeded`），`run_migrations` 的 summary 新增 `seed_reason` 把它带进开机日志；两格布尔的**名字与口径一个字未动**，这条不是改语义，是给已经存在的三条路各挂一块牌子。第二步让「缺 key 半态」在**离线门**上有一次真判据：注入 `IncompleteEnvConfig`（只抹 `OPENAI_API_KEY`，`base_url` 与模型名留着——半套配置才是本机最容易出现的形态），一次证两件事，那一遍**什么都没写**（`users` 的两列不动、`user_models` 也不塞模型名）且 summary **报得出走了哪条**。判据 +3（`test_migrations.py` 30→33；其中一条用 `caplog` 按 logger 名收三遍开机日志，钉"两遍 no-seed 的布尔逐格相同、只有 `seed_reason` 分开它们"，并钉整段日志不许出现 key），另**有意改写**四处既有的"整枚字典相等"断言（新增一格必然改写它们，两格布尔的期望没动）。七轮变异：M1 两条早退同名、M2 「已有 key」的守卫永不为真、M3 summary 不接线、M4 `and`→`or`（半套配置照抄，且**既有那条"两枚全缺"的判据照常绿**——"只缺一枚"这一半牙齿是新增那格给的）、M5 写成功那格误标、M6 `reason` 拼进库里的 key（`test_boot_log` 实测红在凭证不外印那一条断言）、M7 对照组只换字典键序 ⇒ 33 全绿（判据钉的是值不是形状）。**真开机一遍**（Temp 里的 log config，仓库代码零改动）拿到 `'llm_seeded': False, …, 'seed_reason': 'already_configured'`——⑤ 那轮只能靠读源码推断的这一格，现在是日志里读出的事实。**两处边界如实记**：真 `.env` 上"缺键"那半本机至今没跑过（证据换成离线判据）；「写了 key 但没加模型」的两支因（`LLM_MODEL` 为空 / 名单已有同名）没有各自报名。台账见 `.superpowers/sdd/2026-10-08-user-auth-isolation-phase-3/progress.md`。
7. ~~422 的 `detail[*].input` 回显，前端只靠 `client.js:32` 那条 fallback 挡着 ⇒ 要闭合就在 fallback 里剥掉 `input` 键（代价：削弱「原文是唯一的排错线索」，属产品取舍）~~ ⇒ **已闭合（2026-10-08，`74d11b8`）**：走的就是条目给的这条路（使用者裁定「前端 fallback 剥掉 input」）。数组 detail 的每一项改由模块级 `validationItemText` 决定上屏内容——**只准 `msg`（且只认非空字符串）、`type`、`loc` 三格**，兜底从"整枚 `JSON.stringify(item)`"改成**白名单挑键**；于是 `input`（FastAPI 原样回显的请求值，`PUT /api/auth/me/llm` 那一枚里躺着明文 api_key）与 `ctx`（pydantic 允许校验器塞任意值）都到不了界面。兜底挑键顺序按 FastAPI 自己的 `type`、`loc` ⇒ **阶段二既有那条「缺 msg 降级为 JSON 文本」判据的期望值一字未改仍绿**，改动面只有"input 那一格不见了"。三条网络出口（fetch / SSE / 上传的 XHR `documents.js:52`）**共用 `httpError` 这一枚构造点**，所以一处收口三条一起生效——这也是必须给 `httpError` 本身钉一条判据的理由，否则"唯一构造点"只是注释。判据 +4（`frontend/tests/client.test.js` 26→30：兜底不带 input/ctx、有 msg 时不"顺手补全上下文"、非对象项与 `null` 交出那格本身、`httpError` 直接构造的错误也不带 input；其中 ctx 的夹具载荷**故意与 secret 不同**，好让两面各有独立牙齿）。九轮变异：M1 回退整枚 stringify / M2 白名单多带 input ⇒ 各 2 红；M3 多带 ctx ⇒ **只 1 红**（input 与 ctx 分开计量）；M4 去掉 loc ⇒ 2 红（红到阶段二那条既有判据，线索不是可牺牲项）；M5 msg 放宽成"是字符串就用" ⇒ 1 红（界面只剩「请求参数不合法：」空壳）；M6/M7 非对象守卫收窄 / 去掉 null 那半 ⇒ 各 1 红（后者实测 `TypeError: Cannot read properties of null`）；M8 只换键序 ⇒ 2 红（键序属口径）；M9 **对照组**（白名单提成模块常量、行为不变）⇒ 30 全绿（判据钉输出文本不钉写法）。门禁：前端全量 **158 passed / 14 files**（起点实测 154）、`npm run build` exit 0（产物换 `index-CWg0-YgN.js`，css 未变）；后端一行未动（全量 `336 passed / 2 skipped / 2 deselected` 逐字不变，`test_frontend_constants.py` 单跑 5 passed，因为它扫的就是 `frontend/src`）。**两处边界如实记**：这道闸只管"上界面"——**422 响应体里 `input` 依然在**（devtools、反向代理访问日志、直连 API 的消费者都还能看到明文 key），要连那一面一起堵得在后端挂 `RequestValidationError` 处理器，不在本条范围；另一条绕路是"值写进 msg"（`ValueError(f'{value} 不是 URL')` 那种写法会绕过白名单），实测本仓两处 validator（`schemas/auth.py:127`、`:136`）只把**长度**写进文案，故今天不成立，挂账。台账见 `.superpowers/sdd/2026-10-08-user-auth-isolation-phase-3/progress.md`。
8. ~~视口/交互的真浏览器回归是**一次性脚本**（探针全文附在阶段二台账下方留档；`puppeteer-core` 等 25 枚 `--no-save` 装进来的包已于 2026-10-08 `npm prune` 清掉，复验 `154 passed` + build 绿、产物 hash 未变 ⇒ 它们不是真依赖，做这条要重新装）⇒ 没有常驻测试，下次改布局要重新造轮子。~~ ⇒ **已闭合（2026-10-08，`e4f572f`）**：走的是使用者裁定的**「装成 devDependency + 常驻判据」**，`puppeteer-core@^25.12.0` 进 `package.json` 与 `package-lock.json`（"验完就 prune"的时代到此结束，下一个人 `npm ci` 就能跑到）。判据放 **`frontend/tests-browser/` + `vitest.browser.config.js`**，入口 `npm run test:browser`，实数 **21 条**（本机 Edge headless，三档视口 1280×900 / 375×800 / 500×900）。三个设计口径各自都有判据支撑：① **独立目录 + 独立 config，而不是往 `vitest.config.js` 的 include 里加一项** ⇒ 单位门 `npm test` 在没起服务、没 Edge 的机器上照样能跑（新目录刻意叫 `tests-browser/`，正好躲开 `tests/**/*.test.js`）；② **前置条件失败响亮报错、不许 skip**——`requireStack` 把"dev server 连不上"与"dev 在、后端不在"分开（后者靠的是本仓已记录的那条：Vite 代理把不可达上游翻成 **502 + HTML 体**而不是网络异常），skip 会被下一个人读成"布局验过了"；③ **判据只钉数据无关的几何不变式**：不吃文档条数、不吃模型名单长度、不发问答请求，登录与登出都走 API（点 `.rail-signout` 在窄屏会被浮层遮罩吃掉），跑前跑后 `auth_tokens 1 / users 2 / documents 13 / parent_chunks 4 / chat_history 43` **逐格相同**、登出实测 **204** ⇒ 不烧配额、不写业务数据，这条命令因此可以随手重跑。21 条覆盖的是：三档共判「整页不滚 / `.chat-messages` 是有界滚动容器 / 内容长过可用高度时撑开的是消息区而不是页面」（后者靠 DOM 合成 3000px 占位块，**必须给它 `flex:0 0 auto`**——不给就被 `.chat-messages` 自己的 `display:flex; flex-direction:column` 收缩回去，实测 `scrollHeight 469 == clientHeight 469`，"溢出"这个前提根本不发生，靠量数字才发现不是靠推理）、宽屏发送键在视口内且不横向溢出、两层浮层既不压发送键也整块在视口内、≤768 的控件行与候选池退成一列、全程新增 console/page error 为 0。**首跑 12 条里那条红是判据自己写错**（`.picker-results` 是 `v-else-if="chunks.length"`，busy 与零命中两档都不渲染它 ⇒ `getComputedStyle(null)` 直接 TypeError；探针账号本来就没有可选块，这台机器上必然踩），**产品零改动**；修法是"有真实列表就量真实列表，否则往 `.picker-modal` 里挂一枚**同类名临时节点**量样式规则、量完立即删"，两种口径都回报来源（实测两支都交 `309px` / 1 track），并把**类名本身**另钉进 jsdom（`chunk-selection.test.js` 加一句断言，条数不变仍 158）。判据分两轮加宽（12 → 17/18 → 21），加宽前跑过的变异轮在新集上**全部重跑**。十四格变异全打在 `frontend/src/styles/layout.css`（基准 sha `03705068a7e9`，纯 CRLF 422/422、18468 字节；每轮手工 Edit + `cp` 还原，还原后 sha 回基准）：**三格全绿才是本轮最值钱的产出**——M1a/M2a（删 ≤768 那两行控件行 CSS）证明几何判据在"名单只有一枚短名字"时没有牙齿，于是新增一条**计算样式**判据，重跑各 `1 failed`；M5/M5b 证明 `.app-shell{grid-template-rows:minmax(0,1fr)}` 与 `.chat-main{min-height:0}` **互为兜底、缺一不红**，两行一起删才回 `1 failed「页面被顶开 2629px」`（历史 L-1 那个坏法从此有常驻防线）；M3b 弹窗高度脱开视口约束 ⇒ `4 failed`（1 条断言原文命中 `top=-90/bottom=990`，3 条是关不掉的浮层吃掉后续点击的级联）；M4 `1 failed`、M6 `2 failed`；M8 是对照组（`.panel-hint` 13px→12px）⇒ 21 全绿。**门禁**：`npm run test:browser` **21 passed / Test Files 1 passed**；`npm test` **158 passed / 14 files** 逐字不变；`npm run build` exit 0 且两枚产物 hash（`index-CWg0-YgN.js` / `index-CUrklGmJ.css`）**与 ⑦ 完全相同 ⇒ 生产码零改动**，这一格是本项最硬的自查；后端一行未动 ⇒ 三门未重跑（diff 只在 `frontend/`，口径同 ①③⑦）。**三处挂账如实记**：① `.picker-modal` 的**宽度上界 560px 没有判据**（`min(92vw,560px)` 改成 `120vw` 全绿——弹窗是 backdrop 这个 flex 容器的唯一孩子，`flex-shrink` 把它压回 100vw，且它与发送按钮纵向本就不相邻，写不出既真实又有牙齿的断言）；② ≤768 的 `height:100dvh` 与继承来的 `100%` 在桌面 headless 上是同一个数（800），`dvh` 的牙齿只在真机地址栏收放时才出现，本机造不出那个条件；③ `.settings-model-row{flex-wrap:wrap}` 没钉——它的牙齿取决于名单里名字的长度，属**数据相关**判据，与本条第 ③ 项前提相冲，真要堵得先把"长名字"变成可控夹具。台账见 `.superpowers/sdd/2026-10-08-user-auth-isolation-phase-3/progress.md`。

9. **（清单外的追加需求，使用者随后拍板）「注销账号」——硬删，MySQL 与 Chroma 两头一起抹，不可恢复** ⇒ **已闭合（2026-10-09，三闭一提交：`b12c2c2` → `594458a` → `35e9498`）**：语义选项原文是「硬删，两头一起抹（推荐）」，批准语「认了，按这个设计开始写代码」。三条闭口按依赖顺序落地，一条一提交：
   ① **`database.delete_user_cascade`**（`b12c2c2`）：一个事务里按 `auth_tokens → user_models → chat_history → documents → flush → users` 删，`documents` 走**逐行 `session.delete`** 让 ORM `cascade="all, delete-orphan"` 带走两张块表。**这条顺序只有真库能证**——④ 补的那批 RESTRICT 外键错一步就是 errno 1451，而 fake 没有第二张表、FK 不生效，任何顺序在离线门都"过"，所以判据住 live 组：一条里六格断言（先数探针名下 `2/2/2/1/2/2` 证明 fixture 真造齐，再要返回值、六表归零、`users` 行消失、`default@local` 名下前后**逐键相等**（"只砍到自己"）、同刀重放第二次报全 0）。测试侧助手 `_wipe_probe_account` **故意不调生产方法**：判据红在生产方法存在之前，漏下的行就是共享库里的永久残留。两轮变异各红 1 条（改走 `query(...).delete()` ⇒ 1451 `child_chunks_ibfk_1`，绕开 unit-of-work 就不触发 cascade；`users` 那一删提到最前 ⇒ 1451 `auth_tokens_ibfk_1`）。
   ② **`POST /api/auth/deactivate`**（`594458a`，204 无正文）：三道门按**「令牌 → 口令 → 默认账号」**排序——口令门排在默认账号门之前是刻意的（口令错时该说"你证明不了是你"，回"这个账号删不掉"等于替对方确认口令是对的），`401「原密码不正确」` 与改密码共用 `PASSWORD_WRONG` 那枚常量，`409「默认账号不能注销」` 的理由是 `ensure_default_user` 下次开机按 identifier 重铸一枚**新 id**、演示数据全在它名下，删它的表象会是"应用自己重置了"。两头删按**「行先提交、向量后清扫」**，并由两个替身往同一条时间线记账把它变成可观察事实（`events == ["rows","vectors"]`）。`VectorStore.delete_by_user_id` 里那枚 **`str(user_id)`** 是本体：metadata 存的就是字符串，Chroma 的标量相等不做隐式转换，传裸 int 的表征是"静默扫了个空"而不是报错。清扫 **try/except + 记日志、永不外抛** ⇒ 失败不把 204 报成 500（行没了就是没了，残留向量读侧一律按 `user_id` 收窄 ⇒ 是占盘的垃圾不是泄露）。`DeactivateIn.old_password` 的界 `1~64` 与 `PasswordIn.old_password` 逐字相同，空串那格必须在算 PBKDF2 之前拦住。九轮变异逐轮条数见台账（V1 裸 int / V2 只扫父集合 / V3 拆 try / E1 两头调换 / E2 删口令门 / E3 删默认账号门 / E4 不扫向量 / E5 204→200 / S1 `min_length`→0）。
   ③ **前端危险区**（`35e9498`）：设置弹窗第五节，`dangerReady = 原密码非空 && 确认词 === DEACTIVATE_CONFIRM`，两格都过才亮按钮；**没有** 原生 `confirm`（headless 里会被自动 accept，那条判据就没牙，口径同阶段二的清空对话）。确认词是**组件内**单一常量、**刻意不进 `constants.js`**——那文件的章程是"后端契约在前端的镜像"、由 `backend/tests/test_frontend_constants.py` 两头钉，塞一枚纯交互的常量会让那条门禁变成假命题；提示文案与被守住的门禁读同一枚常量，所以"屏上写的词就是被守住的那个词"这条判据有牙。成功后 `emit('deactivated')` ⇒ App 把**已有的 `handleSessionLost` 当回调使**，登出 / 运行中 401 / 注销三条清理路径共用同一段 `resetWorkspace`，代价是那个回调名读起来不像它的语义（注释里写明了是故意的）。**注销后不补发 `/logout`**：`auth_tokens` 那片行已随账号没了，那一枪只会再撞一次 401 ⇒ 回调 ⇒ 环。前端七轮变异 + 浏览器侧一轮（`.settings-danger` 加 `min-width: 420px` ⇒ 既有那条 `.settings-body` 容器不变式红在 `422 != 311`，证明新节落在它的射程内；那一轮的第二失败是**级联**——断言抛出后 `closeModal` 没执行，不是独立事实）。
   **门禁实数**（本轮全部重跑）：后端全量 **345 passed / 2 skipped / 2 deselected**（起点 337 ⇒ ① 给 live +1、② 给离线 +7、③ 后端零改动，逐闭可核对）、离线 **320 / 29 deselected**、live 单文件 **25 passed**、jsdom **162 passed / 14 files**（起点 158 ⇒ +4：封装 1、危险区 2、App 接线 1）、`npm run build` 产物换 **`index-CrrLaEBX.js` / `index-C4mVDwWj.css`**、浏览器门 **21 passed / 1 file**（**条数未变**：本条刻意不往里加"真按注销键"的判据，那会在共享真库里删掉一个账号）。零写库复核：`/api/health` 跑门前后 `document_count 4 / parent 4 / child 10` 逐格相同。
   **四面挂账如实记**：① 两个标签页并发注销**无判据也无变异轮**（今天靠 `handleSessionLost` 顺带成立）；② "越界删到别人名下"那一格只有判据、没有变异证据（跑它等于在共享库里删掉 `default@local` 的 43 条历史与 13 篇文档）；③ 注销后用同一 identifier 重新注册会拿到**新的 `users.id`**，这一格没有判据，界面上也不可见；④ 向量清扫失败的**补偿重扫入口**不存在（Ruling「best-effort 不改状态码」的代价面）。台账见 `.superpowers/sdd/2026-10-08-user-auth-isolation-phase-3/progress.md` 的「追加特性：注销账号」一节（含一次**备份撞名把 `backend/api/auth.py` 覆盖成 schema 内容**的事故与逐字重放恢复路径）。

## 九、已知验证缺口（如实记）

- 12 条判据只用了**本机 Edge headless**：没有跨浏览器；375 档是**视口模拟**不是设备模拟，真触屏 `touch` 行为未验。
  ⇒ 阶段三 ⑧ 之后这套探针已常驻（`npm run test:browser`，21 条，见第八节第 8 条），**这三条缺口原样继承**：常驻判据仍然只有本机 Edge headless、375 档仍然是视口模拟不是设备模拟、真触屏 `touch` 仍未验。
- ⑧ 那 21 条**自己的**三面未堵（都在第八节第 8 条的挂账里逐条给了原因）：`.picker-modal` 的宽度上界 560px 无判据；≤768 的 `height:100dvh` 与继承来的 `100%` 在桌面 headless 上分不出；`.settings-model-row{flex-wrap:wrap}` 属数据相关判据没钉。另：这一门**需要两份服务在跑**，且按裁定"前置条件失败响亮报错、不 skip"——没起服务时它是红的而不是灰的，跑法见第十一节。
- **② 补账（`e1f4d45`）自己的三面未堵**（理由逐条写在台账那一节的「挂账与边界」里）：
  ① `frontend/src/api/documents.js:10` 的 `limit = 50`（候选池**每页条数**）没并进镜像集 —— 它与 `parent_ids`
  的列表界是两个不同事实，数值相同纯属巧合，钉成相等会把一侧的正常改动判红；后端有没有对应的命名权威值本轮未查。
  ② `layout.css:330`「昵称上限 50 字」与 `:373`「模型名上界 100 字」两处**注释里的数字**不进门禁（② 的形状判据量的是
  真会生效的模板属性，注释漂移不改行为），代价是注释可与契约漂移。③ 新切片器 `_py_statement` 的两条早退守卫
  （字段改名 / 括号未闭合）**没有各自的变异轮**，本轮只实测了分半计数与位置归属两轮。
- **注销账号（`b12c2c2` + `594458a` + `35e9498`）自己的验证面**：浏览器门 **刻意没加**"真按注销键"的判据——
  那会在共享真库里删掉一个账号，代价与收益不成比例。于是真浏览器里这一节的**渲染**只被既有的那条
  `.settings-body` 容器不变式覆盖（变异轮 L1 证明它覆盖得到：给新节加 `min-width: 420px` ⇒ 红在 `422 != 311`），
  没有独立的几何断言；**从界面端到端真删一个账号**至今没有自动化，只有 ① 那条 live 判据用探针账号
  调过生产删除方法本身（六张表归零 + 别人名下逐键不变）。其余四面挂账见第八节第 9 条末尾。
- **并发未量**：两个标签页同时改名单只有 Task 10 的补偿测，界面侧没有。
- **默认用户那档没有在界面上手验**（只以 live ④ 组身份出现）。
- 浮层 backdrop 点击关闭与 Esc 关闭在真浏览器的表现未量（jsdom 判据有）。
- 判据 4/5 与 live ④ 组烧的是**真实配额**（2 次界面问答 + 23 条 live 里的真流式往返），本轮终审**没有重跑 live**（改动只碰那枚路由与两处注释/一行死代码，`grep "me/models" tests/test_live_*.py` 0 命中 ⇒ live 组无消费者）。

## 十、流程偏离（必须向用户明示）

按 2026-10-07 23:35 的指令「你直接接管,然后执行到任务完成」：**Task 6 收口 + Task 7-12 全部由控制者一人执行**——自己 TDD、自己跑三门、逐 Task 提交，**没有派实施代理，也没有派评审代理**，本文档所属的**终审是作者自审**，不具备独立评审的对抗性。这与 `superpowers:subagent-driven-development` 的标准流程不同，是裁定而非遗漏。阶段二的 Task 1-5 仍有独立的实施/评审/修正轮，其结论可交叉引用。

缓解措施：终审的七条承重断言全部**重新直查**（`UserOut` 唯一构造点、`default_model_of` 唯一解析函数、`chat_history` 三臂都带 `user_id`、`STATUS_BY_ERROR` 六键含 `NotConfiguredError: 409`、裸 `print` 与 `console.log` 归零、`_llm_context` 的三条 409 顺序、`_reload` 离线无牙重验）；本文档第二节的三门实数是**在 HEAD `25bf2e2` 上刚刚重跑的**，不是引用历史轮次的报告。

**2026-10-09 追加特性「注销账号」三条闭口同样是控制者一人执行**（无实施代理、无评审代理，**终审是自审**），
执行方式沿用上面那条指令。本轮两处偏离如实记在这里：① **变异备份按 `mut-<basename>` 命名造成一次文件互相覆盖**
（`api/auth.py` 与 `schemas/auth.py` basename 相同，还原时拿错了文件），恢复路径是 `git show HEAD:` 取回字节 +
从会话转录逐字重放本轮编辑，sha 与 diff 双向确认后才继续；此后备份一律按**完整路径**命名。
② **控制者自己新写的一条判据首跑红在序列假设上**（先断"填对确认词后按钮可用"、后断"密码被清掉"，
而实现按设计把两格一起清），生产代码没有错，改的是那条测的序列；细节与教训见台账「过程偏离与自纠」。

自审过程中也记下一次控制者自己的事故：还原变异时使用 `allow_multiple`，预期命中 2 处、实际命中 3 处（`GET /me` 那句本来就不带 `_reload`），靠 `sha256sum` 与基线不符 + `git diff` 露出的多余 hunk 才抓出来。教训：涉及变异还原时**先 grep 计数**，并一律以 sha/diff 为准，不以记忆为准。

## 十一、如何复现验收

```bash
# 后端（同一时刻只跑一个 pytest 进程；不要起第二个 uvicorn，Chroma 是单实例锁）
cd backend
python -m pytest -q                                    # 期望 345 passed / 2 skipped / 2 deselected（注销 ① 给 live +1、② 给离线 +7；那 2 个 skip 是需要本机 uvicorn 的流式判据）
python -m pytest -q -m "not live and not migration"     # 期望 320 passed / 29 deselected

# 前端
cd frontend
npm test                                               # 期望 Test Files 14 / Tests 162（注销 ③ 加 4 条：封装 1、危险区 2、App 接线 1）
npm run build                                          # 期望 exit 0，产物 index-CrrLaEBX.js + index-C4mVDwWj.css（③ 真改了生产码，hash 必换）

# 视口/布局的常驻浏览器门（阶段三 ⑧，`frontend/tests-browser/`，独立 config）：
# 需要两份服务**都在跑**——后端 uvicorn :8000 一份（只起一份）+ 前端 `npm run dev` :5173 一份。
# 没起服务时这一条是**红**而不是 skip，这是刻意的（skip 会被读成"布局验过了"）。
# 判据只量几何、不写业务数据、不发问答请求，所以可以随手重跑，也不烧配额。
npm run test:browser                                   # 期望 Test Files 1 / Tests 21（本机 Edge headless；跑前跑后库内行数应逐格相同）

# live 组需要真库（MySQL），流式那两条还需要真服务：先起 uvicorn（只起一份），再
python -m pytest -q tests/test_live_database.py         # 期望 25 passed（注销 ① 新增那条级联删行判据；⑤ 那轮的实数是 24）
python -m pytest -q -m live                            # ⑥ 这轮实跑 24 passed / 2 skipped / 314 deselected；
                                                       # 那 2 条 skip 是 `test_live_stream.py` 的流式判据——
                                                       # 跑这一组时 :8000 上没有服务，按"没服务就 skip"的既有
                                                       # 惯例跳过而不是假绿；本轮只起过一次服务，且只为读迁移
                                                       # summary（验完按 CommandLine 核对后停进程），没有重跑流式组，
                                                       # 不填没量过的数
```

上两行后端期望是**② 的补账（`e1f4d45`）**之后重跑的实数（全量只 +1、离线只 +1，都来自那一枚新判据）；
⑥/⑤ 轮次的实数是 `336 / 312`，⑦ 没有改动它们（⑦ 的 diff 只落在 `frontend/` 两枚文件，
后端全量当轮只重跑一次做冲击确认，逐字相同）；前端那行 **158 是 ⑦（`74d11b8`）之后的实数**（⑦ 前 154，
②补账未增减条数）。
阶段二收口那轮跑在 `25bf2e2`，同两条后端命令的实数是
`306 passed / 2 skipped / 2 deselected` 与 `285 passed / 25 deselected`（见第二节表格，历史值不追改）。
增项逐条记在阶段三台账里：① +3、② +5、② 补账 **+1 单测**（`test_frontend_constants.py` 5→6 条，镜像集 7→9 枚）、③ +1、④ +7 单测 +1 live、⑤ +8 单测（迁移 6 + 形状 2）+2 live、
⑥ +3 单测（`test_migrations.py` 30→33；另**有意改写**四处既有的"整枚字典相等"断言，两格布尔口径未动）、
⑦ **+4 前端 vitest**（`frontend/tests/client.test.js` 26→30，后端 0 增项；既有的"缺 msg 降级为 JSON 文本"那条期望值一字未改）。
⑧ **jsdom 门 0 增项、浏览器门 +21**（`npm run test:browser`，新目录 `frontend/tests-browser/` + 新 config `vitest.browser.config.js` +
新 npm script；`frontend/tests/chunk-selection.test.js` 只多了一句断言，所以 **158 这个数字没动**）。
⑧ 的 diff 只落在 `frontend/` 且**不含任何生产码**：`npm run build` 两枚产物 hash 与 ⑦ 逐字相同（`index-CWg0-YgN.js` / `index-CUrklGmJ.css`），
后端三门在 ⑧ 当轮**未重跑**（口径同 ①③⑦），那句"上表实数是 ⑥/⑤ 轮次的量"只对 ⑧ 那一轮成立 ——
② 的补账（`e1f4d45`）已把三门重跑成新值（`337 / 313 / 158`，build 换 hash），见上两段。

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
