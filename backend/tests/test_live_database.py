"""真 MySQL 上的回归（spec 九节的 live 组）。

`-m "not live"` 会整组跳过：这里的每一条都要连真库，探针数据一律在 finally 里删干净
（`probe` 退文档、`probe_user` 退账号），所以同一台机器上连跑两遍都绿，
也不会把 migration 基线带偏——那份计数由 `test_chroma_data.py` 的 `PARENT_COUNT`/`CHILD_COUNT` 钉住。
"""
import json
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta

import pytest
from config.config import Config
from core.database import DatabaseManager
from schemas.common import Reference

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def db():
    """连接探测：没库就 skip 而不是 fail（无 MySQL 的环境也要能收集这一组）。"""
    try:
        return DatabaseManager(Config())
    except Exception as exc:  # create_all 是第一处真连接，连不上就整组跳过
        pytest.skip(f"MySQL 不可用：{type(exc).__name__}: {exc}")


@pytest.fixture(scope="module")
def probe_user(db):
    """live 判据自己的账号：与 default@local 分开，隔离才测得出来。

    口令现造现丢（不进 .env、不打印）。users 表没有基线计数，但本文件的纪律是
    "探针名带 uuid，不清就每轮长一对永远没人再查的孤儿行"（见 `_drop_probe_account`），
    所以 module 收尾按同一把扫掉：探针文档是各条判据自己退出时删的，到这一步已没有行引用它。
    """
    from core.security import hash_password

    tag = f"live-user-{new_tag()}"
    user = db.create_user(identifier=f"{tag}@local", identifier_type="email",
                          nickname="探针账号", password_hash=hash_password(f"p-{tag}"))
    try:
        yield user
    finally:
        _drop_probe_account(db, user.id)


def default_user_id(db):
    """迁移铸出的默认用户 id：基线那 13 行归它。

    基线池那条判据与白名单那条的**反证**读的都是它的行——探针账号看不到它们才是隔离的证据，
    所以这两处必须拿真 id，不能拿 probe_user.id + 99999 那种假数。
    """
    from sqlalchemy import text

    from core.migrations import DEFAULT_IDENTIFIER

    with db.engine.connect() as conn:
        row = conn.execute(text("SELECT id FROM users WHERE identifier = :i"),
                           {"i": DEFAULT_IDENTIFIER}).fetchone()
    assert row, "默认用户行不存在：lifespan 那次 run_migrations 没跑成"
    return row[0]


def test_new_rows_get_their_own_timestamp(db, probe_user):
    """坑 1 的行为面：两条记录的时间戳不应相同（原 default=datetime.now() 会相等）。"""
    first = db.save_document(filename="probe-a.txt", file_path="", content="a",
                             chunk_count=0, user_id=probe_user.id)
    time.sleep(1.1)
    second = db.save_document(filename="probe-b.txt", file_path="", content="b",
                              chunk_count=0, user_id=probe_user.id)
    try:
        a, b = db.get_document(first, user_id=probe_user.id), db.get_document(second, user_id=probe_user.id)
        assert abs(b.created_at - a.created_at) >= timedelta(seconds=1)
    finally:
        db.delete_document(first)
        db.delete_document(second)


def test_delete_document_cascades_chunks(db, probe_user):
    """回滚依赖 ORM cascade，这里在真库上验它确实把父子块一起带走。"""
    doc_id = db.save_document(filename="probe-c.txt", file_path="", content="c",
                              chunk_count=0, user_id=probe_user.id)
    parent = type("D", (), {"page_content": "父", "metadata": {"parent_id": "probe_parent_0"}})
    child = type("D", (), {"page_content": "子",
                           "metadata": {"parent_id": "probe_parent_0", "child_id": "probe_child_0"}})
    db.save_chunks(doc_id, [parent()], [child()], ["vp"], ["vc"])
    try:
        assert db.delete_document(doc_id) == 1
        assert db.get_document(doc_id, user_id=probe_user.id) is None
    finally:
        db.delete_document(doc_id)


def test_delete_document_reports_missing_rows_as_zero(db, probe_user):
    """补偿路径按"删了几行"判断幽灵状态，不存在的 id 必须是 0 而不是 None/异常。"""
    missing = db.save_document(filename="probe-x.txt", file_path="", content="x",
                               chunk_count=0, user_id=probe_user.id)
    assert db.delete_document(missing) == 1
    assert db.delete_document(missing) == 0
    assert db.get_document(missing, user_id=probe_user.id) is None


def test_get_filenames_by_ids_is_one_in_query(db, probe_user):
    """Task 6 的 IN 查询此前只在 fake 上跑过：真库里钉住 id→filename、缺行不给 None。"""
    plain = db.save_document(filename="probe-d.txt", file_path="", content="d",
                             chunk_count=0, user_id=probe_user.id)
    chinese = db.save_document(filename="探针·中文.txt", file_path="", content="e",
                               chunk_count=0, user_id=probe_user.id)
    try:
        assert db.get_filenames_by_ids([plain, chinese, 10 ** 9]) == {
            plain: "probe-d.txt", chinese: "探针·中文.txt"
        }
        assert db.get_filenames_by_ids([]) == {}
    finally:
        db.delete_document(plain)
        db.delete_document(chinese)


def test_used_chunks_round_trips_through_json(db, probe_user):
    ref = Reference(document_id=999, parent_id="p", filename="中文名.txt", snippet="含 <script> 的片段")
    db.save_chat_history(session_id="probe-live", user_message="问", assistant_message="答",
                         document_ids="999",
                         used_chunks=json.dumps([ref.model_dump()], ensure_ascii=False),
                         user_id=probe_user.id)
    db.save_chat_history(session_id="probe-live", user_message="第二问", assistant_message="第二答",
                         user_id=probe_user.id)
    try:
        rows = db.get_chat_history("probe-live", user_id=probe_user.id)
        # 旧→新：历史窗口 [-3:] 取的就是这个顺序
        assert [r.user_message for r in rows] == ["问", "第二问"]
        assert Reference(**json.loads(rows[0].used_chunks)[0]) == ref
        assert rows[1].used_chunks is None
        assert db.delete_chat_history("probe-live", user_id=probe_user.id) == 2
    finally:
        db.delete_chat_history("probe-live", user_id=probe_user.id)
    assert db.get_chat_history("probe-live", user_id=probe_user.id) == []


