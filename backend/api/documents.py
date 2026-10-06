import logging
import os

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import Field

from deps import get_current_user, get_db, get_doc_processor, get_vector_store
from exceptions import StorageError, UnsupportedDocumentType
from schemas.common import snippet_of
from schemas.documents import ChunkOut, DocumentOut

router = APIRouter(prefix="/api/documents")
logger = logging.getLogger("kb.api.documents")

# spec 六节端点表之外的新增校验：整份文件会被 read() 进内存，给个上界防 OOM。
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

# 清洗后的文件名要拼进 f"{filename}_parent_{i}" 存进 String(100) 的 ParentChunk.parent_id（core/database.py:34）
MAX_FILENAME_CHARS = 88


def _safe_filename(raw: str) -> str:
    """去掉任何路径成分：客户端可以塞 "a/../../b.txt"，也可以塞反斜杠版本。"""
    # os.path.basename 只认本平台那个分隔符，反斜杠先归一，Linux 部署面上才不会整串进库
    return os.path.basename(raw.replace("\\", "/"))


def _suffix_of(filename: str) -> str:
    """后缀取最后一个点之后并小写。rpartition 在没点时返回 ('', '', filename)，
    这时必须给空串——否则 README 会被判成"后缀=README"。"""
    _, dot, ext = filename.rpartition(".")
    return ext.lower() if dot else ""


@router.post("", status_code=201, response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    db=Depends(get_db),
    processor=Depends(get_doc_processor),
    vector_store=Depends(get_vector_store),
    user=Depends(get_current_user),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="文件内容为空")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 20MB")

    # 去掉任何路径成分：客户端可以塞 "a/../../b.txt"
    filename = _safe_filename(file.filename or "")
    try:
        documents = processor.load_document(filename, raw)
    except UnsupportedDocumentType as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    parent_docs, child_docs = processor.create_parent_child_chunks(documents, filename)
    if len(filename) > MAX_FILENAME_CHARS:
        raise HTTPException(status_code=422, detail=f"文件名过长，请控制在 {MAX_FILENAME_CHARS} 字符以内")
    if not child_docs:
        # 切不出子块的文档（图片型 PDF、纯空白 txt）永远检索不到，只能是 422，不该先落一行再炸成"已回滚"的 500
        raise HTTPException(status_code=422, detail="未能解析出可检索的文本内容")

    content = "\n".join(d.page_content for d in documents)

    # 先落主记录拿 doc_id：向量元数据里的 document_id 依赖它（spec 六节）
    doc_id = db.save_document(filename=filename, file_path="", content=content,
                              chunk_count=len(child_docs), user_id=user.id)
    parent_ids, child_ids = [], []
    try:
        parent_ids, child_ids = vector_store.add_documents(parent_docs, child_docs, doc_id,
                                                           user_id=user.id)
        db.save_chunks(doc_id, parent_docs, child_docs, parent_ids, child_ids)
    except Exception as exc:
        logger.exception("文档入库失败，开始回滚: %s", filename)
        # 每步补偿各自兜底：一步失败不能截断另一步，裸异常更不能逃逸到兜底 handler，
        # 否则 500 就失去了"整件事没发生"的可信度（spec 六节 坑 3）。
        # 这三步（delete_by_document_id / delete_by_ids / delete_document）**不加归属**：
        # 它们清的是刚由这个请求写出来的东西，谈不上越权（delete_document 的理由见 core/database.py）。
        try:
            vector_store.delete_by_document_id(doc_id)
        except Exception:
            logger.exception("回滚第零步失败：按 document_id 清扫未确认，可能残留孤儿向量: id=%s", doc_id)
        try:
            vector_store.delete_by_ids(parent_ids, child_ids)
        except Exception:
            logger.exception("回滚第一步失败：向量未确认删除，可能残留幽灵向量: %s", filename)
        try:
            db.delete_document(doc_id)
        except Exception:
            logger.exception("回滚第二步失败：documents 行未删除，幽灵状态残留: id=%s", doc_id)
        raise StorageError("文档入库失败，已回滚") from exc

    saved = db.get_document(doc_id, user_id=user.id)
    return DocumentOut(id=saved.id, filename=saved.filename,
                       chunk_count=saved.chunk_count, created_at=saved.created_at)


@router.get("", response_model=list[DocumentOut])
def list_documents(db=Depends(get_db), user=Depends(get_current_user)):
    return [
        DocumentOut(id=d.id, filename=d.filename, chunk_count=d.chunk_count, created_at=d.created_at)
        for d in db.get_all_documents(user_id=user.id)
    ]


@router.get("/chunks", response_model=list[ChunkOut])
def list_chunks(
    query: str = Query("", max_length=100),
    suffix: Literal["", "pdf", "docx", "txt"] = Query(""),
    parent_ids: list[Annotated[str, Field(min_length=1, max_length=100)]] = Query(
        default=[], max_length=50),
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
    user=Depends(get_current_user),
):
    """父块候选池。三种模式同一条路由：模糊搜（query+suffix）、批量点查（parent_ids，优先）、
    全量前 N（都不给）。拆成两条路由的话，前端 hydrate 与弹窗搜索会各自演化出一套过滤规则。

    注册位置钉在 /{document_id} 之前：FastAPI 按注册顺序匹配，将来加按 id 取文档的路由时
    写反了就会让 /chunks 变成"文档不存在"的 404。
    """
    rows = db.search_parent_chunks(
        user_id=user.id,
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


@router.delete("/{document_id}/chunks/{parent_id}", response_model=DocumentOut)
def delete_parent_chunk(document_id: int, parent_id: str,
                        db=Depends(get_db), vector_store=Depends(get_vector_store),
                        user=Depends(get_current_user)):
    """删一个父块连带它的子块。顺序不能反：先清向量，后删关系库的行。

    反过来的坏法不可自愈——行一旦没了，重试时 (document_id, parent_id) 就查不到块，
    那批还留在两个集合里的向量永远丢了把手：子块照旧被召回，父块却取不出来，
    整轮问答空转到"未在选中的文档里找到相关内容"。
    向量先删则任何一步失败都能重试：按 id 删已经不存在的向量是无害的 no-op，行还在原处。
    """
    plan = db.plan_chunk_deletion(document_id, parent_id, user_id=user.id)
    if plan is None:
        # 这一句现在盖三种情况：不存在、已删过、**别人的**。合起来正是 404 该有的样子——
        # 单说"不是你的"就等于承认"这块存在"，两种情况在响应上不可分辨才是对的。
        raise HTTPException(status_code=404, detail="文档块不存在或已被删除")

    try:
        vector_store.delete_by_ids([plan["parent_vector_id"]], plan["child_vector_ids"])
    except Exception as exc:
        logger.exception("父块向量删除失败，关系库未改动: doc=%s parent=%s", document_id, parent_id)
        raise StorageError("文档块删除未完成，请重试") from exc

    db.delete_parent_chunk(document_id, parent_id, user_id=user.id)

    saved = db.get_document(document_id, user_id=user.id)
    return DocumentOut(id=saved.id, filename=saved.filename,
                       chunk_count=saved.chunk_count, created_at=saved.created_at)
