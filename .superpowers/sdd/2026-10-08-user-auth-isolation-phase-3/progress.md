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

## 第 ⑧ 条 — 视口/交互探针常驻化：一套数据无关的浏览器几何判据，装成 devDependency

提交：`e4f572f`（6 枚文件 +813/-1：`package-lock.json` 341、`package.json` 4、`tests-browser/_browser-probe.js` 150、
`tests-browser/layout.test.js` 300、`tests/chunk-selection.test.js` 3、`vitest.browser.config.js` 16）。
**生产码 0 改动**（build 产物 hash 逐字未变，见门禁表）。

### 预检

- **起点**：阶段二 Task 12 的那次视口验证是 `--no-save` 装的 puppeteer-core + 一次性脚本，验完即删 ⇒
  交付文档第八节第 8 条写下的事实是「下次改布局要重新造轮子」。
- **使用者裁定**：「**装成 devDependency + 常驻判据**」⇒ 本轮 `npm install -D puppeteer-core`（实测 `^25.12.0`），
  依赖进 `package.json` 与 lockfile，下一个人 `npm ci` 就能跑到。
- **目录口径**：`vitest.config.js` 的 include 是 `tests/**/*.test.js`，所以新目录刻意叫 **`tests-browser/`**
  —— 单位门永远不会顺手拉起一个浏览器；配套独立的 `vitest.browser.config.js`
  （`environment: 'node'`、`fileParallelism: false`〔两个 Edge 进程抢同一个 `userDataDir` 会直接起不来〕、
  `testTimeout 60s`、`hookTimeout 180s`），入口 `npm run test:browser`。
- **前置条件失败要响亮报错、不许 skip**：`requireStack()` 分得出两种坏法——「dev server 连不上」与
  「dev 在、后端不在」，后者靠 **Vite 代理把不可达上游翻成 502 + HTML 体** 这一本机已记录的怪癖识别，
  不是靠网络层异常。
- **数据无关前提**（本条最要紧的一条约束）：判据不吃文档条数、不吃模型名单长度、不发问答请求 ⇒
  不烧配额、不写业务数据。登录走页内 `POST /api/auth/login` + `localStorage.setItem('auth_token', …)` + reload，
  收口走 API 登出（实测 **204**）—— 不点 `.rail-signout`，因为窄屏下那个点击会被浮层遮罩吃掉（探针怪癖 6）。
- **口令来源**：`KB_LOGIN_IDENTIFIER/PASSWORD` 环境变量优先，否则剥引号读 `backend/.env` 的
  `DEFAULT_USER_*`（阶段二那次把"解析漏了引号"误读成"配置缺键"，本轮按教训处理）；
  **值永不外印**——不进断言消息、不进日志、不进台账。写死口令会把默认口令第二次推进 git 历史
  （`0b22116` 之前进去过一次，那条"轮换口令"仍是使用者自己的待办）。

### 首跑（本条的 RED 角色）

首跑 **`1 failed | 11 passed (12)`**，红的不是产品而是**判据自己写错**：
`TypeError: Failed to execute 'getComputedStyle' on 'Window': parameter 1 is not of type 'Element'`。
核对组件源码——`.picker-results` 是 `v-else-if="chunks.length"`，busy（「搜索中…」）与零命中两档都不渲染这个节点，
于是"量它退成一列没有意义"这件事**在这台机器上必然发生**（探针账号本来就没有可选块）。
修法是**两条口径都留证据**：`waitForFunction` 等请求落地，真实列表在就量真实列表；不在就往 `.picker-modal` 里挂一枚
**同类名临时节点**量样式规则、量完立即 `remove()`，并把 `source` 一起回报（实测两支都交出 `309px` / 1 track；
临时节点那一支用"搜一个必定零命中的关键词"真跑过一遍，不是只写在代码里）。
配套把**类名本身**钉进 jsdom：`frontend/tests/chunk-selection.test.js` 加一句
`expect(wrapper.find('.picker-results').exists()).toBe(true)`（条数不变，仍 158）——改名就是两边同时量不到东西。

### 判据加宽（12 → 17 → 18 → 21，已跑过的变异轮在新判据集上全部重跑）

- 「整页不滚」从只钉宽屏扩到**三档共判**（实测 docScroll/bodyScroll = 900/900、800/800、900/900）。
- 新增「`.chat-messages` 高度下界」（实测 594 / 469 / 569，下界取半屏）——
  它是旧那次「窄屏浮层塌成 2px」的常驻防线。
- 新增「**内容长过可用高度时，撑开的是消息区而不是页面**」三档 —— 由变异 M5 逼出来的：
  DOM 合成 3000px 占位块，**第一版没给 `flex: '0 0 auto'`，被 `.chat-messages` 自己的
  `display:flex; flex-direction:column` 收缩回去**（实测 `scrollHeight 469 == clientHeight 469`），
  "内容溢出"这个前提根本没发生；靠实测数字发现，不是推理。补上后实测
  pageOverflow 0、`scrollHeight` 3239/3242/3223、`clampedScrollTop` 2645/2773/2654。
- 新增「≤768 控件行的**计算样式**」一条 —— 由 M1/M2 逼出来：那两行 CSS 各自删掉都全绿
  （名单里只有一枚短名字 ⇒ 几何判据没有牙齿）。

### 门禁实数（只抄当轮汇总行）

| 门 | 本轮 | 口径 |
|---|---|---|
| `npm run test:browser` | **21 passed (21) / Test Files 1 passed** | 首跑 12 条（1 红），加宽到 21；需两份服务在跑 |
| 前端全量 `npm test` | **158 passed / Test Files 14 passed** | 与 ⑦ 收口时逐字相同（`chunk-selection.test.js` 只多一句断言，条数不变） |
| 前端 `npm run build` | exit 0，`index-CWg0-YgN.js` 101.39 kB / `index-CUrklGmJ.css` 13.49 kB | **两枚 hash 与 ⑦ 相同 ⇒ 生产码零改动**，这是本条最硬的一道自查 |
| 后端全量 / 离线 / `-m live` | **本轮未重跑** | diff 只在 `frontend/`，口径同 ①③⑦；另：Chroma 单实例锁那轮由 uvicorn 持有，这是不并行跑 pytest 的第二个理由 |
| 库内行数（跑前 == 跑后） | `auth_tokens 1 / users 2 / documents 13 / parent_chunks 4 / chat_history 43` | 只读查询；登出实测 204，判据不写业务数据 |

### 变异自证（十四格，全部手工 Edit + `cp` 还原 + sha256 双向确认）

基准：`frontend/src/styles/layout.css` sha `03705068a7e9…`（纯 CRLF 422/422、18468 字节）。
**十四格还原后 sha 全部回到基准**，每轮动手前后各用一次 `git diff --stat` 确认改动面只有那一处意图。
分母逐轮如实记：判据集在轮中加宽过，同一处破坏在不同分母下跑过两次，**不是笔误**。

| 格 | 变异 | 分母 | 结果 |
|---|---|---|---|
| M1a | 删 ≤768 `.chat-controls{flex-wrap:wrap}` | 17 | **全绿** ⇒ 几何判据没牙齿 |
| M2a | 删 ≤768 `.model-select{flex:1;min-width:0;max-width:none}` | 17 | **全绿**（同上）|
| — | 补「控件行计算样式」判据后的基准 | 18 | `18 passed` |
| M1b | 同 M1a | 18 | `1 failed`（正是新那条）|
| M2b | 同 M2a | 18 | `1 failed`（FAIL 名逐字对上新那条）|
| M3a | `.picker-modal` 宽度 `min(92vw,560px)` → `120vw` | 18 | **全绿** ⇒ 宽度上界那一格**无判据**，见挂账① |
| M3b | 高度不受视口约束（`height:120vh` + `max-height:none`，一枚意图两行） | 18 | **`4 failed`（余 14 绿）**：宽屏那条命中断言原文（`top=-90 / bottom=990` 超出视口），另 3 条是级联——关不掉的浮层吃掉后续点击。复跑一次同果 |
| M4 | 删 ≤768 `.picker-results{grid-template-columns:minmax(0,1fr)}` | 18 | `1 failed`，正是目标那条 |
| M5 | 删宽屏 `.app-shell{grid-template-rows:minmax(0,1fr)}` | 18 | **全绿** ⇒ 逼出「高内容」那一组（+3 → 21）|
| M5′ | 同一处破坏，加宽后重跑 | 21 | **全绿** —— 因为 `.chat-main{min-height:0}` 还在 |
| M5b | 只删 `.chat-main{min-height:0}` | 21 | **全绿**（反向同理）⇒ **两行互为兜底、缺一不红** |
| M5c | 整块删（两行一起） | 21 | **`1 failed`（余 20 绿）**：`页面被顶开 2629px`（1280 那档）——历史 L-1 那个坏法现在有常驻防线 |
| M6 | `.settings-add-model .settings-input` 的 `min-width:0` → `400px` | 21 | **`2 failed`（余 19 绿）**（目标那条 `expected 440 to be 311` 加级联一条）|
| M7 | 删 ≤768 `.app-shell{height:100dvh}` | 21 | **全绿**：桌面 headless 上 `100dvh` 与继承来的 100% 是同一个数（800），见挂账② |
| M8 | **对照组**：`.panel-hint` 13px → 12px | 21 | **全绿** ⇒ 这套判据不是"怎么动都红" |

（M3b 的复跑与 M1/M2 的"两轮"合起来是十五次运行；表格按意图列十四格。）

### 用户可见面

