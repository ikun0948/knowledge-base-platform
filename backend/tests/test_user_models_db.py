"""阶段二两张账号侧结构的离线钉。

真库上的读写归 test_live_database.py（要 MySQL），这里只钉"形状本身"：
列可不可空、name 的长度上界、unique 键在不在——这三个都是**建表之后改不动**的事实，
错了就得删表重来，所以值得一条不连库的判据。
`Base.metadata` 是纯声明，导入它不开连接。
"""
from sqlalchemy import UniqueConstraint

from core.database import Base, User, UserModel


def test_user_llm_columns_exist_and_are_nullable():
    cols = Base.metadata.tables["users"].columns
    assert {"api_key", "base_url"} <= set(cols.keys())
    # 可空是硬要求：老库里已有账号还没配 key，NOT NULL 会让 ALTER 当场失败
    assert cols["api_key"].nullable is True and cols["base_url"].nullable is True


def test_user_model_table_shape():
    table = Base.metadata.tables["user_models"]
    assert table.columns["name"].type.length == 100      # 对齐 ChatRequest.model_name 的 1..100
    assert table.columns["is_default"].nullable is False  # 读侧 next(... if is_default) 不吃 None
    assert any(isinstance(c, UniqueConstraint) for c in table.constraints), \
        "没有 unique(user_id, name) 就能重复添加同一个模型，端点的 409 无从谈起"


def test_column_names_match_what_endpoints_read():
    # 名字是契约：拼错的列名在 MySQL 上是 1054 未知列，在 ORM 上是 AttributeError
    assert User.__tablename__ == "users"
    assert UserModel.__tablename__ == "user_models"
    assert [c.name for c in UserModel.__table__.primary_key.columns] == ["id"]
