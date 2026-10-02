# 阶段二：SSE 流式对话 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `POST /api/chat` 的一次性问答升级为 `POST /api/chat/stream` SSE 流式问答（`meta`/`references`/`token`/`done`/`error` 五种帧），前端 `fetch` + `ReadableStream` 消费并**删除 `utils/typewriter.js`**；顺手闭合阶段一终审移交的三个契约缺口（刷新后来源标签、`document_ids` 无界、AbortError 约定）。

**Architecture:** 后端 `rag_system` 新增两个流式生成器方法（`chat_with_documents_stream` / `normal_chat_stream`，**生成完成才写历史、断流不写半截**）；`api/chat.py` 用 `StreamingResponse` 手拼 SSE 帧（不引新依赖），`meta` 发出后一切失败都降级为 `error` 帧；前端 `api/client.js` 新增 `postStream`（全项目第一个 `signal` 使用者，AbortError 约定就此落地），`useChat` 改事件驱动。`POST /api/chat` **原样保留**作为回退路径（spec 十一节"第 8 步失败可退回第 7 步末状态"）。

**Tech Stack:** FastAPI + `StreamingResponse`（starlette 内置）+ `langchain_openai` 的 `.stream()`；Vue 3 组合式 + 原生 `fetch`/`ReadableStream`/`TextDecoder`/`AbortController`。**两侧零新增依赖**（本机全局环境禁装禁升级，见 Global Constraints）。

**Spec:** `docs/superpowers/specs/2026-09-30-kb-platform-frontend-backend-split-design.md` 第 6.4 节（帧协议逐字）与十一节第 8 步（本计划的直接来源）。移交底稿：`.superpowers/sdd/2026-09-30-kb-platform-frontend/progress.md` 终审节（G-1/G-2/G-3/G-5、L-4/L-5/L-6/L-10）与 `task-7-report.md` 遗留表、`final-review.md`。

**分支与基线：** 从 `master`（阶段一 FF 合并点之后，当前 HEAD `80fb1aa` 或其后的 ledger 收尾提交）新建 `feat/sse-stream` 实施，收尾时再决定合并方式。数据基线继承阶段一终审后现场：`documents` 9 行（#1,#69,#71,#72,#74,#75,#76,#77,#78）、`chat_history` ≥25 行/10 会话、legacy 会话 `0a6e5ed2…`（2026-09-19，`used_chunks`/`document_ids` 均为 NULL）。`legacy_streamlit/` 冻结不动。

---

## Global Constraints（每个 Task 的要求都隐含包含本节）

- **零新增依赖、零安装**：`fastapi`/`uvicorn`/`langchain*`/`httpx` 等全部用 `D:\python\python.exe`（3.12.3）全局已装版本；前端 `package.json` 不加任何依赖。解释器只用 PATH 上的 `python`，**绝不用 `D:/AI-python/.venv`**（空 3.14 假 venv）。
- **平台硬约束（本机实测）**：第二个 uvicorn 实例因 embedding 模型再加载必 os error 1455 起不动——**全程单后端**。复用现存服务（控制方已起：uvicorn `--reload` :8000、vite dev :5173，收尾时若已死可由实施代理自起并记录 PID 白名单）；非自启进程一律不杀。`:8000` 挂着 `--reload`，后端文件编辑期间的 502 抖动属正常，重试即可。
- **代理拓扑 502 事实**：后端宕机时浏览器拿到的是 Vite 代理返回的空体 502（`HTTP 502`），不是网络失败；"无法连接后端"文案仅在直连 :8000 时可达。手测判据按此写，不按直觉写。
- **帧协议逐字钉死（spec 6.4）**：事件名只有 `meta` / `references` / `token` / `done` / `error` 五个；`data:` 是**单行 JSON**（`json.dumps(..., ensure_ascii=False, default=str)` 的输出天然不含裸换行，中文逐字可读）。payload 形状：`meta={mode, session_id}`、`references=[Reference 四键]`、`token={text}`、`done={}`、`error={detail}`。
- **不写半截历史**：写历史只发生在生成完成之后；生成中途断流（`GeneratorExit`）时**宁可不写**，也绝不把残缺答案落进 `chat_history` 污染后续上下文（spec 6.4 实现要点逐字）。
- **安全（坑 6 不变）**：全项目 `v-html`/`innerHTML` 零出现；SSE 帧文本、答案、片段一律 `{{ }}` 插值 + `white-space: pre-wrap`。后端依旧不转义任何 HTML，转义是渲染层职责。
- **字段命名保持 snake_case**（`session_id` / `document_ids` / `mode` / `detail`），前端不做 camelCase 映射层。
- **引用形状不变**：`{document_id, parent_id, filename, snippet}`，`snippet` 最长 83（后端 `SNIPPET_LIMIT = 80` + `"..."`），前端不再截断。
- **CSS 纪律**：颜色字面值只允许出现在 `variables.css`（阶段一终审核定的 11 处豁免保持原样，本计划不新增第 12 处）；组件不写 `<style>` 块；`layout.css` 只允许文件末尾追加（append-only）。本计划**预期不动 CSS**——`streaming-cursor`、`.pre-wrap`、气泡样式全部原样复用（SSE 下 `streaming` 由 `done`/`error`/abort 置 false）。
- **Git**：仓库根 `D:/知识库平台-前后端分离`；提交身份一律 `git -c user.name="31439" -c user.email="31439@local" commit`，不改配置、不 `--amend`、不 `--no-verify`；`.env` 与 `D:/AI-python/**` 绝不触碰；`frontend/dist/`、`node_modules/` 已被 gitignore，构建产物不进库。
- **文案与注释**：界面字符串全中文；注释只写"为什么"，一行以内。
- **验证 = 后端 pytest + 前端手测**：后端每步 TDD（先失败测试后实现）；前端没有测试框架，每个前端 Task 结尾是浏览器/Console/curl 核对清单 + 一次静态把关。
- **数据纪律**：手测产生的新文档/新会话一律保留不清库；**同名文档禁止重传**（后端唯一键会 500，属已记档限制 L-5）；`xss.txt` 用库内 #74，不重传。

---

## File Structure（谁负责什么、谁被改）

### 后端（`backend/`）

| 文件 | 动作 | 责任 |
|---|---|---|
| `core/rag_system.py` | Modify（文件末尾追加两个方法，不动既有 `normal_chat`/`chat_with_documents`） | 流式生成器：`normal_chat_stream()` 与 `chat_with_documents_stream()`，产出 `("references", refs)` / `("token", text)` 事件元组，**生成完成后落库一次** |
| `api/chat.py` | Modify（新增 `_sse()` 与 `chat_stream` 端点；既有 `chat` 端点原样保留） | SSE 编码与帧序装配；`meta` 后的一切失败降级为 `error` 帧 |
| `schemas/chat.py` | Modify | `ChatRequest.document_ids` 加 50 项上限（G-1）；`HistoryMessage` 加 `mode` 字段（L-4） |
| `api/history.py` | Modify | 由行的 `document_ids` 派生 assistant 行的 `mode`，零 DB 迁移 |
| `tests/fakes.py` | Modify | `FakeRAG` 增加两个流式桩方法（可控中途抛错） |
| `tests/test_rag_system.py` | Modify（末尾追加"流式生成器"段） | 生成器语义：帧序、落库时机、`gen.close()` 不落库 |
| `tests/test_api_chat.py` | Modify（末尾追加"/api/chat/stream"段） | 帧协议、状态码边界、错误降级 |
| `tests/test_api_history.py` | Modify | `mode` 派生与 legacy 行表现 |

