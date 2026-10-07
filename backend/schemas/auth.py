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
    # 上界对齐两列：String(255) / String(500)
    api_key: str = Field(min_length=8, max_length=255)
    base_url: str = Field(min_length=8, max_length=500)

    @field_validator("base_url")
    @classmethod
    def _looks_like_a_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
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


class AuthOut(BaseModel):
    token: str
    user: UserOut
    # 对话 id 与登录凭证是两件事（决策 2）：注册/登录那一刻由后端 uuid4() 造一个新的，
    # 刷新页面走 GET /me 不再发新 id，所以刷新不会把当前对话换掉。
    session_id: str


class MeOut(BaseModel):
    user: UserOut
