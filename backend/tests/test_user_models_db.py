"""阶段二两张账号侧结构的离线钉。

真库上的读写归 test_live_database.py（要 MySQL），这里只钉"形状本身"：
列可不可空、列的长度上界、unique 键**盖住哪几列**、⑤ 那枚生成列与唯一索引盖住哪一列——
这些都是**建表之后改不动**的事实，错了就得删表重来，所以值得一条不连库的判据。
最后一组尤其值得：那条缺陷的内容就是"至多一枚默认只靠应用层两步"，
判据要盯的是**约束真的落在列上**，而不是代码里记得写那句 WHERE。
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


def test_user_models_guard_column_is_a_stored_generated_one():
    """「至多一枚默认」从这一条起由**引擎**兜着（阶段三 ⑤），不再只靠应用层两步。

    MySQL 没有部分索引（`WHERE is_default` 那种写法建不出来），所以口径换成生成列：
    `default_guard` 只在 `is_default` 为真时等于 `user_id`，否则是 NULL——唯一索引**不管 NULL**，
    于是"同一用户可以有任意多枚非默认行"与"每人至多一枚默认"这两件事同时成立。

    为什么判据要问"是不是生成列"：普通列由应用自己写，写不写全凭自觉，
    给它加唯一索引等于把不变量交回给同一份应用层代码——也就是这条缺陷的本体。
    """
    col = Base.metadata.tables["user_models"].columns["default_guard"]
    assert col.computed is not None, "default_guard 必须是生成列；普通列上的唯一索引拦不住写 NULL 的人"
    assert col.computed.persisted is True, (
        "STORED 才是本机实测过的那条路（VIRTUAL 也能建索引，但换口径要重跑 live 组）")
    # 可空是硬要求：非默认行拿到的是 NULL，NOT NULL 会让"第二枚模型"根本插不进去
    assert col.nullable is True
    # 同源两条腿：新库由 create_all 按 ORM 建、老库由迁移发 ALTER。
    # 两处各写一句表达式就会分叉，而分叉的后果是"索引管的是另一件事"——这里逐字比。
    assert str(col.computed.sqltext) == migrations.SINGLE_DEFAULT_GUARD_EXPR, (
        "ORM 的生成表达式与 core/migrations.py 的常量不是同一句话")


def test_user_models_guard_index_covers_only_the_generated_column():
    """索引**盖住哪几列**才是判据，"存在一枚唯一索引"不是。

    写成 `unique(default_guard, user_id)` 照样建得出来、照样绿，但它管的是
    "(user_id, 默认位) 组合"——每个用户仍能有任意多枚默认，因为那些行的 guard 是 NULL。
    多盖一列就等于没有约束，与 `test_user_model_table_shape` 那条同一个口径。
    """
    table = Base.metadata.tables["user_models"]
    _table, column, index = migrations.MIGRATED_UNIQUE_INDEXES[0]
    guard = {ix.name: ix for ix in table.indexes}[index]
    assert guard.unique is True, f"{index} 建成了普通索引：两枚默认照样并存"
    assert [c.name for c in guard.columns] == [column], (
        f"唯一索引盖住了 {[c.name for c in guard.columns]}，只该盖 {column} 这一列")
