"""迁移的纪律：缺列才 ALTER、缺外键才 ADD CONSTRAINT（且问的是"这一列有没有外键"，
不是"有没有那个名字"）、已戳不再写、重复跑零副作用、口令空则账号不可登录，
步骤 4 抄 `.env` 三键时一人至多立一枚默认。

这里用假 Connection 记录发出去的 SQL，为的是把"先查再改"这个决策本身钉死——
真 MySQL 上的 ALTER 语义归 live 组，那是另一条判据。外键也一样：它在真库上建成没有、
RESTRICT 拦不拦得住删账号，都在 live 组。
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
                 existing_indexes=(), user_models=(), chat_unowned=3, existing_fks=(),
                 existing_orphans=()):
        self.columns = set(existing_columns)          # {("documents", "user_id")}
        self.indexes = {(t, i) for (t, i) in existing_indexes}   # {("documents", "idx_documents_user_id")}
        # 外键按 **(表, 列)** 存，约束名只是带着的注脚：真库上 create_all 建出来的叫
        # `documents_ibfk_1`，迁移建出来的叫 `fk_documents_user_id`，生产码问的是"这一列有没有外键"，
        # 问名字就会在新库上再叠一枚重复外键（InnoDB 不拦）。
        self.fks = {(t, c): n for (t, c, n) in existing_fks}
        # "有几行的 user_id 指向已经不存在的账号"在这里是个**给定值**：假连接不会去 join users 算，
        # 这条判据要钉的是"数出来了会去归户、且赶在 ALTER 之前"，孤儿判定本身的 SQL 语义归 live 组。
        self.orphans = dict(existing_orphans)         # {"chat_history": 43}
        self.users = list(user_rows)                  # [(id, identifier)]
        self.owned_docs = set(owned_doc_ids)          # 已有 user_id 的文档 id
        self.inserted = []                            # INSERT INTO users 的参数，用来验写了哪个哈希
        self.llm = {}                                 # 默认用户手上的 api_key/base_url（步骤 4 写它）
        self.user_models = list(user_models)          # [(user_id, name, is_default)]
        self.chat_unowned = chat_unowned              # user_id IS NULL 的历史行数
        self.indexed_columns = set()                  # CREATE INDEX 覆盖到的 (表, 列)，顺序判据用它
        self.executed = []                            # 记 DDL/DML，SELECT 不记
        self.reclaims = []                             # [(表, uid)]：孤儿行归户打给了谁，绑定参数不在 SQL 文本里

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
        if head.startswith("SELECT CONSTRAINT_NAME"):
            table, column = params["table"], params["column"]
            return _Result([(name,) for (t, c), name in self.fks.items()
                            if t == table and c == column])
        if head.startswith("ALTER TABLE") and "ADD CONSTRAINT" in head:
            # 必须排在下面那条 `ALTER TABLE`（ADD COLUMN）之前：那条要按 ADD COLUMN 切串，
            # 撞上来只会切出 IndexError，把"外键这件事"的错报成"列这件事"的错。
            self.executed.append(text)
            table = text.split()[2].strip("`")
            # 与上面 CREATE INDEX 分支同一种切法：只按 "(" 切会留着 ") REFERENCES `users`"，
            # 键存错了第二遍就查不到，"重跑交白卷"会红在夹具身上而不是生产码身上。
            column = text.split("FOREIGN KEY")[1].split("(")[1].split(")")[0].strip().strip("`")
            self.fks[(table, column)] = text.split("CONSTRAINT")[1].split()[0].strip("`")
            return _Result([])
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
            self.indexed_columns.add((table, column))
            return _Result([])
        if head.startswith("SELECT COUNT(*) FROM CHAT_HISTORY"):
            return _Result([(self.chat_unowned,)])
        if head.startswith("SELECT COUNT(*) AS ORPHANS"):
            # 必须排在下面那条通用 `SELECT COUNT`（数 users）之前：那条按前缀认领，
            # 撞上来只会把孤儿数报成账号数。表名取 FROM 之后的第一段。
            table = text.split("FROM")[1].split()[0].strip("`")
            return _Result([(self.orphans.get(table, 0),)])
        if head.startswith("UPDATE") and "NOT IN (SELECT ID FROM USERS)" in head:
            # 这一句也以 `UPDATE DOCUMENTS` / `UPDATE CHAT_HISTORY` 开头，所以必须抢在那两条之前：
            # 那两条把这次改动记成"NULL 归户"，孤儿数就永远不清零，第二遍的白卷判据会假红。
            self.executed.append(text)
            table = text.split()[1].strip("`")
            self.orphans[table] = 0
            self.reclaims.append((table, params["uid"]))
            return _Result([])
        if head.startswith("UPDATE CHAT_HISTORY"):
            self.executed.append(text)
            self.chat_unowned = 0                   # 归户之后不再有 NULL 行：重跑零副作用
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


class MigrationConfig:
    """run_migrations 现在读 config 的四格：默认口令 + 迁移种子的三键。

    与 `fakes.FakeConfig` 不是同一个替身，也不该合并：那枚只带 `/api/health` 读的
    `CHROMA_PERSIST_DIR`，合并就是把 `.env` 三键重新塞回交付面（阶段二 Task 7 刚以
    「写了没人读的字段是负资产」删过一次）。同名才是缺陷，两枚各自的形状不是——
    判据见 `tests/test_test_doubles.py`。
    """
    DEFAULT_USER_PASSWORD = "secret-pass"
    OPENAI_API_KEY = "sk-from-env"
    OPENAI_BASE_URL = "https://dashscope/v1"
    LLM_MODEL = "qwen3.7-flash"


def test_ensure_columns_alters_only_when_missing():
    conn = FakeConn(existing_columns=[])
    assert migrations.ensure_columns(conn) == [("documents", "user_id"),
                                               ("users", "api_key"),
                                               ("users", "base_url"),
                                               ("chat_history", "user_id")]
    assert len(conn.executed) == 4
    assert "ADD COLUMN" in conn.executed[0] and "`user_id`" in conn.executed[0]

    conn2 = FakeConn(existing_columns=[("documents", "user_id"), ("users", "api_key"),
                                       ("users", "base_url"), ("chat_history", "user_id")])
    assert migrations.ensure_columns(conn2) == []
    assert conn2.executed == []


def test_ensure_indexes_creates_only_when_missing():
    conn = FakeConn(existing_columns=[("documents", "user_id"), ("chat_history", "user_id")],
                    existing_indexes=())
    assert migrations.ensure_indexes(conn) == [("documents", "idx_documents_user_id"),
                                               ("chat_history", "idx_chat_history_user_id")]
    assert len(conn.executed) == 2
    assert "CREATE INDEX" in conn.executed[0] and "`idx_documents_user_id`" in conn.executed[0]

    conn2 = FakeConn(existing_columns=[("documents", "user_id"), ("chat_history", "user_id")],
                     existing_indexes=[("documents", "idx_documents_user_id"),
                                       ("chat_history", "idx_chat_history_user_id")])
    assert migrations.ensure_indexes(conn2) == []
    assert conn2.executed == []


def test_ensure_foreign_keys_alters_only_when_missing():
    """老库上的 `documents.user_id` / `chat_history.user_id` 是**裸列**：裸 DDL 的 ADD COLUMN
    加不出外键约束（阶段三 ④ 的全部内容）。不补的后果不是读错，是将来做「注销账号」时
    用户名下的行谁都不删、静静变成孤儿。
    """
    conn = FakeConn(existing_columns=[("documents", "user_id"), ("chat_history", "user_id")])
    assert migrations.ensure_foreign_keys(conn) == [
        ("documents", "fk_documents_user_id"),
        ("chat_history", "fk_chat_history_user_id"),
    ]
    assert len(conn.executed) == 2
    assert "ADD CONSTRAINT" in conn.executed[0] and "FOREIGN KEY" in conn.executed[0]

    stamped = FakeConn(existing_columns=[("documents", "user_id"), ("chat_history", "user_id")],
                       existing_fks=[("documents", "user_id", "fk_documents_user_id"),
                                     ("chat_history", "user_id", "fk_chat_history_user_id")])
    assert migrations.ensure_foreign_keys(stamped) == []
    assert stamped.executed == [], "已经有外键还发 ALTER：MySQL 会回 1826（约束名撞车）"


def test_ensure_foreign_keys_asks_about_the_column_not_the_constraint_name():
    """`create_all` 建出来的新库带着 `documents_ibfk_1`，与迁移建的那套**名字不同**，
    但"这一列已经有外键"是同一个事实。按名字问就会在每个新库上再叠一枚重复外键
    （InnoDB 不拦同名之外的重复，它会安静收下）。
    """
    conn = FakeConn(existing_columns=[("documents", "user_id"), ("chat_history", "user_id")],
                    existing_fks=[("documents", "user_id", "documents_ibfk_1"),
                                  ("chat_history", "user_id", "chat_history_ibfk_1")])
    assert migrations.ensure_foreign_keys(conn) == []
    assert conn.executed == [], "按约束名查的写法会在这里红：新库不该被补第二枚"


def test_ensure_foreign_keys_never_cascades_at_the_mysql_level():
    """RESTRICT（不写 ON DELETE 就是它）是刻意的：文档行在 MySQL，向量在 Chroma，
    MySQL 的级联**带不走向量**。写 ON DELETE CASCADE 等于把"行没了、向量还在"变成默认行为，
    而那正是本仓一路在防的召回脏数据。要删就得走应用层两头删。
    """
    conn = FakeConn(existing_columns=[("documents", "user_id"), ("chat_history", "user_id")])
    migrations.ensure_foreign_keys(conn)
    assert len(conn.executed) == 2
    for ddl in conn.executed:
        assert "ON DELETE" not in ddl.upper(), f"外键带了级联：{ddl[:120]}"
        assert "REFERENCES `users` (`id`)" in ddl, f"外键没指到 users(id)：{ddl[:120]}"


def test_reclaim_orphaned_owners_sends_dead_rows_back_to_the_default_user():
    """补 FK 之前必须先清孤儿——这一步不是洁癖，是"后端起得来起不来"。

    2026-10-08 直查真库量到的现状：`chat_history` 43 行的 user_id **全是 1**，而 users 表里
    只剩 30（default@local）和 338 两行。默认账号被重铸过、id 从 1 漂到 30，而这 43 行当年
    写进去时就带着值（非 NULL），`backfill_chat_history` 只捡 `IS NULL` 的行 ⇒ 它们从此
    谁也读不到（历史按 user_id 收窄）、谁也删不掉。带着孤儿去 `ADD CONSTRAINT`，MySQL 当场回
    errno 1452；而 `run_migrations` 挂在 lifespan 且没有 try/except（main.py）⇒ 整台后端起不来。
    """
    conn = FakeConn(existing_columns=[("documents", "user_id"), ("chat_history", "user_id")],
                    existing_orphans={"documents": 0, "chat_history": 43})
    assert migrations.reclaim_orphaned_owners(conn, user_id=30) == [("chat_history", 43)]
    assert len(conn.executed) == 1
    assert "NOT IN (SELECT id FROM users)" in conn.executed[0]
    assert conn.reclaims == [("chat_history", 30)], (
        "归户归错了人：这批行要交给**默认用户**（改造前那一个人在用），不是随便一个 id"
    )

    assert migrations.reclaim_orphaned_owners(conn, user_id=30) == []
    assert len(conn.executed) == 1, "第二遍又发 UPDATE：幂等破了"


def test_reclaim_orphaned_owners_runs_before_the_foreign_keys():
    """顺序判据：孤儿行赶在 `ADD CONSTRAINT` 之前清掉，并且归户数要进 summary（可数、重跑交白卷）。"""
    conn = FakeConn(existing_orphans={"chat_history": 43})
    client = FakeChroma({"parent_document": FakeCollection({}), "child_document": FakeCollection({})})
    first = migrations.run_migrations(FakeEngine(conn), client, MigrationConfig())
    ddl = conn.executed

    reclaim_at = min(i for i, s in enumerate(ddl) if "NOT IN (SELECT id FROM users)" in s)
    fk_at = min(i for i, s in enumerate(ddl) if "ADD CONSTRAINT" in s)
    assert reclaim_at < fk_at, (
        f"孤儿归户口在第 {reclaim_at} 条、ADD CONSTRAINT 在第 {fk_at} 条：顺序一反，"
        "真库上 ALTER 回 1452，lifespan 没兜异常 ⇒ 后端开不了机"
    )
    assert first["orphan_rows_reclaimed"] == [("chat_history", 43)]

    second = migrations.run_migrations(FakeEngine(conn), client, MigrationConfig())
    assert second["orphan_rows_reclaimed"] == []
    assert sum(1 for s in conn.executed if "NOT IN (SELECT id FROM users)" in s) == 1, (
        "第二遍又去归户：孤儿已经清了，这一步该交白卷"
    )


def test_run_migrations_adds_the_keys_after_the_indexes():
    """索引必须早于外键。InnoDB 建外键时如果列上没有可用索引，会**自己**补一枚
    （名字就是约束名），之后 `ensure_indexes` 再按我们的名字补一枚 ⇒ 同一列两枚索引，
    白付一半的写放大，而且没人会报错。
    """
    conn = FakeConn()
    client = FakeChroma({"parent_document": FakeCollection({}), "child_document": FakeCollection({})})
    migrations.run_migrations(FakeEngine(conn), client, MigrationConfig())

    ddl = conn.executed
    fk_at = min(i for i, s in enumerate(ddl) if "ADD CONSTRAINT" in s)
    index_at = max(i for i, s in enumerate(ddl) if s.startswith("CREATE INDEX"))
    assert fk_at > index_at, (
        f"第 {fk_at} 条就是 ADD CONSTRAINT，最后一条 CREATE INDEX 在第 {index_at} 条："
        "外键跑到了索引前面，同列会长出两枚索引"
    )
    assert conn.indexed_columns >= {("documents", "user_id"), ("chat_history", "user_id")}, (
        "补外键时这两列还没有索引：ensure_indexes 没在 ensure_foreign_keys 之前跑"
    )


def test_run_migrations_reports_foreign_keys_and_goes_quiet_on_the_second_pass():
    """`foreign_keys_added` 是可数的：判据不吃日志，重跑必须交白卷。"""
    conn = FakeConn()
    client = FakeChroma({"parent_document": FakeCollection({}), "child_document": FakeCollection({})})
    first = migrations.run_migrations(FakeEngine(conn), client, MigrationConfig())
    assert first["foreign_keys_added"] == [("documents", "fk_documents_user_id"),
                                           ("chat_history", "fk_chat_history_user_id")]

    second = migrations.run_migrations(FakeEngine(conn), client, MigrationConfig())
    assert second["foreign_keys_added"] == []
    assert second["columns_added"] == [] and second["indexes_added"] == []
    # 数的是"含 ADD CONSTRAINT 的那几条"：executed 存整句 SQL，`.count("ADD CONSTRAINT")`
    # 比的是整元素相等，只会永远数到 0，把幂等判据变成假绿。
    assert sum(1 for s in conn.executed if "ADD CONSTRAINT" in s) == 2, "第二遍又发了 ALTER：幂等破了"


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


def test_backfill_chat_history_claims_unowned_rows_only():
    """老历史全归默认用户：改造前这套系统是单人使用的，行里除了 session_id 没有别的归属证据。

    钉两件事：① 只捡 NULL 行（第二次跑零 UPDATE，与 backfill_documents 同一条幂等纪律）；
    ② 归户发生在计数之后——返回的数字来自 COUNT，不是 UPDATE 的 rowcount，
    因为 SQLAlchemy 的 Connection.rowcount 在假连接上根本没有，且真库上"改了几行"
    与"看到几行无主"本该相等，用后者反而能把不一致暴露出来。
    """
    conn = FakeConn(chat_unowned=3)
    assert migrations.backfill_chat_history(conn, 1) == 3
    assert conn.chat_unowned == 0
    assert any("UPDATE CHAT_HISTORY" in sql.upper() for sql in conn.executed)

    idle = FakeConn(chat_unowned=0)
    assert migrations.backfill_chat_history(idle, 1) == 0
    assert not any("UPDATE CHAT_HISTORY" in sql.upper() for sql in idle.executed)


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

    summary = migrations.run_migrations(FakeEngine(FakeConn()), client, MigrationConfig())

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
    assert summary["chat_rows_claimed"] == 3


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
                                       MigrationConfig())
    assert first["vectors_stamped"] == 3
    # 模拟崩在补戳之前：把 Chroma 的戳擦掉，documents 的 user_id 留着（MySQL 已经 commit 了）
    for item in parent.items.values():
        item.pop("user_id", None)
    child.items["cv1"].pop("user_id", None)
    second = migrations.run_migrations(engine, FakeChroma({"parent_document": parent,
                                                           "child_document": child}),
                                        MigrationConfig())
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
        ("chat_history", "user_id", "INTEGER"),
    ]
    assert migrations.MIGRATED_INDEXES == [
        ("documents", "user_id", "idx_documents_user_id"),
        ("chat_history", "user_id", "idx_chat_history_user_id"),
    ]
    # 第三组：外键。(表, 列, 约束名, 引用表)。多一枚、少一枚、或者把约束名换掉，都要过这条评审。
    assert migrations.MIGRATED_FOREIGN_KEYS == [
        ("documents", "user_id", "fk_documents_user_id", "users"),
        ("chat_history", "user_id", "fk_chat_history_user_id", "users"),
    ]
