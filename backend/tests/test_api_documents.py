import posixpath
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from core.document_processor import DocumentProcessor
from deps import get_db, get_doc_processor, get_vector_store
from exceptions import UnsupportedDocumentType
from fakes import FakeDocProcessor, FakeVectorStore
from main import create_app


class RecordingDB:
    def __init__(self, save_chunks_error=None):
        self.save_chunks_error = save_chunks_error
        self.deleted_docs = []
        self.saved_docs = []
        self.rows = []
        self.saved_doc_id = 42
        self.chunks_saved = False
        # get_document 回显这一行，201 响应里的 filename 才是"库里的值"而不是请求字面量
        self.saved_filename = "a.txt"

    def save_document(self, filename, file_path, content, chunk_count=0):
        self.saved_docs.append((filename, chunk_count))
        self.saved_filename = filename
        return self.saved_doc_id

    def save_chunks(self, doc_id, parent_docs, child_docs, parent_ids, child_ids):
        if self.save_chunks_error:
            raise self.save_chunks_error
        self.chunks_saved = True

    def get_document(self, doc_id):
        return type("Doc", (), {"id": doc_id, "filename": self.saved_filename, "chunk_count": 1,
                                "created_at": datetime(2026, 9, 30, 12, 0)})()

    def delete_document(self, doc_id):
        self.deleted_docs.append(doc_id)
        return 1

    def get_all_documents(self):
        return list(self.rows)


def make_client(db, processor=None, vector_store=None):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_doc_processor] = lambda: processor or FakeDocProcessor()
    app.dependency_overrides[get_vector_store] = lambda: vector_store or FakeVectorStore()
    return TestClient(app)


def test_upload_txt_returns_201_with_document_shape():
    client = make_client(RecordingDB())
    res = client.post("/api/documents", files={"file": ("a.txt", "内容".encode("utf-8"), "text/plain")})
    assert res.status_code == 201
    body = res.json()
    assert body["id"] == 42
    assert body["filename"] == "a.txt"
    assert body["created_at"].startswith("2026-09-30")


class CountedProcessor(FakeDocProcessor):
    """父子块数量故意不等（2 父 / 3 子），chunk_count 只能来自子块数。"""

    def create_parent_child_chunks(self, documents, filename):
        parents, children = super().create_parent_child_chunks(documents, filename)
        return parents * 2, children * 3


def test_saved_chunk_count_is_the_child_block_count():
    db = RecordingDB()
    client = make_client(db, processor=CountedProcessor())
    res = client.post("/api/documents", files={"file": ("a.txt", "内容".encode("utf-8"), "text/plain")})
    assert res.status_code == 201
    assert db.saved_docs == [("a.txt", 3)]


def test_unsupported_type_returns_415_with_detail():
    client = make_client(RecordingDB(), processor=FakeDocProcessor(
        fail_with=UnsupportedDocumentType("不支持的文件类型: .exe")))
    res = client.post("/api/documents", files={"file": ("a.exe", b"MZ", "application/octet-stream")})
    assert res.status_code == 415
    assert res.json()["detail"] == "不支持的文件类型: .exe"


def test_empty_file_returns_422():
    client = make_client(RecordingDB())
    res = client.post("/api/documents", files={"file": ("a.txt", b"", "text/plain")})
    assert res.status_code == 422


def test_chunk_save_failure_rolls_back_vectors_and_document():
    """坑 3：save_chunks 失败后，"向量有、关系库无"的幽灵状态不能残留。"""
    db = RecordingDB(save_chunks_error=RuntimeError("boom"))
    store = FakeVectorStore()
    client = make_client(db, vector_store=store)

    res = client.post("/api/documents", files={"file": ("a.txt", "内容".encode("utf-8"), "text/plain")})
    assert res.status_code == 500
    # 必须是 StorageError 走 spec 八节的映射，不能被兜底 handler 的"服务器内部错误"顶包
    assert res.json() == {"detail": "文档入库失败，已回滚"}
    # fakes.FakeVectorStore 把每次调用的 (parent_ids, child_ids) append 进 self.deleted
    assert store.deleted == [(["p0"], ["c0"])]
    assert db.deleted_docs == [42]
    assert db.chunks_saved is False


