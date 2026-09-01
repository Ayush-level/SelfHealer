"""Tests for health check endpoint."""

import pytest
from proxy.app import create_app


@pytest.fixture
def client():
    app = create_app({"TESTING": True, "STORAGE_MODE": "prometheus"})
    with app.test_client() as client:
        yield client


def test_health_endpoint(client):
    """Test GET /health returns 200 OK and healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["storage_mode"] == "prometheus"
