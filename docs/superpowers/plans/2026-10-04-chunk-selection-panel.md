# 块级文档选择面板 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把知识库面板从"列全部文档 + 勾选文档"改成"只显示已选文档块 + 弹窗挑选（搜索/后缀分类）+ 卡片右上角红叉取消"，问答契约随之从 `document_ids` 换成 `parent_ids`。

**Architecture:** 后端加一条只读端点 `GET /api/documents/chunks`（父块候选池：模糊搜文件名与块内文本、按后缀分类、按 parent_id 批量点查），检索器的元数据过滤字段从 `document_id` 换成 `parent_id`（子块向量本就带 `parent_id`，零数据迁移），落库前用 `parent_id` 反查 `document_id` 写进原来的历史列。前端新增 `useChunkSelection`（localStorage 只存 id）与 `ChunkPickerModal`/`ChunkCard` 两件套，`DocumentPanel` 的知识库区重写，`DocCard` 与 `useDocuments.selectedIds` 退役。

**Tech Stack:** FastAPI + SQLAlchemy 1.x-style query + Pydantic v2 + LangChain/Chroma；Vue 3 `<script setup>` + 原生 CSS + vitest/@vue/test-utils。

**Spec:** `docs/superpowers/specs/2026-10-04-chunk-selection-panel-design.md`（本计划按它论证，逐字引用它的判据；两份必须一起读）

## Global Constraints

- **提交身份**：本机无 `user.name`/`user.email`，每条提交都用 `git -c user.name="31439" -c user.email="31439@local" commit`。**禁止 `--amend`、禁止 `--no-verify`**；一次提交只做一件事，消息用本仓现有的中文 conventional 风格（`feat(backend): …` / `test(frontend): …`）。
- **解释器**：一律用 PATH 上的 `python`（`D:\python\python.exe` 3.12.3）。**不要用** `D:/AI-python/.venv`、也不要用 PyCharm 自动建的 `.venv`（只有 pip）。
- **不动共享配置**：`D:/AI-python/.env` 与 git config 都不改。后端读的是 `backend/.env`，本计划不需要改它。
- **只有一个 uvicorn**：绝不起第二个实例（embedding 模型按进程加载，会撞 os error 1455）。要重启就重启自己起的那一个。
- **基线数据不做外科手术**：`documents 9 / parent_chunks 11 / child_chunks 22`，不删不改不重传；探针数据一律在 `finally` 里清干净。
- **同名重传会撞后端唯一键**（parent_id 由文件名拼出）→ 属已知限制，测试判据一律用新文件名。
- **前端渲染纪律**：**永不用 `v-html`**；颜色一律取 `variables.css` 里的 token（G-4 判据见 Task 5）。
- **文件读写**：涉及本地文件时显式 `encoding="utf-8"`（系统默认 cp936）。
- **后端门禁基线**：`cd backend && python -m pytest -q` = **146 passed / 1 deselected**（本机 MySQL 在跑，live 组真执行；约 2 分 40 秒）；`python -m pytest -m migration -q` = **1 passed**。改完允许条数变多，**不允许任何 failed**。
- **前端门禁基线**：`cd frontend && npm test` = **45 passed（5 文件）**；`npm run build` exit 0。
- **文档修订留痕**：改既有 spec/计划一律用 `> 2026-10-XX 修订` 引用块，不抹原文。

---

### Task 1: 后端只读块查询 `GET /api/documents/chunks`

**Files:**
- Create: `backend/tests/test_chunk_search.py`
- Modify: `backend/schemas/common.py`（加 `snippet_of`）
- Modify: `backend/schemas/documents.py`（加 `ChunkOut`）
- Modify: `backend/core/database.py`（加 `_escape_like` + `search_parent_chunks`，import `func`）
- Modify: `backend/core/rag_system.py:121-137`（`_build_references` 改吃 `snippet_of`）
- Modify: `backend/api/documents.py`（加 `GET /chunks` + `_suffix_of`）
- Modify: `backend/tests/test_live_database.py`（SQL 语义的活体判据）

**Interfaces:**
- Consumes: `Document`/`ParentChunk`/`ChildChunk`/`SNIPPET_LIMIT`（均已存在）。
- Produces:
  - `snippet_of(text: str) -> str`（schemas/common.py）
  - `ChunkOut{parent_id: str, document_id: int, filename: str, suffix: str, snippet: str, child_count: int}`（schemas/documents.py）
  - `DatabaseManager.search_parent_chunks(query="", suffix="", parent_ids=(), limit=50) -> list[Row]`，Row 有 `.parent_id/.document_id/.content/.filename/.child_count`
  - 端点 `GET /api/documents/chunks`

- [ ] **Step 1: 写 `snippet_of` 的失败测试**

创建 `backend/tests/test_chunk_search.py`：

```python
"""块候选池的三件纯函数 + 端点形状。

SQL 语义（LIKE 转义、child_count 聚合、is_active 排除）fake 给不出证据，
那些判据在 tests/test_live_database.py 的 live 组里。
"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from core.database import _escape_like
from main import create_app
from deps import get_db
from schemas.common import SNIPPET_LIMIT, snippet_of
from api.documents import _suffix_of
```

（这一段 import 故意一次写全，Step 2 跑红时红的是"东西不存在"，不是"文件写一半"。）

追加第一批用例：

```python
def test_snippet_of_collapses_whitespace_then_truncates():
    assert snippet_of("  多 行\n\t文本  ") == "多 行 文本"
    long = "字" * (SNIPPET_LIMIT + 30)
    out = snippet_of(long)
    assert out == "字" * SNIPPET_LIMIT + "..."
    assert len(out) == SNIPPET_LIMIT + 3


def test_snippet_of_leaves_short_text_untouched():
    assert snippet_of("恰好") == "恰好"


def test_escape_like_neutralises_the_three_wildcard_characters():
    # 反斜杠先处理：否则它会把随后补上的转义符再转义一遍
    assert _escape_like("50%") == "50\\%"
    assert _escape_like("a_b") == "a\\_b"
    assert _escape_like("c:\\d") == "c:\\\\d"
    assert _escape_like("普通文件名.pdf") == "普通文件名.pdf"


def test_suffix_of_takes_the_last_dot_and_lowercases():
    assert _suffix_of("手册.PDF") == "pdf"
    assert _suffix_of("a.tar.gz") == "gz"
    assert _suffix_of("README") == ""       # 无后缀不该被当成 "README"
    assert _suffix_of(".env") == "env"      # rpartition：点在最前也算后缀
```

- [ ] **Step 2: 跑测试确认它红**

Run: `cd backend && python -m pytest tests/test_chunk_search.py -q`
Expected: collection error — `ImportError: cannot import name 'snippet_of' from 'schemas.common'`（后接 `_escape_like`、`_suffix_of` 同类缺失）。

- [ ] **Step 3: 实现 `snippet_of`**

`backend/schemas/common.py` 在 `SNIPPET_LIMIT = 80` 之后追加：

```python
def snippet_of(text: str) -> str:
    """引用片段与候选池卡片共用这一份截断：压掉换行/制表/多余空格，超长补省略号。

    两处若各写一遍，历史渲染与实时渲染会在"第 80 个字符之后长什么样"上分叉。
    """
    flat = " ".join(text.split())
    return f"{flat[:SNIPPET_LIMIT]}..." if len(flat) > SNIPPET_LIMIT else flat
```

- [ ] **Step 4: `rag_system._build_references` 改吃它**

`backend/core/rag_system.py:10` 的 import 改为 `from schemas.common import Reference, snippet_of`（`SNIPPET_LIMIT` 不再被引用，去掉），`_build_references` 循环体改成：

```python
        for doc in compressed_docs:
            references.append(Reference(
                document_id=int(doc.metadata["document_id"]),
                parent_id=doc.metadata.get("parent_id", ""),
                filename=filenames.get(int(doc.metadata["document_id"]), ""),
                snippet=snippet_of(doc.page_content),
            ))
```

保留原有 `filenames` 一次 IN 查询。跑 `python -m pytest tests/test_rag_system.py -q`，Expected: 全 PASS（`test_chat_snippet_collapses_whitespace_and_truncates_at_limit` 就是这条收口的安全网）。

- [ ] **Step 5: 实现 `_escape_like` 与 `_suffix_of`**

`backend/core/database.py`：第 2 行的 sqlalchemy import 补 `func`（改成 `from sqlalchemy import create_engine, func, Column, ...`），并在 `logger = ...` 之后加：

```python
def _escape_like(raw: str) -> str:
    r"""挡掉 LIKE 的三个元字符。

    参数绑定挡住的是 SQL 注入，挡不住通配符语义：搜索框里的 `%` 是用户真想搜的那个字符，
    不是"任意串"。反斜杠必须最先替换，否则它会把随后补上的转义符再转义一遍。
    """
    return raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
```

`backend/api/documents.py` 在 `_safe_filename` 之后加：

```python
def _suffix_of(filename: str) -> str:
    """后缀取最后一个点之后并小写。rpartition 在没点时返回 ('', '', filename)，
    这时必须给空串——否则 README 会被判成"后缀=README"。"""
    _, dot, ext = filename.rpartition(".")
    return ext.lower() if dot else ""
```

- [ ] **Step 6: 跑纯函数用例确认绿**

Run: `cd backend && python -m pytest tests/test_chunk_search.py -q`
Expected: `4 passed`。

- [ ] **Step 7: 写 `search_parent_chunks` 的 live 失败测试**

追加到 `backend/tests/test_live_database.py` 末尾（`pytestmark = pytest.mark.live` 已在文件头，无需重复；文件顶部 import 补 `import uuid`）：