- **产品行为一字未变**：build 产物 hash 与 ⑦ 逐字相同，`layout.css` 净改动为零。
- 使用者得到的是一条命令（`npm run test:browser`）与 **21 条常驻视口判据**：三档几何（1280×900 / 375×800 / 500×900）
  ——整页不滚、消息区是有界滚动容器、高内容撑开的是消息区、发送按钮在视口内且不溢出、
  两层浮层既不与发送键重叠也整块在视口内、≤768 的控件行与候选池口径、全程新增 console/page error 为 0。
- 副作用面：`npm ci` 多装 puppeteer-core 一族依赖（使用者明示批准进 devDependency）。

### Ruling

1. **常驻判据只钉数据无关的几何不变式**（不依赖文档条数、名单长度，不发问答请求）——
   代价：M1/M2/M5/M6 这类"内容撑破"必须靠 DOM 合成或计算样式才量得出，三处已如实写进判据与注释；
   真机才有的条件（地址栏收放）本机造不出，只能挂账。
2. **单独一套 config + 单独一个目录，不进 `npm test`** —— 单位门必须任何机器（没起服务、没 Edge）都能跑；
   代价：这一套不会被随手跑到，红项要靠人记得跑 `test:browser`（**仓库没有 CI，所以这不是新增问题**）。
3. **前置条件失败响亮报错，不 skip** —— skip 会被下一个人读成"布局验过了"；
   代价：没起服务时这条命令是红的，必须靠文档说明"先起两份服务"。
4. **puppeteer-core 装成 devDependency**（不再 `--no-save`）—— 使用者选的这条路，常驻判据要能被下一个人跑到就得进 lockfile；
   代价：依赖面变大，且 `package-lock.json` 多了 341 行 diff。
5. **组件在空态不渲染目标节点时，判据挂计算样式 + 临时同类名节点**，并把类名另钉一道结构判据 ——
   代价：这两条量的是**样式规则**而不是"用户看得见的内容"，所以配套要求回报走的是哪一支口径。
6. **控件行的牙齿来自计算样式，几何判据留作结果面（两者并存）** ——
   代价：改 CSS 写法（例如 `flex-wrap: wrap` 换成 `flex-flow: row wrap`）会红在计算样式那条，
   得判"等价重构"还是"口径变更"，不能顺手改绿。

### 挂账（本条 knowingly 没堵的三面）

1. `.picker-modal` 的**宽度上界 560px 没有判据**（M3a 全绿）：它是 backdrop 这个 flex 容器的唯一孩子，
   `flex-shrink` 把它压回 100vw，而它与发送按钮纵向本就不相邻 ⇒ 在桌面 headless 上写不出一个既真实又有牙齿的断言。
2. ≤768 的 `height:100dvh` 与继承来的 `100%` 在桌面 headless 上是同一个数（M7 全绿）：
   `dvh` 的意义只在真机地址栏收放时出现，本机没有那个条件。
3. `.settings-model-row{flex-wrap:wrap}` 没钉：它的牙齿取决于名单里的名字长度，是**数据相关**判据，
   与本条第 1 条裁定相冲。真要堵得先把"长名字"变成可控夹具。

### 过程偏离与自纠，如实记

- **控制者独自执行**（无实施代理、无评审代理），**终审是自评** —— 交付时必须明示。
- **判据集在轮中两次加宽（12 → 17 → 18 → 21），已跑过的变异轮在新判据集上全部重跑**：
  M1/M2 各有两轮、M5 有三轮（18 分母一次、21 分母两次），上表逐格标了分母。
- **首跑那条红是判据自身错**（`v-else-if` 节点在 busy/空态不渲染），产品零改动 ——
  按「跑红先分产品缺陷 / 判据写错」的既有纪律处理，没有为了变绿去改判据的口径。
- **一次性取数脚本 `tests-browser/_evidence.mjs` 跑完即删**（本台账里的实数来自它，共 4 次运行）；
  它**没有进提交**，所以"常驻"的部分只有判据与 helper。
- **本轮起的两份服务已按 `CommandLine` 核对后停掉**：uvicorn :8000（PID 6892，
  `D:\python\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000`）与 vite :5173（PID 6904）
  连同其 `npm run dev` 父链（27072 cmd → 27696 node）；停完复量 8000/5173 两个端口**都不再监听**。
- 行尾如实记（本轮直测）：新增三枚 `vitest.browser.config.js` / `tests-browser/_browser-probe.js` /
  `tests-browser/layout.test.js` 均**纯 LF**（0/16、0/150、0/300 行，696 / 7085 / 14776 字节），
  `tests/chunk-selection.test.js` 纯 LF（0/255，12019 字节）；`package.json` **纯 CRLF**（24/24，549 字节）、
  `package-lock.json` 纯 CRLF（2443/2443，85215 字节）—— npm 写盘的行尾由 npm 决定，本轮未做转换；
  变异面 `layout.css` 纯 CRLF（422/422，18468 字节）。测量用字节计数，未用 `grep -c $'\r$'`
  （[[project-crlf-mutation-hazards]]）。
- **`git add` 台账的退码 1**（`.superpowers/` 被 gitignore，文件却已 staged）：与 ⑥⑦ 同一现象，
  add 与 commit 分成两次调用（[[ref-sdd-scripts-need-bash]]）。
- **一次 grep 截断把 vitest 汇总行吃掉了**：`head -8` 那种截断法不可靠，改成一轮把输出写进
  `/tmp/kb-m*.log` 再无截断地 grep；有一轮因此重跑过一次。
- **台账正文的数字来自转录回读 + 当场直查双证**：本轮上下文被压缩过，变异表先按会话转录（jsonl）恢复，
  再用可当场复核的量重新确认（commit stat 逐文件行数、`layout.css` sha/行尾/字节、build hash、`git diff --quiet`）——
  只凭回忆的数字一律不写（[[feedback-subagent-report-verify]] 同一条纪律，这次对象是我自己的早期记录）。
- 本轮**未跑 `-m migration`**、未起第二份 uvicorn、未跑后端门（理由见表）；
  `backend/` 一行未动。

## ② 的补账 — 问答契约的三格界进镜像集，前端两枚本地常量收进单一出口

- BASE：`1180f81`（第 ⑧ 条的台账收口）。实现提交 **`e1f4d45`**
  （4 files / **+76 −8**：`backend/tests/test_frontend_constants.py` +67 −3、
  `frontend/src/constants.js` +5 −2、`frontend/src/composables/useChunkSelection.js` +1 −2、
  `frontend/tests/useChunkSelection.test.js` +3 −1）。
- ② 收口时这两格只写进了项目记忆，**台账正文没有这一条**（② 那一节记到"七枚镜像收口"为止），
  所以本节所有实数来自本轮的临时证据文件（`kb-118-rounds*.txt` / `kb-118-gates-*.txt` / `kb-118-verify*.txt`）
  与会话转录回读（jsonl 第 33103 / 33478 两条 tool_result 是原始出处）+ 当场直查，只凭回忆的数字一律不写（[[feedback-subagent-report-verify]]）。

### 预检（全部当场直查，量的是 `e1f4d45^` 那一版）

- **两枚本地常量的位置**：`useChunkSelection.js:6` `export const MAX_SELECTED_CHUNKS = 50`、
  `:7` `const MAX_ID_CHARS = 100 // 对齐 ParentChunk.parent_id 的 String(100)`
  —— 那句注释把**契约界**与**存储宽度**当成同一件事，正是 ② 要区分开的两种事实。
- **改名/移动的冲击面只有一处**：全 `frontend/src` + `frontend/tests` 扫这两个名字，除声明处自身的使用
  （第 19、20、69、70 行）外，唯一外部消费者是 `useChunkSelection.test.js:10` 那枚 import。
- **`chat.py:15-16` 的两枚界写在两行上**：元素界在 `Annotated[str, Field(min_length=1, max_length=100)]` 里，
  列表界在外层 `Field(default_factory=list, max_length=50)`。② 那套按行匹配的
  `_py_field_maxes`（`^\s*{field}: str.*max_length=(\d+)`）既匹配不上 `list[...]` 那行、更看不见续行 ⇒
  **必须补一条按括号深度切整条声明的切片器**（`_py_statement` + `_py_two_bounds`）。
- **`MODEL_NAME_MAX` 虽已在镜像集里，但只钉了 `schemas/auth.py` 那一头**：同一条 chat 请求里的
  `model_name: str | None = Field(..., max_length=100)` 无人核对 ⇒ 后端只改 chat 那一格时判据不红。

### RED → GREEN

- **RED**（只加判据与两条早退守卫，前端一行未动）：实跑 **`2 failed, 4 passed in 0.45s`**，两条红理由不同：
  1. 声明集那条红在 `:172`（集合比对：两枚名字还在 `useChunkSelection.js` 里，`constants.js` 没有）；
  2. 新增那条红在 `:207` → `_js_number` 的早退守卫 `constants.js 里抓不到 \`export const MAX_ID_CHARS = 数字\``。
  `_py_two_bounds` 先过了（能走到第 207 行）⇒ 红在缺镜像，不在缺解析。
- **GREEN**：两枚界进 `frontend/src/constants.js`（注释分别写"= schemas/chat.py 里 parent_ids 的元素界 /
  同一条声明里的列表界"），`useChunkSelection.js` 删两枚本地常量、改从 `../constants.js` import，
  测试的 import 一起挪走（原地留一句"上限那枚数字归 constants.js，这里只从那里取"）。聚焦 **`6 passed`**。
