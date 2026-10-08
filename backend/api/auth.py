"""注册 / 登录 / 登出 / 我是谁（spec 3.1 的阶段一部分）。

发令牌只在这四个端点里的两个发生：那一刻哈希进库、原文写进响应，
此后服务端再也不认识那串原文——这是"可吊销"唯一的成本，也正是它的意义。
"""
import logging
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError

from core.security import (ALGORITHM, PBKDF2_ITERATIONS, hash_password, hash_token,
                           new_token, verify_password)
from deps import bearer_token, get_config, get_current_user, get_db
from schemas.auth import (AuthOut, LlmIn, LoginIn, MeOut, MODEL_NOT_IN_LIST, ModelIn,
                          ModelsOut, PasswordIn, ProfileIn, RegisterIn, UserOut,
                          default_model_of, mask_api_key)

router = APIRouter(prefix="/api/auth")
logger = logging.getLogger("kb.api.auth")

LOGIN_FAILED = "账号或密码不正确"
ACCOUNT_TAKEN = "该账号已注册"

# 预设头像（决策 5：不做图片上传，项目里没有文件存储层）。'auto' = 昵称首字母。
AVATARS = ("auto", "😀", "🤖", "🦊", "🐼", "🚀")

# 账号不存在时也要做一次同价的哈希比较：耗时由 stored 串里的迭代数决定，
# 所以垫片的迭代数必须与真行一致，否则"没这个账号"会明显更快（spec 3.5）。
_DUMMY_SALT_HEX = "0" * 32
_DUMMY_DIGEST_HEX = "0" * 64
_DUMMY_HASH = f"{ALGORITHM}${PBKDF2_ITERATIONS}${_DUMMY_SALT_HEX}${_DUMMY_DIGEST_HEX}"


def default_nickname(identifier: str, identifier_type: str) -> str:
    if identifier_type == "email":
        head = identifier.split("@")[0]
        return head[:50] if head else "用户"
    return f"用户{identifier[-4:]}"


def _user_out(db, user) -> UserOut:
    """把"User 行 + user_models 表"折成 UserOut。全项目唯一组装点，别在端点里各拼一遍。

    `llm_configured` 要 key 与路由**同时**有值：只填一半的人问起来拿到的是上游 401，
    而我们连"你没配全"都说不出口——那不如在设置这一步就拦住（spec 3.4）。
    """
    rows = db.list_user_models(user.id)
    return UserOut(
        id=user.id, identifier=user.identifier, identifier_type=user.identifier_type,
        nickname=user.nickname, avatar=user.avatar,
        llm_configured=bool(user.api_key and user.base_url),
        llm_base_url=user.base_url or "",
        api_key_masked=mask_api_key(user.api_key),
        models=[name for name, _ in rows],
        default_model=default_model_of(rows),
    )


def _reload(db, user):
    """改完必须重新读一行：`user` 是 get_current_user 早先取出的快照，字段还是旧的。

    记一笔账（F5，评审 I-2）：**这一句只在真库侧有意义，离线判据抓不到它被删掉。**
    - 真库：`deps.py:50` 把 `get_user_by_token` 的返回值直接交出，而它在
      `core/database.py:582-596` 里是 `session.close()` 之后交出的 **detached 实例**——
      属性在读取那一刻冻住，写完不回读就还是旧值，所以必须重读。
    - 离线 fake：`tests/test_api_auth.py` 的 `FakeAuthDB.get_user_by_token` 与
      `get_user_by_id` 返回的是**同一个 SimpleNamespace 对象的别名**，写进去就地生效，
      重读与不重读拿到的是同一个东西 ⇒ 把 `update_me` 与 `update_llm` 两处的
      `_reload(db, user)` 退回成 `user`，离线判据一条都不会红（终审复测于 `4c45e96` 之后：
      本文件 47 条全绿。当轮报告住在被 `.gitignore` 排除的 `.superpowers/sdd/` 下，干净检出翻不到，
      所以这条实测以本注释为唯一留痕）。

    本轮按控制者裁定**不动 fake 的返回语义**（改成快照会连带推倒
    `test_half_a_config_is_not_configured_even_when_the_key_is_there`，它正靠 poke
    `db.users[0]` + 不重读这条路）。真判据已在阶段二 Task 12 的浏览器验收里兑现（判据 4：真服务上
    存真凭证，界面 `.setup-banner` 当场换句——`patchMe` 吃的就是 `PUT /me/llm` 的**响应体本身**，
    不追打 `GET /me`；同轮 `/api/auth/me` 回 `llm_configured: true`）。所以别把这里当多余代码顺手删。
    """
    return db.get_user_by_id(user.id) or user


