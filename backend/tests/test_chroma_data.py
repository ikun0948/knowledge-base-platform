import shutil
from pathlib import Path

import chromadb
import pytest
from config.config import BASE_DIR, Config

# 计数为 2026-10-02 阶段二收口实测，后续再上传文档需重钉（/api/health 实测 vector_counts：parent 11 / child 22）
PARENT_COUNT = 11
CHILD_COUNT = 22

# 计数看不出"掉一行又补一行"，身份基线才证明活下来的是这几条（迁移后的库实测）
PARENT_IDS = [
    "25887e7e-5037-4122-af35-05e2d6654a85",
    "38405ea7-c51a-46fc-b183-75318d7c9df5",
    "84c49843-2275-446e-9b5e-f2e8ba206dde",
    "88630281-e5bb-4ca4-a3db-a74ad11213b3",
    "a2f65fd9-9084-40a1-a1fe-924123e5572d",
    "a677b2f1-63b5-4836-aae5-c86355093902",
    "ab6f0cd8-cc3c-4152-8e45-fb5a226974cb",
    "b4202f9e-0d57-4732-8720-03682f62d98f",
    "d2b9aa72-3872-4622-b7a2-c6bf079d9140",
    "e3985550-9937-42d9-a13a-acb7c75ca1ed",
    "f71513ce-f195-4207-91c5-93582e8f313e",
]
CHILD_IDS = [
    "104f3cf3-3afb-4934-a550-2a09dfd2dd41",
    "254f10c6-e3f3-4038-a302-7c86d29343e9",
    "25f4772e-4222-41b1-9ea8-5387edf22b0f",
    "25f47999-686d-41f4-be92-57cd3ff84b2f",
    "427ffbba-7eaa-4779-96b8-e9174dd08cfc",
    "4298d3b2-09b5-43cf-94c6-75e2b45fcecd",
    "42d647ea-3be1-4d21-a5c5-ea0d760477af",
    "5211c213-c4f8-4394-bdda-a55fb726a794",
    "53d4991a-82f1-4e39-99d7-9ae241a7f1cc",
    "584148b1-9a83-4336-bdcc-a491f2ea08c9",
    "6ec23d05-567b-4e05-92b2-8cb2e5b8d1fc",
    "70238de6-d1e2-4114-8c36-04b9552a8d22",
    "768c84d1-312e-4828-9a13-ccc275744a1a",
    "770d63d5-685b-4256-9916-1c19c1ba6cb3",
    "7ab5915f-b357-4544-8f43-09d7366e1aaf",
    "9443a1c3-f431-40ed-9706-fc6dd1d0cc03",
    "9d47d4af-40dd-42ed-ba3f-6d79fa1f88a5",
    "b0735ff9-4bfb-463b-aca8-c8fe18a97b69",
    "b2e1cbda-1235-486e-94c5-bc76a077f393",
    "b3b50c5e-eba2-4ea5-a44a-e52d21d60037",
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