```python
def probe(db, filename, blocks):
    """造一篇探针文档：blocks 是 {parent_id: 子块数}，返回 doc_id。

    parent_id 由调用方带上本次运行的唯一 tag——这些测试连的是共享真库，
    不加隔离的话断言会吃到基线那 11 个块。调用方负责 finally 里 delete_document。
    """
    doc_id = db.save_document(filename=filename, file_path="", content="正文",
                              chunk_count=sum(blocks.values()))
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
    return doc_id


def new_tag():
    return f"probe{uuid.uuid4().hex[:8]}"


def test_search_parent_chunks_matches_filename_and_content_without_touching_wildcards(db):
    """候选池的 SQL 语义只在真 MySQL 上有牙齿：fake 里没有第二张表，通配符也从不生效。"""
    tag = new_tag()
    doc_a = probe(db, f"{tag}甲.txt", {f"{tag}甲_p_0": 2})
    doc_b = probe(db, f"{tag}乙.pdf", {f"{tag}乙_p_0": 1, f"{tag}乙_p_1": 1})
    try:
        by_filename = db.search_parent_chunks(query=f"{tag}甲")
        assert [r.parent_id for r in by_filename] == [f"{tag}甲_p_0"]
        assert by_filename[0].filename == f"{tag}甲.txt"
        assert by_filename[0].child_count == 2      # GROUP BY 的聚合，不是 documents.chunk_count 那个手写数

        # 只出现在父块正文里的串：证明搜的是 content，不只是文件名
        assert [r.parent_id for r in db.search_parent_chunks(query=f"{tag}乙_p_1")] == [f"{tag}乙_p_1"]
        assert db.search_parent_chunks(query=f"{tag}查无此词") == []

        # 转义的两条活体判据：不转义时 % 会命中这批探针块、_ 会顶掉文件名里那个真实的点
        assert db.search_parent_chunks(query=f"{tag}%") == []
        assert db.search_parent_chunks(query=f"{tag}甲_txt") == []

        assert [r.parent_id for r in db.search_parent_chunks(query=tag, suffix="pdf")] == [
            f"{tag}乙_p_0", f"{tag}乙_p_1"]
        assert [r.parent_id for r in db.search_parent_chunks(query=tag, suffix="txt")] == [f"{tag}甲_p_0"]

        # 排序钉 document_id（创建顺序）：created_at 同批相同，用它排会漂
        assert [r.parent_id for r in db.search_parent_chunks(query=tag)] == [
            f"{tag}甲_p_0", f"{tag}乙_p_0", f"{tag}乙_p_1"]
        assert list(db.search_parent_chunks(query=tag, limit=2)) == list(db.search_parent_chunks(query=tag))[:2]
    finally:
        db.delete_document(doc_a)
        db.delete_document(doc_b)


def test_search_parent_chunks_batch_mode_ignores_query_and_survives_commas_in_ids(db):
    """hydrate 的通路：批量点查优先于 query/suffix/limit，且含逗号的 parent_id 原样往返。

    parent_id 由清洗后的文件名拼出，逗号是合法字符——所以契约用重复键而不是逗号拼接。
    """
    tag = new_tag()
    weird = f"{tag},带逗号.txt"
    doc_a = probe(db, weird, {f"{weird}_p_0": 1})
    doc_b = probe(db, f"{tag}丙.txt", {f"{tag}丙_p_0": 1})
    try:
        rows = db.search_parent_chunks(query="不存在这个词", suffix="pdf",
                                       parent_ids=[f"{weird}_p_0", f"{tag}丙_p_0"])
        assert sorted(r.parent_id for r in rows) == sorted([f"{weird}_p_0", f"{tag}丙_p_0"])
        # 未知 id 静默少返回：前端 hydrate 拿"少返回"当剪死 id 的唯一信号
        assert db.search_parent_chunks(parent_ids=[f"{tag}早就没了_p_9"]) == []
        # 重复入参只出一行（GROUP BY 挡住 fan-out）
        dup = db.search_parent_chunks(parent_ids=[f"{tag}丙_p_0", f"{tag}丙_p_0"])
        assert [r.parent_id for r in dup] == [f"{tag}丙_p_0"]
        # 批量模式不吃 limit：limit=1 仍应把两个 id 都问回来
        assert len(db.search_parent_chunks(parent_ids=[f"{weird}_p_0", f"{tag}丙_p_0"], limit=1)) == 2
    finally:
        db.delete_document(doc_a)
        db.delete_document(doc_b)


def test_search_parent_chunks_excludes_hidden_documents(db):
    """chunk_count 归零而隐存的文档不该再往弹窗里供块——选了也召回不到，是死条目。"""
    tag = new_tag()
    doc_id = probe(db, f"{tag}丁.txt", {f"{tag}丁_p_0": 1, f"{tag}丁_p_1": 1})
    try:
        assert len(db.search_parent_chunks(query=tag)) == 2
        db.delete_parent_chunk(doc_id, f"{tag}丁_p_0")
        assert len(db.search_parent_chunks(query=tag)) == 1
        db.delete_parent_chunk(doc_id, f"{tag}丁_p_1")     # 归零 → is_active=False
        assert db.search_parent_chunks(query=tag) == []
    finally:
        db.delete_document(doc_id)


def test_search_parent_chunks_returns_the_baseline_pool_readable(db):
    """spec 3.4 的基线 smoke：这台机器上候选池有的可返回，且字段齐得够前端渲染。
    钉"非空 + 字段形状"，不钉条数——条数是要随上传变的（migration 门才管那个）。"""
    rows = db.search_parent_chunks(limit=200)
    assert rows, "基线库里应有 11 个父块"
    assert all(r.parent_id and r.filename and r.child_count >= 1 for r in rows)
```

- [ ] **Step 8: 跑它确认红**

Run: `cd backend && python -m pytest tests/test_live_database.py -q -k search_parent_chunks`
Expected: 4 条全 FAIL — `AttributeError: 'DatabaseManager' object has no attribute 'search_parent_chunks'`。

- [ ] **Step 9: 实现 `search_parent_chunks`**

`backend/core/database.py` 的 `DatabaseManager` 里，紧跟 `plan_chunk_deletion` 之前插入：

```python
    def search_parent_chunks(self, query="", suffix="", parent_ids=(), limit=50):
        """父块候选池：模糊搜文件名/块内文本，或按 parent_id 批量点查（后者优先）。

        三条不能反的规矩：
        * 只连 is_active 的文档——删块把 chunk_count 打到 0 的文档已隐存，
          它的残块摆进弹窗就是"选了也召回不到"的死条目。
        * 子块数用 outerjoin + GROUP BY 一次聚合。写成 len(chunk.child_chunks) 是 N+1，
          几百个块时弹窗会转圈。
        * 批量模式不吃 limit：hydrate 最多问 50 个 id，limit 插手会把选中项截没。
        """
        session = self.get_session()
        try:
            stmt = (
                session.query(
                    ParentChunk.parent_id,
                    ParentChunk.document_id,
                    ParentChunk.content,
                    Document.filename,
                    func.count(ChildChunk.id).label("child_count"),
                )
                .join(Document, Document.id == ParentChunk.document_id)
                .outerjoin(ChildChunk, ChildChunk.parent_chunk_id == ParentChunk.id)
                .filter(Document.is_active == True)
            )
            ids = list(dict.fromkeys(parent_ids))
            if ids:
                stmt = stmt.filter(ParentChunk.parent_id.in_(ids))
            else:
                if query:
                    pattern = f"%{_escape_like(query)}%"
                    stmt = stmt.filter(
                        Document.filename.like(pattern, escape="\\")
                        | ParentChunk.content.like(pattern, escape="\\")
                    )
                if suffix:
                    stmt = stmt.filter(Document.filename.ilike(f"%.{suffix.lower()}", escape="\\"))
            # group_by 必须在 limit 之前：Query 在已带 LIMIT 的语句上调它会直接抛 InvalidRequestError
            stmt = stmt.group_by(ParentChunk.id).order_by(
                ParentChunk.document_id.asc(), ParentChunk.parent_id.asc()
            )
            return stmt.all() if ids else stmt.limit(limit).all()
        finally:
            session.close()
```

- [ ] **Step 10: 跑 live 组确认绿**

Run: `cd backend && python -m pytest tests/test_live_database.py -q`
Expected: 全部 PASS（原有 7 条 + 新 4 条）。若 `list(...) == list(...)[:2]` 那条因 Row 类型不可比报错，两侧都套 `list()` 后再比，别放宽断言。

- [ ] **Step 11: 写端点失败测试**

追加到 `backend/tests/test_chunk_search.py`：

```python
class ChunkSearchDB:
    """只记录入参、回显预置行：端点的职责是把参数原样交给 db，并把行拼成 ChunkOut。"""

    def __init__(self, rows=()):
        self.rows = list(rows)
        self.calls = []

    def search_parent_chunks(self, query="", suffix="", parent_ids=(), limit=50):
        self.calls.append({"query": query, "suffix": suffix,
                           "parent_ids": list(parent_ids), "limit": limit})
        return self.rows


def row(parent_id="a.txt_parent_0", document_id=3, filename="a.txt", content="父 块 内容"):
    return SimpleNamespace(parent_id=parent_id, document_id=document_id,
                           content=content, filename=filename, child_count=2)


def make_client(db):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_chunks_endpoint_forwards_defaults_and_returns_chunk_shape():
    db = ChunkSearchDB([row(content="x" * 200)])
    body = make_client(db).get("/api/documents/chunks").json()
    assert db.calls == [{"query": "", "suffix": "", "parent_ids": [], "limit": 50}]
    assert len(body) == 1
    out = body[0]
    assert out["parent_id"] == "a.txt_parent_0"
    assert out["document_id"] == 3
    assert out["suffix"] == "txt"          # 从 filename 现推，不信前端传来的值
    assert out["child_count"] == 2
    assert out["snippet"] == "x" * 80 + "..."   # 与引用片段同一把尺子


def test_chunks_endpoint_passes_query_and_suffix_through():
    db = ChunkSearchDB()
    make_client(db).get("/api/documents/chunks", params={"query": "手册", "suffix": "pdf", "limit": 7}).json()
    assert db.calls[0] == {"query": "手册", "suffix": "pdf", "parent_ids": [], "limit": 7}


def test_chunks_endpoint_dedupes_parent_ids_but_keeps_order():
    db = ChunkSearchDB()
    make_client(db).get("/api/documents/chunks",
                        params=[("parent_ids", "b_p_0"), ("parent_ids", "a_p_0"),
                                ("parent_ids", "b_p_0")]).json()
    assert db.calls[0]["parent_ids"] == ["b_p_0", "a_p_0"]
    # 批量模式下 limit 让位，由 db 侧实现；这里只钉端点没把重复项喂进去
    assert db.calls[0]["limit"] == 50


@pytest.mark.parametrize("params,field", [
    ({"suffix": "exe"}, "suffix"),
    ({"limit": 0}, "limit"),
    ({"limit": 201}, "limit"),
    ({"query": "过" * 101}, "query"),
    ({"parent_ids": ""}, "parent_ids"),
    ({"parent_ids": "x" * 101}, "parent_ids"),
    ({"parent_ids": [f"p{i}" for i in range(51)]}, "parent_ids"),
])
def test_chunks_endpoint_rejects_bad_params_with_422(params, field):
    res = make_client(ChunkSearchDB()).get("/api/documents/chunks", params=params)
    assert res.status_code == 422
    assert any(field in str(item) for item in res.json()["detail"])


def test_chunks_route_wins_over_a_future_path_param_route():
    """FastAPI 按注册顺序匹配，/chunks 必须排在任何 /{...} 动态路由之前。

    今天 GET /{document_id} 还不存在，这条钉的是"将来加它时别插到 /chunks 前面"——
    写反了 /chunks 就变成文档不存在那个 404。
    读 documents_router.routes 而不是 app.routes：这个 FastAPI 版本把 include_router
    记成没有 .path 的 _IncludedRouter，展开后的顺序拿不到。
    """
    paths = [r.path for r in documents_router.routes]
    assert "/api/documents/chunks" in paths
    chunk_index = paths.index("/api/documents/chunks")
    assert all(chunk_index < paths.index(p) for p in paths if "{" in p)
```

文件顶部 import 段同步加一行 `from api.documents import router as documents_router`——漏了它 Step 12 红的是 `NameError`，不是"端点不存在"。

- [ ] **Step 12: 跑它确认红**

Run: `cd backend && python -m pytest tests/test_chunk_search.py -q`
Expected: 前 4 条 PASS（纯函数已实现），端点 11 条全 FAIL — 路由不存在，TestClient 拿到 404 后断言炸。

- [ ] **Step 13: 实现 `ChunkOut` 与端点**

`backend/schemas/documents.py` 追加：

```python
class ChunkOut(BaseModel):
    """父块候选池的一条：弹窗与已选列表都只吃这一个形状。"""

    parent_id: str
    document_id: int
    filename: str
    suffix: str
    snippet: str
    child_count: int
```

`backend/api/documents.py` 的 import 段改成：

```python
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import Field
```

`from schemas.documents import DocumentOut` 改成 `from schemas.documents import ChunkOut, DocumentOut`，并加 `from schemas.common import snippet_of`。在 `list_documents` 之后、`delete_parent_chunk` 之前插入：

```python
@router.get("/chunks", response_model=list[ChunkOut])
def list_chunks(
    query: str = Query("", max_length=100),
    suffix: Literal["", "pdf", "docx", "txt"] = Query(""),
    parent_ids: list[Annotated[str, Field(min_length=1, max_length=100)]] = Query(
        default=[], max_length=50),
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
):
    """父块候选池。三种模式同一条路由：模糊搜（query+suffix）、批量点查（parent_ids，优先）、
    全量前 N（都不给）。拆成两条路由的话，前端 hydrate 与弹窗搜索会各自演化出一套过滤规则。"""
    rows = db.search_parent_chunks(
        query=query, suffix=suffix,
        parent_ids=list(dict.fromkeys(parent_ids)), limit=limit,
    )
    return [
        ChunkOut(
            parent_id=r.parent_id,
            document_id=r.document_id,
            filename=r.filename,
            suffix=_suffix_of(r.filename),
            snippet=snippet_of(r.content),
            child_count=r.child_count,
        )
        for r in rows
    ]
```

- [ ] **Step 14: 跑端点测试确认绿**

Run: `cd backend && python -m pytest tests/test_chunk_search.py -q`
Expected: `15 passed`（4 纯函数 + 1 默认转发 + 1 参数透传 + 1 去重 + 7 个 422 参数化 + 1 路由顺序）。

- [ ] **Step 15: 跑后端默认门禁**

Run: `cd backend && python -m pytest -q`
Expected: 零 failed。默认组基线 146 → 本 Task 净增 `test_chunk_search.py` 的 15 条，实测 `163 passed, 2 skipped, 1 deselected`；另 live 组净增 4 条（`tests/test_live_database.py` 11 passed）。**把实数记进 ledger。**

