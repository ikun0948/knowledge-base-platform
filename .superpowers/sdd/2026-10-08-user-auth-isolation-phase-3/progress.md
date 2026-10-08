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

## 第 ② 条 — 前后端镜像常量收到单一出口，判据放 pytest 两头钉

- BASE：`da4b942`（第 ① 条的交付文档销账）。实现提交 **`ee117fd`**
  （4 files / **+194 −19**：新增 `backend/tests/test_frontend_constants.py` 176 行、
  `frontend/src/constants.js` 13 行，改 `AuthPanel.vue`、`SettingsModal.vue`）。

### 预检（直查，非推测）

- **副本实况 = 7 处声明**：`AuthPanel.vue` 里 `EMAIL_RE`/`PHONE_RE`/`PASSWORD_MIN`/
  `PASSWORD_MAX`/`NICKNAME_MAX` 五枚，`SettingsModal.vue` 里 `AVATARS`/`AVATAR_LABELS`/`PASSWORD_MIN`
  ⇒ **`PASSWORD_MIN` 三份**。权威定义：`schemas/auth.py:11-13`（两枚正则 + `PASSWORD_MIN = 6`）、
  `api/auth.py:27` 的 `AVATARS` 元组、`schemas/auth.py` 各 `Field` 里的 `max_length`
  （**后端这三格没有命名**：`password` 64、`nickname` 50、`name` 100）。
- **另有三种名字扫描看不见的副本形态**（实测）：`AuthPanel.vue:119 placeholder="至少 6 位"`、
  `SettingsModal.vue:144 maxlength="50"`、`SettingsModal.vue:196 maxlength="100"`。
- **会被连带打断的既有判据**：`AuthPanel.test.js:131/175` 断言文案「密码至少 6 位」、
  `SettingsModal.test.js:113` 断言「新密码至少 6 位」。两处的 6 都由 `PASSWORD_MIN` 插值生成 ⇒
  绑定常量后字符串逐字不变，实测复跑仍绿（未改动任何一条 vitest 判据）。
- `grep -rn "constants.js" frontend/src` 开工前 0 命中 ⇒ 项目**没有**跨端共享常量层，
  新建一枚模块不会与既有 import 冲突。
- live 组无消费者（本轮只碰前端与判据文件，未碰任何端点）。

### RED → GREEN（两轮，因为第 7 枚镜像与模板形态是量出来后追加的）

- **第一轮**（三条判据：单一声明模块 / 镜像==后端 / 头像标签同枚覆盖）：红在扫描面抓到 7 处声明
  （offender 列表逐条给 `(相对路径, 行号, 名字)`）。落 `constants.js` + 两组件改 import 后绿，
  当时全量 `312 passed`（= 309 + 3）、离线 `291 passed`（= 288 + 3）。
- **第二轮**（追加 `MODEL_NAME_MAX` 与两条形状判据后，未改前端就先跑）：实跑
  **`4 failed, 1 passed`**，四条红各自的理由都不同，逐条核过：
  1. 声明集判据 ⇒ `实抓 ['AVATARS','EMAIL_RE','NICKNAME_MAX','PASSWORD_MAX','PASSWORD_MIN','PHONE_RE']`，
     `Extra items in the right set: 'MODEL_NAME_MAX'`（第 7 枚还没落地）。
  2. 镜像==后端 ⇒ `constants.js 里抓不到 \`export const MODEL_NAME_MAX = 数字\``（解析器的下限声明生效）。
  3. 形状判据（maxlength）⇒ offender `('components/SettingsModal.vue', 144, 'maxlength="50"')` 与 `:196`。
  4. 形状判据（placeholder）⇒ offender `('components/AuthPanel.vue', 119, '至少 6 位')`。
- **GREEN**：`constants.js` 加第 7 枚；三处模板字面量改绑常量（`SettingsModal.vue` 的 import
  同步补 `NICKNAME_MAX`/`MODEL_NAME_MAX` —— 少补一个就是"绑了个 undefined、上界静默消失"）。
  聚焦 **`5 passed`**。

### Ruling

- **判据放 pytest，不放 vitest**（也否决了"开一枚 `GET /api/auth/options` 让前端拉"）：
  漂移更可能由后端那一侧引入，而后端改动的人往往不跑 `npm test`；放 pytest 后，
  **改后端不改镜像 ⇒ 下一道后端门就红**，改镜像不改后端 ⇒ 同一道门红。端点方案的代价：
  要进认证白名单、要给一个同步表单加异步加载态、而且首屏仍需一份编译期兜底副本 —— 那正是本条要消灭的东西。
- **头像只比集合不比顺序**：后端那枚元组管的是"收不收"（`not in AVATARS` 就 422），
  前端的顺序是选择条的显示顺序，属界面自选。比顺序会把"调一下按钮次序"变成跨端改动。
- **后端源码本轮一行没动**：三格 `max_length` 没有命名，是判据按**字段名**抓行
  （`_py_field_maxes`），不为了被测而给后端加常量或改名。成本：后端若把这三格挪去
  `model_validator` 里手写，解析器会抓空并**主动红**（`assert values` 那句），不会静默假绿。
- **明知可加而不加的第 6 臂**："`:maxlength="X"` 里的 X 必须在 `constants.js` 真存在"。
  M7 已经证明**只要名字在 `NAMES` 里**，删掉声明会同时红两条（声明集 + 镜像），
  漏网只剩"把名字打错成一个陌生标识符"这种假想形态 ⇒ 不为它加判据（同"不为不可能发生的场景加防护"口径）。

### 变异自证（七轮，全部手工 Edit + `cp` 还原 + sha256 对拍；聚焦文件纯 LF，实测 CRLF 0）

| 轮 | 变异 | 结果 | 红在哪条 |
|---|---|---|---|
| M1 | 后端 `PASSWORD_MIN = 6` → `7` | `1 failed, 4 passed` | 镜像==后端（`assert 6 == 7`，两侧带 `_js_number`/`_py_number` 标签） |
| M2 | 在第三个组件 `ChatInput.vue` 再立一份 `const PASSWORD_MIN` | `1 failed, 4 passed` | 单一声明模块（offender 给到文件+行号） |
| M3 | 删掉 `AVATAR_LABELS` 里 `'🚀'` 那一格 | `1 failed, 4 passed` | 标签覆盖（镜像那条**仍绿**：它只比 `AVATARS`，不比标签 ⇒ 两条分工不重叠） |
| M4 | 后端 `EMAIL_RE` 的 `{2,}` → `{3,}` | `1 failed, 4 passed` | 镜像==后端（逐字符 diff 打在顶级域下界上） |
| M5 | `AuthPanel.vue` placeholder 退回写死「至少 6 位」 | `1 failed, 4 passed` | 形状判据（placeholder） |
| M6 | `SettingsModal.vue` 昵称退回写死 `maxlength="50"` | `1 failed, 4 passed` | 形状判据（maxlength） |
| M7 | 删掉 `constants.js` 的 `MODEL_NAME_MAX` 整行 | `2 failed, 3 passed` | 声明集 + 镜像（**一轮红两条**：第 7 枚被两条同时管着） |

- 还原校验：`schemas/auth.py` `5a0d523654c1`、`api/auth.py` `0201d84f1bc6`、
  `test_frontend_constants.py` `0e168e77d4d0`、`constants.js` `4b3b08ad56fe`、
  `AuthPanel.vue` `68df8ea834fe`、`SettingsModal.vue` `35060b7c463a` —— 六枚全部与变异前**逐字节相同**；
  再直查 `PASSWORD_MIN = 6`、`EMAIL_RE …{2,}$`、两处 `maxlength` 无写死数字、`ChatInput.vue` 无副本
  ⇒ 零残留。`git status --short` 最终只剩本轮四个交付物。

### 终态门禁实数（还原后复跑）

- 后端全量 **`314 passed / 2 skipped / 2 deselected / 1 warning`**（45.84s）
- 离线门 `-m "not live and not migration"` **`293 passed / 25 deselected / 1 warning`**（36.01s）
- 聚焦 `tests/test_frontend_constants.py` **`5 passed`**
- 前端 **`Tests 154 passed (154)` / `Test Files 14 passed (14)`**、`npm run build` exit 0
  （`index-CUrklGmJ.css 13.49 kB` 未变，`index-CH0iZltg.js 101.22 kB` ← 原 `index-DGgHp3J3.js`）
- 对账：`309 + 5 = 314`、`288 + 5 = 293` ⇒ **既有判据一条没被打断**；前端 154 未变是预期的
  （跨端判据全在 pytest 侧，本轮没新增 vitest 用例，也不改既有断言）。
- 风格 grep：`console.log|debugger` 在 `frontend/src` **0**；组件内 `<style` **0**。
- live 两组未跑：本轮 diff 只碰前端两组件 + 一枚新模块 + 一枚判据文件，端点与 DB 一行未动。

### 用户可见面

**没有可观察的变化**。三处写死的数字换成绑定常量后渲染出的仍是同一个 `maxlength="50"`/
`maxlength="100"`/同一个「至少 6 位」文案（那两串文案正是既有 vitest 判据逐字钉着的）。
收益在下一轮：以后改后端那一格，`npm test` 全绿也不再是安全信号——后端门会直接红。

### 过程偏离与自纠，如实记

- **M3 起初用 python 脚本 `replace`（带 `assert count == 1`）做的变异** —— 与"变异只许手工编辑"的
  长期约束不符。当场撤销、`cp` 还原并核对 sha256 后，改用 Edit 工具重做。此后 M1/M2/M4–M7 全为手工编辑。
- **行尾测量假阳性**：在 Git Bash 里 `grep -c $'\r$'` 对一枚纯 LF 文件报 187/187 —— ANSI-C 引用被
  shell 吃掉后剩下的模式是 `$`（匹配每一行）。权威办法是
  `python -c "b=pathlib.Path(p).read_bytes(); print(b.count(b'\r\n'), b.count(b'\n'))"`。
  本轮六枚被碰文件实测全纯 LF。
- 判据自身先红过一次：解析器最初写 `\s*(?:const|let|var)`，漏 `export` ⇒ `hits == []`，
  空集下限守卫（`assert hits, "…空集假绿"`）当场把它抓住 —— 这条守卫的存在理由被实测验证了一次。
  同轮还纠出三处自写缺陷：`{int} == set(...)` 写成了 `int == set`（永不可能成立）、
  `_js_number`/`_js_regex_source` 不容行尾注释、`nickname` 会被 `\w*name\w*` 抓进模型名那一格
  （50 与 100 混集）⇒ 现都改为显式字段名正则，并把坑写进 `_py_field_maxes` 的 docstring。
- **一处记录更正**：`bd75263` 的提交信息标题写「两处过程偏离」，而这一节实际列了**三条**
  （脚本化变异、行尾测量假阳性、判据自身的四处自纠）。引用该提交时按三条口径说。

