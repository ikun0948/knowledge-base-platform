"""认证接口的入出参形状（spec 3.1）。

标识符的正则与归一放这里：它是"接口接受什么样的字符串"这件事的一部分，
将来换一种登录入口（比如用户名）要动的就是这个文件，不是端点也不是 core。
"""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EMAIL_RE = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
PHONE_RE = r"^1[3-9]\d{9}$"
PASSWORD_MIN = 6


def normalize_identifier(kind: str, raw: str) -> str:
    """只验格式、不发验证码（决策 1）。邮箱归一小写：`A@B.com` 与 `a@b.com` 是同一个人。

    手机号只做整串校验、不剔除中间空格/横线——真发验证码的话这里还得归一成纯数字，
    本期没有那件事，多洗一次反而会把用户输进去的号改得他自己都对不上。
    """
    value = raw.strip()
    if kind == "email":
        value = value.lower()
        if not re.match(EMAIL_RE, value):
            raise ValueError("邮箱格式不正确")
    else:
        if not re.match(PHONE_RE, value):
            raise ValueError("手机号格式不正确")
    return value


class RegisterIn(BaseModel):
    identifier_type: Literal["email", "phone"]
    identifier: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=PASSWORD_MIN, max_length=64)
    nickname: str | None = Field(default=None, min_length=1, max_length=50)

    @field_validator("identifier")
    @classmethod
    def _normalize(cls, value: str, info) -> str:
        # 声明顺序保证 identifier_type 先验完，这里才拿得到它；坏值在 Literal 那关就 422 了
        return normalize_identifier(info.data.get("identifier_type", "email"), value)


class LoginIn(BaseModel):
    identifier: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=64)

    @field_validator("identifier")
    @classmethod
    def _normalize(cls, value: str) -> str:
        value = value.strip()
        # 登录不再要求前端声明类型：含 @ 就按邮箱归一大小写，否则原样当手机号
        return value.lower() if "@" in value else value


def mask_api_key(raw: str | None) -> str:
    """`sk-` 前缀 + 尾 4 位，其余 `****`（spec 3.1）。原文离开这个函数就只有数据库里那一份。

    短值不露尾巴：key 只有 7 位时"尾 4 位"会把大半串还回去，掩码就成了提示。
    """
    if not raw:
        return ""
    head = "sk-" if raw.startswith("sk-") else ""
    body = raw[len(head):] if head else raw
    if len(body) <= 8:
        return f"{head}****"
    return f"{head}****{body[-4:]}"


class UserOut(BaseModel):
    """from_attributes 让它能直接吃 ORM 的 User 行。

    没有 password_hash 这个字段——少写一个字段比写一个"过滤掉敏感列"的逻辑可靠得多。
    api_key 同理不出现：这里只有 `api_key_masked`，掩码在 `_user_out` 里做。
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    identifier: str
    identifier_type: str
    nickname: str
    avatar: str
    # —— 阶段二新增：后五项没有一项能靠 from_attributes 从 User 行读出来，
    #    它们来自 users.api_key/base_url 与 user_models 表，由 api/auth.py 的 _user_out 组装。
    llm_configured: bool = False
    llm_base_url: str = ""
    api_key_masked: str = ""
    models: list[str] = Field(default_factory=list)
    default_model: str | None = None


class ProfileIn(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=50)
    avatar: str | None = Field(default=None, min_length=1, max_length=20)

    @model_validator(mode="after")
    def _at_least_one(self):
        # 空 body 回 422 而不是 200："我提交了设置，它说成功了，我刷新一看没变"最难查
        if self.nickname is None and self.avatar is None:
            raise ValueError("昵称与头像至少要改一样")
        return self


class PasswordIn(BaseModel):
    old_password: str = Field(min_length=1, max_length=64)
    new_password: str = Field(min_length=PASSWORD_MIN, max_length=64)


class LlmIn(BaseModel):
    # 两格都不写 min_length/max_length：那两个数在 pydantic 里量的是**贴进来的原文**，
    # 而两侧的空白不是 key 的一部分。写在 Field 上的后果是双向的——
    # `"  sk-ab  "`（9 格、strip 后 5 格）被当成合法 key 写进库，症状推迟到问答侧的上游 401；
    # 而正好卡着列宽（String(255) / String(500)）的合法值，多贴一个空格反而吃 422。
    # 界因此搬进 validator，量在 strip 之后，值也在这里洗净。
    api_key: str
    base_url: str

    @field_validator("api_key")
    @classmethod
    def _strip_then_measure_key(cls, value: str) -> str:
        value = value.strip()
        # 纯空白不在这里报：端点那句「api_key 不能是空白」是一句话的 detail，比 pydantic 的
        # 数组好读，且 test_blank_api_key_is_422_and_writes_neither_column 钉的就是那句。
        if value and not 8 <= len(value) <= 255:
            raise ValueError(f"api_key 去掉首尾空白后须为 8~255 位，当前 {len(value)} 位")
        return value

    @field_validator("base_url")
    @classmethod
    def _looks_like_a_url(cls, value: str) -> str:
        value = value.strip()
        # 先量长度再验协议：顺序反过来会让"501 位的 http:// 开头串"收到一句答非所问的文案
        if not 8 <= len(value) <= 500:
            raise ValueError(f"路由去掉首尾空白后须为 8~500 位，当前 {len(value)} 位")
        value = value.rstrip("/")
        if not re.match(r"^https?://", value):
            raise ValueError("路由必须以 http:// 或 https:// 开头")
        return value


class ModelIn(BaseModel):
    # 1..100 与 user_models.name 的 String(100)、ChatRequest.model_name 三处同源
    name: str = Field(min_length=1, max_length=100)


class ModelsOut(BaseModel):
    models: list[str]
    default_model: str | None = None


# 设置端点（本 Task）与问答端点的模型解析（Task 7）要说同一句话，抄两遍迟早分叉
MODEL_NOT_IN_LIST = "模型不在你的名单里"

# 同一条理由的第二枚：有 key 但名单是空的人，收到的该是"去添加一个模型"而不是"去填 key"
EMPTY_MODEL_LIST = "你的模型名单是空的，请先在设置里添加一个模型"


def default_model_of(rows) -> str | None:
    """名单里"现在用哪个模型"的唯一口径：有标记取标记的那个，没标记取名单第一项。

    为什么住在这里而不是端点里：设置侧（`_user_out`/`_models_out`）与问答侧
    （`api/chat.py::_llm_context`）要的是同一个答案，两处各写一遍迟早分叉——分叉的表现是
    界面里选中的是 A、实际打出去的是 B。与 `mask_api_key` 同处一身的道理一样：
    这是"接口把 user_models 这张表说成什么口径"的一部分。

    为什么要有回落：`delete_user_model` 删掉当前默认时**不**动别人的 `is_default`
    （core/database.py 的 docstring 记着这个取舍），于是"删掉最后一个默认"之后名单会
    暂时没有标记。读取侧不兜的话 `default_model` 就是 None，而问答侧兜的是第一项——
    两边必须在同一句上，否则设置里显示有模型、发送却 409。
    """
    if not rows:
        return None
    return next((name for name, is_default in rows if is_default), rows[0][0])


class AuthOut(BaseModel):
    token: str
    user: UserOut
    # 对话 id 与登录凭证是两件事（决策 2）：注册/登录那一刻由后端 uuid4() 造一个新的，
    # 刷新页面走 GET /me 不再发新 id，所以刷新不会把当前对话换掉。
    session_id: str


class MeOut(BaseModel):
    user: UserOut
