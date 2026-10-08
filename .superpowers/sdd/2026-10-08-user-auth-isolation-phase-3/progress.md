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

## 清单进度

| 条 | 事项 | 状态 |
|---|---|---|
| ① | `LlmIn` 两格长度界量在 strip 之前 | **已闭合**（`de8499d`） |
| ② | `AVATARS` 两份 / `PASSWORD_MIN` 三份没有单一出口 | **已闭合**（`ee117fd`：七枚镜像收进 `frontend/src/constants.js`，`backend/tests/test_frontend_constants.py` 五条判据两头钉，另消灭三处模板里写死的数字） |
| ③ | 两枚同名 `FakeConfig`（`tests/fakes.py:1`、`tests/test_migrations.py:182`） | **已闭合**（`bcc0296` + 补正 `d89bb29`：预检证明迁移判据吃四键 ⇒ 不合并，迁移那枚改名 `MigrationConfig`；新增 `tests/test_test_doubles.py` 钉"模块顶层 `Fake*` 类名唯一"，六轮变异自证） |
| ④ | `ChatHistory.user_id` / `documents.user_id` 的 FK 只在新建库存在 | 待开工（做任何"注销账号"前必须先补） |
| ⑤ | `user_models` 至多一枚默认靠应用层两步，并发可留两枚 | 待开工 |
| ⑥ | 迁移的"缺 key 半态"分支从未在真 `.env` 上跑过 | 待开工（需要一个能临时改 `.env` 的受控窗口） |
| ⑦ | 422 的 `detail[*].input` 回显，只靠 `client.js:32` 那条 fallback 挡着 | 待开工 |
| ⑧ | 视口/交互探针是一次性脚本，没有常驻回归测试 | 待开工（`puppeteer-core` 本轮已 `npm prune` 清掉，做它要重装） |
