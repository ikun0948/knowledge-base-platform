## Task 2: Chroma 数据搬家 + 计数基线（spec 坑 2、验收判据 1）

**Files:**
- Create: `backend/data/chroma_db/`（复制）、`backend/tests/test_chroma_data.py`

**Interfaces:**
- Consumes: `Config.CHROMA_PERSIST_DIR`
- Produces: 断言基线 `PARENT_COUNT = 2`、`CHILD_COUNT = 7`，Task 3 的 `/api/health` 用同一组常量

- [ ] **Step 1: 复制数据目录**

```bash
cd "D:/知识库平台-前后端分离"
cp -r "D:/AI-python/core/chroma_db" backend/data/chroma_db
ls backend/data/chroma_db
```

原目录 `D:/AI-python/core/chroma_db` **保留不动**（回退只需把 `.env` 那行改回去）。

- [ ] **Step 2: 写搬家校验测试**

`backend/tests/test_chroma_data.py`：

```python
import chromadb
from config.config import Config

# 搬家前在旧目录实测的计数，作为"数据没丢"的判据（spec 第十节判据 1）
PARENT_COUNT = 2
CHILD_COUNT = 7


def test_collection_counts_survived_the_move():
    client = chromadb.PersistentClient(path=Config.CHROMA_PERSIST_DIR)
    counts = {c.name: c.count() for c in client.list_collections()}
    assert counts == {"parent_document": PARENT_COUNT, "child_document": CHILD_COUNT}
```

- [ ] **Step 3: 运行**

```bash
cd "D:/知识库平台-前后端分离/backend" && python -m pytest tests/test_chroma_data.py -v
```
预期：PASS。若 FAIL 且计数为 0，先确认 `cp -r` 是否把整棵目录（含 `chroma.sqlite3`）复制完整，**不要**改测试里的常量去"适配"结果。

- [ ] **Step 4: 提交**

```bash
cd "D:/知识库平台-前后端分离" && git add backend/tests/test_chroma_data.py
git -c user.name="31439" -c user.email="31439@local" commit -m "test(backend): Chroma 搬家后集合计数与旧库一致"
```

（`backend/data/` 已在 `.gitignore` 里，不入库。）

---