## 第 ③ 条 — 两枚同名 `FakeConfig`：缺陷是重名，不是双份

**BASE `ffc62e0` → 代码 `bcc0296`（2 files，+61/−5）+ 补正 `d89bb29`（1 file，+9/−4）。**

### 预检（挂账原文要求的那一句）

挂账写的是「合并前先确认迁移组判据不依赖局部那份的四键形状」。实测**依赖成立**：
`core/migrations.py:252-256` 读 `config.DEFAULT_USER_PASSWORD` + `OPENAI_API_KEY` /
`OPENAI_BASE_URL` / `LLM_MODEL` 四格，而 `tests/fakes.py:1` 那枚只带 `/api/health` 读的
`CHROMA_PERSIST_DIR`。⇒ **合并这条路直接否掉**（合了就缺一格，或者把阶段二 Task 7 以
「写了没人读的字段在本仓是负资产」删掉的三键重新塞回交付面），剩下的缺陷只有"重名"这一件事。

### 开工前形态（口径写死，免得下一个人复现不出来）

从 BASE 的 blob 量（不是工作树，`tests/` 当时与 `ffc62e0` 相同）：25 枚 `.py`、
`Fake*` 前缀的**模块级类声明 13 枚**、去重 12 个名字，唯一重复的是 `FakeConfig`
（`fakes.py:1`、`test_migrations.py:182`）。不限前缀时是 45 枚声明、43 个名字，
重复的变成 `Recorder`（×3，全在 `test_llm_factory.py` 的 35/50/66 行、各待在自己的测试函数里）。

### RED → GREEN

- RED：`tests/test_test_doubles.py` 第一次跑 → `1 failed`，红在
  `同名替身 {'FakeConfig': [('fakes.py', 1), ('test_migrations.py', 182)]}`。
- GREEN：`test_migrations.py` 那枚改名 `MigrationConfig`（定义 1 处 + 使用 3 处），
  docstring 里写清"与 `fakes.FakeConfig` 不是同一个替身，也不该合并"并把判据指回
  `tests/test_test_doubles.py` → 聚焦 **`18 passed`**。

### 变异自证（六轮，全部手工编辑 + `cp` 还原 + sha256 双向确认）

| 轮 | 变异 | 结果 | 说明 |
|---|---|---|---|
| N1（对照组） | 把 `MigrationConfig` 再改成与 `fakes.py` 无关的 `MigrationProbe` | `18 passed`（**绿**） | 判据管的是"重名"这件事，不是记住了 `FakeConfig`/`MigrationConfig` 这两个具体名字 |
| N2 | `test_migrations.py` 末尾模块顶层追加 `class FakeRAG: pass` | `1 failed`，红在 `{'FakeRAG': [('fakes.py', 84), ('test_migrations.py', 419)]}` | 不限于 `FakeConfig` 那一对，是通用判据 |
| N2' | 口径收窄成 `tree.body` 之后重做 N2 | `1 failed`，同一个 `FakeRAG` 集 | 收窄没把该抓的放掉 |
| N3 | 扫描面的 glob 改成匹配不到任何文件 | `1 failed`，红在空集守卫那句消息 | 目录挪窝/改名时这条判据不会静默假绿 |
| N4 | 函数体内放一枚 `class FakeRAG`（口径 = `tree.body`） | `1 passed`（**绿**） | 函数内的局部类出不了那个函数，同名互不可见，不是本条的缺陷 |
| N4b（反证） | 同一枚 N4 变异挂着，把扫描面临时改回 `ast.walk` | `1 failed`，红在 `{'FakeRAG': [('fakes.py', 84), ('test_migrations.py', 420)]}` | 证明"顶层 vs 整棵树"是有后果的口径选择，不是注释里的装饰话 |

- 还原校验：`test_migrations.py` `f8ca71fd6433`、`test_test_doubles.py` `8069f2565de3`、
  `fakes.py` `911d5c4abff3`（全程未参与变异）—— 与变异前快照 `mut3e/` **逐字节相同**；
  `_mutation_N` 标记在 `tests/*.py` grep 零命中，唯一命中是一枚过期 `.pyc`。

### 终态门禁实数（还原后复跑）

- 后端全量 **`315 passed / 2 skipped / 2 deselected / 1 warning`**（40.83s）
- 离线门 `-m "not live and not migration"` **`294 passed / 25 deselected / 1 warning`**（35.29s）
- 聚焦 `tests/test_test_doubles.py tests/test_migrations.py` **`18 passed`**（3.26s）
- 对账：② 收口是 314 / 293，本轮 +1 枚新判据 ⇒ **既有判据一条没被打断**。
- 前端未跑：`npm test` / `build` 本轮不重跑 —— diff 只有 `backend/tests/` 两枚文件，
  生产码与前端一行未动（与 ① 的处理口径一致，不是遗漏）。
- live 两组未跑：同上理由。

### 用户可见面

**没有可观察的变化**：改的是测试文件里的类名与一枚新判据，生产码零 diff。
收益在下一轮：以后谁在 `backend/tests/` 再立一枚同名 `Fake*` 替身，后端门当场红，
不用等评审看见。

### Ruling

1. **钉"名字唯一"，不合并两枚 config 替身** —— 预检实测迁移判据依赖四键形状，
   合并要么缺一格、要么把 `.env` 三键塞回交付面（Task 7 刚删过）—— 代价：将来真出现
   "两枚该合成一枚"的正当合并，这条判据不会替人做判断，仍靠评审。
2. **口径 = 模块顶层 + `Fake*` 前缀** —— 不限前缀会把 `Recorder`×3 那种函数内合法同名判红；
   用 `ast.walk` 会把局部类算进来（N4b 实测红过）—— 代价：藏在函数体内的同名生产码替身
   不在射程内（今天实测 0 枚），真有那天需要另加一条。
3. **改名而不是移动位置**（把迁移那枚搬进 `fakes.py` 也能消重名）—— 搬过去就等于把四键
   塞进共享交付面，正是 Ruling 1 要挡的方向 —— 代价：`test_migrations.py` 多一枚局部替身，
   读它的人要看 docstring 才知道它为什么不和 `fakes.FakeConfig` 合体。
4. **补正单独一笔提交（`d89bb29`），不 amend `bcc0296`** —— 那笔已经在台账口径里是"③ 的代码"，
   且 `d89bb29` 的 diff 本身带着两轮新实测（N4/N4b），混进前一笔会让变异表与提交对不上 ——
   代价：③ 占两笔，读的人要知道它们是同一条。

### 过程偏离与自纠，如实记

- **注释里的"35 个类名"是我先写下、后复现不出来的数字**：`Fake*` 口径实测 13，全类名口径 45，
  35 哪一种都不是。按"数字一律实测"的长期约束，从 BASE 的 blob 重量出 13/12/唯一重复 `FakeConfig`
  之后才改进注释（`d89bb29`）。这正是本仓记忆里那条"计划数字别凭回忆"的又一次命中。
- **口径写在注释里、实现却不匹配**：docstring 说"模块级、跨文件可见"，代码用 `ast.walk`
  连函数体内的一起抓。纠法是把口径钉进实现（`tree.body`）再正反各测一轮（N4 绿 / N2' 红），
  而不是只把注释改软。
- **N4 第一次做变异时锚点选错，真写坏了文件**：我把锚点定在 `def test_run_migrations_self_heals_…():`
  那一行整行替换，等于删掉原测试函数头、把它的 docstring 与函数体挂到我的探针上。
  当场 `cp` 还原、核对 sha `f8ca71fd6433` 与那句 `def` 计数回到 1，再改用"文件末尾 + 唯一锚点"重做。
  教训与 10-07 那条同源：**锚点要选唯一且不被替换内容依赖的行**，`Edit` 的"1 replacements"不代表结构完好。

## 第 ④ 条 — 补 `user_id` 的外键：真库里躺着 43 行孤儿，于是先归户再 ALTER

**BASE `8b17698` → 代码 + 判据 `423a26a`（4 files，+356/−9：生产码 `core/migrations.py` `core/database.py`、测试 `tests/test_migrations.py` `tests/test_live_database.py`）。**

### 预检（真库 `mydb`，只读）

`SELECT … FROM information_schema.KEY_COLUMN_USAGE WHERE REFERENCED_TABLE_NAME='users'` 只回两枚：
`auth_tokens_ibfk_1`、`user_models_ibfk_1` ⇒ `documents.user_id` / `chat_history.user_id` **确实没有外键**
（挂账那句"只存在于新建库"被证实）。逐表再量行数、NULL 主人数、孤儿数：

| 表 | 行数 | `user_id IS NULL` | 指向不存在账号 | user_id 上已有的索引 |
|---|---|---|---|---|
| `documents` | 13 | 0 | 0（全部 = 30） | `idx_documents_user_id` |
| `chat_history` | 43 | 0 | **43**（全部 = 1） | `idx_chat_history_user_id` |

`users` 当时只有两行：`(30, default@local)` 与 `(338, 3143958700@qq.com)`。孤儿根因是**默认账号被重铸过、
id 从 1 漂到 30**，而那 43 行当年写入时就带着值 ⇒ `backfill_chat_history` 的 `WHERE user_id IS NULL`
永远不会再碰它们。这 43 行的实际处境是**谁也读不到**（`GET /api/history` 按 `user_id` 收窄）**也删不掉**。

后果链：带着孤儿去 `ADD CONSTRAINT` ⇒ MySQL 回 **errno 1452**；而 `run_migrations` 挂在 lifespan 且不兜异常
⇒ 症状不是"这条迁移没做成"，是**整台后端起不来**。

### 拍板（唯一一次打断使用者，因为要动真数据）

给出三条：① 先归户给默认用户再建 FK ② 有孤儿就跳过那张表、只建 `documents` 那半 ③ 这条退回挂账。
**使用者选 ①**（`先归户给默认用户再建 FK（推荐）`）。真实数据改动：**43 行 `chat_history.user_id` 1 → 30**，
原值与反向 SQL 记在这里，可回滚：`UPDATE chat_history SET user_id = 1 WHERE user_id = 30`（只在"确要退回"时执行，
那 43 行 id=1 现在指向的是不存在的账号）。

### RED → GREEN

- FK 判据 RED：`5 failed / 17 passed`（聚焦 `test_migrations.py`，3.92s）。两类红因：
  `AttributeError: module 'core.migrations' has no attribute 'ensure_foreign_keys'`、
  `ValueError: min() iterable argument is empty`（顺序判据拿不到 `ADD CONSTRAINT` 的下标）。
- GREEN：`ensure_foreign_keys` + `foreign_key_exists`（按 **(表, 列)** 问 `KEY_COLUMN_USAGE`）
  + `add_foreign_key`（不写 `ON DELETE`）+ `run_migrations` 接线 + summary 加 `foreign_keys_added`
  → **`22 passed`**。
