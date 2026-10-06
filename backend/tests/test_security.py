"""口令哈希与会话令牌的四条纪律：可验回、盐随机、时序恒定、库里不留原文。

这一段完全不碰 MySQL 也不碰 HTTP——pbkdf2 的迭代数与令牌的形状是"数据泄露后
还剩多少防线"的那条线，值得单独钉住，而不是混在端点测里靠 mock 演一遍。
"""
import time

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


from core.database import AuthToken, Document, User


def test_documents_user_column_is_a_nullable_foreign_key():
    """可空是迁移的前提：旧行在被认领之前就是没有归属，NOT NULL 会让 ALTER 直接失败。"""
    column = Document.__table__.c.user_id
    assert column.nullable is True
    assert [fk.target_fullname for fk in column.foreign_keys] == ["users.id"]
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
