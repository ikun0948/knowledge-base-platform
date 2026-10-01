import logging
import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from deps import get_db, get_doc_processor, get_vector_store
from exceptions import StorageError, UnsupportedDocumentType
from schemas.documents import DocumentOut

router = APIRouter(prefix="/api/documents")
logger = logging.getLogger("kb.api.documents")

# spec 六节端点表之外的新增校验：整份文件会被 read() 进内存，给个上界防 OOM。
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


@router.post("", status_code=201, response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    db=Depends(get_db),
    processor=Depends(get_doc_processor),
    vector_store=Depends(get_vector_store),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="文件内容为空")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 20MB")

    # 去掉任何路径成分：客户端可以塞 "a/../../b.txt"
    filename = os.path.basename(file.filename or "")
    try:
        documents = processor.load_document(filename, raw)
    except UnsupportedDocumentType as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    parent_docs, child_docs = processor.create_parent_child_chunks(documents, filename)
    content = "\n".join(d.page_content for d in documents)

    # 先落主记录拿 doc_id：向量元数据里的 document_id 依赖它（spec 六节）
    doc_id = db.save_document(filename=filename, file_path="", content=content,
                              chunk_count=len(child_docs))
    parent_ids, child_ids = [], []
    try:
        parent_ids, child_ids = vector_store.add_documents(parent_docs, child_docs, doc_id)
        db.save_chunks(doc_id, parent_docs, child_docs, parent_ids, child_ids)
    except Exception as exc:
        logger.exception("文档入库失败，开始回滚: %s", filename)
        vector_store.delete_by_ids(parent_ids, child_ids)
        db.delete_document(doc_id)
        raise StorageError("文档入库失败，已回滚") from exc

    saved = db.get_document(doc_id)
    return DocumentOut(id=saved.id, filename=saved.filename,
                       chunk_count=saved.chunk_count, created_at=saved.created_at)


@router.get("", response_model=list[DocumentOut])
def list_documents(db=Depends(get_db)):
    return [
        DocumentOut(id=d.id, filename=d.filename, chunk_count=d.chunk_count, created_at=d.created_at)
        for d in db.get_all_documents()
    ]
