"""阶段三 ②：前端那几枚"后端的镜像"必须有单一出口，而且必须真的对得上。

开工前的形态（实测）：`EMAIL_RE`/`PHONE_RE`/`PASSWORD_MIN`/`PASSWORD_MAX`/`NICKNAME_MAX`
五枚写在 `AuthPanel.vue`，`AVATARS`/`PASSWORD_MIN` 又写在 `SettingsModal.vue`——
PASSWORD_MIN 一共三份，权威的那份在 `backend/schemas/auth.py:13`。每一处副本上面都挂着
一句"改动要两边一起改"。那句话不是门禁，是一句要求某个记性很好的人去执行的约定：
后端把 6 改成 8，前端全仓不会有一条判据红，表征是"注册页说 6 位能过、提交被 422 拒"。

这里把五件事变成判据：
① 这些名字在整个 `frontend/src` 里只许出现在一枚模块里（扫描面 = 交付物，不含 tests）；
② 那枚模块里的值必须与后端的权威定义逐字相同（数字、正则原文、头像集合）；
③ `AVATARS` 与 `AVATAR_LABELS` 同枚覆盖：加头像忘配标签，界面会给出 undefined 的 aria-label；
④ 副本的第二种长相——模板属性里写死的字面量（`maxlength="50"`、`placeholder="至少 6 位"`）——
   也不许存在：那种写法 ① 抓不到，但漂移后果与副本一模一样。
⑤ 问答契约那三格也算镜像：`schemas/chat.py` 的 `parent_ids` 有两个界（元素 100 = 一条块 id
   的长度，列表 50 = 最多选几条），`model_name` 有一个界（100，与 `ModelIn.name` 同源）。
   前端在 `useChunkSelection.js` 里各留了一枚本地常量（`MAX_ID_CHARS`/`MAX_SELECTED_CHUNKS`）。
   后端把 50 改成 80 时，前端仍然只在本地留 50，表征是"点到第 51 块前端就拦，而直接改
   localStorage 塞进去的那份会整请求被 422 拒"——两种入口各说一套。

判据放 pytest 而不是 vitest：漂移更可能由后端那一侧引入，而后端改动的人往往不跑 `npm test`；
反过来只改前端镜像时，本项目的收口口径是三门一起跑，下一道门就红。
"""
import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"

SCHEMAS_AUTH = BACKEND_DIR / "schemas" / "auth.py"
SCHEMAS_CHAT = BACKEND_DIR / "schemas" / "chat.py"
API_AUTH = BACKEND_DIR / "api" / "auth.py"
MIRROR = FRONTEND_SRC / "constants.js"

# 九枚"后端拥有、前端镜像"的字面量。后端权威定义分别在哪：
#   AVATARS -> api/auth.py 的元组（头像的唯一白名单）
#   PASSWORD_MIN / EMAIL_RE / PHONE_RE -> schemas/auth.py 顶部三行
#   PASSWORD_MAX / NICKNAME_MAX / MODEL_NAME_MAX -> schemas/auth.py 各 Field 里的
#       max_length（后端没有命名，所以按字段名抓行）
#   MAX_ID_CHARS / MAX_SELECTED_CHUNKS -> schemas/chat.py 的 parent_ids 那条声明
#       （一条声明两枚界，分两行写：元素界 100 = 一条块 id 的长度，列表界 50 = 最多选几条）
NAMES = ("AVATARS", "PASSWORD_MIN", "PASSWORD_MAX", "NICKNAME_MAX", "MODEL_NAME_MAX",
         "EMAIL_RE", "PHONE_RE", "MAX_ID_CHARS", "MAX_SELECTED_CHUNKS")


def _frontend_lines(*suffixes):
    """逐行产出 (相对路径, 行号, 原文)。扫描面 = frontend/src 的交付物，不含 tests。"""
    for path in sorted(FRONTEND_SRC.rglob("*")):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        rel = str(path.relative_to(FRONTEND_SRC)).replace("\\", "/")
        for lineno, line in enumerate(_text(path).splitlines(), 1):
            yield rel, lineno, line


def _text(path: Path) -> str:
    # 中文与 emoji 都在这两个文件里，读的时候必须钉 utf-8（本机默认 cp936）
    return path.read_text(encoding="utf-8")


def _frontend_declarations():
    """返回 frontend/src 里那些名字的声明位置 [(相对路径, 行号, 名字)]。"""
    hits = []
    for rel, lineno, line in _frontend_lines(".js", ".vue"):
        match = re.match(r"\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=", line)
        if match and match.group(1) in NAMES:
            hits.append((rel, lineno, match.group(1)))
    return hits


def _js_number(name):
    text = _text(MIRROR)
    match = re.search(rf"^export const {name} = (\d+)\s*(?://.*)?$", text, re.M)
    assert match, f"constants.js 里抓不到 `export const {name} = 数字`"
    return int(match.group(1))


