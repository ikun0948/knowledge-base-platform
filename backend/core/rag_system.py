from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
import uuid


class RAGSystem:
    def __init__(self, config, db_manager, vector_store):
        self.config = config
        self.db_manager = db_manager
        self.vector_store = vector_store

        # 初始化LLM（通义千问，兼容OpenAI接口格式）
        self.llm = ChatOpenAI(
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_BASE_URL,
            model="qwen3.8-max",
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
        """普通对话（不使用文档）"""
        try:
            # 获取历史对话
            chat_history = self.db_manager.get_chat_history(session_id)

            # 构建对话上下文
            messages = []
            for chat in chat_history[-5:]:  # 最近5轮对话
                messages.append(f"Human: {chat.user_message}")
                messages.append(f"Assistant: {chat.assistant_message}")

            # 添加当前问题
            messages.append(f"Human: {question}")

            conversation_context = "\n".join(messages)

            # 生成回答
            response = self.llm.invoke(conversation_context + "\nAssistant:")
            answer = response.content

            # 保存对话历史
            self.db_manager.save_chat_history(
                session_id=session_id,
                user_message=question,
                assistant_message=answer,
            )

            return answer

        except Exception as e:
            error_msg = f"普通对话出错: {str(e)}"
            print(error_msg)
            return error_msg

    def chat_with_documents(self, question, document_ids, session_id):
        """基于文档的RAG对话"""
        try:
            # 创建子文档检索器（限定在用户选中的文档范围内，只负责初始召回）
            retriever = self.vector_store.create_retriever(document_ids)
            retrieved_docs = retriever.invoke(question)

            # 回溯到父文档，获得完整上下文（Document对象）
            parent_docs = self.vector_store.get_parent_documents(retrieved_docs)
            if not parent_docs:
                return "未在选中的文档里找到相关内容，请换个问法或确认文档已上传。", []

            # 对父文档做上下文压缩，只保留与问题相关的部分
            compressed_docs = self.vector_store.compressor.compress_documents(
                parent_docs, question
            )
            context = "\n\n".join(d.page_content for d in compressed_docs)
            print("最终检索的上下文：", context)

            # 历史对话转为消息对象（MessagesPlaceholder不接受字符串）
            chat_history = self.db_manager.get_chat_history(session_id)
            history_msgs = []
            for chat in chat_history[-3:]:  # 最近3轮对话
                history_msgs.append(HumanMessage(content=chat.user_message))
                history_msgs.append(AIMessage(content=chat.assistant_message))

            # 组装提示词并生成回答
            answer = (self.rag_prompt | self.llm).invoke({
                "context": context,
                "chat_history": history_msgs,
                "question": question,
            }).content

            # 保存对话历史
            self.db_manager.save_chat_history(
                session_id=session_id,
                user_message=question,
                assistant_message=answer,
                document_ids=",".join(map(str, document_ids))
            )

            return answer, compressed_docs
        except Exception as e:
            error_msg = f"RAG对话出错: {str(e)}"
            print(error_msg)
            return error_msg, []

