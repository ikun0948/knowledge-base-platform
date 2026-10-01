from datetime import datetime

from fastapi.testclient import TestClient

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

    def save_document(self, filename, file_path, content, chunk_count=0):
        self.saved_docs.append((filename, chunk_count))
        return self.saved_doc_id

    def save_chunks(self, doc_id, parent_docs, child_docs, parent_ids, child_ids):
        if self.save_chunks_error:
            raise self.save_chunks_error
        self.chunks_saved = True

    def get_document(self, doc_id):
        return type("Doc", (), {"id": doc_id, "filename": "a.txt", "chunk_count": 1,
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
