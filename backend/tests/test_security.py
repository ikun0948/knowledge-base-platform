"""口令哈希与会话令牌的四条纪律：可验回、盐随机、时序恒定、库里不留原文。

这一段不碰 HTTP，也不连真实 MySQL：表形状读的是 ORM 元数据，账号/会话那几条确实要建
引擎，但那是 monkeypatch 喂进 DatabaseManager 的 sqlite 临时库——documents.content 是
MySQL 方言的 MEDIUMTEXT，sqlite 编译不出来，所以逐表 create 而不走 create_all。
pbkdf2 的迭代数与令牌的形状是"数据泄露后还剩多少防线"的那条线，值得单独钉住，
而不是混在端点测里靠 mock 演一遍。
"""
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import create_engine

from core.security import hash_password, hash_token, new_token, verify_password


def test_password_round_trips_and_is_not_the_plaintext():
    stored = hash_password("hunter2-pass")
    assert verify_password("hunter2-pass", stored) is True
    assert verify_password("hunter2-pas", stored) is False
    assert stored != "hunter2-pass"
    assert "hunter2" not in stored


def test_same_password_hashes_differ_each_time():
    # 盐必须随机：两条相同口令的哈希一样，等于把"谁和谁口令相同"写进了库里
    assert hash_password("same-pass") != hash_password("same-pass")


def test_malformed_stored_hash_reports_false_not_raises():
    # 库里被手改过一行不该让登录接口 500：边界只在这四个 split 结果上
    for junk in ["", "not-a-hash", "pbkdf2_sha256$abc$00$00", "sha512$1000$00$00"]:
        assert verify_password("whatever", junk) is False


def test_hash_is_slow_enough_to_be_a_real_barrier():
    # 390k 次迭代不是玄学：单次哈希必须 ≥ 100ms，否则拖库者一秒能枚举上万次
    start = time.perf_counter()
    hash_password("timing-probe")
    assert time.perf_counter() - start >= 0.1


def test_token_is_url_safe_and_stored_only_as_sha256_hex():
    token = new_token()
    assert len(token) >= 32 and token != new_token()
    digest = hash_token(token)
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)
    assert digest == hash_token(token)  # 同输入同输出：查表靠的就是这一点


def test_new_token_is_exactly_43_characters():
    """令牌长度是 43，不是"至少 32"：secrets.token_urlsafe(32) = 32 字节 → 43 个字符。

    只写 len(token) >= 32 的话，改成 token_urlsafe(24) 照样绿，而熵实打实地少了 8 字节——
    令牌就是凭证原文，长度是它唯一的暴力上界（spec 4 节）。
    """
    assert len(new_token()) == 43


def test_stored_hash_keeps_its_documented_shape():
    """存储格式 pbkdf2_sha256$390000$<salt 32 位 hex>$<digest 64 位 hex> 本身就是契约。

    只断言"能验回"拦不住格式漂移：verify_password 的盐是从存储串里解出来的，
    把 hash_password 的盐长改短之后新行照样自洽、套件全绿，可这条串已经不是
    文档里那条串了——形状要有独立的钉子，才有人会在改成 48 位 hex 时看见红。
    """
    fields = hash_password("shape-probe").split("$")
    assert len(fields) == 4
    assert fields[0] == "pbkdf2_sha256"
    assert int(fields[1]) == 390000
    assert len(fields[2]) == 32  # 16 字节的盐，hex 后 32 字符
    assert len(fields[3]) == 64  # sha256 摘要，hex 后 64 字符


from core import database
from core.database import AuthToken, DatabaseManager, Document, User


def test_documents_user_column_is_a_nullable_foreign_key():
    """可空是迁移的前提：旧行在被认领之前就是没有归属，NOT NULL 会让 ALTER 直接失败。"""
    column = Document.__table__.c.user_id
    assert column.nullable is True
    assert [fk.target_fullname for fk in column.foreign_keys] == ["users.id"]
    # 这条钉的是 ORM 元数据（建表蓝图），不是已部署库的 schema：真库上有没有这个索引
    # 由迁移/DDL 决定，这里变绿不代表线上那条索引存在。
    assert "idx_documents_user_id" in {ix.name for ix in Document.__table__.indexes}


