from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_community.document_loaders import Docx2txtLoader
import os
import tempfile

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

    def load_document(self, uploaded_file):
        """加载上传的文档"""
        # 保存临时文件，suffix获取后缀（UploadedFile 是 BytesIO 子类，后缀只能从其 name 取）
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp_file:
            # 获取当前数据
            tmp_file.write(uploaded_file.getvalue())
            # 获取当前临时文件地址
            tmp_path = tmp_file.name
        print(tmp_path)

        try:
            # 根据当前文件的类型选择加载器
            if uploaded_file.name.endswith('.pdf'):
                loader = PyPDFLoader(tmp_path)
            elif uploaded_file.name.endswith('.docx'):
                loader = Docx2txtLoader(tmp_path)
            elif uploaded_file.name.endswith('.txt'):
                loader = TextLoader(tmp_path, encoding='utf-8')
            else:
                raise ValueError(f"不支持当前文件的类型: {uploaded_file.name}")

            documents = loader.load()
            return documents

        finally:
            # 清理临时文件
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