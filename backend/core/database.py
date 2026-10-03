import logging
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Index, Text
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

from exceptions import StorageError

logger = logging.getLogger("kb.database")

Base = declarative_base()

# 定义一个创建documents表的类
class Document(Base):
    __tablename__ = 'documents'

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    content = Column(MEDIUMTEXT, nullable=False)
    chunk_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)
    is_active = Column(Boolean, default=True)

    # 关联关系 设定一对多表 ParentChunk 关联模型 back_populates 关联字段 cascade级联操作(删除操作)
    parent_chunks = relationship("ParentChunk", back_populates="document", cascade="all, delete-orphan")
    child_chunks = relationship("ChildChunk", back_populates="document", cascade="all, delete-orphan")

# 父文档表
class ParentChunk(Base):
    __tablename__ = 'parent_chunks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey('documents.id'), nullable=False)
    parent_id = Column(String(100), nullable=False, unique=True)  # 父文档唯一标识
    content = Column(Text, nullable=False)
    json_metadata = Column(Text)  # JSON格式存储元数据
    vector_id = Column(String(100))  # Chroma中的向量ID
    created_at = Column(DateTime, default=datetime.now)

    # 关联关系
    document = relationship("Document", back_populates="parent_chunks")
    child_chunks = relationship("ChildChunk", back_populates="parent_chunk", cascade="all, delete-orphan")

    # 索引  提高查询效率 通过树结构快速定位
    __table_args__ = (
        Index('idx_parent_document_id', 'document_id'),
        Index('idx_parent_id', 'parent_id'),
    )

# 子文档表
class ChildChunk(Base):
    __tablename__ = 'child_chunks'

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey('documents.id'), nullable=False)
    parent_chunk_id = Column(Integer, ForeignKey('parent_chunks.id'), nullable=False)
    child_id = Column(String(100), nullable=False)  # 子文档标识
    content = Column(Text, nullable=False)
    json_metadata = Column(Text)  # JSON格式存储元数据
    vector_id = Column(String(100))  # Chroma中的向量ID
    created_at = Column(DateTime, default=datetime.now)

    # 关联关系
    document = relationship("Document", back_populates="child_chunks")
    parent_chunk = relationship("ParentChunk", back_populates="child_chunks")

    # 索引
    __table_args__ = (
        Index('idx_child_document_id', 'document_id'),
        Index('idx_child_parent_id', 'parent_chunk_id'),
        Index('idx_child_id', 'child_id'),
    )

# 历史聊天记录表
class ChatHistory(Base):
    __tablename__ = 'chat_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(100), nullable=False)
    user_message = Column(Text, nullable=False)
    assistant_message = Column(Text, nullable=False)
    document_ids = Column(String(500))  # 存储使用的文档ID，逗号分隔
    used_chunks = Column(Text)  # JSON格式存储使用的文档块信息
    created_at = Column(DateTime, default=datetime.now)

    # 索引
    __table_args__ = (
        Index('ix_chat_history_session_id_created_at', 'session_id', 'created_at'),
        # 如果需要单独为 created_at 建立索引（例如全局清理旧数据时按时间查询）：
        # Index('ix_chat_history_created_at', 'created_at'),
    )