def test_emoji_survives_the_history_round_trip(db, probe_user):
    """4 字节字符必须写得进、读得出：连接串回退成 `charset=utf8` 时这条会红。

    表是 utf8mb4，但 PyMySQL 按连接串的 charset 协商**会话**字符集——utf8 即 utf8mb3，
    只装得下 3 字节。千问很爱在回答里带 😊，于是 INSERT 撞 MySQL 1366 Incorrect string
    value，整轮历史落不进去：用户先看到答案逐字上屏，接着弹一条"保存对话历史失败"，
    刷新后这一轮凭空消失。2026-10-03 换 flash 模型后第一次真正生成成功才暴露——
    此前全在 LLM 那一步 error，写历史那行从未执行过。
    """
    question = "用一个表情符号跟我打个招呼 😀"
    answer = "你好 😀 😊 ✅ 🚀"  # 中文与 4 字节字符混排
    db.save_chat_history(session_id="probe-emoji", user_message=question,
                         assistant_message=answer, user_id=probe_user.id)
    try:
        rows = db.get_chat_history("probe-emoji", user_id=probe_user.id)
        assert [(r.user_message, r.assistant_message) for r in rows] == [(question, answer)]
        assert db.delete_chat_history("probe-emoji", user_id=probe_user.id) == 1
    finally:
        db.delete_chat_history("probe-emoji", user_id=probe_user.id)
    assert db.get_chat_history("probe-emoji", user_id=probe_user.id) == []


def test_deleting_a_parent_chunk_takes_its_children_and_hides_the_document(db, probe_user):
    """删块这条路在真库上的四条判据，fake 一条都给不出：ORM cascade、重算的计数、归零隐存、联合定位。

    cascade 只在 `session.delete(ORM对象)` 这条路上生效，写成 `delete(synchronize_session=...)`
    的批量删就带不走子行——那种写法在 fake 上照样"过"，因为 fake 根本没有第二张表。
    """
    doc_id = db.save_document(filename="probe-parent.txt", file_path="", content="正文",
                              chunk_count=3, user_id=probe_user.id)
    parents = [type("D", (), {"page_content": f"父{i}",
                              "metadata": {"parent_id": f"probe_p_{i}"}})() for i in (0, 1)]
    children = [
        type("D", (), {"page_content": "子0", "metadata": {"parent_id": "probe_p_0", "child_id": "probe_c_0"}})(),
        type("D", (), {"page_content": "子1", "metadata": {"parent_id": "probe_p_0", "child_id": "probe_c_1"}})(),
        type("D", (), {"page_content": "子2", "metadata": {"parent_id": "probe_p_1", "child_id": "probe_c_2"}})(),
    ]
    db.save_chunks(doc_id, parents, children, ["vp0", "vp1"], ["vc0", "vc1", "vc2"])
    try:
        plan = db.plan_chunk_deletion(doc_id, "probe_p_0", user_id=probe_user.id)
        # 向量 id 必须在删行之前交出去，而子块的 vector_id 只能从关系里捞
        assert plan["parent_vector_id"] == "vp0"
        assert sorted(plan["child_vector_ids"]) == ["vc0", "vc1"]

        assert db.delete_parent_chunk(doc_id, "probe_p_0", user_id=probe_user.id) == {
            "deleted_children": 2, "chunk_count": 1, "document_hidden": False}
        # 重算而非 chunk_count - 2：库里历史漂移时减法会算出负数，重算顺手把它修回来
        assert db.get_document(doc_id, user_id=probe_user.id).chunk_count == 1
        assert db.get_document(doc_id, user_id=probe_user.id).is_active is True

        # 归属是第三道钥匙，而且**只有此刻**这条判据有牙齿：probe_p_1 还在库里，
        # 换个人拿逐字相同的 (document_id, parent_id) 必须查不到、也删不动——
        # 这里的 None 不可能是"行已经删过"给的。
        assert db.plan_chunk_deletion(doc_id, "probe_p_1", user_id=probe_user.id + 99999) is None
        assert db.delete_parent_chunk(doc_id, "probe_p_1", user_id=probe_user.id + 99999) is None

        assert db.delete_parent_chunk(doc_id, "probe_p_1", user_id=probe_user.id) == {
            "deleted_children": 1, "chunk_count": 0, "document_hidden": True}
        assert db.get_document(doc_id, user_id=probe_user.id).is_active is False
        # 列表与计数都读 is_active：0 块的文档留在列表里是个选了就报错的死条目
        assert doc_id not in [d.id for d in db.get_all_documents(user_id=probe_user.id)]

        # 联合定位：parent_id 单独不是钥匙——跨文档与已删的都得是 None，端点才能只回一个 404
        assert db.plan_chunk_deletion(doc_id, "probe_p_0", user_id=probe_user.id) is None
        assert db.plan_chunk_deletion(10 ** 9, "probe_p_1", user_id=probe_user.id) is None
        assert db.delete_parent_chunk(doc_id, "probe_p_0", user_id=probe_user.id) is None
    finally:
        db.delete_document(doc_id)
    assert db.get_document(doc_id, user_id=probe_user.id) is None