### 前端（`frontend/`）

| 文件 | 动作 | 责任 |
|---|---|---|
| `src/api/client.js` | Modify（末尾追加 `postStream` + `dispatch`） | SSE 帧切分与派发；AbortError 约定落地（G-2 收口） |
| `src/api/chat.js` | Modify（Task 4 追加 `sendChatStream`；Task 5 删除 `sendChat`） | 流式出口单函数；删除时机与调用方切换同提交，不留死代码 |
| `src/composables/useChat.js` | Modify（`send` 改事件驱动；新增内部 `abortStream`） | 流消费、气泡生命周期、断流即撤本地消息的一致性策略 |
| `src/utils/typewriter.js` | **Delete**（`git rm`） | spec 十一节第 8 步逐字：SSE 落地当天整文件删除 |
| `src/components/MessageList.vue` | Modify（仅改一处注释措辞） | 跟底 watch 的理由从"打字机每 20ms"改为"token 帧持续推高内容"；逻辑零改动 |
| `src/App.vue` / `ChatInput.vue` / `MessageBubble.vue` / `ReferenceList.vue` / 样式三件套 | **不动** | `streaming-cursor`、`mode` 标签、`pending` 禁用输入——阶段一形状天然承接流式（Task 5 已论证） |

### 工作区（`.superpowers/sdd/2026-10-02-kb-platform-sse/`）

ledger `progress.md`（执行时由控制方创建）+ 各 Task brief/report/review 落盘（**执行纪律：评审返回即落盘**，阶段一 G-7 的教训）。

---

## 移交项对照（本计划做哪些、留哪些）

| 阶段一记档 | 落点 | 处置 |
|---|---|---|
| G-2 AbortError 约定（"第一个 signal 使用者"） | Task 4 | ✅ 落地 |
| G-5 取消/超时/卸载同族三条 | Task 4（abort 传播）+ Task 5（换会话/清空时断流） | ✅ 最小闭环：abort 路径打通；**"停止生成"按钮不做**（无 spec 依据，记阶段三候选） |
| L-4 刷新后来源标签消失 | Task 3（后端派生）+ Task 5（前端消费 `row.mode`） | ✅ 闭环（legacy 行统一显 `normal`，属可接受误标，Task 3 Step 记档） |
| G-1 `document_ids` 无界 | Task 3 | ✅ 上限 50 项（String(500) 列：50 个 ≤6 位 id + 逗号 ≤350 字符，安全余量充足） |
| G-3 `res.json()` 空体兜底 | —— | 阶段一实测路径已全部走 `res.text()`+`detailFromText`，无 `res.json()` 残留；终审 grep 证实。**无需动作**，记档即闭 |
| L-5 同名重传 500 | Global Constraints | 绕开（数据纪律），后端唯一键改造不在本计划 |
| L-1/L-2/L-3 移动端折叠与 ≤768 滚动 | —— | **不做**：修法构成对 brief CSS 的偏离且需独立设计决策，留阶段三专项 |
| G-4 颜色 token 收口 / ReferenceList `docLabel` 合并 | —— | 不做（纯重构、无行为收益），记档 |

---

## Task 1: `rag_system` 流式生成器

**Files:**
- Modify: `backend/core/rag_system.py`（文件末尾追加两个方法，类内缩进；既有方法零改动）
- Modify: `backend/tests/test_rag_system.py`（顶部导入行补 `RunnableGenerator`；末尾追加"流式生成器"段）

**Interfaces:**
- Consumes: 既有测试助手 `StubDb`/`StubVectorStore`/`build()`/`parent()`/`chat()`；常量 `LLM_FAILED`/`RETRIEVAL_FAILED`/`EMPTY_RETRIEVAL_ANSWER`；`db_manager.save_chat_history(**kwargs)` 既有签名。
- Produces:
  - `normal_chat_stream(question: str, session_id: str)`：产出若干 `("token", str)`；生成完成后落库一次，落库 kwargs 形状与非流版 `normal_chat` 逐字一致（无 `document_ids`/`used_chunks`）。
  - `chat_with_documents_stream(question: str, document_ids: list[int], session_id: str)`：先产出**恰好一个** `("references", list[Reference])`，随后若干 `("token", str)`；空检索时产出 `("references", [])` + 一个说明文案 token 并落库一次（与非流版终态一致）。
  - 失败语义：检索/压缩失败在第一个事件产出之前 `raise RetrievalError(RETRIEVAL_FAILED)`；LLM 中途失败在已产出若干事件后 `raise LLMError(LLM_FAILED)`；都不落库。消费方提前 `close()`（模拟 HTTP 断流）→ `GeneratorExit` 落在 yield 点，**不落库**。
  - 事件元组第一个字段（`"references"`/`"token"`）就是 Task 2 的 SSE 帧类型名来源。

- [ ] **Step 1: 写失败测试** —— 顶部 langchain 导入行改为：

```python
from langchain_core.runnables import RunnableGenerator, RunnableLambda
```

追加到 `backend/tests/test_rag_system.py` 末尾：