class DatabaseManager:
    def __init__(self, config):
        self.config = config
        self.engine = None
        self.SessionLocal = None
        self.init_database()

    def init_database(self):
        # 创建数据库连接
        connection_string = f"mysql+pymysql://{self.config.MYSQL_USER}:{self.config.MYSQL_PASSWORD}@{self.config.MYSQL_HOST}:{self.config.MYSQL_PORT}/{self.config.MYSQL_DATABASE}?charset=utf8"

        try:
            self.engine = create_engine(connection_string,echo=False)
            # 创建所有的表
            Base.metadata.create_all(self.engine)
            self.SessionLocal = sessionmaker(bind=self.engine)
            logger.info("数据库连接成功")
        except Exception:
            logger.exception("数据库连接失败")
            raise

    def get_session(self):
        return self.SessionLocal()

    def save_document(self, filename, file_path, content, chunk_count=0):
        """保存文档主记录，返回doc_id"""
        session = self.get_session()
        try:
            doc = Document(
                filename=filename,
                file_path=file_path,
                content=content,
                chunk_count=chunk_count
            )
            session.add(doc)
            session.commit()
            return doc.id
        finally:
            session.close()

    def save_chunks(self, doc_id, parent_docs, child_docs, parent_vector_ids, child_vector_ids):
        """保存父子文档块，并关联文档id与向量id"""
        session = self.get_session()
        try:
            # 保存父文档块
            parent_chunk_map = {}  # parent_id -> parent_chunk_id 映射
            for i, (parent_doc, vector_id) in enumerate(zip(parent_docs, parent_vector_ids)):
                parent_chunk = ParentChunk(
                    document_id=doc_id,
                    parent_id=parent_doc.metadata.get('parent_id', f'parent_{i}'),
                    content=parent_doc.page_content,
                    json_metadata=str(parent_doc.metadata),
                    vector_id=vector_id
                )
                session.add(parent_chunk)
                session.flush()
                # 把父文档parent_id和父文档表的id进行绑定 "txt_parent_0": 1
                parent_chunk_map[parent_chunk.parent_id] = parent_chunk.id

            # 保存子文档块
            for child_doc, vector_id in zip(child_docs, child_vector_ids):
                parent_id = child_doc.metadata.get('parent_id', 'unknown')
                parent_chunk_id = parent_chunk_map.get(parent_id) # 得到父文档表的id

                child_chunk = ChildChunk(
                    document_id=doc_id,
                    parent_chunk_id=parent_chunk_id,
                    child_id=child_doc.metadata.get('child_id', f'child_{len(child_docs)}'),
                    content=child_doc.page_content,
                    json_metadata=str(child_doc.metadata),
                    vector_id=vector_id
                )
                session.add(child_chunk)

            session.commit()

        except Exception as e:
            session.rollback()
            raise e

        finally:
            session.close()

    def get_all_documents(self):
        # 返回Document表中is_active == True的所有数据
        session = self.get_session()
        try:
            docs = session.query(Document).filter(Document.is_active == True).all()
            return docs
        finally:
            session.close()

    def get_document(self, doc_id):
        session = self.get_session()
        try:
            return session.get(Document, doc_id)
        finally:
            session.close()

    def delete_document(self, doc_id):
        """回滚专用：删 documents 行，parent/child_chunks 由 ORM cascade 带走。"""
        session = self.get_session()
        try:
            doc = session.get(Document, doc_id)
            if doc is None:
                return 0
            session.delete(doc)
            session.commit()
            return 1
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def count_documents(self) -> int:
        session = self.get_session()
        try:
            return session.query(Document).filter(Document.is_active == True).count()
        finally:
            session.close()

    def get_filenames_by_ids(self, doc_ids):
        """一次 IN 查询，供引用片段补 filename（spec 6.3，不做 N+1）。"""
        if not doc_ids:
            return {}
        session = self.get_session()
        try:
            rows = session.query(Document.id, Document.filename).filter(Document.id.in_(doc_ids)).all()
            return {row.id: row.filename for row in rows}
        finally:
            session.close()

    # 获取历史聊天记录
    def get_chat_history(self, session_id, limit=10):
        # 获取数据库操作游标
        session = self.get_session()
        try:
            chats = session.query(ChatHistory).filter(
                ChatHistory.session_id == session_id
            ).order_by(ChatHistory.id.desc()).limit(limit).all()
            return list(reversed(chats))
        finally:
            session.close()

    # 保存历史聊天记录
    def save_chat_history(self, session_id, user_message, assistant_message, document_ids=None, used_chunks=None):
        session = self.get_session()
        try:
            chat = ChatHistory(
                session_id=session_id,
                user_message=user_message,
                assistant_message=assistant_message,
                document_ids=document_ids,
                used_chunks=used_chunks
            )
            session.add(chat)
            session.commit()
        except Exception as e:
            session.rollback()
            # M2-7/M-b：裸 sqlalchemy 异常直上会让流式端点只能兜成"服务器内部错误"，
            # 策展文案永远不可达；这里收成领域异常，回滚与异常链都不丢
            raise StorageError("保存对话历史失败，请稍后重试") from e
        finally:
            session.close()

    def delete_chat_history(self, session_id):
        session = self.get_session()
        try:
            deleted = session.query(ChatHistory).filter(ChatHistory.session_id == session_id).delete()
            session.commit()
            return deleted
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