@contextmanager
def probe(db, filename, blocks, *, user_id):
    """造一篇探针文档，交出 `(doc_id, parent_ids)`，退出即 `delete_document`。

    blocks 是 `{parent_id: 子块数}`，也可以是一串 parent_id（每个配一个子块）——
    新加的那两条归属判据只关心 parent_id 有哪些，不想再编一个全 1 的字典。

    parent_id 由调用方带上本次运行的唯一 tag——这些测试连的是共享真库，
    不加隔离的话断言会吃到基线那批块。`user_id` 是必填的：探针文档一律挂 live 组自己的账号
    （`probe_user`）而不是 default@local，归属这条主线在真库上才测得出差别。
    清理从"调用方各自 try/finally 手删"搬进这里的 finally：改完调用点就少了成对删除行，
    而一条都漏不掉（异常路径同样退出）。
    """
    if not isinstance(blocks, dict):
        blocks = {p: 1 for p in blocks}
    # try 从 save_document 成功那一刻就开始：save_chunks 炸了也要把那一行删掉，
    # 否则留下一行已归户的 documents，而 probe_user 收尾会把那个账号删了（_drop_probe_account），
    # 这行就成了谁都不再引用的孤儿——而且它的 parent_id 带着本轮的 uuid，下轮也扫不到它。
    doc_id = db.save_document(filename=filename, file_path="", content="正文",
                              chunk_count=sum(blocks.values()), user_id=user_id)
    try:
        parent_docs = [type("D", (), {"page_content": f"{p} 的正文", "metadata": {"parent_id": p}})()
                       for p in blocks]
        child_docs = [
            type("D", (), {"page_content": f"{p} 的子块 {i}",
                           "metadata": {"parent_id": p, "child_id": f"c_{p}_{i}"}})()
            for p, n in blocks.items() for i in range(n)
        ]
        db.save_chunks(doc_id, parent_docs, child_docs,
                       [f"vp_{p}" for p in blocks],
                       [f"vc_{c.metadata['child_id']}" for c in child_docs])
        yield doc_id, list(blocks)
    finally:
        db.delete_document(doc_id)


def new_tag():
    return f"probe{uuid.uuid4().hex[:8]}"


def test_search_parent_chunks_matches_filename_and_content_without_touching_wildcards(db, probe_user):
    """候选池的 SQL 语义只在真 MySQL 上有牙齿：fake 里没有第二张表，通配符也从不生效。"""
    tag = new_tag()
    with (probe(db, f"{tag}甲.txt", {f"{tag}甲_p_0": 2}, user_id=probe_user.id) as (doc_a, _),
          probe(db, f"{tag}乙.pdf", {f"{tag}乙_p_0": 1, f"{tag}乙_p_1": 1},
                user_id=probe_user.id) as (doc_b, _)):
        by_filename = db.search_parent_chunks(user_id=probe_user.id, query=f"{tag}甲")
        assert [r.parent_id for r in by_filename] == [f"{tag}甲_p_0"]
        assert by_filename[0].filename == f"{tag}甲.txt"
        assert by_filename[0].child_count == 2      # GROUP BY 的聚合，不是 documents.chunk_count 那个手写数

        # 只出现在父块正文里的串：证明搜的是 content，不只是文件名
        assert [r.parent_id for r in
                db.search_parent_chunks(user_id=probe_user.id, query=f"{tag}乙_p_1")] == [f"{tag}乙_p_1"]
        assert db.search_parent_chunks(user_id=probe_user.id, query=f"{tag}查无此词") == []

        # 转义的两条活体判据：不转义时 % 会命中这批探针块、_ 会顶掉文件名里那个真实的点
        assert db.search_parent_chunks(user_id=probe_user.id, query=f"{tag}%") == []
        assert db.search_parent_chunks(user_id=probe_user.id, query=f"{tag}甲_txt") == []

        assert [r.parent_id for r in
                db.search_parent_chunks(user_id=probe_user.id, query=tag, suffix="pdf")] == [
            f"{tag}乙_p_0", f"{tag}乙_p_1"]
        assert [r.parent_id for r in
                db.search_parent_chunks(user_id=probe_user.id, query=tag, suffix="txt")] == [f"{tag}甲_p_0"]

        # 排序钉 document_id（创建顺序）：created_at 同批相同，用它排会漂
        assert [r.parent_id for r in db.search_parent_chunks(user_id=probe_user.id, query=tag)] == [
            f"{tag}甲_p_0", f"{tag}乙_p_0", f"{tag}乙_p_1"]
        assert (list(db.search_parent_chunks(user_id=probe_user.id, query=tag, limit=2))
                == list(db.search_parent_chunks(user_id=probe_user.id, query=tag))[:2])


def test_search_parent_chunks_batch_mode_ignores_query_and_survives_commas_in_ids(db, probe_user):
    """hydrate 的通路：批量点查优先于 query/suffix/limit，且含逗号的 parent_id 原样往返。

    parent_id 由清洗后的文件名拼出，逗号是合法字符——所以契约用重复键而不是逗号拼接。
    """
    tag = new_tag()
    weird = f"{tag},带逗号.txt"
    with (probe(db, weird, {f"{weird}_p_0": 1}, user_id=probe_user.id) as (doc_a, _),
          probe(db, f"{tag}丙.txt", {f"{tag}丙_p_0": 1}, user_id=probe_user.id) as (doc_b, _)):
        rows = db.search_parent_chunks(user_id=probe_user.id, query="不存在这个词", suffix="pdf",
                                       parent_ids=[f"{weird}_p_0", f"{tag}丙_p_0"])
        assert sorted(r.parent_id for r in rows) == sorted([f"{weird}_p_0", f"{tag}丙_p_0"])
        # 未知 id 静默少返回：前端 hydrate 拿"少返回"当剪死 id 的唯一信号
        assert db.search_parent_chunks(user_id=probe_user.id,
                                       parent_ids=[f"{tag}早就没了_p_9"]) == []
        # 重复入参只出一行（GROUP BY 挡住 fan-out）
        dup = db.search_parent_chunks(user_id=probe_user.id,
                                      parent_ids=[f"{tag}丙_p_0", f"{tag}丙_p_0"])
        assert [r.parent_id for r in dup] == [f"{tag}丙_p_0"]
        # 批量模式不吃 limit：limit=1 仍应把两个 id 都问回来
        assert len(db.search_parent_chunks(user_id=probe_user.id,
                                           parent_ids=[f"{weird}_p_0", f"{tag}丙_p_0"],
                                           limit=1)) == 2


def test_search_parent_chunks_excludes_hidden_documents(db, probe_user):
    """chunk_count 归零而隐存的文档不该再往弹窗里供块——选了也召回不到，是死条目。"""
    tag = new_tag()
    with probe(db, f"{tag}丁.txt", {f"{tag}丁_p_0": 1, f"{tag}丁_p_1": 1},
               user_id=probe_user.id) as (doc_id, _):
        assert len(db.search_parent_chunks(user_id=probe_user.id, query=tag)) == 2
        db.delete_parent_chunk(doc_id, f"{tag}丁_p_0", user_id=probe_user.id)
        assert len(db.search_parent_chunks(user_id=probe_user.id, query=tag)) == 1
        db.delete_parent_chunk(doc_id, f"{tag}丁_p_1", user_id=probe_user.id)   # 归零 → is_active=False
        assert db.search_parent_chunks(user_id=probe_user.id, query=tag) == []