- 孤儿判据 RED：`2 failed / 22 passed`（`… has no attribute 'reclaim_orphaned_owners'`、
  顺序判据那条 `min()` 空集）→ GREEN **`24 passed`**（`orphaned_owner_count` + `reclaim_orphaned_owners`，
  排在 `ensure_foreign_keys` 之前，summary 加 `orphan_rows_reclaimed`）。
- 两处**夹具洞**在 GREEN 路上当场补掉（都属"判据自己先骗人"）：
  ① `FakeConn` 解析 `ADD CONSTRAINT` 时取列名用了 `.split("(")[1].strip()`，拿到的是
  `` `user_id`)``，键集变成 `{('chat_history', chr(96))}` ⇒ 第二遍判据会以夹具原因长红；改为再 `split(")")`。
  ② `conn.executed.count("ADD CONSTRAINT") == 2` —— `list.count` 比的是**整元素相等**，`executed` 里存整句 SQL，
  所以**永远数到 0**，这条幂等判据会**长期假绿**。改为 `sum(1 for s in … if "ADD CONSTRAINT" in s)`，
  并把理由写进判据注释里（不是只改代码，要让下一个人不再踩）。

### 变异自证（十二轮，全部手工 Edit + `cp` 还原 + sha256 与符号计数双向确认）

聚焦文件纯 LF（实测 `core/migrations.py` CRLF 0 / LF 361）。八轮 FK 的还原基准 sha `9970aa41d026`（17252 字节），
四轮孤儿的还原基准 sha `6722508c2367`（19783 字节）——每轮还原后都重新打 sha 并 `grep -c` 被替换的那一句回到 1（或 2/5）。

| 轮 | 变异 | 结果 | 红在哪条 |
|---|---|---|---|
| N1 | 删掉 `added.append((table, constraint))`（发 DDL 却永远交空清单） | `2 failed / 20 passed` | `…alters_only_when_missing` + `…reports_foreign_keys_and_goes_quiet…` ⇒ 判据吃**返回值**，不吃日志 |
| N2 | 去掉"先查"这一格，无条件发 `ALTER` | `3 failed / 19 passed` | 缺才 ALTER / 按列不按名 / 幂等三条一起红 |
| N3 | 按**约束名**问（换成同文件里按名字问的 `index_exists`） | `3 failed / 19 passed` | 同 N2 三条 ⇒ "问法"不是修辞，`documents_ibfk_1` 那个事实答不出来 |
| N4 | DDL 加 `ON DELETE CASCADE` | `1 failed / 21 passed` | `…never_cascades_at_the_mysql_level`（唯一管级联的那条，不多咬） |
| N5 | `ensure_foreign_keys` 挪到 `ensure_indexes` 之前 | `1 failed / 21 passed` | `…adds_the_keys_after_the_indexes` |
| N6 | 函数留着、`run_migrations` 里那一步不接线 | `4 failed / 18 passed` | `NameError: name 'foreign_keys' is not defined`（summary 那几行）——红的四条里 **2 条是本次新增**（`…adds_the_keys_after_the_indexes`、`…reports_foreign_keys_and_goes_quiet…`），**2 条是既有**（`…stamps_after_documents_are_claimed`、`…self_heals_a_crash_between_claim_and_stamp`）⇒ 动 `run_migrations` 的形状一定会被既有判据连带抓住 |
| N7 | summary 键名 `foreign_keys_added` → `fks_added` | `1 failed / 21 passed` | 幂等/可数那条；同轮 `grep` 实查 `columns_added\|indexes_added\|foreign_keys_added` 生产侧只 `migrations.py:313` 一处命中 ⇒ 键名没有别的消费者，改名=对上游失联 |
| N8 | `fk_chat_history_user_id` 换成 `fk_chat_history_owner` | `3 failed / 19 passed` | 含逐字 pin 那条（`…default_identifier_is_the_one_the_spec_names` 现同时 pin 三组常量）⇒ 换约束名要过评审 |
| N9 | 去掉 `if count:` 守卫（零孤儿也发 UPDATE） | `2 failed / 22 passed` | 归户两条（幂等 + 顺序） |
| N10 | 归户与补外键**先后对调** | `1 failed / 23 passed` | `…runs_before_the_foreign_keys` ⇒ 这条判据钉的就是 1452 那个开机面 |
| N11 | 归户 `:uid` 写死 `1`（正是这次事故里那个已不存在的旧 id） | `1 failed / 23 passed` | `…sends_dead_rows_back_to_the_default_user`（断言的是 `self.reclaims == [(表, 传进来的 user_id)]`） |
| N12（对照组） | 计数 SQL 去掉冗余的 `IS NOT NULL` | **`24 passed`（绿）** | 语义等价：NULL 在三值逻辑下本就不进 `NOT IN`。留着 `IS NOT NULL` 是为了**读起来就是"孤儿"的定义**，不是为了正确性——这条现在由变异而不是注释说话 |

### live 侧

- live RED（服务未重启，真库还没被迁移碰过）：`2 failed / 20 deselected`——
  `documents.user_id 上没有外键：服务没重启过` 与 `Failed: 删掉了仍持有文档的账号 id=714：外键没起作用，RESTRICT 没生效`。
  两条都在**加完判据、还没落库**的时候红，这就是它们要的证据。
- 起服务一次（pid 21604，`python -m uvicorn main:app --host 127.0.0.1 --port 8000`）让 lifespan 落库。
  日志只有 5 行、**没有 `迁移完成`**——root logger 是 WARNING，`logger.info` 那句本来就不出。
  这条不算证据也不当反证，证据是下面的直查。
- 落库后直查（不是拿判据当证明）：两张表各**恰好一枚**外键（`fk_documents_user_id` / `fk_chat_history_user_id`，
  均 `-> users`）、孤儿 **0**、`user_id` 列上各**只一枚**索引、`chat_history` 归属分布 `[(30, 43)]`、
  `documents` `[(30, 13)]`。
- 收口：`TaskStop` 掉那个 uvicorn，`netstat` 复确认 8000 空着。
- 纪律（写进了 live 判据的注释与 docstring）：共享库上**先 assert 再调用**——
  `ensure_foreign_keys` / `reclaim_orphaned_owners` 在没迁移过的库上会真发 ALTER / UPDATE，
  顺序一反这条 live 判据自己就会改结构。
- 新增 live 判据一条：`test_foreign_key_restricts_deleting_a_user_who_still_owns_rows`
  （探针账号自己造自己删、`default@local` 一次都不出现在 DELETE 里；拦下后还验文档行**仍在**，
  再删掉文档才删得掉账号——反向那一半也钉住，否则"永远删不掉"也算绿）。
  `_drop_probe_account` 的 docstring 记下新现实：漏删探针行现在会让清理当场抛 IntegrityError，**静默变响亮**。
- `tests/test_live_database.py` 现 **22 passed**（含新那条），整文件跑绿。

### 终态门禁实数（台账前复跑，逐条抄汇总行）

- 后端全量 **`323 passed / 2 skipped / 2 deselected / 1 warning`**（40.87s；写本节前的最新一次，另一次 40.97s）
- 离线门 `-m "not live and not migration"` **`301 passed / 26 deselected / 1 warning`**（35.33s）
- 聚焦 `tests/test_migrations.py` + `tests/test_test_doubles.py` **`25 passed`**（3.74s）
- live 文件 `tests/test_live_database.py` **`22 passed`**（3.04s）
- 对账：`315 + 5（FK 单测）+ 2（孤儿单测）= 322`，`322 + 1（live RESTRICT）= 323`；离线 `294 + 7 = 301`，
  被 `not live` 挡掉的从 25 涨到 26（正是新加的那条 live）；既有判据一条没被打断。
- **前端未跑**：本轮 diff 只碰 `backend/` 四枚文件，前端一行未动 ⇒ `npm test` / `npm run build` 不重跑，
  口径同 ①②③，明示不省略。

### 用户可见面

- **43 行旧对话记录回到可见**：它们从"归属指向不存在的账号"改为归 `default@local`。
  只有当某台设备的 localStorage 里还躺着当年那批 `session_id` 时才看得到，否则仍是历史数据。
- **「注销账号」这条路从此被 MySQL 拦下**：仍持有文档的账号删不掉（errno 1451），要删必须两头删
  （今天本仓没有删账号入口，所以这一条是给将来的人的护栏，不是给今天的用户的）。
- 每次开机多两次 `COUNT(*) AS orphans` 与一次 `KEY_COLUMN_USAGE` 查询；孤儿清完后归户那步交白卷，
  `ADD CONSTRAINT` 一条也不发（幂等由单测与 live 两头钉）。

### Ruling

1. **按 (表, 列) 问外键是否存在，不按约束名问** —— `create_all` 建的那枚叫 `documents_ibfk_1`，
   迁移建的那枚叫 `fk_documents_user_id`，是同一个事实的两个名字；按名字查会在**每一个新库**上再叠一枚
   重复外键（InnoDB 对不同名不拦，且安静收下）—— 代价：将来真要"换名"时判据不会帮忙（N8 正是要它红，逼评审）。
2. **不写 `ON DELETE`（= RESTRICT）** —— 文档正文在 MySQL、向量在 Chroma，MySQL 的级联带不走向量；
   写 CASCADE 等于把"行没了、向量还能被召回"变成开机即定的默认行为 —— 代价：删账号必须先手工清两头，
   将来做「注销账号」时要多写一段应用层删除流程。
3. **孤儿归户给默认用户，而不是删行** —— 与 `backfill_*` 同一个前提（改造前只有那一个人在用，
   行里没有任何别的归属线索）；归户是把数据交还唯一的失主，删是替用户做决定 ——
   代价：如果那 43 行其实属于别的真人，现在被并进了默认账号名下（本机不可能：users 只有两行，
   338 是本次改造后新注册的）。
4. **计数 SQL 里冗余的 `IS NOT NULL` 保留** —— N12 已证它不影响结果（NULL 不进 `NOT IN`），
   留着是为了让这一句**读起来就是孤儿的定义** —— 代价：多一个"看起来多余"的条件，靠变异记录而不是注释自证。

### 过程偏离与自纠，如实记

- **预检的 SQL 是对的，孤儿数字就在输出里，我却把结论读反了。** 那次直查打的是
  `… WHERE x.user_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM users u WHERE u.id=x.user_id)`，
  原始输出两行：`documents rows 13 NULL owner 0 ORPHANS 0` 与 `chat_history rows 43 NULL owner 0 ORPHANS 43`。
  我在任务账（Task #97）和当轮的话里写成「13/43 行零 NULL、**零孤儿** ⇒ ALTER 无阻塞」，
  把两张表混成了一句结论。这不是"问法错"（问法本来就是对的），是**读错自己刚打出来的东西**。
  发现时机：FK 半段 GREEN 之后为写交付面重查（`SELECT user_id, COUNT(*) … GROUP BY user_id` 回 `(1, 43)`，
  `users` 只剩 30/338）——那一刻才改口，并停下来请使用者拍板。
  自纠口径：**涉及数据改动的预检，结论要按表逐行抄原始输出，抄完再判断**；一句跨过两张表的结论不许出现。