- [ ] **Step 16: 提交**

```bash
git add backend/schemas/common.py backend/schemas/documents.py backend/core/database.py \
        backend/core/rag_system.py backend/api/documents.py \
        backend/tests/test_chunk_search.py backend/tests/test_live_database.py
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(backend): GET /api/documents/chunks 父块候选池，LIKE 元字符转义 + 截断收口一处"
```

---

### Task 2: 后端问答契约 `document_ids` → `parent_ids`

**Files:**
- Modify: `backend/schemas/chat.py:9-15`
- Modify: `backend/core/vector_store.py:86-95`
- Modify: `backend/core/database.py`（加 `document_ids_for_parents`）
- Modify: `backend/core/rag_system.py:67-119, 164-217`
- Modify: `backend/api/chat.py:15-55`
- Modify: `backend/tests/fakes.py:59-72`
- Modify: `backend/tests/test_api_chat.py`、`backend/tests/test_rag_system.py`、`backend/tests/test_live_stream.py:31`
- Modify: `backend/tests/test_live_database.py`（反查的活体判据）

**Interfaces:**
- Consumes: Task 1 的 `snippet_of`（本 Task 不动它）。
- Produces:
  - `ChatRequest{session_id, question, parent_ids: list[str]}`
  - `VectorStore.create_retriever(parent_ids=None)`
  - `DatabaseManager.document_ids_for_parents(parent_ids) -> list[int]`
  - `RAGSystem.chat_with_documents(question, parent_ids, session_id)` 与流式版同名同形

- [ ] **Step 1: 写 `ChatRequest` 的新校验判据（先红）**

`backend/tests/test_api_chat.py`：把全文所有 `"document_ids": [...]` 换成 `"parent_ids": [...]`，整数改字符串（`[1]` → `["a.txt_parent_0"]`，`[3, 1]` → `["丙_p_0", "甲_p_0"]`，`[]` 照旧）。**同文件里 `RecordingRAG`/`StreamRecordingRAG` 记录并断言的那批整数（`("rag", "营收多少", [3, 1], "s9")` 之类）要一并换成同样的字符串数组**——那是同一个契约的两端，漏改会让红看起来像断言写错而不是字段没换。然后：

- `test_non_integer_document_ids_is_422` 改名并重写为"101 字符元素 → 422"：

```python
def test_overlong_parent_id_is_422():
    """元素上界对齐 ParentChunk.parent_id 的 String(100)：超长的 id 不可能在库里。"""
    res = make_client(FakeRAG()).post("/api/chat", json={
        "session_id": "s1", "question": "q", "parent_ids": ["x" * 101]})
    assert res.status_code == 422


def test_empty_parent_id_element_is_422():
    res = make_client(FakeRAG()).post("/api/chat", json={
        "session_id": "s1", "question": "q", "parent_ids": [""]})
    assert res.status_code == 422


def test_legacy_document_ids_field_is_ignored_not_rejected():
    """老字段静默丢弃 → 空池 → normal。写死这条，免得以后有人把它当兼容入口重新接上。"""
    body = make_client(FakeRAG()).post(
        "/api/chat", json={"session_id": "s1", "question": "q", "document_ids": [1]}).json()
    assert body["mode"] == "normal"
```

- `test_more_than_50_document_ids_is_422` 改名 `test_more_than_50_parent_ids_is_422`，两处 `list(range(1, 52))` 换成 `[f"p{i}" for i in range(51)]`。
- `test_stream_rejects_oversized_and_nonpositive_document_ids_*` 里的坏值 `[10**9]` / `0` 换成 `["x" * 101]` / `""`。

- [ ] **Step 2: 跑它确认红**

Run: `cd backend && python -m pytest tests/test_api_chat.py -q`
Expected: 大面积 FAIL（`parent_ids` 尚不是字段 → 传了等于没传，mode 变 normal；断言 rag 的那些红）。

- [ ] **Step 3: 改 `ChatRequest`**

`backend/schemas/chat.py:9-15` 替换为：

```python
class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1)
    # 块级允许池：元素上界对齐 ParentChunk.parent_id 的 String(100)，与删块端点同源。
    # 50 项上界的推导照旧成立：落库列存的是反查出的 document_id，≤50 个 ⇒ 499 字符 ≤ String(500)。
    # 老字段 document_ids 不留 shim：唯一客户端是自家前端，同仓同部署，留着就是永不有人删的死入口。
    parent_ids: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        default_factory=list, max_length=50)
```

`mode_of` 原样不动（它同时服务历史行里的 `"1,2"` 字符串与 `None`，判据是真假）。`api/chat.py:17` 的 docstring 首句改成 `"""parent_ids 为空即普通对话，用 mode 回传实际走了哪条链（spec 6.2）。"""`，两处 `payload.document_ids` → `payload.parent_ids`。

- [ ] **Step 4: 写反查的失败测试**

`backend/tests/test_rag_system.py` 的 `StubDb` 加一个方法（放在 `get_filenames_by_ids` 之后）：

```python
    def __init__(self, history=(), filenames=None, parents=None):
        self.history = list(history)
        self.filenames = filenames or {}
        # parent_id -> document_id：反查表，缺键即"这个块已经不在库里了"
        self.parents = parents or {}
        self.saved = []

    def document_ids_for_parents(self, parent_ids):
        self.reverse_calls = list(parent_ids)
        out = []
        for pid in parent_ids:
            doc_id = self.parents.get(pid)
            if doc_id is not None and doc_id not in out:
                out.append(doc_id)
        return out
```

（`__init__` 整体替换原实现，注意别丢 `self.saved = []`。）追加用例：

```python
def test_history_still_keys_on_document_ids_found_by_reverse_lookup():
    """契约换成 parent_ids，但 chat_history.document_ids 这一列的形状不能变：
    mode 派生与引用补全 filename 都吃它，加第二列是第二份真相。"""
    db = StubDb(filenames={7: "手册.txt"}, parents={"甲_p_0": 7, "乙_p_1": 9})
    rag = build(db, StubVectorStore(parent_docs=[parent()]), ok_llm("答"))
    rag.chat_with_documents("问", ["甲_p_0", "乙_p_1", "早删了_p_9"], "s1")
    assert db.saved[0]["document_ids"] == "7,9"
    assert db.reverse_calls == ["甲_p_0", "乙_p_1", "早删了_p_9"]


def test_all_selected_chunks_dead_still_goes_down_the_rag_path():
    """选中的块全被删时不改判 normal：mode 只看请求里带没带池子。
    空召回自有 EMPTY_RETRIEVAL_ANSWER 那条路，落库照旧。"""
    db = StubDb(parents={})
    rag = build(db, StubVectorStore(parent_docs=[]), ok_llm("不该被调用"))
    answer, refs = rag.chat_with_documents("问", ["死块_p_0"], "s1")
    assert refs == []
    assert answer.startswith("未在选中的文档里找到相关内容")
    assert db.saved[0]["document_ids"] == ""      # 反查空 → 空串，不是 None 也不是 "None"


def test_stream_variant_uses_the_same_reverse_lookup():
    db = StubDb(filenames={7: "手册.txt"}, parents={"甲_p_0": 7})
    # stream_llm 是本文件已有的助手：RunnableGenerator 只收生成器函数，
    # 图省事写 lambda: [SimpleNamespace(...)] 会直接 TypeError。
    rag = build(db, StubVectorStore(parent_docs=[parent()]), stream_llm(["一", "二"]))
    list(rag.chat_with_documents_stream("问", ["甲_p_0"], "s1"))
    assert db.saved[-1]["document_ids"] == "7"
    assert db.reverse_calls == ["甲_p_0"]
```

（易漏的一半：`test_rag_system.py` 里既有的 14 处 `chat_with_documents("q", [7], "s1")` 也要一起改。
第二参数现在是块池，整数 `[7]` 反查不到任何东西，落库列会变空串——那批断言 `document_ids == "7"` 的用例
会红成"字段没接上"的样子。统一按 `parent()` 桩的默认 `parent_id="p0"` 换成 `["p0"]`，并给对应
`StubDb(...)` 补 `parents={"p0": 7}`；`[3]`/`[4]` 两处同理换成 `["p0"]` + `parents={"p0": 3}`/`{"p0": 4}`。）

- [ ] **Step 5: 跑它确认红**

Run: `cd backend && python -m pytest tests/test_rag_system.py -q`
Expected: `7 failed, 13 passed` — 新 3 条红在旧签名把 parent_ids 当 document_ids 直接 join（得到 `"甲_p_0"` 这种串）；
既有 4 条红在整数池反查为空、落库列变空串（正是上面那条"易漏的一半"）。

- [ ] **Step 6: 实现反查与 rag_system 改名**

`backend/core/database.py` 在 `get_filenames_by_ids` 之后加：

```python
    def document_ids_for_parents(self, parent_ids):
        """parent_id → document_id 的反查：历史列的形状不变，靠这一步补齐。

        按入参顺序去重、库里没有的静默少返回——与 search_parent_chunks 同一句话：
        删掉的块不该在历史里留一个指向空的 id。
        """
        ids = list(dict.fromkeys(parent_ids))
        if not ids:
            return []
        session = self.get_session()
        try:
            rows = session.query(ParentChunk.parent_id, ParentChunk.document_id).filter(
                ParentChunk.parent_id.in_(ids)).all()
        finally:
            session.close()
        by_parent = {r.parent_id: r.document_id for r in rows}
        doc_ids = []
        for pid in ids:
            doc_id = by_parent.get(pid)
            if doc_id is not None and doc_id not in doc_ids:
                doc_ids.append(doc_id)
        return doc_ids
```

`backend/core/rag_system.py` 两个 rag 方法：签名参数 `document_ids` → `parent_ids`，方法体开头加反查，`create_retriever(parent_ids)`，落库改 `document_ids=",".join(map(str, doc_ids))`：

```python
    def chat_with_documents(self, question, parent_ids, session_id):
        """基于文档块的 RAG 问答：块内召回 → 回溯父块 → 压缩 → 带历史生成。

        落库列仍是 document_ids（形状不变，历史渲染与 mode 派生都吃它），
        所以进来先做一次反查。反查为空不是故障：池子全是死块，召回自然为空，
        走的还是 EMPTY_RETRIEVAL_ANSWER 那条既有分支。
        """
        doc_ids = self.db_manager.document_ids_for_parents(parent_ids)
        if parent_ids and not doc_ids:
            logger.warning("选中的文档块已全部失效，这一轮按空召回走: %s", parent_ids)
        no_retrieval = False
        try:
            retriever = self.vector_store.create_retriever(parent_ids)
```

（其余行保持不变，只把 `",".join(map(str, document_ids))` 两处换成 `",".join(map(str, doc_ids))`。）流式版同样改法：

```python
    def chat_with_documents_stream(self, question, parent_ids, session_id):
        doc_ids = self.db_manager.document_ids_for_parents(parent_ids)
        if parent_ids and not doc_ids:
            logger.warning("选中的文档块已全部失效，这一轮按空召回走（流式）: %s", parent_ids)
        try:
            retriever = self.vector_store.create_retriever(parent_ids)
```

- [ ] **Step 7: 改检索器过滤字段**

`backend/core/vector_store.py:86-95` 替换为：

```python
    def create_retriever(self, parent_ids=None):
        """创建子文档检索器(只负责初始召回)"""
        search_kwargs = {"k": self.config.TOP_K * 2}
        if parent_ids:
            # 允许池按父块收窄。子块向量本身就带 parent_id 元数据（document_processor.py:81），
            # 所以换过滤字段不需要重新灌库——现存集合里的向量直接可用。
            search_kwargs["filter"] = {
                "parent_id": {"$in": list(parent_ids)}
            }
        # 返回一个 LangChain 检索器对象
        return self.child_vectorstore.as_retriever(search_kwargs=search_kwargs)
```

`backend/tests/fakes.py:59,69` 的 `FakeRAG` 两个方法参数名同步改 `parent_ids`（行为不变）。`backend/tests/test_api_chat.py` 里的 `RecordingRAG`/`StreamRecordingRAG` 两处覆写方法的参数名同步。`test_rag_system.py` 的 `StubVectorStore.create_retriever(self, document_ids)` → `(self, parent_ids)`。

