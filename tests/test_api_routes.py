import pytest
from fastapi.testclient import TestClient

from loom.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_history_returns_list(client):
    response = client.get("/history")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_history_detail_404_for_unknown_id(client):
    response = client.get("/history/does-not-exist")
    assert response.status_code == 404


def test_report_404_for_unknown_id(client):
    response = client.get("/report/does-not-exist")
    assert response.status_code == 404


def test_summary_range_404_when_nothing_in_range(client):
    response = client.get("/summary/range", params={"start": "1999-01-01", "end": "1999-01-02"})
    assert response.status_code == 404


def test_analyze_rejects_missing_feedback_column(client):
    csv_bytes = b"id,other\n1,hello\n"
    response = client.post(
        "/analyze", files={"file": ("bad.csv", csv_bytes, "text/csv")}
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == 4001


def test_analyze_rejects_oversized_upload(client):
    from loom.api.deps import container

    original_max = container.analysis_controller.max_upload_size
    container.analysis_controller.max_upload_size = 10
    try:
        response = client.post(
            "/analyze", files={"file": ("small.csv", b"feedback\nhello world\n", "text/csv")}
        )
        assert response.status_code == 413
    finally:
        container.analysis_controller.max_upload_size = original_max


def test_response_headers_include_timing(client):
    response = client.get("/health")
    assert "X-Process-Time-Ms" in response.headers