```python
# --- 流式生成器（阶段二 Task 1）---


def stream_llm(tokens, error_at=None):
    """假 LLM 的流式版：RunnableGenerator 让 `prompt | llm` 的 .stream() 逐块产出。
    error_at=i 表示产出第 i 块时抛错（None = 全程顺利）。"""
    def gen(_):
        for i, t in enumerate(tokens):
            if error_at is not None and i == error_at:
                raise RuntimeError("流到一半断了")
            yield SimpleNamespace(content=t)
    return RunnableGenerator(gen)


def collect(gen):
    events = list(gen)
    return events, "".join(d for k, d in events if k == "token")


def test_rag_stream_yields_references_before_tokens_and_saves_once():
    db = StubDb(filenames={7: "操作手册.txt"})
    rag = build(db, StubVectorStore(parent_docs=[parent()]), stream_llm(["基于", "文档"]))
    events, answer = collect(rag.chat_with_documents_stream("父子索引是什么", [7], "s1"))

    assert [k for k, _ in events] == ["references", "token", "token"]
    assert events[0][1] == [Reference(document_id=7, parent_id="p0",
                                      filename="操作手册.txt", snippet="父 块 内容")]
    assert answer == "基于文档"
    assert len(db.saved) == 1
    saved = db.saved[0]
    assert saved["assistant_message"] == "基于文档"
    assert saved["document_ids"] == "7"
    assert saved["used_chunks"].startswith('[{"document_id"')


def test_normal_stream_yields_tokens_only_and_saves_plain_history():
    db = StubDb(history=[chat("旧问", "旧答")])
    events, answer = collect(build(db, StubVectorStore([]), stream_llm(["你", "好"])).normal_chat_stream("你好", "s1"))

    assert [k for k, _ in events] == ["token", "token"]
    assert answer == "你好"
    assert db.saved == [{"session_id": "s1", "user_message": "你好", "assistant_message": "你好"}]


def test_rag_stream_empty_retrieval_is_notice_token_and_persists_once():
    db = StubDb()
    events, answer = collect(build(db, StubVectorStore(parent_docs=[]), stream_llm([])).chat_with_documents_stream("无关问题", [7], "s1"))

    assert events == [("references", []), ("token", "未在选中的文档里找到相关内容，请换个问法或确认文档已上传。")]
    assert len(db.saved) == 1
    assert db.saved[0]["used_chunks"] is None
    assert db.saved[0]["document_ids"] == "7"


def test_rag_stream_retrieval_failure_raises_before_first_event():
    db = StubDb()
    rag = build(db, StubVectorStore(parent_docs=[], retriever_error=RuntimeError("chroma down")), stream_llm(["x"]))
    gen = rag.chat_with_documents_stream("q", [7], "s1")
    with pytest.raises(RetrievalError):
        next(gen)
    assert db.saved == []


def test_rag_stream_llm_failure_midway_raises_llmerror_and_saves_nothing(caplog):
    db = StubDb(filenames={7: "a.txt"})
    rag = build(db, StubVectorStore(parent_docs=[parent()]), stream_llm(["开头", "炸了"], error_at=1))
    with caplog.at_level(logging.ERROR):
        with pytest.raises(LLMError) as exc_info:
            list(rag.chat_with_documents_stream("q", [7], "s1"))
    assert str(exc_info.value) == "大模型调用失败，请稍后重试"
    assert "流到一半断了" in caplog.text
    assert db.saved == []


def test_stream_consumer_disconnect_saves_nothing():
    """消费方只拿前两个事件就 close()：GeneratorExit 落在 yield 点（BaseException，
    不被 except Exception 捕获），落库代码执行不到——spec 6.4"不写半截历史"的机制证明。"""
    db = StubDb(filenames={7: "a.txt"})
    rag = build(db, StubVectorStore(parent_docs=[parent()]), stream_llm(["一段", "二段", "三段"]))
    gen = rag.chat_with_documents_stream("q", [7], "s1")
    next(gen); next(gen)
    gen.close()
    assert db.saved == []


def test_normal_stream_disconnect_saves_nothing():
    db = StubDb()
    gen = build(db, StubVectorStore([]), stream_llm(["x", "y"])).normal_chat_stream("你好", "s1")
    next(gen)
    gen.close()
    assert db.saved == []
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests/test_rag_system.py -q 2>&1 | tail -4
```
预期：新增 7 个 FAIL（`AttributeError: 'RAGSystem' object has no attribute 'chat_with_documents_stream'`），既有 15 个 PASS。

- [ ] **Step 3: 实现** —— 追加到 `backend/core/rag_system.py` 末尾（类内）：

```python
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
```

两处与非流版的**刻意差异**（评审别当漂移）：① 空检索的落库在 `yield` 之前——该路径没有 LLM 等待、不存在"中途断流"，先写后 yield 反而保证"界面出现说明文案时后端必有这一轮"；② `get_chat_history` 挪到 references 之后读——压缩期间不占着历史查询，行为无差。

- [ ] **Step 4: 跑测试确认通过**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests/test_rag_system.py -q 2>&1 | tail -2
```
预期：`17 passed`（既有 10 + 新增 7）。

- [ ] **Step 5: 提交**

```bash
cd "D:/知识库平台-前后端分离"
git add backend/core/rag_system.py backend/tests/test_rag_system.py
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(backend): rag_system 两条链的流式生成器，生成完成才落库"
```

---

## Task 2: `POST /api/chat/stream` SSE 端点

**Files:**
- Modify: `backend/api/chat.py`（新增 `_sse()` 与 `chat_stream` 端点；既有 `chat` 端点原样保留——spec 十一节的回退路径）
- Modify: `backend/tests/fakes.py`（`FakeRAG` 增加两个流式桩方法）
- Modify: `backend/tests/test_api_chat.py`（末尾追加 `/api/chat/stream` 段 + `sse_frames` 助手）

**Interfaces:**
- Consumes: Task 1 的事件元组协议（`("references", list[Reference])` / `("token", str)`）；`ChatRequest`（既有 schema，本 Task 不动）；`get_rag_system`；`RetrievalError`/`LLMError`/`StorageError`。
- Produces: HTTP 端点 `POST /api/chat/stream`，`200` + `content-type: text/event-stream`，帧序严格按 spec 6.4：`meta` 立即先发 → `references`（仅 rag 链）→ `token`×N → `done`；`meta` 之后任何失败 → `error {detail}` 帧后流关闭。Task 4 的前端解析器以此帧序为契约。
- 错误边界（评审重点）：**流开始前**的参数错误仍是普通 HTTP（422，body 校验先于生成器）；**流开始后**的一切领域错误只以 `error` 帧出现，HTTP 状态码保持 200——头已发出，状态码改不了，这是 SSE 的固有语义，不是"丢了 502"。非流版 `/api/chat` 的 502/500 语义原样不动。

- [ ] **Step 1: 升级 `tests/fakes.py` 的 `FakeRAG`**（整类替换为下面版本；构造参数全部向后兼容，旧测试不改也能跑）

```python
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

    def chat_with_documents(self, question, document_ids, session_id):
        if self.error:
            raise self.error
        return self.answer, self.refs

    def normal_chat(self, question, session_id):
        if self.error:
            raise self.error
        return self.answer

    def chat_with_documents_stream(self, question, document_ids, session_id):
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
```

- [ ] **Step 2: 写失败测试** —— 追加到 `backend/tests/test_api_chat.py` 末尾（文件顶部补 `import json`）：

```python
# --- POST /api/chat/stream（阶段二 Task 2）---


def sse_frames(text):
    """把响应体切成 (event, data) 列表；帧以空行分隔，与前端 client.js 的切法同构。"""
    frames = []
    for block in text.strip().split("\n\n"):
        event = data = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event = line[len("event: "):]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        frames.append((event, data))
    return frames


def stream_client(rag):
    return make_client(rag)


def post_stream(client, payload):
    return client.post("/api/chat/stream", json=payload)


def test_stream_rag_frame_sequence_is_meta_references_tokens_done():
    res = post_stream(stream_client(FakeRAG(refs=[REF], tokens=["基于", "文档"])),
                      {"session_id": "s1", "question": "q", "document_ids": [1]})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")
    frames = sse_frames(res.text)
    assert [e for e, _ in frames] == ["meta", "references", "token", "token", "done"]
    assert frames[0][1] == {"mode": "rag", "session_id": "s1"}
    assert frames[1][1] == [{"document_id": 1, "parent_id": "a.txt_parent_0", "filename": "a.txt", "snippet": "片段"}]
    assert frames[2][1] == {"text": "基于"}
    assert frames[-1][1] == {}


def test_stream_normal_frame_sequence_has_no_references_frame():
    res = post_stream(stream_client(FakeRAG(tokens=["你", "好"])),
                      {"session_id": "s1", "question": "q", "document_ids": []})
    assert [e for e, _ in sse_frames(res.text)] == ["meta", "token", "token", "done"]
    assert sse_frames(res.text)[0][1] == {"mode": "normal", "session_id": "s1"}


def test_stream_midway_llm_failure_degrades_to_error_frame_after_200():
    """meta 之后头已发出：LLM 中途失败只能是 error 帧，不能是 502 状态码。"""
    res = post_stream(stream_client(FakeRAG(refs=[REF], tokens=["开头"], error=LLMError("大模型调用失败，请稍后重试"), error_after=1)),
                      {"session_id": "s1", "question": "q", "document_ids": [1]})
    assert res.status_code == 200
    frames = sse_frames(res.text)
    assert [e for e, _ in frames] == ["meta", "references", "token", "error"]
    assert frames[-1][1] == {"detail": "大模型调用失败，请稍后重试"}
    assert "done" not in [e for e, _ in frames]