`backend/tests/test_vector_store.py` 追加（文件顶部补 `from types import SimpleNamespace`）。注意 `store` fixture 是 `VectorStore.__new__` 造的，**手上没有 config**，而 `create_retriever` 要读 `self.config.TOP_K`，所以必须自己塞：

```python
def test_retriever_filters_by_parent_id_not_document_id(store):
    """块级允许池的落点。子块向量带 parent_id，所以这个过滤不需要重新灌库。"""
    store.config = SimpleNamespace(TOP_K=3)
    store.child_vectorstore.as_retriever = lambda search_kwargs: search_kwargs
    kwargs = store.create_retriever(["甲.txt_parent_0"])
    assert kwargs["filter"] == {"parent_id": {"$in": ["甲.txt_parent_0"]}}
    assert kwargs["k"] == 6          # TOP_K * 2 的老规矩没被顺手改掉


def test_retriever_without_pool_carries_no_filter(store):
    store.config = SimpleNamespace(TOP_K=3)
    store.child_vectorstore.as_retriever = lambda search_kwargs: search_kwargs
    # 纯对话链根本不调它，但空池必须"不加 filter"而不是"filter 命中零条"
    assert "filter" not in store.create_retriever([])
    assert "filter" not in store.create_retriever()
```

- [ ] **Step 8: 跑受影响的后端测试**

Run: `cd backend && python -m pytest tests/test_api_chat.py tests/test_rag_system.py tests/test_vector_store.py tests/test_schemas.py tests/test_live_stream.py -q`
Expected: 全 PASS。`test_live_stream.py:31` 的 payload 已改成 `"parent_ids": []`，那条继续 skip 或真跑都算过。

- [ ] **Step 9: 补反查的 live 判据**

`backend/tests/test_live_database.py` 追加：

```python
def test_document_ids_for_parents_reverse_lookup_is_ordered_deduped_and_silent_on_miss(db):
    """历史列仍写 document_ids，靠这一步补齐。fake 给不出"库里真没有这个块"的形状。"""
    tag = new_tag()     # parent_id 在全库是唯一键：不带 tag 的重跑一旦残留就撞锁，顺序断言会多吃一行
    doc_a = probe(db, f"{tag}戊.txt", {f"{tag}戊_p_0": 1, f"{tag}戊_p_1": 1})
    doc_b = probe(db, f"{tag}己.docx", {f"{tag}己_p_0": 1})
    try:
        # 顺序=入参顺序（不是 document_id 顺序）：历史里"用了哪些文档"该保留挑选的叙述顺序
        assert db.document_ids_for_parents([f"{tag}己_p_0", f"{tag}戊_p_1", f"{tag}戊_p_0"]) == [doc_b, doc_a]
        # 同文档的两个块 → 一个 id，落库不出现 "9,9"
        assert db.document_ids_for_parents([f"{tag}戊_p_0", f"{tag}戊_p_1"]) == [doc_a]
        assert db.document_ids_for_parents([f"{tag}没这个块_p_0"]) == []
        assert db.document_ids_for_parents([]) == []
    finally:
        db.delete_document(doc_a)
        db.delete_document(doc_b)
```

（`probe` / `new_tag` 是 Task 1 Step 7 定稿的两个助手，签名 `probe(db, filename, blocks)`，
`blocks` 是 `{parent_id: 子块数}`。）

Run: `cd backend && python -m pytest tests/test_live_database.py -q`
Expected: 全 PASS。

- [ ] **Step 10: 跑后端默认门禁 + migration 门**

```bash
cd backend && python -m pytest -q
python -m pytest -m migration -q
```
Expected: 默认门零 failed = `170 passed, 2 skipped, 1 deselected`（比 Task 1 末净增 7 条：
test_api_chat +1、test_rag_system +3、test_vector_store +2、test_live_database +1）；
migration 门 **1 passed**。2 skipped 是 `test_live_stream.py` 够不到 :8000，非本 Task 引入。

- [ ] **Step 11: 提交**

```bash
git add backend/schemas/chat.py backend/api/chat.py backend/core/vector_store.py \
        backend/core/database.py backend/core/rag_system.py \
        backend/tests/fakes.py backend/tests/test_api_chat.py backend/tests/test_rag_system.py \
        backend/tests/test_vector_store.py backend/tests/test_live_stream.py \
        backend/tests/test_live_database.py
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(backend)!: 问答契约 document_ids→parent_ids，检索按父块收窄、历史反查补齐"
```

---

### Task 3: 前端 api 出口 + `useChunkSelection`

**Files:**
- Create: `frontend/tests/useChunkSelection.test.js`
- Modify: `frontend/src/api/documents.js`
- Modify: `frontend/src/composables/useChat.js:58,80`
- Modify: `frontend/tests/useChat.test.js`、`frontend/tests/documents-api.test.js`

**Interfaces:**
- Consumes: `GET /api/documents/chunks`（Task 1）、`parent_ids` 载荷（Task 2）。
- Produces:
  - `listChunks({ query, suffix, parentIds, limit }) -> Promise<Chunk[]>`，每项含 `parent_id/document_id/filename/suffix/snippet/child_count`
  - `useChunkSelection()` → `{ selectedChunks, selectedParentIds, selectedCount, pickerOpen, selectionError, hydrate, toggle, remove, isSelected, clearSelection }`
  - `MAX_SELECTED_CHUNKS = 50`

- [ ] **Step 1: 写 `listChunks` 的 URL 判据（先红）**

`frontend/tests/documents-api.test.js` 的 import 改成 `import { deleteChunk, listChunks } from '../src/api/documents.js'`，追加：

```js
describe('listChunks（Task 1 契约的前端出口）', () => {
  it('空入参打裸路径，不拼一串无意义的问号', async () => {
    const calls = stubFetch()
    await listChunks()
    expect(calls[0][0]).toBe('/api/documents/chunks')
  })

  it('中文关键词与后缀都进 query', async () => {
    const calls = stubFetch()
    await listChunks({ query: '手册 上', suffix: 'pdf' })
    const params = new URLSearchParams(calls[0][0].split('?')[1])
    // 比解析后的原文，不比编码串：URLSearchParams 把空格编成 +，
    // 拿 decodeURIComponent 反解会得到"手册 +上"，那是判据写错不是实现错
    expect(params.get('query')).toBe('手册 上')
    expect(params.get('suffix')).toBe('pdf')
  })

  // 这一条是"选中项刷新后蒸发"的唯一防线：parent_id 由清洗后的文件名拼出，
  // 逗号是合法字符。逗号拼接会把一个真 id 拆成两个假 id，后端只会静默少返回。
  it('parent_ids 用重复键而不是逗号拼接，含逗号的 id 原样往返', async () => {
    const calls = stubFetch()
    const ids = ['手册,第一版.txt_parent_0', 'b.txt_parent_1']
    await listChunks({ parentIds: ids })
    const params = new URLSearchParams(calls[0][0].split('?')[1])
    expect(params.getAll('parent_ids')).toEqual(ids)
  })

  it('limit 只在非默认值时才出现在 query 里', async () => {
    const calls = stubFetch()
    await listChunks({ limit: 200 })
    expect(calls[0][0]).toContain('limit=200')
    await listChunks({ limit: 50 })
    expect(calls[1][0]).not.toContain('limit=')
  })
})
```

Run: `cd frontend && npm test`
Expected: FAIL — `listChunks is not a function`。

- [ ] **Step 2: 实现 `listChunks`**

`frontend/src/api/documents.js` 在 `listDocuments` 之后加：

```js
// 候选池一次问三条：模糊搜（query+suffix）、批量点查（parentIds，后端优先认它）、默认前 50。
// parentIds 用重复键 append：一个真 id 里可以含逗号，逗号拼接会被后端拆成两个假 id，
// 坏法是"刷新后选中项凭空少几个"而不是报错——比崩难查。
export function listChunks({ query = '', suffix = '', parentIds = [], limit = 50 } = {}) {
  const params = new URLSearchParams()
  if (query) params.set('query', query)
  if (suffix) params.set('suffix', suffix)
  for (const id of parentIds) params.append('parent_ids', id)
  if (limit !== 50) params.set('limit', String(limit))
  const qs = params.toString()
  return request(`/api/documents/chunks${qs ? `?${qs}` : ''}`)
}
```

Run: `cd frontend && npm test` → Expected: documents-api 6 passed。

- [ ] **Step 3: `useChat.send` 的载荷键换掉（先改测试看红）**

`frontend/tests/useChat.test.js`：全文 `document_ids:` → `parent_ids:`，值 `[1]` → `['甲.txt_parent_0']`，并在第一个用例后追加：

> 批量换键的口径：本文件里有 **2 处 `document_ids: [1]`**（载荷）和 **9 处 `document_ids: []`**（载荷），
> 都要换；但引用对象里的 **`document_id:`（单数，如 `{ document_id: 1, filename: '甲.txt' }`）一个都不能动**——
> 那是后端 Reference 的字段。用 `document_ids:` 整串做替换才不会误伤。
> 追加的用例别照抄下游模板里的 `setStream(chat, [])`：本仓这个文件的流桩叫 `scriptEvents`，
> 而且每条用例要自己 `const chat = useChat()`。

```js
  // 后端那份 ChatRequest 只认 parent_ids；多余字段被 Pydantic 静默丢掉，
  // 坏法是"每次对话都走普通链、引用条永远空"，不是 422 也不是报错。
  it('载荷里的池子字段叫 parent_ids', async () => {
    scriptEvents([['token', { text: 'x' }], DONE])
    const chat = useChat()
    await chat.send({ session_id: 's1', question: 'q', parent_ids: ['甲.txt_parent_0'] })
    expect(sendChatStream.mock.calls[0][0]).toEqual({
      session_id: 's1', question: 'q', parent_ids: ['甲.txt_parent_0'],
    })
  })
```

Run: `cd frontend && npm test` → Expected: 该条 FAIL。实测红因是"缺字段"而不是"多字段"：
`toEqual` 忽略值为 `undefined` 的属性，所以旧的 `document_ids: undefined` 不会出现在 received 里，
received 只有 `{ session_id, question }`——判据靠 expected 里那个真值 `parent_ids` 撑住。

- [ ] **Step 4: 改 `useChat.js`**

`frontend/src/composables/useChat.js:58` → `async function send({ session_id, question, parent_ids }) {`；`:80` → `{ session_id, question, parent_ids },`。Run: `cd frontend && npm test` → Expected: useChat 全绿。

- [ ] **Step 5: 写 `useChunkSelection` 的失败测试**

创建 `frontend/tests/useChunkSelection.test.js`：

