"""Config routes — setup wizard save/read.

GET  /api/config   — return current saved config, or {} if none saved yet
POST /api/config   — validate and save wizard input; return saved config

The config is stored in app.wizard_config (in-memory dict).  It is NOT
written back to .env at runtime because the proxy has no Docker socket
access and restarting containers requires a host-level command anyway —
see ARCHITECTURE.md §GUI & Frontend and FRONTEND.md §First-Run Setup Wizard.

The frontend uses the saved config to assemble the docker compose command
that the user runs manually.
"""

from flask import Blueprint, current_app, jsonify, request

config_bp = Blueprint("config", __name__, url_prefix="/api")

# Required fields and their types for basic validation
_REQUIRED: dict = {
    "storage_mode": str,
}

# Optional fields with defaults — all must be present in a complete config
_DEFAULTS: dict = {
    "storage_mode": "prometheus",
    "enable_grafana": True,
    "grafana_port": 3000,
    "enable_prometheus_ui": True,
    "prometheus_port": 9090,
    "enable_signoz": False,
    "signoz_port": 8080,
    "llm_provider": "mock",
    "llm_api_key": "",
    "rca_trigger_mode": "manual",
    "rca_interval_minutes": 15,
}

_VALID_STORAGE_MODES = ("prometheus", "clickhouse_only")
_VALID_LLM_PROVIDERS = ("openai", "anthropic", "mock")
_VALID_RCA_MODES = ("manual", "automatic")


def _validate(data: dict) -> list[str]:
    """Return a list of validation error strings, empty if valid."""
    errors = []
    mode = data.get("storage_mode")
    if mode not in _VALID_STORAGE_MODES:
        errors.append(f"storage_mode must be one of {_VALID_STORAGE_MODES}")
    if data.get("llm_provider") not in _VALID_LLM_PROVIDERS:
        errors.append(f"llm_provider must be one of {_VALID_LLM_PROVIDERS}")
    if data.get("rca_trigger_mode") not in _VALID_RCA_MODES:
        errors.append(f"rca_trigger_mode must be one of {_VALID_RCA_MODES}")
    for port_key in ("grafana_port", "prometheus_port", "signoz_port"):
        val = data.get(port_key)
        if not isinstance(val, int) or not (1 <= val <= 65535):
            errors.append(f"{port_key} must be an integer 1–65535")
    interval = data.get("rca_interval_minutes")
    if not isinstance(interval, int) or interval < 1:
        errors.append("rca_interval_minutes must be a positive integer")
    return errors


@config_bp.route("/config", methods=["GET"])
def get_config():
    """Return saved wizard config, or {} on first run."""
    return jsonify(current_app.wizard_config), 200


@config_bp.route("/config", methods=["POST"])
def post_config():
    """Validate and save wizard config.  Returns the saved config."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    # Merge over defaults so partial payloads are accepted
    merged = {**_DEFAULTS, **body}

    errors = _validate(merged)
    if errors:
        return jsonify({"error": "Validation failed", "details": errors}), 400

    current_app.wizard_config = merged
    return jsonify(merged), 200