def test_users_and_tokens_shapes():
    assert User.__table__.c.identifier.unique is True
    assert User.__table__.c.identifier_type.nullable is False
    assert User.__table__.c.password_hash.nullable is False
    # 默认值钉在列上，不在端点里补：漏一个调用方就会写进一个空 avatar
    assert User.__table__.c.avatar.default.arg == "auto"

    token = AuthToken.__table__
    assert token.c.token_hash.unique is True
    assert token.c.expires_at.nullable is False
    assert [fk.target_fullname for fk in token.c.user_id.foreign_keys] == ["users.id"]
    assert "idx_tokens_user_id" in {ix.name for ix in token.indexes}


CFG = SimpleNamespace(MYSQL_USER="u", MYSQL_PASSWORD="p", MYSQL_HOST="localhost",
                      MYSQL_PORT=3306, MYSQL_DATABASE="mydb")


def test_create_user_returns_a_row_readable_after_the_session_closes(monkeypatch, tmp_path):
    """返回的行必须读得出 id：Task 2 的 /register 要在会话之外把它拼进响应。

    这个 bug 与用哪个库无关：sessionmaker 默认 expire_on_commit=True，commit() 把实例属性
    全标记成过期，方法里 finally 的 close() 再把对象摘出会话——此后读 user.id 就是
    DetachedInstanceError。修法是在会话还开着的时候 refresh()。这条用例就是那层门：
    谁哪天把 refresh() 删了，这里立刻红。
    sqlite 只建 users 表：users/auth_tokens 都是普通列，而 documents.content 是 MySQL 方言的
    MEDIUMTEXT，sqlite 编译不出来，所以绕开 Base.metadata.create_all。
    """
    engine = create_engine(f"sqlite:///{(tmp_path / 'users.db').as_posix()}")
    monkeypatch.setattr(database, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(database.Base.metadata, "create_all",
                        lambda bind: User.__table__.create(bind))
    db = DatabaseManager(CFG)  # 走真构造：sessionmaker 保持 expire_on_commit 默认值

    stored = hash_password("pw")
    user = db.create_user("a@b.com", "email", "小A", stored)

    # 三个都是普通列，读它们不需要会话：这里任何一项抛 DetachedInstanceError 都算红
    assert user.id is not None
    assert user.identifier == "a@b.com"
    assert user.nickname == "小A"
    # id 得是真自增值而不是"过期对象侥幸没炸"：第二条不该和第一条撞车
    second = db.create_user("c@d.com", "email", "小C", stored)
    assert second.id != user.id
    assert db.get_user_by_identifier("a@b.com").id == user.id


def test_create_token_returns_a_row_readable_after_the_session_closes(monkeypatch, tmp_path):
    """令牌行也要在会话之外读得出 id：Task 2 的 /login 就靠它拼响应。

    与上一条同一个前提（expire_on_commit=True + finally close() → DetachedInstanceError），
    只不过对象换成了 auth_tokens 那一行。round 1 只给 users 建了门，create_token 里的
    refresh() 当时没有任何测试覆盖——删了它整套件仍全绿，这条就是补上的那层门。
    这里两张表都建：auth_tokens.user_id 指向 users.id，令牌只存哈希、原文不进库。
    """
    engine = create_engine(f"sqlite:///{(tmp_path / 'tokens.db').as_posix()}")
    monkeypatch.setattr(database, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(
        database.Base.metadata, "create_all",
        lambda bind: [table.create(bind) for table in (User.__table__, AuthToken.__table__)])
    db = DatabaseManager(CFG)  # 走真构造：sessionmaker 保持 expire_on_commit 默认值

    user = db.create_user("t@b.com", "email", "小T", hash_password("pw"))
    digest = hash_token(new_token())
    row = db.create_token(user.id, digest, datetime.now() + timedelta(days=7))

    # 三个都是普通列：close() 之后任何一项抛 DetachedInstanceError 都算红
    assert row.id is not None
    assert row.token_hash == digest
    assert row.user_id == user.id
    second = db.create_token(user.id, hash_token(new_token()), datetime.now() + timedelta(days=7))
    assert second.id != row.id