- **用户可见面：无行为变化**。两枚数字一个都没改（100/50 原值搬家），文案「最多只能选择 50 个文档块」
  由插值生成 ⇒ 逐字不变；jsdom 158 条与 build 产物只反映"少了一处声明、多了一处 import"。

### 门禁实数（变异全部还原之后重跑）

| 门 | 结果 |
|---|---|
| 焦点 `pytest tests/test_frontend_constants.py` | **`6 passed`**（② 的 5 条 + 本轮 1 条） |
| 后端全量（含 `-m live`） | **`337 passed, 2 skipped, 2 deselected, 1 warning`**（2 skip 要本机 uvicorn；warning 是 `core/database.py` 的 `declarative_base()` MovedIn20Warning，先前就有） |
| 后端离线门 | **`313 passed, 28 deselected, 1 warning`** |
| 前端 jsdom | **`158 passed / 14 files`**（逐字未变） |
| 前端 build | 退出 0 ⇒ **`index-CKhscz7G.js` 101.39 kB**（**换 hash**：`index-CWg0-YgN.js` → 新；本轮生产码真改了，与 ⑦⑧ 的"hash 未变"不同）+ `index-CUrklGmJ.css` 13.49 kB **未变** |
| 浏览器门（⑧ 那套 21 条） | **未跑**：要同时起 uvicorn + vite 两份服务，本轮不碰布局与 CSS（`layout.css` 一行未动）；口径同 ①③⑦ |
| `-m migration` / 真库 | **未跑、未碰**：本轮零迁移、零 DB 触达 |

### 变异自证（八轮，逐轮条数；全部手工 Edit + `cp` 还原 + sha256 与 `git diff --quiet` 双向确认）

| 轮 | 变异 | 结果 | 红在哪条 / 结论 |
|---|---|---|---|
| M1 | `chat.py` 元素界 `100` → `80` | `1 failed, 5 passed` | `:207 assert 100 == 80`（带 `where 100 = _js_number('MAX_ID_CHARS')`）。**首跑只抓到汇总行**（grep 口径太窄），还原后另起一轮重跑才拿到理由行 ⇒ 表里这行是重跑那次 |
| M2 | 列表界 `50` → `60` | `1 failed, 5 passed` | `:208 assert 50 == 60` ⇒ 续行里那枚界真被抓到了（老行匹配口径会漏） |
| M3 | `model_name` 界 `100` → `90` | `1 failed, 5 passed` | `:209 assert {100} == {90}` ⇒ chat 那一头补上，`MODEL_NAME_MAX` 现在两头都被核对 |
| M4 | 镜像侧漂移：`constants.js` 的 `MAX_ID_CHARS` → `101` | `1 failed, 5 passed` | `:207 assert 101 == 100` ⇒ **改镜像不改后端也红**（② 那句"两头钉"在这一格仍成立） |
| M5 | 删掉标注里那枚元素界 | `1 failed, 5 passed` | 红在**形状守卫** `:157`：「`parent_ids` 该是标注里一枚界 + Field 一枚界，实抓 `[]` / `['50']`」⇒ 分半计数生效，不靠值相等 |
| M6 | 两枚界对调（元素 `50` / 列表 `100`） | `1 failed, 5 passed` | `:207 assert 100 == 50` ⇒ 归属按**位置**（以深度 0 的 ` = Field(` 分半）；若写成多重集，这一轮会**全绿** —— 那才是这条判据真正的牙齿所在 |
| M7 | 只改注释（对照组） | `6 passed` | 全绿 ⇒ 判据不咬注释，改说明文字不会被打红 |
| M8 | 接线面：`constants.js` 的 `MAX_SELECTED_CHUNKS` → `51` | jsdom **`2 failed, 156 passed`**、`Test Files 1 failed / 13 passed (14)` | 红在「第 51 块被拒…」与「脏 localStorage 读回即丢…」两条 ⇒ `constants.js` 那枚**真是**被 composable 用的那一枚，不是摆设。这一轮只跑 jsdom 全量（焦点 pytest 同口径的红已由 M4 证） |

- 还原校验（直测）：`schemas/chat.py` 2055 B / `3de94d59e501` / **44 CR + 44 LF**（纯 CRLF）/ `git diff --quiet` == HEAD；
  `constants.js` 1435 B / `368e2bea23af`；`useChunkSelection.js` 3021 B / `68a2d110cd84`；
  `useChunkSelection.test.js` 6600 B / `79501d7fd102`；`test_frontend_constants.py` 13099 B / `fac145744c36`；
  `ChunkPickerModal.vue` 4658 B / `e2294deef5e2`（只被拿来试过锚点，**未进提交**）。

### Ruling（这一轮定下的口径，附代价）

1. **两枚界按位置归属，不按多重集**：以深度 0 处的 ` = Field(` 分半，每半必须**恰好一枚** `max_length`。
   代价：声明一旦换写法（元素界挪进外层、或改 `conlist`），判据先红在形状守卫上，得人来判
   "等价重构"还是"口径变更"，不许顺手改绿（与 ⑧ 第 6 条同一类账）。M5/M6 就是这条牙齿被实测过的两轮。
2. **`ParentChunk.parent_id = Column(String(100))` 刻意不并进来**：那是**存储宽度**不是契约界，
   合法的改法是加宽列而契约留 100 ⇒ 钉成相等会把一次正常迁移判红。理由写进了那条判据的 docstring（不只留在台账里）。
3. **`session_id` 的 `max_length=100` 也刻意不并进来**：前端没有对应输入框（它来自 `GET /me`，用户不经手），
   没有可镜像的面 ⇒ 镜像集的准入条件是"前端真有一处要用这个数字"，不是"后端有 max_length 就算"。
4. **沿用旧名 `MAX_ID_CHARS` / `MAX_SELECTED_CHUNKS`，不强行改成 auth 那几枚的 `X_MAX` 后缀**：
   代价是镜像集内部命名不齐；换来的是 diff 只碰四文件、消费者一处跟着挪，不制造"改名顺带扫全仓"的噪声
   （[[feedback-incremental-reversible]]：先小路径打通，不做本轮范围外的整理）。
5. **composable 里不留 re-export**：留着就是两处出口，正是 ② 要消灭的形态；测试改直接从 `constants.js` 取。

### 挂账与边界（knowingly 没堵的三面）

1. `frontend/src/api/documents.js:10` 的 `limit = 50`（候选池**每页条数**）与 `:15` 的 `if (limit !== 50)`
   **没并进镜像集**：它与 `parent_ids` 的列表界是**两个不同事实**（查询分页 vs 请求负载上界），
   数值相同纯属巧合，钉成相等会把其中一侧的正常改动判红。后端那一头有没有对应的命名权威值，本轮未查 ⇒ 要补得先做预检。
2. `layout.css` 注释里两处写死的数字（`:330`「昵称上限 50 字」、`:373`「模型名上界 100 字」）**不进门禁**：
   ② 的形状判据量的是**模板属性**（`maxlength="50"` 那类真会生效的副本），注释漂移不改变行为。
   代价：注释可与契约漂移，属"文档陈旧"一类，不属"镜像漂移"一类。
3. `_py_statement` 的两条早退守卫（"抓不到 `{field}:` 开头的声明"、"声明括号没闭合"）**没有各自的变异轮**：
   它们服务的是字段改名/整体换写法那一类风险，本轮只实测了 M5（分半计数）与 M6（位置归属）。

### 过程偏离与自纠，如实记

- **控制者独自执行**（无实施代理、无评审代理），**终审是自评** ⇒ 交付时明示。
- **压缩摘要把变异轮数记成「十轮（7 红 / 2 对照 / 1 jsdom）」，实测只有 8 轮（6 红 / 1 对照 / 1 jsdom）**：
  `kb-118-rounds.txt` 全文只有 R7/R1/R2/R3/R4/R5/R8 七个标签，转录里 grep `R6|R9` 无匹配 ⇒ 不编数，按 8 轮记。
- **日志标签与本表不是一套**（`R7-swapped-bounds` = 本表 M6、`R1` = M1）：多轮交错编辑后标签失去单调性，
  本表按"变异内容"重排。教训同 [[project-crlf-mutation-hazards]]：一轮没落标签就进下一轮，事后只能靠 grep 复原。
- **`grep -c $'\r$'` 这一轮反向假报**：对纯 CRLF 的 `chat.py` 报 `No matches found`（记忆里那条记的是"对纯 LF 假报全命中"）。
  本轮只用 `tr -cd '\r' | wc -c` 数字节（44/44），一次都不信 grep。
  **收口后补了一次机制直查**（受控样本 `printf 'a\r\nb\r\nc\n'` = 2 行 CRLF，`grep (GNU grep) 3.0`）：
  `grep -c $'\r$'` 与 `grep -c "\r$"` 都回 **0**，对 `chat.py` 也回 0 ⇒ **这层 grep 按文本模式读文件，CR 在它眼里不存在**，
  报 0 不是"没有 CR"而是"看不见 CR"；另一头 `grep -c "$" schemas/auth.py` 实测 **187**（= `wc -l`），
  正是 ② 那轮"187/187 全命中"的来源（`$'\r'` 被引号处理吃掉后只剩 `$`）。两种方向都错 ⇒ 结论升级成
  "**grep 不是量行尾的仪器**"，只认字节计数（已同步进 [[project-crlf-mutation-hazards]]）。
