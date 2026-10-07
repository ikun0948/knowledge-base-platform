import logging
from sqlalchemy import create_engine, func, Column, Integer, String, DateTime, Boolean, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.exc import IntegrityError
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
    # 每用户的大模型出口（spec 2.1）。明文入库是 spec 第 4 节记过的权衡：对称加密的主密钥
    # 只能躺在同一台机器的 .env 里，读盘的人两样都拿得到，等于只防"单独拖走数据库"。
    # 可空 = "还没配置"，它是 409 门禁的判据，不是缺省值。
    api_key = Column(String(255))
    base_url = Column(String(500))
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


# 用户自己维护的模型名单（决策 6：不去调远端 GET /models）。
# 单独一张表而不是逗号串：要做"增 / 删 / 设默认"三种行级操作，整串重写会在并发下互相覆盖。
class UserModel(Base):
    __tablename__ = 'user_models'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    # 长度上界 100 与 ChatRequest.model_name、ParentChunk.parent_id 同源：
    # 三个地方三种上界，早晚有一个会把用户的输入切掉半截。
    name = Column(String(100), nullable=False)
    is_default = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint('user_id', 'name', name='uq_user_models_user_name'),
        Index('idx_user_models_user_id', 'user_id'),
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

    def save_document(self, filename, file_path, content, chunk_count=0, *, user_id):
        """保存文档主记录，返回doc_id

        user_id 做成 keyword-only 且无默认值：忘记传归属必须是 TypeError 当场炸，
        不能是"写出一行 user_id IS NULL，于是它出现在所有人的候选池里"。
        NULL 只属于迁移前的旧行（Task 3 会把它们归给默认用户）。
        """
        session = self.get_session()
        try:
            doc = Document(
                filename=filename,
                file_path=file_path,
                content=content,
                chunk_count=chunk_count,
                user_id=user_id
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

    def get_all_documents(self, *, user_id):
        """当前用户的活动文档列表。原来那句 `filter(is_active == True)` 一个条件都没减，
        只是前面多了一道主人——列表类端点的隔离成本就是这样，一行 WHERE。"""
        session = self.get_session()
        try:
            return (session.query(Document)
                    .filter(Document.is_active == True, Document.user_id == user_id)
                    .all())
        finally:
            session.close()

    def get_document(self, doc_id, *, user_id):
        """按 id 取文档，但只取属于这个用户的。越权与不存在都回 None。

        不用 `session.get` 再看属性：那样写要多一次对象访问，而且把"先确认存在、再说没权限"
        的顺序带进了 SQL——404 的语义要求在**同一条** WHERE 里同时比 id 和主人。
        """
        session = self.get_session()
        try:
            return (session.query(Document)
                    .filter(Document.id == doc_id, Document.user_id == user_id)
                    .first())
        finally:
            session.close()

    def delete_document(self, doc_id):
        """回滚专用：删 documents 行，parent/child_chunks 由 ORM cascade 带走。

        不加归属是**有意为之的不对称**（Task 4 计划文 Step 4 明写）：它只服务两处——上传失败的
        自我回滚（那一行刚由这个请求自己写出来）和 live 测试的清理。给它补 user_id 只会让回滚
        多出一条"删除失败因为查不到"的歧义路径，而那条路径不可能发生。读到这儿别手痒去"补全"它。
        """
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

    def _find_parent_chunk(self, session, document_id, parent_id, user_id):
        """定位父块要 (document_id, parent_id) 这一对，外加"这块的主人是你"。

        parent_id 由清洗后的文件名拼出来，同名文档能造出同样的字符串；而 user_id 这一道
        挡的是另一件事：拿着别人 document_id 的请求。两者都要，缺一不可。
        """
        return (session.query(ParentChunk)
                .join(Document, Document.id == ParentChunk.document_id)
                .filter(ParentChunk.document_id == document_id,
                        ParentChunk.parent_id == parent_id,
                        Document.user_id == user_id)
                .first())

    def search_parent_chunks(self, *, user_id, query="", suffix="", parent_ids=(), limit=50):
        """父块候选池：模糊搜文件名/块内文本，或按 parent_id 批量点查（后者优先）。

        三条不能反的规矩：
        * 只连 is_active 的文档——删块把 chunk_count 打到 0 的文档已隐存，
          它的残块摆进弹窗就是"选了也召回不到"的死条目。
        * 子块数用 outerjoin + GROUP BY 一次聚合。写成 len(chunk.child_chunks) 是 N+1，
          几百个块时弹窗会转圈。
        * 批量模式不吃 limit：hydrate 最多问 50 个 id，limit 插手会把选中项截没。

        上面三条一条没变，只在 is_active 旁边多了一道主人（spec 3.3）：候选池是所有人的入口，
        这一行 WHERE 就是列表类隔离的全部成本。
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
                .filter(Document.is_active == True, Document.user_id == user_id)
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

    def plan_chunk_deletion(self, document_id, parent_id, *, user_id):
        """只读一步：把父块与其子块的 vector_id 交出去，好让端点先清向量再动行。

        查不到就是 None——"不存在""已删过""是你的"三种情况在这里合流，端点据此统一回 404。
        """
        session = self.get_session()
        try:
            chunk = self._find_parent_chunk(session, document_id, parent_id, user_id)
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

    def delete_parent_chunk(self, document_id, parent_id, *, user_id):
        """删父块行（cascade 带走子块），按剩余子块重算 chunk_count，归零则隐存文档。"""
        session = self.get_session()
        try:
            chunk = self._find_parent_chunk(session, document_id, parent_id, user_id)
            if chunk is None:
                return None
            deleted_children = len(chunk.child_chunks)
            # 必须是 session.delete(ORM对象)：cascade="all, delete-orphan" 挂在 relationship 上，
            # 只有走对象才生效；query.delete() 那种批量写法会把孤儿子行留在库里。
            session.delete(chunk)

            remaining = session.query(ChildChunk).filter(
                ChildChunk.document_id == document_id).count()
            # 原来这里是 session.get(Document, document_id)：只比 id 不比主人。
            # 同一条 WHERE 里带上 user_id（与 _find_parent_chunk 同一口径），并且它本来就在
            # 这个 session 里，不用新开一次查询——所以不另设 _owned_document 小助手，一种写法只留一处。
            doc = (session.query(Document)
                   .filter(Document.id == document_id, Document.user_id == user_id)
                   .first())
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

    def owned_parent_ids(self, parent_ids, *, user_id):
        """父块白名单：只回"确实属于这个用户"的那些 id。

        按入参顺序去重、库里没有的静默少回——与 document_ids_for_parents 同一口径。
        端点拿它和原始列表比长度，少一个就说明有人递了别人的 parent_id，回 404。
        """
        ids = list(dict.fromkeys(parent_ids))
        if not ids:
            return []
        session = self.get_session()
        try:
            rows = (session.query(ParentChunk.parent_id)
                    .join(Document, Document.id == ParentChunk.document_id)
                    .filter(ParentChunk.parent_id.in_(ids), Document.user_id == user_id)
                    .all())
        finally:
            session.close()
        allowed = {r.parent_id for r in rows}
        return [pid for pid in ids if pid in allowed]

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

    # ---------- 账号设置与模型名单（spec 2.1/3.1 的阶段二部分）----------

    def update_user_profile(self, user_id, nickname=None, avatar=None) -> int:
        """只改传了的那一格，返回受影响行数。

        整行 UPDATE 而不是"读出来再写回去"：nickname 与 avatar 各自独立，
        读改写会让两个并发请求互相覆盖掉对方那一格。
        """
        fields = {}
        if nickname is not None:
            fields["nickname"] = nickname
        if avatar is not None:
            fields["avatar"] = avatar
        if not fields:
            return 0
        return self._update_user(User, user_id, fields)

    def update_user_password(self, user_id, password_hash) -> int:
        return self._update_user(User, user_id, {"password_hash": password_hash})

    def update_user_llm(self, user_id, api_key, base_url) -> int:
        """key 与路由一起写：分开两个端点会造出"有 key 没路由"这个必 401 上游的半套配置（spec 3.4）。"""
        return self._update_user(User, user_id, {"api_key": api_key, "base_url": base_url})

    def _update_user(self, model, user_id, fields: dict) -> int:
        """按主键更新这几格，返回 rowcount。

        口径的覆盖面要说准：`update_user_password` 与 `update_user_llm` 的返回值确实出自这里，
        但 `update_user_profile` 只在**至少传了一格**时才走到这里——它自己那句
        `if not fields: return 0` 是另一码事（一个字段都没传，连 UPDATE 都不发）。

        在当前驱动下 **这里的 `0` 只有一种来路：这一行不存在**。
        裸 MySQL 在不带 `CLIENT_FOUND_ROWS` 时 UPDATE 的 affected_rows 只数**真被改变**的行，
        那种驱动下同值重写会回 `0`；但本项目走 SQLAlchemy 的 MySQL 方言，它在连接时
        **硬编码**把 `CLIENT_FOUND_ROWS` 或进 client_flag
        （site-packages/sqlalchemy/dialects/mysql/base.py:709-715、mysqldb.py:244-251），
        rowcount 被标准化成"匹配到的行数"。本机 2026-10-07 实测：不存在的 id 回 `0`，
        同值重写回 `1`——所以这里数的从来不是"真被改的行"（真值表与判据见
        tests/test_live_database.py 的 `test_empty_profile_update_touches_nothing`）。
        哪天换了驱动或客户端标志，`0` 才会多出"值原样未变"这一种来路。

        不管哪种驱动，**端点都不要拿这个返回值判 404**：它既不等于"成功"也不等于"存在"。
        用户存在性由 auth 依赖保证（令牌换出的行已在库里），计划 Task 2 的端点正文确实不读
        这个返回值——这句是给后来人的护栏，别顺手写成 `if not rows: raise HTTPException(404)`。
        真要区分"没这行"与"值原样未变"，去 get_user_by_id，不要在这里加一次 SELECT。
        """
        session = self.get_session()
        try:
            updated = session.query(model).filter(model.id == user_id).update(fields)
            session.commit()
            return updated
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_user_models(self, user_id) -> list:
        """返回 [(name, is_default)]，按 id 升序 = 用户添加的顺序。

        "第一个"的口径必须钉住：spec 3.4 的"没有 default 就取名单第一个"是问答链的兜底，
        按 name 排会让它随字母序漂移，用户在界面上选中的和实际打出去的对不上。
        会话关闭前就展平成元组：别让调用方去摸已 detach 的 ORM 行（create_user 的 docstring 记过这个坑）。
        """
        session = self.get_session()
        try:
            rows = (session.query(UserModel).filter(UserModel.user_id == user_id)
                    .order_by(UserModel.id).all())
            return [(r.name, bool(r.is_default)) for r in rows]
        finally:
            session.close()

    def add_user_model(self, user_id, name) -> bool:
        """True = 新增；False = 名单里已经有了（端点据此回 409）。

        **名单原本为空时这一枚自动成为默认**（计划级补全，spec 未写）：只配了一个模型的
        用户从来不会去点"设为默认"，没有这一步他的名单就是"有一个人、一个默认都没有"，
        而设置端点回给前端的 `default_model` 也一直是 None。有了它，spec 3.4 的
        "没有 default 就取名单第一个"退成纯兜底。
        """
        session = self.get_session()
        try:
            hit = session.query(UserModel.id).filter(UserModel.user_id == user_id,
                                                     UserModel.name == name).first()
            if hit:
                return False
            # 判空必须是**另一次不带 name 过滤**的查询：复用上面那次 hit 等于拿
            # "名单里没有这个名字"当"名单是空的"，第二枚也会被标成默认，之后两个默认并存
            # （实测：改成复用 hit 之后只有 live 的 test_user_settings_round_trip 红，离线全绿）。
            is_first = session.query(UserModel.id).filter(
                UserModel.user_id == user_id).first() is None
            session.add(UserModel(user_id=user_id, name=name, is_default=is_first))
            session.commit()
            return True
        except IntegrityError:
            # 上面那次预查挡不住并发：两个请求同时"查不到"就同时插，unique 键才是唯一真相
            session.rollback()
            return False
        finally:
            session.close()

    def delete_user_model(self, user_id, name) -> int:
        """返回删掉的行数（0 = 名单里本来没这个名字）。

        **不**自动把下一个提成默认：spec 3.4 的解析规则自带"没有 default 就取名单第一个"，
        回落点在读取侧。写入侧再动一次默认会让"删掉默认"变成"悄悄换了个人"。
        """
        session = self.get_session()
        try:
            deleted = session.query(UserModel).filter(UserModel.user_id == user_id,
                                                      UserModel.name == name).delete()
            session.commit()
            return deleted
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def set_default_user_model(self, user_id, name) -> bool:
        """一事务内"清掉别人的 is_default + 立这一个"。

        分两次调用（先全清再立）会在两次之间留下"零个默认"或"两个默认"的中间态，
        而问答链正好读这个值决定用哪个模型。
        """
        session = self.get_session()
        try:
            target = session.query(UserModel).filter(UserModel.user_id == user_id,
                                                     UserModel.name == name).first()
            if target is None:
                return False
            (session.query(UserModel)
             .filter(UserModel.user_id == user_id, UserModel.name != name)
             .update({"is_default": False}))
            target.is_default = True
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