def test_search_parent_chunks_returns_the_baseline_pool_readable(db):
    """spec 3.4 的基线 smoke：这台机器上候选池有的可返回，且字段齐得够前端渲染。
    钉"非空 + 字段形状"，不钉条数——条数是要随上传变的（migration 门才管那个）。

    读的是 default@local 名下的基线行（Task 3 把那 13 行全归了它），所以这里要的真用户 id
    不是探针账号的——探针账号看这些行才该是空的，那条判据在 test_parent_whitelist_drops_foreign_owners。
    """
    rows = db.search_parent_chunks(user_id=default_user_id(db), limit=200)
    assert rows, "基线库里应有父块（2026-10-07 重钉：4 篇活文档 / 4 个父块）"
    assert all(r.parent_id and r.filename and r.child_count >= 1 for r in rows)


def test_document_ids_for_parents_reverse_lookup_is_ordered_deduped_and_silent_on_miss(db, probe_user):
    """历史列仍写 document_ids，靠这一步补齐。fake 给不出"库里真没有这个块"的形状。"""
    tag = new_tag()
    with (probe(db, f"{tag}戊.txt", {f"{tag}戊_p_0": 1, f"{tag}戊_p_1": 1},
                user_id=probe_user.id) as (doc_a, _),
          probe(db, f"{tag}己.docx", {f"{tag}己_p_0": 1}, user_id=probe_user.id) as (doc_b, _)):
        # 顺序=入参顺序（不是 document_id 顺序）：历史里"用了哪些文档"该保留挑选的叙述顺序
        assert db.document_ids_for_parents([f"{tag}己_p_0", f"{tag}戊_p_1", f"{tag}戊_p_0"]) == [doc_b, doc_a]
        # 同文档的两个块 → 一个 id，落库不出现 "9,9"
        assert db.document_ids_for_parents([f"{tag}戊_p_0", f"{tag}戊_p_1"]) == [doc_a]
        assert db.document_ids_for_parents([f"{tag}没这个块_p_0"]) == []
        assert db.document_ids_for_parents([]) == []


def test_new_document_carries_its_owner(db, probe_user):
    """写入侧归属 + 读侧过滤一次跑完：别人拿同一个 id 也查不到。"""
    tag = f"own-{new_tag()}"
    doc_id = db.save_document(filename=f"{tag}.txt", file_path="", content="x",
                              chunk_count=0, user_id=probe_user.id)
    try:
        assert db.get_document(doc_id, user_id=probe_user.id).id == doc_id
        other = db.get_document(doc_id, user_id=probe_user.id + 99999)
        assert other is None, "越权取到了别人的文档：WHERE 里那道 user_id 没生效"
        assert doc_id in [d.id for d in db.get_all_documents(user_id=probe_user.id)]
        assert db.get_all_documents(user_id=probe_user.id + 99999) == [] or all(
            d.id != doc_id for d in db.get_all_documents(user_id=probe_user.id + 99999))
    finally:
        db.delete_document(doc_id)


def test_parent_whitelist_drops_foreign_owners(db, probe_user):
    """owned_parent_ids 是 Task 5 那道 404 的底座，所以它必须在真库上先站住。

    两条对照查询（spec 7.1 报数口径）：自己的 id 查得到、别人的查不到——单看"空结果"
    分不清"过滤生效"和"根本没这条行"。
    """
    with probe(db, f"whitelist-{new_tag()}.txt", ["甲"], user_id=probe_user.id) as (doc_id, pids):
        assert db.owned_parent_ids(pids, user_id=probe_user.id) == pids
        assert db.owned_parent_ids(pids, user_id=probe_user.id + 99999) == []

    # 反证：default 用户名下的 parent_id 对探针账号必须不可见。
    # 拿 id 只能走 search_parent_chunks——ORM 行在方法返回时 session 已关，
    # 这时访问 doc.parent_chunks 会抛 DetachedInstanceError（懒加载需要活的 session）。
    theirs = [r.parent_id for r in db.search_parent_chunks(user_id=default_user_id(db), limit=200)]
    assert theirs, "default 用户名下取不到任何父块：反证没有输入，这条判据等于没跑"
    assert db.owned_parent_ids(theirs, user_id=probe_user.id) == []


def _drop_probe_account(db, user_id):
    """删掉探针账号：先 auth_tokens 与 user_models 再 users（前两者对后者有外键）。

    生产代码里没有 delete_user——Task 2 用不上，为一条测试加一个只给测试用的删除口是 YAGNI，
    所以清理留在测试侧：这三张表没有基线计数钉着，但探针名带 uuid，不清就每轮长一对
    永远没人再查的孤儿行，共享库里攒的是垃圾而不是证据。

    阶段三 ④ 之后 `documents` / `chat_history` 也带上了对 users 的外键（RESTRICT）：探针名下
    漏删的行不再只是垃圾，会让这次 `DELETE FROM users` 当场抛 IntegrityError。这是想要的方向——
    漏删从静默变响亮。（也正是这个原因，本文件每条 live 判据都在自己的 finally 里删掉探针行。）
    """
    from core.database import AuthToken, User, UserModel

    session = db.get_session()
    try:
        session.query(AuthToken).filter(AuthToken.user_id == user_id).delete()
        session.query(UserModel).filter(UserModel.user_id == user_id).delete()
        session.query(User).filter(User.id == user_id).delete()
        session.commit()
    finally:
        session.close()