- **一次 Edit 误吞了相邻判据的 `def` 行**（新测试插在 `test_every_avatar_choice_has_a_label` 的函数头上，
  头像标签那条被并进了新测试）：当场发现、当场拆回；之后收集到 6 条、两条都在（聚焦 `6 passed`，全量 337 亦含二者）。
  与 ② 那轮的"锚点唯一但形状错"同族，这次错在**锚点选了下一函数的头**。
- **`Glob` 在中文路径下对 `frontend/src/components/*.vue` 返空**：改用 `ls` 直查（只影响取文件名，不影响任何数字）。

## 追加特性：注销账号（硬删，MySQL 与 Chroma 两头一起抹）— 三条闭口 ①②③

清单八条收口之后使用者追加的需求，不在 ①–⑧ 的编号里，所以单开一节。
语义经使用者拍板为**硬删、两头一起抹、不可恢复**（选项原文「认了，按这个设计开始写代码」），
执行按「一条一闭一提交」推进，三条各一枚提交：`b12c2c2` → `594458a` → `35e9498`。

### 预检（读的是数据面，不是记忆）

- 真库 FK 现状（① 那轮直查，结论进 `b12c2c2` 提交信息）：**四张表带指向 `users` 的 RESTRICT 外键**
  （阶段三 ④ 补的那一批），两张块表又挡着 `documents` ⇒ 删用户的顺序只有真库能证，
  错一步就是 MySQL 1451；**fake 没有第二张表、FK 不生效**，任何顺序在离线门都"过"。
  这决定了 ① 的判据必须住 live 组，不能拿 TestClient 凑。
- Chroma 侧：metadata 里的 `user_id` 存的是 **`str(user_id)`**，`delete(where=...)` 的标量相等
  **不做隐式转换** ⇒ 传裸 int 的表征是"静默扫了个空"而不是报错。这一格由 ② 的离线判据钉住（V1）。
- 共享库基线（① 那轮跑完复核）：`documents 13 / chat_history 43 / parent_chunks 4 / child_chunks 10 / users 2`，
  零探针残留；⑥ 那轮记录过的 `auth_tokens` 面未变。

### RED → GREEN（三条闭口的顺序就是依赖顺序）

1. **① `database.delete_user_cascade`**（live 判据先红：方法不存在）：一个事务里按
   `auth_tokens → user_models → chat_history → documents → flush → users` 删，documents 走
   **逐行 `session.delete`** 让 ORM `cascade="all, delete-orphan"` 带走两张块表；交出各表行数，
   删不到行报全 0 安静返回。判据一条里六格断言（先数探针名下 2/2/2/1/2/2 证明 fixture 造齐，
   再要返回值、六表归零、`users` 行消失、`default@local` 名下前后逐键相等、同刀重放第二次全 0）。
   测试侧两个助手：`_probe_rows`（块表没有 `user_id` 列，只能经 documents join）、
   `_wipe_probe_account`（**故意不调生产方法**：判据红在生产方法存在之前，漏下的行就是共享库里的永久残留）。
2. **② `POST /api/auth/deactivate`**（204，无正文）：三道门按「令牌 → 口令 → 默认账号」排序，
   `verify_password` 不过回 401「原密码不正确」（`PASSWORD_WRONG` 与改密码共用，同 `LOGIN_FAILED` 的待遇），
   `user.identifier == DEFAULT_IDENTIFIER` 回 409「默认账号不能注销」。
   **口令门排在默认账号门之前**：口令错时该说"你证明不了是你"，回"这个账号删不掉"等于替对方确认口令是对的。
   两头删按「行先提交、向量后清扫」；`VectorStore.delete_by_user_id` 内部 try/except + 记日志、永不外抛
   ⇒ 清扫失败不把 204 报成 500（行没了就是没了，残留向量不可达，是占盘的垃圾不是泄露）。
   `schemas/auth.DeactivateIn` 的 `old_password` 界 `1~64` 与 `PasswordIn.old_password` 逐字相同，
   空串那格必须在算 PBKDF2 之前拦住。默认账号不放行的理由：`ensure_default_user` 下次开机按 identifier
   重铸一枚**新 id**，演示数据全在它名下，删它的表象是"应用自己重置了"。
3. **③ 前端危险区**：设置弹窗第五节，`dangerReady = 原密码非空 && 确认词 === DEACTIVATE_CONFIRM`，
   按钮同一处还吃 `busy !== ''`。成功后 `emit('deactivated')` ⇒ App 把已有的 `handleSessionLost` 当回调使，
   **不新写第三套清理**。verb 用 POST 不用 DELETE（这一枪要带请求体）。

### 门禁实数（全部在变异还原之后重跑，只抄当轮汇总行）

| 门 | 命令 | 本轮实数 | 上一记档基线 |
|---|---|---|---|
| 后端全量 | `python -m pytest -q` | **345 passed / 2 skipped / 2 deselected**（68.21s） | 337/2/2（② 补账） ⇒ **+8**，逐闭可核对：① 给 live +1、② 给离线 +7、③ 后端 0 改动 |
| 后端离线 | `-m "not live and not migration"` | **320 passed / 29 deselected**（45.36s） | 313/28 ⇒ +7 条、deselect +1 是 ① 那条 live 判据 |
| 后端 live | `pytest -q tests/test_live_database.py` | **25 passed**（3.55s） | 24 ⇒ +1（① 那条） |
| 前端 jsdom | `npx vitest run` | **162 passed / 14 files** | 158 ⇒ **+4**（api-auth +1、SettingsModal +2、App 接线 +1） |
| 前端构建 | `npm run build` | exit 0，产物换 **`index-CrrLaEBX.js`**（102.85 kB）+ **`index-C4mVDwWj.css`**（13.73 kB） | `index-CKhscz7G.js` / `index-CUrklGmJ.css` |
| 浏览器门 | `npm run test:browser`（两份服务自起自停） | **21 passed / 1 file**，三次实跑：变异前绿 → L1 红 2 → 还原后绿 | 21（⑧ 收口值，**未增减条数**） |

那 2 个 skip 是 `-m live` 的流式判据（本轮全量跑在"没服务"那一档）；服务只在浏览器门那一段起着，
按 CommandLine 核对后停干净（`netstat` 复核两端口空），**没有为了凑流式数字而重跑 live 组**。
零写库复核：`/api/health` 跑门前后逐格相同（`document_count 4 / parent 4 / child 10`）。

### 变异自证（19 轮，全部手工 Edit + `cp` 还原 + sha256 与 `git diff` 双向确认）

① 两轮（基线 sha `cc522a78399530cc…`，还原后 diff 回到 +38/−0）：
M1 documents 那段换成 `query(...).delete(synchronize_session=False)` → **红 1 条**，1451 `child_chunks_ibfk_1`
（绕开 unit-of-work 就不触发 cascade）；M2 `users` 那一删提到最前 → **红 1 条**，1451 `auth_tokens_ibfk_1`。

② 九轮（末轮复跑焦点 `67 passed / 2 deselected`，与变异前同数）：
V1 `where` 传裸 int → 1 failed；V2 只扫父集合 → 2 failed；V3 拆掉 try/except → 1 failed（RuntimeError 外抛）；
E1 两头先后调换 → 1 failed（`['vectors','rows']`）；E2 删口令门 → 2 failed（含门序那条）；
E3 删默认账号门 → 1 failed（`assert 204 == 409`）；E4 删那一行向量清扫 → 2 failed；
E5 204 改 200 → 2 failed；S1 `min_length` 改 0 → 1 failed（`assert 401 == 422`）。

③ 前端七轮（焦点集 `21 passed / 2 files`；末轮还原后全量 `162 passed`）：
F1 `dangerReady` 去掉确认词那半 → 1 failed | 21 passed；F2 精确相等改前缀宽松比 → 1 failed | 21 passed；
F3 删 `emit('deactivated')` → **2 failed** | 20 passed（组件与 App 接线同时红）；
F4 只删 App 侧监听 → 1 failed | 21 passed（只红接线那条，证明 F3 的两条红各有归属）；
F5 成功后不清明文 → 1 failed | 21 passed（`expected 'hunter2-pass' to be ''`）；
F6 `setKindError` 删 danger 分支 → 1 failed | 9 passed（SettingsModal 单文件）；
F7 封装字段名翻错成 camelCase → **2 failed** | 17 passed（封装与 App 真实链路两层都红）。

③ 补一轮浏览器侧（既有容器不变式对新节有没有牙）：
**L1** `.settings-danger` 加 `min-width: 420px` → **2 failed | 19 passed**，目标那条红在
`expected 422 to be 311`（`.settings-body` 的 `scrollWidth` vs `clientWidth`）。第二失败是**级联**，
不是独立事实：断言抛出后那句 `await closeModal(page)` 没执行，弹窗一直开着，下一档候选池那条量错了东西。
还原后 sha `0d665109498f…` 与基线逐字一致、`git diff --quiet` == HEAD、重跑 `21 passed`。

### 用户可见面

设置弹窗底部多一节「注销账号」：一条上边框把它从纵向流里切出来（上面四节是"改了还能用"，这一节是
"删了就回不去"），红色标题走 `--fail-fg`，提示要求手打「确认注销」四个字，两格都过才亮按钮。
点成功后整屏落回登录页，界面不闪不刷，屏上不留上一个账号的任何一行；**没有** 原生 `confirm`
（headless 里它会被自动 accept，那条判据就没牙了——口径同阶段二的清空对话）。

### Ruling（这一轮定下的口径，附代价）