- **控制者独自执行**（无 implementer/reviewer 代理），**终审是自评** —— 交付时必须明示这一条。
- **两处夹具洞都是判据先骗人**：`FakeConn` 的列名解析（红得没道理）与 `list.count`（绿得没道理）。
  后者方向更坏——实现真破掉时它照样交白卷，属"假绿"，已把理由钉进判据注释。
- **一次多余的变异重跑，且它的命令描述写错了轮次**：N2 首跑（`tail -6`）已经打印出三条失败函数名，
  我又保持同一变异状态重跑一次只换 grep 口径（结果一致：`3 failed / 19 passed`），
  而那次重跑的命令描述被我写成 "Capture N1 mutation failure list"——当时文件状态是 **N2**。
  表里 N1 记 `2 failed`（`added.append` 被删）、N2 记 `3 failed`（无先查），两条都出自各自的真实运行，
  没有互相顶替；但下一轮**同一状态不重跑、不复用上一轮的输出**，命令描述要与轮次号一起写。
- 自己写判据时手滑引用了不存在的 `second_ddl(conn)`：在**跑之前** grep 夹具方法名时抓到，改为 `conn.executed`。
- 一次 `Edit` 因 `old_string` 与当前缩进不符被拒（N10 第一次尝试），未产生半截状态，按当前文件内容重发成功。
- `cd backend` 失败一次（Bash 的 `cd` 状态跨调用保留，当时已在 `backend/` 里）⇒ 之后一律绝对路径。
- 确认"没删掉不该删的行"用的是 `git diff -U0 … | grep '^-'`（只看被删的那几行），**没有**拿 `--stat` 当证据；
  `git diff --stat` 附带的 CRLF warning 是 `core.autocrlf` 的既有口径，不是本轮引入的异常（工作树实测仍纯 LF）。
- **这一节曾被压缩丢掉一次**：上一次会话结束时它只存在于对话里、没落盘（那笔 Edit 因参数名写错被拒）。
  恢复时我手上的备忘把孤儿来源记成"预检问法用了 LEFT JOIN `IS NULL`"——核对转录
  （`C:\Users\31439\.qoder\projects\D-------------\80c2fc91-….jsonl`，本轮区间）后确认**归因是错的**：
  两次查询都带了 `NOT EXISTS` / `NOT IN (SELECT id FROM users)`，孤儿数一直是 43。
  ⇒ 本节只写核对过的版本；教训与记忆里那条"子代理回报先直查再采信"同源：**自己的备忘同样要先直查**。

## 第 ⑤ 条 — 「至多一枚默认」交给引擎：STORED 生成列 + 唯一索引，去重必须赶在建索引之前

**BASE `3af77da` → 代码 `e0ecfe1`（5 files，+523/−10：生产码 `core/migrations.py` `core/database.py`、测试 `tests/test_migrations.py` `tests/test_live_database.py` `tests/test_user_models_db.py`）。**

### 预检（真库 `mydb` 只读 + 本机 scratch 表实测）

清单原文给的路是「要堵得加唯一约束（MySQL 无部分索引，需生成列或应用级锁）」，所以先量两条路在本机 MySQL 8.0.39 上成不成立，再选：

- 唯一索引直接盖 `is_default` **建不出来**（那是全员共用一列，第二个用户立默认就撞）；部分索引 `WHERE is_default` 在 MySQL 上不存在。剩下唯一可行的声明式写法就是生成列。
- 生成列 + 唯一索引这条路**实测成立**，四格都在 scratch 表上量过（不是推理）：① INSERT 第二枚默认 → 1062；② **UPDATE 把非默认那枚提升成默认**也 → 1062（这一格是关键——`set_default_user_model` 才是应用层天天在走的路，只测 INSERT 会整条漏掉）；③ 另一个人立默认**插得进**（guard 里带的是 `user_id`，不是常量）；④ 同一人再加几枚**非默认**照常（唯一索引不理 NULL）。
- **顺序是量出来会炸的，不是猜的**：`ALTER TABLE … ADD COLUMN … STORED` 在**已经带着两枚默认**的数据上**照样成功**（两行都算出同一个 guard，此刻还没有索引管着它），紧接着的 `CREATE UNIQUE INDEX` 才在同一份数据上回 `1062 Duplicate entry`。⇒ 去重必须早于建索引。而 `run_migrations` 挂在 lifespan 且不兜异常（`main.py:59`）⇒ 反了的症状与 ④ 的 1452 同族：**不是"这条迁移没做成"，是整台后端起不来**。
- **看着更"原子"的那条捷径被实测否决**：一条语句 `UPDATE user_models SET is_default = (name = :t) WHERE user_id = :u`。同一份数据跑两个方向——目标那枚 id 排在现任**之后**成功、排在**之前**回 1062。顺序依赖的约束不是约束。现行两步形状（先清别人、再立这个）保留。
- 真库现状逐行抄：`user_models` **1 行、1 枚默认、0 个多默认用户**、无 `default_guard` 列（列清单 `id/user_id/name/is_default`）。⇒ 本条**不动任何用户数据**，因此没有像 ④ 那样打断使用者去拍板；去重那一步在真库上是交白卷的，它的正确性由 scratch 实测 + 离线判据两头供。
- `information_schema.COLUMNS.GENERATION_EXPRESSION` 存的是**小写 + 反引号**那一份（`` (case when `is_default` then `user_id` else NULL end) ``）⇒ 存在性只能问 `<> ''`，逐字比串必然假红；全文那半改由常量与 ORM 声明同源钉。

### RED → GREEN

- 离线 RED（聚焦 `test_migrations.py` + `tests/test_user_models_db.py`）：**`9 failed / 26 passed`**。两类红因：
  `AttributeError: module 'core.migrations' has no attribute 'ensure_single_default_guard'`（连带 `generated_column_exists`、`duplicate_default_count`）
  与形状那两条「`default_guard` 必须是生成列」「唯一索引只盖一列」。
- GREEN 分两段落地：
  ① 迁移侧——`generated_column_exists`（严格口径）+ `add_generated_column` + `duplicate_default_count` + `clear_duplicate_defaults`
  + `add_unique_index` + 入口 `ensure_single_default_guard`（三格返回值都可数）+ `run_migrations` 接线 + summary 加 `single_default_guard`
  → `test_migrations.py` **30 passed**（24→30）。
  ② ORM 侧——`default_guard = Column(Integer, Computed(SINGLE_DEFAULT_GUARD_EXPR, persisted=True), nullable=True)`、
  `Index('uq_user_models_single_default', 'default_guard', unique=True)`，且 `core/database.py:12` **从 `core/migrations.py` 导入那枚表达式**
  （方向是"声明吃迁移的常量"，无环；同源判据由此才有意义）→ `test_user_models_db.py` **5 passed**（3→5）。
- live RED：**`2 failed / 22 deselected`**，两条各咬一面——
  一条红在**前置闸门**（`真库上 default_guard 不是生成列`：闸门放在最前，是为了不把"压根没有约束"误报成"引擎不管"）；
  一条红在 `AssertionError: 重试把默认位抢走了：[('p5-race-anchor', True), ('p5-race', True)]`。
- 落库 + GREEN：真库就位后 live 文件 **24 passed**（22→24）。
- **⑤ 自己会引入的一句谎，顺手堵掉**：`add_user_model` 原先把**所有** `IntegrityError` 都回 False，端点据此回 409「该模型已在你的名单里」。
  守卫键一进来，"名单里根本没这个名字"也会撞键（另一个事务刚立了默认，而这里的 `is_first` 读的是旧快照）
  ⇒ 那句话变成**没人能查下去的假话**，而且用户要的那枚也没进去。现在回滚后再查一次名字分流两件事：
  真在名单里 ⇒ False；不在 ⇒ 补插成**非默认**（NULL 不参与唯一比较，这次不可能再撞守卫）⇒ True。
  双击两次"添加"（两个不同名字）就能撞进这个窗口，所以它必须有自己的判据——见 live 侧的注入钩子。
- 一处**夹具洞**在 GREEN 路上当场补掉：`FakeConn` 认去重语句时写的是 `head.startswith("UPDATE USER_MODELS")`，
  而生产发的是 `` UPDATE `user_models` d JOIN … `` ——带反引号，**永远匹配不上**，这条判据会长期空跑。
  改成 `head.split()[1].strip("`") == "USER_MODELS"`，理由写进夹具注释。

### 变异自证（八轮，全部手工 Edit + `cp` 还原 + sha256 与符号计数双向确认）

终态实测（也是每轮的还原基准）：`core/migrations.py` sha `861e10dde7ef` / 27454 字节（纯 LF 482 行），
`core/database.py` sha `20bc51079d2b` / 39942 字节（纯 CRLF 817 行）。R1-R3/R7-R8 改迁移码，R4-R6 改 ORM 声明与 `add_user_model`。

| 轮 | 变异 | 结果 | 红在哪条 |
|---|---|---|---|
| R1 | 去掉 `GENERATION_EXPRESSION <> ''`（同名**普通列**也算守卫已就位） | `1 failed / 29 passed` | `test_guard_exists_only_if_that_column_is_really_a_generated_one`。这一格不是修辞：宽松口径的后果是**静默的零约束**——那列由应用自己写，不写就整列 NULL，唯一索引正好不管 NULL，它安安静静管着一列空值，比没有索引更糟 |
| R2 | 去重挪到 `CREATE UNIQUE INDEX` **之后** | `1 failed / 29 passed` | `test_duplicate_defaults_are_cleaned_before_the_unique_index_is_built`（钉的就是预检量出的 1062 开机面） |
| R3 | DDL 去掉 `STORED` | `1 failed / 29 passed` | `test_single_default_guard_alters_the_column_before_indexing_it` |
| R4 | ORM 去掉 `persisted=True` | `1 failed / 4 passed`（形状文件单跑） | `test_user_models_guard_column_is_a_stored_generated_one`——新库走 `create_all`，它与迁移那侧不同源就是分叉 |
| R5 | 唯一索引多盖一列（`default_guard, user_id`） | `1 failed / 4 passed` | `test_user_models_guard_index_covers_only_the_generated_column`。多盖一列**照样建得出来**，管成了"(user_id, 默认位) 组合"⇒ 与 ②③ 那两条"盖住哪几列才是判据"同一口径 |
| R6 | 删掉撞键后补插非默认的那半段 | `1 failed / 23 deselected` | `test_add_user_model_retries_as_non_default_when_the_guard_race_wins`——离线三枚 fake 不真建约束，这条路只有真 MySQL + 注入钩子能咬 |
| R7 | 函数留着、`run_migrations` 里**不接线** | `1 failed / 29 passed` | `test_run_migrations_reports_the_guard_and_goes_quiet_on_reboot`（`NameError: name 'guard' is not defined`）。与 ④ 的 N6 不同（那轮咬 4 条）：⑤ 的接线只被**一条** run_migrations 级判据消费，如实记 |
| R8 | `SINGLE_DEFAULT_GUARD_EXPR` 里 `user_id` 换成 `1`（全体共用一个 guard 值） | `1 failed / 34 passed`（聚焦 pair） | `test_default_identifier_is_the_one_the_spec_names`（逐字 pin 第三组常量）。**同轮 ORM 同源那条照常绿**——它比的是"两处是不是同一句话"，改常量则两处一起变，这正是单一出口要的效果，不是判据漏牙 |