def test_account_methods_round_trip_on_real_mysql(db):
    """join + expires_at 那两条 SQL 语义 fake 给不出证据：这里钉真库上的成功与过期。"""
    from core.security import hash_password, hash_token, new_token

    tag = f"probe-{new_tag()}"
    user = db.create_user(identifier=f"{tag}@local", identifier_type="email",
                          nickname="探针", password_hash=hash_password("probe-pass"))
    token = new_token()
    try:
        db.create_token(user_id=user.id, token_hash=hash_token(token),
                        expires_at=datetime.now() + timedelta(days=1))
        assert db.get_user_by_token(hash_token(token)).id == user.id
        assert db.count_users() >= 1

        expired = f"{tag}-expired"
        db.create_token(user_id=user.id, token_hash=expired,
                        expires_at=datetime.now() - timedelta(seconds=1))
        assert db.get_user_by_token(expired) is None, "过期令牌仍能换回用户：expires_at 那道滤条件没生效"

        assert db.delete_token(hash_token(token)) == 1
        assert db.get_user_by_token(hash_token(token)) is None
        assert db.delete_token(hash_token(token)) == 0, "重复登出不该报第二行"
    finally:
        _drop_probe_account(db, user.id)
    assert db.get_user_by_id(user.id) is None, "探针账号没清干净：共享库残留"


def test_identifier_unique_on_real_mysql(db):
    """`users.identifier` 的 unique 是 DDL 层事实，只有真库能证。"""
    from sqlalchemy.exc import IntegrityError

    from core.security import hash_password

    tag = f"dup-{new_tag()}"
    user = db.create_user(identifier=f"{tag}@local", identifier_type="email",
                          nickname="甲", password_hash=hash_password("probe-pass"))
    try:
        with pytest.raises(IntegrityError):
            db.create_user(identifier=f"{tag}@local", identifier_type="email",
                           nickname="乙", password_hash=hash_password("probe-pass"))
        # 不补一次空 rollback：create_user 自己的 except 已经 rollback、finally 已经 close，
        # 再 get_session() 只会漏一条没人 close 的连接
        assert db.get_user_by_identifier(f"{tag}@local").nickname == "甲", "第二行撞库了？unique 没挡住"
    finally:
        _drop_probe_account(db, user.id)
    assert db.get_user_by_id(user.id) is None


@pytest.mark.live
def test_migration_columns_are_present_and_the_second_pass_is_quiet(db):
    """`ADD COLUMN` 的真语义只有真库能证，而这条判据钉的是"第二遍零 ALTER"。

    这里绝不主动触发第一遍：测试不许改共享库的结构（基线判据靠它）。列的存在本身就是
    证据——它只可能由 lifespan 那次 run_migrations 补出来。索引同理：spec 2.2 要的
    `idx_documents_user_id` 只有迁移会去建，`SHOW INDEX` 的行数在两次 ensure_indexes
    前后相等是它幂等的证据，也是全计划里唯一直接查已部署 schema（而非 ORM 元数据）的索引判据。

    外键与孤儿行走同一条纪律：先读 `information_schema` 确认 lifespan 已经建好、且库里没有
    指向不存在账号的行，然后才敢拿 `ensure_foreign_keys` / `reclaim_orphaned_owners` 验幂等
    （这两步在没迁移过的库上会真的发 ALTER / UPDATE）。`KEY_COLUMN_USAGE` 里必须是**一枚**：
    两枚说明补外键的写法按约束名问，那会在每个新库上叠一枚重复外键。
    """
    from sqlalchemy import text

    from core import migrations

    with db.engine.connect() as conn:
        assert migrations.column_exists(conn, "documents", "user_id"), (
            "documents.user_id 不存在：服务没重启过，或迁移没接进 lifespan"
        )
        before = len(conn.execute(text("SHOW COLUMNS FROM documents")).fetchall())
        assert migrations.ensure_columns(conn) == []
        assert migrations.ensure_columns(conn) == []
        after = len(conn.execute(text("SHOW COLUMNS FROM documents")).fetchall())

        assert migrations.index_exists(conn, "documents", "idx_documents_user_id"), (
            "idx_documents_user_id 不存在：ensure_indexes 没进 run_migrations，"
            "或者它压根没跑起来"
        )
        index_before = len(conn.execute(text("SHOW INDEX FROM documents")).fetchall())
        assert migrations.ensure_indexes(conn) == []
        assert migrations.ensure_indexes(conn) == []
        index_after = len(conn.execute(text("SHOW INDEX FROM documents")).fetchall())

        # 外键与孤儿行（阶段三 ④）。这两格**先 assert 再调用**，顺序是有讲究的：
        # `ensure_foreign_keys` / `reclaim_orphaned_owners` 在没迁移过的库上会真发
        # ALTER / UPDATE——共享库的结构与数据归 lifespan 管，测试只许读。
        # 所以先读 information_schema 确认"lifespan 那次已经建好了"，再拿这两步验幂等（零副作用）。
        for table in ("documents", "chat_history"):
            assert migrations.foreign_key_exists(conn, table, "user_id", "users"), (
                f"{table}.user_id 上没有外键：服务没重启过，迁移的 ensure_foreign_keys 没跑起来"
            )
            assert migrations.orphaned_owner_count(conn, table, "user_id") == 0, (
                f"{table} 上还有指向不存在账号的行：ADD CONSTRAINT 会被 MySQL 回 1452 拒收"
            )
        fk_rows_before = len(conn.execute(text(
            "SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'documents' "
            "AND COLUMN_NAME = 'user_id' AND REFERENCED_TABLE_NAME = 'users'")).fetchall())
        assert migrations.ensure_foreign_keys(conn) == []
        assert migrations.ensure_foreign_keys(conn) == []
        assert migrations.reclaim_orphaned_owners(conn, default_user_id(db)) == []
        fk_rows_after = len(conn.execute(text(
            "SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'documents' "
            "AND COLUMN_NAME = 'user_id' AND REFERENCED_TABLE_NAME = 'users'")).fetchall())
    assert after == before, "两次 ensure_columns 之间列数变了：幂等破了"
    assert index_after == index_before, "两次 ensure_indexes 之间索引行数变了：幂等破了"
    assert (fk_rows_before, fk_rows_after) == (1, 1), (
        f"documents.user_id 上的外键数 {fk_rows_before}→{fk_rows_after}：不是 1 枚（按约束名查的写法"
        "会在每个新库上叠一枚重复外键，InnoDB 不拦）"
    )