1. **确认词不进 `frontend/src/constants.js`，留在组件内当单一常量**：那文件的章程是"后端契约在前端的镜像"，
   由 `backend/tests/test_frontend_constants.py` 两头钉；把一枚纯交互的常量塞进去，会让"这里多写一份副本会红"
   那条门禁变成假命题。代价是镜像集与交互常量分在两处，读代码的人得知道哪个是哪个。
2. **三条清理路径复用同一段 `resetWorkspace`（经 `handleSessionLost`）**：登出、运行中 401、注销成功后
   清理动作必须一字不差，否则"退出清得干净、注销清不干净"是最难查的那种不对称。代价是注销的回调名
   （`handleSessionLost`）读起来不像它的语义——注释里写明了这层复用是故意的。
3. **注销成功后不补发 `/logout`**：`auth_tokens` 那片行已经随账号没了，那一枪只会撞一次 401 ⇒ 回调 ⇒ 环。
   与 advisory ②（票过期那条）同一条理由，两处判据各钉一半（`calls.filter(...logout)` 为空）。
4. **向量清扫是 best-effort，失败不改状态码**：使用者拿到的 204 说的是"账号没了"，不是"两个库都验证干净了"。
   代价是残留向量在界面上一律不可达（读侧按 `user_id` 收窄）却仍占盘，本轮**没有**清扫失败的补偿重扫入口。
5. **浏览器门不加"真按注销键"的判据**：它会在共享真库里删掉一个账号，代价与收益不成比例。
   端到端的替代证据是 jsdom 那条走真实链路的判据（真发 POST、真清 localStorage）+ ①② 两闭的端点判据。
   代价：真浏览器里这一节的**渲染**只被既有的容器不变式覆盖（L1 证明那条覆盖得到），没有独立几何断言。

### 挂账（knowingly 没堵的四面）

1. **两个标签页并发注销**：一处注销、另一处仍活着，那一侧的下一次请求会撞 401 落回登录页——今天靠
   `handleSessionLost` 顺带成立，**没有判据、也没有变异轮**。与 ② 提交信息里那句是同一笔账。
2. **"越界删到别人名下"只有判据、没有变异证据**：跑那一轮的变异等于在共享真库里删掉 `default@local`
   的 43 条历史与 13 篇文档，代价不可接受（① 那轮就写进提交信息）。
3. **注销后重新注册同一个 identifier**：会拿到**新的 `users.id`**，旧数据（若清扫失败）与新账号无关联。
   这一格今天没有判据，界面上也不可见；要堵得先决定"同名重注册"算不算预期行为。
4. **清扫失败的补偿入口**（重扫某个 `user_id` 的向量）不存在：Ruling 4 的代价面，挂在这里而不是藏着。

### 过程偏离与自纠，如实记

- **控制者独自执行三条闭口**（无实施代理、无评审代理），**终审是自评** ⇒ 交付时明示。
- **一次备份撞名把 `backend/api/auth.py` 覆盖成了 `schemas/auth.py` 的内容**：变异备份按
  `mut-<basename>.py` 命名，而这两个文件 basename 相同。恢复路径：`git show HEAD:` 取回字节，
  再从会话转录里逐字重放本轮四处编辑（**排除那次变异本身**），sha 与基线 `64775ec0…` 逐字吻合、
  diff 回到 32/−4 才算数。此后所有备份一律按**完整路径**命名（`mut-frontend_src_api_auth.js` 这种），
  并把这条写进 [[project-crlf-mutation-hazards]]。
- **我自己新写的那条判据有个排序 bug**（不是实现的）：先断"填对确认词后按钮可用"、后断"密码被清掉"，
  而实现按设计把两格一起清 ⇒ 该条首跑红在 `expected '' to be undefined`。修法是把序列改成
  "词对 + 密码空 ⇒ 仍禁用 ⇒ 再填密码 ⇒ 可用"，两句判据都留住且都成立。教训与 ⑧ 那条同源：
  **先想清楚这一句在测门禁还是测清理，再决定它在序列里的位置**。
- **② 那轮里，`.queue-item` 长度 0 那条 DOM 断言是永久绿**（那个场景从头到尾没有队列项），
  已收掉、改由 `app.vm.documents/queue/messages` 三句 vm 层断言钉——理由写在测里：登出时 `.app-shell`
  整棵卸载，屏上没有残留可断。
- **预检复量脚本这次没跑成**（想当场重验 FK 图，`from config import get_config` ImportError、
  以及一句 `SELECT ... email` 撞 Unknown column）：台账里的 FK 与行数**抄自 ①② 那两轮的提交信息**，
  不是本轮新量；本轮新量的只有六张门的条数与 `/api/health` 的三格。
- **`Glob`/`grep` 在中文路径与 cp936 控制台上仍有假空**（`grep -n` 对明明存在的符号返回空）：
  关键计数一律换 `Read`/`ls`/字节计数复核，不以一次 grep 为空为证据。

## 追加运维：轮换 `DEFAULT_USER_PASSWORD`（2026-10-09，零代码改动）

注销账号收口时留给使用者的那一格（交付文档第四节第 10 条）由本人下令执行。语义：**换掉
`default@local` 的口令**，旧值因在脱敏提交 `0b22116` 之前进过 git history 而作废。
**本轮没有改一行代码、没有加一条判据**，所以没有 RED/GREEN，只有"改之前量一次、改之后量一次"。

### 为什么必须两头一起做（这条是本节的根，不是背景知识）

- `core/migrations.py:305-314`：`ensure_default_user` 查到 `identifier='default@local'` 已有行就
  **直接 return**，不重写哈希 ⇒ **只改 `.env` 是空转**，旧口令照样登录。
- 反过来只改库：`backend/tests/test_live_stream.py:46-50` 与 `frontend/tests-browser/_browser-probe.js:44`
  都从 `.env` 那枚键取口令去登录，两边不一致就是这两道门一起 401。
- 应用写法选 `db.update_user_password(user_id, hash_password(new))`（端点 `api/auth.py:181` 用的就是它），
  不写裸 SQL、不起第二份服务，也就绕开 Chroma 单实例锁（[[env-chroma-single-instance-lock]]）。

### 预检（改之前）

`.env` 655 B、**纯 LF**（`\r\n` 计数 0 / `\n` 计数 16 / 17 段）、`^DEFAULT_USER_PASSWORD=` 恰一枚、
键名清单 14 枚；旧值长度 **15**；`users` 里那枚 id=**30**；`verify_password(旧值, 库里哈希)` = **True**
（两头本来一致，所以这不是"修一处坏一处"的现场）；默认账号名下 `auth_tokens` = **0**。
备份先落 `D:\tmp\backup-backend_env-before-rotate`（**按完整路径命名**，见 [[project-crlf-mutation-hazards]] 第四族），
`cp` 后 sha 对拍相同。**验证通过后这份备份已删除**——它装的是已作废的口令，留着只多一个副本。

### 做法与顺序（先库后文件，每一步都有回验）

1. `secrets.token_urlsafe(24)` ⇒ 新值长度 **32**（在 `schemas/auth.py:36` 的 `6~64` 界内，这条先判过再写）。
2. 写库：`update_user_password(30, …)` 回 **1**；重读那行 `verify_password(新)=True`、
   `verify_password(旧)=False` **两半都过**才动文件（任一半不过就用内存里的旧值回滚库并退出）。
3. 改文件：只替换那一行，**其余 16 段逐段比对未变**（`assert`）；长度增量 **17** = 32−15；
   写后 672 B、键行仍唯一、`\r\n` 仍 0；`.env` sha256 前 `bc2f5dce1357` → 后 `c4c9c5bbcc7d`。
4. 全程**没有任何一处打印过键值**（脚本只打印长度、计数、sha 前 12 位与布尔）。

### 一条假警报，机制值得记（别按"读不到新值"去查 .env）

脚本内用 `subprocess` 起"全新解释器"读 `Config.DEFAULT_USER_PASSWORD`，回 **15**（旧值）⇒ 看着像写失败。
真相是 `load_dotenv` **默认不覆盖已存在的环境变量**，而父进程早已把旧值注入 `os.environ`，子进程继承了过去。
换法：`env -u DEFAULT_USER_PASSWORD python -c …` 从干净环境起 ⇒ 读到 **32**（新值）。
**口径**：验"`.env` 的新值被新进程读到"必须在**不继承该键**的子进程里量，别在父进程内 spawn。

### 端到端与库内复核

真 uvicorn（:8000，单实例，`Application startup complete` 后开测）：旧口令 `POST /api/auth/login` ⇒ **401**、
新口令 ⇒ **200** 且拿到票、`GET /api/auth/me` ⇒ **200**。

**我自己探针的两处错**（不是产品缺陷，但先记错处再记结论）：① 断 `me` 时读顶层 `identifier`，
而 `MeOut` 把载荷包在 `{"user": …}` 里 ⇒ 假红 False（状态码 200 才是真信号）；
② 登出打了 `DELETE /api/auth/logout`，端点是 **POST**（`api/auth.py:127`）⇒ 回 **405**，
于是漏下一张票。收尾用端点同一枚 `db.delete_token(hash)` 清掉自己那张（回 1），再走一遍
login → **POST** `/logout`（**204**）→ 用那张已花的票再打 `/me`（**401**）⇒ 默认账号名下 `auth_tokens` 归 **0**。

改完复核共享库现状：`users 2 / documents 13 / parent_chunks 4 / child_chunks 10 / chat_history 43 / auth_tokens 1`。
那唯一一枚票属 `users.id=338`（`3143958700@qq.com`，2026-11-06 过期），**不是本轮产生的**
（⑧ 那轮记的基线就是 `auth_tokens 1`），没动它。