### live 侧

- **落库方式**：脚本直调 `ensure_single_default_guard(conn)`（真库 `mydb`，`user_models` 只有 1 行 1 枚默认，`duplicates_cleared: 0`
  ⇒ 无数据改动，反向 SQL 都不需要）。**这不是 lifespan 路径**，所以补了两头的证据：
- 真库落库后**直查**（不是拿判据当证明）：列 = `('default_guard', 'int', 'STORED GENERATED', '(case when \`is_default\` then \`user_id\` else NULL end)')`；
  索引 = `('uq_user_models_single_default', 'default_guard', 0)` **只盖一列**、`NON_UNIQUE=0`；多默认用户 `(0,)`；
  行数与默认数 `(1, Decimal('1'))` 前后一致 ⇒ 去重没误伤。第二遍 `{column_added: False, duplicates_cleared: 0, index_added: False}`。
- **去重那一格在真表上没被执行过**（真库本来就 0 重复），所以另在 **scratch 表**上把"首次建守卫"整条走了一遍并落盘：
  初始 `[(1,1,'a',1),(2,1,'b',1),(3,1,'c',0),(4,2,'d',1)]`（同一人两枚默认）→
  首次 `{'column_added': True, 'duplicates_cleared': 1, 'index_added': True}` →
  去重后 `[(1,1,'a',1),(2,1,'b',0),(3,1,'c',0),(4,2,'d',1)]`：**留的是 `MIN(id)` 那枚、别人（user 2）那枚一行没动** →
  第二遍全白卷 → 再插 `(1,'e',1)` 被 `1062 … uq_user_models_single_default` 拦下 →
  `(5,'f',1)` 与 `(1,'g',0),(1,'h',0)` 照常插进 → `DROP TABLE`，残表 `[]`，全程未碰 `user_models`。
- **真开机一遍**（本轮唯一的端到端证据，也是本台账第一次拿到 lifespan 的 summary 原文）：
  起 `python -m uvicorn main:app --host 127.0.0.1 --port 8000 --log-config <Temp>/p5logconf.json`
  （④ 那轮"日志里没有 `迁移完成`"的根因这次查出来了：root 是 WARNING，而那句挂在 **`kb.migrations`**
  这只 logger 上，`core/migrations.py:22`——按模块名 `core.migrations` 配等级是配不到的）。
  `GET /api/health` 回 200（`document_count 4`、`vector_counts parent 4 / child 10` 与基线一致），日志：
  `INFO kb.migrations: 迁移完成: {'columns_added': [], 'indexes_added': [], 'single_default_guard': {'column_added': False, 'duplicates_cleared': 0, 'index_added': False}, 'orphan_rows_reclaimed': [], 'foreign_keys_added': [], 'default_user_id': 30, 'documents_claimed': 0, 'chat_rows_claimed': 0, 'llm_seeded': False, 'model_seeded': False, 'vectors_stamped': 0}`
  ⇒ 接线在真 lifespan 里跑到了、且第二遍不改任何东西。收口：`TaskStop` 掉那个 uvicorn，`netstat` 复确认 8000 无人 LISTEN。
- **`llm_seeded: False` 这一格别读成 ⑥ 的进展**：`seed_default_llm` 有两条早退（`.env` 缺 key / 账号已有 key），
  两条回的是**同一个值**，日志分不出来。这次开机走的是第二条（`default@local` 早就有 key），⑥ 关心的是第一条 ⇒ ⑥ 的挂账原样保留。
- 新增 live 判据两条的口径要点：
  ① `test_engine_itself_rejects_a_second_default_for_the_same_user`——第一条断言是**前置闸门**（列不是生成列就在这里红，
  而不是把"压根没约束"误报成"引擎不管"）；1062 之外还要**认索引名**（只盯错误号会漏掉"被 `unique(user_id,name)` 拦下"这种张冠李戴）；
  行数用**相对增长** `len(models) == len(before) + 1` 而不是绝对条数（`probe_user` 是 module 级共享账号，写死数字等于把判据绑在执行顺序上）；
  `finally` 里连"那次该失败的 INSERT 万一没失败"留下的行一起删。
  ② `test_add_user_model_retries_as_non_default_when_the_guard_race_wins`——`monkeypatch` 换掉 `db.get_session`，
  `_StaleSnapshot` 按 **SQL 文本**（不是调用次数）只 spoof 「判空那一次」，让 `is_first` 读到旧快照，
  于是撞守卫键变成**确定性可复现**而不是碰运气；并断言 `len(spoofed) == 1`——钩子没命中这条就是空跑。

### 终态门禁实数（台账前复跑，逐条抄汇总行）

- 后端全量 **`333 passed / 2 skipped / 2 deselected / 1 warning`**（46.78s）
- 离线门 `-m "not live and not migration"` **`309 passed / 28 deselected / 1 warning`**（40.52s）
- `-m live` **`24 passed / 2 skipped / 311 deselected / 1 warning`**（26.78s）
- 聚焦 `tests/test_migrations.py` + `tests/test_user_models_db.py` **`35 passed`**（4.47s；逐文件收集数 30 + 5）
- live 文件 `tests/test_live_database.py` **`24 passed`**（3.46s）
- 对账：`323 + 6（迁移）+ 2（形状）+ 2（live）= 333`；离线 `301 + 8 = 309`，被 `not live` 挡掉的 `26 → 28` 正是新增两条 live；
  既有判据一条没被打断（③④ 那两组的计数与口径原样）。
- **前端未跑**：本轮 diff 只碰 `backend/` 五枚文件，前端一行未动 ⇒ `npm test` / `npm run build` 不重跑，
  口径同 ①②③④，明示不省略。

### 用户可见面

- **界面行为不变**：名单、下拉、"设为默认"的可见结果都和改造前一样。变的是**再也不会出现两个默认**——
  之前"并发插入留下两枚默认"是读侧按 id 升序取第一枚来兜的，用户看到的是"我设的默认偶尔不算数"，且没有任何线索指向原因；
  现在第二次写会被引擎拒掉，`set_default_user_model` 那两条语句的窗口里输的一方**要么成功要么 500，不会留下脏数据**。
- **开机多两条查询**：一次 `COUNT(*) AS dupes`、一次 `information_schema.COLUMNS` 的生成列问话；
  零重复时那句 UPDATE 不发，列与索引都在位时两条 DDL 也不发（幂等由离线判据 + 真开机两头钉）。
- **`user_models` 多了一枚没人读的列** `default_guard`：它是约束的载体，不是数据。ORM 里它 `nullable=True`、
  应用侧一次都不写它——写它反而会被 MySQL 拒（生成列不可直接赋值）。这一格在 docstring 里解释了"为什么存在"。

### Ruling

1. **用生成列 + 唯一索引，不用应用级锁（`GET_LOCK` / 串行化事务）** —— 不变量落在引擎上才叫约束：
   锁要求**每一个**写入方都自觉拿同一把，而本表的写入方已有三处（`add_user_model`、`set_default_user_model`、迁移的 `seed_default_llm`），
   将来任何脚本化写入都是第四处 —— 代价：表上多一枚"没人读的列"，读代码的人必须先理解 NULL 不参与唯一比较这件事（已写进 ORM docstring），
   且换 MySQL 版本 / 换存储引擎时 `STORED` 这条路要重跑整个 live 组。
2. **严格口径（"是不是真的生成列"）只用在列那一步，索引那一步仍按名字问 `index_exists`** ——
   两处补救手段不同：列那侧是可加的 `ALTER ADD COLUMN`，跳过才是错的；索引那侧若真出现"同名但是普通索引"，
   正确修法是 `DROP INDEX`，而**启动期迁移不问自取地删东西**是比"约束没建上"更糟的先例 ——
   代价：万一出现同名普通索引，守卫会静默不生效（本机不存在：`uq_` 前缀是本仓起的，`SHOW INDEX` 实测无冲突），此格挂账。
3. **去重留 `MIN(id)` 那枚**，而不是"最近写入的那枚" —— 判据反了的话同一行每次开机都被改写，
   而"谁当默认"要稳定可复现，用户第二次打开设置页看到的才是同一个模型 ——
   代价：极端情况下用户"刚设的默认"在重启后被降回非默认（本机不可能：真库 `duplicates_cleared = 0`，从未有重复可清）。
4. **撞守卫键后补插成非默认，而不是回 409** —— `add_user_model` 回 False 的口径是"名单里已经有了"，
   名单里没有就必须让他那枚进去；把它挡在门外是 ⑤ 自己造出来的谎 ——
   代价：重试里那层嵌套 `except IntegrityError`（同一名字被别的请求抢先加上，这次才是真的"已经有了"）
   只有 3 行、且**没有专属判据**（要确定性地复现它得再 spoof 一层），挂账。
5. **不把 `set_default_user_model` 合成一条 `SET is_default = (name = :t)`** —— 实测顺序依赖（目标 id 在现任之前回 1062），
   "看着原子"的写法把不变量换成了一个更难复现的 bug —— 代价：并发输掉的一方仍以 1213（死锁）或 1062 冒成 500，
   但**不变量仍然成立**（引擎在位），这条 500 面没有判据覆盖，挂账。

### 过程偏离与自纠，如实记

- **控制者独自执行**（无 implementer/reviewer 代理），**终审是自评** —— 交付时必须明示这一条。
- **验证脚本自己写错一步，被引擎纠正**：scratch 表第 5 步想证"别人的默认插得进"，却复用了 `user 2`——
  它在初始数据里**已经有一枚默认**，于是被守卫以 `1062` 拦下。错在脚本不在代码；换成全新的人（`user 5`）后通过。
  教训：验证"边界外的人没事"要挑**没有默认的那个人**，别复用已有数据的 id。
  第一次运行的失败只打到 stderr（脚本 stdout 是重定向到文件的），所以 `p5scratch.txt` 里那一格是**缺的**而不是错的——
  这类"输出文件少一行"要当信号读，不能当"没测"糊过去。
- **上一轮"日志没有 `迁移完成`"的根因这次才查对**：①②③④ 记的是"root logger 是 WARNING，`logger.info` 本来就不出"，
  那半句没错，但按 `core.migrations` 配 INFO 也拿不到——真名是 `kb.migrations`（`core/migrations.py:22` 用的是 `logging.getLogger("kb.migrations")`）。
  第一次开机白起了一次（`p5boot.log` 6 行、没有 summary）。⇒ 记这一条是为了下次**先 grep logger 的注册名**再配日志。