def _models_out(db, user) -> ModelsOut:
    rows = db.list_user_models(user.id)
    return ModelsOut(models=[name for name, _ in rows], default_model=default_model_of(rows))


def _issue(db, config, user) -> AuthOut:
    token = new_token()
    db.create_token(user_id=user.id, token_hash=hash_token(token),
                    expires_at=datetime.now() + timedelta(days=config.AUTH_TOKEN_TTL_DAYS))
    return AuthOut(token=token, user=_user_out(db, user), session_id=str(uuid.uuid4()))


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
def me(db=Depends(get_db), user=Depends(get_current_user)):
    return MeOut(user=_user_out(db, user))


@router.put("/me", response_model=MeOut)
def update_me(payload: ProfileIn, db=Depends(get_db), user=Depends(get_current_user)):
    nickname = payload.nickname.strip() if payload.nickname is not None else None
    if payload.nickname is not None and not nickname:
        raise HTTPException(status_code=422, detail="昵称不能是空白")
    if payload.avatar is not None and payload.avatar not in AVATARS:
        # 头像走预设白名单（决策 5）：这一列不是图片 URL，随便存一串只会让
        # 前端渲染出一个空的 .rail-avatar
        raise HTTPException(status_code=422, detail="头像不在预设里")
    db.update_user_profile(user.id, nickname=nickname, avatar=payload.avatar)
    return MeOut(user=_user_out(db, _reload(db, user)))


@router.put("/me/password", status_code=204)
def update_password(payload: PasswordIn, db=Depends(get_db), user=Depends(get_current_user)):
    # 已经过 get_current_user 的门，这里回"原密码不正确"不泄露账号存在性，只防"捡到一枚还没过期的令牌"的人改密码
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(status_code=401, detail="原密码不正确")
    db.update_user_password(user.id, hash_password(payload.new_password))
    return None


@router.put("/me/llm", response_model=MeOut)
def update_llm(payload: LlmIn, db=Depends(get_db), user=Depends(get_current_user)):
    # 与上面昵称、下面模型名同层同风格的一条规矩：只拦"空白伪装成有值"这一格。
    # 两格在 `LlmIn` 里已经 strip 过、长度也量在 strip 之后，所以到这里的值要么是干净串、
    # 要么是空串——不再有「8 格空白过了 schema、strip 成空串写进库」那条路。
    # 空串这一格仍要在写库之前拦住：响应用户看到的是 200「保存成功」而 `llm_configured` 是
    # False、掩码是空串，Task 7 的 409 门禁再把他挡在门外且界面说不出原因（最难查的那种谎）。
    # 它没并进 schema 的 8~255 那条，是因为这里能给出一句话的 detail，而 pydantic 给的是数组。
    if not payload.api_key:
        raise HTTPException(status_code=422, detail="api_key 不能是空白")
    db.update_user_llm(user.id, payload.api_key, payload.base_url)
    return MeOut(user=_user_out(db, _reload(db, user)))


@router.post("/me/models", response_model=ModelsOut)
def add_model(payload: ModelIn, db=Depends(get_db), user=Depends(get_current_user)):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="模型名不能是空白")
    if not db.add_user_model(user.id, name):
        raise HTTPException(status_code=409, detail="该模型已在你的名单里")
    return _models_out(db, user)


# `{name:path}`：默认那段 `[^/]+` 匹配不上带斜杠的名字，而 `%2F` 到 ASGI 已被解回 `/`——
# 「厂商/模型」这种 id（OpenRouter 一类网关）加得进去却删不掉。见 test_a_model_name_with_a_slash_is_still_deletable。
@router.delete("/me/models/{name:path}", response_model=ModelsOut)
def remove_model(name: str, db=Depends(get_db), user=Depends(get_current_user)):
    db.delete_user_model(user.id, name)
    return _models_out(db, user)


@router.put("/me/models/default", response_model=ModelsOut)
def set_default_model(payload: ModelIn, db=Depends(get_db), user=Depends(get_current_user)):
    if not db.set_default_user_model(user.id, payload.name.strip()):
        raise HTTPException(status_code=409, detail=MODEL_NOT_IN_LIST)
    return _models_out(db, user)
