"""迁移的纪律：缺列才 ALTER、已戳不再写、重复跑零副作用、口令空则账号不可登录，
步骤 4 抄 `.env` 三键时一人至多立一枚默认。

这里用假 Connection 记录发出去的 SQL，为的是把"先查再改"这个决策本身钉死——
真 MySQL 上的 ALTER 语义归 live 组，那是另一条判据。
"""

from core import migrations
from core.security import verify_password

# 向量 id → 所属文档 id。真库上这份对应关系由 `parent_chunks JOIN documents` 给出来，
# 假连接复述的是新语义（advisory ①）：**文档已经归户**的那些向量才进补戳清单，
# 并且按 SQL 里 `d.user_id IS NOT NULL` / `IS NULL` 哪一种来决定自己该收哪批行。
UNOWNED_VECTOR_ROWS = {"parent": {"pv1": 3, "pv2": 4}, "child": {"cv1": 5}}


class FakeConn:
    """只实现 migrations 用到的那几件事：查 information_schema、执行 DDL、跑 SELECT/UPDATE。"""

    def __init__(self, existing_columns=(), user_rows=(), owned_doc_ids=(),
                 existing_indexes=(), user_models=()):
        self.columns = set(existing_columns)          # {("documents", "user_id")}
        self.indexes = {(t, i) for (t, i) in existing_indexes}   # {("documents", "idx_documents_user_id")}
        self.users = list(user_rows)                  # [(id, identifier)]
        self.owned_docs = set(owned_doc_ids)          # 已有 user_id 的文档 id
        self.inserted = []                            # INSERT INTO users 的参数，用来验写了哪个哈希
        self.llm = {}                                 # 默认用户手上的 api_key/base_url（步骤 4 写它）
        self.user_models = list(user_models)          # [(user_id, name, is_default)]
        self.executed = []                            # 记 DDL/DML，SELECT 不记

    def execute(self, sql, params=None):
        text = str(sql)
        head = text.strip().upper()
        params = params or {}
        if head.startswith("SELECT COLUMN_NAME"):
            table = params["table"]
            rows = [(c,) for (t, c) in self.columns if t == table and c == params["column"]]
            return _Result(rows)
        if head.startswith("SELECT INDEX_NAME"):
            table, index = params["table"], params["index"]
            rows = [(i,) for (t, i) in self.indexes if t == table and i == index]
            return _Result(rows)
        if head.startswith("ALTER TABLE"):
            self.executed.append(text)
            table = text.split()[2].strip("`")
            column = text.split("ADD COLUMN")[1].strip().split()[0].strip("`")
            self.columns.add((table, column))
            return _Result([])
        if head.startswith("CREATE INDEX"):
            # 先列后索引的真语义钉在这里：列还不存在就建索引，MySQL 会直接报错，
            # 假连接也当场断言——run_migrations 里谁先谁后不再是可读注释的规矩。
            table = text.split("ON")[1].strip().split()[0].strip("`")
            column = text.split("(")[1].strip().split(")")[0].strip("`")
            if (table, column) not in self.columns:
                raise AssertionError(f"列 {table}.{column} 还不存在就建了索引：{text[:120]}")
            self.executed.append(text)
            index = text.split()[2].strip("`")
            self.indexes.add((table, index))
            return _Result([])
        if head.startswith("SELECT COUNT"):
            return _Result([(len(self.users),)])
        if head.startswith("SELECT ID, IDENTIFIER"):
            return _Result(list(self.users))
        if head.startswith("SELECT ID FROM USERS"):
            return _Result([(i,) for (i, ident) in self.users if ident == params["identifier"]])
        if head.startswith("INSERT INTO USERS"):
            new_id = (max([i for i, _ in self.users], default=0) + 1)
            self.users.append((new_id, params["identifier"]))
            self.inserted.append(dict(params))
            return _Result([])
        if head.startswith("SELECT ID FROM DOCUMENTS"):
            return _Result([(i,) for i in range(1, 10) if i not in self.owned_docs])
        if head.startswith("UPDATE DOCUMENTS"):
            self.executed.append(text)
            self.owned_docs |= {i for i in range(1, 10)}
            return _Result([])
        if head.startswith("SELECT API_KEY FROM USERS"):
            uid = params["uid"]
            for i, _ident in self.users:
                if i == uid:
                    return _Result([(self.llm.get("api_key"),)])
            return _Result([])
        if head.startswith("UPDATE USERS SET API_KEY"):
            self.llm = {"user_id": params["uid"], "api_key": params["k"], "base_url": params["u"]}
            self.executed.append(text)
            return _Result([])
        if head.startswith("SELECT ID FROM USER_MODELS"):
            # 这个前缀两个消费者共用：带 `:n` 是 (uid, name) 查重，只带 `:uid` 是"名单是否为空"的探询。
            if "n" in params:
                rows = [1 for (u, n, _d) in self.user_models
                        if u == params["uid"] and n == params["n"]]
            else:
                rows = [1 for (u, _n, _d) in self.user_models if u == params["uid"]]
            return _Result(rows)
        if head.startswith("INSERT INTO USER_MODELS"):
            # is_default 随 `:d` 参数走（生产码按"名单是否为空"决定），不再写死 True
            self.user_models.append((params["uid"], params["n"], bool(params["d"])))
            return _Result([])
        if head.startswith("SELECT C.VECTOR_ID"):
            key = "parent" if "PARENT_CHUNKS" in head else "child"
            # 假连接按 SQL 里的 WHERE 决定收哪批行：新语义（`d.user_id IS NOT NULL`）收**已归户**的，
            # 阶段一那句 `d.user_id IS NULL` 收未归户的。生产码里这一格取反就是 advisory ① 的全部
            # 内容，所以这里必须读条件、不能只看前缀——否则判据没牙。
            if "D.USER_ID IS NOT NULL" not in head and "D.USER_ID IS NULL" not in head:
                raise AssertionError("补戳 SQL 的归属条件读不出来，改这里请同步 FakeConn")
            owned_only = "D.USER_ID IS NOT NULL" in head
            # 真 SQL 返回 (vector_id, d.user_id) 两列。主人必须**随文档走**（`100 + doc_id`），
            # 这条判据的全部内容就是这个映射：生产码若把它写成恒 1，`test_run_migrations_stamps_
            # after_documents_are_claimed` 里"两枚父向量主人不同"的断言当场红。
            return _Result([(vid, 100 + int(doc_id))
                            for vid, doc_id in UNOWNED_VECTOR_ROWS[key].items()
                            if (doc_id in self.owned_docs) == owned_only])
        raise AssertionError(f"FakeConn 没料到的 SQL: {text[:120]}")

    def commit(self):
        pass

    def rollback(self):
        pass


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def rowcount(self):
        return len(self._rows)


