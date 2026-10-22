from fastapi.testclient import TestClient

from ds_project import __version__
from ds_project.api.main import app


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}
