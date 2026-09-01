"""POST /correlate route — wraps the CorrelationEngine."""

from typing import Any, Dict

from flask import Blueprint, current_app, jsonify, request

from proxy.correlation.engine import CorrelationEngine

correlate_bp = Blueprint("correlate", __name__)


@correlate_bp.route("/correlate", methods=["POST"])
def correlate() -> tuple:
    """Correlate metrics, logs, and traces for a given time window.

    Request body (JSON):
        start_time   float  required  Unix epoch seconds, window start
        end_time     float  required  Unix epoch seconds, window end
        service_name str    optional  filter to a single service
        trace_id     str    optional  filter to a single trace
        metric_names list   optional  explicit metric names to fetch;
                                      defaults to auto-selected key metrics

    Returns:
        200  CorrelationPayload as JSON
        400  if start_time or end_time are missing / invalid
        500  if the engine raises an unexpected error
    """
    body: Dict[str, Any] = request.get_json(silent=True) or {}

    # --- Validate required fields ---
    missing = [f for f in ("start_time", "end_time") if f not in body]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    try:
        start_time = float(body["start_time"])
        end_time = float(body["end_time"])
    except (TypeError, ValueError):
        return jsonify({"error": "start_time and end_time must be numeric (Unix epoch seconds)"}), 400

    if end_time <= start_time:
        return jsonify({"error": "end_time must be greater than start_time"}), 400

    service_name: str | None = body.get("service_name")
    trace_id: str | None = body.get("trace_id")
    metric_names: list | None = body.get("metric_names")

    # --- Build engine from app context ---
    clickhouse_url: str = current_app.config.get("CLICKHOUSE_URL", "http://localhost:8123")
    engine = CorrelationEngine(
        metrics_adapter=current_app.metrics_adapter,
        clickhouse_url=clickhouse_url,
    )

    try:
        payload = engine.correlate(
            start_time=start_time,
            end_time=end_time,
            service_name=service_name,
            trace_id=trace_id,
            metric_names=metric_names,
        )
    except Exception as exc:  # pragma: no cover — real infra errors
        current_app.logger.exception("Correlation engine error: %s", exc)
        return jsonify({"error": "Internal correlation error", "detail": str(exc)}), 500

    return jsonify(payload.to_dict()), 200