class FakeCollection:
    """只实现 stamp_vector_owner 用到的 get/update，并把写过的东西留在身上。"""

    def __init__(self, items):
        self.items = items          # {id: metadata}
        self.requested = []         # 每次 get 收到的 id 清单，顺序即调用顺序

    def get(self, ids=None, include=None):
        picked = list(ids) if ids else list(self.items)
        self.requested.append(list(picked))
        return {"ids": [i for i in picked if i in self.items],
                "metadatas": [self.items[i] for i in picked if i in self.items]}

    def update(self, ids, metadatas):
        for i, m in zip(ids, metadatas):
            self.items[i] = m


class FakeChroma:
    def __init__(self, collections):
        self.collections = collections

    def get_collection(self, name):
        return self.collections[name]


class FakeEngine:
    """run_migrations 只用 `with engine.connect() as conn`，这里就只给这一个入口。"""

    def __init__(self, conn):
        self.conn = conn

    def connect(self):
        return self

    def __enter__(self):
        return self.conn

    def __exit__(self, *exc):
        return False


class FakeConfig:
    """run_migrations 现在读 config 的四格：默认口令 + 迁移种子的三键。"""
    DEFAULT_USER_PASSWORD = "secret-pass"
    OPENAI_API_KEY = "sk-from-env"
    OPENAI_BASE_URL = "https://dashscope/v1"
    LLM_MODEL = "qwen3.7-flash"


