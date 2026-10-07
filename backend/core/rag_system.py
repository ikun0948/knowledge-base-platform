import json
import logging
import uuid

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from core.llm_factory import build_compressor, build_llm
from exceptions import LLMError, RetrievalError
from schemas.common import Reference, snippet_of

logger = logging.getLogger("kb.rag")

# detail 会被前端原样弹出来：固定文案，原始异常文本只进日志（spec 八节"不透堆栈给前端"）
LLM_FAILED = "大模型调用失败，请稍后重试"
RETRIEVAL_FAILED = "检索或上下文压缩失败，请稍后重试"
EMPTY_RETRIEVAL_ANSWER = "未在选中的文档里找到相关内容，请换个问法或确认文档已上传。"


class RAGSystem:
    def __init__(self, db_manager, vector_store,
                 llm_factory=build_llm, compressor_factory=build_compressor):
        """两个工厂作为参数注入，为的是链级判据不依赖真 ChatOpenAI。

        测试传 `lambda ctx: 假可运行对象`，生产用默认值，而默认值只可能来自
        `core/llm_factory.py`（坑 9 的收口方式）。注入工厂而不是注入 llm 本身：
        一次请求里答题链与压缩器都要建客户端，且压缩器和答题共用同一枚 ctx；
        把客户端存成属性就等于把某个人的 key 冻在进程级单例上——那正是本次要拆的东西。
        """
        self.db_manager = db_manager
        self.vector_store = vector_store
        self.llm_factory = llm_factory
        self.compressor_factory = compressor_factory

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

    def normal_chat(self, ctx, question, session_id):
        """普通对话（不使用文档）。"""
        chat_history = self.db_manager.get_chat_history(session_id, user_id=ctx.user_id)
        messages = []
        for chat in chat_history[-5:]:
            messages.append(f"Human: {chat.user_message}")
            messages.append(f"Assistant: {chat.assistant_message}")
        messages.append(f"Human: {question}")

        try:
            llm = self.llm_factory(ctx)
            answer = llm.invoke("\n".join(messages) + "\nAssistant:").content
        except Exception as exc:
            logger.exception("normal 链 LLM 调用失败")
            raise LLMError(LLM_FAILED) from exc

        self.db_manager.save_chat_history(
            session_id=session_id, user_message=question, assistant_message=answer,
            user_id=ctx.user_id,
        )
        return answer

    def chat_with_documents(self, ctx, question, parent_ids, session_id):
        """基于文档块的 RAG 问答：块内召回 → 回溯父块 → 压缩 → 带历史生成。

        落库列仍是 document_ids（形状不变，历史渲染与 mode 派生都吃它），
        所以进来先做一次反查。反查为空不是故障：池子全是死块，召回自然为空，
        走的还是 EMPTY_RETRIEVAL_ANSWER 那条既有分支。
        """
        doc_ids = self.db_manager.document_ids_for_parents(parent_ids)
        if parent_ids and not doc_ids:
            logger.warning("选中的文档块已全部失效，这一轮按空召回走: %s", parent_ids)
        no_retrieval = False
        try:
            retriever = self.vector_store.create_retriever(parent_ids, ctx.user_id)
            retrieved_docs = retriever.invoke(question)
            parent_docs = self.vector_store.get_parent_documents(retrieved_docs, ctx.user_id)
            if not parent_docs:
                # 检索为空不是故障：业务结果，用 200 携带说明文案，落库在 try 之后（终审 D4）
                no_retrieval = True
            else:
                compressed_docs = self.compressor_factory(ctx).compress_documents(parent_docs, question)
        except Exception as exc:
            logger.exception("检索或上下文压缩失败")
            raise RetrievalError(RETRIEVAL_FAILED) from exc

        if no_retrieval:
            # 落库在域错误包装之外：这一轮不进历史的话，刷新后它就凭空消失了（spec 五节"后端是真相"）
            self.db_manager.save_chat_history(
                session_id=session_id,
                user_message=question,
                assistant_message=EMPTY_RETRIEVAL_ANSWER,
                document_ids=",".join(map(str, doc_ids)),
                used_chunks=None,
                user_id=ctx.user_id,
            )
            return EMPTY_RETRIEVAL_ANSWER, []

        context = "\n\n".join(d.page_content for d in compressed_docs)
        logger.debug("最终检索上下文长度: %d", len(context))

        chat_history = self.db_manager.get_chat_history(session_id, user_id=ctx.user_id)
        history_msgs = []
        for chat in chat_history[-3:]:
            history_msgs.append(HumanMessage(content=chat.user_message))
            history_msgs.append(AIMessage(content=chat.assistant_message))

        try:
            llm = self.llm_factory(ctx)
            answer = (self.rag_prompt | llm).invoke(
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
            document_ids=",".join(map(str, doc_ids)),
            used_chunks=json.dumps([r.model_dump() for r in references], ensure_ascii=False),
            user_id=ctx.user_id,
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

    def normal_chat_stream(self, ctx, question, session_id):
        """normal 链流式版（spec 6.4）：只产 token；生成完成后落库一次。
        断流时消费方 close() 使 GeneratorExit 落在 yield 点——它不是 Exception，
        不会被下面的 except 捕获，落库自然执行不到（残缺答案绝不进历史）。"""
        chat_history = self.db_manager.get_chat_history(session_id, user_id=ctx.user_id)
        messages = []
        for chat in chat_history[-5:]:
            messages.append(f"Human: {chat.user_message}")
            messages.append(f"Assistant: {chat.assistant_message}")
        messages.append(f"Human: {question}")

        pieces = []
        try:
            llm = self.llm_factory(ctx)
            for chunk in llm.stream("\n".join(messages) + "\nAssistant:"):
                if chunk.content:
                    pieces.append(chunk.content)
                    yield ("token", chunk.content)
        except Exception as exc:
            logger.exception("normal 链 LLM 流式调用失败")
            raise LLMError(LLM_FAILED) from exc

        self.db_manager.save_chat_history(
            session_id=session_id, user_message=question, assistant_message="".join(pieces),
            user_id=ctx.user_id,
        )

    def chat_with_documents_stream(self, ctx, question, parent_ids, session_id):
        """rag 链流式版：references 事件先于一切 token（引用先于答案上屏，spec 6.4 帧表）。
        落库时机与非流版一致：生成完成之后、一次。落库列的 document_ids 由入参池子反查补齐。"""
        doc_ids = self.db_manager.document_ids_for_parents(parent_ids)
        if parent_ids and not doc_ids:
            logger.warning("选中的文档块已全部失效，这一轮按空召回走（流式）: %s", parent_ids)
        try:
            retriever = self.vector_store.create_retriever(parent_ids, ctx.user_id)
            retrieved_docs = retriever.invoke(question)
            parent_docs = self.vector_store.get_parent_documents(retrieved_docs, ctx.user_id)
            compressed_docs = None if not parent_docs else self.compressor_factory(ctx).compress_documents(parent_docs, question)
        except Exception as exc:
            logger.exception("检索或上下文压缩失败（流式）")
            raise RetrievalError(RETRIEVAL_FAILED) from exc

        if compressed_docs is None:
            references = []
            self.db_manager.save_chat_history(
                session_id=session_id,
                user_message=question,
                assistant_message=EMPTY_RETRIEVAL_ANSWER,
                document_ids=",".join(map(str, doc_ids)),
                used_chunks=None,
                user_id=ctx.user_id,
            )
            yield ("references", references)
            yield ("token", EMPTY_RETRIEVAL_ANSWER)
            return

        references = self._build_references(compressed_docs)
        yield ("references", references)

        context = "\n\n".join(d.page_content for d in compressed_docs)
        chat_history = self.db_manager.get_chat_history(session_id, user_id=ctx.user_id)
        history_msgs = []
        for chat in chat_history[-3:]:
            history_msgs.append(HumanMessage(content=chat.user_message))
            history_msgs.append(AIMessage(content=chat.assistant_message))

        pieces = []
        try:
            llm = self.llm_factory(ctx)
            for chunk in (self.rag_prompt | llm).stream(
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
            document_ids=",".join(map(str, doc_ids)),
            used_chunks=json.dumps([r.model_dump() for r in references], ensure_ascii=False),
            user_id=ctx.user_id,
        )