@pytest.mark.live
def test_default_user_exists_and_owns_the_baseline_documents(db):
    """spec 7.3 的第 5 条判据（旧数据归位 SQL 直查）搬进自动化：基线 13 行全归 default。

    13 是 documents 的**物理行数**（4 篇活 + 9 篇删块删到 is_active=0 的隐存行），不是
    `/api/health` 那个活文档计数——归户 SQL 是 `WHERE user_id IS NULL`，隐存行同样要归户。

    这条不成立就说明 lifespan 那次 run_migrations 没跑成——手动起服务时最容易漏。
    """
    from sqlalchemy import text

    from core.migrations import DEFAULT_IDENTIFIER

    with db.engine.connect() as conn:
        row = conn.execute(text(
            "SELECT id FROM users WHERE identifier = :i"), {"i": DEFAULT_IDENTIFIER}).fetchall()
        assert row, "默认用户行没建出来：迁移没跑或跑在 create_all 之前"
        default_id = row[0][0]
        owned = conn.execute(text(
            "SELECT COUNT(*) FROM documents WHERE user_id = :u"), {"u": default_id}).fetchone()[0]
        unowned = conn.execute(text(
            "SELECT COUNT(*) FROM documents WHERE user_id IS NULL")).fetchone()[0]
    assert unowned == 0, f"还有 {unowned} 篇文档无主，归户那步没做完"
    assert owned == 13, f"基线 13 行应全归 default，实得 {owned}"


@pytest.mark.live
def test_foreign_key_restricts_deleting_a_user_who_still_owns_rows(db):
    """RESTRICT 的行为面只有真库能证：假连接不会拦，MySQL 回 errno 1451。

    为什么不写 `ON DELETE CASCADE`（见 core/migrations.py 的 add_foreign_key）：级联删得掉
    `documents` 行，删不掉 Chroma 里的向量——"行没了、向量还能被召回"正是本仓一路在防的
    脏数据面。拦下来、逼调用方两头删，才是这里想要的默认。
    探针账号自己造、自己删（不复用 `probe_user`）：这条要**删**账号，删成功的那一路也必须
    只删到自己；`default@local` 一次都不许出现在 DELETE 里。
    """
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    from core.security import hash_password

    tag = f"live-fk-{new_tag()}"
    user = db.create_user(identifier=f"{tag}@local", identifier_type="email",
                          nickname="外键探针", password_hash=hash_password(f"p-{tag}"))
    doc_id = db.save_document(filename=f"{tag}.txt", file_path="", content="x",
                              chunk_count=0, user_id=user.id)
    try:
        with db.engine.connect() as conn:
            try:
                conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user.id})
                conn.commit()
            except IntegrityError:
                conn.rollback()
            else:
                pytest.fail(f"删掉了仍持有文档的账号 id={user.id}：外键没起作用，RESTRICT 没生效")
        assert db.get_document(doc_id, user_id=user.id) is not None, (
            "DELETE 被拦下了却把文档也带走了：那不是 1451，是别的动静"
        )

        # 反证的另一半：行没了就删得掉——拦的是"还有主人名下有东西"，不是"这个账号删不掉"。
        db.delete_document(doc_id)
        with db.engine.connect() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user.id})
            conn.commit()
        assert db.get_user_by_id(user.id) is None
    finally:
        db.delete_document(doc_id)          # 幂等：已删则 0
        _drop_probe_account(db, user.id)    # 同上：已删则删不到行


# 假 key／假路由（计划指定的探针串，不是任何真凭证）。提成模块级常量是为了**单独成句比对**：
# 与别的断言用 `and` 合并时 pytest 会把整条表达式的实际值打出来，将来这一格换成真凭证，
# 日志与终端里就会多出它。拆开写还能在红的时候直接看出是哪一格漂了。
PROBE_API_KEY = "sk-probe-abcdefg1234"
PROBE_BASE_URL = "https://probe.example/v1"


def test_user_settings_round_trip(db, probe_user):
    """两列 + 名单四种行级操作在真库上的语义。fake 给不出 unique 键与 is_default 互斥的证据。"""
    assert db.update_user_profile(probe_user.id, nickname="改名了") == 1
    assert db.update_user_llm(probe_user.id, PROBE_API_KEY, PROBE_BASE_URL) == 1
    fresh = db.get_user_by_id(probe_user.id)
    assert fresh.nickname == "改名了"
    assert fresh.api_key == PROBE_API_KEY
    # base_url 也要回读：update_user_llm 一次写两格，只回读 api_key 时"`_update_user` 的 dict
    # 少写 base_url"这一整类退化测不出来（实测离线与 live 双双全绿），而 database.py:632-634
    # 那句 docstring 论证的恰恰是"key 与路由必须一起写，否则造出必 401 上游的半套配置"。
    assert fresh.base_url == PROBE_BASE_URL

    assert db.add_user_model(probe_user.id, "probe-max") is True
    assert db.add_user_model(probe_user.id, "probe-max") is False      # unique 键那一条
    assert db.add_user_model(probe_user.id, "probe-mini") is True
    # 阶段二 Task 2 的新行为：**首个入名单的模型自动置默认**。probe-max 一进就是 True，
    # probe-mini 因为是第二个所以是 False —— 这一句就是那条逻辑的直接判据：
    # 删掉 add_user_model 里算 is_first 那两行，红的就是这里。
    # is_first 判空用的是**另一次不带 name 过滤**的查询；退化成复用上面那次带 name 的 hit
    # 会让 probe-mini 也被标成默认，同样只在这里红（离线侧看不出，fake 自己算的 not rows）。
    assert db.list_user_models(probe_user.id) == [("probe-max", True), ("probe-mini", False)]

    # 前置态（"名单里已经有一个人是默认"）现在由上面那次 add 自己造出来了，所以这一次
    # set_default(probe-max) 退成**同值重设**：它证的是"目标在名单里时回 True、且不把别人
    # 的标记写坏"（这里被洗的是 probe-mini 的 False，写回 False 观察不到差别），
    # 不再负责造前置态。真正带清场证据的是下面第二次设默认。
    assert db.set_default_user_model(probe_user.id, "probe-max") is True
    assert db.list_user_models(probe_user.id) == [("probe-max", True), ("probe-mini", False)]
    # 第二次设默认才是清场句的证据：probe-max 必须由 True 翻回 False。
    # 前置态由 add 立起来之后，把 set_default_user_model 里的清场句整段删掉就会红在这里。
    assert db.set_default_user_model(probe_user.id, "probe-mini") is True
    assert db.list_user_models(probe_user.id) == [("probe-max", False), ("probe-mini", True)]
    assert db.set_default_user_model(probe_user.id, "早没了") is False

    # 第三枚：名字**字母序排最前、添加序排最后**，两种排序才分得开。
    # 上面两枚 probe-max/probe-mini 的字母序恰好等于插入序，把 order_by(UserModel.id)
    # 改成 order_by(UserModel.name) 这几条断言逐字不变 ⇒ 测不出来（实测全绿）。
    # "按添加序"不是洁癖：spec 3.4 的"没有 default 就取名单第一个"是问答链的兜底，
    # 排序口径漂了，用户在界面上选中的和实际打出去的就对不上。
    assert db.add_user_model(probe_user.id, "a-probe-later") is True
    assert db.list_user_models(probe_user.id) == [("probe-max", False), ("probe-mini", True),
                                                  ("a-probe-later", False)]

    # 同值重写（原样重存同一套 key/路由）回 1：这是本机实测值，口径与它的来由见
    # `update_user_llm` 的 docstring——rowcount 数的是"匹配到的行"，不是"真被改的行"。
    # 把它钉成断言，是为了让"哪天换了驱动/客户端标志"这件事在这里先红，而不是让端点悄悄长出 404。
    assert db.update_user_llm(probe_user.id, PROBE_API_KEY, PROBE_BASE_URL) == 1

    assert db.delete_user_model(probe_user.id, "probe-mini") == 1      # 删的是当前默认
    # 删默认不自动提升（写入侧不动别人的 is_default），读侧靠"没有 default 就取第一个"兜。
    # 名单顺序仍是添加序：probe-max 在前、a-probe-later 在末。
    assert db.list_user_models(probe_user.id) == [("probe-max", False), ("a-probe-later", False)]
    assert db.delete_user_model(probe_user.id, "probe-mini") == 0      # 幂等：第二次是 0 不是异常