def test_stream_storage_error_comes_as_error_frame_not_hijacked():
    """StorageError（写历史失败，发生在生成完成后）：中央映射对已开播的流无能为力，
    detail 必须原文进 error 帧——前端据此撤消息，界面与后端历史一致。"""
    res = post_stream(stream_client(FakeRAG(tokens=["x"], error=StorageError("存储坏了"), error_after=1)),
                      {"session_id": "s1", "question": "q", "document_ids": [1]})
    frames = sse_frames(res.text)
    assert frames[-1] == ("error", {"detail": "存储坏了"})


def test_stream_retrieval_failure_is_meta_plus_error_only():
    res = post_stream(stream_client(FakeRAG(error=RetrievalError("检索或上下文压缩失败，请稍后重试"))),
                      {"session_id": "s1", "question": "q", "document_ids": [1]})
    assert res.status_code == 200
    assert [e for e, _ in sse_frames(res.text)] == ["meta", "error"]


def test_stream_unknown_failure_gives_generic_detail_without_internals():
    class Boom(FakeRAG):
        def chat_with_documents_stream(self, q, ids, sid):
            raise RuntimeError("OperationalError(2003): 密码 hunter2 @ 127.0.0.1:3306")

    res = post_stream(Boom(), {"session_id": "s1", "question": "q", "document_ids": [1]})
    detail = sse_frames(res.text)[-1][1]["detail"]
    assert detail == "服务器内部错误"
    assert "hunter2" not in res.text


def test_stream_blank_question_is_plain_http_422_before_any_frame():
    """body 校验发生在 StreamingResponse 之前：422 仍是真状态码 + JSON detail。"""
    res = post_stream(stream_client(FakeRAG()), {"session_id": "s1", "question": "", "document_ids": [1]})
    assert res.status_code == 422
    assert not res.text.startswith("event:")


def test_stream_payload_is_forwarded_in_the_right_positions():
    class SpyStreamRAG(FakeRAG):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.stream_calls = []

        def chat_with_documents_stream(self, question, document_ids, session_id):
            self.stream_calls.append(("rag", question, list(document_ids), session_id))
            return super().chat_with_documents_stream(question, document_ids, session_id)

        def normal_chat_stream(self, question, session_id):
            self.stream_calls.append(("normal", question, session_id))
            return super().normal_chat_stream(question, session_id)

    rag = SpyStreamRAG(tokens=["x"])
    post_stream(rag, {"session_id": "s9", "question": "营收多少", "document_ids": [3, 1]})
    post_stream(rag, {"session_id": "s9", "question": "你好", "document_ids": []})
    assert rag.stream_calls == [("rag", "营收多少", [3, 1], "s9"), ("normal", "你好", "s9")]


def test_stream_frames_are_single_line_json_with_readable_chinese():
    """帧协议钉死（spec 6.4）：一条帧的 data 恰好一行——ensure_ascii=False 保中文逐字，
    JSON 字符串里的换行自带转义，不可能劈开帧。"""
    ref = Reference(document_id=1, parent_id="p", filename="甲.txt", snippet="中文片段")
    res = post_stream(stream_client(FakeRAG(refs=[ref], tokens=["第一段\n第二段"])),
                      {"session_id": "s1", "question": "q", "document_ids": [1]})
    lines = res.text.strip().split("\n")
    assert sum(1 for ln in lines if ln.startswith("data: ")) == 4  # meta/references/token/done
    assert "中文片段" in res.text and "\\u" not in res.text
    assert "第一段\\n第二段" in res.text  # 换行被 JSON 转义在字符串内部

```

- [ ] **Step 3: 跑测试确认失败**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests/test_api_chat.py -q 2>&1 | tail -4
```
预期：新增 9 个 FAIL（`/api/chat/stream` 404），既有 14 个 PASS。

- [ ] **Step 4: 实现** —— `backend/api/chat.py` **整文件替换**为：

```python
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from deps import get_rag_system
from exceptions import LLMError, RetrievalError, StorageError
from schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/chat")
logger = logging.getLogger("kb.api.chat")


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest, rag=Depends(get_rag_system)):
    """document_ids 为空即普通对话，用 mode 回传实际走了哪条链（spec 6.2）。"""
    if payload.document_ids:
        try:
            answer, references = rag.chat_with_documents(
                payload.question, payload.document_ids, payload.session_id
            )
        except (RetrievalError, LLMError) as exc:
            # 失败不写历史：残缺答案进 chat_history 会污染后续上下文（spec 七节）
            logger.warning("RAG 问答失败: %s", exc)
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        mode = "rag"
    else:
        try:
            answer = rag.normal_chat(payload.question, payload.session_id)
        except (RetrievalError, LLMError) as exc:
            logger.warning("普通对话失败: %s", exc)
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        references, mode = [], "normal"

    return ChatResponse(answer=answer, references=references, mode=mode)


def _sse(event: str, data) -> str:
    # json.dumps 的字符串里换行必是 \\n，裸换行不会出现——一帧一个 data 行由此保证
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/stream")
def chat_stream(payload: ChatRequest, rag=Depends(get_rag_system)):
    """SSE 流式版问答（spec 6.4 帧表逐字）。meta 发出后状态码已定格 200：
    之后的失败一律降级为 error 帧，前端读 detail，HTTP 语义让位于流协议。
    /api/chat 原样保留——spec 十一节的回退路径。"""
    if payload.document_ids:
        events = rag.chat_with_documents_stream(
            payload.question, payload.document_ids, payload.session_id
        )
        mode = "rag"
    else:
        events = rag.normal_chat_stream(payload.question, payload.session_id)
        mode = "normal"

    def frames():
        yield _sse("meta", {"mode": mode, "session_id": payload.session_id})
        try:
            for kind, data in events:
                if kind == "references":
                    yield _sse("references", [r.model_dump() for r in data])
                else:
                    yield _sse("token", {"text": data})
            yield _sse("done", {})
        except (RetrievalError, LLMError, StorageError) as exc:
            logger.warning("流式问答失败: %s", exc)
            yield _sse("error", {"detail": str(exc)})
        except Exception:
            logger.exception("流式问答未知异常")
            yield _sse("error", {"detail": "服务器内部错误"})

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
```

设计依据（写进提交信息之外，评审者核对）：① `StorageError` 只在流式路径进 `except` 元组——非流版它继续走中央映射给 500（终审"不被劫持成 502"两条测试保护的就是这条线）；② 客户端断流时 starlette 关闭 `frames()`，`GeneratorExit` 是 `BaseException`，两个 `except` 都不接，继续沿 `events` 生成器传导 → `rag_system` 的落库被跳过（Task 1 的 close 测试在单元层证明过这条链）。

