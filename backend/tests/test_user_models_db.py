"""阶段二两张账号侧结构的离线钉。

真库上的读写归 test_live_database.py（要 MySQL），这里只钉"形状本身"：
列可不可空、列的长度上界、unique 键**盖住哪几列**——这三个都是**建表之后改不动**的事实，
错了就得删表重来，所以值得一条不连库的判据。
`Base.metadata` 是纯声明，导入它不开连接。
"""
from sqlalchemy import UniqueConstraint

from core import migrations
from core.database import Base, User, UserModel


def test_user_llm_columns_exist_and_are_nullable():
    cols = Base.metadata.tables["users"].columns
    assert {"api_key", "base_url"} <= set(cols.keys())
    # 可空是硬要求：老库里已有账号还没配 key，NOT NULL 会让 ALTER 当场失败
    assert cols["api_key"].nullable is True and cols["base_url"].nullable is True
    # 长度上界也钉：这两列**已部署的库**上只能靠 ALTER 补（create_all 对已存在的表整表跳过），
    # 所以 ORM 声明的 255/500 必须与 core/migrations.py 的 VARCHAR(255)/VARCHAR(500) 同源。
    # 现在拆成两句而不是一句 and：失败时能直接看出是哪一格漂了。
    assert cols["api_key"].type.length == 255
    assert cols["base_url"].type.length == 500
    # 同源的第二半：DDL 串里的数字逐字等于 ORM 声明的长度。
    # 只钉 ORM 一侧，未来有人单独改 ALTER（或反过来）就分叉；这条 pin 就是那条分叉的报警。
    ddl = {(table, column): ddl_type for (table, column, ddl_type) in migrations.MIGRATED_COLUMNS}
    assert ddl[("users", "api_key")] == f"VARCHAR({cols['api_key'].type.length})"
    assert ddl[("users", "base_url")] == f"VARCHAR({cols['base_url'].type.length})"


def test_user_model_table_shape():
    table = Base.metadata.tables["user_models"]
    assert table.columns["name"].type.length == 100      # 对齐 ChatRequest.model_name 的 1..100
    assert table.columns["is_default"].nullable is False  # 读侧 next(... if is_default) 不吃 None
    # 判据必须问"盖住哪几列"，不能只问"存不存在"：把 __table_args__ 写成 UniqueConstraint('name')
    # 上面那句照样绿，而后果是**全局**唯一 ⇒ 两个用户不能都加 gpt-4，第二个拿 409，
    # per-user 名单的语义整个塌掉。
    uqs = [sorted(c.name for c in col.columns) for col in table.constraints
           if isinstance(col, UniqueConstraint)]
    assert ["name", "user_id"] in uqs, \
        "没有 unique(user_id, name) 就能重复添加同一个模型，端点的 409 无从谈起"


def test_column_names_match_what_endpoints_read():
    # 名字是契约：拼错的列名在 MySQL 上是 1054 未知列，在 ORM 上是 AttributeError
    assert User.__tablename__ == "users"
    assert UserModel.__tablename__ == "user_models"
    assert [c.name for c in UserModel.__table__.primary_key.columns] == ["id"]
