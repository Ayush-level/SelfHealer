"""Tests for GET /api/health and GET /api/telemetry/summary (Task 7.5).

Health checks and telemetry queries hit external services; we mock the
outbound HTTP calls so tests run without a live stack.
"""
import pytest
from unittest.mock import patch, MagicMock
from proxy.app import create_app


@pytest.fixture
def client():
    app = create_app({"TESTING": True, "STORAGE_MODE": "prometheus",
                      "CLICKHOUSE_URL": "http://clickhouse:8123",
                      "PROMETHEUS_URL": "http://prometheus:9090"})
    # Set a minimal wizard config
    app.wizard_config = {
        "enable_grafana": True, "grafana_port": 3000,
        "enable_prometheus_ui": True,
        "enable_signoz": False,
    }
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# /api/health
# ---------------------------------------------------------------------------

def _mock_ok():
    m = MagicMock()
    m.ok = True
    return m


def _mock_err():
    m = MagicMock()
    m.ok = False
    return m


def test_api_health_all_healthy(client):
    with patch("proxy.routes.api._requests.get", return_value=_mock_ok()):
        r = client.get("/api/health")
    assert r.status_code == 200
    data = r.get_json()
    assert "services" in data
    for svc, info in data["services"].items():
        assert info["status"] == "healthy", f"{svc} should be healthy"


def test_api_health_unreachable(client):
    with patch("proxy.routes.api._requests.get", side_effect=ConnectionError("down")):
        r = client.get("/api/health")
    assert r.status_code == 200
    for svc, info in r.get_json()["services"].items():
        assert info["status"] == "unreachable"


def test_api_health_includes_expected_services(client):
    with patch("proxy.routes.api._requests.get", return_value=_mock_ok()):
        data = client.get("/api/health").get_json()
    names = set(data["services"])
    assert "clickhouse" in names
    assert "otel-collector" in names
    assert "grafana" in names
    assert "prometheus" in names
    assert "signoz" not in names  # disabled in fixture


def test_api_health_signoz_included_when_enabled(client):
    with client.application.app_context():
        client.application.wizard_config["enable_signoz"] = True
    with patch("proxy.routes.api._requests.get", return_value=_mock_ok()):
        data = client.get("/api/health").get_json()
    assert "signoz" in data["services"]


# ---------------------------------------------------------------------------
# /api/telemetry/summary
# ---------------------------------------------------------------------------

def _ch_post_mock(url, **kwargs):
    """Return fake ClickHouse JSON responses based on the SQL in the body."""
    sql = kwargs.get("data", b"").decode()
    m = MagicMock()
    m.raise_for_status = lambda: None
    if "DISTINCT ServiceName" in sql:
        m.json.return_value = {"data": [{"ServiceName": "frontend"}, {"ServiceName": "cartservice"}]}
    elif "otel_logs" in sql:
        m.json.return_value = {"data": [{"n": "42"}]}
    elif "countIf" in sql:
        m.json.return_value = {"data": [{"errors": "5", "total": "100"}]}
    else:
        m.json.return_value = {"data": [{"n": "200"}]}
    return m


def test_telemetry_summary_shape(client):
    with patch("proxy.routes.api._requests.post", side_effect=_ch_post_mock):
        r = client.get("/api/telemetry/summary")
    assert r.status_code == 200
    data = r.get_json()
    assert "services" in data
    assert "trace_count" in data
    assert "log_count" in data
    assert "error_rate_pct" in data


def test_telemetry_summary_values(client):
    with patch("proxy.routes.api._requests.post", side_effect=_ch_post_mock):
        data = client.get("/api/telemetry/summary").get_json()
    assert set(data["services"]) == {"frontend", "cartservice"}
    assert data["trace_count"] == 200
    assert data["log_count"] == 42
    assert data["error_rate_pct"] == 5.0


def test_telemetry_summary_clickhouse_unreachable(client):
    """If ClickHouse is down, returns zeros rather than a 500."""
    with patch("proxy.routes.api._requests.post", side_effect=ConnectionError("down")):
        r = client.get("/api/telemetry/summary")
    assert r.status_code == 200
    data = r.get_json()
    assert data["trace_count"] == 0
    assert data["services"] == []


# ---------------------------------------------------------------------------
# /api/rca/results and /api/rca/trigger
# ---------------------------------------------------------------------------

def test_rca_results_empty(client):
    r = client.get("/api/rca/results")
    assert r.status_code == 200
    assert r.get_json()["results"] == []


def test_rca_trigger_missing_fields(client):
    r = client.post("/api/rca/trigger", json={})
    assert r.status_code == 400


def test_rca_trigger_end_before_start(client):
    r = client.post("/api/rca/trigger", json={"start_time": 1000, "end_time": 999})
    assert r.status_code == 400