- **一次 Edit 打错了目标文件**（想改 `p5scratch.py` 却指到输出 `p5scratch.txt`），因 `old_string` 无命中被拒，未产生任何状态。
- **一次 Edit 误删了既有判据的 docstring**：给 `tests/test_live_database.py` 插入第二条 live 判据时，
  `old_string` 跨过 `test_empty_profile_update_touches_nothing` 的 docstring 把它带走了；工具输出里当场看到，下一笔 Edit 补回。
  确认方式与 ④ 相同：只看 `git diff` 里被删的那几行（`grep '^-'`），不拿 `--stat` 当证据。
- **量行尾的一次脚本列写错**：`b.count(bytes(10))` 打的是十个 NUL 字节，`total_nl` 那列恒为 0、无意义；
  真正要看的是 `crlf` 与 `lf_only` 两列（`b.count(b'\r\n')` 与其差），实测五枚文件形状与基线一致
  （`database.py` 817 纯 CRLF / `migrations.py` 482 纯 LF / `test_migrations.py` 747 纯 LF / `test_live_database.py` 839 纯 CRLF / `test_user_models_db.py` 87 纯 LF）。
- 一次 `Edit` 因 `old_string` 与当前 docstring 用词不符被拒（记成「补上的」、原文是「建了的」），重读原文后重发成功，未产生半截状态。
- **两处"没牙"如实记下，不粉饰成已闭合**：① `ensure_single_default_guard` 必须早于 `seed_default_llm` 那句注释**没有判据**
  （反向不会开机炸，只是 seed 那次插入不受引擎把关）；② 上面 Ruling 2/4/5 各自点名的三格（同名普通索引、重试嵌套分支、`set_default` 输家的 500）都没有判据。
- 变异八轮**逐轮只红目标那一条**，且每轮还原后重新打 sha + `grep -c` 被替换的那一句回到原次数；
  与 ④ 的 N6 相比 R7 只咬 1 条（④ 咬 4 条），这个差别记在上表里而不是略过。
- 本轮**起了两次服务**（第一次为拿不到 summary 而白起），两次都由 `TaskStop` 收口，`netstat` 复确认 8000 无人 LISTEN；
  全程只有一个 pytest 进程、没有并发跑 `-m migration`（那组是 Chroma 搬家校验，与本条无关，未跑）。

## 第 ⑥ 条 — 「缺 key 半态」第一次可分辨：`seed_default_llm` 的三条出口各挂一块牌子

挂账原文：「迁移的『缺 key 半态』分支从未在真 `.env` 上跑过 ⇒ 闭合需要一个能临时改 `.env` 的受控窗口。」
**这条路被使用者否决**，选项是「不动 `.env`，改判据」——把 `.env` 改坏再改回，中间任何一次崩溃都会留下一台
起不来的后端（`run_migrations` 挂在 lifespan 且不兜异常），风险大于收益。于是这条变成两件事：
**先让两条早退可分辨**，再让「缺 key 半态」在**离线门**上有一次真判据。全程 `.env` 一行未读未写。

### 预检（读的是形状与消费者，不是凭证）

- 开工前的形状：`core/migrations.py:365-369` 两条早退回**同一个字典**
  `{"llm_written": False, "model_added": False}`——`env 缺键` 与 `账号已有 key` 在返回值与日志里都不分开。
- 跨任务冲击扫描（`grep -rn "llm_seeded|model_seeded|seed_default_llm|llm_written|model_added"`，全 `backend/`）：
  消费者**只有两处**——`core/migrations.py` 自己（`run_migrations` 的 seed 调用与 summary 两格）与
  `tests/test_migrations.py` 的 `:621 :650 :660 :667 :678` 五处。**live 组 0 处**读 summary ⇒ 冲击全在离线门内，
  live 不需要为这条加判据。
- summary 那一枚字典**没有任何判据断"整枚相等"**（逐条读 `first[...]` / `second[...]` 都是按键取格）
  ⇒ 新增一格 `seed_reason` 不会打断既有判据；会被打断的只有那四处"整枚字典相等"的 seed 断言。
- ⑤ 那轮真开机（`p5boot2.log`）拿到的 `llm_seeded: False`，按当时的返回值**只能推断**走的哪条——
  这条要闭合的第一半步就是把那句推断变成日志里读得出的一句事实。

### RED → GREEN

- 离线 RED（聚焦 `tests/test_migrations.py`，收集 33 条）：**`8 failed / 25 passed`**，与预期逐条对上——
  三处新增（`KeyError: 'reason'` / `KeyError: 'seed_reason'`）+ 四处既有整字典相等失配 + stamps 那格新增的一行。
  既有 ⑤ ④ ③ 的 25 条**原样绿**，说明改写只落在 seed 这一族。
- GREEN 三段（`core/migrations.py`，纯 LF，改后 489 行 / 28148 字节 / sha `d4d4db07be46`）：
  ① 两条早退各带 `"reason": "env_incomplete"` / `"already_configured"`；
  ② 写成功那格带 `"reason": "seeded"`（三格都要报名，不许留白让读日志的人猜）；
  ③ `run_migrations` 的 summary 接线 `"seed_reason": seed["reason"]`。
  两格布尔的**名字与口径一个字未动**；docstring 补一段说明"为什么有这一格"与"只准取常量"。
  → `test_migrations.py` **33 passed**（30→33）。
- 新增替身 `IncompleteEnvConfig(MigrationConfig)`（`test_migrations.py` 模块顶层）：只抹 `OPENAI_API_KEY`，
  `base_url` 与模型名都留着——**半套配置才是本机最容易出现的形态**，而 seed 要防的正是"缺一枚还照抄"。
  命名不带 `Fake` 前缀，所以 ③ 的唯一性判据不管它（如实记：那枚判据的射程是 `Fake*`，不是所有替身）。
- **中途自己判掉一条没牙的断言**：初版 `test_boot_log_...` 里写的是 `assert lines[1] != lines[2]`，
  而这两遍用的是**不同的 conn**（`columns_added` 本来就一空一满），那句不等号**必然成立**，
  跟分辨力无关。换成 summary 级断言：两遍 no-seed 的 `llm_seeded` / `model_seeded` 逐格相同、
  只有 `seed_reason` 分开它们。改完才跑 GREEN。

### 变异自证（七轮，全部手工 Edit + `cp` 还原 + sha256 双向确认）

基准：`core/migrations.py` sha `d4d4db07be46`（纯 LF 489 行 / 28148 字节）。每轮还原后重新打 sha，七轮全部回到基准；
七轮只改生产码，`tests/test_migrations.py` 全程 sha `df7568fb4adb` 不变。聚焦跑 `tests/test_migrations.py`（33 条）。

| 轮 | 变异 | 结果 | 红在哪条 / 为什么是这一组 |
|---|---|---|---|
| M1 | 第二条早退的 reason 也写成 `env_incomplete`（回到"两条同名"） | `3 failed / 30 passed` | `test_seed_never_overwrites_a_key_the_user_set_himself`、`test_seed_reports_which_early_exit_it_took`、`test_boot_log_tells_the_two_no_seed_faces_apart`——⑥ 的新名字被打回同一个词，三条一起红 |
| M2 | 「账号已有 key」的守卫永不为真（`if row and …` → `if not row and …`） | `3 failed / 30 passed` | 同 M1 那三条。**M1 与 M2 命中同一组**：这三条对"已有 key 那一格"的分辨力是重合的，不是三个独立面，如实记 |
| M3 | 函数改了、`run_migrations` 里**不接线** `seed_reason` | `3 failed / 30 passed` | 换成 run_migrations 级那三条（stamps / 半态 / 开机日志），`KeyError: 'seed_reason'`——与 ⑤ 的 R7 同一口径：接线被几条判据消费就红几条 |
| M4 | `not (api_key and base_url)` → `not (api_key or base_url)`（半套配置照抄） | `3 failed / 30 passed` | 新增的三条红。**既有那条 `test_seed_does_nothing_when_env_has_no_key` 照常绿**（两枚全缺时 `or` 也早退）⇒ "只缺一枚"这一半牙齿是新增的 `no_url` 那格给的，不是老判据带的 |
| M5 | 写成功那格误标成 `already_configured` | `4 failed / 29 passed` | 两处整字典相等 + stamps 新增行 + 开机日志的 `s_seeded["seed_reason"] == "seeded"` |
| M6 | `reason` 拼进库里已有的 key（`f"already_configured:{row[0][0]}"`） | `3 failed / 30 passed` | 两条按值断的 + **`test_boot_log` 红在 `"sk-from-env" not in caplog.text` 这一条**（用 `-k` 单跑确认到断言行，不是推断）⇒ "新增一格就多一次泄漏机会"那句注释有判据守着 |
| M7 | **对照组**：只把早退字典里三格的书写顺序换成 `reason` 打头 | `33 passed` 全绿 | 判据钉的是**值**不是形状/顺序；这轮预期就是绿，绿了才算把"判据会不会误伤写法"这一面量出来 |

### 用户可见面

- **界面一行没变**：seed 只在开机跑，写库条件、返回给前端的字段都原样。变的是**排错的那一句话**：
  以后开机日志里 `seed_reason` 会直说三种情况之一，"这台机器的 `.env` 没填 key"与
  "默认账号早就有自己的 key"不再共用一句 `llm_seeded: False`。
- **真机上的那一遍**（本轮实测，Temp 里的 log config，仓库代码零改动）：
  `… 'default_user_id': 30, 'documents_claimed': 0, 'chat_rows_claimed': 0, 'llm_seeded': False,
  'model_seeded': False, 'seed_reason': 'already_configured', 'vectors_stamped': 0`
  —— 这句日志**能证明的**只有一件事：真库上 `users` 里默认账号（`id=30`）的 `api_key` 非空，
  所以走的是"不许覆盖"那条。它**为什么**非空是推断（以前某一次开机 seed 成功过，或用户在设置里改过），
  本轮没有去读那一列的值；⑤ 那轮只能靠读源码推断的分辨力，现在由日志自己说出来了。
- **`llm_seeded` 的旧读者**（如果有脚本 grep 这句日志）不受影响：两格布尔的位置与值都没动，只是多一枚键。

### Ruling

1. **改判据不动 `.env`**（使用者选的这条，我复核后同意并落地）——真 `.env` 上跑"缺 key 半态"要先把三键改坏，
   而 lifespan 不兜异常，中途崩一次就留下一台起不来的后端；这一格的**证据换成注入假 config 的离线判据 ——
   代价：本机始终没有"真配置缺键 + 真 MySQL"的那一遍，理论上留一条只属于真环境的分叉（`Config` 读 `.env` 是
   `os.getenv` 裸读，见 `config/config.py:30-31`，那两键没有 `validate_required`，所以"空串"与"缺键"在真机上
   都归到同一个 `not (api_key and base_url)`，分叉面很小）。此格**如实记为边界**，不写成已闭合。