- [ ] **Step 5: 跑测试确认通过**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests/test_api_chat.py tests/test_rag_system.py -q 2>&1 | tail -2
```
预期：`41 passed`（chat 15+9=24，rag 10+7=17）。

- [ ] **Step 6: 活服务冒烟（curl -N，后端 :8000 已在跑，勿杀勿重起；编辑触发 --reload 的 502 抖动就等 3 秒重试）**

```bash
curl -sN -X POST http://127.0.0.1:8000/api/chat/stream -H "Content-Type: application/json" -d '{"session_id":"sse-smoke-1","question":"用两三句话介绍父子索引","document_ids":[]}' | head -c 1200
```
预期：看到 `event: meta` → 若干 `event: token` → `event: done` 的**渐进**输出（curl 不聚合，token 一行行冒出来）；中文逐字非 `\uXXXX`。再跑一条 rag 版（`"document_ids":[69]`）：`meta` 后第一条业务帧必须是 `references`。

- [ ] **Step 7: 提交**

```bash
cd "D:/知识库平台-前后端分离"
git add backend/api/chat.py backend/tests/fakes.py backend/tests/test_api_chat.py
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(backend): POST /api/chat/stream 五种帧，meta 后失败降级 error 帧"
```

---

## Task 3: 历史行的 `mode` 派生 + `document_ids` 上界（闭合 L-4 / G-1）

**Files:**
- Modify: `backend/schemas/chat.py`（`ChatRequest.document_ids` 加 `max_length=50`；`HistoryMessage` 加 `mode` 字段）
- Modify: `backend/api/history.py`（assistant 行派生 `mode`）
- Modify: `backend/tests/test_api_history.py`（`Row` 桩加 `document_ids`；追加 3 条测试）
- Modify: `backend/tests/test_api_chat.py`（追加 1 条 51 项 422 测试，两个端点共用 schema，测一条即覆盖两条）

**Interfaces:**
- Consumes: `ChatHistory` 模型既有的 `document_ids` 列（`core/database.py:82`，`String(500)`，逗号分隔）——**零 DB 迁移**是本 Task 的设计决策。
- Produces:
  - `HistoryMessage` 新字段 `mode: Literal["rag", "normal"] | None = None`；assistant 行按该行 `document_ids` 是否非空派生（非空 → `"rag"`，空/NULL → `"normal"`），user 行恒 `None`。派生规则与 `api/chat.py` 的模式判定（`if payload.document_ids`）逐字同源，不会出现"实时显 rag、刷新显 normal"的分叉。
  - `POST /api/chat` 与 `POST /api/chat/stream` 对 `document_ids` 超过 50 项的请求返回 422（Pydantic v2 的 `Field(max_length=…)` 对 list 限**元素个数**）。
  - Task 5 的前端 `restore` 直接消费 `row.mode`。

- [ ] **Step 1: 写失败测试** —— `backend/tests/test_api_history.py` 的 `Row` 类整类替换：

```python
class Row:
    def __init__(self, used_chunks, document_ids=None):
        self.user_message = "问"
        self.assistant_message = "答"
        self.used_chunks = used_chunks
        self.document_ids = document_ids
        self.created_at = datetime(2026, 9, 30, 10, 0)
```

追加到该文件末尾：

```python
# --- mode 派生（阶段二 Task 3，闭合 L-4）---


def test_assistant_mode_is_rag_when_document_ids_present():
    body = make_client(HistoryDB([Row('[]', document_ids="69,71")])).get("/api/history/s1").json()
    assert body[0]["mode"] is None            # user 行永远不带 mode
    assert body[1]["mode"] == "rag"


def test_assistant_mode_is_normal_when_document_ids_missing():
    body = make_client(HistoryDB([Row(None)])).get("/api/history/s1").json()
    assert body[1]["mode"] == "normal"


def test_legacy_rows_read_as_normal_and_load_cleanly():
    """改造前的老行 document_ids 也是 NULL：统一读成 normal。
    把老 rag 轮误标成"自由对话"是可接受的代价——加 mode 列的迁移没有赚头（终审 L-4 裁定路径）。"""
    body = make_client(HistoryDB([Row('[{"document_id":1,"parent_id":"p","filename":"a.txt","snippet":"片"}]')])) \
        .get("/api/history/0a6e5ed2-legacy").json()
    assert body[1]["mode"] == "normal"
    assert body[1]["references"][0]["filename"] == "a.txt"
```

追加到 `backend/tests/test_api_chat.py` 末尾：

```python
def test_more_than_50_document_ids_is_422():
    """G-1 收口：String(500) 列 + 检索扇出都不该吃无界列表；50 项上限一次钉住两个端点。"""
    client = make_client(FakeRAG())
    res = client.post("/api/chat", json={"session_id": "s1", "question": "q",
                                         "document_ids": list(range(1, 52))})
    assert res.status_code == 422
    res = client.post("/api/chat/stream", json={"session_id": "s1", "question": "q",
                                                "document_ids": list(range(1, 52))})
    assert res.status_code == 422
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests/test_api_history.py tests/test_api_chat.py -q 2>&1 | tail -4
```
预期：新增 4 条 FAIL（`mode` 键不存在 / 51 项没有 422），其余 PASS。

- [ ] **Step 3: 实现**

`backend/schemas/chat.py` 的两处改动（改后的类原文）：

```python
class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1)
    # G-1：上限 50 项——String(500) 的落库列与检索扇出都吃不消无界列表
    document_ids: list[int] = Field(default_factory=list, max_length=50)
```

```python
class HistoryMessage(BaseModel):
    role: str
    content: str
    references: list[Reference] | None = None
    created_at: datetime | None = None
    # 由行的 document_ids 派生（api/history.py），不给 chat_history 加列——L-4 的最小闭法
    mode: Literal["rag", "normal"] | None = None
```

`backend/api/history.py` 的 `get_history` 循环体替换为：

```python
    messages: list[HistoryMessage] = []
    for row in db.get_chat_history(session_id, limit=limit):
        mode = "rag" if row.document_ids else "normal"
        messages.append(HistoryMessage(role="user", content=row.user_message,
                                       references=None, created_at=row.created_at))
        messages.append(HistoryMessage(role="assistant", content=row.assistant_message,
                                       references=_parse_references(row.used_chunks),
                                       created_at=row.created_at, mode=mode))
    return messages
```

- [ ] **Step 4: 跑全量后端测试**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m pytest -q 2>&1 | tail -3
```
预期：全绿（基线 87 + 本计划 Task 1-3 新增 20 条 = **107 passed** 量级；若数字对不上，以"零 failed"为判据并把实数记进报告）。

- [ ] **Step 5: 活服务契约复验（curl，直连 :8000）**

```bash
curl -s -X POST http://127.0.0.1:8000/api/chat -H "Content-Type: application/json" -d '{"session_id":"t3-probe","question":"q","document_ids":[1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51]}'
```
预期：422，`detail` 数组含 `List should have at most 50 items after validation`。再 `curl -s http://127.0.0.1:8000/api/history/<阶段一任一带引用会话id>`：assistant 行出现 `"mode": "rag"` 或 `"normal"`，user 行 `"mode": null`。

- [ ] **Step 6: 提交**

```bash
cd "D:/知识库平台-前后端分离"
git add backend/schemas/chat.py backend/api/history.py backend/tests/test_api_history.py backend/tests/test_api_chat.py
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(backend): 历史 mode 由 document_ids 派生（零迁移），document_ids 限 50 项"
```

---

## Task 4: 前端 `api/` 流式读取层（`postStream` + `sendChatStream`，G-2 收口）