```js
// 已选块是"刷新后还得认得回来"的状态：只有 id 值得进 localStorage。
// 快照会在块被删/改名后说谎，所以读回必须整批去问后端，并以后端没返回来剪死 id。
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../src/api/documents.js', () => ({ listChunks: vi.fn() }))

import { listChunks } from '../src/api/documents.js'
import { MAX_SELECTED_CHUNKS, useChunkSelection } from '../src/composables/useChunkSelection.js'

const KEY = 'selected_parent_ids'

function chunk(parentId, docId = 3, filename = 'a.txt') {
  return { parent_id: parentId, document_id: docId, filename, suffix: 'txt',
           snippet: '片段', child_count: 2 }
}

beforeEach(() => {
  localStorage.clear()
  listChunks.mockReset()
})

describe('useChunkSelection', () => {
  it('toggle 追加并落盘，只落 id 不落快照', () => {
    const s = useChunkSelection()
    s.toggle(chunk('甲_p_0'))
    s.toggle(chunk('乙_p_0', 9, 'b.pdf'))
    expect(s.selectedParentIds.value).toEqual(['甲_p_0', '乙_p_0'])
    expect(JSON.parse(localStorage.getItem(KEY))).toEqual(['甲_p_0', '乙_p_0'])
    expect(localStorage.getItem(KEY)).not.toContain('snippet')
  })

  it('再点一次同一个块即取消，持久化同步', () => {
    const s = useChunkSelection()
    s.toggle(chunk('甲_p_0'))
    s.toggle(chunk('甲_p_0'))
    expect(s.selectedChunks.value).toEqual([])
    expect(JSON.parse(localStorage.getItem(KEY))).toEqual([])
  })

  it('第 51 块被拒：中文文案说清上限与出路，且不进集合不发盘', () => {
    const s = useChunkSelection()
    for (let i = 0; i < MAX_SELECTED_CHUNKS; i += 1) s.toggle(chunk(`p${i}`))
    expect(s.selectedCount.value).toBe(50)
    s.toggle(chunk('overflow'))
    expect(s.selectedCount.value).toBe(50)
    expect(s.selectionError.value).toContain('50')
    expect(JSON.parse(localStorage.getItem(KEY))).not.toContain('overflow')
  })

  it('hydrate 以后端返回为准：没返回的 id 就是死了，就地剪掉并回写', async () => {
    localStorage.setItem(KEY, JSON.stringify(['活_p_0', '死_p_1']))
    listChunks.mockResolvedValue([chunk('活_p_0')])
    const s = useChunkSelection()
    await s.hydrate()
    expect(s.selectedParentIds.value).toEqual(['活_p_0'])
    expect(JSON.parse(localStorage.getItem(KEY))).toEqual(['活_p_0'])
    expect(listChunks.mock.calls[0][0]).toEqual({ parentIds: ['活_p_0', '死_p_1'] })
  })

  it('hydrate 保住点选顺序，不按后端返回顺序重排', async () => {
    localStorage.setItem(KEY, JSON.stringify(['乙_p_0', '甲_p_0']))
    listChunks.mockResolvedValue([chunk('甲_p_0'), chunk('乙_p_0')])
    const s = useChunkSelection()
    await s.hydrate()
    expect(s.selectedParentIds.value).toEqual(['乙_p_0', '甲_p_0'])
  })

  it('本地没有选择时不打后端：一次空请求只会把错误横幅平白点亮', async () => {
    const s = useChunkSelection()
    await s.hydrate()
    expect(listChunks).not.toHaveBeenCalled()
    expect(s.selectedChunks.value).toEqual([])
  })

  it('脏 localStorage 读回即丢：非数组、非字符串元素、超长、超额都不进集合', async () => {
    localStorage.setItem(KEY, '不是 JSON')
    const a = useChunkSelection()
    await a.hydrate()
    expect(a.selectedChunks.value).toEqual([])

    localStorage.setItem(KEY, JSON.stringify(['ok_p_0', 7, '', 'x'.repeat(101), null]))
    listChunks.mockResolvedValue([chunk('ok_p_0')])
    const b = useChunkSelection()
    await b.hydrate()
    expect(listChunks.mock.calls.at(-1)[0]).toEqual({ parentIds: ['ok_p_0'] })

    localStorage.setItem(KEY, JSON.stringify(Array.from({ length: 80 }, (_, i) => `p${i}`)))
    listChunks.mockResolvedValue([])
    const c = useChunkSelection()
    await c.hydrate()
    expect(listChunks.mock.calls.at(-1)[0].parentIds).toHaveLength(50)
  })

  it('hydrate 失败只落文案、保留已有集合：面板不该因为一次网络失败就空掉', async () => {
    const s = useChunkSelection()
    s.toggle(chunk('甲_p_0'))
    listChunks.mockRejectedValue(new Error('无法连接后端，请确认 uvicorn 已在 :8000 运行'))
    localStorage.setItem(KEY, JSON.stringify(['甲_p_0', '乙_p_0']))
    await s.hydrate()
    expect(s.selectionError.value).toContain('无法连接后端')
    expect(s.selectedParentIds.value).toEqual(['甲_p_0'])
  })

  it('remove 只按 parent_id 摘，isSelected 跟着变', () => {
    const s = useChunkSelection()
    s.toggle(chunk('甲_p_0'))
    expect(s.isSelected('甲_p_0')).toBe(true)
    s.remove('甲_p_0')
    expect(s.isSelected('甲_p_0')).toBe(false)
    expect(JSON.parse(localStorage.getItem(KEY))).toEqual([])
  })

  it('clearSelection 把集合与本地存储一起清掉', () => {
    const s = useChunkSelection()
    s.toggle(chunk('甲_p_0'))
    s.clearSelection()
    expect(localStorage.getItem(KEY)).toBe('[]')
    expect(s.selectedChunks.value).toEqual([])
  })
})
```

Run: `cd frontend && npm test` → Expected: FAIL，但红在"文件级"而不是"用例级"：模块缺失时 vitest 整个文件加载失败、
一条都不收集，实测汇总 `Test Files  1 failed | 5 passed (6)` + `Tests  50 passed (50)`。
别把 50 全绿看成"新测试没写进去"——看的是那 1 个 failed 文件。

- [ ] **Step 6: 实现 `useChunkSelection.js`**

创建 `frontend/src/composables/useChunkSelection.js`：

```js
import { computed, ref } from 'vue'

import { listChunks } from '../api/documents.js'

const STORAGE_KEY = 'selected_parent_ids'
export const MAX_SELECTED_CHUNKS = 50
const MAX_ID_CHARS = 100  // 对齐 ParentChunk.parent_id 的 String(100)

// localStorage 是用户能亲手改的地方（DevTools、上个版本的残留），坏值必须在这道关口
// 就被丢掉，而不是带着进请求 URL——同 useSession 的"坏值构造不可达"，别等后端 422。
function readStoredIds() {
  let raw
  try {
    raw = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]')
  } catch {
    return []
  }
  if (!Array.isArray(raw)) return []
  const clean = raw.filter((id) => typeof id === 'string' && id.length > 0 && id.length <= MAX_ID_CHARS)
  return [...new Set(clean)].slice(0, MAX_SELECTED_CHUNKS)
}

function writeStoredIds(ids) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(ids))
}

export function useChunkSelection() {
  const selectedChunks = ref([])
  const pickerOpen = ref(false)
  const selectionError = ref('')

  const selectedParentIds = computed(() => selectedChunks.value.map((c) => c.parent_id))
  const selectedCount = computed(() => selectedChunks.value.length)

  function persist() {
    writeStoredIds(selectedParentIds.value)
  }

  async function hydrate() {
    const ids = readStoredIds()
    if (!ids.length) {
      selectedChunks.value = []
      selectionError.value = ''
      return
    }
    try {
      const rows = await listChunks({ parentIds: ids })
      const byId = new Map(rows.map((row) => [row.parent_id, row]))
      // 按存下来的顺序重建，并剪掉后端没返回的：那是已删/已隐存的块，留着等于发一个必空召回的请求
      selectedChunks.value = ids.map((id) => byId.get(id)).filter(Boolean)
      // 剪过就要回写，否则下次刷新再剪一次，坏值永远赖在本地
      persist()
    } catch (err) {
      // 一次网络失败不该把面板清空：保留已有集合，只把错误说出来
      selectionError.value = err.message
    }
  }

  function isSelected(parentId) {
    return selectedChunks.value.some((c) => c.parent_id === parentId)
  }

  function toggle(chunk) {
    const i = selectedChunks.value.findIndex((c) => c.parent_id === chunk.parent_id)
    if (i !== -1) {
      selectedChunks.value.splice(i, 1)
      selectionError.value = ''
    } else {
      if (selectedChunks.value.length >= MAX_SELECTED_CHUNKS) {
        selectionError.value = `最多只能选择 ${MAX_SELECTED_CHUNKS} 个文档块，请先取消几个再添加。`
        return
      }
      selectedChunks.value.push(chunk)
      selectionError.value = ''
    }
    persist()
  }

  function remove(parentId) {
    selectedChunks.value = selectedChunks.value.filter((c) => c.parent_id !== parentId)
    persist()
  }

  function clearSelection() {
    selectedChunks.value = []
    persist()
  }

  return {
    selectedChunks, selectedParentIds, selectedCount, pickerOpen, selectionError,
    hydrate, toggle, remove, isSelected, clearSelection,
  }
}
```

Run: `cd frontend && npm test` → Expected: useChunkSelection 10 passed（实测全量 `Tests  60 passed (60)`，6 个文件）。

- [ ] **Step 7: 跑前端门禁并提交**

Run: `cd frontend && npm test && npm run build`
Expected: 测试零 failed、build exit 0。实测数：**45 → 60 passed**（新增 15 条 = listChunks 4 + useChat 载荷键 1 + useChunkSelection 10），
build 产物 `78.56 kB` 的入口 js 正常 exit 0（`useChunkSelection.js` 此刻还没有组件引用它，不在打包图里，属预期）。

```bash
git add frontend/src/api/documents.js frontend/src/composables/useChat.js \
        frontend/src/composables/useChunkSelection.js \
        frontend/tests/documents-api.test.js frontend/tests/useChat.test.js \
        frontend/tests/useChunkSelection.test.js
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(frontend): listChunks 出口 + useChunkSelection，localStorage 只存 parent_id"
```

---

### Task 4: 前端组件——面板重写 + 弹窗 + 红叉

**Files:**
- Create: `frontend/src/components/ChunkCard.vue`
- Create: `frontend/src/components/ChunkPickerModal.vue`
- Create: `frontend/tests/chunk-selection.test.js`
- Modify: `frontend/src/components/DocumentPanel.vue`
- Modify: `frontend/src/components/StatusBar.vue`
- Modify: `frontend/src/components/MessageList.vue:26`（欢迎语从"勾选左侧文档"改成块级说法）
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/styles/variables.css`（只加一个 `--overlay-bg`）
- Modify: `frontend/src/styles/layout.css`
- Delete: `frontend/src/components/DocCard.vue`
- Modify: `frontend/src/composables/useDocuments.js`（去掉 `selectedIds`/`toggleSelect`）

**Interfaces:**
- Consumes: Task 3 的 `useChunkSelection` 与 `listChunks`、`docLabel`（useDocuments.js，原位不动）。
- Produces: `ChunkCard`（props `chunk/selected/removable`，emits `toggle`/`remove`）、`ChunkPickerModal`（props `selectedIds/error`，emits `toggle`/`close`）、`DocumentPanel` 新增 emits `open-picker`/`deselect-chunk`。注意 `deselect-chunk`（取消选择，本地不发请求）与 App.vue 里已有的 `remove-chunk`（MessageList 引用条上的不可逆删数据）是两个不同事件,别混名。

- [ ] **Step 1: 写 `ChunkCard` 的失败测试（含红叉不双触发）**

创建 `frontend/tests/chunk-selection.test.js`：

```js
// 面板与弹窗共用 ChunkCard，两处的"点一下"语义必须相反又不打架：
// 弹窗里点卡片=选中/取消，面板里右上角那个 ✕=取消选择（本地动作，不发请求）。
// 🗑（删除文档块）在引用条上，是另一回事——文案必须区分，混了会让人以为点一下就丢数据。
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('../src/api/documents.js', () => ({ listChunks: vi.fn() }))

import ChunkCard from '../src/components/ChunkCard.vue'
import ChunkPickerModal from '../src/components/ChunkPickerModal.vue'
import { listChunks } from '../src/api/documents.js'

const chunk = { parent_id: '手册.pdf_parent_0', document_id: 7, filename: '手册.pdf',
                suffix: 'pdf', snippet: '片段一', child_count: 3 }

beforeEach(() => {
  listChunks.mockReset()
  listChunks.mockResolvedValue([chunk])
})