### 门禁冲击（只抄当轮汇总行）

| 门 | 实数 | 说明 |
|---|---|---|
| 后端全量 `python -m pytest -q` | **345 passed / 2 skipped / 2 deselected / 1 warning**（58.38s） | 与注销收口那一记档值**逐字相同**；那 2 skip 仍是 `test_live_stream`（需要真服务，本轮只在端到端那一小段起过） |
| 浏览器门 `npm run test:browser` | **21 passed / 1 file**（两份服务自起自停） | 它是这枚口令的**真消费者**（`_browser-probe.js:44` 从 `.env` 读）⇒ 这条绿才是"轮换没打断验收门"的证据 |
| 前端 jsdom | **未重跑** | 本轮一行生产码没改，且那套把 API 全 mock 了、不吃这枚口令 |
| `-m live` 单文件 | **未重跑** | 全量那遍已含 live 组 |

服务按 CommandLine 核对后停干净（uvicorn PID 11904、vite PID 23972），两端口 `netstat` 复核 0 枚 LISTENING。

### 边界与偏离，如实记

- **历史仍翻得开**：轮换让旧值失效，但没有重写 git 历史（本机无远端，重写属破坏性操作，未做）。
- **不影响别的账号**：`users.id=338` 那枚账号的口令、它的 `auth_tokens` 一行都没动；
  `users.api_key/base_url` 与 `user_models` 也未动（本轮只碰 `password_hash` 一列一行）。
- **没走 `PUT /api/auth/password`**：那条路要填旧口令，而旧口令的值按纪律不进我的视野；
  选应用层的 DB 方法是同等效果里少一次凭据暴露的做法。**代价**：没测到端点那一层的表单校验，
  但界面上"改密码"那格仍归使用者自己用（他手上有 `.env` 里的新值）。
- **流程偏离**：零代码改动、无判据改动，因此没有变异自证轮；预检/写库/改文件/复核全部由控制者一人执行，
  结论是自评。

## 追加运维：把旧默认口令从 git 历史里抹掉（2026-10-09，改写 113 枚提交）

上一节留下那一格（「历史仍翻得开」）由使用者发话执行。**这是本机唯一一份仓库、无远端、无分支、无标签**，
一次不可逆的历史重写，所以顺序是：先把足迹量到无争议 ⇒ 三条裁定请使用者点定 ⇒ 在一份本地克隆里演练 ⇒
才动真仓。全程**没有任何一处打印过口令值**（除了第一版脚本的错，见「自错」那节）。

### 足迹预检（动之前量的，不是动之后补的）

- `backend/.env` **从未被跟踪**（`.gitignore:9`），所以明文不是从它进历史的；`git log --all -- backend/.env` 零命中。
- 全仓按对象类型扫（`rev-list --all --objects` + `cat-file`）⇒ 含 `DEFAULT_USER_PASSWORD=<字面量>` 的 blob
  跨**唯一一条路径**：`docs/superpowers/plans/2026-10-06-user-auth-isolation-phase-1.md`，**14 枚 blob 版本、43 枚提交**
  （最早 `218f89b8e` 2026-10-06、最晚 `f3fd3134d` 2026-10-07）。脱敏提交 `0b22116` 只改了**工作区那一版**，
  旧 blob 一枚没动 ⇒ "已经抹过了"是假安全感。
- 那枚字面量长 **17**、`sha1[:12]=0f1959dae8f2`（此后一律用哈希当身份，值不进脚本、不进日志）。
- **「一个 blob 里只出现一次」**是用值字节计数量的（14 枚 blob / 14 次命中）⇒ 没有散文里的第二处引用。
- 顺带做了"历史里有、HEAD 里没有"的孤儿扫描（口令形状 + `sk-` 形状），另两组 `hashpassword=…`（`test_api_auth.py`
  的测试假口令）与全部 `sk-` 命中都是**现在也还在 HEAD 里的替身值** ⇒ 本轮只需清那一枚，不必改两轮。
- 与上一节的一处**对不上，如实记**：台账记旧 `.env` 值长度 **15**，本轮从历史里清掉的那枚字面量长度 **17**
  ⇒ 两者不是同一枚串（历史那枚是计划文示例值）。那枚 15 字符的值现在**已无任何载体**（`.env` 已被覆盖、
  上轮备份已删），因此本轮**无法**对它做同样的全对象证明——这条挂在挂账里。

### 三条裁定（使用者点定，全部选推荐）

1. **做法**：`git filter-branch --index-filter` 就地改写（git 自带、零安装）；不装 `git-filter-repo`（那是新增依赖）。
2. **备份**：改前 `git bundle --all`，**验证通过即删**——备份必然含那枚旧值，留着等于没清干净。
3. **旧引用**：**不改写文档**，只在台账落一张新旧映射表。

### 做法（只动那一条路径、只动那一枚值）

回调脚本 `D:/tmp/kb_purge_filter.py`（本轮临时件，跑完删）在 index-filter 环境里：`ls-files -s` 取该路径的 blob ⇒
按 `sha1[:12]` 认出目标 ⇒ 先把**键锚定那一格**换成 `<REDACTED-ROTATED-2026-10-09>` ⇒ 再把同一 blob 里剩余的同样字节
一并换掉（防散文引用）⇒ `hash-object -w` + `update-index --cacheinfo`。**其它任何路径、任何提交信息都不碰**。
`FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch --force --index-filter 'python …' -- master`。

### 演练仓先跑一遍，抓到两处「旧对象赖着不走」

`git clone --no-hardlinks` 出一份本地克隆（236 提交 / 同 HEAD / 同树 / 同样 14 枚含值 blob）跑同一命令：

- **第一次收口失败**：删了 `refs/original/refs/heads/master` + `reflog expire` + `gc --prune=now` 之后
  仍 **14 枚命中**。原因是克隆自带的 **`refs/remotes/origin/master` 还钉着旧 tip**（`-- master` 不碰远端跟踪引用）。
  删掉它再 gc ⇒ blob 总数 **615 → 601**（正是那 14 枚），命中 **0**。
- **口径**：`filter-branch` 之后"对象真消失"需要三件一起：**`refs/original` 删 + reflog expire（含 `--expire-unreachable`）+ `gc --prune=now`**，
  而且**任何指向旧 tip 的 ref 都得算进去**。真仓无远端跟踪引用，预检时 `for-each-ref` 只有 `refs/heads/master` 一条。

### 真跑与验证（逐条实测，不采信"应该没问题"）

| 量 | 结果 |
|---|---|
| 回调 REWRITE 次数 | **43**（与"43 枚提交含值"对上） |
| 新 HEAD | `a6d75fb`（与演练仓**同一枚**，改写是确定性的，这是一条交叉验证） |
| HEAD 树 | `5500878d297c83ff4a018d51c2e364f3e211139c` **与改前逐字节相同** ⇒ 当前工作区内容零改动 |
| 133 个文件的 blob 指纹对拍 | `diff` 空 ⇒ 生产码 / 测试 / 文档的**当前版**一枚都没变 |
| `git fsck --full` | 无输出 |
| 提交数 / 标题 / 日期 | **236 / 236 逐位标题一致 / 236 逐位日期一致**（filter-branch 保住了 author 与 committer 日期） |
| 换 SHA 的枚数 | **113**（从最早含值提交 `218f89b8e` 起整条后缀），前 **123** 枚不动且实测全部未动 |
| **全对象滑窗复扫**（1874 枚：601 blob / 1037 tree / **236 commit**） | 目标值命中 **0** ⇒ 连提交信息也证清了 |
| `.git` 里非 objects 文件（`logs/`、`COMMIT_EDITMSG`、遗留的 `t6msg.txt` 等 28 枚） | 命中 **0**（`t6msg.txt` 连键名都不含，本轮复测仍是 28 / 0） |
| 引用面复测（"旧对象不再被钉住"） | `for-each-ref` 只 **1 条**（`refs/heads/master a6d75fb`，且在 `packed-refs` 里）、`.git/refs/**` 零文件（`refs/original` 是空目录树）、`git reflog --all` **0 条**、blob 总数 **601**（演练仓收口后同一个数）、`ORIG_HEAD=d07c62d…` 是 filter-branch 留下的**悬空指针**（`cat-file` 直接报 could not get object info ⇒ 它指向的对象已回收） |
| 盘上扫（工作区 / 桌面 / `.qoder` / `D:/tmp`） | 初扫命中 **7**，见下节；处置后复扫实测 **5581 枚文件 / 命中 0**（97.0s，跳过 5 枚 >30MB；根＝仓库工作区（不含 `.git`、`node_modules`、`.venv`、`__pycache__`、`site-packages`）、`C:/Users/31439/.qoder` 整棵、Desktop、Downloads、`D:/tmp`、`AppData/Local/Temp/qoder-cli`） |

### 盘外那 7 处载体：在 Qoder 自己的 file-history 里

`C:/Users/31439/.qoder/file-history/<session>/7f56ee3cb14875ac@v2 … @v8` —— **阶段一计划文的 7 份编辑快照**，
每份 1 处明文（225535B → 225547B 等，各 +12 字节 = 占位串 29 字节 − 原值 17 字节）。这不在 git 范围内，但装的是同一枚值。
处置选**原地替换**而不是删文件：删快照会在 file-history 里留悬空索引，原地换值既断载体又保住版本序列。
字节数与残留计数（每份替换后滑窗 0）逐条记在过程日志。

### 自错四条（都在"证据"这一面，不是产品）

