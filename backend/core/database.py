import logging
from sqlalchemy import create_engine, func, Column, Integer, String, DateTime, Boolean, ForeignKey, Index, Text
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

from exceptions import StorageError

logger = logging.getLogger("kb.database")

Base = declarative_base()


def _escape_like(raw: str) -> str:
    r"""挡掉 LIKE 的三个元字符。

    参数绑定挡住的是 SQL 注入，挡不住通配符语义：搜索框里的 `%` 是用户真想搜的那个字符，
    不是"任意串"。反斜杠必须最先替换，否则它会把随后补上的转义符再转义一遍。
    """
    return raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)

    __table_args__ = (
        Index('idx_documents_user_id', 'user_id'),
    )

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


# 账号表：identifier 单列存邮箱或手机号原文，配 identifier_type 说明它是哪一种。
# 为什么不做 email/phone 两列：两列各 nullable-unique 会让"同一手机号能注册两次"
# 这类边界要靠额外约束兜，单列 + 类型列天然唯一（spec 2.1）。
class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    identifier = Column(String(255), nullable=False, unique=True)
    identifier_type = Column(String(10), nullable=False)
    nickname = Column(String(50), nullable=False)
    # 预设头像标识（'auto' = 昵称首字母），不是图片 URL：本仓没有文件存储层（spec 决策 5）
    avatar = Column(String(20), nullable=False, default='auto')
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.now)


# 会话表：库里只有令牌哈希，令牌原文只在登录响应里出现一次（spec 4 节）
class AuthToken(Base):
    __tablename__ = 'auth_tokens'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.now)
    expires_at = Column(DateTime, nullable=False)

    __table_args__ = (
        Index('idx_tokens_user_id', 'user_id'),
    )


