from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_metrics_are_exposed():
    client.get("/")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "app_http_requests_total" in response.text
    assert "app_process_memory_bytes" in response.text


def test_error_endpoint():
    response = client.get("/error")
    assert response.status_code == 500
