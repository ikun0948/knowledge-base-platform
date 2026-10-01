from fakes import FakeConfig, FakeDatabase, FakeVectorStore
from deps import get_config, get_db, get_vector_store
from main import create_app
from fastapi.testclient import TestClient


def make_client():
    app = create_app()
    app.dependency_overrides[get_config] = lambda: FakeConfig()
    app.dependency_overrides[get_db] = lambda: FakeDatabase()
    app.dependency_overrides[get_vector_store] = lambda: FakeVectorStore()
    # 不进 with：TestClient 只在上下文管理器里才跑 lifespan，这里故意让它不跑，
    # 否则每个接口测试都会连真 MySQL 并加载 0.6B embedding 模型。
    return TestClient(app)


def test_health_reports_counts_from_both_stores():
    client = make_client()
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["chroma_dir"] == "fake://chroma"
    assert body["document_count"] == 1
    assert body["vector_counts"] == {"parent": 2, "child": 7}