1. **第一版扫描脚本打印了值的前 8 个字符**（`prefix8=`）——口令前缀因此进了终端记录与本轮会话转录，**不可回收**。
   纪律补一条：验值只报 `sha1[:12]` 与长度，**连前缀都不报**。值已作废（上一节 401 实测），但这是本轮最实在的一处失分。
2. **两次"0 命中"是假阴性**，都靠"数字不合理就该怀疑"抓回来：① `git cat-file --batch-all-objects` **单用是非法参数**
   （退码 **129**，需要配 batch 模式），我 `capture_output` 把 stderr 吞了 ⇒ python 数到 **0 枚对象**却打出"命中 0"；
   ② 改流式解析后状态机只数到 **1 枚**（同样假绿）。第三次改成 `--batch-check` 拿清单 + 逐枚 `cat-file`，
   数到 **1874** 才认。另早先那句"盘上 0 命中"只扫了 `memory` 目录 ⇒ 漏掉 `.qoder/file-history` 那 7 处。
3. **`grep` 打印值的上下文**这一步一开始想做"带 120 字节上下文"的辨认，改成先脱敏再显示（`<TOK>` / `<REDACTED>`），
   避免辨认动作本身把值二次外印。
4. **台账正文里两处数字是没量就写下的**：①「复扫 5108+ 文件 0」用的是估计值，本轮真跑一遍复扫得到 **5581 / 0**（97.0s）才替换；
   ② 高频锚点那格里 `fae2acc` 的新 SHA 我写了 `b7e…` 省略号——**根本没查就编了个前缀**，映射表第 4 行的实测值是 `cf4647f76`。
   这条最扎心的地方在于：本项目纪律就是「报数一律实测、只抄当轮汇总行」，而违反发生在**记这条纪律的同一轮写盘里**。
   顺带把扫描口径写清：**键锚定**（`PASSWORD=` 之类）+ 值哈希比对 ⇒ 只能测到"带键的字面量"，
   若那 17 字节散落在没有键名的散文里，这两次扫描都测不到；全对象滑窗（1874 枚）才是无锚的兜底，而那一只覆盖了 git 对象。
   收口那一笔提交之后又改了一次写法：本台账与交付文档里两处「**现 HEAD = `a6d75fb`**」都改成「**重写那一刻的 tip**」——
   长命文本里填具体 tip 会随下一笔提交当场腐烂（这一笔本身就是证据），要现值只问 `git rev-parse HEAD`。

### 门禁冲击（本轮一行生产码没改，门是"确认没打断"）

| 门 | 实数 | 说明 |
|---|---|---|
| 前端 jsdom `npm test` | **162 passed / 14 files**（4.78s） | 与注销收口那一记档值**逐字相同** |
| 后端离线 `-m "not live and not migration"` | **320 passed / 29 deselected / 1 warning**（48.04s） | 同上逐字相同；不起服务、不开 Chroma，不撞单实例锁 |
| 后端全量 / live / 浏览器门 / build | **未跑** | HEAD 树与 133 枚文件指纹**逐字节未变** ⇒ 跑不出新信息；浏览器门要两份服务，本轮无必要起 |

### 边界与挂账，如实记

- **备份已删 ⇒ 没有回滚路径**。可用的是：映射表（本目录 `sha-mapping-2026-10-09.txt`，115 行 = 2 行注释 + **113 条 old→new**）
  与改写确定性交叉验证（演练仓与真仓得到同一枚新 tip）。
- **文档里的旧 SHA 引用一条没改**（按裁定 3）。口径：**100 枚**作废旧 SHA、**598 处**出现、散在 **53 枚 md**。
  上一节预检报的 **170** 是"每文件去重后相加"的另一个口径，两个数都对，别混用。高频锚点：
  `28928d763`→`347f69f48`(x21)、`41b45d222`→`a6678578a`(x19)、`79902a2c9`→`a218537bc`(x18)、
  `0b22116d0`→**`8d351b0d8`**(x14，交付文档与台账里"脱敏提交"那一枚)、`fae2acc1a`→**`cf4647f76`**、`12bf74b`→**`a6d75fb`**（旧 tip 即新 tip 的前身）。
  完整逐条查 `sha-mapping-2026-10-09.txt`。
- **本台账/交付文档/记忆里最常引用的 16 枚短 SHA 现已全部 `DANGLING`**（`git cat-file -e <sha>^{commit}` 逐个实测），
  顺翻文档的人按这张表换算（新值逐条从映射表 grep，不是回忆）：
  `de8499d`→`6e67d1f4e`(①)、`ee117fd`→`bd2bd1f51`(②)、`e1f4d45`→`4910b8f50`(② 补账)、`bcc0296`→`051553215`(③)、
  `423a26a`→`874949ed2`(④)、`e0ecfe1`→`d1622c5a4`(⑤)、`6a327ca`→`79a671358`(⑥)、`74d11b8`→`02d7b7ecb`(⑦)、
  `e4f572f`→`8c1a2cb03`(⑧)、`b12c2c2`→`f6702b196`(注销①)、`594458a`→`77d7ce9fd`(注销②)、`35e9498`→`0ba49fe73`(注销③)、
  `fae2acc`→`cf4647f76`(注销台账)、`12bf74b`→`a6d75fb52`(轮换台账；`a6d75fb` 只是**重写那一刻的 tip**，收口的文档提交会让 HEAD 继续前移 ⇒ 要现值就问 `git rev-parse HEAD`，别把本文任何"现 HEAD"当长期事实)、`0b22116`→`8d351b0d8`(脱敏提交)、
  `e60dcf4`→`0534e6588`(阶段二码末)。**未换的 123 枚里**能查到的锚点照旧可用——判断方法只有一个：拿旧 SHA 问一次 `cat-file -e`。
- **挂账①**：那枚 15 字符的 `.env` 旧值本轮无法证伪（载体已全灭，无值可扫）。若将来再要证明，需要重新取得该串。
- **挂账②**：会话转录 jsonl 里留有我打印的 **8 个字符前缀**（自错 1）。转录不是仓库的一部分，也没法"重写"，只能记下来。
- **挂账③**：`.git/t6msg.txt` 是一枚来历不明的遗留文件（117 B，已验不含本值，**未动**——不是我建的文件我不删）。
- **流程偏离**：零代码改动、无判据改动，因此没有 RED/GREEN 与变异轮；改写由控制者一人执行，
  但**先在本地克隆演练、再动真仓**，且验证不靠自评而是靠"树逐字节相同 + 全对象滑窗 + 文件指纹对拍"三条可复核的硬指标。

## 清单进度