class DatabaseManager:
    def __init__(self, config):
        self.config = config
        self.engine = None
        self.SessionLocal = None
        self.init_database()

    def init_database(self):
        # 创建数据库连接
        connection_string = f"mysql+pymysql://{self.config.MYSQL_USER}:{self.config.MYSQL_PASSWORD}@{self.config.MYSQL_HOST}:{self.config.MYSQL_PORT}/{self.config.MYSQL_DATABASE}?charset=utf8mb4"

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

    def _find_parent_chunk(self, session, document_id, parent_id):
        """删块唯一的定位钥匙是 (document_id, parent_id) 这一对。

        parent_id 由清洗后的文件名拼出来，同名文档（不同 id）能造出同样的字符串，
        单靠它查就会把别人的块删掉。
        """
        return session.query(ParentChunk).filter(
            ParentChunk.document_id == document_id,
            ParentChunk.parent_id == parent_id,
        ).first()

    def search_parent_chunks(self, query="", suffix="", parent_ids=(), limit=50):
        """父块候选池：模糊搜文件名/块内文本，或按 parent_id 批量点查（后者优先）。

        三条不能反的规矩：
        * 只连 is_active 的文档——删块把 chunk_count 打到 0 的文档已隐存，
          它的残块摆进弹窗就是"选了也召回不到"的死条目。
        * 子块数用 outerjoin + GROUP BY 一次聚合。写成 len(chunk.child_chunks) 是 N+1，
          几百个块时弹窗会转圈。
        * 批量模式不吃 limit：hydrate 最多问 50 个 id，limit 插手会把选中项截没。
        """
        session = self.get_session()
        try:
            stmt = (
                session.query(
                    ParentChunk.parent_id,
                    ParentChunk.document_id,
                    ParentChunk.content,
                    Document.filename,
                    func.count(ChildChunk.id).label("child_count"),
                )
                .join(Document, Document.id == ParentChunk.document_id)
                .outerjoin(ChildChunk, ChildChunk.parent_chunk_id == ParentChunk.id)
                .filter(Document.is_active == True)
            )
            ids = list(dict.fromkeys(parent_ids))
            if ids:
                stmt = stmt.filter(ParentChunk.parent_id.in_(ids))
            else:
                if query:
                    pattern = f"%{_escape_like(query)}%"
                    stmt = stmt.filter(
                        Document.filename.like(pattern, escape="\\")
                        | ParentChunk.content.like(pattern, escape="\\")
                    )
                if suffix:
                    stmt = stmt.filter(Document.filename.ilike(f"%.{suffix.lower()}", escape="\\"))
            # group_by 必须在 limit 之前：Query 在已带 LIMIT 的语句上调它会直接抛 InvalidRequestError
            stmt = stmt.group_by(ParentChunk.id).order_by(
                ParentChunk.document_id.asc(), ParentChunk.parent_id.asc()
            )
            return stmt.all() if ids else stmt.limit(limit).all()
        finally:
            session.close()

    def plan_chunk_deletion(self, document_id, parent_id):
        """只读一步：把父块与其子块的 vector_id 交出去，好让端点先清向量再动行。"""
        session = self.get_session()
        try:
            chunk = self._find_parent_chunk(session, document_id, parent_id)
            if chunk is None:
                return None
            return {
                "document_id": document_id,
                "parent_id": parent_id,
                "parent_vector_id": chunk.vector_id,
                "child_vector_ids": [child.vector_id for child in chunk.child_chunks],
            }
        finally:
            session.close()

    def delete_parent_chunk(self, document_id, parent_id):
        """删父块行（cascade 带走子块），按剩余子块重算 chunk_count，归零则隐存文档。"""
        session = self.get_session()
        try:
            chunk = self._find_parent_chunk(session, document_id, parent_id)
            if chunk is None:
                return None
            deleted_children = len(chunk.child_chunks)
            # 必须是 session.delete(ORM对象)：cascade="all, delete-orphan" 挂在 relationship 上，
            # 只有走对象才生效；query.delete() 那种批量写法会把孤儿子行留在库里。
            session.delete(chunk)

            remaining = session.query(ChildChunk).filter(
                ChildChunk.document_id == document_id).count()
            doc = session.get(Document, document_id)
            # 重算而不是 chunk_count -= deleted_children：库里计数一旦漂过，减法会把它带进负数，
            # 重算顺手把已经不存在的事实修正掉。
            doc.chunk_count = remaining
            doc.is_active = remaining > 0
            session.commit()
            return {"deleted_children": deleted_children, "chunk_count": remaining,
                    "document_hidden": remaining == 0}
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

    def document_ids_for_parents(self, parent_ids):
        """parent_id → document_id 的反查：历史列的形状不变，靠这一步补齐。

        按入参顺序去重、库里没有的静默少返回——与 search_parent_chunks 同一句话：
        删掉的块不该在历史里留一个指向空的 id。
        """
        ids = list(dict.fromkeys(parent_ids))
        if not ids:
            return []
        session = self.get_session()
        try:
            rows = session.query(ParentChunk.parent_id, ParentChunk.document_id).filter(
                ParentChunk.parent_id.in_(ids)).all()
        finally:
            session.close()
        by_parent = {r.parent_id: r.document_id for r in rows}
        doc_ids = []
        for pid in ids:
            doc_id = by_parent.get(pid)
            if doc_id is not None and doc_id not in doc_ids:
                doc_ids.append(doc_id)
        return doc_ids

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

    # ---------- 账号与会话（spec 3.1/3.2）----------

    def create_user(self, identifier, identifier_type, nickname, password_hash, avatar="auto"):
        """返回可直读的 User 实例（会话已关掉之后仍然可读）。

        commit() 会把实例属性全部标记过期（sessionmaker 默认 expire_on_commit=True），
        finally 里的 close() 再把对象摘出会话——此时读 user.id 就是 DetachedInstanceError。
        所以 commit 之后立刻 refresh()：属性在会话还开着的时候重新灌满，返回的实例
        只剩普通列可读（它没有 relationship，也不去碰 relationship）。
        """
        session = self.get_session()
        try:
            user = User(identifier=identifier, identifier_type=identifier_type,
                        nickname=nickname, avatar=avatar, password_hash=password_hash)
            session.add(user)
            session.commit()
            session.refresh(user)
            return user
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_user_by_identifier(self, identifier):
        session = self.get_session()
        try:
            return session.query(User).filter(User.identifier == identifier).first()
        finally:
            session.close()

    def get_user_by_id(self, user_id):
        session = self.get_session()
        try:
            return session.get(User, user_id)
        finally:
            session.close()

    def count_users(self) -> int:
        session = self.get_session()
        try:
            return session.query(User).count()
        finally:
            session.close()

    def create_token(self, user_id, token_hash, expires_at):
        """返回可直读的 AuthToken 实例：commit() 让属性过期，所以 refresh() 必须在 close() 之前。

        与 create_user 同一件事——调用方（Task 2 的 /login）拿到的行要能读 row.id。
        """
        session = self.get_session()
        try:
            row = AuthToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
            session.add(row)
            session.commit()
            session.refresh(row)
            return row
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_user_by_token(self, token_hash):
        """一枚 join 同时验"令牌有效"与"账号还在"。

        过期行不是删除而是查不出来：`expires_at > now()` 让登出之外的第二种失效方式
        不需要后台清扫（30 天不用完的令牌躺在库里也换不到任何东西）。
        """
        session = self.get_session()
        try:
            return (session.query(User)
                    .join(AuthToken, AuthToken.user_id == User.id)
                    .filter(AuthToken.token_hash == token_hash,
                            AuthToken.expires_at > datetime.now())
                    .first())
        finally:
            session.close()

    def delete_token(self, token_hash) -> int:
        """登出 = 删这一行。返回删掉的行数，0 表示"本来就没有"，不是错误。"""
        session = self.get_session()
        try:
            deleted = session.query(AuthToken).filter(
                AuthToken.token_hash == token_hash).delete()
            session.commit()
            return deleted
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---------- 迁移用（Task 3 的 core/migrations.py 调这三条）----------

    def assign_unowned_documents(self, user_id) -> int:
        """只动 user_id IS NULL 的行：跑第二遍就是 0 行，这是整段迁移幂等的支点。"""
        session = self.get_session()
        try:
            n = session.query(Document).filter(Document.user_id.is_(None)).update(
                {Document.user_id: user_id}, synchronize_session=False)
            session.commit()
            return n
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def vector_ids_for_user(self, user_id):
        """按归属取两份 vector_id 清单——Chroma 的 id 就存这两列里（2026-10-04 live 验过）。"""
        session = self.get_session()
        try:
            parents = session.query(ParentChunk.vector_id).join(
                Document, Document.id == ParentChunk.document_id).filter(
                Document.user_id == user_id, ParentChunk.vector_id.isnot(None)).all()
            children = session.query(ChildChunk.vector_id).join(
                Document, Document.id == ChildChunk.document_id).filter(
                Document.user_id == user_id, ChildChunk.vector_id.isnot(None)).all()
            return {"parent": [r[0] for r in parents], "child": [r[0] for r in children]}
        finally:
            session.close()


