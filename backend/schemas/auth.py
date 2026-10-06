"""认证接口的入出参形状（spec 3.1）。

标识符的正则与归一放这里：它是"接口接受什么样的字符串"这件事的一部分，
将来换一种登录入口（比如用户名）要动的就是这个文件，不是端点也不是 core。
"""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class UserOut(BaseModel):
    """from_attributes 让它能直接吃 ORM 的 User 行。

    没有 password_hash 这个字段——少写一个字段比写一个"过滤掉敏感列"的逻辑可靠得多。
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    identifier: str
    identifier_type: str
    nickname: str
    avatar: str


class AuthOut(BaseModel):
    token: str
    user: UserOut
    # 对话 id 与登录凭证是两件事（决策 2）：注册/登录那一刻由后端 uuid4() 造一个新的，
    # 刷新页面走 GET /me 不再发新 id，所以刷新不会把当前对话换掉。
    session_id: str


class MeOut(BaseModel):
    user: UserOut
