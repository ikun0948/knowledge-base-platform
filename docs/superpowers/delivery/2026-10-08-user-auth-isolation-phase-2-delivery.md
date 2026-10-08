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

两处诚实注脚：

1. 全量门的 **2 个 skip** 是 `-m live` 的两条流式测（本机此刻没有 uvicorn）；它们在 Task 12 的「服务在」那一档真跑过，实数 `23 passed / 286 deselected / 1 warning in 143.72s`，**且无一条 skip**。
2. 唯一的 **1 warning** 是既有噪声 `core/database.py:13` 的 `declarative_base()` MovedIn20Warning，阶段二没有触碰该行，不属本轮引入。

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
8. **`PASSWORD_MIN` 是 6 不是 8**（`schemas/auth.py:13`），前端两处已同步。
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
- **Task 4/5/6**：数字口径与类型标注类 **保持现状**；两枚同名 `FakeConfig` → ③；`ChatHistory.user_id` 的 FK 只在新建库存在 → ④。
- **Task 8 M-A**（`%2F`）**已闭合** —— 本条从「未验」变成实测并修在生产路由上，是本轮最有价值的一条。M-C（`ApiError.status` 取值域）**保持现状**：界面层不按 `err.status` 分支（Task 11 的裁定就是不按状态码改写文案）。
- **Task 9/10/11**：`?? '我'` **已闭合**；其余（弹窗只在 setup 回填、`.settings-*` 复用 `.picker-*` 底座、八条 R 裁定）**保持现状/维持**，Task 12 的判据 11/12 已把相关 rect 量过。

## 八、阶段三开工单（明确不在阶段二范围，每条给「要闭合得做什么」）

1. `LlmIn.api_key`/`base_url` 的长度界量在 **strip 之前** ⇒ 在 `field_validator` 里 strip 完再量，并补一条「8 格里 4 格空白 + 4 字符 key」的判据。
2. 前后端枚举清单没有单一出口：`AVATARS` 两份（`api/auth.py:27` / `SettingsModal.vue:19`）、`PASSWORD_MIN` 三份（`schemas/auth.py:13` / `AuthPanel.vue:14` / `SettingsModal.vue:25`）⇒ 加一枚 options 端点，或前端集中 constants 并用判据钉住与后端逐字相同。
3. 两枚同名 `FakeConfig`（`tests/fakes.py:1` 与 `tests/test_migrations.py:182`）⇒ 合并前先确认迁移组判据不依赖局部那份的四键形状。
4. `ChatHistory.user_id` / `documents.user_id` 的外键**只存在于新建库** ⇒ 做任何「注销账号」功能之前必须先补 FK 或显式级联删行，否则老库留孤儿。
5. `user_models`「至多一枚默认」靠应用层两步（判空 + 清场）⇒ 并发插入可留两枚默认；要堵得加唯一约束（MySQL 无部分索引，需生成列或应用级锁）。
6. 迁移的「缺 key 半态」分支（`llm_seeded: False`）从未在真 `.env` 上跑过 ⇒ 闭合需要一个能临时改 `.env` 的受控窗口。
7. 422 的 `detail[*].input` 回显，前端只靠 `client.js:32` 那条 fallback 挡着 ⇒ 要闭合就在 fallback 里剥掉 `input` 键（代价：削弱「原文是唯一的排错线索」，属产品取舍）。
8. 视口/交互的真浏览器回归是**一次性脚本**（探针全文附在台账下方留档，`puppeteer-core` 以 `--no-save` 残留在 `frontend/node_modules`）⇒ 没有常驻测试，下次改布局要重新造轮子。

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
python -m pytest -q                                    # 期望 306 passed / 2 skipped / 2 deselected
python -m pytest -q -m "not live and not migration"     # 期望 285 passed / 25 deselected

# 前端
cd frontend
npm test                                               # 期望 Test Files 14 / Tests 154
npm run build                                          # 期望 exit 0

# live 组与浏览器判据需要真服务：先起 uvicorn（只起一份），再
python -m pytest -q -m live                            # 期望 23 passed 且无 skip
```

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