**Files:**
- Modify: `frontend/src/api/client.js`（末尾追加 `postStream` 与 `dispatch`；顶部注释区补 AbortError 约定一段）
- Modify: `frontend/src/api/chat.js`（追加 `sendChatStream`；**`sendChat` 本 Task 保留**——调用方 `useChat` 到 Task 5 才切换，删早了会炸构建）
- Create（临时，不进库）: `%TEMP%\sse-t4\probe.mjs` —— Node 24 直测两函数的探针脚本

**Interfaces:**
- Consumes: Task 2 的帧序契约（`meta`/`references`/`token`/`done`/`error`，单行 JSON data）；既有 `detailFromText`。
- Produces:
  - `postStream(path: string, payload: object, onEvent: (event: string, data: any) => void, { signal } = {}) -> Promise<void>`：流正常读完（收到 done 或 EOF）resolve；`error` 帧**不算 throw**——它照常 `onEvent('error', data)` 派发（Task 5 据此走"撤消息"分支）；主动 abort 原样传播 `AbortError`；流开始前 `!res.ok` 用 `detailFromText` 抛中文可读错误；流中途网络断裂抛 `new Error('流式响应中断，请重试')`。
  - `sendChatStream(payload, onEvent, { signal })`：`postStream('/api/chat/stream', ...)` 的一行包装。
  - **AbortError 约定（G-2 正式收口，client.js 注释落档）**：调用方主动 abort → `err.name === 'AbortError'` 原样上抛，不套"无法连接后端"；Task 5 是第一个消费者。

- [ ] **Step 1: `client.js` 末尾追加**（既有两函数一字不动；`import` 行无新增）

```js
// 阶段二（spec 6.4）：SSE 读取。EventSource 不支持 POST body，只能用 fetch + ReadableStream。
// AbortError 约定（ledger 终审 G-2 收口）：调用方主动 abort 时原样上抛——
// 把它包成"无法连接后端"会让用户去查服务器，而真相是他自己取消了。
export async function postStream(path, payload, onEvent, { signal } = {}) {
  let res
  try {
    res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify(payload),
      signal,
    })
  } catch (err) {
    if (err?.name === 'AbortError') throw err
    throw new Error('无法连接后端，请确认 uvicorn 已在 :8000 运行')
  }
  if (!res.ok) {
    // 流开始前的失败（422/502/500）仍是普通 HTTP：状态码 + detail 照旧
    throw new Error(detailFromText(await res.text(), res.status))
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let cut = buffer.indexOf('\n\n')
      while (cut >= 0) {
        dispatch(buffer.slice(0, cut), onEvent)
        buffer = buffer.slice(cut + 2)
        cut = buffer.indexOf('\n\n')
      }
    }
  } catch (err) {
    if (err?.name === 'AbortError') throw err
    throw new Error('流式响应中断，请重试')
  }
}

// 一条帧 = "event: 名" 行 + "data: 单行JSON" 行；无 event 行按 SSE 默认名 message 派发，
// 后端不会发这种帧，但默认值让 onEvent 的 switch 分支不用处理 undefined。
function dispatch(frame, onEvent) {
  let event = 'message'
  const dataLines = []
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
  }
  if (!dataLines.length) return
  let data
  try {
    data = JSON.parse(dataLines.join('\n'))
  } catch {
    throw new Error('流式帧解析失败，请重试')
  }
  onEvent(event, data)
}
```

- [ ] **Step 2: `chat.js` 整文件替换**

```js
import { postStream, request } from './client.js'

// 入参直接用后端形状，不做 camelCase 映射层。
// sendChat 是阶段一的一次性问答（Task 5 切换调用方后即删）；
// sendChatStream 对应 backend/api/chat.py 的 chat_stream：五种帧经 onEvent 逐帧回调，
// 帧序 meta → references(rag) → token* → done，中途失败以 error 帧到达（HTTP 已是 200）。
export function sendChat(payload) {
  return request('/api/chat', { method: 'POST', body: payload })
}

export function sendChatStream(payload, onEvent, { signal } = {}) {
  return postStream('/api/chat/stream', payload, onEvent, { signal })
}
```

- [ ] **Step 3: Node 探针直测（后端 :8000 活服务，直连不走代理）**

写 `%TEMP%\sse-t4\probe.mjs`（import 用 `file://` URL 指到 `frontend/src/api/`；两文件无 DOM 依赖，Node 24 可直跑）并执行三轮：

```bash
mkdir -p "$TEMP/sse-t4" && cat > "$TEMP/sse-t4/probe.mjs" <<'JS'
const mod = await import('file:///' + process.env.FE + '/src/api/client.js')
const { sendChatStream } = await import('file:///' + process.env.FE + '/src/api/chat.js')
const events = []
await sendChatStream(
  { session_id: 't4-probe-normal', question: '一句话回答：1+1等于几？', document_ids: [] },
  (e, d) => { events.push(e); if (e === 'token') process.stdout.write('.') },
  { signal: AbortSignal.timeout(60000) },
)
console.log('\n帧序列=', events.join(','))
JS
FE="D:/知识库平台-前后端分离/frontend" node "$TEMP/sse-t4/probe.mjs"
```

**预期 ①（normal 全序列）**：点号随 token 逐个冒出（不是攒到最后一起打）；`帧序列= meta,token(,…),done`，**没有** references 帧。

```bash
cat > "$TEMP/sse-t4/probe2.mjs" <<'JS'
const { sendChatStream } = await import('file:///' + process.env.FE + '/src/api/chat.js')
const seen = []
await sendChatStream(
  { session_id: 't4-probe-rag', question: '甲公司的营收是多少？', document_ids: [75] },
  (e) => { seen.push(e); if (e === 'references') console.log('references 到达，其后首帧将是 token') },
  { signal: AbortSignal.timeout(120000) },
)
console.log('帧序列=', seen.join(','))
JS
FE="D:/知识库平台-前后端分离/frontend" node "$TEMP/sse-t4/probe2.mjs"
```

**预期 ②（rag 帧序）**：`帧序列= meta,references,token,…,done`，且 `references` 的位置固定是第 2 帧（引用先于答案，spec 6.4）。

```bash
cat > "$TEMP/sse-t4/probe3.mjs" <<'JS'
const { sendChatStream } = await import('file:///' + process.env.FE + '/src/api/chat.js')
const ac = new AbortController()
let n = 0
const p = sendChatStream(
  { session_id: 't4-probe-abort', question: '请写一篇五百字短文', document_ids: [] },
  () => { n += 1; if (n === 3) ac.abort() },
  { signal: ac.signal },
)
try { await p; console.log('没有抛——不对') }
catch (err) { console.log('err.name=', err.name, '| 已收到帧数=', n) }
JS
FE="D:/知识库平台-前后端分离/frontend" node "$TEMP/sse-t4/probe3.mjs"
```

**预期 ③（G-2 约定）**：`err.name= AbortError | 已收到帧数= 3`——abort 原样传播，没有被包成"无法连接后端"。

- [ ] **Step 4: 静态把关复跑**

```bash
cd "D:/知识库平台-前后端分离/frontend" && grep -rn "v-html\|innerHTML" src/ ; echo "退出码 $?" && grep -rn "127.0.0.1:8000\|localhost:8000" src/ ; echo "退出码 $?"
```
预期两条都打印 `退出码 1`（`client.js` 里那句"uvicorn 已在 :8000 运行"是文案不是地址，含 `:8000` 但匹配不上这两条模式）。

- [ ] **Step 5: 提交**