def test_ensure_columns_alters_only_when_missing():
    conn = FakeConn(existing_columns=[])
    assert migrations.ensure_columns(conn) == [("documents", "user_id"),
                                               ("users", "api_key"),
                                               ("users", "base_url")]
    assert len(conn.executed) == 3
    assert "ADD COLUMN" in conn.executed[0] and "`user_id`" in conn.executed[0]

    conn2 = FakeConn(existing_columns=[("documents", "user_id"), ("users", "api_key"),
                                       ("users", "base_url")])
    assert migrations.ensure_columns(conn2) == []
    assert conn2.executed == []


def test_ensure_indexes_creates_only_when_missing():
    conn = FakeConn(existing_columns=[("documents", "user_id")], existing_indexes=())
    assert migrations.ensure_indexes(conn) == [("documents", "idx_documents_user_id")]
    assert len(conn.executed) == 1
    assert "CREATE INDEX" in conn.executed[0] and "`idx_documents_user_id`" in conn.executed[0]

    conn2 = FakeConn(existing_columns=[("documents", "user_id")],
                     existing_indexes=[("documents", "idx_documents_user_id")])
    assert migrations.ensure_indexes(conn2) == []
    assert conn2.executed == []


def test_ensure_default_user_is_idempotent_and_tolerates_empty_password():
    conn = FakeConn()
    first = migrations.ensure_default_user(conn, password="secret-pass")
    second = migrations.ensure_default_user(conn, password="secret-pass")
    assert first == second and len(conn.users) == 1

    blank = FakeConn()
    uid = migrations.ensure_default_user(blank, password="")
    assert uid == blank.users[0][0], "空口令也要建行：这行是旧数据的归属锚点，不能因为没口令就不建"


def test_blank_password_writes_the_unusable_sentinel_not_a_live_credential():
    conn = FakeConn()
    migrations.ensure_default_user(conn, password="")
    assert conn.inserted[0]["password_hash"] == migrations.UNUSABLE_PASSWORD_HASH

    filled = FakeConn()
    migrations.ensure_default_user(filled, password="secret-pass")
    assert verify_password("secret-pass", filled.inserted[0]["password_hash"])


def test_unusable_password_hash_never_verifies():
    """空口令哨兵必须不可用：它替代的是原先那枚源码里看得见的可用凭证。"""
    assert verify_password("this-account-has-no-password",
                           migrations.UNUSABLE_PASSWORD_HASH) is False
    assert verify_password("", migrations.UNUSABLE_PASSWORD_HASH) is False


def test_backfill_documents_only_touches_unowned_rows():
    conn = FakeConn(owned_doc_ids={1, 2})
    changed = migrations.backfill_documents(conn, user_id=7)
    assert changed == 7, "1..9 里已归属的 1、2 必须跳过，剩下 7 行归户"
    assert len(conn.executed) == 1
    assert "WHERE user_id IS NULL" in conn.executed[0]