describe('ChunkCard', () => {
  it('三行内容：docLabel 格式唯一出处 + 片段 + 块与子块数', () => {
    const text = mount(ChunkCard, { props: { chunk } }).text()
    expect(text).toContain('手册.pdf(#7)')
    expect(text).toContain('片段一')
    expect(text).toContain('手册.pdf_parent_0')
    expect(text).toContain('3 个子块')
  })

  it('removable 才给红叉，且它的 aria-label 说的是"取消选择"不是"删除"', () => {
    const plain = mount(ChunkCard, { props: { chunk } })
    expect(plain.find('.chunk-remove').exists()).toBe(false)

    const card = mount(ChunkCard, { props: { chunk, removable: true } })
    const x = card.find('.chunk-remove')
    expect(x.attributes('aria-label')).toBe('取消选择')
    expect(x.text()).toBe('✕')
    expect(card.text()).not.toMatch(/删除文档块[^（]/)
  })

  it('点红叉只 emit remove，不连带 emit toggle（同一卡片两个动作不能双触发）', async () => {
    const card = mount(ChunkCard, { props: { chunk, removable: true } })
    await card.find('.chunk-remove').trigger('click')
    expect(card.emitted('remove')).toEqual([[chunk.parent_id]])
    expect(card.emitted('toggle')).toBeUndefined()
  })

  it('点卡片本体 emit toggle(整块)', async () => {
    const card = mount(ChunkCard, { props: { chunk, removable: true } })
    await card.find('.chunk-card-body').trigger('click')
    expect(card.emitted('toggle')).toEqual([[chunk]])
  })

  it('selected 时带角标与高亮类', () => {
    const card = mount(ChunkCard, { props: { chunk, selected: true } })
    expect(card.find('.chunk-badge').exists()).toBe(true)
    expect(card.classes()).toContain('chunk-card-selected')
  })
})
```

Run: `cd frontend && npm test` → Expected: FAIL — 找不到 `ChunkCard.vue`。
红在文件级（同 Task 3 Step 5）：`Test Files  1 failed | 6 passed (7)`、`Tests  60 passed (60)`。

- [ ] **Step 2: 实现 `ChunkCard.vue`**

> **执行期回写（DOM 顺序 = 视觉位置）**：计划原本把红叉写在 `.chunk-card-body` **之前**。
> `.chunk-card` 是 `display: flex` 的横向容器，第一个孩子会落在**左上角**——而需求要的是**右上角**。
> jsdom 不排版，所以 Step 1 那五条判据对"写在前面"照样全绿：位置错只能靠浏览器量测发现。
> 落地版把本体排在前、✕ 排在后，`align-self: flex-start` + `margin: 6px 6px 0 0` 正好把它钉在右上。

```vue
<script setup>
import { docLabel } from '../composables/useDocuments.js'

const props = defineProps({
  chunk: { type: Object, required: true },
  selected: { type: Boolean, default: false },
  removable: { type: Boolean, default: false },
})
const emit = defineEmits(['toggle', 'remove'])
</script>

<template>
  <div class="chunk-card" :class="{ 'chunk-card-selected': props.selected }">
    <button class="chunk-card-body" type="button" @click="emit('toggle', props.chunk)">
      <span class="chunk-title">
        {{ docLabel(props.chunk) }}
        <span v-if="props.selected" class="chunk-badge">已选</span>
      </span>
      <span class="chunk-snippet">{{ props.chunk.snippet }}</span>
      <span class="chunk-meta">块 {{ props.chunk.parent_id }} · {{ props.chunk.child_count }} 个子块</span>
    </button>
    <!-- 红叉排在卡片本体之后：.chunk-card 是横向 flex，第二个孩子才落在右上角（写在前面会顶到左上角）。
         stop 也是必需的：红叉嵌在同一张卡片里，不拦住冒泡就会连带触发 toggle，看起来像"取消两次=没变"。 -->
    <button
      v-if="props.removable"
      class="chunk-remove"
      type="button"
      aria-label="取消选择"
      title="取消选择这个文档块"
      @click.stop="emit('remove', props.chunk.parent_id)"
    >✕</button>
  </div>
</template>
```

Run: `cd frontend && npm test` → Expected: ChunkCard 5 条绿。

- [ ] **Step 3: 写弹窗的失败测试**

追加到 `frontend/tests/chunk-selection.test.js`：

```js
describe('ChunkPickerModal', () => {
  const props = { selectedIds: [], error: '' }

  it('一挂载就先查一次全量（弹窗要的是真值，不缓存上次的结果）', async () => {
    mount(ChunkPickerModal, { props })
    await Promise.resolve()
    expect(listChunks).toHaveBeenCalledWith({ query: '', suffix: '' })
  })

  it('回车提交：关键词去空白后交给 listChunks', async () => {
    const wrapper = mount(ChunkPickerModal, { props })
    await wrapper.find('input').setValue('  手册  ')
    await wrapper.find('form').trigger('submit')
    expect(listChunks.mock.calls.at(-1)[0]).toEqual({ query: '手册', suffix: '' })
  })

  it('切分类用当前关键词立即重查', async () => {
    const wrapper = mount(ChunkPickerModal, { props })
    await wrapper.find('input').setValue('手册')
    await wrapper.findAll('.picker-tab')[2].trigger('click')   // DOCX
    expect(listChunks.mock.calls.at(-1)[0]).toEqual({ query: '手册', suffix: 'docx' })
    expect(wrapper.findAll('.picker-tab')[2].classes()).toContain('picker-tab-active')
  })

  it('点结果卡片 emit toggle(整块)；卡片本体不带红叉', async () => {
    const wrapper = mount(ChunkPickerModal, { props })
    await Promise.resolve()
    await wrapper.find('.chunk-card-body').trigger('click')
    expect(wrapper.emitted('toggle')).toEqual([[chunk]])
    expect(wrapper.find('.chunk-remove').exists()).toBe(false)
  })

  it('已选中的卡片带角标（选中状态在弹窗里也看得见）', async () => {
    const wrapper = mount(ChunkPickerModal, { props: { ...props, selectedIds: [chunk.parent_id] } })
    await Promise.resolve()
    expect(wrapper.find('.chunk-badge').exists()).toBe(true)
  })

  it('两种点击关闭：✕ 按钮与点遮罩空白；点内容区不关', async () => {
    const wrapper = mount(ChunkPickerModal, { props })
    await wrapper.find('.picker-close').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)

    await wrapper.find('.picker-backdrop').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(2)

    await wrapper.find('.picker-modal').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(2)   // 内容区点击不算"点空白"
    wrapper.unmount()
  })

  // Esc 的监听挂在 window 上（焦点在弹窗内任意处都吃得到），所以判据也必须从 window 派发：
  // wrapper.trigger 只会打到那个 DOM 节点，keydown 不会往下传。
  it('Esc 关闭', async () => {
    const wrapper = mount(ChunkPickerModal, { props })
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(wrapper.emitted('close')).toHaveLength(1)
    // 不 unmount 的话 onUnmounted 不跑，window 上的监听会活到下一条用例里
    wrapper.unmount()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('上限文案顶在弹窗里而不是全局横幅：错在哪就说在哪', async () => {
    const wrapper = mount(ChunkPickerModal, { props: { ...props, error: '最多只能选择 50 个文档块' } })
    expect(wrapper.find('.picker-error').text()).toContain('50')
  })

  it('请求失败给一句能行动的中文，不把空白弹窗留给用户', async () => {
    listChunks.mockRejectedValue(new Error('无法连接后端，请确认 uvicorn 已在 :8000 运行'))
    const wrapper = mount(ChunkPickerModal, { props })
    await Promise.resolve()
    await Promise.resolve()
    expect(wrapper.find('.picker-error').text()).toContain('无法连接后端')
    expect(wrapper.findAll('.chunk-card')).toHaveLength(0)
  })

  it('零命中时说"没有匹配"而不是空面板', async () => {
    listChunks.mockResolvedValue([])
    const wrapper = mount(ChunkPickerModal, { props })
    await Promise.resolve()
    expect(wrapper.find('.picker-hint').text()).toContain('没有匹配')
  })
})
```

Run: `cd frontend && npm test` → Expected: FAIL — 找不到 `ChunkPickerModal.vue`。

- [ ] **Step 4: 实现 `ChunkPickerModal.vue`**

```vue
<script setup>
import { onMounted, onUnmounted, ref } from 'vue'

import ChunkCard from './ChunkCard.vue'
import { listChunks } from '../api/documents.js'

const props = defineProps({
  selectedIds: { type: Array, required: true },
  error: { type: String, default: '' },
})
const emit = defineEmits(['toggle', 'close'])

const TABS = [
  { value: '', label: '全部' },
  { value: 'pdf', label: 'PDF' },
  { value: 'docx', label: 'DOCX' },
  { value: 'txt', label: 'TXT' },
]

const keyword = ref('')
const suffix = ref('')
const chunks = ref([])
const busy = ref(false)
const searchError = ref('')

// 只有回车与按钮提交，不做输入防抖：搜索框每敲一个字打一次后端，
// 在这个体量（父块十来个）上是纯浪费，真要加防抖得先有分页。
async function search() {
  busy.value = true
  searchError.value = ''
  try {
    chunks.value = await listChunks({ query: keyword.value.trim(), suffix: suffix.value })
  } catch (err) {
    chunks.value = []
    searchError.value = err.message
  } finally {
    busy.value = false
  }
}

function pickSuffix(value) {
  suffix.value = value
  search()
}

function onKeydown(event) {
  if (event.key === 'Escape') emit('close')
}

function onBackdrop(event) {
  // target===currentTarget 才关：从内容区冒泡上来的点击不是"点空白"
  if (event.target === event.currentTarget) emit('close')
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  search()
})
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="picker-backdrop" @click="onBackdrop">
    <div class="picker-modal" role="dialog" aria-modal="true" aria-label="选择文档块">
      <header class="picker-header">
        <h3 class="picker-title">🧩 选择文档块</h3>
        <button class="picker-close" type="button" aria-label="关闭" title="关闭" @click="emit('close')">✕</button>
      </header>

      <form class="picker-search" @submit.prevent="search">
        <input
          v-model="keyword"
          class="picker-input"
          type="search"
          aria-label="搜索文档块"
          placeholder="按文件名或块内文字搜索，回车提交"
        />
        <button class="btn btn-small" type="submit">搜索</button>
      </form>

      <div class="picker-tabs">
        <button
          v-for="tab in TABS"
          :key="tab.value"
          class="picker-tab"
          :class="{ 'picker-tab-active': suffix === tab.value }"
          type="button"
          @click="pickSuffix(tab.value)"
        >{{ tab.label }}</button>
      </div>

      <p v-if="props.error || searchError" class="picker-error">⚠️ {{ props.error || searchError }}</p>
      <p v-else-if="busy" class="picker-hint">搜索中…</p>
      <ul v-else-if="chunks.length" class="picker-results">
        <li v-for="item in chunks" :key="item.parent_id">
          <ChunkCard
            :chunk="item"
            :selected="props.selectedIds.includes(item.parent_id)"
            @toggle="emit('toggle', $event)"
          />
        </li>
      </ul>
      <p v-else class="picker-hint">没有匹配的文档块，换个关键词或分类试试。</p>
    </div>
  </div>