class RaisingDeleteVectorStore(FakeVectorStore):
    """回滚时 Chroma 自己也挂了：delete_by_ids 抛异常，但调用确实发生过。"""

    def __init__(self, error=None):
        super().__init__()
        self.error = error or RuntimeError("chroma 不可用")
        self.delete_called = False

    def delete_by_ids(self, parent_ids, child_ids):
        self.delete_called = True
        raise self.error


class RaisingDeleteDocumentDB(RecordingDB):
    """回滚时 MySQL 掉线：删行请求已发出，但提交失败。"""

    def __init__(self, save_chunks_error=None, delete_document_error=None):
        super().__init__(save_chunks_error=save_chunks_error)
        self.delete_document_error = delete_document_error or RuntimeError("mysql 掉线")

    def delete_document(self, doc_id):
        self.deleted_docs.append(doc_id)
        raise self.delete_document_error


def test_vector_delete_failure_still_deletes_row_and_returns_500():
    """复合故障：回滚第一步（删向量）自己炸了，第二步（删行）也必须执行，500 语义不能退化成兜底文案。"""
    db = RecordingDB(save_chunks_error=RuntimeError("boom"))
    store = RaisingDeleteVectorStore()
    client = make_client(db, vector_store=store)

    res = client.post("/api/documents", files={"file": ("a.txt", "内容".encode("utf-8"), "text/plain")})
    assert res.status_code == 500
    assert res.json() == {"detail": "文档入库失败，已回滚"}
    assert store.delete_called is True
    assert db.deleted_docs == [42]


def test_row_delete_failure_still_returns_500_with_storage_detail():
    """复合故障镜像面：删行炸了也不能让裸异常逃逸到兜底 handler。"""
    db = RaisingDeleteDocumentDB(save_chunks_error=RuntimeError("boom"))
    store = FakeVectorStore()
    client = make_client(db, vector_store=store)

    res = client.post("/api/documents", files={"file": ("a.txt", "内容".encode("utf-8"), "text/plain")})
    assert res.status_code == 500
    assert res.json() == {"detail": "文档入库失败，已回滚"}
    assert store.deleted == [(["p0"], ["c0"])]
    assert db.deleted_docs == [42]


def test_oversized_upload_returns_413_before_anything_is_written(monkeypatch):
    import api.documents as documents_api

    monkeypatch.setattr(documents_api, "MAX_UPLOAD_BYTES", 4)
    db = RecordingDB()
    store = FakeVectorStore()
    client = make_client(db, vector_store=store)

    res = client.post("/api/documents", files={"file": ("a.txt", "0123456789".encode("utf-8"), "text/plain")})
    assert res.status_code == 413
    assert store.deleted == []
    assert db.deleted_docs == []
    assert db.chunks_saved is False


def test_list_documents_returns_array():
    client = make_client(RecordingDB())
    assert client.get("/api/documents").json() == []


def test_list_documents_maps_rows_to_spec_shape():
    db = RecordingDB()
    db.rows = [type("Doc", (), {"id": 3, "filename": "手册.pdf", "chunk_count": 2,
                                "created_at": datetime(2026, 9, 30, 12, 0)})()]
    res = make_client(db).get("/api/documents")
    assert res.status_code == 200
    assert res.json() == [{"id": 3, "filename": "手册.pdf", "chunk_count": 2,
                           "created_at": "2026-09-30T12:00:00"}]