def test_run_migrations_stamps_after_documents_are_claimed():
    """清单读的是"有主人的向量"：归户必须在补戳之前，且崩溃之后能自愈
    （对照同文件 `test_run_migrations_self_heals_a_crash_between_claim_and_stamp`）。

    阶段一这条钉的是"清单必须在归户**之前**读"，那个前提本身就是 advisory ① 的病根。
    换成反向判据后牙齿还在：假连接按 SQL 的 WHERE 条件决定收哪批行，`backfill_documents`
    把 1..9 标成已归户之后清单才有内容——顺序一反，或者条件被改回 `IS NULL`，
    requested 就只剩空清单，断言当场红。
    """
    parent = FakeCollection({"pv1": {"document_id": "3"}, "pv2": {"document_id": "4"}})
    child = FakeCollection({"cv1": {"document_id": "5"}})
    client = FakeChroma({"parent_document": parent, "child_document": child})

    summary = migrations.run_migrations(FakeEngine(FakeConn()), client, FakeConfig())

    assert parent.requested == [["pv1", "pv2"]] and child.requested == [["cv1"]]
    # 主人随文档走：pv1/pv2 的文档不同 ⇒ 两枚戳的主人必须不同（生产码写成恒 1 就会在这里红）
    assert parent.items["pv1"] == {"document_id": "3", "user_id": "103"}
    assert parent.items["pv2"] == {"document_id": "4", "user_id": "104"}
    assert parent.items["pv1"]["user_id"] != parent.items["pv2"]["user_id"]
    # 子块"合并写回不丢原键"：document_id 留着，user_id 是新补的那一枚
    assert child.items["cv1"] == {"document_id": "5", "user_id": "105"}
    assert summary["vectors_stamped"] == 3
    assert summary["documents_claimed"] == 9
    assert summary["llm_seeded"] is True and summary["model_seeded"] is True
    assert "sk-from-env" not in str(summary)     # 汇总进日志：种子 key 绝不能在里面


def test_stamp_merges_existing_metadata_and_skips_stamped():
    parent = FakeCollection({
        "p1": {"document_id": "3", "parent_id": "x_parent_0"},
        "p2": {"document_id": "4", "user_id": "7"},
    })
    client = FakeChroma({"parent_document": parent, "child_document": FakeCollection({})})
    # 重跑第二遍必须是零写：判据靠返回值，不靠"看起来没报错"
    assert migrations.stamp_vector_owner(client, {"parent": [("p1", 7), ("p2", 7)], "child": []}) == 1
    assert parent.items["p1"] == {"document_id": "3", "parent_id": "x_parent_0", "user_id": "7"}
    assert migrations.stamp_vector_owner(client, {"parent": [("p1", 7), ("p2", 7)], "child": []}) == 0


def test_stamp_never_rewrites_a_foreign_users_vector():
    """已戳但戳的是**别人**的向量不该被动——迁移只补空，不改归属。"""
    parent = FakeCollection({"p1": {"user_id": "9"}})
    client = FakeChroma({"parent_document": parent, "child_document": FakeCollection({})})
    assert migrations.stamp_vector_owner(client, {"parent": [("p1", 7)], "child": []}) == 0
    assert parent.items["p1"] == {"user_id": "9"}


def test_seed_copies_the_three_env_keys_once():
    conn = FakeConn(user_rows=[(1, "default@local")])
    out = migrations.seed_default_llm(conn, 1, api_key="sk-from-env",
                                      base_url="https://dashscope/v1", model="qwen3.7-flash")
    assert out == {"llm_written": True, "model_added": True}
    assert conn.llm == {"user_id": 1, "api_key": "sk-from-env", "base_url": "https://dashscope/v1"}
    assert conn.user_models == [(1, "qwen3.7-flash", True)]     # 首个模型即默认


def test_seed_never_overwrites_a_key_the_user_set_himself():
    """幂等在这里的含义是"第二次什么都不写"：用户改过自己的 key，重启不该把 .env 的值盖回去。"""
    conn = FakeConn(user_rows=[(1, "default@local")])
    migrations.seed_default_llm(conn, 1, "sk-first", "https://a/v1", "m-one")
    second = migrations.seed_default_llm(conn, 1, "sk-second", "https://b/v1", "m-two")
    assert second == {"llm_written": False, "model_added": False}
    assert conn.llm["api_key"] == "sk-first"
    assert [n for _, n, _ in conn.user_models] == ["m-one"]     # 没追加第二个


