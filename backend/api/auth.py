"""注册 / 登录 / 登出 / 我是谁（spec 3.1 的阶段一部分）。

发令牌只在这四个端点里的两个发生：那一刻哈希进库、原文写进响应，
此后服务端再也不认识那串原文——这是"可吊销"唯一的成本，也正是它的意义。
"""
import logging
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError

from core.security import hash_password, hash_token, new_token, verify_password
from deps import bearer_token, get_config, get_current_user, get_db
from schemas.auth import AuthOut, LoginIn, MeOut, RegisterIn, UserOut

router = APIRouter(prefix="/api/auth")
logger = logging.getLogger("kb.api.auth")

LOGIN_FAILED = "账号或密码不正确"
ACCOUNT_TAKEN = "该账号已注册"

# 账号不存在时也走一次哈希比较，让"没这个账号"与"密码错"在耗时上不可分辨。
# 迭代数给 1000 就够：这条路径要的是"确实花时间算过"，不是"算满 39 万次"。
_DUMMY_HASH = "pbkdf2_sha256$1000$" + "0" * 32 + "$" + "0" * 64


def default_nickname(identifier: str, identifier_type: str) -> str:
    if identifier_type == "email":
        head = identifier.split("@")[0]
        return head[:50] if head else "用户"
    return f"用户{identifier[-4:]}"


def _issue(db, config, user) -> AuthOut:
    token = new_token()
    db.create_token(user_id=user.id, token_hash=hash_token(token),
                    expires_at=datetime.now() + timedelta(days=config.AUTH_TOKEN_TTL_DAYS))
    return AuthOut(token=token, user=UserOut.model_validate(user), session_id=str(uuid.uuid4()))


@router.post("/register", status_code=201, response_model=AuthOut)
def register(payload: RegisterIn, db=Depends(get_db), config=Depends(get_config)):
    try:
        user = db.create_user(
            identifier=payload.identifier,
            identifier_type=payload.identifier_type,
            nickname=(payload.nickname or "").strip() or default_nickname(
                payload.identifier, payload.identifier_type),
            password_hash=hash_password(payload.password),
        )
    except IntegrityError:
        # 并发注册撞 unique 必须收在 409：让它冒到兜底 handler 就成 500，
        # 而 500 会让客户端以为"没注册上"从而重试，重试再撞一个更难看的世界
        logger.info("注册撞已存在的标识: %s", payload.identifier_type)
        raise HTTPException(status_code=409, detail=ACCOUNT_TAKEN)
    return _issue(db, config, user)


@router.post("/login", response_model=AuthOut)
def login(payload: LoginIn, db=Depends(get_db), config=Depends(get_config)):
    user = db.get_user_by_identifier(payload.identifier)
    matched = verify_password(payload.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not matched:
        # 一句文案盖住两种失败：分开回等于把"哪些邮箱注册过"送给外人
        raise HTTPException(status_code=401, detail=LOGIN_FAILED)
    return _issue(db, config, user)


@router.post("/logout", status_code=204)
def logout(request: Request, db=Depends(get_db), user=Depends(get_current_user)):
    db.delete_token(hash_token(bearer_token(request)))
    return None


@router.get("/me", response_model=MeOut)
def me(user=Depends(get_current_user)):
    return MeOut(user=UserOut.model_validate(user))
