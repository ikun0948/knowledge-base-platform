"""四个认证端点的契约。三条判据是这块的全部风险：

① "账号不存在"与"密码错"必须**逐字节相同**（防枚举）；
② 库里/响应里都不许出现口令哈希原文；
③ 登出后同一枚令牌立刻换不回用户（可吊销是这套凭证形态唯一的卖点）。
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from api.auth import _DUMMY_HASH
from core.security import ALGORITHM, PBKDF2_ITERATIONS, hash_password, verify_password
from deps import get_config, get_db
from main import create_app
from schemas.auth import normalize_identifier

UUID_RE = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


class FakeAuthDB:
    def __init__(self):
        self.users = []          # SimpleNamespace 列表，字段与 ORM 行同名
        self.tokens = {}         # token_hash -> (user_id, expires_at)
        self._next_id = 1

    def create_user(self, identifier, identifier_type, nickname, password_hash, avatar="auto"):
        if any(u.identifier == identifier for u in self.users):
            raise IntegrityError("INSERT INTO users", {}, Exception("duplicate entry"))
        user = SimpleNamespace(id=self._next_id, identifier=identifier,
                               identifier_type=identifier_type, nickname=nickname,
                               avatar=avatar, password_hash=password_hash)
        self._next_id += 1
        self.users.append(user)
        return user

    def get_user_by_identifier(self, identifier):
        return next((u for u in self.users if u.identifier == identifier), None)

    def create_token(self, user_id, token_hash, expires_at):
        self.tokens[token_hash] = (user_id, expires_at)

    def get_user_by_token(self, token_hash):
        entry = self.tokens.get(token_hash)
        if entry is None or entry[1] <= datetime.now():
            return None
        return next((u for u in self.users if u.id == entry[0]), None)

    def delete_token(self, token_hash):
        return 1 if self.tokens.pop(token_hash, None) else 0


def make_client(db=None):
    db = db or FakeAuthDB()
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_config] = lambda: SimpleNamespace(AUTH_TOKEN_TTL_DAYS=30)
    return TestClient(app), db


def register(client, identifier="a@b.com", **over):
    payload = {"identifier_type": "email", "identifier": identifier, "password": "hunter2-pass", **over}
    return client.post("/api/auth/register", json=payload)


def test_register_returns_token_user_and_a_uuid_session():
    client, db = make_client()
    res = register(client)
    assert res.status_code == 201
    body = res.json()
    assert len(body["token"]) >= 32
    import re
    assert re.match(UUID_RE, body["session_id"])
    assert body["user"] == {"id": 1, "identifier": "a@b.com", "identifier_type": "email",
                            "nickname": "a", "avatar": "auto"}
    assert len(db.tokens) == 1


def test_register_lowercases_the_email_and_reuses_it_for_lookup():
    client, db = make_client()
    assert register(client, identifier="A@Example.COM").status_code == 201
    assert db.users[0].identifier == "a@example.com"
    assert client.post("/api/auth/login", json={"identifier": "a@example.com",
                                                "password": "hunter2-pass"}).status_code == 200


def test_register_nickname_defaults_and_overrides():
    client, _ = make_client()
    assert register(client, identifier="dev@team.io").json()["user"]["nickname"] == "dev"
    assert register(client, identifier="13800000001", identifier_type="phone",
                    ).json()["user"]["nickname"] == "用户0001"
    # 顶级域至少两个字母（见 test_register_rejects_malformed_email 里的 "a@b.c"），所以这里是 .zz
    assert register(client, identifier="x@y.zz", nickname="小明").json()["user"]["nickname"] == "小明"


@pytest.mark.parametrize("bad", ["a@b", "a b@c", "@b.com", "a@b.", "a@b.c", "abc.def"])
def test_register_rejects_malformed_email(bad):
    client, _ = make_client()
    assert register(client, identifier=bad).status_code == 422


@pytest.mark.parametrize("bad", ["12345678901", "1380000000", "138000000012", "23800000001", "1380000000a"])
def test_register_rejects_malformed_phone(bad):
    client, _ = make_client()
    assert register(client, identifier=bad, identifier_type="phone").status_code == 422


def test_register_rejects_short_password_and_unknown_type():
    client, _ = make_client()
    assert register(client, password="12345").status_code == 422
    assert register(client, identifier_type="username").status_code == 422


def test_empty_password_is_rejected_before_any_hash_comparison():
    """`hash_password("")` 是一枚**可验证通过**的合法哈希（core/security.py 不判空串），
    空口令这道门只能在 schema 的 min_length 上。这里钉的是门真的在：账号存在也照样 422。"""
    client, _ = make_client()
    register(client)
    assert register(client, identifier="fresh@b.com", password="").status_code == 422
    res = client.post("/api/auth/login", json={"identifier": "a@b.com", "password": ""})
    assert res.status_code == 422


def test_normalize_identifier_is_pure_and_raises_value_error():
    """422 的中文文案就是从这两个 ValueError 来的，所以它们得能单独验。"""
    assert normalize_identifier("email", "  A@B.com  ") == "a@b.com"
    assert normalize_identifier("phone", "13800000001") == "13800000001"
    with pytest.raises(ValueError):
        normalize_identifier("email", "nope")
    with pytest.raises(ValueError):
        normalize_identifier("phone", "12345678901")


def test_duplicate_register_is_409_with_one_chinese_line():
    client, _ = make_client()
    assert register(client).status_code == 201
    res = register(client)
    assert res.status_code == 409
    assert res.json() == {"detail": "该账号已注册"}


def test_login_mints_a_new_session_id_every_time():
    client, _ = make_client()
    register(client)
    first = client.post("/api/auth/login", json={"identifier": "a@b.com",
                                                 "password": "hunter2-pass"}).json()
    second = client.post("/api/auth/login", json={"identifier": "a@b.com",
                                                  "password": "hunter2-pass"}).json()
    assert first["token"] != second["token"]
    # 需求 2 的正面：重新登录 = 新对话 id
    assert first["session_id"] != second["session_id"]


def test_wrong_password_is_401():
    client, _ = make_client()
    register(client)
    res = client.post("/api/auth/login", json={"identifier": "a@b.com", "password": "wrong-pass"})
    assert res.status_code == 401
    assert res.json() == {"detail": "账号或密码不正确"}


def test_unknown_account_and_wrong_password_are_byte_identical():
    """防枚举钉的是**响应本身**，不是文案：状态码、字节串、长度三样都得一样。"""
    client, _ = make_client()
    register(client)
    known = client.post("/api/auth/login", json={"identifier": "a@b.com", "password": "wrong-pass"})
    unknown = client.post("/api/auth/login", json={"identifier": "nobody@b.com", "password": "wrong-pass"})
    assert unknown.status_code == known.status_code == 401
    assert unknown.content == known.content


def test_dummy_hash_never_verifies_any_password():
    """垫片的另一半判据是**恒假**：它那 64 个 0 的摘要不可能被任何口令算出来。

    这条不是洁癖——`login` 里 `user is None` 那道滤条件一旦被人去掉或写反，
    垫片就是唯一的门；而它要是在某个口令上返回 True，未知账号就登录成功了。
    """
    for password in ("", "hunter2-pass", "wrong-pass", "0" * 32, "0" * 64, "pbkdf2_sha256"):
        assert verify_password(password, _DUMMY_HASH) is False, "垫片被验过了：未知账号会登录成功"


def test_dummy_hash_is_the_same_shape_and_cost_as_a_real_row():
    """耗时面的钉子：`verify_password` 的迭代数取自 stored 串自己（core/security.py:30）。

    所以垫片写成 `…$1000$…` 时"没这个账号"只算 1000 轮、"密码错"算 390000 轮，
    实测差约 200 倍——注释里那句"不可分辨"就是假话。这条钉住四段形状与迭代数同价，
    谁再把它改回小数字就撞红。
    """
    dummy = _DUMMY_HASH.split("$")
    real = hash_password("shape-probe").split("$")
    assert len(dummy) == 4
    assert dummy[0] == real[0] == ALGORITHM
    assert dummy[1] == real[1] == str(PBKDF2_ITERATIONS)
    assert len(dummy[2]) == len(real[2]) == 32
    assert len(dummy[3]) == len(real[3]) == 64
    assert bytes.fromhex(dummy[2]) and bytes.fromhex(dummy[3]), "hex 段解不开就等于验时静默 False"


def test_me_returns_the_user_and_never_the_password_hash():
    client, db = make_client()
    token = register(client).json()["token"]
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["user"]["identifier"] == "a@b.com"
    assert "password_hash" not in res.text
    assert db.users[0].password_hash not in res.text


@pytest.mark.parametrize("header", [
    None,
    {},
    {"Authorization": ""},
    {"Authorization": "token abc"},          # scheme 不是 Bearer
    {"Authorization": "Bearer "},            # 有 scheme 没凭证
    {"Authorization": "Bearer not-in-db"},   # 真令牌但库里没有
], ids=["none", "empty-dict", "blank", "wrong-scheme", "no-credential", "unknown-token"])
def test_me_rejects_every_kind_of_missing_credential_the_same_way(header):
    client, _ = make_client()
    res = client.get("/api/auth/me", headers=header or {})
    assert res.status_code == 401
    assert res.json() == {"detail": "未登录或登录已过期"}


def test_expired_token_is_rejected_without_deleting_anything():
    """过期靠 expires_at 判定，不靠后台清扫：30 天不动的令牌躺在库里也换不到东西。"""
    client, db = make_client()
    token = register(client).json()["token"]
    from core.security import hash_token
    user_id, _ = db.tokens[hash_token(token)]
    db.tokens[hash_token(token)] = (user_id, datetime.now() - timedelta(seconds=1))
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    assert len(db.tokens) == 1, "过期不是删除：这条只认 expires_at 那道滤条件"


def test_logout_revokes_the_same_token_immediately():
    client, _ = make_client()
    token = register(client).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.post("/api/auth/logout", headers=headers).status_code == 401


def test_logout_revokes_only_the_token_in_hand():
    """同一用户多枚令牌并存时，登出只吊销手里这枚。

    今天 `logout` 吊销的是**手里那枚令牌原文**的哈希、`delete_token` 只按 token_hash 过滤，这是对
    的；但"改成按 user_id 清掉全部会话"（很常见的需求变更）今天撞不红任何测。这条同时钉住
    两件事：多登录不互踢（产品语义），以及吊销的粒度是**一枚票**而不是一个账号。
    """
    client, db = make_client()
    first = register(client).json()["token"]
    second = client.post("/api/auth/login", json={"identifier": "a@b.com",
                                                  "password": "hunter2-pass"}).json()["token"]
    assert first != second
    assert len(db.tokens) == 2, "两次登录各自留一行：谁也不踢谁"
    assert client.post("/api/auth/logout",
                       headers={"Authorization": f"Bearer {second}"}).status_code == 204
    assert client.get("/api/auth/me",
                      headers={"Authorization": f"Bearer {second}"}).status_code == 401
    kept = client.get("/api/auth/me", headers={"Authorization": f"Bearer {first}"})
    assert kept.status_code == 200
    assert kept.json()["user"]["identifier"] == "a@b.com"
    assert len(db.tokens) == 1, "登出不该把没交出来的那枚一起清掉"

    # 204 是**空体且不带 content-type**：光钉状态码挡不住 Task 7 在 logout 里 .json()——
    # 那会当场 SyntaxError。与 200 那格并排钉，形状差才是前端要拿到的事实。
    gone = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {first}"})
    assert gone.status_code == 204
    assert gone.content == b""
    assert "content-type" not in gone.headers
    assert kept.content != b"" and "content-type" in kept.headers


def test_logout_without_a_token_is_401_not_silently_ok():
    client, _ = make_client()
    assert client.post("/api/auth/logout").status_code == 401
