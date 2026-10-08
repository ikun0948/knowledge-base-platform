# SDD ledger — 阶段三（清单来源：阶段二全分支终审的「阶段三顺延八条」）

计划级文档：本轮**没有新写 12-Task 计划**——八条各自是 bounded 修复，按用户 2026-10-08 的
「删掉残留，开阶段三第 1 条」逐条开工，一条一闭一提交。清单原文见
`docs/superpowers/delivery/2026-10-08-user-auth-isolation-phase-2-delivery.md` 第八节，
以及阶段二台账 `.superpowers/sdd/2026-10-07-user-auth-isolation-phase-2/progress.md`
的「全分支终审」一节。

## 执行方式（交付时必须明示的同一句话继续有效）

控制者一人执行：自己 TDD、自己跑三门、自己变异自证、自己提交，**没有实施代理也没有评审代理**。
本轮走的技能：`superpowers:test-driven-development`（RED→GREEN 全程）与
`superpowers:verification-before-completion`（写台账与提交信息前重跑取证）。

## 预检（第 ① 条派发前，2026-10-08）

真码实测（全部直查，非推测）：
- `schemas/auth.py:111-122` `LlmIn` 原状——两格 `Field(min_length=8, max_length=255/500)`，
  `base_url` 另有一枚 `_looks_like_a_url`（`value.strip().rstrip("/")` + `^https?://`）。
- `api/auth.py:157-167` 端点：`if not payload.api_key.strip(): 422「api_key 不能是空白」`，
  写库时第二次 `.strip()`。**两处的 strip 都在 Field 长度检查之后** ⇒ 这就是第 ① 条的成因。
- 现存消费者只有 `PUT /api/auth/me/llm`（`LlmIn` 全仓无其它引用），`grep -rn "me/llm\|LlmIn" tests/test_live_*.py` **0 命中** ⇒ live 组无消费者，本轮不跑 live 有依据。
- 会被连带打断的既有判据：`test_api_auth.py:371` `test_llm_config_requires_both_key_and_base_url`
  发的是 `{"api_key": "sk-x", "base_url": ""}`，只断 `422` 与 `llm_configured False`，
  **不断 detail 文案** ⇒ 新 validator 仍然 422，不冲突（实测见下）。`:358` 用的是
  `"sk-abcdef1234567890"`（18 位）与干净 URL ⇒ 不受影响。
- **同族可疑项，实测后排除**：`RegisterIn.identifier` / `LoginIn.identifier` 同样带着
  `max_length=255`（量在 strip 前），但两枚都挂了归一 validator
  （`normalize_identifier(...)` / `value.strip()` 再按 `@` 决定大小写），空白进不了库 ⇒
  **不是同一个洞**，不扩大本轮范围（裁定理由：改了它就要动注册/登录两条链路，
  而它们的判据本轮一条都不红）。

## 第 ① 条 — LlmIn 两格的长度界改量 strip 之后

- BASE：`ddc9144`（阶段二交付文档）。实现提交 **`de8499d`**（3 files / +84 −11：
  `schemas/auth.py`、`api/auth.py`、`tests/test_api_auth.py`）。
- 起点三门实数：**306 passed / 2 skipped / 2 deselected / 1 warning**（74.63s）、
  离线门 **285 passed / 25 deselected / 1 warning**（65.36s）、聚焦 **47 passed**。
  这三枚数字是在 `25bf2e2` 上为写交付文档重跑的，本轮起点即它。
- **RED**：三条新判据各钉一个行为，实跑 `3 failed, 47 deselected`，且逐条确认"为自己的原因红"：
  - `test_api_key_is_too_short_when_the_length_comes_from_padding` ⇒
    `AssertionError: strip 后只有 5 位的 key 被当成 9 位放行了：200`（这条就是缺陷本体）。
  - `test_api_key_padding_does_not_push_it_over_the_column_bound` ⇒
    `422 {"detail":[{"type":"string_too_long","loc":["body","api_key"]…`（反方向：合法值被拒）。
  - `test_base_url_padding_does_not_push_it_over_the_column_bound` ⇒ 同型，`loc` 是 `base_url`。
- **GREEN**：两格去掉 Field 的长度约束，检查搬进 `field_validator`（先 strip 再量，返回洗净值）；
  `base_url` 的长度检查**排在协议检查之前**。聚焦 `50 passed`（47 + 3）。
