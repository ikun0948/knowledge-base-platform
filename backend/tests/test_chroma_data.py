import shutil
from pathlib import Path

import chromadb
import pytest
from config.config import BASE_DIR, Config

# 计数为 2026-10-07 重钉：旧基线（parent 11 / child 22）作废——用户在界面上把 9 篇里 8 篇的
# 块删到 chunk_count 归零，只剩 deepseek简介.docx 那一份活着；随后用真 HTTP 通路（POST
# /api/documents，同一份 uvicorn 进程）补传 baseline-a/b/c.txt 三篇小文档重建基线。
# 复测两处一致：Chroma 目录副本的集合计数、MySQL 的 parent_chunks/child_chunks 都是 4 / 10。
PARENT_COUNT = 4
CHILD_COUNT = 10

# 计数看不出"掉一行又补一行"，身份基线才证明活下来的是这几条。
# 下面两个列表按 uuid 排序，归属读不出来，这里给出 vector_id 直查的对应关系：
#   deepseek简介.docx  父 e3985550；子 42d647ea / 7ab5915f / b2e1cbda / c276a890 / ee6ccabc
#   baseline-a.txt     父 9a7d9885；子 05d825a4
#   baseline-b.txt     父 8fcccd10；子 1b3360dd / 5443f45c / 9a17c1f4
#   baseline-c.txt     父 17ed6521；子 772ed645
# deepseek简介.docx 那一份穿过那轮删除，一条没变。
PARENT_IDS = [
    "17ed6521-8b52-40bf-aae5-5d508b027b41",
    "8fcccd10-dcca-4136-b09d-ed22751a5563",
    "9a7d9885-fa18-44ce-abd6-067d93a013b0",
    "e3985550-9937-42d9-a13a-acb7c75ca1ed",
]
CHILD_IDS = [
    "05d825a4-420a-42f6-8ac3-00a84361ceb0",
    "1b3360dd-54c7-4e4f-bf08-7c64340ffd82",
    "42d647ea-3be1-4d21-a5c5-ea0d760477af",
    "5443f45c-6305-400c-afcc-323b8224fab4",
    "772ed645-d49f-4421-ae74-ac491a744b97",
    "7ab5915f-b357-4544-8f43-09d7366e1aaf",
    "9a17c1f4-aacc-4c5a-9846-543383632100",
    "b2e1cbda-1235-486e-94c5-bc76a077f393",
    "c276a890-fb5a-4bbd-8323-611e9ac238d3",
    "ee6ccabc-d25a-49af-b843-f1ced132a151",
]


@pytest.mark.migration
def test_collection_identity_survived_the_move(tmp_path):
    # 旧库同样是绝对路径且计数一致，不钉住路径这条就能整体验证别的东西
    assert Path(Config.CHROMA_PERSIST_DIR).resolve() == BASE_DIR / "data" / "chroma_db"
    # PersistentClient 对不存在的路径会静默新建空库，先确认打开的是搬过来的那一份
    sqlite = Path(Config.CHROMA_PERSIST_DIR) / "chroma.sqlite3"
    assert sqlite.is_file(), f"{sqlite} 不存在：向量库未搬家，先把旧库复制进 backend/data/chroma_db"
    # 打开持久化库本身就会回写 chroma.sqlite3，所以校验跑在 tmp_path 副本上，不碰迁移后的数据
    store = tmp_path / "chroma_db"
    shutil.copytree(Config.CHROMA_PERSIST_DIR, store)
    collections = {c.name: c for c in chromadb.PersistentClient(path=str(store)).list_collections()}
    assert {n: c.count() for n, c in collections.items()} == {
        "parent_document": PARENT_COUNT,
        "child_document": CHILD_COUNT,
    }
    assert sorted(collections["parent_document"].get()["ids"]) == sorted(PARENT_IDS)
    assert sorted(collections["child_document"].get()["ids"]) == sorted(CHILD_IDS)