def test_engine_itself_rejects_a_second_default_for_the_same_user(db, probe_user):
    """阶段三 ⑤ 的真库面：「一人至多一枚默认」由 STORED 生成列 + 唯一索引兜，两类写入口都要被拒。

    离线那组（`test_migrations.py`）钉的是"先查再改"这个决策，这里钉它在真 MySQL 上成立。
    本机 scratch 表实测的四格，逐格搬到这里：INSERT 第二枚默认 → 1062；
    **UPDATE 把非默认那枚提升成默认**也 → 1062（只测 INSERT 会漏掉 `set_default` 那条路径，
    而那才是应用层天天在走的一条）；别人的默认不受影响（guard 里带的是 user_id，不是常量 1）；
    非默认行想有几枚有几枚（唯一索引不理 NULL）。

    第一条断言是前置闸门：守卫列没在真库上建起来就在这里红，而不是把"压根没有索引"
    误报成"引擎不管"。真库的 ALTER 由 lifespan 那次 `run_migrations` 发（本机已就位）。
    """
    from sqlalchemy import exc, text

    from core.security import hash_password

    with db.engine.connect() as conn:
        guard = conn.execute(text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'user_models' "
            "AND COLUMN_NAME = 'default_guard' AND GENERATION_EXPRESSION <> ''"
        )).fetchone()
    assert guard, ("真库上 default_guard 不是生成列（或压根没这列）：迁移那一步没落，"
                   "下面三条只是在没有约束的表上自说自话")

    assert db.add_user_model(probe_user.id, "p5-keep") is True
    # 上一轮 round_trip 把默认那枚删掉了，这里**显式**立一枚：不靠测试执行顺序造前置态
    assert db.set_default_user_model(probe_user.id, "p5-keep") is True
    # 这一枚是**非默认**行（名单已有人是默认），它既是"非默认行随便加"的证据，
    # 也是下面那次 UPDATE 提升的对象——先插后提升，反过来那句 UPDATE 匹配 0 行、
    # `pytest.raises` 会红在夹具身上而不是引擎身上。
    assert db.add_user_model(probe_user.id, "p5-keep-other") is True
    before = db.list_user_models(probe_user.id)

    other = db.create_user(identifier=f"live-p5b-{new_tag()}@local", identifier_type="email",
                           nickname="探针账号乙", password_hash=hash_password("p-unusable"))
    try:
        with db.engine.connect() as conn:
            with pytest.raises(exc.IntegrityError) as by_insert:
                conn.execute(text("INSERT INTO user_models (user_id, name, is_default) "
                                  "VALUES (:u, :n, 1)"),
                             {"u": probe_user.id, "n": "p5-second-default"})
            conn.rollback()
        # 只盯错误号会漏掉"被别的约束拦下"（比如 unique(user_id,name) 撞名），所以名字也要对
        assert "1062" in str(by_insert.value)
        assert "uq_user_models_single_default" in str(by_insert.value)

        with db.engine.connect() as conn:
            with pytest.raises(exc.IntegrityError) as by_update:
                conn.execute(text("UPDATE user_models SET is_default = 1 "
                                  "WHERE user_id = :u AND name = :n"),
                             {"u": probe_user.id, "n": "p5-keep-other"})
            conn.rollback()
        assert "1062" in str(by_update.value)

        # 另一个人立默认是**该允许的**：guard 值 = user_id，两人各一枚时是两枚不同的键
        with db.engine.connect() as conn:
            conn.execute(text("INSERT INTO user_models (user_id, name, is_default) "
                              "VALUES (:u, :n, 1)"), {"u": other.id, "n": "p5-b-default"})
            conn.commit()

        # 同一人再加一枚非默认：唯一索引不管 NULL，写成 `unique(user_id, is_default)`
        # 会把这一句直接拦死（那条路实测建得出来，但语义错了）
        assert db.add_user_model(probe_user.id, "p5-third") is True

        models = db.list_user_models(probe_user.id)
        assert [n for n, d in models if d] == ["p5-keep"], f"名单里冒出多枚默认：{models}"
        # 相对增长而不是绝对条数：probe_user 是 module 级共享账号，别的判据在它名下
        # 加过几行数不出一个稳定的常数，写死就等于把这条判据绑在测试执行顺序上。
        assert len(models) == len(before) + 1, f"第三枚非默认没进去：{before} → {models}"
    finally:
        _drop_probe_account(db, other.id)
        with db.engine.connect() as conn:          # 万一守卫没生效，那次"该失败"的 INSERT 会留下行
            conn.execute(text("DELETE FROM user_models WHERE name = 'p5-second-default'"))
            conn.commit()