</template>
```

- [ ] **Step 5: 跑弹窗测试并修接线问题**

Run: `cd frontend && npm test`
Expected: 弹窗用例全绿。

> **执行期回写（实测四条红，两类原因）**
>
> ① **`await Promise.resolve()` 一轮不够。** 计划里"点结果卡片""带角标""零命中"三条各写了一轮、
> "请求失败"写了两轮，实测全红——`await listChunks(...)` 的 mock promise 落地占一轮 microtask，
> Vue 调度器的渲染排队又是一轮，DOM 里那时还没有卡片。"零命中"那条收到的实际文案是 `搜索中…`
> （busy 还挂着）。四条 DOM 判据统一改 `await flushPromises()`（`@vue/test-utils` 导出，
> 走一个 `setTimeout(0)` 把 microtask 队列排空）；只验"调用过什么"的那条不用等。
>
> ② **Esc 那条的后半是假判据。** `wrapper.unmount()` 会把 VTU 的事件记录一起清掉，
> 之后再读 `wrapper.emitted('close')` 拿到 `undefined`，报的是
> `AssertionError: Target cannot be null or undefined`——而不是"监听没摘掉"这个真信号。
> "卸载后不再响应"必须用一个存活于卸载之外的观察点：
>
> ```js
> it('Esc 关闭，卸载后不再抢键盘', async () => {
>   const closed = []
>   const shown = ref(true)
>   const Host = {
>     setup() {
>       return () => (shown.value
>         ? h(ChunkPickerModal, { selectedIds: [], error: '', onClose: () => closed.push(1) })
>         : null)
>     },
>   }
>   mount(Host)
>   window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
>   expect(closed).toHaveLength(1)
>
>   shown.value = false
>   await nextTick()   // 让 onUnmounted 跑掉
>   window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
>   expect(closed).toHaveLength(1)
> })
> ```
>
> 宿主用 `h()` 而不是字符串 `template`：vitest 这边解析到的是 Vue 运行时构建，没有模板编译器。
> 别为了过测试把 `busy` 分支删掉——它挡的是"搜索中"与"没有匹配"两种状态的岔路。

- [ ] **Step 6: `DocumentPanel` 知识库区重写 + `useDocuments` 瘦身 + 删 `DocCard`**

`frontend/src/composables/useDocuments.js`：删 `const selectedIds = ref([])`、`toggleSelect` 函数、`refresh` 里那两行失效摘勾（连同它的注释）、return 里的 `selectedIds` 与 `toggleSelect`。**`docLabel` 留在原位**（M-F2 的唯一出处，`ReferenceList` 也在吃）。

删除文件：`git rm frontend/src/components/DocCard.vue`。

> **执行期回写（三处连带）**
>
> 1. **`documents` prop 删掉，不保留。** 计划原文在 props 与 App 接线里都留着它，但新模板通体没有一处
>    读 `props.documents`（文档总数由 `docCount` 那条 metric 说，弹窗里自己会搜）——留一个没人吃的
>    必填 prop 只会让 App 继续传一个哑参数。落地版 props 是：
>    `selectedChunks / selectionError / queue / listError / docCount / clearing`。
>    App.vue 仍解构 `documents`，那是 `MessageList :has-documents` 在吃，别跟着删。
> 2. **`layout.css` 里退役的不止三条规则**：`.doc-list / .doc-card / .doc-card:hover / .doc-card-checked`
>    之外还有 `.doc-name`、`.doc-meta` 两条只服务 DocCard。判据是 `grep -rn "doc-card\|doc-list" src/`，
>    落地时把口径扩到 `grep -rn "DocCard\|doc-card\|doc-list\|doc-name\|doc-meta" src/ tests/`，
>    确认只剩 `layout.css` 自身才动手。
> 3. **`--shadow-card-hover` 变成死 token**：它唯一的使用者是 `.doc-card:hover`。删掉后
>    `grep -rn "shadow-card-hover" src/` 必须 0 命中——G-4 的门只查字面量，不查没用的 token，
>    所以这一条得手动扫。

`frontend/src/components/DocumentPanel.vue` 全文替换为：

```vue
<script setup>
import ChunkCard from './ChunkCard.vue'
import FileUploader from './FileUploader.vue'

const props = defineProps({
  selectedChunks: { type: Array, required: true },
  selectionError: { type: String, default: '' },
  queue: { type: Array, required: true },
  listError: { type: String, default: '' },
  docCount: { type: Number, required: true },
  clearing: { type: Boolean, default: false },
})
// deselect-chunk 是"取消选择"（本地动作，不发请求）；
// App.vue 里 MessageList 那条 remove-chunk 才是"删数据"（不可逆，要过 confirm）——两个名字不能混。
const emit = defineEmits(['enqueue', 'retry', 'dismiss', 'clear', 'open-picker', 'deselect-chunk'])
</script>

<template>
  <div class="side-panel-inner">
    <h2 class="panel-title">📁 文档管理</h2>
    <FileUploader
      :queue="props.queue"
      @enqueue="emit('enqueue', $event)"
      @retry="emit('retry', $event)"
      @dismiss="emit('dismiss', $event)"
    />

    <p v-if="props.listError" class="queue-error">📚 文档列表加载失败：{{ props.listError }}</p>

    <hr class="panel-hr" />
    <h2 class="panel-title">🧩 已选文档块</h2>
    <button class="btn btn-small picker-open" type="button" @click="emit('open-picker')">
      ➕ 选择文档块
    </button>
    <p v-if="props.selectionError" class="queue-error">⚠️ {{ props.selectionError }}</p>

    <ul v-if="props.selectedChunks.length" class="chunk-list">
      <li v-for="chunk in props.selectedChunks" :key="chunk.parent_id">
        <ChunkCard
          :chunk="chunk"
          selected
          removable
          @toggle="emit('deselect-chunk', chunk.parent_id)"
          @remove="emit('deselect-chunk', $event)"
        />
      </li>
    </ul>
    <p v-else class="panel-hint">还没有选择文档块，点上方按钮挑几块。</p>
    <p class="panel-hint">一个块都不选就是普通对话。点卡片右上角的 ✕ 取消选择（不删任何数据）。</p>

    <hr class="panel-hr" />
    <div class="metric">📊 文档数 {{ props.docCount }}</div>
    <button class="btn" type="button" :disabled="props.clearing" @click="emit('clear')">
      {{ props.clearing ? '清空中…' : '🗑️ 清空对话' }}
    </button>
  </div>
</template>
```

（面板里的卡片 `@toggle` 与 `@remove` 都归到取消选择——卡片本体点一下=取消，红叉也是取消，两条路语义一致，不会一个删一个不删。）

- [ ] **Step 7: `StatusBar` 文案 + `App.vue` 接线**

`frontend/src/components/StatusBar.vue:16` → `🔍 知识库模式（{{ props.selectedCount }} 个文档块）`，第 4 行注释同步改成"选了几个文档块"。

`frontend/src/App.vue` 改动四处：

```js
import ChunkPickerModal from './components/ChunkPickerModal.vue'
import { useChunkSelection } from './composables/useChunkSelection.js'
```

```js
const {
  documents, queue, listError, docCount, refresh, enqueue, retry, dismiss,
} = useDocuments()
const {
  selectedChunks, selectedParentIds, selectedCount, pickerOpen, selectionError,
  hydrate, toggle, remove,
} = useChunkSelection()
```

```js
onMounted(async () => {
  await refresh()
  // hydrate 要打一枪 /api/documents/chunks：放在 restore 之前，
  // 让"选中项已被剪掉"这件事先于历史渲染，错误横幅只剩最后一条真的
  await hydrate()
  await restore(sessionId.value)
})
```

> **执行期补一条（第五处改动）**：`handleRemoveChunk` 在 `deleteChunk` 成功后要顺手 `remove(parentId)`。
> spec 六节"已知遗留"写的是"死块要下次 hydrate 才剪"，那是针对**别处**发生的删除（另一个标签页、
> 文档被隐存）；而引用条上的 🗑 是**此刻本地亲手删的**，这块的死是确定事实——不摘就是面板上挂一张
> 指向已消失内容的卡片、下一次问答还带一个必空召回的 id，白等一次刷新。
> `parent_id` 在全库是唯一键（`ParentChunk.parent_id` 带 UNIQUE），所以按它摘正好，不会误伤别的文档。
> 顺带改掉那条注释里对 `selectedIds` 的引用：失效摘勾那套机制随 DocCard 一起退役了。

```js
async function handleSend(text) {
  if (!text || pending.value) return
  question.value = ''
  const ok = await send({ session_id: sessionId.value, question: text, parent_ids: selectedParentIds.value })
  if (!ok) question.value = text
}
```

模板：`DocumentPanel` 的 props 换成 `:selected-chunks="selectedChunks" :selection-error="selectionError"`，事件加 `@open-picker="pickerOpen = true"` 与 `@deselect-chunk="remove"`；`MessageList` 上原有的 `@remove-chunk="handleRemoveChunk"` **保持不动**（那是引用条删数据那条链，与取消选择无关）；`StatusBar` 的 `:selected-count="selectedCount"`；`ChatInput` 之后加：

```html
    <ChunkPickerModal
      v-if="pickerOpen"
      :selected-ids="selectedParentIds"
      :error="selectionError"
      @toggle="toggle"
      @close="pickerOpen = false"
    />
```

**同时要删掉** `DocumentPanel` 上的两条旧接线（留着会传 `undefined` 进必填 prop，Vue 会在控制台刷警告）：`:selected-ids="selectedIds"` 与 `@toggle="toggleSelect"`。

`frontend/src/components/MessageList.vue:26` 的欢迎语第三行改文案——面板已经没有"勾选文档"这个动作了，界面不能继续教用户做不存在的事：

```js
    props.hasDocuments ? '从左侧「➕ 选择文档块」挑几块，或直接开始对话吧！' : '请先在左侧上传文档，或直接开始对话吧！',
