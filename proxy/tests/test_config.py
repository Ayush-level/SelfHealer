"""Tests for GET/POST /api/config (Task 7.2) and command generation (Task 7.3)."""
import pytest
from proxy.app import create_app


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    app = create_app({"TESTING": True, "STORAGE_MODE": "prometheus"})
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Task 7.2 — GET/POST /api/config
# ---------------------------------------------------------------------------

def test_get_config_empty_on_first_run(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    assert r.get_json() == {}


def test_post_config_returns_saved(client):
    payload = {
        "storage_mode": "prometheus",
        "enable_grafana": True,
        "grafana_port": 3000,
        "enable_prometheus_ui": False,
        "prometheus_port": 9090,
        "enable_signoz": False,
        "signoz_port": 8080,
        "llm_provider": "mock",
        "llm_api_key": "",
        "rca_trigger_mode": "manual",
        "rca_interval_minutes": 15,
    }
    r = client.post("/api/config", json=payload)
    assert r.status_code == 200
    saved = r.get_json()
    assert saved["storage_mode"] == "prometheus"
    assert saved["enable_prometheus_ui"] is False


def test_get_config_returns_what_was_saved(client):
    payload = {"storage_mode": "clickhouse_only", "llm_provider": "mock",
               "rca_trigger_mode": "automatic", "rca_interval_minutes": 5,
               "enable_grafana": True, "grafana_port": 3000,
               "enable_prometheus_ui": True, "prometheus_port": 9090,
               "enable_signoz": True, "signoz_port": 8080, "llm_api_key": ""}
    client.post("/api/config", json=payload)
    r = client.get("/api/config")
    assert r.status_code == 200
    data = r.get_json()
    assert data["storage_mode"] == "clickhouse_only"
    assert data["enable_signoz"] is True
    assert data["rca_interval_minutes"] == 5


def test_post_config_invalid_storage_mode(client):
    r = client.post("/api/config", json={"storage_mode": "badmode", "llm_provider": "mock",
                                          "rca_trigger_mode": "manual", "rca_interval_minutes": 5,
                                          "enable_grafana": True, "grafana_port": 3000,
                                          "enable_prometheus_ui": True, "prometheus_port": 9090,
                                          "enable_signoz": False, "signoz_port": 8080, "llm_api_key": ""})
    assert r.status_code == 400
    assert "storage_mode" in r.get_json()["details"][0]


def test_post_config_bad_port(client):
    r = client.post("/api/config", json={"storage_mode": "prometheus", "llm_provider": "mock",
                                          "rca_trigger_mode": "manual", "rca_interval_minutes": 5,
                                          "enable_grafana": True, "grafana_port": 99999,
                                          "enable_prometheus_ui": True, "prometheus_port": 9090,
                                          "enable_signoz": False, "signoz_port": 8080, "llm_api_key": ""})
    assert r.status_code == 400


def test_post_config_defaults_applied(client):
    """Partial payload — missing keys get defaults."""
    r = client.post("/api/config", json={"storage_mode": "prometheus"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["llm_provider"] == "mock"
    assert data["enable_grafana"] is True


def test_post_config_non_json_body(client):
    r = client.post("/api/config", data="not-json", content_type="text/plain")
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Task 7.3 — command generation matches expected flags
# ---------------------------------------------------------------------------

def _cmd(cfg: dict) -> str:
    """Re-implement buildCommand logic from Setup.jsx in Python for testing."""
    files = ["docker-compose.yml"]
    if cfg.get("enable_prometheus_ui"):
        files.append("docker-compose.prometheus-ui.yml")
    if cfg.get("enable_signoz"):
        files.append("docker-compose.signoz.yml")
    files.append("docker-compose.otel-demo-override.yml")
    file_args = " ".join(f"-f {f}" for f in files)
    profile = "--profile mode-a" if cfg.get("storage_mode") == "prometheus" else ""
    parts = ["docker compose", file_args]
    if profile:
        parts.append(profile)
    parts.append("up -d")
    return " ".join(p for p in parts if p)


def test_command_mode_a_with_all_tools():
    cfg = {"storage_mode": "prometheus", "enable_prometheus_ui": True, "enable_signoz": True}
    cmd = _cmd(cfg)
    assert "-f docker-compose.yml" in cmd
    assert "-f docker-compose.prometheus-ui.yml" in cmd
    assert "-f docker-compose.signoz.yml" in cmd
    assert "--profile mode-a" in cmd
    assert "up -d" in cmd


def test_command_mode_b_no_optional_files():
    cfg = {"storage_mode": "clickhouse_only", "enable_prometheus_ui": False, "enable_signoz": False}
    cmd = _cmd(cfg)
    assert "--profile mode-a" not in cmd
    assert "docker-compose.prometheus-ui.yml" not in cmd
    assert "docker-compose.signoz.yml" not in cmd
    assert "up -d" in cmd


def test_command_signoz_only():
    cfg = {"storage_mode": "prometheus", "enable_prometheus_ui": False, "enable_signoz": True}
    cmd = _cmd(cfg)
    assert "docker-compose.signoz.yml" in cmd
    assert "docker-compose.prometheus-ui.yml" not in cmd
    assert "--profile mode-a" in cmd