def test_add_user_model_retries_as_non_default_when_the_guard_race_wins(db, probe_user,
                                                                        monkeypatch):
    """⑤ 的新分支要有牙：并发下「判空读到旧快照 → 插入撞守卫键」不能把用户挡在门外。

    不用真线程复现竞态（要稳定赢很难），改成把 `get_session` 包一层：只把
    `add_user_model` 里**判空那一次**查询的 `first()` 钉成 None，等价于"这个事务的快照里
    名单是空的"，而真表里已经有一枚默认。于是 INSERT 带着 `is_default=1` 出门，
    被 `uq_user_models_single_default` 当场 1062。

    没有那个分支（`except IntegrityError` 直接 `return False`）时这里红在返回值上：
    端点会对一个**名单里根本没有的**名字回 409「该模型已在你的名单里」——那是 ⑤ 自己带来的谎，
    而且是双击两次"添加"就能撞到的那种（两个不同名字，第二个也以为自己是第一个）。
    """
    real_factory = db.get_session
    spoofed = []                        # 命中钩子的那次查询的 SQL，同时当"只 spoof 一次"的开关

    class _StaleSnapshot:
        """把「只按 user_id 过滤」那一次 first() 改成 None，其余逐字转给真会话。

        认领条件是 SQL 文本而不是调用次数：`add_user_model` 里查重那次带 `user_models.name`、
        判空那次只带 `user_models.user_id`。按次数认领会被将来的一次查询重排无声改掉，
        按行号认领会更早就失效。
        """

        def __init__(self, real):
            self._real = real

        def query(self, *args, **kwargs):
            inner = self._real.query(*args, **kwargs)

            class _Q:
                def filter(self, *fa, **fk):
                    q = inner.filter(*fa, **fk)

                    class _F:
                        def first(_self):
                            sql = str(q).lower()
                            if (not spoofed and "user_models.user_id" in sql
                                    and "user_models.name" not in sql):
                                spoofed.append(sql)
                                return None
                            return q.first()

                        def __getattr__(self, n):
                            return getattr(q, n)

                    return _F()

                def __getattr__(self, n):
                    return getattr(inner, n)

            return _Q()

        def __getattr__(self, n):
            return getattr(self._real, n)

    assert db.add_user_model(probe_user.id, "p5-race-anchor") is True
    assert db.set_default_user_model(probe_user.id, "p5-race-anchor") is True
    monkeypatch.setattr(db, "get_session", lambda: _StaleSnapshot(real_factory()))
    try:
        assert db.add_user_model(probe_user.id, "p5-race") is True, (
            f"撞守卫键之后没把这一枚加成非默认（钩子命中：{spoofed}）")
    finally:
        monkeypatch.undo()

    assert len(spoofed) == 1, f"判空那次查询没被改成旧快照，这条判据是空跑的：{spoofed}"
    models = db.list_user_models(probe_user.id)
    assert "p5-race" in [n for n, _d in models], models
    # 输掉竞争的那一方**不该**抢走默认位：现任默认还是 anchor
    assert [n for n, d in models if d] == ["p5-race-anchor"], f"重试把默认位抢走了：{models}"


def test_empty_profile_update_touches_nothing(db, probe_user):
    """两个字段都没传就该零副作用，而不是把昵称写成 NULL。"""
    before = db.get_user_by_id(probe_user.id).nickname
    assert before, "对照失去输入：探针账号昵称已是空值，这条绿不说明任何事"
    assert db.update_user_profile(probe_user.id) == 0
    assert db.get_user_by_id(probe_user.id).nickname == before
    # 同值重写的实测口径（钉的是**本机这套驱动**的实数，不是 MySQL 的默认行为）：
    # 裸 MySQL 的 UPDATE affected_rows 只数"真被改变"的行 ⇒ 这里本该回 0；但本项目走
    # SQLAlchemy 的 MySQL 方言，它在连接时硬编码或上 CLIENT_FOUND_ROWS
    # （site-packages/sqlalchemy/dialects/mysql/base.py:709-715 与 mysqldb.py:244-251），
    # rowcount 的口径被标准化成"匹配到的行数" ⇒ 实测回 1。口径全文见 update_user_llm 的 docstring。
    assert db.update_user_profile(probe_user.id, nickname=before) == 1
    assert db.get_user_by_id(probe_user.id).nickname == before


def test_chat_history_is_invisible_to_another_user(db):
    """跨用户证据只能来自真库：fake 那三枚桩不真过滤，WHERE 少写一句在它们身上照样绿。

    A 写得进、读得出；B 读回空、删掉 0 行。B 的删除返回 0 而不是 1 是本条的牙——
    "GET 加了过滤、DELETE 忘了"是这类改造最常见的半截交付。
    """
    from core.security import hash_password

    a = db.create_user(identifier=f"hist-a-{new_tag()}@local", identifier_type="email",
                       nickname="甲", password_hash=hash_password("p-a"))
    b = db.create_user(identifier=f"hist-b-{new_tag()}@local", identifier_type="email",
                       nickname="乙", password_hash=hash_password("p-b"))
    sid = f"probe-shared-{new_tag()}"
    try:
        db.save_chat_history(session_id=sid, user_message="甲的问", assistant_message="甲的答",
                             user_id=a.id)
        assert [r.user_message for r in db.get_chat_history(sid, user_id=a.id)] == ["甲的问"]
        assert db.get_chat_history(sid, user_id=b.id) == []
        assert db.delete_chat_history(sid, user_id=b.id) == 0
    finally:
        # 先删行再删账号：真库上 create_all 会把 chat_history.user_id 的 FK 约束建出来，
        # 留着引用行就删不掉 users 那一行（AssertionError 中途抛出时也走这里）
        db.delete_chat_history(sid, user_id=a.id)
        _drop_probe_account(db, a.id)
        _drop_probe_account(db, b.id)
