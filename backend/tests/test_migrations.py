"""迁移的四条纪律：缺列才 ALTER、已戳不再写、重复跑零副作用、口令空则账号不可登录。

这里用假 Connection 记录发出去的 SQL，为的是把"先查再改"这个决策本身钉死——
真 MySQL 上的 ALTER 语义归 live 组，那是另一条判据。
"""

from core import migrations
from core.security import verify_password

# 向量 id → 所属文档 id。真库上这份对应关系由 `parent_chunks JOIN documents` 给出来，
# 假连接只需要复述同一件事：文档归户之后，这些行就不再满足 `d.user_id IS NULL`。
UNOWNED_VECTOR_ROWS = {"parent": {"pv1": 3, "pv2": 4}, "child": {"cv1": 5}}


class FakeConn:
    """只实现 migrations 用到的那几件事：查 information_schema、执行 DDL、跑 SELECT/UPDATE。"""

    def __init__(self, existing_columns=(), user_rows=(), owned_doc_ids=(),
                 existing_indexes=()):
        self.columns = set(existing_columns)          # {("documents", "user_id")}
        self.indexes = {(t, i) for (t, i) in existing_indexes}   # {("documents", "idx_documents_user_id")}
        self.users = list(user_rows)                  # [(id, identifier)]
        self.owned_docs = set(owned_doc_ids)          # 已有 user_id 的文档 id
        self.inserted = []                            # INSERT INTO users 的参数，用来验写了哪个哈希
        self.executed = []                            # 记 DDL/DML，SELECT 不记

    def execute(self, sql, params=None):
        text = str(sql)
        head = text.strip().upper()
        params = params or {}
        if head.startswith("SELECT COLUMN_NAME"):
            table = params["table"]
            rows = [(c,) for (t, c) in self.columns if t == table]
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
        if head.startswith("SELECT C.VECTOR_ID FROM"):
            key = "parent" if "PARENT_CHUNKS" in head else "child"
            rows = [vid for vid, doc_id in UNOWNED_VECTOR_ROWS[key].items()
                    if doc_id not in self.owned_docs]
            return _Result([(vid,) for vid in rows])
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


def test_ensure_columns_alters_only_when_missing():
    conn = FakeConn(existing_columns=[])
    assert migrations.ensure_columns(conn) == [("documents", "user_id")]
    assert len(conn.executed) == 1
    assert "ADD COLUMN" in conn.executed[0] and "`user_id`" in conn.executed[0]

    conn2 = FakeConn(existing_columns=[("documents", "user_id")])
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


def test_run_migrations_stamps_the_vectors_read_before_documents_are_claimed():
    """补戳清单必须在归户之前读：backfill_documents 自己会 commit，之后 NULL 行就不存在了。

    只断言 `vectors_stamped > 0` 挡不住顺序写反——那在假连接下照样绿。这里的判据是
    "fake client 收到的 id 清单 == 那条 `d.user_id IS NULL` SELECT 返回的行"：假连接收到
    UPDATE documents 之后就把 1..9 全标成已归户，同一句 SELECT 从此返回空，
    所以顺序一反，requested 里只剩空清单（或者一次都不发），断言当场红。
    """
    parent = FakeCollection({"pv1": {"document_id": "3"}, "pv2": {"document_id": "4"}})
    child = FakeCollection({"cv1": {"document_id": "5"}})
    client = FakeChroma({"parent_document": parent, "child_document": child})

    summary = migrations.run_migrations(FakeEngine(FakeConn()), client, password="secret-pass")

    assert parent.requested == [["pv1", "pv2"]], "补戳没拿到归户之前的父块清单"
    assert child.requested == [["cv1"]], "补戳没拿到归户之前的子块清单"
    assert parent.items["pv1"] == {"document_id": "3", "user_id": "1"}
    assert child.items["cv1"] == {"document_id": "5", "user_id": "1"}
    assert summary["vectors_stamped"] == 3
    assert summary["documents_claimed"] == 9


def test_stamp_merges_existing_metadata_and_skips_stamped():
    parent = FakeCollection({
        "p1": {"document_id": "3", "parent_id": "x_parent_0"},
        "p2": {"document_id": "4", "user_id": "7"},
    })
    client = FakeChroma({"parent_document": parent, "child_document": FakeCollection({})})
    # 重跑第二遍必须是零写：判据靠返回值，不靠"看起来没报错"
    assert migrations.stamp_vector_owner(client, {"parent": ["p1", "p2"], "child": []}, 7) == 1
    assert parent.items["p1"] == {"document_id": "3", "parent_id": "x_parent_0", "user_id": "7"}
    assert migrations.stamp_vector_owner(client, {"parent": ["p1", "p2"], "child": []}, 7) == 0


def test_stamp_never_rewrites_a_foreign_users_vector():
    """已戳但戳的是**别人**的向量不该被动——迁移只补 NULL，不改归属。"""
    parent = FakeCollection({"p1": {"user_id": "9"}})
    client = FakeChroma({"parent_document": parent, "child_document": FakeCollection({})})
    assert migrations.stamp_vector_owner(client, {"parent": ["p1"], "child": []}, 7) == 0
    assert parent.items["p1"] == {"user_id": "9"}


def test_default_identifier_is_the_one_the_spec_names():
    assert migrations.DEFAULT_IDENTIFIER == "default@local"
    assert migrations.MIGRATED_COLUMNS == [("documents", "user_id", "INTEGER")]