```

`frontend/src/styles/layout.css` 里 `.doc-card`、`.doc-card-checked`、`.doc-list` 三块规则随 `DocCard.vue` 一起退役（先确认无引用再删）：

```bash
cd frontend && grep -rn "doc-card\|doc-list" src/
```
Expected: 只剩 `src/styles/layout.css` 自身（`DocCard.vue` 已 `git rm`）。若还有别处引用，停手别删。

- [ ] **Step 8: 样式（颜色只进 token）**

`frontend/src/styles/variables.css` 在 `--shadow-panel` 之后加一行（弹窗遮罩的底色必须走 token，G-4 口径下 `layout.css` 里出现 `rgba(` 就红）：

```css
  --overlay-bg: rgba(0, 0, 0, 0.45);
```

`frontend/src/styles/layout.css` 在 `.chunk-delete { align-self: flex-start; }` 之后追加：

```css
/* ---- 块级选择（2026-10-04）：面板里的已选卡片 + 候选池弹窗 ---- */
.picker-open { margin: 4px 0 10px; }
.chunk-list { display: flex; flex-direction: column; gap: 8px; margin: 0 0 10px; padding: 0; list-style: none; }
.chunk-card {
  position: relative; display: flex; gap: 8px;
  border: 1px solid var(--border); border-radius: var(--radius-card);
  background: var(--panel-bg); box-shadow: var(--shadow-bubble);
}
.chunk-card-selected { border-color: var(--brand-1); }
.chunk-card-body {
  flex: 1; display: flex; flex-direction: column; gap: 2px;
  padding: 10px 12px; border: 0; background: none; text-align: left;
  font: inherit; color: var(--text-main); cursor: pointer;
}
.chunk-title { font-weight: 600; word-break: break-all; }
.chunk-snippet { font-size: 12px; color: var(--text-muted); }
.chunk-meta { font-size: 11px; color: var(--text-muted); word-break: break-all; }
.chunk-badge {
  margin-left: 6px; padding: 0 6px; border-radius: var(--radius-pill);
  background: var(--status-rag-bg); color: var(--status-rag-fg); font-size: 11px; font-weight: 400;
}
/* ✕ 是"取消选择"（本地、不发请求）；引用条上的 🗑 才是删数据，两者文案必须不同 */
.chunk-remove {
  align-self: flex-start; flex: 0 0 auto; margin: 6px 6px 0 0;
  width: 22px; height: 22px; padding: 0;
  border: 0; border-radius: 50%; background: var(--fail-bg); color: var(--fail-fg);
  font-size: 13px; line-height: 1; cursor: pointer;
}

.picker-backdrop {
  position: fixed; inset: 0; z-index: 4;   /* 高于 ≤768 侧栏浮层的 3，否则窄屏下弹窗被盖住点不到 */
  display: flex; align-items: center; justify-content: center;
  background: var(--overlay-bg);
}
.picker-modal {
  width: min(92vw, 560px); max-height: 82vh; overflow: hidden;
  display: flex; flex-direction: column; gap: 10px; padding: 16px;
  border: 1px solid var(--border); border-radius: var(--radius-card);
  background: var(--panel-bg); box-shadow: var(--shadow-panel);
}
.picker-header { display: flex; align-items: center; justify-content: space-between; }
.picker-title { margin: 0; font-size: 16px; }
.picker-close {
  width: 26px; height: 26px; padding: 0; border: 0; border-radius: 50%;
  background: var(--page-bg); color: var(--text-muted); cursor: pointer;
}
.picker-search { display: flex; gap: 8px; }
.picker-input {
  flex: 1; min-width: 0; padding: 8px 10px;
  border: 1px solid var(--border); border-radius: var(--radius-card);
  background: var(--panel-bg); color: var(--text-main);
}
.picker-tabs { display: flex; gap: 6px; flex-wrap: wrap; }
.picker-tab {
  padding: 4px 12px; border: 1px solid var(--border); border-radius: var(--radius-pill);
  background: var(--panel-bg); color: var(--text-muted); font-size: 13px; cursor: pointer;
}
.picker-tab-active { background: var(--grad-brand); color: var(--on-brand); border-color: transparent; }
.picker-error { font-size: 13px; color: var(--fail-fg); }
.picker-hint { font-size: 13px; color: var(--text-muted); }
/* 有界滚动：弹窗结果区不随内容长高（L-2 同族要求，长列表撑破视口是老病根） */
.picker-results {
  flex: 1; margin: 0; padding: 0 2px 0 0; overflow-y: auto; max-height: 60vh;
  display: flex; flex-direction: column; gap: 8px; list-style: none;
}
```

`.picker-results` 是 `<ul>`，`li` 里放 `.chunk-card`：在 `.picker-results li` 上加 `display: flex;` 让卡片随栏宽。追加到上面块的末尾。

> **执行期回写（落地版比计划多两处，都是为了不被排版咬）**
> - `.picker-open` 补 `align-self: flex-start;`：`.side-panel-inner` 是 `flex-direction: column`，
>   按钮默认被拉成整行宽，"➕ 选择文档块"会顶满侧栏，与旁边 `metric` 的观感不一致。
> - `.chunk-card-body` 补 `min-width: 0;`：flex 子项的默认最小宽度是 `auto`，长 `parent_id`
>   （`手册 上.pdf_parent_0` 这种带空格/中文的）在 `word-break: break-all` 下也照样把卡片撑破侧栏，
>   必须先把最小尺寸松开，`break-all` 才真的生效。
> - `.picker-results li { display: flex; }` 按计划那句追加在块末尾，实测必需：`li` 默认 block，
>   里面的 `.chunk-card` 收成内容宽，弹窗里每张卡片宽度不一。

- [ ] **Step 9: 跑前端门禁**

```bash
cd frontend && npm test && npm run build
grep -rnE '#[0-9a-fA-F]{3,8}\b|rgba?\(' frontend/src --include='*.css' --include='*.vue' --include='*.js' | grep -v 'styles/variables.css'
```
Expected: 测试零 failed、build exit 0、**grep 0 命中**（G-4 唯一口径）。若 grep 报 `--include` 语法问题，命令前缀去掉重复的 `frontend/`（在 frontend 目录下跑时用 `src`）。

实测数：**75 passed (75)、7 个文件**（Task 3 末 60 + ChunkCard 5 + 弹窗 10），
build `dist/assets/index-*.css 9.99 kB` + `index-*.js 85.07 kB`、exit 0；
G-4 grep 命中 0（`--overlay-bg` 是这一轮唯一新增的颜色字面量，只进 `variables.css`）。
旧接线扫描只剩两处合法命中：`ChunkPickerModal` 自己的 `selectedIds` prop（它吃的是 parent_id 数组，
与退役的文档勾选无关），以及 `useChat.js:40` 那句指**数据库列名** `chat_history.document_ids` 的注释。

- [ ] **Step 10: 提交**

```bash
git add -A frontend/src frontend/tests
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(frontend): 面板只显已选文档块 + 候选池弹窗（搜索/后缀分类/红叉取消），DocCard 退役"
```

---

### Task 5: 双端门禁 + live 联调 + 基线核对

**Files:**
- Modify: `.superpowers/sdd/2026-10-02-kb-platform-sse-streaming/progress.md`（或本阶段新建 ledger 段：记门禁实数、验证结论、遗留）

- [ ] **Step 1: 后端两条门 + 前端三条门**

```bash
cd backend && python -m pytest -q
cd backend && python -m pytest -m "live" -q
cd backend && python -m pytest -m migration -q
cd frontend && npm test
cd frontend && npm run build
```
Expected: 全部零 failed；migration **1 passed**（没重钉的必要——本功能不动数据）。把每条的实数记下来。

- [ ] **Step 2: 重启我自起的 uvicorn，让新后端代码上线**

现存那个 :8000 实例是我起的、跑的是本轮改动之前的代码（uvicorn 无热重载）。**先核对 PID 归属再杀**，只杀自己起的那一个；然后：

```bash
cd backend && python -m uvicorn main:app --host 127.0.0.1 --port 8000
```
（后台跑，记下 PID。）前端 vite（:5173）沿用现存实例，不必重启。

- [ ] **Step 3: 端点直连冒烟（先看后端，再看 UI）**

```bash
curl -s "http://127.0.0.1:8000/api/documents/chunks?limit=3" | head -c 600
curl -s "http://127.0.0.1:8000/api/documents/chunks?query=%E7%9F%A5%E8%AF%86%E5%BA%93%E5%B9%B3%E5%8F%B0" | head -c 400
curl -s "http://127.0.0.1:8000/api/documents/chunks?query=%25" | python -c "import json,sys;print(len(json.load(sys.stdin)))"   # 转义后的 %
curl -s "http://127.0.0.1:8000/api/documents/chunks?query=%5F" | python -c "import json,sys;print(len(json.load(sys.stdin)))"  # 转义后的 _
curl -s "http://127.0.0.1:8000/api/documents/chunks?suffix=exe"       # 期望 422 数组 detail
```
Expected: `limit=3` 与 `query=知识库平台` 返回带 `parent_id/filename/suffix/snippet/child_count` 的行；`suffix=exe` 返回 422。

> **执行期改判（两处旧预期都错了，按实测口径覆盖）**：
> ① 旧文写 `query=手册&suffix=pdf` 期望返回行——基线 9 篇里**没有**文件名含「手册」的文档，它本来就该返回 `[]`，用它当"搜索生效"的证据等于什么都没验。换成 `query=知识库平台`（实测命中 `rag.txt_parent_0`、`rag2.txt_parent_0`，且这是**块内正文**命中，不是文件名命中）。
> ② 旧文写 `query=%` 期望 `[]`——`deepseek简介.docx_parent_0` 的正文里**确实有一个字面 `%`**，转义生效后诚实命中 1 行；判据不能钉"零命中"，要钉**条数对照**：全量 11 行、`%` → 1、`%%` → 0、`_` → 0。不转义时 `%`/`_` 会各自把全库 11 行捞回来（`_` 匹配任意单字符），这才是转义生效的证据。


- [ ] **Step 4: 浏览器验证（宽屏 1280×900 + 窄屏 375×800 各一遍）**

视口必须显式设（headless 默认 754px 会掉进 `max-width:768` 断点，把正确 CSS 判成缺陷）；报告里回读 `innerWidth` 原始值。in-app 浏览器无 surface 时改走 `puppeteer-core` + 本机 Edge（`--no-save`，验完 `npm prune` + 删 `node_modules/@puppeteer`，`package-lock.json` 不动）。

判据（逐条记 PASS/FAIL + 证据数字）：
1. 面板知识库区标题是 `🧩 已选文档块`，其下有 `➕ 选择文档块` 按钮，且**不再出现**任何未选中的文档卡片列表。
2. 点按钮 → 弹窗出现，`innerWidth` 变化不影响可见性；≤768 时弹窗在侧栏浮层之上（`z-index: 4 > 3`），实测能点到搜索框。
3. 搜 `deepseek` → 结果全部文件名或片段含该词；切 `DOCX` → 只剩 `suffix==='docx'` 的行；切 `全部` → 条数回到上一步或更多；搜 `%` → **条数远小于全量**（实测 11 → 1，那 1 行的正文里有字面 `%`；未转义会直接返回全量 11），搜 `_` → 0 条。
4. 选 2 块 → 面板只显示这 2 块；StatusBar 显示 `（2 个文档块）`。
5. 点其中 1 块右上角 ✕ → 面板剩 1 块；**刷新页面仍是 1 块**（localStorage 真生效，`selected_parent_ids` 里那一项已被摘掉）。
6. 就着留下的那块问一个只在那块里能答的问题 → `meta` 帧 mode=rag、`references` 帧非空、答案逐字上屏。
7. **改问只在"刚才取消选择的那块"里的内容 → `references` 帧为空，且答案里不出现那块独有的词。** 这一条是"允许池真收窄了召回"的唯一活体证据，光看 UI 不算。
   > **执行期改判（旧文钉了 `EMPTY_RETRIEVAL_ANSWER` 的文案，机制猜错了一半。）** 实测帧序列是 `meta mode=rag` → `references []` → 一串模型自己的 token（"…并未包含关于'第三份占位文档'的任何内容…"），**不是**那句固定说明文案。原因是两级过滤叠加：池里只剩 `rag.txt_parent_0` 时，带 `$in` 过滤的相似度检索**一定会**返回池内最近的那条子块，`parent_docs` 非空 ⇒ 不进空召回分支；随后压缩器按相关度阈值把它也滤掉，`compressed_docs=[]` ⇒ `references` 帧空、`context` 是空串。所以判据只能钉"references 为空 + 答案不含 `串行`/`上传队列`"，不能钉文案。压缩器阈值是**既有行为**（`VectorStore.compressor`），与本功能无关；顺带证明引用条如实反映"真正进了上下文的块"。
8. 取消全部选择 → StatusBar 变 `💬 普通对话模式`，发送后 mode=normal、无 references 帧。
9. 卡片红叉的 `title` 是"取消选择这个文档块"、引用条上的按钮文案仍是"删除此块"（两条文案不得混同；用 `evaluate` 读 `title` 原文作证）。
10. 全程零控制台错误（`list_console_messages` 只允许 favicon 之类无害项）。

> **执行期补：十条判据本身没改，红的全是探针接线（三处，都值得进下次的 prompt）**
> ① **搜索框不能用 `click({clickCount:3})` 选旧内容再输入**——这个框里 triple-click 选不中，第二次实测框内变成 `deepseek%_知识库平台`，于是 `%` 那次"0 条命中"其实是搜了一个不存在的组合词，证据假绿。改成先 `el.value=''` + `dispatchEvent(new Event('input'))`（v-model 才会跟着清），再把**回读到的框内值**一起进证据，并且 `typed !== text` 直接抛错。
> ② **窄屏点面板 ✕ 之前必须先关弹窗**。≤768 时侧栏是 `position: fixed` 浮层、遮罩 `z-index:4` 在它上面，那一下点击落在 backdrop 上只关掉了弹窗，取消选择根本没触发——表现为"刷新后还是 2 块"，看着像 localStorage 没同步，实际是事件没派发。宽屏没这个问题（侧栏不是浮层），所以同一份代码宽屏绿、窄屏红。
> ③ **分类标签按文字定位，不按索引表**：`TABS` 里的 value 是 `''`，显示文字是「全部」，`['', 'PDF', 'DOCX', 'TXT'].indexOf('全部')` 拿到 `-1` 就崩在 `tabs[-1].click()`。

- [ ] **Step 5: 基线核对（没被这轮验证改动）**

```bash
curl -s "http://127.0.0.1:8000/api/health"
python -m pytest -m migration -q
```
Expected: `document_count: 9`、`vector_counts` 与迁移基线一致、migration 门 1 passed。若第 4/7 步往 `chat_history` 里写了新会话行：那是正常业务写入（探针 session_id 是自己造的 UUID），记下 session_id 即可，不必删；**但不得改动 documents/parent_chunks/child_chunks 与向量集合**。

- [ ] **Step 6: 记 ledger 并提交**

在 `.superpowers/sdd/2026-10-02-kb-platform-sse-streaming/progress.md` 末尾（或本功能自己的 ledger 段）追加一节 `=== 块级文档选择面板（2026-10-04）===`，写：五条门的实数、十判据的 PASS/FAIL、`query=%` 转义的两级证据（curl + UI）、已知遗留四条（`deleted` 不持久化、死块要下次 hydrate 才剪、无防抖、弹窗无分页）。

```bash
git add .superpowers/sdd/2026-10-02-kb-platform-sse-streaming/progress.md
git -c user.name="31439" -c user.email="31439@local" commit -m "docs(ledger): 块级选择面板落地——双端门禁实数、十判据 live 互证、四条已知遗留"
```

## Self-Review 结论（写完计划后按 spec 逐条回扫）

- **spec 覆盖**：三节约定的端点/契约/反查 → Task 1、2；四节约定的 composable/组件/文案 → Task 3、4；五节的门禁与十判据 → Task 5。六节"已知遗留"不进实现。
- **占位符**：无 TBD/TODO；每条代码步骤都给了可直接粘贴的实现。
- **类型一致性**：`parent_ids`（请求体/检索器/前端载荷）与 `parent_id`（`ChunkOut` 字段、`Reference` 字段，单数）两套命名各守其位；`listChunks({ parentIds })` 是前端驼峰入参、出 query 时转成 `parent_ids` 重复键；`remove(parentId)` / `toggle(chunk)` 的入参形状在 Task 3 定义、Task 4 消费，两端一致。
