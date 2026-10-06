import json
import logging
import uuid

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from exceptions import LLMError, RetrievalError
from schemas.common import Reference, snippet_of

logger = logging.getLogger("kb.rag")

# detail 会被前端原样弹出来：固定文案，原始异常文本只进日志（spec 八节"不透堆栈给前端"）
LLM_FAILED = "大模型调用失败，请稍后重试"
RETRIEVAL_FAILED = "检索或上下文压缩失败，请稍后重试"
EMPTY_RETRIEVAL_ANSWER = "未在选中的文档里找到相关内容，请换个问法或确认文档已上传。"


class RAGSystem:
    def __init__(self, config, db_manager, vector_store):
        self.config = config
        self.db_manager = db_manager
        self.vector_store = vector_store

        # 初始化LLM（通义千问，兼容OpenAI接口格式）；模型名硬编码，spec 第七节坑 9 本次不动
        self.llm = ChatOpenAI(
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_BASE_URL,
            model="qwen3.7-flash",
            temperature=0.7,
            streaming=True,
        )

        self.rag_prompt = ChatPromptTemplate.from_messages([
            ("system", """你是一个智能助手。请基于以下上下文信息回答用户的问题。如果上下文中没有相关信息，请诚实地说明。
        上下文信息:
        {context}"""),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{question}")
        ])

    def generate_session_id(self):
        # 生成会话id 判断是否是同一个用户
        return str(uuid.uuid4())

    def normal_chat(self, question, session_id):
        """普通对话（不使用文档）。"""
        chat_history = self.db_manager.get_chat_history(session_id)
        messages = []
        for chat in chat_history[-5:]:
            messages.append(f"Human: {chat.user_message}")
            messages.append(f"Assistant: {chat.assistant_message}")
        messages.append(f"Human: {question}")

        try:
            answer = self.llm.invoke("\n".join(messages) + "\nAssistant:").content
        except Exception as exc:
            logger.exception("normal 链 LLM 调用失败")
            raise LLMError(LLM_FAILED) from exc

        self.db_manager.save_chat_history(
            session_id=session_id, user_message=question, assistant_message=answer
        )
        return answer

    def chat_with_documents(self, question, document_ids, session_id):
        """基于文档的 RAG 问答：子块召回 → 回溯父块 → 压缩 → 带历史生成。"""
        no_retrieval = False
        try:
            retriever = self.vector_store.create_retriever(document_ids)
            retrieved_docs = retriever.invoke(question)
            parent_docs = self.vector_store.get_parent_documents(retrieved_docs)
            if not parent_docs:
                # 检索为空不是故障：业务结果，用 200 携带说明文案，落库在 try 之后（终审 D4）
                no_retrieval = True
            else:
                compressed_docs = self.vector_store.compressor.compress_documents(parent_docs, question)
        except Exception as exc:
            logger.exception("检索或上下文压缩失败")
            raise RetrievalError(RETRIEVAL_FAILED) from exc

        if no_retrieval:
            # 落库在域错误包装之外：这一轮不进历史的话，刷新后它就凭空消失了（spec 五节"后端是真相"）
            self.db_manager.save_chat_history(
                session_id=session_id,
                user_message=question,
                assistant_message=EMPTY_RETRIEVAL_ANSWER,
                document_ids=",".join(map(str, document_ids)),
                used_chunks=None,
            )
            return EMPTY_RETRIEVAL_ANSWER, []

        context = "\n\n".join(d.page_content for d in compressed_docs)
        logger.debug("最终检索上下文长度: %d", len(context))

        chat_history = self.db_manager.get_chat_history(session_id)
        history_msgs = []
        for chat in chat_history[-3:]:
            history_msgs.append(HumanMessage(content=chat.user_message))
            history_msgs.append(AIMessage(content=chat.assistant_message))

        try:
            answer = (self.rag_prompt | self.llm).invoke(
                {"context": context, "chat_history": history_msgs, "question": question}
            ).content
        except Exception as exc:
            logger.exception("rag 链 LLM 调用失败")
            raise LLMError(LLM_FAILED) from exc

        references = self._build_references(compressed_docs)
        self.db_manager.save_chat_history(
            session_id=session_id,
            user_message=question,
            assistant_message=answer,
            document_ids=",".join(map(str, document_ids)),
            used_chunks=json.dumps([r.model_dump() for r in references], ensure_ascii=False),
        )
        return answer, references

    def _build_references(self, compressed_docs):
        filenames = self.db_manager.get_filenames_by_ids(
            sorted({int(d.metadata["document_id"]) for d in compressed_docs})
        )
        references = []
        for doc in compressed_docs:
            document_id = int(doc.metadata["document_id"])
            references.append(Reference(
                document_id=document_id,
                parent_id=doc.metadata.get("parent_id", ""),
                filename=filenames.get(document_id, ""),
                snippet=snippet_of(doc.page_content),
            ))
        return references

    def normal_chat_stream(self, question, session_id):
        """normal 链流式版（spec 6.4）：只产 token；生成完成后落库一次。
        断流时消费方 close() 使 GeneratorExit 落在 yield 点——它不是 Exception，
        不会被下面的 except 捕获，落库自然执行不到（残缺答案绝不进历史）。"""
        chat_history = self.db_manager.get_chat_history(session_id)
        messages = []
        for chat in chat_history[-5:]:
            messages.append(f"Human: {chat.user_message}")
            messages.append(f"Assistant: {chat.assistant_message}")
        messages.append(f"Human: {question}")

        pieces = []
        try:
            for chunk in self.llm.stream("\n".join(messages) + "\nAssistant:"):
                if chunk.content:
                    pieces.append(chunk.content)
                    yield ("token", chunk.content)
        except Exception as exc:
            logger.exception("normal 链 LLM 流式调用失败")
            raise LLMError(LLM_FAILED) from exc

        self.db_manager.save_chat_history(
            session_id=session_id, user_message=question, assistant_message="".join(pieces)
        )

    def chat_with_documents_stream(self, question, document_ids, session_id):
        """rag 链流式版：references 事件先于一切 token（引用先于答案上屏，spec 6.4 帧表）。
        落库时机与非流版一致：生成完成之后、一次。"""
        try:
            retriever = self.vector_store.create_retriever(document_ids)
            retrieved_docs = retriever.invoke(question)
            parent_docs = self.vector_store.get_parent_documents(retrieved_docs)
            compressed_docs = None if not parent_docs else self.vector_store.compressor.compress_documents(parent_docs, question)
        except Exception as exc:
            logger.exception("检索或上下文压缩失败（流式）")
            raise RetrievalError(RETRIEVAL_FAILED) from exc

        if compressed_docs is None:
            references = []
            self.db_manager.save_chat_history(
                session_id=session_id,
                user_message=question,
                assistant_message=EMPTY_RETRIEVAL_ANSWER,
                document_ids=",".join(map(str, document_ids)),
                used_chunks=None,
            )
            yield ("references", references)
            yield ("token", EMPTY_RETRIEVAL_ANSWER)
            return

        references = self._build_references(compressed_docs)
        yield ("references", references)

        context = "\n\n".join(d.page_content for d in compressed_docs)
        chat_history = self.db_manager.get_chat_history(session_id)
        history_msgs = []
        for chat in chat_history[-3:]:
            history_msgs.append(HumanMessage(content=chat.user_message))
            history_msgs.append(AIMessage(content=chat.assistant_message))

        pieces = []
        try:
            for chunk in (self.rag_prompt | self.llm).stream(
                {"context": context, "chat_history": history_msgs, "question": question}
            ):
                if chunk.content:
                    pieces.append(chunk.content)
                    yield ("token", chunk.content)
        except Exception as exc:
            logger.exception("rag 链 LLM 流式调用失败")
            raise LLMError(LLM_FAILED) from exc

        self.db_manager.save_chat_history(
            session_id=session_id,
            user_message=question,
            assistant_message="".join(pieces),
            document_ids=",".join(map(str, document_ids)),
            used_chunks=json.dumps([r.model_dump() for r in references], ensure_ascii=False),
        )
