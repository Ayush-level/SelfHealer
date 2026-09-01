"""Integration tests for POST /correlate."""

import json
import pytest
from unittest.mock import MagicMock, patch

from proxy.app import create_app
from proxy.correlation.engine import (
    CorrelationPayload,
    TraceCorrelation,
    CorrelatedSpan,
    CorrelatedLog,
)
from proxy.adapters.metrics_adapter import MetricQueryResult, MetricSeries, MetricSample


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    app = create_app({
        "TESTING": True,
        "STORAGE_MODE": "prometheus",
        "CLICKHOUSE_URL": "http://mock-ch:8123",
    })
    with app.test_client() as c:
        yield c


def _make_payload() -> CorrelationPayload:
    """Build a realistic CorrelationPayload for use as the engine mock return."""
    span_root = CorrelatedSpan(
        trace_id="abc123",
        span_id="s001",
        parent_span_id="",
        service_name="frontend",
        span_name="GET /cart",
        status_code="Error",
        status_message="upstream error",
        duration_ns=120_000_000,
        timestamp=1_700_000_000.0,
        attributes={"http.status_code": "500"},
    )
    span_child = CorrelatedSpan(
        trace_id="abc123",
        span_id="s002",
        parent_span_id="s001",
        service_name="cartservice",
        span_name="GetCart",
        status_code="Error",
        status_message="redis unavailable",
        duration_ns=40_000_000,
        timestamp=1_700_000_000.05,
        attributes={},
    )
    log = CorrelatedLog(
        timestamp=1_700_000_000.06,
        trace_id="abc123",
        span_id="s002",
        service_name="cartservice",
        severity="ERROR",
        body="Redis connection refused",
        attributes={"error": "ECONNREFUSED"},
    )
    trace_corr = TraceCorrelation(
        trace_id="abc123",
        root_service="frontend",
        services_involved=["frontend", "cartservice"],
        has_errors=True,
        spans=[span_root, span_child],
        logs=[log],
    )
    metric_result = MetricQueryResult(
        metric_name="rpc_server_duration_milliseconds",
        series=[
            MetricSeries(
                metric_name="rpc_server_duration_milliseconds",
                labels={"service_name": "frontend"},
                samples=[MetricSample(timestamp=1_700_000_000.0, value=310.5)],
            )
        ],
    )
    return CorrelationPayload(
        time_window={"start": 1_700_000_000.0, "end": 1_700_000_060.0},
        services_impacted=["cartservice", "frontend"],
        total_traces=1,
        error_traces=1,
        metrics=[metric_result.to_dict()],
        correlated_traces=[trace_corr],
    )


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------

@patch("proxy.routes.correlate.CorrelationEngine")
def test_correlate_returns_200_with_expected_shape(MockEngine, client):
    """POST /correlate returns 200 and the correct top-level JSON shape."""
    mock_engine_instance = MagicMock()
    mock_engine_instance.correlate.return_value = _make_payload()
    MockEngine.return_value = mock_engine_instance

    response = client.post(
        "/correlate",
        data=json.dumps({"start_time": 1_700_000_000.0, "end_time": 1_700_000_060.0}),
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.get_json()

    # Top-level keys required by CorrelationPayload.to_dict()
    for key in ("time_window", "services_impacted", "total_traces", "error_traces",
                "metrics", "correlated_traces"):
        assert key in data, f"Missing key: {key}"

    assert data["time_window"] == {"start": 1_700_000_000.0, "end": 1_700_000_060.0}
    assert data["total_traces"] == 1
    assert data["error_traces"] == 1
    assert sorted(data["services_impacted"]) == ["cartservice", "frontend"]


@patch("proxy.routes.correlate.CorrelationEngine")
def test_correlate_trace_structure(MockEngine, client):
    """Correlated traces in the response carry spans and logs."""
    mock_engine_instance = MagicMock()
    mock_engine_instance.correlate.return_value = _make_payload()
    MockEngine.return_value = mock_engine_instance

    response = client.post(
        "/correlate",
        data=json.dumps({"start_time": 1_700_000_000.0, "end_time": 1_700_000_060.0}),
        content_type="application/json",
    )

    data = response.get_json()
    assert len(data["correlated_traces"]) == 1
    trace = data["correlated_traces"][0]

    assert trace["trace_id"] == "abc123"
    assert trace["root_service"] == "frontend"
    assert trace["has_errors"] is True
    assert len(trace["spans"]) == 2
    assert len(trace["logs"]) == 1
    assert trace["logs"][0]["body"] == "Redis connection refused"


@patch("proxy.routes.correlate.CorrelationEngine")
def test_correlate_engine_receives_correct_args(MockEngine, client):
    """Engine.correlate() is called with the exact values from the request body."""
    mock_engine_instance = MagicMock()
    mock_engine_instance.correlate.return_value = _make_payload()
    MockEngine.return_value = mock_engine_instance

    body = {
        "start_time": 1_700_000_000.0,
        "end_time": 1_700_000_060.0,
        "service_name": "frontend",
        "trace_id": "abc123",
        "metric_names": ["rpc_server_duration_milliseconds"],
    }
    client.post("/correlate", data=json.dumps(body), content_type="application/json")

    mock_engine_instance.correlate.assert_called_once_with(
        start_time=1_700_000_000.0,
        end_time=1_700_000_060.0,
        service_name="frontend",
        trace_id="abc123",
        metric_names=["rpc_server_duration_milliseconds"],
    )


# ---------------------------------------------------------------------------
# Validation / error-path tests
# ---------------------------------------------------------------------------

def test_correlate_missing_start_time(client):
    """Missing start_time returns 400 with an error message."""
    response = client.post(
        "/correlate",
        data=json.dumps({"end_time": 1_700_000_060.0}),
        content_type="application/json",
    )
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data
    assert "start_time" in data["error"]


def test_correlate_missing_end_time(client):
    """Missing end_time returns 400 with an error message."""
    response = client.post(
        "/correlate",
        data=json.dumps({"start_time": 1_700_000_000.0}),
        content_type="application/json",
    )
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data
    assert "end_time" in data["error"]


def test_correlate_end_before_start(client):
    """end_time <= start_time returns 400."""
    response = client.post(
        "/correlate",
        data=json.dumps({"start_time": 1_700_000_060.0, "end_time": 1_700_000_000.0}),
        content_type="application/json",
    )
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data


def test_correlate_non_numeric_times(client):
    """Non-numeric start_time returns 400."""
    response = client.post(
        "/correlate",
        data=json.dumps({"start_time": "not-a-number", "end_time": 1_700_000_060.0}),
        content_type="application/json",
    )
    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data


def test_correlate_empty_body(client):
    """Empty body (no JSON) returns 400 listing both missing fields."""
    response = client.post("/correlate", content_type="application/json")
    assert response.status_code == 400
    data = response.get_json()
    assert "start_time" in data["error"]
    assert "end_time" in data["error"]
