"""启动期一次性改造：建表之后补列、补索引、造默认用户、旧数据归户、旧向量补戳。

三句写在这里的话不能丢：
① 每一步都必须幂等——lifespan 每次开机都跑，开发者本地库和部署库进度不齐是常态；
② MySQL 没有 `ADD COLUMN IF NOT EXISTS`（`CREATE INDEX` 同样没有 IF NOT EXISTS），所以
   "先查 information_schema 再 ALTER"不是洁癖，是唯一写法；`Base.metadata.create_all`
   对已存在的表整表跳过，补不出列也补不出索引（core/database.py 的 init_database）。
③ 补向量戳**只改 metadata，绝不重新嵌入**：重嵌一遍全库子块（2026-10-07 重钉的基线是
   10 条）要再加载一次 0.6B 模型，而且会改变已经验过的向量，把迁移变成一次重新灌库。
"""
import logging

from sqlalchemy import text

from core.security import hash_password

logger = logging.getLogger("kb.migrations")

DEFAULT_IDENTIFIER = "default@local"
DEFAULT_NICKNAME = "默认用户"

# 空口令时写进 password_hash 的占位值。这一列是 NOT NULL，所以"没有口令"也得有个串；
# 它不含 `$`，verify_password 在四段解包那一格就 ValueError → False（即便拼出四段，
# 首段也不是 pbkdf2_sha256，算法门照样拒绝）。替代的是原先 hash_password("this-account-
# has-no-password") 那种写法——那是一枚源码里看得见的可用凭证。
UNUSABLE_PASSWORD_HASH = "unusable-no-password-set"

# (表, 列, DDL 类型)。阶段一只加 documents.user_id；chat_history.user_id 归阶段二
# （spec 2.2 勘误：历史的读写过滤和 RAGSystem 四方法要一起重接，分两轮改同一文件不值）。
MIGRATED_COLUMNS = [
    ("documents", "user_id", "INTEGER"),
    ("users", "api_key", "VARCHAR(255)"),
    ("users", "base_url", "VARCHAR(500)"),
]

# (表, 列, 索引名)。spec 2.2 要求 documents.user_id 带索引，而 create_all 对已存在的表
# 整表跳过 ⇒ 已部署库会永远带着一个无索引的外键列，这条长期收拢靠这里。
MIGRATED_INDEXES = [("documents", "user_id", "idx_documents_user_id")]


def column_exists(conn, table: str, column: str) -> bool:
    rows = conn.execute(
        text("SELECT COLUMN_NAME FROM information_schema.COLUMNS "
             "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table "
             "AND COLUMN_NAME = :column"),
        {"table": table, "column": column},
    ).fetchall()
    return bool(rows)


