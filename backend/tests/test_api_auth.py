"""四个认证端点的契约。三条判据是这块的全部风险：

① "账号不存在"与"密码错"必须**逐字节相同**（防枚举）；
② 库里/响应里都不许出现口令哈希原文；
③ 登出后同一枚令牌立刻换不回用户（可吊销是这套凭证形态唯一的卖点）。
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from urllib.parse import quote

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
        self.models = {}         # user_id -> [(name, is_default)]，与 list_user_models 同形状
        self._next_id = 1

    def create_user(self, identifier, identifier_type, nickname, password_hash, avatar="auto"):
        if any(u.identifier == identifier for u in self.users):
            raise IntegrityError("INSERT INTO users", {}, Exception("duplicate entry"))
        user = SimpleNamespace(id=self._next_id, identifier=identifier,
                               identifier_type=identifier_type, nickname=nickname,
                               avatar=avatar, password_hash=password_hash,
                               # 与 ORM 行同名同初值：新注册的人还没配 key
                               api_key=None, base_url=None)
        self._next_id += 1
        self.users.append(user)
        return user

    def get_user_by_identifier(self, identifier):
        return next((u for u in self.users if u.identifier == identifier), None)

    def create_token(self, user_id, token_hash, expires_at):
        self.tokens[token_hash] = (user_id, expires_at)

    def get_user_by_token(self, token_hash):
        """返回 `self.users` 里那个对象**本身**（别名，不是快照）。

        真库交出的不是这一个对象，而是会话已关闭的 detached 实例
        （core/database.py:582-596），属性在取出那一刻冻住，所以端点改完必须回读。
        fake 给的是别名，写进去就地生效 ⇒ `api/auth.py` 的 `_reload` 在这里观察不到
        （把它退回成直接用 `user`，本文件 47 条判据全绿——终审复测于 `4c45e96` 之后。当轮报告住在被
        `.gitignore` 排除的 `.superpowers/sdd/` 下，干净检出翻不到，故这条实测以本注释为唯一留痕）。
        本轮按裁定不改这个语义；真判据已由阶段二 Task 12 的判据 4 兑现（真服务 + 真凭证存完 key 后
        界面横幅当场换句，而那次换句用的就是 `PUT /me/llm` 响应体本身，不是追打的 `GET /me`）。
        """
        entry = self.tokens.get(token_hash)
        if entry is None or entry[1] <= datetime.now():
            return None
        return next((u for u in self.users if u.id == entry[0]), None)

    def delete_token(self, token_hash):
        return 1 if self.tokens.pop(token_hash, None) else 0

    # ---------- 阶段二：设置类方法（与 DatabaseManager 同名同返回形状）----------

    def update_user_profile(self, user_id, nickname=None, avatar=None):
        user = self.get_user_by_id(user_id)
        if nickname is not None:
            user.nickname = nickname
        if avatar is not None:
            user.avatar = avatar
        return 1

    def update_user_password(self, user_id, password_hash):
        self.get_user_by_id(user_id).password_hash = password_hash
        return 1

    def update_user_llm(self, user_id, api_key, base_url):
        user = self.get_user_by_id(user_id)
        user.api_key, user.base_url = api_key, base_url
        return 1

    def get_user_by_id(self, user_id):
        # 别名：返回的就是 get_user_by_token 交出去的那个对象本身（不是快照），
        # 所以 `_reload` 在这里观察不到——两种形态的差别见 get_user_by_token 的 docstring。
        return next((u for u in self.users if u.id == user_id), None)

    def list_user_models(self, user_id):
        return list(self.models.get(user_id, []))

    def add_user_model(self, user_id, name):
        rows = self.models.setdefault(user_id, [])
        if (name, False) in rows or (name, True) in rows:
            return False
        rows.append((name, not rows))     # 第一个自动成为默认
        return True

    def delete_user_model(self, user_id, name):
        rows = self.models.setdefault(user_id, [])
        before = len(rows)
        self.models[user_id] = [r for r in rows if r[0] != name]
        return before - len(self.models[user_id])

    def set_default_user_model(self, user_id, name):
        rows = self.models.setdefault(user_id, [])
        if not any(n == name for n, _ in rows):
            return False
        self.models[user_id] = [(n, n == name) for n, _ in rows]
        return True


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
                            "nickname": "a", "avatar": "auto", "llm_configured": False,
                            "llm_base_url": "", "api_key_masked": "", "models": [],
                            "default_model": None}
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

    # 实测形状：204 的 body 是空的，但 FastAPI 的默认响应类**照样给它挂了
    # content-type: application/json**。所以前端判"要不要 .json()"只能看 204 这个状态码，
    # 看头会当场 SyntaxError。这里把头在场一起钉住：哪天框架把它清干净了这条会红，届时改判。
    gone = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {first}"})
    assert gone.status_code == 204
    assert gone.content == b""
    assert gone.headers.get("content-type") == "application/json"
    assert kept.content != b"" and kept.headers.get("content-type") == "application/json"


def test_logout_without_a_token_is_401_not_silently_ok():
    client, _ = make_client()
    assert client.post("/api/auth/logout").status_code == 401


# ---------- 阶段二 Task 2：六个设置类端点 + UserOut 的十键 ----------


def _login_llm_client(identifier="a@b.com"):
    """注册并登录，返回 (client, db, token)。设置类端点都要带 Bearer 头。"""
    client, db = make_client()
    register(client, identifier=identifier)
    token = client.post("/api/auth/login", json={
        "identifier": identifier, "password": "hunter2-pass"}).json()["token"]
    return client, db, {"Authorization": f"Bearer {token}"}


def test_me_returns_the_five_new_keys_without_the_raw_key():
    client, db, headers = _login_llm_client()
    client.put("/api/auth/me/llm", json={"api_key": "sk-abcdef1234567890",
                                         "base_url": "https://vLLM.internal/v1"}, headers=headers)
    user = client.get("/api/auth/me", headers=headers).json()["user"]
    assert user["llm_configured"] is True
    assert user["llm_base_url"] == "https://vLLM.internal/v1"
    # 掩码口径（spec 3.1）：sk- 前缀 + 尾 4 位，中间一律 ****
    assert user["api_key_masked"] == "sk-****7890"
    assert "abcdef" not in client.get("/api/auth/me", headers=headers).text
    assert user["models"] == [] and user["default_model"] is None


def test_llm_config_requires_both_key_and_base_url():
    client, _, headers = _login_llm_client()
    assert client.put("/api/auth/me/llm", json={"api_key": "sk-x", "base_url": ""},
                      headers=headers).status_code == 422
    # 只填一半不算配置：llm_configured 必须 False，否则 409 门禁形同虚设
    assert client.get("/api/auth/me", headers=headers).json()["user"]["llm_configured"] is False


def test_profile_update_changes_nickname_and_avatar():
    client, _, headers = _login_llm_client()
    res = client.put("/api/auth/me", json={"nickname": "小明", "avatar": "🤖"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["user"]["nickname"] == "小明"
    assert res.json()["user"]["avatar"] == "🤖"
    # 预设白名单外的一律 422（Step 4 的 AVATARS 分支）：这列不是图片 URL，存进去前端渲染不出
    assert client.put("/api/auth/me", json={"avatar": "<script>"}, headers=headers).status_code == 422
    # 只传头像时昵称不许被清掉：update_user_profile 是"只改传了的格子"
    assert client.put("/api/auth/me", json={"avatar": "🦊"}, headers=headers
                      ).json()["user"]["nickname"] == "小明"
    # 空 body（两格都没传）不算更新：422 比 200 但什么都没变更诚实
    assert client.put("/api/auth/me", json={}, headers=headers).status_code == 422
    # 昵称上界 50 对齐 users.nickname 的 String(50)，超了必须 422 而不是被 MySQL 切掉
    assert client.put("/api/auth/me", json={"nickname": "字" * 51}, headers=headers).status_code == 422
    # 反方向（F3 补网）：上面只钉了"只传头像不清昵称"，这一句钉"只传昵称不清头像"。
    # fake 侧写丢 `if avatar is not None` 会被 UserOut.avatar: str 的构造校验炸成 500 而间接红；
    # 真库侧（core/database.py 的 fields 只收非 None）写丢则是**无声**把头像列刷掉，
    # 而现在没有任何判据走这条路 ⇒ 这一格写丢时本轮之前的 43 条判据全绿。这里先把头像立成 🤖 再只传昵称。
    assert client.put("/api/auth/me", json={"avatar": "🤖"}, headers=headers).status_code == 200
    mirrored = client.put("/api/auth/me", json={"nickname": "小红"}, headers=headers).json()["user"]
    assert mirrored["nickname"] == "小红"
    assert mirrored["avatar"] == "🤖", "只传昵称把头像那一格洗掉了"


def test_password_change_requires_the_old_one():
    client, db, headers = _login_llm_client()
    # F4：原来是 `db.users[0].password_hash != "brand-new-pass"`（brief 逐字那句）——新哈希
    # 恒不等于明文，这条排得掉的只有"存了明文"，排不掉"根本没写库/写错了列"。改成先存旧哈希再判三件事。
    before_hash = db.users[0].password_hash
    assert client.put("/api/auth/me/password", json={"old_password": "wrong-pass",
                                                     "new_password": "brand-new-pass"},
                      headers=headers).status_code == 401
    assert db.users[0].password_hash == before_hash, "旧口令错了也不许写库：这一格被改了就是先写后判"
    assert client.put("/api/auth/me/password", json={"old_password": "hunter2-pass",
                                                     "new_password": "brand-new-pass"},
                      headers=headers).status_code == 204
    after_hash = db.users[0].password_hash
    assert after_hash != before_hash, "哈希没变：这一步根本没写进库"
    assert after_hash != "brand-new-pass", "库里存的是明文"
    fresh = client.post("/api/auth/login", json={"identifier": "a@b.com",
                                                 "password": "brand-new-pass"})
    assert fresh.status_code == 200
    assert fresh.json()["token"], "新口令登录没交出令牌"
    assert client.post("/api/auth/login", json={"identifier": "a@b.com",
                                                "password": "hunter2-pass"}).status_code == 401


def test_model_list_add_default_and_delete():
    client, _, headers = _login_llm_client()
    add = lambda name: client.post("/api/auth/me/models", json={"name": name}, headers=headers)
    assert add("qwen-max").json() == {"models": ["qwen-max"], "default_model": "qwen-max"}
    assert add("qwen-max").status_code == 409              # 重复添加
    assert add("qwen-turbo").json()["models"] == ["qwen-max", "qwen-turbo"]   # 添加顺序就是名单顺序
    # 第一个进来的人自动是默认：没有这一步的话用户配完 key 仍会撞"名单为空"以外的第三条 409
    assert client.put("/api/auth/me/models/default", json={"name": "qwen-turbo"},
                      headers=headers).json() == {"models": ["qwen-max", "qwen-turbo"],
                                                  "default_model": "qwen-turbo"}
    assert client.put("/api/auth/me/models/default", json={"name": "早删了"},
                      headers=headers).status_code == 409
    res = client.delete("/api/auth/me/models/qwen-turbo", headers=headers)
    assert res.json() == {"models": ["qwen-max"], "default_model": "qwen-max"}


def test_a_model_name_with_a_slash_is_still_deletable():
    # 带斜杠的模型名是真场景（OpenRouter 那类网关的 id 就是「厂商/模型」），前端也确实把整段
    # 名字 encodeURIComponent 之后才拼进 URL。但 `%2F` 在 ASGI 里会被解回 `/`，而默认路径参数
    # `{name}` 的正则是 `[^/]+`——那一段匹配不上就是 404：名字加得进去、删不掉，只能去库里手删。
    client, _, headers = _login_llm_client()
    name = "qwen 2.5/coder"
    assert client.post("/api/auth/me/models", json={"name": name},
                       headers=headers).status_code == 200
    res = client.delete(f"/api/auth/me/models/{quote(name)}", headers=headers)
    assert res.status_code == 200, f"带斜杠的名字删不掉（{res.status_code}），用户只能改库"
    assert name not in res.json()["models"]


def test_model_name_length_matches_the_column_and_chat_request():
    client, _, headers = _login_llm_client()
    assert client.post("/api/auth/me/models", json={"name": "x" * 101},
                       headers=headers).status_code == 422
    assert client.post("/api/auth/me/models", json={"name": ""}, headers=headers).status_code == 422


def test_settings_endpoints_are_all_behind_the_login_gate():
    client, _ = make_client()
    for method, path in [("PUT", "/api/auth/me"), ("PUT", "/api/auth/me/password"),
                         ("PUT", "/api/auth/me/llm"), ("POST", "/api/auth/me/models"),
                         ("DELETE", "/api/auth/me/models/x"), ("PUT", "/api/auth/me/models/default")]:
        res = client.request(method, path, json={})
        assert res.status_code == 401, f"{method} {path} 没上门：{res.status_code}"


def test_masking_never_echoes_a_short_key_back_as_its_own_tail():
    """短 key 的"尾 4 位"就是它自己：那时宁可只回前缀 + 一串星。"""
    from schemas.auth import mask_api_key
    assert mask_api_key("sk-abc") == "sk-****"
    assert mask_api_key("") == "" and mask_api_key(None) == ""
    assert mask_api_key("noplus-1234567890") == "****7890"     # 没有 sk- 前缀也照样只留尾 4


def test_half_a_config_is_not_configured_even_when_the_key_is_there():
    """`llm_configured` 判的是"key 与路由同时有值"那个合取，只判 api_key 时这条红。

    半套配置从哪来：库里被人直写过一格、或将来拆出单独的 key 端点。这时响应仍要给掩码
    （用户得知道自己在用哪把 key），但 llm_configured 必须是 False——Task 7 的 409 门禁
    读的就是这一格，它在半套配置上说是 True，用户问一句就只拿到上游那句 401。
    """
    client, db, headers = _login_llm_client()
    db.users[0].api_key = "sk-half-only-1234567890"          # 只有 key，base_url 仍是 None
    user = client.get("/api/auth/me", headers=headers).json()["user"]
    assert user["api_key_masked"] == "sk-****7890"
    assert user["llm_base_url"] == ""
    assert user["llm_configured"] is False


# ---------- 阶段二 Task 2 修正轮 1（F1 / F2）：三处空白守卫各补一条判据 ----------


def test_blank_api_key_is_422_and_writes_neither_column():
    """八格空白过得了 `LlmIn.api_key` 的 `min_length=8`——那个长度是在 **strip 之前**量的。

    没有守卫时的形状是最难查的那种谎：响应 200「保存成功」，而 `llm_configured` 是 False、
    `api_key_masked` 是 `""`（key 被 `.strip()` 成空串写进了库）。用户以为配好了，Task 7 的
    409 门禁再把他挡在门外，而设置页说不出任何原因。所以这条既判 422，也判"两格根本没被写"。
    """
    client, db, headers = _login_llm_client()
    res = client.put("/api/auth/me/llm", json={"api_key": "        ",
                                               "base_url": "https://vLLM.internal/v1"},
                     headers=headers)
    assert res.status_code == 422
    assert res.json() == {"detail": "api_key 不能是空白"}
    # 拦在写库之前：两格都还是注册时的初值 None，不是被写成 ""
    assert db.users[0].api_key is None, "空白的 api_key 被写进了库"
    assert db.users[0].base_url is None, "路由跟着一起被写了"
    user = client.get("/api/auth/me", headers=headers).json()["user"]
    assert user["llm_configured"] is False
    assert user["api_key_masked"] == ""


def test_whitespace_nickname_is_422_at_the_endpoint_not_the_schema():
    """`{"nickname": ""}` 由 `min_length=1` 挡在 schema 层，**走不到**端点那句空白守卫，
    所以那句 422 从来没有判据覆盖过。空白但非空的串才是它的入口。"""
    client, db, headers = _login_llm_client()
    res = client.put("/api/auth/me", json={"nickname": "   "}, headers=headers)
    assert res.status_code == 422
    assert res.json() == {"detail": "昵称不能是空白"}
    assert db.users[0].nickname == "a", "昵称被洗成了空串"


def test_whitespace_model_name_is_422_and_stays_out_of_the_list():
    """同上：`test_model_name_length_matches_the_column_and_chat_request` 那条用的是 `{"name": ""}`，
    长度 0，被 pydantic 拦下，端点那句「模型名不能是空白」拔掉它、本轮之前的 43 条判据一条都不会红。这条补它的入口。"""
    client, _, headers = _login_llm_client()
    res = client.post("/api/auth/me/models", json={"name": "   "}, headers=headers)
    assert res.status_code == 422
    assert res.json() == {"detail": "模型名不能是空白"}
    # 名单必须是空的：空白名一旦进了 user_models，它就是默认模型，问答侧会拿它去打下游
    body = client.get("/api/auth/me", headers=headers).json()["user"]
    assert body["models"] == [] and body["default_model"] is None


# ---------- 阶段三 ①：两格的长度界要量在 strip 之后 ----------


def test_api_key_is_too_short_when_the_length_comes_from_padding():
    """`"  sk-ab  "` 一共 9 格，过得了 `min_length=8`，可 strip 之后只剩 5 格——那不是 key 的长度，
    是空白的长度。

    修前的形状：schema 放行，端点把 `.strip()` 后的 5 格原样写进 `users.api_key` 并回 200。
    界面上掩码、`llm_configured` 全都"正常"（非空即算配好），症状推迟到问答侧——上游拿一把
    被截短过的 key 回 401，而 401 在这里只有一句"未登录或登录已过期"。所以这一格必须在写库
    之前拦住，并且要断"两格都没被写"。
    """
    client, db, headers = _login_llm_client()
    res = client.put("/api/auth/me/llm", json={"api_key": "  sk-ab  ",
                                               "base_url": "https://vLLM.internal/v1"},
                     headers=headers)
    assert res.status_code == 422, f"strip 后只有 5 位的 key 被当成 9 位放行了：{res.status_code}"
    assert db.users[0].api_key is None, "不足位的 api_key 被写进了库"
    assert db.users[0].base_url is None, "路由跟着一起被写了"


def test_api_key_padding_does_not_push_it_over_the_column_bound():
    """反方向：`String(255)` 装得下 255 位的 key，两侧那几格空白不是 key 的一部分。

    修前它会被拒（strip 前 259 > 255），用户只能去手工删空格；而"贴进来一段带换行的 key"
    恰恰是最常见的用法。这条同时钉两件事：带空白的 255 位 key 收 200，落库的是 **strip 后
    的整串**（不是带空白的原文——空白进列里会让掩码尾四位变成空格）。
    """
    client, db, headers = _login_llm_client()
    key = "k" * 255
    res = client.put("/api/auth/me/llm", json={"api_key": f"  {key}  ",
                                               "base_url": "https://vLLM.internal/v1"},
                     headers=headers)
    assert res.status_code == 200, f"255 位的 key 因为两侧空白被拒：{res.status_code} {res.text[:120]}"
    assert db.users[0].api_key == key, "入库的不是 strip 之后的整串"


def test_base_url_padding_does_not_push_it_over_the_column_bound():
    """路由那一格同族：`String(500)`，界应该量在洗净之后。

    它今天已经有一条 `_looks_like_a_url` 顺手 `.strip()`，所以"落库是干净串"这条在修前也成立；
    红的是**拒绝方向**——500 位的路由多贴一个空格就 422，而那句 422 的文案来自 pydantic 的
    长度校验，用户看不出跟空格有关。
    """
    client, db, headers = _login_llm_client()
    url = "https://" + "p" * 492          # 正好 500，与列宽同界
    assert len(url) == 500
    res = client.put("/api/auth/me/llm", json={"api_key": "sk-abcdef1234567890",
                                               "base_url": f" {url} "},
                     headers=headers)
    assert res.status_code == 200, f"500 位的路由因为两侧空白被拒：{res.status_code} {res.text[:120]}"
    assert db.users[0].base_url == url, "入库的不是 strip 之后的整串"
