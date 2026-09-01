"""API routes for health aggregation and telemetry summary.

GET /api/health            — aggregate HTTP health checks per service
GET /api/telemetry/summary — recent telemetry volume from ClickHouse
GET /api/rca/results       — list all RCA results (alias for frontend)
POST /api/rca/trigger      — alias for POST /rca (frontend manual trigger)

Health checks use HTTP only — no Docker socket access per ARCHITECTURE.md
§Container Health Monitoring.
"""

import time
from typing import Any, Dict

import requests as _requests
from flask import Blueprint, current_app, jsonify, request

from proxy.correlation.engine import CorrelationEngine
from proxy.rca.llm_client import create_llm_client

api_bp = Blueprint("api", __name__, url_prefix="/api")

_TIMEOUT = 3.0  # seconds per health probe


def _probe(url: str) -> Dict[str, Any]:
    """Return {status: healthy|unhealthy|unreachable, latency_ms: float}."""
    try:
        t0 = time.monotonic()
        r = _requests.get(url, timeout=_TIMEOUT)
        latency = round((time.monotonic() - t0) * 1000, 1)
        status = "healthy" if r.ok else "unhealthy"
        return {"status": status, "latency_ms": latency}
    except Exception:
        return {"status": "unreachable", "latency_ms": None}


@api_bp.route("/health", methods=["GET"])
def api_health():
    """Aggregate HTTP health checks for each service in the stack.

    Probes each service's own health endpoint — does NOT query Docker.
    Returns 200 always; callers should inspect each service's status field.
    """
    cfg = current_app.wizard_config
    services: Dict[str, Dict] = {}

    # Always check ClickHouse
    ch_url = current_app.config.get("CLICKHOUSE_URL", "http://localhost:8123")
    services["clickhouse"] = _probe(f"{ch_url}/ping")

    # OTel Collector health_check extension
    services["otel-collector"] = _probe("http://localhost:13133")

    if cfg.get("enable_grafana", True):
        port = cfg.get("grafana_port", 3000)
        services["grafana"] = _probe(f"http://localhost:{port}/api/health")

    storage_mode = current_app.config.get("STORAGE_MODE", "prometheus")
    if storage_mode != "clickhouse_only":
        prom_url = current_app.config.get("PROMETHEUS_URL", "http://localhost:9090")
        services["prometheus"] = _probe(f"{prom_url}/-/healthy")

    if cfg.get("enable_signoz", False):
        port = cfg.get("signoz_port", 8080)
        services["signoz"] = _probe(f"http://localhost:{port}/api/v1/health")

    return jsonify({"services": services}), 200


@api_bp.route("/telemetry/summary", methods=["GET"])
def telemetry_summary():
    """Return recent telemetry volume from ClickHouse.

    Queries otel_traces for the last hour:
    - distinct services seen
    - trace count
    - log count (otel_logs if available)
    - error rate %
    """
    ch_url = current_app.config.get("CLICKHOUSE_URL", "http://localhost:8123")
    base = ch_url.rstrip("/")

    def _query(sql: str):
        try:
            r = _requests.post(
                f"{base}/",
                data=f"{sql} FORMAT JSON".encode(),
                headers={"Content-Type": "text/plain; charset=utf-8"},
                timeout=5.0,
            )
            r.raise_for_status()
            return r.json().get("data", [])
        except Exception:
            return []

    # Services seen in last hour
    svc_rows = _query(
        "SELECT DISTINCT ServiceName FROM otel_traces "
        "WHERE Timestamp >= now() - INTERVAL 1 HOUR"
    )
    services = [r["ServiceName"] for r in svc_rows if r.get("ServiceName")]

    # Trace count
    tc_rows = _query(
        "SELECT count() AS n FROM otel_traces "
        "WHERE Timestamp >= now() - INTERVAL 1 HOUR"
    )
    trace_count = int(tc_rows[0]["n"]) if tc_rows else 0

    # Log count
    lc_rows = _query(
        "SELECT count() AS n FROM otel_logs "
        "WHERE Timestamp >= now() - INTERVAL 1 HOUR"
    )
    log_count = int(lc_rows[0]["n"]) if lc_rows else 0

    # Error rate
    err_rows = _query(
        "SELECT countIf(StatusCode='Error') AS errors, count() AS total "
        "FROM otel_traces WHERE Timestamp >= now() - INTERVAL 1 HOUR"
    )
    if err_rows and int(err_rows[0].get("total", 0)) > 0:
        error_rate_pct = round(
            100.0 * int(err_rows[0]["errors"]) / int(err_rows[0]["total"]), 2
        )
    else:
        error_rate_pct = 0.0

    return jsonify({
        "services": services,
        "trace_count": trace_count,
        "log_count": log_count,
        "error_rate_pct": error_rate_pct,
    }), 200


@api_bp.route("/rca/results", methods=["GET"])
def rca_results():
    """Return all RCA results (newest first)."""
    results = current_app.rca_store.list_all()
    results_sorted = sorted(results, key=lambda r: r.id, reverse=True)
    return jsonify({"results": [r.to_dict() for r in results_sorted]}), 200


@api_bp.route("/rca/trigger", methods=["POST"])
def rca_trigger():
    """Manual RCA trigger — same logic as POST /rca, under /api prefix."""
    body: Dict[str, Any] = request.get_json(silent=True) or {}

    missing = [f for f in ("start_time", "end_time") if f not in body]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    try:
        start_time = float(body["start_time"])
        end_time = float(body["end_time"])
    except (TypeError, ValueError):
        return jsonify({"error": "start_time and end_time must be numeric"}), 400

    if end_time <= start_time:
        return jsonify({"error": "end_time must be greater than start_time"}), 400

    ch_url: str = current_app.config.get("CLICKHOUSE_URL", "http://localhost:8123")
    engine = CorrelationEngine(
        metrics_adapter=current_app.metrics_adapter,
        clickhouse_url=ch_url,
    )
    try:
        payload = engine.correlate(
            start_time=start_time,
            end_time=end_time,
            service_name=body.get("service_name"),
            trace_id=body.get("trace_id"),
            metric_names=body.get("metric_names"),
        )
    except Exception as exc:
        current_app.logger.exception("Correlation failed in /api/rca/trigger: %s", exc)
        return jsonify({"error": "Correlation failed", "detail": str(exc)}), 500

    llm_provider: str = current_app.config.get("LLM_PROVIDER", "mock")
    llm_api_key: str = current_app.config.get("LLM_API_KEY", "")
    try:
        llm_client = create_llm_client(provider=llm_provider, api_key=llm_api_key)
        result = llm_client.generate(payload.to_dict())
    except Exception as exc:
        current_app.logger.exception("LLM failed in /api/rca/trigger: %s", exc)
        return jsonify({"error": "LLM RCA failed", "detail": str(exc)}), 500

    stored = current_app.rca_store.save(result)
    return jsonify(stored.to_dict()), 200