```bash
cd "D:/知识库平台-前后端分离"
git add frontend/src/api/client.js frontend/src/api/chat.js
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(frontend): client.postStream 与 sendChatStream，AbortError 约定落地"
```

---

## Task 5: `useChat` 改流式事件驱动，删除 typewriter

**Files:**
- Modify: `frontend/src/composables/useChat.js`（整文件替换）
- Modify: `frontend/src/api/chat.js`（删 `sendChat`，只留 `sendChatStream`——与调用方切换同提交，不留死代码）
- Modify: `frontend/src/components/MessageList.vue`（仅第 28-29 行注释改述，逻辑零改动）
- Delete: `frontend/src/utils/typewriter.js`（`git rm`——spec 十一节第 8 步"SSE 落地当天整文件删除 typewriter.js"）

**Interfaces:**
- Consumes: Task 4 的 `sendChatStream(payload, onEvent, { signal })`；帧形状 `meta {mode, session_id}` / `references [Reference×N]`（data 就是数组本身）/ `token {text}` / `error {detail}` / `done {}`；Task 3 的历史行 `mode` 字段（assistant 行为 `"rag"|"normal"`，user 行为 null）。
- Produces: `useChat()` 返回 `{ messages, pending, error, restore, send, clear, abortStream }`。**`finishTyping` 消失**——全仓检索确认只有 `useChat.js` 自身用过（App.vue 的解构不含它），无其他文件需要改。
- 契约改写（评审重点）：`pending` 从阶段一的"只覆盖网络请求"改为**覆盖整个流**（done/error/abort 关流才释放，输入框禁用更久是预期行为）；没有"停止生成"按钮（阶段三候选），用户能触发的 abort 只有两条路径——"换一个 session_id"和"清空对话"。

- [ ] **Step 1: `chat.js` 整文件替换**

```js
import { postStream } from './client.js'

// 入参直接用后端形状，不做 camelCase 映射层。
// sendChatStream 对应 backend/api/chat.py 的 chat_stream：五种帧经 onEvent 逐帧回调，
// 帧协议见 spec 6.4（meta 立即先发 → references 仅 rag 链且先于一切 token → token×N → done；
// meta 后任何失败 → error {detail} 后流关闭）。
// 非流版 sendChat 已在阶段二 Task 5 删除：回退路径由后端 /api/chat 保留端点本身承担，
// 前端不再引用它（spec 十一节第 7→6 步回退只需把 useChat 换回一次 POST 拿整包）。
export function sendChatStream(payload, onEvent, { signal } = {}) {
  return postStream('/api/chat/stream', payload, onEvent, { signal })
}
```

- [ ] **Step 2: `useChat.js` 整文件替换**

```js
import { ref } from 'vue'

import { sendChatStream } from '../api/chat.js'
import { clearHistory, getHistory } from '../api/history.js'

let seq = 0

// v-for 的 key 只求稳定唯一，自增比 randomUUID 省事，刷新后按历史重建也不会撞
function nextKey() {
  seq += 1
  return `m${seq}`
}

export function useChat() {
  const messages = ref([])
  const pending = ref(false)
  const error = ref('')
  let controller = null

  // 主动打断（换会话 / 清空）：后端收到断连会掐掉生成器、不写半截历史，
  // 所以本地这两条也必须跟着撤——"前端只留后端有的"原则不变。
  function abortStream() {
    if (controller) {
      controller.abort()
      controller = null
    }
  }

  // 按 key 撤而不是按下标撤：竞态下 restore/clear 可能已整体替换 messages.value，
  // 此时按下标 splice(len-2, 2) 会误删刚恢复回来的历史末两条；找不到 key 即无操作。
  function removeTurn(bubble) {
    const i = messages.value.findIndex((m) => m.key === bubble.key)
    if (i !== -1) messages.value.splice(Math.max(i - 1, 0), 2)
  }

  async function restore(sessionId) {
    abortStream()
    try {
      // 后端已把一行 DB 展开成 user + assistant 两条，形状与实时发送一致（spec 6.2 第 3 条）。
      // mode 由后端从 chat_history.document_ids 派生（Task 3），user 行为 null——MessageBubble 的 v-if 不渲染标签
      const rows = await getHistory(sessionId)
      messages.value = rows.map((row) => ({
        key: nextKey(),
        role: row.role,
        content: row.content,
        references: row.references ?? [],
        mode: row.mode ?? null,
        streaming: false,
      }))
      error.value = ''
      return true
    } catch (err) {
      error.value = err.message
      return false
    }
  }

  async function send({ session_id, question, document_ids }) {
    if (pending.value || !question.trim()) return false
    error.value = ''
    // 阶段二 pending 覆盖整条流：没有停止生成按钮时，中途放手会让界面挂着一条
    // 后端没有的半截答案，禁用输入到关流是唯一能守住"界面==历史"的做法。
    pending.value = true

    messages.value.push({ key: nextKey(), role: 'user', content: question, references: [], mode: null, streaming: false })
    messages.value.push({ key: nextKey(), role: 'assistant', content: '', references: [], mode: null, streaming: true })
    // 必须 push 完再按下标取回：拿到的是响应式代理，改它的字段才推动视图；
    // 改 push 之前那个原始对象，数据变了但界面不动。
    const bubble = messages.value[messages.value.length - 1]

    controller = new AbortController()
    const signal = controller.signal
    let fail = ''
    try {
      await sendChatStream(
        { session_id, question, document_ids },
        (event, data) => {
          switch (event) {
            case 'meta':
              // 模式标签先于答案上屏（spec 6.4：meta 立即先发）
              bubble.mode = data.mode
              break
            case 'references':
              // references 帧恒在第一个 token 之前，后端数组直接上屏
              bubble.references = data
              break
            case 'token':
              bubble.content += data.text
              break
            case 'error':
              // error 帧后流正常关闭，postStream 不 throw；失败在这里记账，走循环后分支
              fail = data.detail
              break
            case 'done':
              break
          }
        },
        { signal },
      )
      if (fail) {
        // meta 后失败：后端没写历史（异常在 save 前抛出），本地两条一起撤 + 横幅
        removeTurn(bubble)
        error.value = fail
        return false
      }
      return true
    } catch (err) {
      if (err?.name === 'AbortError') {
        // 自己按的打断：不弹横幅（真相是用户自己取消了，弹错反而让人去查服务器），
        // 但半截那两条必须撤——后端断流即丢，从没写历史。
        removeTurn(bubble)
        return false
      }
      removeTurn(bubble)
      error.value = err.message
      return false
    } finally {
      bubble.streaming = false
      if (controller?.signal === signal) controller = null
      pending.value = false
    }
  }

  async function clear(sessionId) {
    abortStream()
    try {
      // 先确认后端删掉了再动本地：本地清空而后端没删，刷新会把历史原样冲回来
      await clearHistory(sessionId)
      messages.value = []
      error.value = ''
      return true
    } catch (err) {
      error.value = err.message
      return false
    }
  }

  return { messages, pending, error, restore, send, clear, abortStream }
}
```

**实现者注意（三条评审锚点）：**
1. `references` 帧的 `data` 是数组本身（Task 2 编码时已 `[r.model_dump() for r in data]` 展平），不是 `{references: [...]}`——写成 `data.references` 是漂移。
2. `error` 分支走"循环后 `if (fail)`"而不是 throw：Task 4 的 `postStream` 契约明写 error 帧照常派发不 throw。
3. `finally` 里 `bubble.streaming = false` 兜底所有出口（done/error/abort/网络断），光标不会永远闪。撤消息后改孤儿代理无副作用。

