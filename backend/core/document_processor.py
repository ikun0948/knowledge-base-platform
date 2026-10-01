import logging
import os
import tempfile
from functools import partial

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader
from langchain_core.documents import Document  # noqa: F401  (类型一致性检查用)
from langchain_text_splitters import RecursiveCharacterTextSplitter

from exceptions import UnsupportedDocumentType

logger = logging.getLogger("kb.document_processor")

SUPPORTED_SUFFIXES = (".pdf", ".docx", ".txt")
# txt 必须钉死 utf-8：不传 encoding 时 TextLoader 用系统编码，中文 Windows 是 cp936，读 UTF-8 字节直接报错
LOADER_BY_SUFFIX = {".pdf": PyPDFLoader, ".docx": Docx2txtLoader, ".txt": partial(TextLoader, encoding="utf-8")}

# 文档分割（父子索引）
class DocumentProcessor:
    def __init__(self, config):
        self.config = config
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.config.CHUNK_SIZE,
            chunk_overlap=self.config.CHUNK_OVERLAP,
            separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""]
        )

        # 父子文档分割器（RAG 父子检索 / 多向量检索方案）
        self.parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.config.CHUNK_SIZE * 2,  # 父文档块更大
            chunk_overlap=self.config.CHUNK_OVERLAP,
            separators=["\n\n", "\n", "。", "！", "？"]
        )

        self.child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.config.CHUNK_SIZE // 2,  # 子文档块更小
            chunk_overlap=self.config.CHUNK_OVERLAP // 2,
            separators=["\n", "。", "！", "？", ".", "!", "?", " "]
        )

    def load_document(self, filename: str, raw_bytes: bytes):
        """加载上传的文档。

        不再接收 Streamlit 的 UploadedFile：FastAPI 的 UploadFile、测试里的 bytes
        都能直接调用（spec 四节）。
        """
        # 去掉任何路径成分：客户端可以塞 "a/../../b.txt"
        safe_name = os.path.basename(filename)
        suffix = os.path.splitext(safe_name)[1].lower()
        if suffix not in SUPPORTED_SUFFIXES:
            raise UnsupportedDocumentType(f"不支持的文件类型: {suffix or safe_name}")

        loader_cls = LOADER_BY_SUFFIX[suffix]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(raw_bytes)
            tmp_path = tmp_file.name
        logger.debug("临时文件: %s", tmp_path)

        try:
            return loader_cls(tmp_path).load()
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def create_parent_child_chunks(self, documents, fileName):
        """创建父子文档块"""
        parent_docs = self.parent_splitter.split_documents(documents)
        child_docs = []

        for i, parent_doc in enumerate(parent_docs):
            # 为每个父文档创建唯一ID
            parent_id = f"{fileName}_parent_{i}"
            parent_doc.metadata['parent_id'] = parent_id
            # 添加doc_type字段: 父文档 or 子文档
            parent_doc.metadata['doc_type'] = 'parent'

            # 从父文档创建子文档, [parent_doc]包装成list
            child_chunks = self.child_splitter.split_documents([parent_doc])
            for j, child_doc in enumerate(child_chunks):
                # 用id进行关联
                child_doc.metadata['parent_id'] = parent_id
                # 第 n 个父文档中的第 m 个子文档，如：child_0_1
                child_doc.metadata['child_id'] = f"child_{i}_{j}"
                child_doc.metadata['doc_type'] = 'child'
                child_docs.append(child_doc)

        # 获取到父文档 子文档
        # 父文档 documents(metadata={'parent_id': 'aaa.txt_parent_0', 'doc_type': "parent"}, page_conten='文档内容')
        # 子文档 documents(metadata={'parent_id': 'aaa.txt_parent_0', 'doc_type': "child", 'child_id': 'child_0_0'}, page_conten='文档内容'

        return parent_docs, child_docs