class SpyProcessor(FakeDocProcessor):
    def __init__(self):
        super().__init__()
        self.seen = []

    def load_document(self, filename, raw_bytes):
        self.seen.append(("load", filename))
        return super().load_document(filename, raw_bytes)

    def create_parent_child_chunks(self, documents, filename):
        self.seen.append(("chunks", filename))
        return super().create_parent_child_chunks(documents, filename)


class RecordingVectorStore(FakeVectorStore):
    def __init__(self):
        super().__init__()
        self.added = []

    def add_documents(self, parent_docs, child_docs, document_id):
        self.added.append((parent_docs, child_docs))
        return super().add_documents(parent_docs, child_docs, document_id)


# 客户端能自己决定 multipart 里的 filename，浏览器只会给 basename，curl/脚本不会
MALICIOUS_FILENAMES = [
    ("a..\\..\\b.txt", "b.txt"),
    ("a/../b.txt", "b.txt"),
    ("..\\escape.txt", "escape.txt"),
    ("C:\\Windows\\System32\\a.txt", "a.txt"),
    ("/etc/passwd.txt", "passwd.txt"),
]


@pytest.fixture(params=["host", "posix"], ids=lambda p: f"basename={p}")
def posix_style_basename(request, monkeypatch):
    """把 api.documents 看到的 os.path 换成 posixpath：Linux 部署面上 basename 不认反斜杠。

    只在 host 平台跑的话，os.path 就是 ntpath，反斜杠那一半清洗永远测不到。
    """
    import api.documents as documents_api

    if request.param == "posix":
        monkeypatch.setattr(documents_api, "os", SimpleNamespace(path=posixpath))
        # 换不掉就是空转：这条 assert 保证 posix 那一臂真在测 posixpath 的 basename
        assert documents_api.os.path is posixpath
    return request.param


@pytest.mark.parametrize("raw, expected", MALICIOUS_FILENAMES)
def test_uploaded_filename_reaches_storage_without_path_components(raw, expected, posix_style_basename):
    db, processor, store = RecordingDB(), SpyProcessor(), RecordingVectorStore()
    client = make_client(db, processor=processor, vector_store=store)

    res = client.post("/api/documents", files={"file": (raw, "内容".encode("utf-8"), "text/plain")})

    assert res.status_code == 201, res.json()
    assert db.saved_docs == [(expected, 1)]
    assert processor.seen == [("load", expected), ("chunks", expected)]
    assert res.json()["filename"] == expected
    parent_docs, child_docs = store.added[0]
    ids = [d.metadata["parent_id"] for d in parent_docs + child_docs]
    assert ids == [f"{expected}_parent_0"] * 2
    assert all(("/" not in i and "\\" not in i) for i in ids)


class ProcessorCfg:
    CHUNK_SIZE = 30
    CHUNK_OVERLAP = 5


@pytest.mark.parametrize("raw", ["..", "a/..", "..\\..", "./"])
def test_pure_traversal_name_is_refused_before_anything_is_written(raw):
    """清洗后什么都不剩的名字只能是 415，不能变成一条 filename=".." 的库记录。

    这里用真 DocumentProcessor：假处理器接受任何文件名，测不出这条拒绝路径。
    """
    db, store = RecordingDB(), RecordingVectorStore()
    client = make_client(db, processor=DocumentProcessor(ProcessorCfg()), vector_store=store)

    res = client.post("/api/documents", files={"file": (raw, "内容".encode("utf-8"), "text/plain")})

    assert res.status_code == 415, res.text
    assert db.saved_docs == []
    assert store.added == []


# --- 终审 D1：写不进去的文档必须在任何写入之前就说清楚 ---

class ZeroChunkProcessor(FakeDocProcessor):
    """切不出任何子块：真形态是图片型 PDF（PyPDF 只给空 page_content）与纯空白 txt。"""

    def create_parent_child_chunks(self, documents, filename):
        return [], []