- **Ruling（空白那一格留在端点，不并进 schema）**：`_strip_then_measure_key` 对空串放行
  （`if value and not 8 <= …`），因为端点那句 `422「api_key 不能是空白」` 是**一句话的 detail**，
  而 pydantic 给的是数组；`test_blank_api_key_is_422_and_writes_neither_column` 逐字钉着那句。
  代价：`api_key` 的非法值有两个出口（schema 管"有内容但太短/太长"、端点管"没内容"），
  读代码的人要在两处之间跳一次——已由变异 B 证清两者不互相顶班。
- **Ruling（端点第二次 `.strip()` 删掉，而不是留着当保险）**：schema 返回的已是洗净值，
  留着就是"为不可能发生的场景加防护"；同时那段注释原写「`min_length=8` 量的是 strip 之前」，
  事实变了就说它的这句话必须一起改（与阶段二对 `_drop_probe_account`/`migrations.py:28`
  的裁定同一口径）。
- **变异自证**（手工编辑 + `git diff` 双向确认 + sha256 对拍；`schemas/auth.py` 是纯 LF，
  动手前实测 CRLF 0 / LF 187）：
  - A：把 `max_length=255/500` 加回两枚 Field ⇒ `2 failed, 1 passed`。红的是两条 padding 判据，
    下界那条绿（它测的不是上界）⇒ 两条上界判据**有牙且分工不重叠**。
  - B：拔掉 `api_key` 的长度检查（只留 strip）⇒ `1 failed, 2 passed`。红的是下界判据，
    **空白那条仍绿** ⇒ 同时证明 Ruling 的那句"空白由端点负责"是真话，不是巧合。
  - 还原校验：`schemas/auth.py` sha256 前缀 `5a0d523654c19c05` 与改前**逐字节相同**，
    `grep -n "max_length=255\|max_length=500" schemas/auth.py` 只剩 `:35/:47` 两枚 `identifier`
    （既有、与本轮无关）⇒ 零变异残留。
- **终态三门实数（还原后复跑）**：全量 `309 passed / 2 skipped / 2 deselected / 1 warning`（39.22s）、
  离线门 `288 passed / 25 deselected / 1 warning`（33.65s）、聚焦 `50 passed`（28.34s）。
  对账：306+3=309、285+3=288、47+3=50，三处全部吻合，**没有一条既有判据被打断**。
- 前端零改动 ⇒ `npm test` / `npm run build` 未重跑（本轮 diff 只碰后端三枚文件）。
  注：本轮开工前 `npm prune` 清掉了阶段二 Task 12 残留的 `puppeteer-core` 等 25 枚
  `--no-save` 装进来的包，并当场复跑过 `154 passed` + build 绿、产物 hash 未变
  （`index-CUrklGmJ.css` / `index-DGgHp3J3.js`）⇒ 那 25 枚不是真依赖。
- **一条行为变化要告诉用户**：贴进来的 key 若两侧带空白，现在**入库的是洗净后的整串**，
  而"strip 之后不足 8 位"从原来的 200（存进一把残缺 key）改成 422。反方向也一起通了：
  正好 255 位 / 500 位的合法值再也不会因为多贴一个空格被拒。

## 清单进度

| 条 | 事项 | 状态 |
|---|---|---|
| ① | `LlmIn` 两格长度界量在 strip 之前 | **已闭合**（`de8499d`） |
| ② | `AVATARS` 两份 / `PASSWORD_MIN` 三份没有单一出口 | 待开工 |
| ③ | 两枚同名 `FakeConfig`（`tests/fakes.py:1`、`tests/test_migrations.py:182`） | 待开工 |
| ④ | `ChatHistory.user_id` / `documents.user_id` 的 FK 只在新建库存在 | 待开工（做任何"注销账号"前必须先补） |
| ⑤ | `user_models` 至多一枚默认靠应用层两步，并发可留两枚 | 待开工 |
| ⑥ | 迁移的"缺 key 半态"分支从未在真 `.env` 上跑过 | 待开工（需要一个能临时改 `.env` 的受控窗口） |
| ⑦ | 422 的 `detail[*].input` 回显，只靠 `client.js:32` 那条 fallback 挡着 | 待开工 |
| ⑧ | 视口/交互探针是一次性脚本，没有常驻回归测试 | 待开工（`puppeteer-core` 本轮已 `npm prune` 清掉，做它要重装） |
