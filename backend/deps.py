from fastapi import Depends, Request

from core.security import hash_token
from exceptions import AuthError

LOGIN_REQUIRED = "未登录或登录已过期"


def bearer_token(request: Request) -> str:
    """从 Authorization 头取 Bearer 令牌原文。不合格一律同一句 401，不说哪里不合格。"""
    raw = request.headers.get("Authorization") or ""
    scheme, _, credential = raw.partition(" ")
    if scheme.lower() != "bearer" or not credential.strip():
        raise AuthError(LOGIN_REQUIRED)
    return credential.strip()


def get_config(request: Request):
    return request.app.state.config


def get_db(request: Request):
    return request.app.state.db


def get_doc_processor(request: Request):
    return request.app.state.doc_processor


def get_vector_store(request: Request):
    return request.app.state.vector_store


def get_rag_system(request: Request):
    return request.app.state.rag_system


def get_current_user(request: Request, db=Depends(get_db)):
    """唯一那道门：令牌哈希 → auth_tokens（带有效期）→ users。

    库里只存哈希（spec 4 节），所以这里必须先把原文算一遍再查；任一步查不到
    都只说"未登录或登录已过期"，登出与过期因此在响应上不可分辨。
    """
    user = db.get_user_by_token(hash_token(bearer_token(request)))
    if user is None:
        raise AuthError(LOGIN_REQUIRED)
    return user
