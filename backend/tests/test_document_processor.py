import pytest
from core.document_processor import DocumentProcessor
from exceptions import UnsupportedDocumentType


class Cfg:
    CHUNK_SIZE = 30
    CHUNK_OVERLAP = 5


@pytest.fixture
def processor():
    return DocumentProcessor(Cfg())


def test_txt_bytes_are_loaded(processor):
    docs = processor.load_document("a.txt", "第一段。\n\n第二段。".encode("utf-8"))
    assert docs[0].page_content.startswith("第一段")


def test_unsupported_extension_raises_domain_error(processor):
    with pytest.raises(UnsupportedDocumentType):
        processor.load_document("virus.exe", b"MZ\x00")


def test_parent_child_ids_line_up(processor):
    """父子索引是全项目的立身之本：child 的 parent_id 必须能在 parent 列表里找到。"""
    documents = processor.load_document("a.txt", ("句子一。句子二。\n\n" * 8).encode("utf-8"))
    parents, children = processor.create_parent_child_chunks(documents, "a.txt")
    assert parents and children
    parent_ids = {p.metadata["parent_id"] for p in parents}
    assert all(c.metadata["parent_id"] in parent_ids for c in children)
    assert all(p.metadata["doc_type"] == "parent" for p in parents)
    assert all(c.metadata["doc_type"] == "child" for c in children)
    assert all(c.metadata["child_id"].startswith("child_") for c in children)


def test_single_short_document_does_not_index_error(processor):
    documents = processor.load_document("tiny.txt", "只有一行".encode("utf-8"))
    parents, children = processor.create_parent_child_chunks(documents, "tiny.txt")
    assert len(parents) == 1 and len(children) >= 1