def _js_regex_source(name):
    text = _text(MIRROR)
    match = re.search(rf"^export const {name} = /(.+)/\s*(?://.*)?$", text, re.M)
    assert match, f"constants.js 里抓不到 `export const {name} = /.../`"
    return match.group(1)


def _js_string_list(name):
    text = _text(MIRROR)
    match = re.search(rf"^export const {name} = \[(.*?)\]", text, re.M | re.S)
    assert match, f"constants.js 里抓不到 `export const {name} = [...]`"
    return re.findall(r"'([^']*)'", match.group(1))


def _js_object_keys(name):
    text = _text(MIRROR)
    match = re.search(rf"^export const {name} = \{{(.*?)\}}", text, re.M | re.S)
    assert match, f"constants.js 里抓不到 `export const {name} = {{...}}`"
    keys = []
    for quoted, single, bare in re.findall(r"(?:'([^']*)'|\"([^\"]*)\"|([A-Za-z_]\w*))\s*:", match.group(1)):
        keys.append(quoted or single or bare)
    return keys


def _py_number(text, name):
    match = re.search(rf"^{name} = (\d+)$", text, re.M)
    assert match, f"schemas/auth.py 里抓不到 {name} = 数字：权威定义挪窝了，这条判据该先红提醒你"
    return int(match.group(1))


def _py_string(text, name):
    match = re.search(rf'^{name} = r"([^"]*)"$', text, re.M)
    assert match, f'schemas/auth.py 里抓不到 {name} = r"..."：权威定义挪窝了'
    return match.group(1)


def _py_field_maxes(text, field_pattern):
    """抓 `<字段>: str = Field(..., max_length=N)` 每一行的 N（后端没命名，只能按行抓）。

    `field_pattern` 是字段名正则：password 要写 `\\w*password\\w*`（老密码/新密码都算一格），
    而 model 名那一格必须写精确的 `name`——写成 `\\w*name\\w*` 会把 `nickname` 也抓进来
    （nick**name**），50 与 100 混成一集，判据就红在解析器身上而不是漂移身上。
    """
    values = [int(m.group(1)) for m in re.finditer(rf"^\s*{field_pattern}: str.*max_length=(\d+)", text, re.M)]
    assert values, f"后端没有任何 {field_pattern} 的 max_length 界可抓"
    return values


def _py_statement(text, field):
    """按字段名切出整条声明（含续行）：括号不平就一直吃下一行。

    逐行正则为什么不够：`parent_ids` 的声明写在两行上，元素界在第一行的
    `Annotated[str, Field(...)]` 里、列表界在第二行的 `Field(default_factory=list, max_length=50)`
    里，`^\\s*字段: str.*max_length=` 那种单行模式只会看见第一枚，第二枚静悄悄漏掉。
    """
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if re.match(rf"^\s*{field}: ", line)), None)
    assert start is not None, f"抓不到 `{field}:` 开头的声明：字段改名或挪窝了，先红给你看"
    stmt, depth = "", 0
    for line in lines[start:]:
        stmt += line + "\n"
        depth += line.count("(") + line.count("[") - line.count(")") - line.count("]")
        if depth == 0:
            return stmt
    raise AssertionError(f"`{field}` 的声明括号没闭合，切片器口径得改：\n{stmt}")


def _py_two_bounds(text, field):
    """把一条带两枚界的声明分成 (元素界, 列表界)，每半必须恰好一枚。

    分界按 ` = Field(` 切：左半边是类型标注（`list[Annotated[str, Field(... max_length=100)]]`，
    管一条 id 多长），右半边是外层 Field（`max_length=50`，管最多几条）。
    为什么不用「先出现的算元素」这种顺序判据：把两行合成一行、或多加一枚界时，顺序判据会
    安静地把两枚界读反，界面表现是「能选 100 条、每条限 50 字」——数字都在，含义换了。
    """
    stmt = _py_statement(text, field)
    head, sep, tail = stmt.partition(" = Field(")
    assert sep, f"`{field}` 的声明里抓不到 ` = Field(`，形状变了"
    element, listed = re.findall(r"max_length=(\d+)", head), re.findall(r"max_length=(\d+)", tail)
    assert len(element) == 1 and len(listed) == 1, \
        f"`{field}` 该是标注里一枚界 + Field 一枚界，实抓 {element} / {listed}"
    return int(element[0]), int(listed[0])


def _py_avatars(text):
    match = re.search(r"^AVATARS = \((.*)\)$", text, re.M)
    assert match, "api/auth.py 里抓不到 AVATARS = (...) 元组"
    return re.findall(r'"([^"]*)"', match.group(1))


