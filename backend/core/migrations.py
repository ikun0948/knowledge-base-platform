"""启动期一次性改造：建表之后补列、补索引、补外键、补"一人至多一枚默认"的生成列与唯一索引、
造默认用户、旧数据归户（既捡 `user_id IS NULL` 的行，也把指向不存在账号的孤儿行交还默认用户——
后者是补外键的前置）、把 `.env` 的三键抄给默认用户、旧向量补戳。

三句写在这里的话不能丢：
① 每一步都必须幂等——lifespan 每次开机都跑，开发者本地库和部署库进度不齐是常态；
② MySQL 没有 `ADD COLUMN IF NOT EXISTS`（`CREATE INDEX` 同样没有，外键的
   `ADD CONSTRAINT` 也没有 IF NOT EXISTS），所以"先查 information_schema 再 ALTER"不是洁癖，
   是唯一写法——列查 COLUMNS、索引查 STATISTICS、外键查 KEY_COLUMN_USAGE；
   ⑤ 的守卫列查的也是 COLUMNS，但要多带一句 `GENERATION_EXPRESSION <> ''`：
   同名**普通列**不能被当成生成列（理由见 generated_column_exists）；
   `Base.metadata.create_all` 对已存在的表整表跳过，补不出列也补不出索引（core/database.py 的 init_database）。
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

# (表, 列, DDL 类型)。阶段一：documents.user_id；阶段二：users.api_key/base_url（spec 2.1，
# 与 core/database.py 的 User 两列同源，长度由 tests/test_user_models_db.py 钉成一处）；
# 以及 chat_history.user_id（spec 2.2 勘误：历史的读写过滤和 RAGSystem 四方法一起重接）。
MIGRATED_COLUMNS = [
    ("documents", "user_id", "INTEGER"),
    ("users", "api_key", "VARCHAR(255)"),
    ("users", "base_url", "VARCHAR(500)"),
    ("chat_history", "user_id", "INTEGER"),
]

# (表, 列, 索引名)。spec 2.2 要求 documents.user_id 带索引，而 create_all 对已存在的表
# 整表跳过 ⇒ 已部署库会永远带着一个无索引的外键列，这条长期收拢靠这里。
MIGRATED_INDEXES = [
    ("documents", "user_id", "idx_documents_user_id"),
    ("chat_history", "user_id", "idx_chat_history_user_id"),
]

# (表, 列, 约束名, 引用表)。阶段一/二给这两列发的是裸 `ALTER TABLE ... ADD COLUMN`，
# 那句 DDL 加不出外键；`create_all` 又对已存在的表整表跳过 ⇒ 已部署库上"documents.user_id
# 引用 users.id"只活在 core/database.py 的 Column 声明里，MySQL 并不知道。缺了它不会读错数据，
# 但将来做「注销账号」时没有任何东西拦着孤儿行——那笔账要到删数据那天才结。
MIGRATED_FOREIGN_KEYS = [
    ("documents", "user_id", "fk_documents_user_id", "users"),
    ("chat_history", "user_id", "fk_chat_history_user_id", "users"),
]

# ⑤：「一个用户至多一枚 `is_default`」此前只靠应用层两步（`add_user_model` 判空 +
# `set_default_user_model` 清场），并发下两个请求各自"以为自己是第一个"就能留下两枚默认
# （live 判据 `test_add_user_model_retries_as_non_default_when_the_guard_race_wins` 在 RED 轮
# 就在真库上复现过：[(anchor, True), (race, True)]）。
# MySQL **没有部分索引**（`CREATE UNIQUE INDEX … WHERE is_default` 那种写法建不出来），
# 所以口径换成生成列：默认行算出 `user_id`，非默认行算出 NULL，而唯一索引**不管 NULL**——
# "非默认行任意多"与"每人至多一枚默认"因此同时成立，并且这两件事由引擎兜着，不靠应用自觉。
SINGLE_DEFAULT_GUARD_EXPR = "CASE WHEN is_default THEN user_id ELSE NULL END"

# (表, 守卫列, 唯一索引名)。与 MIGRATED_COLUMNS 同一族两条腿：新库由 `create_all` 按
# core/database.py 的 ORM 声明建，已部署库由 ensure_single_default_guard 发 ALTER。
# 两侧的表达式必须同源——`core/database.py` 直接 import 上面这个常量，
# tests/test_user_models_db.py 再拿 ORM 的 `sqltext` 与它逐字对撞兜住"改了 import 那侧"的路。
MIGRATED_UNIQUE_INDEXES = [
    ("user_models", "default_guard", "uq_user_models_single_default"),
]


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


def generated_column_exists(conn, table: str, column: str) -> bool:
    """问的是"**这一列是不是生成列**"，不是"有没有这一列"。

    同名普通列在真库上完全可能出现（有人手建过、或上一版迁移只发了裸 `ADD COLUMN`），
    把它当成"守卫已建好"的后果是**静默的零约束**：那一列由应用自己写，应用不写就整列 NULL，
    而唯一索引正好不管 NULL——它安安静静管着一列空值，两枚默认照样并存，
    比没有索引更糟，因为校验会以为已经堵上了。所以这里必须带上 `GENERATION_EXPRESSION <> ''`。

    只能问"非空"、不能比全文：MySQL 把表达式存成**小写 + 反引号**的串
    （`` ``is_default`` `` 这种），逐字比 `CASE WHEN is_default THEN user_id …` 必然假红。
    表达式的全文那半由上面的常量与 ORM 声明同源钉住。
    """
    rows = conn.execute(
        text("SELECT COLUMN_NAME FROM information_schema.COLUMNS "
             "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table "
             "AND COLUMN_NAME = :column AND GENERATION_EXPRESSION <> ''"),
        {"table": table, "column": column},
    ).fetchall()
    return bool(rows)


def add_generated_column(conn, table: str, column: str) -> None:
    # 与 add_column/add_index 同一条理由：DDL 不接受绑定参数，两个名字与表达式只可能来自模块常量。
    # `STORED` 是实测选的：这一列要被唯一索引盖住，只写 `GENERATED ALWAYS AS (…)`（默认 VIRTUAL）
    # 走的是另一套索引实现，本仓没在那上面验过，换口径就要重跑整个 live 组。
    conn.execute(text(f"ALTER TABLE `{table}` ADD COLUMN `{column}` INT "
                      f"GENERATED ALWAYS AS ({SINGLE_DEFAULT_GUARD_EXPR}) STORED"))


def duplicate_default_count(conn, table: str) -> int:
    """有几枚"多出来的"默认：每人留下 id 最小那枚，其余都算重复。

    先数再改、不拿 UPDATE 的 rowcount（同 `orphaned_owner_count` 那条备忘：本仓的 MySQL 方言
    硬带了 CLIENT_FOUND_ROWS，同值重写也回 1，那个数当"改了几行"不可信）。
    """
    rows = conn.execute(
        text(f"SELECT COUNT(*) AS dupes FROM `{table}` m "
             f"JOIN (SELECT user_id, MIN(id) AS keep FROM `{table}` "
             "WHERE is_default = 1 GROUP BY user_id) k ON m.user_id = k.user_id "
             "WHERE m.is_default = 1 AND m.id > k.keep")).fetchall()
    return rows[0][0]


def clear_duplicate_defaults(conn, table: str) -> None:
    """把每人名下**除 id 最小那枚之外**的默认降成非默认。

    派生表（`JOIN (SELECT …) k`）不是风格：MySQL 1093 不允许在被 UPDATE 的表上做引用同表
    的子查询，绕开它的标准写法就是把那份结果先 JOIN 进来。
    留最小 id 而不是留"最后写入的那枚"：判据反了的话同一行每次开机都被改写，
    而且"谁当默认"要稳定可复现，用户第二次打开设置页看到的才是同一个模型。
    """
    conn.execute(text(
        f"UPDATE `{table}` d JOIN (SELECT user_id, MIN(id) AS keep FROM `{table}` "
        "WHERE is_default = 1 GROUP BY user_id) k ON d.user_id = k.user_id "
        "SET d.is_default = 0 WHERE d.is_default = 1 AND d.id > k.keep"))
    conn.commit()


def add_unique_index(conn, table: str, column: str, index: str) -> None:
    conn.execute(text(f"CREATE UNIQUE INDEX `{index}` ON `{table}` (`{column}`)"))


def ensure_single_default_guard(conn, table: str = "user_models", column: str = "default_guard",
                                index: str = "uq_user_models_single_default") -> dict:
    """⑤ 的引擎守卫：清重复 → 补生成列 → 建唯一索引，三件事各查各的，重跑交白卷。

    返回值三格都可数（判据不吃日志）：`duplicates_cleared` 是这次降掉几行，
    另两格是这次真发了哪两条 DDL。

    顺序里有两处实测钉出来的坑，反了不是"报错"而是"后端起不来"
    （`run_migrations` 挂在 lifespan 且不兜异常，main.py:59）：
    ① 去重必须早于建索引。本机 scratch 表实测：`ALTER … ADD COLUMN … STORED` 在**已经带着
       两枚默认**的数据上照样成功（两行都算出 guard=1，此时还没有索引管着它），紧接着的
       `CREATE UNIQUE INDEX` 才在同一份数据上回 `1062 Duplicate entry '1'`。
    ② 生成列必须早于索引（列都不存在，索引无从盖起）——这一条假连接也当场断言。

    Ruling：严格口径（"是不是真的那件事"）只用在**列**那一步，索引那一步仍按名字问 `index_exists`。
    不是漏掉——两处的补救手段不同：列那侧的修法是可加的 `ALTER ADD COLUMN`，跳过才是错的；
    索引那侧如果真出现"同名但是普通索引"，正确的修法是 `DROP INDEX`，而启动期迁移不问自取地
    删东西是比"约束没建上"更糟的先例。这种情况在这台机器上不存在（索引名是本仓起的、
    且 `uq_` 前缀撞不上谁），代价记在台账的挂账里。
    """
    duplicates = duplicate_default_count(conn, table)
    if duplicates:
        clear_duplicate_defaults(conn, table)
    column_added = False
    if not generated_column_exists(conn, table, column):
        add_generated_column(conn, table, column)
        column_added = True
    index_added = False
    if not index_exists(conn, table, index):
        add_unique_index(conn, table, column, index)
        index_added = True
    conn.commit()
    return {"column_added": column_added, "duplicates_cleared": duplicates,
            "index_added": index_added}


def foreign_key_exists(conn, table: str, column: str, ref_table: str) -> bool:
    """问的是"**这一列**有没有指向 users 的外键"，不是"有没有 `fk_documents_user_id` 那个名字"。

    名字会因库而异：`create_all` 建出来的外键叫 `documents_ibfk_1`，本迁移建出来的叫
    `fk_documents_user_id`。按名字查的写法会在每一个新建库上再叠一枚同列外键——InnoDB
    对不同的约束名不拦，它会安静收下，然后每次校验做两遍。
    """
    rows = conn.execute(
        text("SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
             "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :table "
             "AND COLUMN_NAME = :column AND REFERENCED_TABLE_NAME = :ref_table"),
        {"table": table, "column": column, "ref_table": ref_table},
    ).fetchall()
    return bool(rows)


def add_foreign_key(conn, table: str, column: str, constraint: str, ref_table: str) -> None:
    # 与 add_column/add_index 同一条理由：DDL 不接受绑定参数，四个值只可能来自 MIGRATED_FOREIGN_KEYS。
    # 故意不写 ON DELETE：MySQL 的默认是 RESTRICT，而级联删除在这里是**要避免**的行为——文档正文在
    # MySQL、向量在 Chroma，MySQL 的级联带不走向量，写 CASCADE 等于把"行没了、向量还能被召回"
    # 变成开机即定的默认行为。要删就走应用层两头删（core/database.py 的删除路径）。
    conn.execute(text(f"ALTER TABLE `{table}` ADD CONSTRAINT `{constraint}` "
                      f"FOREIGN KEY (`{column}`) REFERENCES `{ref_table}` (`id`)"))


def ensure_foreign_keys(conn) -> list:
    """返回这次真的补上的 (表, 约束名)。必须排在 ensure_indexes 之后：列上没有可用索引时
    InnoDB 会自己补一枚（名字就是约束名），随后 ensure_indexes 再按我们的名字补一枚，
    同一列两枚索引没人报错，只是每次写多付一半的开销。
    """
    added = []
    for table, column, constraint, ref_table in MIGRATED_FOREIGN_KEYS:
        if not foreign_key_exists(conn, table, column, ref_table):
            add_foreign_key(conn, table, column, constraint, ref_table)
            added.append((table, constraint))
    conn.commit()
    return added


def orphaned_owner_count(conn, table: str, column: str) -> int:
    """有几行的归属列"**有值但那个账号已经不在了**"。

    先数再改、不拿 `UPDATE` 的 rowcount：本仓的 MySQL 方言硬带了 CLIENT_FOUND_ROWS，
    同值重写照样回 1（见 project knowledge 里那条 rowcount 备忘），拿它当"改了几行"不可信。
    """
    rows = conn.execute(
        text(f"SELECT COUNT(*) AS orphans FROM `{table}` "
             f"WHERE `{column}` IS NOT NULL AND `{column}` NOT IN (SELECT id FROM users)")).fetchall()
    return rows[0][0]


def reclaim_orphaned_owners(conn, user_id: int) -> list:
    """把指向不存在账号的行交还给默认用户，返回 [(表, 行数)]。

    孤儿是怎么来的（2026-10-08 真库实测：chat_history 43 行全指 user_id=1，users 里只剩 30/338）：
    默认账号被重铸过一次、id 从 1 漂到 30，而那 43 行当年写入时就带着值，`backfill_chat_history`
    只捡 `IS NULL` 的行 ⇒ 从此读不到（历史按 user_id 收窄）也删不掉。

    为什么归默认用户而不是删：与 backfill_* 同一个前提——改造前只有那一个人在用，行里没有
    任何别的归属线索；归户是把数据交还唯一的失主，删是替用户做决定。
    为什么必须赶在 `ADD CONSTRAINT` 之前：带着孤儿建外键，MySQL 回 errno 1452，而 lifespan 里的
    `run_migrations` 不兜异常（main.py）——顺序一反，症状是"后端开不了机"。
    FK 建好之后 RESTRICT 会让新孤儿产生不了（本仓也没有删账号的入口），这一步就只剩一次 COUNT。
    """
    reclaimed = []
    for table, column, _constraint, _ref_table in MIGRATED_FOREIGN_KEYS:
        count = orphaned_owner_count(conn, table, column)
        if count:
            conn.execute(text(f"UPDATE `{table}` SET `{column}` = :uid "
                              f"WHERE `{column}` IS NOT NULL AND `{column}` NOT IN (SELECT id FROM users)"),
                         {"uid": user_id})
            reclaimed.append((table, count))
    conn.commit()
    return reclaimed


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


def backfill_chat_history(conn, user_id: int) -> int:
    """老历史整批归默认用户：改造前只有一的人在用，行里没有任何别的归属线索。

    为什么不学 documents 那边先 SELECT 一份清单：documents 的清单是给向量补戳用的
    （第二份存储在 Chroma），chat_history 只有 MySQL 一份，读行数只为让日志会说人话。
    """
    count = conn.execute(
        text("SELECT COUNT(*) FROM chat_history WHERE user_id IS NULL")).fetchall()[0][0]
    if not count:
        return 0
    conn.execute(text("UPDATE chat_history SET user_id = :uid WHERE user_id IS NULL"),
                 {"uid": user_id})
    conn.commit()
    return count


def seed_default_llm(conn, user_id: int, api_key, base_url, model) -> dict:
    """迁移步骤 4（spec 6）：把 `.env` 的三键抄给默认用户——坑 9 成果的去向。

    两个返回值都要**可数**，幂等这条判据不能吃日志。
    只在默认用户手上还没有 key 时抄：运行期他改过配置，重启再把 `.env` 盖回去等于每次开机
    偷走一次用户的修改。`api_key` 与 `base_url` 必须同时有值才抄（半套配置只会撞上游 401）。

    `reason`（阶段三 ⑥）：开工前两条早退回的是**同一个字典**，于是开机日志里那一句
    `llm_seeded: False` 猜不出是谁——"这台机器的 `.env` 没填 key"和"默认账号早就有自己的 key"
    是同一种症状的两种原因，前者要人去补配置，后者恰恰是不该覆盖用户的修改。
    现在三条出口各带一个名字，`run_migrations` 的 summary 里叫 `seed_reason`。
    这一格只准取常量：summary 会整枚进日志，多一格可变量就多一次把凭证印出来的机会。
    """
    if not (api_key and base_url):
        return {"llm_written": False, "model_added": False, "reason": "env_incomplete"}
    row = conn.execute(text("SELECT api_key FROM users WHERE id = :uid"), {"uid": user_id}).fetchall()
    if row and row[0][0]:
        return {"llm_written": False, "model_added": False, "reason": "already_configured"}
    conn.execute(text("UPDATE users SET api_key = :k, base_url = :u WHERE id = :uid"),
                 {"k": api_key, "u": base_url, "uid": user_id})
    conn.commit()
    added = False
    if model:
        exists = conn.execute(text("SELECT id FROM user_models WHERE user_id = :uid AND name = :n"),
                              {"uid": user_id, "n": model}).fetchall()
        if not exists:
            # is_default 与 core/database.py 的 add_user_model 同口径：名单为空才立默认。
            # 写死 1 会在"用户先加了模型、之后 .env 才补上 key"的序列里造出两枚默认，
            # 与本仓"一个用户至多一枚 is_default"的不变量冲突（读侧按 id 升序取第一枚）。
            first = conn.execute(text("SELECT id FROM user_models WHERE user_id = :uid LIMIT 1"),
                                 {"uid": user_id}).fetchall()
            conn.execute(text("INSERT INTO user_models (user_id, name, is_default) "
                              "VALUES (:uid, :n, :d)"),
                         {"uid": user_id, "n": model, "d": 1 if not first else 0})
            conn.commit()
            added = True
    return {"llm_written": True, "model_added": added, "reason": "seeded"}


def vectors_needing_owner(conn) -> dict:
    """补戳清单：**以文档现在的主人为准**，不再以"文档还没主人"为准（终审 advisory ①）。

    阶段一写的是 `WHERE d.user_id IS NULL`，于是 `backfill_documents` 提交之后、
    `stamp_vector_owner` 跑完之前挂掉 ⇒ 下次开机这条 SELECT 返回空集，那批向量**永远**补不上戳。
    换成"所有有主人的向量都进清单"，幂等就交给 Chroma 侧的"已戳就跳过"，崩溃窗口一次开机自愈。
    代价：每次开机多一次全量 id 的 `get()`（基线 4 父 + 10 子，见 tests/test_chroma_data.py，只读 metadata）。

    真库上这两列存的**就是** Chroma 的 id（2026-10-04 已 live 验过：用它删向量，
    计数如实下降），所以直接拿它当 get/update 的 ids，不需要任何映射。
    """
    out = {"parent": [], "child": []}
    for key, table in (("parent", "parent_chunks"), ("child", "child_chunks")):
        rows = conn.execute(text(
            f"SELECT c.vector_id, d.user_id FROM {table} c "
            "JOIN documents d ON d.id = c.document_id "
            "WHERE c.vector_id IS NOT NULL AND c.vector_id <> '' AND d.user_id IS NOT NULL"
        )).fetchall()
        out[key] = [(r[0], r[1]) for r in rows]
    return out


def stamp_vector_owner(client, vectors: dict) -> int:
    """把 (向量 id, 主人) 补进 metadata。已戳的一律跳过，**哪怕戳的是别人**——
    迁移只补空，改归属不是它的活。

    为什么不依赖"Chroma 的 update 只补提供的键"这个较新版本的语义：真依赖它的迁移，
    在语义变化时会静默清掉 document_id/parent_id 这类既有 metadata，而那两个键一丢，
    召回与按文档清扫会同时坏掉，且没有任何报错。读回来合并写是最保守的做法。
    """
    from core.vector_store import COLLECTION_CHILD, COLLECTION_PARENT

    total = 0
    for name, rows in ((COLLECTION_PARENT, vectors["parent"]),
                       (COLLECTION_CHILD, vectors["child"])):
        if not rows:
            continue
        collection = client.get_collection(name)
        found = collection.get(ids=[vid for vid, _ in rows], include=["metadatas"])
        owner = {vid: uid for vid, uid in rows}
        to_update, metadatas = [], []
        for vid, meta in zip(found["ids"], found["metadatas"]):
            meta = meta or {}
            if meta.get("user_id") not in (None, ""):
                # 已戳就跳过，**哪怕戳的是别人**：迁移只补空，改归属不是它的活
                # （Interfaces 那句"已戳过的跳过"就是这个意思）。这一格同时让
                # "每次开机重跑"退化成一次只读扫描，也是新清单敢包含已归户向量的前提。
                continue
            to_update.append(vid)
            metadatas.append({**meta, "user_id": str(owner[vid])})
        if to_update:
            collection.update(ids=to_update, metadatas=metadatas)
            total += len(to_update)
    return total


def run_migrations(engine, chroma_client, config) -> dict:
    """lifespan 唯一入口。返回一份可直接进日志的汇总，不返回秘密（没有令牌、没有哈希、没有 api_key）。

    第三个参数从阶段一的 `password: str` 换成 `config`：步骤 4 要读三个种子键，
    再多加一个形参就是第五件要记顺序的事——`Config` 就在那儿，直接吃它。
    """
    with engine.connect() as conn:
        added = ensure_columns(conn)
        indexes = ensure_indexes(conn)   # 顺序硬要求：列还没加出来就建索引会当场炸
        # ⑤ 的守卫列 + 唯一索引：与上一行同属"补 DDL"这一族，且必须早于 `seed_default_llm`——
        # 那一步会按"名单为空"新插一枚 `is_default=1`，守卫要先在位，才有引擎替你把关。
        guard = ensure_single_default_guard(conn)
        user_id = ensure_default_user(conn, config.DEFAULT_USER_PASSWORD)
        docs = backfill_documents(conn, user_id)
        chats = backfill_chat_history(conn, user_id)
        # 索引 → 归户 → 外键，这三步的相对位置是钉死的：
        # ① 外键晚于索引，否则 InnoDB 替缺索引的列自建一枚（名字就是约束名），我们那枚再补一次；
        # ② 外键晚于孤儿归户，否则 ALTER 回 errno 1452，而 lifespan 不兜异常 ⇒ 后端起不来。
        orphans = reclaim_orphaned_owners(conn, user_id)
        foreign_keys = ensure_foreign_keys(conn)
        seed = seed_default_llm(conn, user_id, config.OPENAI_API_KEY,
                                config.OPENAI_BASE_URL, config.LLM_MODEL)
        # 补戳清单现在读的是"有主人的向量"，必须在归户之后：顺序一反，第一次开机就拿到空集
        pending = vectors_needing_owner(conn)
    # 补戳放在连接之外：Chroma 那边可能是一次几秒的只读扫描，别把 MySQL 连接摁在它上面
    vectors = stamp_vector_owner(chroma_client, pending)
    summary = {"columns_added": added, "indexes_added": indexes,
               "single_default_guard": guard,
               "orphan_rows_reclaimed": orphans,
               "foreign_keys_added": foreign_keys,
               "default_user_id": user_id, "documents_claimed": docs,
               "chat_rows_claimed": chats,
               "llm_seeded": seed["llm_written"], "model_seeded": seed["model_added"],
               "seed_reason": seed["reason"],
               "vectors_stamped": vectors}
    logger.info("迁移完成: %s", summary)   # summary 里没有 api_key：多一个键就多一次泄漏机会
    return summary
