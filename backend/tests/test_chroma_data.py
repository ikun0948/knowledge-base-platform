import shutil
from pathlib import Path

import chromadb
import pytest
from config.config import BASE_DIR, Config

# 搬家前在旧库实测的计数，Task 3 的 /api/health 共用这两个常量
PARENT_COUNT = 2
CHILD_COUNT = 7

# 计数看不出"掉一行又补一行"，身份基线才证明活下来的是这几条（迁移后的库实测）
PARENT_IDS = [
    "a677b2f1-63b5-4836-aae5-c86355093902",
    "e3985550-9937-42d9-a13a-acb7c75ca1ed",
]
CHILD_IDS = [
    "42d647ea-3be1-4d21-a5c5-ea0d760477af",
    "584148b1-9a83-4336-bdcc-a491f2ea08c9",
    "770d63d5-685b-4256-9916-1c19c1ba6cb3",
    "7ab5915f-b357-4544-8f43-09d7366e1aaf",
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
