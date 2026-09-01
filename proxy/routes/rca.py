"""RCA routes.

POST /rca                   — correlate → LLM → persist → return pending result
GET  /rca/<id>              — retrieve a stored RCA by id
POST /rca/<id>/approve      — approve a pending RCA suggestion
POST /rca/<id>/reject       — reject a pending RCA suggestion

Every RCA suggestion requires explicit human approval before anything is
considered actioned (ARCHITECTURE.md §Human Review & Approval).
"""

from typing import Any, Dict

from flask import Blueprint, current_app, jsonify, request

from proxy.correlation.engine import CorrelationEngine
from proxy.rca.llm_client import create_llm_client
from proxy.store.rca_store import STATUS_APPROVED, STATUS_PENDING, STATUS_REJECTED

rca_bp = Blueprint("rca", __name__)


# ---------------------------------------------------------------------------
# POST /rca — produce and persist a new RCA suggestion
# ---------------------------------------------------------------------------

@rca_bp.route("/rca", methods=["POST"])
def rca() -> tuple:
    """Trigger on-demand RCA for a given time window.

    Request body (JSON):
        start_time   float  required  Unix epoch seconds, window start
        end_time     float  required  Unix epoch seconds, window end
        service_name str    optional  scope correlation to one service
        trace_id     str    optional  scope correlation to one trace
        metric_names list   optional  explicit metrics to include

    Response 200 — StoredRCA as JSON (status always "pending" at creation):
        {
          "id":         "<uuid>",
          "cause":      "<root-cause sentence>",
          "confidence": <float 0–1>,
          "evidence":   ["<observation>", ...],
          "playbook":   ["<step>", ...],
          "status":     "pending",
          "note":       ""
        }

    Errors: 400 invalid input | 500 correlation or LLM failure
    """
    body: Dict[str, Any] = request.get_json(silent=True) or {}

    missing = [f for f in ("start_time", "end_time") if f not in body]
    if missing:
        return jsonify({"error": f"Missing required fields: {', '.join(missing)}"}), 400

    try:
        start_time = float(body["start_time"])
        end_time = float(body["end_time"])
    except (TypeError, ValueError):
        return jsonify(
            {"error": "start_time and end_time must be numeric (Unix epoch seconds)"}
        ), 400

    if end_time <= start_time:
        return jsonify({"error": "end_time must be greater than start_time"}), 400

    service_name: str | None = body.get("service_name")
    trace_id: str | None = body.get("trace_id")
    metric_names: list | None = body.get("metric_names")

    # Step 1: correlate
    clickhouse_url: str = current_app.config.get("CLICKHOUSE_URL", "http://localhost:8123")
    engine = CorrelationEngine(
        metrics_adapter=current_app.metrics_adapter,
        clickhouse_url=clickhouse_url,
    )
    try:
        correlation_payload = engine.correlate(
            start_time=start_time,
            end_time=end_time,
            service_name=service_name,
            trace_id=trace_id,
            metric_names=metric_names,
        )
    except Exception as exc:
        current_app.logger.exception("Correlation step failed in /rca: %s", exc)
        return jsonify({"error": "Correlation failed", "detail": str(exc)}), 500

    # Step 2: LLM RCA
    llm_provider: str = current_app.config.get("LLM_PROVIDER", "mock")
    llm_api_key: str = current_app.config.get("LLM_API_KEY", "")
    try:
        llm_client = create_llm_client(provider=llm_provider, api_key=llm_api_key)
        result = llm_client.generate(correlation_payload.to_dict())
    except Exception as exc:
        current_app.logger.exception("LLM step failed in /rca: %s", exc)
        return jsonify({"error": "LLM RCA failed", "detail": str(exc)}), 500

    # Step 3: persist as pending
    stored = current_app.rca_store.save(result)
    return jsonify(stored.to_dict()), 200


# ---------------------------------------------------------------------------
# GET /rca/<id> — retrieve a stored suggestion
# ---------------------------------------------------------------------------

@rca_bp.route("/rca/<string:rca_id>", methods=["GET"])
def get_rca(rca_id: str) -> tuple:
    """Return a stored RCA suggestion by id.

    Response 200 — StoredRCA as JSON
    Response 404 — {"error": "Not found"}
    """
    entry = current_app.rca_store.get(rca_id)
    if entry is None:
        return jsonify({"error": f"RCA '{rca_id}' not found"}), 404
    return jsonify(entry.to_dict()), 200


# ---------------------------------------------------------------------------
# POST /rca/<id>/approve
# ---------------------------------------------------------------------------

@rca_bp.route("/rca/<string:rca_id>/approve", methods=["POST"])
def approve_rca(rca_id: str) -> tuple:
    """Approve a pending RCA suggestion.

    Optional request body (JSON):
        note  str  free-form reason / comment

    Response 200 — updated StoredRCA (status="approved")
    Response 404 — not found
    """
    body: Dict[str, Any] = request.get_json(silent=True) or {}
    note: str = str(body.get("note", ""))

    entry = current_app.rca_store.approve(rca_id, note=note)
    if entry is None:
        return jsonify({"error": f"RCA '{rca_id}' not found"}), 404
    return jsonify(entry.to_dict()), 200


# ---------------------------------------------------------------------------
# POST /rca/<id>/reject
# ---------------------------------------------------------------------------

@rca_bp.route("/rca/<string:rca_id>/reject", methods=["POST"])
def reject_rca(rca_id: str) -> tuple:
    """Reject a pending RCA suggestion.

    Optional request body (JSON):
        note  str  free-form reason / comment

    Response 200 — updated StoredRCA (status="rejected")
    Response 404 — not found
    """
    body: Dict[str, Any] = request.get_json(silent=True) or {}
    note: str = str(body.get("note", ""))

    entry = current_app.rca_store.reject(rca_id, note=note)
    if entry is None:
        return jsonify({"error": f"RCA '{rca_id}' not found"}), 404
    return jsonify(entry.to_dict()), 200
