import chromadb
from langchain_chroma import Chroma
from langchain_openai import ChatOpenAI
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_classic.retrievers.document_compressors import LLMChainExtractor
from langchain_core.documents import Document


class VectorStore:
    def __init__(self, config):
        self.config = config
        # 初始化模型
        embed_path = self.config.LOCAL_MODEL_PATH
        self.embeddingd = HuggingFaceEmbeddings(model_name=embed_path)

        # 初始化Chroma客户端
        self.chroma_client = chromadb.PersistentClient(
            path=config.CHROMA_PERSIST_DIR,
        )

        # 父文档和子文档使用不同集合
        self.parent_vectorstore = Chroma(
            client=self.chroma_client,
            collection_name="parent_document",
            embedding_function=self.embeddingd
        )

        self.child_vectorstore = Chroma(
            client=self.chroma_client,
            collection_name="child_document",
            embedding_function=self.embeddingd
        )

        # 初始化大模型
        self.llm = ChatOpenAI(
            api_key=self.config.OPENAI_API_KEY,
            base_url=self.config.OPENAI_BASE_URL,
            model="qwen3.8-max",
            temperature=0,
        )

        self.compressor = LLMChainExtractor.from_llm(self.llm)

    def add_documents(self, parent_docs, child_docs, document_id):
        """添加文档到向量存储"""
        # 为所有文档添加document_id元数据
        for doc in parent_docs + child_docs:
            doc.metadata['document_id'] = str(document_id)
        # 存储父文档和子文档
        parent_ids = self.parent_vectorstore.add_documents(parent_docs)
        child_ids = self.child_vectorstore.add_documents(child_docs)
        # print(parent_ids, child_ids)
        return parent_ids, child_ids

    def create_retriever(self, document_ids=None):
        """创建子文档检索器(只负责初始召回)"""
        search_kwargs = {"k": self.config.TOP_K * 2}
        if document_ids:
            # 给检索器增加一个 元数据过滤条件
            search_kwargs["filter"] = {
                "document_id": {"$in": [str(i) for i in document_ids]}
            }
        # 返回一个 LangChain 检索器对象
        return self.child_vectorstore.as_retriever(search_kwargs=search_kwargs)

    def get_parent_documents(self, child_docs):
        """根据子文档获取对应的父文档的parent_id"""
        parent_ids = set() # 集合去重，如: 多个子文档可能属于同一个父文档
        for doc in child_docs:
            if 'parent_id' in doc.metadata:
                parent_ids.add(doc.metadata['parent_id'])

        return self.get_parent_documents_by_metadata(list(parent_ids))

    def get_parent_documents_by_metadata(self, parent_ids):
        if not parent_ids:
            return []
        parent_docs = []
        for parent_id in parent_ids:
            try:
                results = self.parent_vectorstore.get(
                    where={"parent_id": parent_id},
                    include=["documents", "metadatas"],
                )
                if results["documents"]:
                    parent_docs.append(Document(
                        page_content=results["documents"][0],
                        metadata=results["metadatas"][0] or {},
                    ))
            except Exception as e:
                print(f"获取父文档时出错 (parent_id: {parent_id}): {e}")
        return parent_docs