2. **`reason` 进返回值与 summary，而不是"多打一行日志"** —— 本仓纪律是判据不能吃日志：幂等、走了哪一条、
   有没有把凭证印出来，三件都要在返回值上断 —— 代价：`seed_default_llm` 的返回字典多一格，
   凡断"整枚相等"的判据都要跟着改写（本轮 4 处，已逐处注明是有意改写）。
3. **三条出口全部报名**，不是只给两条早退报名 —— 只给早退报名会让"种上了"那一格在日志里是**空格**，
   读的人仍要反推；`seeded` 这一格同时把"写成功"与 `model_seeded: False` 的语义分开（后者只说结果）——
   代价：**"写了 key 但没加模型"的两支因（`LLM_MODEL` 为空 / 名单已有同名）没有各自报名**，挂账。
4. **`reason` 只准取常量**，M6 是这一条的自证 —— summary 整枚进日志，`api_key` 一旦能被拼进任何一格，
   就等于在开机日志里印凭证（本仓已有 `UserOut` 单一构造点守这个面，见 [[project-api-key-leak-surfaces]]）——
   代价：以后想让它带上下文（例如带缺的是哪一枚键）必须同时补一条"不许带值"的判据。

### 过程偏离与自纠，如实记

- **控制者独自执行**（无 implementer / reviewer 代理），**终审是自评** —— 交付时必须明示。
- **一次 Edit 把下一条判据的 `def` 行当锚点吃掉了**：给 `test_migrations.py` 插入三条新判据时，
  `old_string` 用了 `def test_run_migrations_self_heals_a_crash_between_claim_and_stamp():` 这一行，
  替换文本里忘了把它写回去 ⇒ 那条判据的 docstring 当场悬空。工具输出里看到，下一笔 Edit 补回 `def` 行，
  随后用 `--collect-only` 复确认收集数（33）与 `git diff` 里 `^-` 的行。**这正是 [[project-crlf-mutation-hazards]]
  里记的"锚点唯一但形状错"那一族**：拿函数头当锚点就得把函数头写回 new_string。
- **一次自己判自己没牙**（见 RED→GREEN 末段）：`lines[1] != lines[2]` 换成 summary 级断言。
  这条是在**跑 GREEN 之前**改的，不是事后补的，所以那条初版从未变绿过。
- **`--log-config` 的 logger 名沿用 ⑤ 查到的 `kb`**（不是 `core.migrations`），本轮一次开机就拿到 summary，
  没有再白起一次。后台进程由 `Stop-Process` 收口（先按 `CommandLine` 核对 PID 23908 再杀），
  复确认 `Get-NetTCPConnection -LocalPort 8000 -State Listen` 计数 0。
  后台任务壳子回报的退码是 127（进程被强制停止后的包装层返回值），与启动是否成功无关——
  证据是 `p6boot.log` 里有 `Application startup complete` 与那句 summary，如实记下免得下轮把 127 当"起不来"。
- 本轮**只起一份服务、只有一个 pytest 进程**、全程未跑 `-m migration`；服务停掉之后才跑 live 组（Chroma 单实例锁）。
- **前端未碰**：diff 只落在 `backend/` 两枚文件 ⇒ `npm test` / `npm run build` 不重跑，口径同 ①②③④⑤，明示不省略。

## 第 ⑦ 条 — 422 的兜底剥掉 `input`：明文 api_key 上界面的唯一通道改成白名单

挂账原文：「422 的 `detail[*].input` 回显，前端只靠 `client.js:32` 那条 fallback 挡着 ⇒ 要闭合就在 fallback 里剥掉
`input`（代价：削弱「原文是唯一的排错线索」，属产品取舍）」。**使用者选的正是这条路**（「前端 fallback 剥掉 input」），
所以那句代价不是我的推断，是批准时写下的话——它逐字进了代码注释（「代价如实记：排错时拿不到"后端收到了什么"，
只能拿"哪一格、哪种错"」）。

### 预检（读的是通道与形状，不是凭证）

- 旧的这一行（改前 `client.js:32`）：`detail.map((item) => item?.msg ?? JSON.stringify(item))`。
  有 msg 时只抄 msg（这一半本来就安全），**缺 msg 时把整枚 item 拼进界面文案**。
  pydantic 的校验项形状是 `{type, loc, msg, input, ctx?}`，其中 **`input` 是原样回显的请求值**。
- 全项目唯一"请求体里带明文凭证"的端点是 `PUT /api/auth/me/llm`（`api_key` 就在 body 里）
  ⇒ 这一格一旦上屏，key 就出现在界面上。
- 后端那一侧挡不住：`main.py:79` 只挂领域异常、`:83` 兜 500，**没有 `RequestValidationError` 处理器**
  ⇒ 422 响应体里 `input` 永远在。界面上看不看得到，全凭前端这一道闸。
- 闸为什么"唯一"：三条网络出口（`request` / `postStream` / 上传的 XHR `documents.js:52`）**都复用 `httpError`**，
  而 `httpError` 是 message 的唯一构造点 ⇒ 只要把规则收在 `detailFromText` 这一族，三条出口一起生效。
  这也是"必须给 `httpError` 本身钉一条判据"的理由，否则"唯一构造点"只是注释里的一句话。
- 绕过白名单的另一条路是**值写进 msg**（`ValueError(f'{value} 不是 URL')` 那种写法）。实测本仓两处 validator
  （`schemas/auth.py:127`、`:136`）只把**长度**写进文案（「当前 {len(value)} 位」），不写值 ⇒ 今天这条路不成立，
  见 Ruling 4，挂账不预判。

### RED → GREEN

- RED（判据先行，聚焦 `frontend/tests/client.test.js`，收集 30 条）：**`2 failed | 28 passed (30)`**。
  红的两条正是新增的「兜底走白名单，input 与 ctx 一律不上屏」与「`httpError` 直接构造的错误也不带 input」。
  另两条新增判据（「有 msg 时只抄 msg」「非对象项交出那格本身」）**当场即绿**——如实记：它们的身份是口径钉，
  不是新功能的实现证据（前者防下一个人在这里"顺手补全上下文"，后者把 `null` 那半的坏法钉住）。
- GREEN（`frontend/src/api/client.js`，工作树**纯 CRLF** 197/197，改后 9921 字节 / sha `e007f25130bf`；
  改前 177 行 / git blob 8212 字节）：新增模块级纯函数 `validationItemText(item)`（`:25`）——
  ① 非对象（含 `null`）→ `JSON.stringify(item)`，与改前完全一致；
  ② `msg` 只认**非空字符串**，空串与缺键一样走兜底；
  ③ 兜底是**白名单**：新建一枚空对象，只按 `type`、`loc` 的顺序挑键再 stringify。
  `detailFromText` 的数组分支改为 `detail.map(validationItemText)`（`:52`）。
- **挑键顺序刻意为 `type`、`loc`**（与 FastAPI 自己输出的顺序一致）：阶段二既有那条
  「422 数组里缺 msg 的项降级为 JSON 文本」（`toBe('请求参数不合法：{"type":"too_short","loc":["body","x"]}')`）
  **期望值一字未改仍绿** ⇒ 这道闸的改动面只有"input 那一格不见了"，没有连带改写任何既有判据。

### 门禁实数（只抄当轮汇总行）

| 门 | 本轮 | 起点 / 口径 |
|---|---|---|
| `frontend/tests/client.test.js` | GREEN **30 passed (30)** | 改前该文件 26 条 ⇒ **+4 条** |
| 前端全量 `npm test` | **158 passed / Test Files 14 passed** | 本轮起点实测 154/14 ⇒ +4 全落在 client.test.js |
| 前端 `npm run build` | exit 0，产物 `index-CWg0-YgN.js` | 原 `index-CH0iZltg.js`；css `index-CUrklGmJ.css` **未变** |
| 后端全量 `pytest` | **336 passed / 2 skipped / 2 deselected / 1 warning** | 与 ⑥ 收口时逐字相同（本轮只跑这一门做冲击确认） |
| `backend/tests/test_frontend_constants.py` | **5 passed** | 它的扫描面是 `frontend/src`，本轮动了 client.js ⇒ 必须单跑 |
| 后端离线 / `-m live` | **本轮未重跑** | diff 只在 `frontend/` 两枚文件，口径同 ①③，明示不是遗漏 |

### 变异自证（九轮，全部手工 Edit + `cp` 还原 + sha256 双向确认）

基准：`client.js` sha `e007f25130bf`（纯 CRLF 197 行 / 9921 字节）。九轮只改生产码，
`frontend/tests/client.test.js` 全程 sha `061258ccd126` 不变；每轮还原后重新打 sha，九轮全部回到基准。
聚焦跑 `frontend/tests/client.test.js`（30 条）。

| 轮 | 变异 | 结果 | 红在哪条 / 为什么是这一组 |
|---|---|---|---|
| M1 | 回退成改前的整枚 stringify（`item?.msg ?? JSON.stringify(item)`） | `2 failed` | ⑦ 那条 + `httpError` 那条——两枚新判据对同一条通道的牙齿 |
| M2 | 白名单多带 `input`（`['type','loc','input']`） | `2 failed` | 同 M1 ⇒ M1 不是"靠缺键侥幸红"，键集才是判据 |
| M3 | 白名单多带 `ctx` | **`1 failed`** | 只红 ⑦ 那条：`httpError` 的夹具里**故意没有 ctx** ⇒ `input` 与 `ctx` 两面**分开计量**，不是重合的牙齿 |
| M4 | 白名单去掉 `loc`，只剩 `type` | `2 failed` | ⑦ 那条 + **阶段二既有那条降级判据** ⇒ 线索（哪一格）不是本轮可牺牲项 |
| M5 | `msg` 口径放宽成"是字符串就用"（空串也算） | `1 failed` | 红在空串那一格：界面实际交出「请求参数不合法：」一句没有内容的中文 |
| M6 | 非对象守卫收窄成只挡 `null` | `1 failed` | 字符串项落进白名单变成 `{}`，那格的原文消失 |
| M7 | 非对象守卫去掉 `null` 那半 | `1 failed` | `TypeError: Cannot read properties of null` ——正是那枚断言要拦的坏法（可读的 422 变成"界面自己坏了"） |
| M8 | 键序换成 `loc` 打头（内容一字未动） | `2 failed` | 两处整枚相等的判据把**键序**也钉住了 ⇒ 口径不是随手写法（与 ⑥ 的 M7 相反方向：那轮换的是值无关的形状，这轮换的是期望值本身的一部分） |
| M9 | **对照组**：把白名单键集提成模块常量，行为不变 | `30 passed` 全绿 | 判据钉**输出文本**，不钉实现写法；这轮绿了才证明 M8 的红不是过拟合 |

### 用户可见面

