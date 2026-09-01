"""Tests for GET /api/tools (Task 7.4)."""
import pytest
from proxy.app import create_app


@pytest.fixture
def client():
    app = create_app({"TESTING": True, "STORAGE_MODE": "prometheus"})
    with app.test_client() as c:
        yield c


def _save_config(client, overrides: dict):
    defaults = {
        "storage_mode": "prometheus",
        "enable_grafana": True, "grafana_port": 3000,
        "enable_prometheus_ui": True, "prometheus_port": 9090,
        "enable_signoz": False, "signoz_port": 8080,
        "llm_provider": "mock", "llm_api_key": "",
        "rca_trigger_mode": "manual", "rca_interval_minutes": 15,
    }
    client.post("/api/config", json={**defaults, **overrides})


def test_tools_default_config(client):
    """Default config: Grafana + Prometheus UI enabled, SigNoz off."""
    _save_config(client, {})
    r = client.get("/api/tools")
    assert r.status_code == 200
    tools = r.get_json()
    names = [t["name"] for t in tools]
    assert "Grafana" in names
    assert "Prometheus" in names
    assert "SigNoz" not in names


def test_tools_grafana_disabled(client):
    _save_config(client, {"enable_grafana": False})
    tools = client.get("/api/tools").get_json()
    assert all(t["name"] != "Grafana" for t in tools)


def test_tools_prometheus_disabled(client):
    _save_config(client, {"enable_prometheus_ui": False})
    tools = client.get("/api/tools").get_json()
    assert all(t["name"] != "Prometheus" for t in tools)


def test_tools_signoz_enabled(client):
    _save_config(client, {"enable_signoz": True, "signoz_port": 8080})
    tools = client.get("/api/tools").get_json()
    names = [t["name"] for t in tools]
    assert "SigNoz" in names
    signoz = next(t for t in tools if t["name"] == "SigNoz")
    assert ":8080" in signoz["url"]


def test_tools_all_disabled(client):
    _save_config(client, {"enable_grafana": False, "enable_prometheus_ui": False, "enable_signoz": False})
    tools = client.get("/api/tools").get_json()
    assert tools == []


def test_tools_custom_port(client):
    _save_config(client, {"enable_grafana": True, "grafana_port": 3001})
    tools = client.get("/api/tools").get_json()
    grafana = next(t for t in tools if t["name"] == "Grafana")
    assert ":3001" in grafana["url"]


def test_tools_empty_config_uses_defaults(client):
    """No config saved yet → defaults include Grafana + Prometheus."""
    r = client.get("/api/tools")
    assert r.status_code == 200
    # wizard_config is {} so _build_tools gets defaults from cfg.get(key, default)
    tools = r.get_json()
    names = [t["name"] for t in tools]
    assert "Grafana" in names
    assert "Prometheus" in names