def test_mirrored_constants_are_declared_in_exactly_one_frontend_module():
    hits = _frontend_declarations()
    assert hits, "扫描面一个都没抓到：frontend/src 挪窝或改名了，此时这条判据是空集假绿"
    offenders = [hit for hit in hits if hit[0] != "constants.js"]
    assert offenders == []
    assert {name for _, _, name in hits} == set(NAMES), \
        f"每一枚镜像都该在那一个模块里，实抓 {sorted(n for _, _, n in hits)}"


def test_the_frontend_mirror_equals_the_backend_definitions():
    assert MIRROR.is_file(), "frontend/src/constants.js 不存在——镜像常量还没有单一出口"
    schema_text, api_text = _text(SCHEMAS_AUTH), _text(API_AUTH)

    assert _js_number("PASSWORD_MIN") == _py_number(schema_text, "PASSWORD_MIN")
    assert {_js_number("PASSWORD_MAX")} == set(_py_field_maxes(schema_text, r"\w*password\w*"))
    assert {_js_number("NICKNAME_MAX")} == set(_py_field_maxes(schema_text, "nickname"))
    assert {_js_number("MODEL_NAME_MAX")} == set(_py_field_maxes(schema_text, "name"))
    assert _js_regex_source("EMAIL_RE") == _py_string(schema_text, "EMAIL_RE")
    assert _js_regex_source("PHONE_RE") == _py_string(schema_text, "PHONE_RE")
    # 头像只比集合不比顺序：后端那枚元组管的是"收不收"（`not in AVATARS` 就 422），
    # 前端的顺序是选择条的显示顺序，属界面自选。比顺序会把"调一下按钮次序"变成跨端改动。
    assert set(_js_string_list("AVATARS")) == set(_py_avatars(api_text))


def test_chat_contract_bounds_are_mirrored_too():
    """问答契约的三格界与前端那三枚镜像必须同数——这一格是 ② 收口时留的账。

    `MAX_ID_CHARS`/`MAX_SELECTED_CHUNKS` 之前是 `useChunkSelection.js` 的本地常量（各一份，
    注释里写着"对齐 String(100)"），`MODEL_NAME_MAX` 已经进镜像集但只钉了 auth.py 那一头，
    chat.py 的 `model_name` 界无人核对——同一条请求里两个字段共用一枚上界，只核对一头等于
    没核对。

    两格刻意不并进来：`core/database.py` 的 `ParentChunk.parent_id = Column(String(100))` 是
    **存储宽度**不是契约界，合法的改法是加宽列而契约仍留 100，钉成相等会把一次正常迁移判红；
    `session_id` 的 100 前端没有对应的输入框（它来自 `GET /me`，用户不经手），没有可镜像的面。
    """
    chat_text = _text(SCHEMAS_CHAT)
    element_max, list_max = _py_two_bounds(chat_text, "parent_ids")

    assert _js_number("MAX_ID_CHARS") == element_max
    assert _js_number("MAX_SELECTED_CHUNKS") == list_max
    assert {_js_number("MODEL_NAME_MAX")} == set(_py_field_maxes(chat_text, "model_name"))


def test_every_avatar_choice_has_a_label():
    assert set(_js_string_list("AVATARS")) == set(_js_object_keys("AVATAR_LABELS"))


# 名字之外的第二种副本形态：模板属性里写死的字符串字面量。`const X =` 那种扫描看不见它，
# 而它的漂移后果与副本一模一样——后端把昵称上界改成 80，这里的 50 不会跟着动，
# 表征是"输入框还能敲到 80，提交被 422 拒"。两条判据各钉一种形状。
def test_no_hardcoded_number_in_a_vue_maxlength_attribute():
    offenders = []
    for rel, lineno, line in _frontend_lines(".vue"):
        match = re.search(r'\bmaxlength="(\d+)"', line)
        if match:
            offenders.append((rel, lineno, match.group(0)))
    assert offenders == [], "maxlength 必须绑到常量（:maxlength=\"NAME\"），不许写死数字"


def test_no_hardcoded_length_hint_in_a_vue_placeholder():
    """只打"数字 + 位/个字符"这种长度提示。

    实测 src 里带数字的 placeholder 有两枚：`至少 6 位`（违规）与
    `https://dashscope.aliyuncs.com/compatible-mode/v1`（示例路由，里面的 1 与长度无关）。
    口径写宽了就会拦掉后者，那种判据红一次就没人信它了。
    """
    offenders = []
    for rel, lineno, line in _frontend_lines(".vue"):
        match = re.search(r'\bplaceholder="([^"]*)"', line)
        if match and re.search(r"\d+\s*(?:个)?(?:位|字符)", match.group(1)):
            offenders.append((rel, lineno, match.group(1)))
    assert offenders == [], "输入提示里的长度数字必须来自常量，否则它与后端各自漂移"