def test_seed_does_nothing_when_env_has_no_key():
    conn = FakeConn(user_rows=[(1, "default@local")])
    assert migrations.seed_default_llm(conn, 1, None, None, "m") == {
        "llm_written": False, "model_added": False}
    assert conn.user_models == []      # 没有 key 却塞一个模型名 = 造一条必 409 的半套配置


def test_seed_does_not_add_a_second_default_when_the_list_already_has_one():
    """名单里已有一枚默认（用户登录后自己加的）时，seed 只把 `.env` 的 key 抄进去，
    新插的那枚必须是非默认——写死 `is_default=1` 会打破"一人至多一枚默认"这条不变量。"""
    conn = FakeConn(user_rows=[(1, "default@local")], user_models=[(1, "m-existing", True)])
    out = migrations.seed_default_llm(conn, 1, "sk-from-env", "https://dashscope/v1",
                                      "qwen3.7-flash")
    assert out == {"llm_written": True, "model_added": True}
    assert conn.llm["api_key"] == "sk-from-env"
    defaults = [m for m in conn.user_models if m[2] is True]
    assert len(defaults) == 1 and defaults[0][1] == "m-existing"
    assert conn.user_models[-1] == (1, "qwen3.7-flash", False)


def test_run_migrations_self_heals_a_crash_between_claim_and_stamp():
    """advisory ①：MySQL 已归户、Chroma 还没戳之间挂掉，下次开机必须把这批向量补上。

    同文件的 `test_run_migrations_stamps_after_documents_are_claimed`（阶段一那条判据"清单在
    归户之前读"，本轮改名改写）钉住顺序，而正因为前提是这个，那次崩溃之后清单永远为空。
    这里换成"以文档现在的主人为准"：连跑两遍，中间把那批 Chroma 的戳擦掉（MySQL 的归户留着，
    这就是崩在补戳之前的现场），第二遍必须还能补上同样 3 枚。
    """
    parent = FakeCollection({"pv1": {"document_id": "3"}, "pv2": {"document_id": "4"}})
    child = FakeCollection({"cv1": {"document_id": "5"}})
    engine = FakeEngine(FakeConn())
    first = migrations.run_migrations(engine, FakeChroma({"parent_document": parent,
                                                          "child_document": child}),
                                       FakeConfig())
    assert first["vectors_stamped"] == 3
    # 模拟崩在补戳之前：把 Chroma 的戳擦掉，documents 的 user_id 留着（MySQL 已经 commit 了）
    for item in parent.items.values():
        item.pop("user_id", None)
    child.items["cv1"].pop("user_id", None)
    second = migrations.run_migrations(engine, FakeChroma({"parent_document": parent,
                                                           "child_document": child}),
                                        FakeConfig())
    assert second["vectors_stamped"] == 3, "归户之后就不再有补戳清单——advisory ① 回来了"
    assert parent.items["pv1"] == {"document_id": "3", "user_id": "103"}


def test_stamp_uses_each_documents_own_owner():
    """每个向量按**自己文档**的主人补戳，不再假设"无主的都归默认用户"。"""
    parent = FakeCollection({"p1": {"document_id": "3"}, "p2": {"document_id": "4"}})
    client = FakeChroma({"parent_document": parent, "child_document": FakeCollection({})})
    stamped = migrations.stamp_vector_owner(
        client, {"parent": [("p1", 7), ("p2", 8)], "child": []})
    assert stamped == 2
    assert parent.items["p1"]["user_id"] == "7" and parent.items["p2"]["user_id"] == "8"


def test_default_identifier_is_the_one_the_spec_names():
    assert migrations.DEFAULT_IDENTIFIER == "default@local"
    # 加列必须同步改这里：这条逐字 pin 的存在意义就是让"偷偷多一列"过一次评审
    assert migrations.MIGRATED_COLUMNS == [
        ("documents", "user_id", "INTEGER"),
        ("users", "api_key", "VARCHAR(255)"),
        ("users", "base_url", "VARCHAR(500)"),
    ]