- [ ] **Step 3: `MessageList.vue` 注释改述（唯一改动，第 28-29 行）**

```js
// 阶段二流式：token 逐帧追加会让最后一条 content 持续变长，所以 watch 的是"长度"而不只是条数，
// 否则气泡会长出视口外而页面不跟到底部。
```

- [ ] **Step 4: 删除 typewriter 并静态把关**

```bash
cd "D:/知识库平台-前后端分离"
git rm frontend/src/utils/typewriter.js
grep -rn "typewriter\|startTypewriter\|fullText\|finishTyping" frontend/src/ ; echo "残留检查退出码 $?"
grep -rn "sendChat\b" frontend/src/ ; echo "sendChat 检查退出码 $?"
```
预期两条都打印 `退出码 1`（零残留；`sendChatStream` 不会被 `\b` 边界误匹配）。

- [ ] **Step 5: 浏览器全链路验证（vite :5173，复用现存 uvicorn :8000——严禁再起第二个后端）**

用浏览器工具打开 `http://localhost:5173`（**headless 视口显式设 ≥769，并回读 innerWidth 确认**），按序验证并逐项记录实测值：

1. **normal 链帧序**：不勾选文档，发送"你好"。预期：点下发送后**答案还在逐字长时，💬 自由对话标签已出现**（meta 先发的直接证据）；光标 ▌ 全程恰好 1 个；流期间输入框禁用（pending 覆盖整条流）。
2. **rag 链引用先于答案**：勾选一个文档（用基线 #78 wide.txt 之外已存在的文档，**不要同名重传**），发送与之相关的问题。预期：📚 知识库检索标签 + 引用片段列表**先于任何答案文字**出现。
3. **刷新回归**：F5 后模式标签、内容、引用与流式上屏一致（restore 消费 `row.mode` 的证据）。
4. **断流撤消息**：发送一个长问题，流期间点"换一个 session_id"。预期：无错误横幅；半截那两条消失；新会话历史正常加载；再切回旧 session，`GET /api/history/<旧id>`（页面刷新即可）**没有**那条半截 assistant——界面与后端历史一致（spec 6.4"断流不写半截历史"的前端侧闭环）。
5. **清空对话**：确认后消息清零。
6. **Console 洁净**：全流程零 error/warning（Vue devtools 提示除外）。

任何一项不过，修完再提交；**不许**带着红项收口。

- [ ] **Step 6: 提交**

```bash
cd "D:/知识库平台-前后端分离"
git add frontend/src/composables/useChat.js frontend/src/api/chat.js frontend/src/components/MessageList.vue
git -c user.name="31439" -c user.email="31439@local" commit -m "feat(frontend): useChat 改流式事件驱动，删除 typewriter 本地逐字"
```
（`git rm` 的删除已随本提交入库；若 `git add` 对某些路径报 exit 1"ignored paths"警告，文件其实已 staged，分开跑 commit 即可。）

---

## Task 6: 阶段二收口——全链路终验 + 构建冒烟 + 台账

**Files:**
- Modify: `.superpowers/sdd/2026-10-02-kb-platform-sse/progress.md`（收口记录；若 SDD 工作区在别处，以台账实际路径为准）

**Interfaces:**
- Consumes: Task 1-5 全部产出。
- Produces: 阶段二"可交付"判定——本 Task 只验证与记账，**不做分支集成**（集成走 finishing-a-development-branch 的三选一菜单，归控制器/用户）。

- [ ] **Step 1: 后端全量测试**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m pytest -q
```
预期全绿（含 Task 1/2/3 新增用例；live 用例打的是 :8000 现存实例，复用 b4ah2ndi6 那个进程，**勿杀勿重起**；若刚改过后端文件触发了 --reload 瞬时 502，等几秒重跑）。

- [ ] **Step 2: 前端回退路径 + 边界手测（curl，打 :8000）**

```bash
curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"t6-check","question":"你好","document_ids":[]}'
```
预期 `200`——`POST /api/chat` 非流版原样可用（spec 十一节回退路径没被阶段二弄坏）。

```bash
python - <<'PY'
import json, urllib.request
ids = list(range(1, 52))  # 51 个 > max_length=50
req = urllib.request.Request('http://127.0.0.1:8000/api/chat/stream',
    data=json.dumps({'session_id': 't6-check', 'question': 'q', 'document_ids': ids}).encode(),
    headers={'Content-Type': 'application/json'})
try:
    urllib.request.urlopen(req)
    print('没拦——不对')
except urllib.error.HTTPError as e:
    print(e.code, e.headers.get('content-type', '').split(';')[0])
PY
```
预期 `422 application/json`（G-1 上界；**流开始前**的失败仍是普通 HTTP，一帧 SSE 都不发）。

- [ ] **Step 3: 静态把关总表**

```bash
cd "D:/知识库平台-前后端分离/frontend"
grep -rn "v-html\|innerHTML" src/ ; echo "退出码 $?"
grep -rn "typewriter\|startTypewriter\|fullText\|finishTyping\|sendChat\b" src/ ; echo "退出码 $?"
grep -rn "127.0.0.1:8000\|localhost:8000" src/ ; echo "退出码 $?"
grep -rEoh "#[0-9a-fA-F]{3,8}\b" src/styles/*.css src/components/*.vue src/App.vue | sort | uniq | wc -l
```
预期前三条 `退出码 1`；第四条颜色字面量去重计数 **≤11**（T7 基线 11 处，阶段二 CSS 零改动，不该增长）。

- [ ] **Step 4: 构建冒烟（dist 已 gitignore，纯验证不入库）**

```bash
cd "D:/知识库平台-前后端分离/frontend" && rm -rf dist && npm run build
```
预期 exit 0。

- [ ] **Step 5: 台账收口**

在 SDD 台账 `progress.md` 记：各 Task 提交号与评审结论、Step 1-4 实测输出原文（数字要用实测值，不许抄预期）、断流不落半截的验证会话 id、legacy 会话 `0a6e5ed2` 刷新后显示"💬 自由对话"的 L-4 记档。阶段三候选入台账：停止生成按钮（abort 通道已就绪，只缺 UI）、L-1/L-2/L-3 移动端适配、G-4 颜色 tokens、M-F2 docLabel 合并、M-F3 handleSend 忽略 emit 载荷。

```bash
cd "D:/知识库平台-前后端分离"
git add .superpowers/sdd/2026-10-02-kb-platform-sse/progress.md
git -c user.name="31439" -c user.email="31439@local" commit -m "docs(ledger): 阶段二 SSE 流式收口台账"
```
若台账路径不同以实际为准；**无文件变更则跳过提交**（禁空提交）。

---

## 阶段三候选（本计划不做，记账备查）

- **停止生成按钮**：`postStream` 的 `signal` 与 `useChat.abortStream()` 已就绪，缺的只是 ChatInput 上的一个按钮和 pending 期的可点样式。
- **移动端适配**：L-1/L-2/L-3（阶段一遗留，见 `2026-09-30-kb-platform-frontend` 台账）。
- **颜色 tokens 化**：G-4（基线 11 处字面量的收敛）。
- **小杂项**：M-F2 ReferenceList docLabel 内联重复、M-F3 handleSend 忽略 emit 载荷。

---