| 条 | 事项 | 状态 |
|---|---|---|
| ① | `LlmIn` 两格长度界量在 strip 之前 | **已闭合**（`de8499d`） |
| ② | `AVATARS` 两份 / `PASSWORD_MIN` 三份没有单一出口 | **已闭合**（`ee117fd`：七枚镜像收进 `frontend/src/constants.js`，`backend/tests/test_frontend_constants.py` 五条判据两头钉，另消灭三处模板里写死的数字）**+ 补账 `e1f4d45`**（② 收口时留的两格账：`schemas/chat.py` 的 `parent_ids` 两枚界 + `model_name` 一枚界进镜像集 ⇒ **九枚镜像 / 六条判据**，前端 `MAX_ID_CHARS`/`MAX_SELECTED_CHUNKS` 从 `useChunkSelection.js` 的本地常量收进同一出口；括号深度切片器 + 按位置归属两枚界，八轮变异自证，`6 passed` / 全量 337 / 离线 313 / jsdom 158 / build 换 hash `index-CKhscz7G.js`） |
| ③ | 两枚同名 `FakeConfig`（`tests/fakes.py:1`、`tests/test_migrations.py:182`） | **已闭合**（`bcc0296` + 补正 `d89bb29`：预检证明迁移判据吃四键 ⇒ 不合并，迁移那枚改名 `MigrationConfig`；新增 `tests/test_test_doubles.py` 钉"模块顶层 `Fake*` 类名唯一"，六轮变异自证） |
| ④ | `ChatHistory.user_id` / `documents.user_id` 的 FK 只在新建库存在 | **已闭合**（`423a26a`：`ensure_foreign_keys` 按 **(表, 列)** 问 `KEY_COLUMN_USAGE`、不写 `ON DELETE`（RESTRICT）、排在 `ensure_indexes` 之后；预检在真库量到 `chat_history` 43 行孤儿（旧默认账号 id=1 已不存在），经使用者拍板新增 `reclaim_orphaned_owners` **先归户再 ALTER**；单测 +7、live +1（RESTRICT 行为面）+1 格（外键与孤儿的第二遍白卷），十二轮变异自证，真库落库后实测各一枚 FK / 0 孤儿 / 各一枚索引） |
| ⑤ | `user_models` 至多一枚默认靠应用层两步，并发可留两枚 | **已闭合**（`e0ecfe1`：MySQL 无部分索引 ⇒ 守卫落在 `default_guard` 这枚 **STORED 生成列** + 只盖它一列的**唯一索引**上（NULL 不参与唯一比较 ⇒ 非默认随便多、默认每人至多一枚）；迁移四步各查各的：**数重复 → 降掉除 `MIN(id)` 之外 → 补列 → 建索引**，去重早于建索引是 scratch 表实测钉的（`ALTER` 在两枚默认上照样成功、`CREATE UNIQUE INDEX` 才回 1062，而 lifespan 不兜异常 ⇒ 反了就是后端起不来）；存在性用严格口径问 `GENERATION_EXPRESSION <> ''`（同名普通列的后果是静默的零约束）；顺带堵掉 ⑤ 自己会引入的谎——撞守卫键不再回 409「已在你的名单里」，改为补插成非默认。单测 +8（迁移 6、形状 2）、live +2（引擎本身拒第二枚默认 / 注入钩子把撞键窗口变成确定性可复现），八轮变异逐轮一条红；真库落库后直查列与索引形状、多默认人数 0、行数与默认数未变，另在 scratch 表上把"首次建守卫 + 去重 1 行"整条实测过，真开机一遍拿到 `kb.migrations` 的 summary 原文） |
| ⑥ | 迁移的"缺 key 半态"分支从未在真 `.env` 上跑过 | **已闭合**（`6a327ca`，按使用者裁定**不动 `.env`、改判据**：`seed_default_llm` 的三条出口各带一枚常量 `reason`（`env_incomplete` / `already_configured` / `seeded`），`run_migrations` 的 summary 新增 `seed_reason` 把它带进开机日志——原先两条早退回同一个字典，`llm_seeded: False` 分不清是"`.env` 缺键"还是"默认账号已有 key"；「缺 key 半态」由注入的 `IncompleteEnvConfig` 在**离线门**上证两件事（那遍一行没写 + 报得出走了哪条）。判据 +3（`test_migrations.py` 30→33，含 caplog 钉"两遍 no-seed 布尔逐格相同、只有 reason 分开"与"日志里不许出现 key"），另**有意改写**四处整字典相等断言。七轮变异 M1–M6 各红 3–4 条、M7 是对照组（只换字典键序 ⇒ 33 全绿，判据钉值不钉形状）；真开机一遍拿到 `'seed_reason': 'already_configured'`（⑤ 那轮只能推断的这一格现在是日志里读出的事实）。**边界如实记**：真 `.env` 上"缺键"那半本机仍未跑过，证据换成离线判据；"写了 key 但没加模型"的两支因没有各自报名 |
| ⑦ | 422 的 `detail[*].input` 回显，只靠 `client.js:32` 那条 fallback 挡着 | **已闭合**（`74d11b8`，按使用者裁定的这条路「前端 fallback 剥掉 input」：新增模块级 `validationItemText`，数组 detail 的每一项只准 **msg（且只认非空字符串）、type、loc** 上屏，兜底改成**白名单挑键**而不是整枚 stringify ⇒ `input`（FastAPI 原样回显的请求值，`PUT /api/auth/me/llm` 那一枚里就是明文 api_key）与 `ctx`（pydantic 允许塞任意值）都到不了界面。键序按 FastAPI 自己的 `type`、`loc` ⇒ 阶段二那条"缺 msg 降级为 JSON 文本"判据**期望值一字未改仍绿**；三条网络出口共用 `httpError` 这一构造点，故 fetch / SSE / 上传 XHR 一起受保护。判据 +4（`client.test.js` 26→30，含 `httpError` 直接构造那条、`null` 项那条、ctx 载荷故意与 secret 不同那条），九轮变异 M1–M8 逐轮只红目标面（M3 只红 1 条证明 input/ctx 两面分开计量）、M9 对照组全绿。前端全量 **158 passed/14 files**、build 产物换 `index-CWg0-YgN.js`；后端一行未动（全量 336/2/2/1 逐字不变，跨端那 5 条单跑绿）。**边界如实记**：只管"上界面"，422 响应体里 `input` 依然在（devtools / 代理日志 / 直连 API 仍可见），要连那一面一起堵得在后端挂 `RequestValidationError` 处理器，不在本条范围；"值写进 msg"的绕路今天不成立（两处 validator 实测只写长度），挂账 |
| ⑧ | 视口/交互探针是一次性脚本，没有常驻回归测试 | **已闭合**（`e4f572f`，按使用者裁定的这条路「装成 devDependency + 常驻判据」：`puppeteer-core@^25.12.0` 进 `package.json`/lockfile，判据放**独立目录 + 独立 config**（`frontend/tests-browser/` + `vitest.browser.config.js`，`fileParallelism:false`）⇒ `npm test` 那套单位门仍然任何机器都能跑，浏览器门走 `npm run test:browser`；前置条件失败**响亮报错不 skip**（`requireStack` 分得清"dev 连不上"与"dev 在、后端不在=代理 502"）。判据口径钉**数据无关的几何不变式**：三档视口（1280×900 / 375×800 / 500×900）共判整页不滚、消息区是有界滚动容器、高内容（DOM 合成 3000px，必须 `flex:0 0 auto`）撑开的是消息区不是页面，宽屏发送键在视口内且不溢出、两层浮层不重叠且整块在视口内，≤768 控件行与候选池、全程新增 console/page error 为 0；登录/登出全走 API（点 `.rail-signout` 在窄屏会被遮罩吃掉），跑前跑后库内行数逐格相同（`auth_tokens 1 / users 2 / documents 13 / parent_chunks 4 / chat_history 43`，登出实测 204）⇒ **不烧配额、不写业务数据**。首跑 12 条有 1 条红且红在**判据自己**（`.picker-results` 是 `v-else-if`，busy/空态不渲染）⇒ 改成"真实列表优先、否则挂同类名临时节点"两口径并报，并把类名另钉进 `chunk-selection.test.js`；判据分两轮加宽到 21，已跑过的变异轮在新集上全部重跑。十四格变异（基准 `layout.css` sha `03705068a7e9`，每轮 sha 回基准）：M1a/M2a 各全绿**逼出计算样式判据**、M1b/M2b 各 `1 failed`、M3a 宽度上界全绿（挂账①）、M3b 高度脱约束 `4 failed`、M4 `1 failed`、M5/M5b 两行互为兜底各全绿、M5c 一起删 `1 failed「页面被顶开 2629px」`、M6 `2 failed`、M7 `100dvh` 与继承 100% 分不出（挂账②）、M8 对照组全绿。门禁：浏览器门 **21 passed/1 file**、`npm test` **158/14** 逐字不变、build 产物 hash **两枚都未变**（生产码 0 改动）、后端三门未重跑（diff 只在 `frontend/`，口径同 ①③⑦）。**挂账三面**：弹窗宽度上界 560 无判据、`100dvh` 桌面 headless 不可分辨、`.settings-model-row{flex-wrap:wrap}` 的牙齿是数据相关 |
| 追加 | 注销账号（硬删，MySQL + Chroma 两头一起抹，不可恢复） | **已闭合**（三闭一提交：`b12c2c2` 级联删行 → `594458a` `deactivate` 端点 + 按主人戳清扫向量 → `35e9498` 前端危险区两道确认 + App 接线；三道门按「令牌 → 口令 → 默认账号」排序、两头删按「行先、向量后」，确认词留组件内不进镜像集，清理复用 `handleSessionLost` 不补发 logout。19 轮变异自证 + 浏览器侧 L1 一轮。六张门实数：后端 **345/2/2**、离线 **320/29**、live **25**、jsdom **162/14**、build 换 `index-CrrLaEBX.js` + `index-C4mVDwWj.css`、浏览器门 **21/1**。挂账四面见上节 |
| 追加运维 | 轮换 `DEFAULT_USER_PASSWORD`（交付文档第四节第 10 条那一格） | **已完成**（2026-10-09，**零代码改动**：顺序是先用 `db.update_user_password` 写库并双向回验（新 True / 旧 False）再改 `.env` 那一行；真 HTTP 实测旧口令 401、新口令 200、`POST /logout` 204 后默认账号名下票归 0；冲击确认后端全量 **345/2/2** 与浏览器门 **21/1** 逐字不变，jsdom 与 `-m live` 未重跑（理由见上节）。新值只进 `backend/.env`，未落任何文本副本，含口令的备份文件验证后已删） |
| 追加运维 | 把旧默认口令从 **git 历史**里抹掉（上一节「历史仍翻得开」那一格） | **已完成**（2026-10-09，零代码改动：`filter-branch --index-filter` 只动 `docs/superpowers/plans/2026-10-06-user-auth-isolation-phase-1.md` 这一条路径、只换那一枚值 ⇒ **43 次 REWRITE**、HEAD `12bf74b`→**`a6d75fb`**、**113 枚换 SHA / 前 123 枚实测未动**、236/236 标题与日期逐位一致。四条硬指标：HEAD **树 `5500878d297c…` 逐字节未变** + **133 枚文件指纹 `diff` 空** ⇒ 工作区零改动；**1874 枚对象滑窗 0 命中**（含 236 枚提交信息）；`.git` 非 objects **28 枚 0 命中**；盘上 **5581 枚 0 命中**。收口靠三件一起（删 `refs/original` + `reflog expire --expire-unreachable=now` + `gc --prune=now`），这条是演练仓抓到「克隆的 `refs/remotes/origin/master` 钉着旧 tip ⇒ 14 枚 blob 杀不掉」才写实的。盘外同一枚值另有 **7 份 Qoder file-history 快照**，原地换值不删文件。按裁定**没有重写任何文档里的旧 SHA 引用**，改用本目录 `sha-mapping-2026-10-09.txt`（115 行 = 2 注释 + **113 条 old→new**）；**备份 bundle 验证通过后已删 ⇒ 无回滚路径**。门禁只重跑 jsdom **162/14**、后端离线 **320/29**（两遍逐字相同）。**自错四条**（含"第一版脚本打印了值的前 8 字符"与"台账里两处没量就写的数字"）、**挂账三面**（15 字符那枚旧 `.env` 值无载体无法证伪 / 转录里的 8 字符前缀 / `.git/t6msg.txt` 未动）见上一节 |
