import logging

import chromadb
from langchain_chroma import Chroma
from langchain_openai import ChatOpenAI
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_classic.retrievers.document_compressors import LLMChainExtractor
from langchain_core.documents import Document

logger = logging.getLogger("kb.vector_store")

COLLECTION_PARENT = "parent_document"
COLLECTION_CHILD = "child_document"


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
            collection_name=COLLECTION_PARENT,
            embedding_function=self.embeddingd
        )

        self.child_vectorstore = Chroma(
            client=self.chroma_client,
            collection_name=COLLECTION_CHILD,
            embedding_function=self.embeddingd
        )

        # 初始化大模型
        self.llm = ChatOpenAI(
            api_key=self.config.OPENAI_API_KEY,
            base_url=self.config.OPENAI_BASE_URL,
            model="qwen3.7-flash",
            temperature=0,
        )

        self.compressor = LLMChainExtractor.from_llm(self.llm)

    def collection_counts(self) -> dict:
        return {
            "parent": self.chroma_client.get_collection(COLLECTION_PARENT).count(),
            "child": self.chroma_client.get_collection(COLLECTION_CHILD).count(),
        }

    def delete_by_document_id(self, document_id):
        """尽力清扫：按 add_documents 打上的 document_id 戳删两个集合（id 列表不全时唯一找得回孤儿向量的键）。"""
        try:
            self.parent_vectorstore.delete(where={"document_id": str(document_id)})
        except Exception:
            logger.exception("按 document_id 清扫父集合失败: %s", document_id)
        try:
            self.child_vectorstore.delete(where={"document_id": str(document_id)})
        except Exception:
            logger.exception("按 document_id 清扫子集合失败: %s", document_id)

    def delete_by_ids(self, parent_ids, child_ids):
        """回滚入口：按向量 id 删除刚写入的块（spec 第七节 坑 3 的补偿动作）。"""
        if parent_ids:
            self.parent_vectorstore.delete(ids=parent_ids)
        if child_ids:
            self.child_vectorstore.delete(ids=child_ids)

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
            except Exception as exc:
                logger.warning("获取父文档失败 parent_id=%s: %s", parent_id, exc)
        return parent_docs