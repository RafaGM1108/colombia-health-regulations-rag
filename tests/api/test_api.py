from fastapi.testclient import TestClient

from colombia_health_rag import __version__
from colombia_health_rag.api.main import app


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}