- **有 msg 的正常 422 一字未变**：仍是「请求参数不合法：<英文原文照抄>」（M-j 那条口径原样保留）。
- **变的是兜底那一格**：以前缺 msg 时界面会出现整串 JSON，其中 `input` 就是后端收到的原值（`PUT /api/auth/me/llm`
  那一枚里是明文 key）；现在只出现 `{"type":…,"loc":[…]}`——**哪一格、犯了哪种错**仍读得出来，
  **后端收到了什么值**读不出来了。这就是批准时写下的那句代价。
- 非对象项（后端手写的 detail，如 `['api_key 不能是空白']`）与 `[null]` 的行为与改前**完全一致**（M6/M7 各守一半）。
- 上传那条（XHR）同受这道闸保护：它复用的就是 `httpError`（`documents.js:52`），所以本轮没有第二种文案的风险。

### Ruling

1. **闸放前端，不在后端挂 `RequestValidationError` 处理器**（使用者选的这条）——界面是"上屏"的必经面，
   改前端一处就覆盖三条出口；改后端响应体则会把 devtools、代理日志之外的既有 API 消费者一起改掉形状 ——
   代价：**422 响应体本身仍然带 `input`**，devtools、反向代理访问日志、直接打 API 的脚本都还能看到明文 key。
   这一面**如实记为边界**，不写成本条已闭合。
2. **白名单（挑 `type`、`loc`）而不是黑名单（删 `input`、`ctx`）** —— 黑名单要能枚举 pydantic 未来新增的字段，
   而 `ctx` 允许校验器塞任意值（本轮夹具就是把 secret 同时塞进 `input` 与 `ctx.error`）——
   代价：以后 msg 之外真正有用的字段（例如 `url` 帮助链接）也一并进不了界面，要放就得同时加判据。
3. **`msg` 只认非空字符串** —— 空串走兜底，否则界面只剩一句中文前缀（M5 是这一条的自证）；
   代价：非字符串的 msg（那不是 pydantic 的形状）会被整格丢掉，**宁可丢、不上屏**。
4. **"值写进 msg"那条绕路本条不处理** —— 实测两处 validator 只写长度（`schemas/auth.py:127`、`:136`），
   今天不成立；将来谁写成 `ValueError(f'{value} 不是 URL')` 就绕过白名单，而那条判据今天无从下笔 ——
   **挂账**：真要堵的是"文案里不许出现请求原值"，那是 validator 的纪律，不是 `detailFromText` 的。
5. **判据钉输出文本、不钉实现形状**（M9 绿 / M8 红一起构成这一条）—— 代价：以后重构 `validationItemText`
   的内部形状是自由的，但**改键序就是改判据**，得当成口径变更走。

### 过程偏离与自纠，如实记

- **控制者独自执行**（无实施代理、无评审代理），**终审是自评** —— 交付时必须明示。
- **判据加宽过一遍，变异整批重跑**：初版四条判据写完、跑过四轮之后，又补了三处加宽
  （`[null]` 那枚断言、把 `ctx` 载荷换成与 `secret` **不同**的标记、空串 msg 那一格）。
  加宽前跑过的四轮**已在新判据集上重跑**，上表条数全部是重跑后的观测输出；提交信息里也写了这一句，
  免得下一轮读到混合口径的数。其中"ctx 载荷故意不等于 secret"这一处是本轮真得到的口径——
  它让 M3 只红 1 条而不是 2 条，两面分开计量才有意义。
- **一次 Bash 的 `cd` 残留**：先前 `cd backend` 跨调用保留，导致量 `src/api/client.js` 时 `FileNotFoundError`；
  换绝对路径重测。这是 [[ref-sdd-scripts-need-bash]] 里那句「cd 跨调用保留」的又一次命中。
- **`git add` 台账的退码 1**（`.superpowers/` 被 gitignore，文件却已 staged）：与 ⑥ 同一现象，
  按 [[ref-sdd-scripts-need-bash]] 记录的用法处理——add 与 commit 分成两次调用。
- 行尾如实记：`frontend/src/api/client.js` 工作树**纯 CRLF**（197/197）、`frontend/tests/client.test.js` **纯 LF**（0/352），
  本轮两枚都保持原样未转换，Edit 自动跟随；测量用字节计数，未用 `grep -c $'\r$'`（[[project-crlf-mutation-hazards]]）。
- 本轮**未起服务**、**未跑 `-m migration`**；变异只在 `client.js` 一枚文件上，九轮还原全部 sha 回到基准。
- **后端一行未动**：diff 只落在 `frontend/` 两枚文件 ⇒ 后端只跑全量那一门做冲击确认（336/2/2/1 与 ⑥ 逐字相同），
  离线门与 live 组本轮**未重跑**，口径同 ①③，明示而非省略。

## 清单进度

| 条 | 事项 | 状态 |
|---|---|---|
| ① | `LlmIn` 两格长度界量在 strip 之前 | **已闭合**（`de8499d`） |
| ② | `AVATARS` 两份 / `PASSWORD_MIN` 三份没有单一出口 | **已闭合**（`ee117fd`：七枚镜像收进 `frontend/src/constants.js`，`backend/tests/test_frontend_constants.py` 五条判据两头钉，另消灭三处模板里写死的数字） |
| ③ | 两枚同名 `FakeConfig`（`tests/fakes.py:1`、`tests/test_migrations.py:182`） | **已闭合**（`bcc0296` + 补正 `d89bb29`：预检证明迁移判据吃四键 ⇒ 不合并，迁移那枚改名 `MigrationConfig`；新增 `tests/test_test_doubles.py` 钉"模块顶层 `Fake*` 类名唯一"，六轮变异自证） |
| ④ | `ChatHistory.user_id` / `documents.user_id` 的 FK 只在新建库存在 | **已闭合**（`423a26a`：`ensure_foreign_keys` 按 **(表, 列)** 问 `KEY_COLUMN_USAGE`、不写 `ON DELETE`（RESTRICT）、排在 `ensure_indexes` 之后；预检在真库量到 `chat_history` 43 行孤儿（旧默认账号 id=1 已不存在），经使用者拍板新增 `reclaim_orphaned_owners` **先归户再 ALTER**；单测 +7、live +1（RESTRICT 行为面）+1 格（外键与孤儿的第二遍白卷），十二轮变异自证，真库落库后实测各一枚 FK / 0 孤儿 / 各一枚索引） |
| ⑤ | `user_models` 至多一枚默认靠应用层两步，并发可留两枚 | **已闭合**（`e0ecfe1`：MySQL 无部分索引 ⇒ 守卫落在 `default_guard` 这枚 **STORED 生成列** + 只盖它一列的**唯一索引**上（NULL 不参与唯一比较 ⇒ 非默认随便多、默认每人至多一枚）；迁移四步各查各的：**数重复 → 降掉除 `MIN(id)` 之外 → 补列 → 建索引**，去重早于建索引是 scratch 表实测钉的（`ALTER` 在两枚默认上照样成功、`CREATE UNIQUE INDEX` 才回 1062，而 lifespan 不兜异常 ⇒ 反了就是后端起不来）；存在性用严格口径问 `GENERATION_EXPRESSION <> ''`（同名普通列的后果是静默的零约束）；顺带堵掉 ⑤ 自己会引入的谎——撞守卫键不再回 409「已在你的名单里」，改为补插成非默认。单测 +8（迁移 6、形状 2）、live +2（引擎本身拒第二枚默认 / 注入钩子把撞键窗口变成确定性可复现），八轮变异逐轮一条红；真库落库后直查列与索引形状、多默认人数 0、行数与默认数未变，另在 scratch 表上把"首次建守卫 + 去重 1 行"整条实测过，真开机一遍拿到 `kb.migrations` 的 summary 原文） |
| ⑥ | 迁移的"缺 key 半态"分支从未在真 `.env` 上跑过 | **已闭合**（`6a327ca`，按使用者裁定**不动 `.env`、改判据**：`seed_default_llm` 的三条出口各带一枚常量 `reason`（`env_incomplete` / `already_configured` / `seeded`），`run_migrations` 的 summary 新增 `seed_reason` 把它带进开机日志——原先两条早退回同一个字典，`llm_seeded: False` 分不清是"`.env` 缺键"还是"默认账号已有 key"；「缺 key 半态」由注入的 `IncompleteEnvConfig` 在**离线门**上证两件事（那遍一行没写 + 报得出走了哪条）。判据 +3（`test_migrations.py` 30→33，含 caplog 钉"两遍 no-seed 布尔逐格相同、只有 reason 分开"与"日志里不许出现 key"），另**有意改写**四处整字典相等断言。七轮变异 M1–M6 各红 3–4 条、M7 是对照组（只换字典键序 ⇒ 33 全绿，判据钉值不钉形状）；真开机一遍拿到 `'seed_reason': 'already_configured'`（⑤ 那轮只能推断的这一格现在是日志里读出的事实）。**边界如实记**：真 `.env` 上"缺键"那半本机仍未跑过，证据换成离线判据；"写了 key 但没加模型"的两支因没有各自报名 |
| ⑦ | 422 的 `detail[*].input` 回显，只靠 `client.js:32` 那条 fallback 挡着 | **已闭合**（`74d11b8`，按使用者裁定的这条路「前端 fallback 剥掉 input」：新增模块级 `validationItemText`，数组 detail 的每一项只准 **msg（且只认非空字符串）、type、loc** 上屏，兜底改成**白名单挑键**而不是整枚 stringify ⇒ `input`（FastAPI 原样回显的请求值，`PUT /api/auth/me/llm` 那一枚里就是明文 api_key）与 `ctx`（pydantic 允许塞任意值）都到不了界面。键序按 FastAPI 自己的 `type`、`loc` ⇒ 阶段二那条"缺 msg 降级为 JSON 文本"判据**期望值一字未改仍绿**；三条网络出口共用 `httpError` 这一构造点，故 fetch / SSE / 上传 XHR 一起受保护。判据 +4（`client.test.js` 26→30，含 `httpError` 直接构造那条、`null` 项那条、ctx 载荷故意与 secret 不同那条），九轮变异 M1–M8 逐轮只红目标面（M3 只红 1 条证明 input/ctx 两面分开计量）、M9 对照组全绿。前端全量 **158 passed/14 files**、build 产物换 `index-CWg0-YgN.js`；后端一行未动（全量 336/2/2/1 逐字不变，跨端那 5 条单跑绿）。**边界如实记**：只管"上界面"，422 响应体里 `input` 依然在（devtools / 代理日志 / 直连 API 仍可见），要连那一面一起堵得在后端挂 `RequestValidationError` 处理器，不在本条范围；"值写进 msg"的绕路今天不成立（两处 validator 实测只写长度），挂账 |
| ⑧ | 视口/交互探针是一次性脚本，没有常驻回归测试 | 待开工（`puppeteer-core` 本轮已 `npm prune` 清掉，做它要重装） |
