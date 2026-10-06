class FakeConfig:
    CHROMA_PERSIST_DIR = "fake://chroma"


class FakeDatabase:
    def __init__(self):
        self.saved_history = []

    def count_documents(self):
        return 1


class FakeVectorStore:
    def __init__(self, counts=None):
        self.counts = counts or {"parent": 2, "child": 7}
        self.deleted = []
        self.deleted_by_doc = []

    def collection_counts(self):
        return dict(self.counts)

    def delete_by_ids(self, parent_ids, child_ids):
        self.deleted.append((list(parent_ids), list(child_ids)))

    def delete_by_document_id(self, document_id):
        self.deleted_by_doc.append(document_id)

    def add_documents(self, parent_docs, child_docs, document_id, *, user_id=None):
        # user_id 给默认值 None 是为同时服务新旧两组判据：test_api_documents.py 那 20 条不传，
        # 端点改完（Task 4 Step 6）之后所有调用都带真值，None 只剩"端点漏传"这一种坏情况。
        self.stamped_user = user_id
        return [f"p{i}" for i in range(len(parent_docs))], [f"c{i}" for i in range(len(child_docs))]


class FakeDocProcessor:
    def __init__(self, fail_with=None):
        self.fail_with = fail_with

    def load_document(self, filename, raw_bytes):
        if self.fail_with:
            raise self.fail_with
        return [type("D", (), {"page_content": raw_bytes.decode("utf-8"), "metadata": {}})()]

    def create_parent_child_chunks(self, documents, filename):
        parent = type("D", (), {"page_content": "父块", "metadata": {"parent_id": f"{filename}_parent_0", "doc_type": "parent"}})
        child = type("D", (), {"page_content": "子块", "metadata": {"parent_id": f"{filename}_parent_0", "child_id": "child_0_0", "doc_type": "child"}})
        return [parent()], [child()]


class FakeRAG:
    def __init__(self, answer="回答", refs=(), tokens=("片段1", "片段2"), error=None, error_after=None):
        self.answer = answer
        self.refs = list(refs)
        self.error = error
        self.tokens = list(tokens)
        # error_after=None：不抛错；整数=产出第 n 个 token 前抛（模拟流到一半失败）
        self.error_after = error_after

    def generate_session_id(self):
        return "fake-session"

    def chat_with_documents(self, question, parent_ids, session_id):
        if self.error:
            raise self.error
        return self.answer, self.refs

    def normal_chat(self, question, session_id):
        if self.error:
            raise self.error
        return self.answer

    def chat_with_documents_stream(self, question, parent_ids, session_id):
        if self.error is not None and self.error_after is None:
            raise self.error  # 检索/压缩失败：第一个事件都没有
        yield ("references", self.refs)
        emitted = 0
        for token in self.tokens:
            if self.error is not None and emitted == self.error_after:
                raise self.error
            yield ("token", token)
            emitted += 1
        if self.error is not None and self.error_after is not None and emitted == self.error_after:
            raise self.error  # error_after 越过 token 数：生成完成后、done 之前失败

    def normal_chat_stream(self, question, session_id):
        if self.error is not None and self.error_after is None:
            raise self.error
        emitted = 0
        for token in self.tokens:
            if self.error is not None and emitted == self.error_after:
                raise self.error
            yield ("token", token)
            emitted += 1


class FakeUser:
    """认证依赖在端点测试里的最小替身。

    业务代码只读 `.id`（归属）与 `.nickname`/`.avatar`（出参），所以这里只给这几个字段：
    多给一个用不到的字段，就多一个"测试通过但真 ORM 行里没有它"的坑。
    """

    def __init__(self, user_id=1, identifier="probe@local", nickname="探针"):
        self.id = user_id
        self.identifier = identifier
        self.identifier_type = "email"
        self.nickname = nickname
        self.avatar = "auto"


def with_auth(app, user=None):
    """spec 7.1：各模块自己的 make_client 都要覆盖这一格，写成一函数免得五处各写各的。"""
    from deps import get_current_user

    app.dependency_overrides[get_current_user] = lambda: user or FakeUser()
    return app
