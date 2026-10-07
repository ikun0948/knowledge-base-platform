class FakeConfig:
    # 只剩 /api/health 读的这一格（main.py 的健康检查报持久目录）。
    # 阶段二 Task 7 起问答凭证来自用户行，此前挂在这里的 OPENAI_* 三键随之拆掉——
    # "写了没人读"的字段在本仓是负资产（FakeVectorStore.stamped_user 记过同一笔账）。
    CHROMA_PERSIST_DIR = "fake://chroma"


class FakeDatabase:
    def __init__(self):
        self.saved_history = []

    def count_documents(self):
        return 1


class FakeOwnedParentsDB:
    """问答测的最小假库：递给它的 parent_id 一律算"属于你"。

    存在的理由是 chat 端点多了一个 db 依赖——那 29 条测不该为此各自造库，
    而越权那条路径由 test_ownership_isolation.py 用会过滤的假库专门钉。
    """

    def __init__(self):
        self.calls = []
        self.user_models = None   # None ⇒ 用下面那份缺省名单

    def owned_parent_ids(self, parent_ids, *, user_id):
        self.calls.append((tuple(parent_ids), user_id))
        return list(dict.fromkeys(parent_ids))

    def list_user_models(self, user_id):
        """默认一枚带 default：那 30 条 chat 测要能过 `_llm_context` 的名单检查。

        绝不往 self.calls 里记——`test_api_chat.py` 的
        `test_rag_question_passes_the_parent_pool_through_the_whitelist` 逐字比较那一份，
        多记一笔就把"白名单收到正确的 user_id"那条判据撞红。
        """
        return self.user_models if self.user_models is not None else [("fake-model", True)]

    def get_chat_history(self, session_id, *, user_id, limit=10):
        return []

    def delete_chat_history(self, session_id, *, user_id):
        return 0


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

    def chat_with_documents(self, ctx, question, parent_ids, session_id):
        if self.error:
            raise self.error
        return self.answer, self.refs

    def normal_chat(self, ctx, question, session_id):
        if self.error:
            raise self.error
        return self.answer

    def chat_with_documents_stream(self, ctx, question, parent_ids, session_id):
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

    def normal_chat_stream(self, ctx, question, session_id):
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

    业务代码读 `.id`（归属）、`.nickname`/`.avatar`（出参），阶段二起 `api/chat.py::_llm_context`
    还读 `.api_key`/`.base_url`（凭证）。缺省给一对假凭证而不是 None：问答测有 30 条，
    每条都要 200 才有意义，"没配 key"那条路径自己传 None。
    """

    def __init__(self, user_id=1, identifier="probe@local", nickname="探针",
                 api_key="sk-fake-user", base_url="https://fake-user/v1"):
        self.id = user_id
        self.identifier = identifier
        self.identifier_type = "email"
        self.nickname = nickname
        self.avatar = "auto"
        self.api_key = api_key
        self.base_url = base_url


def with_auth(app, user=None):
    """spec 7.1：各模块自己的 make_client 都要覆盖这一格，写成一函数免得五处各写各的。"""
    from deps import get_current_user

    app.dependency_overrides[get_current_user] = lambda: user or FakeUser()
    return app