def test_document_without_retrievable_chunks_is_422_and_writes_nothing():
    db, processor, store = RecordingDB(), ZeroChunkProcessor(), RecordingVectorStore()
    client = make_client(db, processor=processor, vector_store=store)

    res = client.post("/api/documents", files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")})

    assert res.status_code == 422, res.text
    assert res.json() == {"detail": "未能解析出可检索的文本内容"}
    # 这种文档永远检索不到，半创建（有行没块、或行已提交又回滚成「已回滚」的 500）都是误导
    assert db.saved_docs == []
    assert store.added == []
    assert store.deleted == []
    assert store.deleted_by_doc == []
    assert db.deleted_docs == []


def test_whitespace_only_txt_is_422_through_the_real_processor():
    """真 DocumentProcessor 对纯空白文本切出 0 块，这条拒绝得覆盖到真实解析路径。"""
    db, store = RecordingDB(), RecordingVectorStore()
    client = make_client(db, processor=DocumentProcessor(ProcessorCfg()), vector_store=store)

    res = client.post("/api/documents", files={"file": ("blank.txt", "  \n\n\t \n".encode("utf-8"), "text/plain")})

    assert res.status_code == 422, res.text
    assert db.saved_docs == []
    assert store.added == []


def make_long_filename(total_chars):
    """长度算到"清洗后"那一头：88 字符名 + "_parent_" + 序号才顶到 String(100)。"""
    return "a" * (total_chars - 4) + ".txt"


@pytest.mark.parametrize("length, expected", [(88, 201), (89, 422)])
def test_filename_length_guard_sits_at_88_chars(length, expected):
    db, processor, store = RecordingDB(), SpyProcessor(), RecordingVectorStore()
    client = make_client(db, processor=processor, vector_store=store)

    res = client.post("/api/documents", files={"file": (make_long_filename(length), "内容".encode("utf-8"), "text/plain")})

    assert res.status_code == expected, res.text
    if expected == 422:
        assert res.json() == {"detail": "文件名过长，请控制在 88 字符以内"}
        assert db.saved_docs == []
        assert store.added == []
        assert db.deleted_docs == []
    else:
        assert len(processor.seen) == 2


# --- 终审 D2：add_documents 半途失败时，孤儿向量只能按 document_id 找回 ---

class PartialAddVectorStore(FakeVectorStore):
    """真 VectorStore 的失败形态：两次写入之前就打好了 document_id 戳，父集合已落、子集合炸，返回值仍是不存在的 ids。"""

    def __init__(self, error=None):
        super().__init__()
        self.error = error or RuntimeError("chroma 写子集合时掉线")
        self.calls = []

    def add_documents(self, parent_docs, child_docs, document_id):
        for doc in parent_docs + child_docs:
            doc.metadata["document_id"] = str(document_id)
        raise self.error

    def delete_by_ids(self, parent_ids, child_ids):
        self.calls.append(("delete_ids", list(parent_ids), list(child_ids)))
        super().delete_by_ids(parent_ids, child_ids)

    def delete_by_document_id(self, document_id):
        self.calls.append(("sweep", document_id))
        super().delete_by_document_id(document_id)


def test_partial_vector_add_is_swept_by_document_id_first():
    """ids 为空时 delete_by_ids 删不到已写入的父向量（ parked-b）：清扫必须按 document_id，且排在补偿第一步。"""
    db = RecordingDB()
    store = PartialAddVectorStore()
    client = make_client(db, vector_store=store)

    res = client.post("/api/documents", files={"file": ("a.txt", "内容".encode("utf-8"), "text/plain")})

    assert res.status_code == 500
    assert res.json() == {"detail": "文档入库失败，已回滚"}
    assert store.deleted_by_doc == [42]
    # 顺序也是契约：先按 document_id 扫孤儿，再按 ids 精确删（后者在这里必然删不到东西）
    assert store.calls == [("sweep", 42), ("delete_ids", [], [])]
    assert db.deleted_docs == [42]
    assert db.chunks_saved is False
