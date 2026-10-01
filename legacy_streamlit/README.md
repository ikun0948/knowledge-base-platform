# legacy_streamlit

本目录**不放任何代码**，它只是一块指路碑：改造前的 Streamlit 单体没有被拷贝进本仓，
活体归档在原项目目录 `D:/AI-python/知识库平台/`（2026-10-01 迁移裁定：原目录即归档，**只读、不改**）。

不在这里做物理拷贝的理由：spec 7.2 给 legacy 副本定了"至多两份"的上限。迁移裁定后这条规则的读法是——
原始＝`D:/AI-python/知识库平台`，副本＝本仓的 `backend/`，两份已经在。本仓根从未有过
`app.py`/`config/`/`core/`/`.streamlit/`，再抄一份进 `legacy_streamlit/` 就成了第三份真相，两处会随时间漂移。

## 归档里实际有什么（`ls` 实测，非推测）

| 路径 | 实测内容 |
|---|---|
| `app.py` | 原入口，Streamlit 单体，526 行（`render_message_html` 在 288 行，坑 6 现场在 322 行） |
| `streamlit页面.py` | 更早的 UI 原型，409 行，已废弃（坑 16 提到的就是它） |
| `config/config.py` | 旧配置层，830 字节，无参 `load_dotenv()` |
| `core/` | `database.py`、`document_processor.py`、`vector_store.py`、`rag_system.py`（`get_parent_documents_by_metadata` 在 `vector_store.py:75`） |
| `.streamlit/config.toml` | 两行主题配置（`primaryColor = "#667eea"`） |
| `知识库平台开发文档.md`、`requirements.txt`、`docs/` | 同期的开发文档、依赖记录、spec 与计划副本 |
| `backend/` | 迁移前的后端开发残留副本，同样只读；**当前活跃实现是本仓根下的 `backend/`** |

归档目录内**没有** `.env`（真实配置在上一级的 `D:/AI-python/.env`），也**没有** `chroma_db` 目录。

## 用途

- **手测行为比对**：新接口表现存疑时，去归档跑一遍老界面看原本行为，再和本地 `backend/` 对答案。
- **读旧实现**：Streamlit 侧的渲染/缓存/历史写法只存在于归档，本仓不留副本。

任何功能修改只进 `backend/`；本目录与归档都不接受改动。

## 跑旧 app 之前要知道的（配置来源与向量库）

- 旧 `config/config.py` 用的是无参 `load_dotenv()`，python-dotenv 从调用文件所在目录逐级向上找，
  实际命中的是 `D:/AI-python/.env`——跨项目共用文件（spec 7.1 已规定本项目不再读它，`backend/.env` 才是后端的配置来源）。
- 该 `.env` 里 `CHROMA_PERSIST_DIR=../core/chroma_db`，**相对 cwd**（这正是开发文档第七节坑 2）：
  - 按文档命令 `cd D:/AI-python/知识库平台 && streamlit run app.py` 启动 → 解析成 `D:/AI-python/core/chroma_db`，
    实测**该目录并不存在**，而 `chromadb.PersistentClient` 对不存在的路径会静默新建空库，于是旧 app 表现为"向量库空了"。
  - 旧库的真实位置实测在 `D:/AI-python/langchain框架/core/chroma_db`，只有 cwd 是 `langchain框架` 时才命中。
  - 本仓 `backend/.env` 已把它写成绝对路径 `D:/知识库平台-前后端分离/backend/data/chroma_db`，数据也复制过去了。
- 结论：旧 app 与 `backend/` 各用各的向量目录，**同时跑不会互写**——但那是两个彼此独立的库，
  旧 app 里的检索结果不代表 `backend/` 的数据；想让旧 app 复现"有向量"的行为，得从 `D:/AI-python/langchain框架` 启动。
- 另外别忽略：两边连的是**同一个 MySQL**（实测两份 `.env` 都是 `localhost:3306` / `root` / `mydb`），
  关系库那一侧是同一份数据。并发手测时上传/清空会互相影响，且 `D:/AI-python/.env` 是共用文件，不要为了测试去改它。

## 去留

阶段一验收通过后，由用户决定 `D:/AI-python/知识库平台` 这份归档的去留（spec 第十一节第 7 步后半）。
若终审希望本仓内也留一份物理冻结副本，届时单独补一次 `cp` 即可——不做也不损失任何 spec 判据。