def add_column(conn, table: str, column: str, ddl_type: str) -> None:
    # 表名/列名走 f-string 不是注入风险：三者只可能来自 MIGRATED_COLUMNS 这个模块常量，
    # MySQL 的 DDL 又不接受绑定参数——这条"只能拼"是语法事实，不是偷懒。
    conn.execute(text(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {ddl_type} NULL"))


def ensure_columns(conn) -> list:
    """返回这次真的补上的列。判据要数这个返回值，所以不能图省事返回 None。"""
    added = []
    for table, column, ddl_type in MIGRATED_COLUMNS:
        if not column_exists(conn, table, column):
            add_column(conn, table, column, ddl_type)
            added.append((table, column))
    conn.commit()
    return added


def index_exists(conn, table: str, index: str) -> bool:
    """STATISTICS 里一个索引名有多行（每列一行），这里只按名字问"有没有"。"""
    rows = conn.execute(
        text("SELECT INDEX_NAME FROM information_schema.STATISTICS "
             "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table "
             "AND INDEX_NAME = :index"),
        {"table": table, "index": index},
    ).fetchall()
    return bool(rows)


def add_index(conn, table: str, column: str, index: str) -> None:
    # 与 add_column 同一条理由：DDL 不接受绑定参数，三个值只可能来自 MIGRATED_INDEXES。
    conn.execute(text(f"CREATE INDEX `{index}` ON `{table}` (`{column}`)"))


def ensure_indexes(conn) -> list:
    """返回这次真的建了的 (表, 索引名)。必须在 ensure_columns 之后跑——列还不存在就建索引会当场炸。"""
    created = []
    for table, column, index in MIGRATED_INDEXES:
        if not index_exists(conn, table, index):
            add_index(conn, table, column, index)
            created.append((table, index))
    conn.commit()
    return created


def ensure_default_user(conn, password: str) -> int:
    """旧数据的归属锚点。口令为空照样建行、不写可用哈希——spec 2.6 与 6.3 说的是同一件事：
    账号存在的意义是 `documents.user_id` 有个可指的值，能不能登录是另一回事。
    """
    existing = conn.execute(
        text("SELECT id, identifier FROM users WHERE identifier = :identifier"),
        {"identifier": DEFAULT_IDENTIFIER},
    ).fetchall()
    if existing:
        return existing[0][0]
    conn.execute(
        text("INSERT INTO users (identifier, identifier_type, nickname, avatar, "
             "password_hash, created_at) VALUES (:identifier, 'email', :nickname, "
             "'auto', :password_hash, NOW())"),
        {"identifier": DEFAULT_IDENTIFIER, "nickname": DEFAULT_NICKNAME,
         # 空口令时也要有非 NULL 的哈希（列是 NOT NULL）。放一个永不通过的占位串，
         # 比放一个能匹配的固定值安全：那条登录路径无论如何都进不来。
         "password_hash": hash_password(password) if password else UNUSABLE_PASSWORD_HASH},
    )
    conn.commit()
    return conn.execute(
        text("SELECT id FROM users WHERE identifier = :identifier"),
        {"identifier": DEFAULT_IDENTIFIER},
    ).fetchall()[0][0]


def backfill_documents(conn, user_id: int) -> int:
    """只捡 user_id 为 NULL 的行：已经归过户的一次 UPDATE 白扫全表。"""
    unowned = conn.execute(text("SELECT id FROM documents WHERE user_id IS NULL")).fetchall()
    if not unowned:
        return 0
    conn.execute(text("UPDATE documents SET user_id = :uid WHERE user_id IS NULL"),
                 {"uid": user_id})
    conn.commit()
    return len(unowned)


def vector_ids_without_owner(conn) -> dict:
    """补戳的输入清单：parent_chunks/child_chunks 里那些所属文档还没有 user_id 的向量 id。

    真库上这两列存的**就是** Chroma 的 id（2026-10-04 已 live 验过：用它删向量，
    计数如实下降），所以直接拿它当 get/update 的 ids，不需要任何映射。
    """
    out = {"parent": [], "child": []}
    for key, table in (("parent", "parent_chunks"), ("child", "child_chunks")):
        rows = conn.execute(text(
            f"SELECT c.vector_id FROM {table} c "
            "JOIN documents d ON d.id = c.document_id "
            "WHERE c.vector_id IS NOT NULL AND c.vector_id <> '' AND d.user_id IS NULL"
        )).fetchall()
        out[key] = [r[0] for r in rows]
    return out


def stamp_vector_owner(client, vector_ids: dict, user_id: int) -> int:
    """把无主的旧向量补上 user_id 戳。get → merge → update，跳过已戳的。

    为什么不依赖"Chroma 的 update 只补提供的键"这个较新版本的语义：真依赖它的迁移，
    在语义变化时会静默清掉 document_id/parent_id 这类既有 metadata，而那两个键一丢，
    召回与按文档清扫会同时坏掉，且没有任何报错。读回来合并写是最保守的做法。
    """
    from core.vector_store import COLLECTION_CHILD, COLLECTION_PARENT

    total = 0
    for name, ids in ((COLLECTION_PARENT, vector_ids["parent"]),
                      (COLLECTION_CHILD, vector_ids["child"])):
        if not ids:
            continue
        collection = client.get_collection(name)
        found = collection.get(ids=ids, include=["metadatas"])
        to_update, metadatas = [], []
        for vid, meta in zip(found["ids"], found["metadatas"]):
            meta = meta or {}
            if meta.get("user_id") not in (None, ""):
                # 已戳就跳过，**哪怕戳的是别人**：迁移只补无主的，改归属不是它的活
                # （Interfaces 那句"已戳过的跳过"就是这个意思）。这一格同时让
                # "每次开机重跑"退化成一次只读扫描。
                continue
            to_update.append(vid)
            metadatas.append({**meta, "user_id": str(user_id)})
        if to_update:
            collection.update(ids=to_update, metadatas=metadatas)
            total += len(to_update)
    return total


def run_migrations(engine, chroma_client, password: str) -> dict:
    """lifespan 唯一入口。返回一份可直接进日志的汇总，不返回秘密（没有令牌、没有哈希）。"""
    with engine.connect() as conn:
        added = ensure_columns(conn)
        indexes = ensure_indexes(conn)   # 顺序硬要求：列还没加出来就建索引会当场炸
        user_id = ensure_default_user(conn, password)
        # 清单必须在归户之前读：backfill_documents 自己会 commit，之后 NULL 行就不存在了
        pending = vector_ids_without_owner(conn)
        docs = backfill_documents(conn, user_id)
        if not docs:
            pending = {"parent": [], "child": []}
    # 补戳放在连接之外：Chroma 那边可能是一次几秒的只读扫描，别把 MySQL 连接摁在它上面
    vectors = stamp_vector_owner(chroma_client, pending, user_id)
    summary = {"columns_added": added, "indexes_added": indexes,
               "default_user_id": user_id, "documents_claimed": docs,
               "vectors_stamped": vectors}
    logger.info("迁移完成: %s", summary)
    return summary
