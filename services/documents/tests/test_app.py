from fastapi.testclient import TestClient


def test_live_health_endpoint_returns_ok() -> None:
    from tests.test_documents_api import create_test_app

    with TestClient(create_test_app()) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
