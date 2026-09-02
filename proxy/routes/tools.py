"""Tools route — returns enabled tool links from saved wizard config.

GET /api/tools — list of {name, url, description} for each enabled tool.

The list is derived entirely from app.wizard_config — the frontend renders
whatever this returns without hardcoding which tools exist.
"""

import os

from flask import Blueprint, current_app, jsonify

tools_bp = Blueprint("tools", __name__, url_prefix="/api")


def _env_flag(name: str) -> str | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    return raw.strip().lower()


def _signoz_enabled(cfg: dict) -> bool:
    """Wizard toggle, overridden by ENABLE_SIGNOZ env when set.

    ENABLE_SIGNOZ=false always hides SigNoz from /api/tools, matching
    the compose file not being included (no SigNoz containers).
    """
    env = _env_flag("ENABLE_SIGNOZ")
    if env in ("false", "0", "no", "off"):
        return False
    if env in ("true", "1", "yes", "on"):
        return True
    return bool(cfg.get("enable_signoz", False))


def _build_tools(cfg: dict) -> list:
    """Build the tool list from a wizard config dict."""
    tools = []
    if cfg.get("enable_grafana", True):
        port = cfg.get("grafana_port", 3000)
        tools.append({
            "name": "Grafana",
            "url": f"http://localhost:{port}",
            "description": "Metrics dashboards",
        })
    if cfg.get("enable_prometheus_ui", True):
        port = cfg.get("prometheus_port", 9090)
        tools.append({
            "name": "Prometheus",
            "url": f"http://localhost:{port}",
            "description": "Metrics explorer (Mode A only)",
        })
    if _signoz_enabled(cfg):
        port = cfg.get("signoz_port", int(current_app.config.get("SIGNOZ_PORT", 8080)))
        tools.append({
            "name": "SigNoz",
            "url": f"http://localhost:{port}",
            "description": "Distributed tracing & metrics (SigNoz stack)",
        })
    return tools


@tools_bp.route("/tools", methods=["GET"])
def get_tools():
    """Return list of enabled tool links derived from saved wizard config."""
    return jsonify(_build_tools(current_app.wizard_config)), 200
