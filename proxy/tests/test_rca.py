"""Integration tests for POST /rca — Task 5.2.

Both CorrelationEngine and the LLM client are patched so no real ClickHouse,
Prometheus, or LLM API calls are made.  The tests verify:
  - the full correlate → LLM → JSON pipeline runs end-to-end
  - the response contains all four required fields (cause/confidence/evidence/playbook)
  - optional request fields are forwarded correctly
  - input validation returns appropriate 400s
"""

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
from proxy.rca.llm_client import RCAResult


# ---------------------------------------------------------------------------
# Shared fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    app = create_app({
        "TESTING": True,
        "STORAGE_MODE": "prometheus",
        "CLICKHOUSE_URL": "http://mock-ch:8123",
        "LLM_PROVIDER": "mock",
        "LLM_API_KEY": "",
    })
    with app.test_client() as c:
        yield c


def _make_correlation_payload() -> CorrelationPayload:
    span = CorrelatedSpan(
        trace_id="trace-rca-01",
        span_id="s001",
        parent_span_id="",
        service_name="frontend",
        span_name="GET /checkout",
        status_code="Error",
        status_message="upstream payment failure",
        duration_ns=200_000_000,
        timestamp=1_700_000_000.0,
        attributes={"http.status_code": "503"},
    )
    child = CorrelatedSpan(
        trace_id="trace-rca-01",
        span_id="s002",
        parent_span_id="s001",
        service_name="paymentservice",
        span_name="Charge",
        status_code="Error",
        status_message="credit card processor timeout",
        duration_ns=180_000_000,
        timestamp=1_700_000_000.02,
        attributes={},
    )
    log = CorrelatedLog(
        timestamp=1_700_000_000.03,
        trace_id="trace-rca-01",
        span_id="s002",
        service_name="paymentservice",
        severity="ERROR",
        body="Timeout calling payment processor after 180ms",
        attributes={},
    )
    trace_corr = TraceCorrelation(
        trace_id="trace-rca-01",
        root_service="frontend",
        services_involved=["frontend", "paymentservice"],
        has_errors=True,
        spans=[span, child],
        logs=[log],
    )
    metric = MetricQueryResult(
        metric_name="rpc_server_duration_milliseconds",
        series=[
            MetricSeries(
                metric_name="rpc_server_duration_milliseconds",
                labels={"service_name": "paymentservice"},
                samples=[MetricSample(timestamp=1_700_000_000.0, value=920.0)],
            )
        ],
    )
    return CorrelationPayload(
        time_window={"start": 1_700_000_000.0, "end": 1_700_000_060.0},
        services_impacted=["frontend", "paymentservice"],
        total_traces=5,
        error_traces=4,
        metrics=[metric.to_dict()],
        correlated_traces=[trace_corr],
    )


def _make_rca_result() -> RCAResult:
    return RCAResult(
        cause="Payment processor timeout causing checkout failures",
        confidence=0.91,
        evidence=[
            "paymentservice/Charge: credit card processor timeout",
            "paymentservice [ERROR]: Timeout calling payment processor after 180ms",
        ],
        playbook=[
            "Check payment processor status page",
            "Review paymentservice timeout configuration",
            "Enable circuit breaker if not already active",
        ],
    )


# ---------------------------------------------------------------------------
# Happy-path: end-to-end pipeline
# ---------------------------------------------------------------------------

@patch("proxy.routes.rca.create_llm_client")
@patch("proxy.routes.rca.CorrelationEngine")
def test_rca_returns_200_with_required_shape(MockEngine, MockLLMFactory, client):
    """POST /rca returns 200 with all four required RCA fields present."""
    mock_engine = MagicMock()
    mock_engine.correlate.return_value = _make_correlation_payload()
    MockEngine.return_value = mock_engine

    mock_llm = MagicMock()
    mock_llm.generate.return_value = _make_rca_result()
    MockLLMFactory.return_value = mock_llm

    response = client.post(
        "/rca",
        data=json.dumps({"start_time": 1_700_000_000.0, "end_time": 1_700_000_060.0}),
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.get_json()

    for key in ("id", "cause", "confidence", "evidence", "playbook"):
        assert key in data, f"Missing required key: {key}"


@patch("proxy.routes.rca.create_llm_client")
@patch("proxy.routes.rca.CorrelationEngine")
def test_rca_response_values_match_llm_output(MockEngine, MockLLMFactory, client):
    """Response values are exactly what the LLM client returned."""
    mock_engine = MagicMock()
    mock_engine.correlate.return_value = _make_correlation_payload()
    MockEngine.return_value = mock_engine

    expected = _make_rca_result()
    mock_llm = MagicMock()
    mock_llm.generate.return_value = expected
    MockLLMFactory.return_value = mock_llm

    response = client.post(
        "/rca",
        data=json.dumps({"start_time": 1_700_000_000.0, "end_time": 1_700_000_060.0}),
        content_type="application/json",
    )
    data = response.get_json()

    assert data["cause"] == expected.cause
    assert data["confidence"] == expected.confidence
    assert data["evidence"] == expected.evidence
    assert data["playbook"] == expected.playbook
    assert data["id"] == expected.id


@patch("proxy.routes.rca.create_llm_client")
@patch("proxy.routes.rca.CorrelationEngine")
def test_rca_llm_receives_correlation_payload(MockEngine, MockLLMFactory, client):
    """LLM client's generate() is called with the serialised correlation dict."""
    correlation = _make_correlation_payload()
    mock_engine = MagicMock()
    mock_engine.correlate.return_value = correlation
    MockEngine.return_value = mock_engine

    mock_llm = MagicMock()
    mock_llm.generate.return_value = _make_rca_result()
    MockLLMFactory.return_value = mock_llm

    client.post(
        "/rca",
        data=json.dumps({"start_time": 1_700_000_000.0, "end_time": 1_700_000_060.0}),
        content_type="application/json",
    )

    mock_llm.generate.assert_called_once()
    call_arg = mock_llm.generate.call_args[0][0]
    # The arg must be the dict form of the payload
    assert call_arg["total_traces"] == correlation.total_traces
    assert call_arg["error_traces"] == correlation.error_traces
    assert "correlated_traces" in call_arg


@patch("proxy.routes.rca.create_llm_client")
@patch("proxy.routes.rca.CorrelationEngine")
def test_rca_forwards_optional_params_to_engine(MockEngine, MockLLMFactory, client):
    """Optional service_name, trace_id, metric_names are forwarded to CorrelationEngine."""
    mock_engine = MagicMock()
    mock_engine.correlate.return_value = _make_correlation_payload()
    MockEngine.return_value = mock_engine

    mock_llm = MagicMock()
    mock_llm.generate.return_value = _make_rca_result()
    MockLLMFactory.return_value = mock_llm

    body = {
        "start_time": 1_700_000_000.0,
        "end_time": 1_700_000_060.0,
        "service_name": "paymentservice",
        "trace_id": "trace-rca-01",
        "metric_names": ["rpc_server_duration_milliseconds"],
    }
    client.post("/rca", data=json.dumps(body), content_type="application/json")

    mock_engine.correlate.assert_called_once_with(
        start_time=1_700_000_000.0,
        end_time=1_700_000_060.0,
        service_name="paymentservice",
        trace_id="trace-rca-01",
        metric_names=["rpc_server_duration_milliseconds"],
    )


@patch("proxy.routes.rca.create_llm_client")
@patch("proxy.routes.rca.CorrelationEngine")
def test_rca_mock_provider_end_to_end(MockEngine, MockLLMFactory, client):
    """Full end-to-end with MockLLMClient (no fixed_response) — covers the
    real mock path so the pipeline works without a live LLM key."""
    from proxy.rca.llm_client import MockLLMClient

    mock_engine = MagicMock()
    mock_engine.correlate.return_value = _make_correlation_payload()
    MockEngine.return_value = mock_engine

    # Use the real MockLLMClient, not a MagicMock
    MockLLMFactory.return_value = MockLLMClient()

    response = client.post(
        "/rca",
        data=json.dumps({"start_time": 1_700_000_000.0, "end_time": 1_700_000_060.0}),
        content_type="application/json",
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["cause"]
    assert 0.0 <= data["confidence"] <= 1.0
    assert len(data["evidence"]) >= 1
    assert len(data["playbook"]) >= 1


# ---------------------------------------------------------------------------
# Validation / error-path
# ---------------------------------------------------------------------------

def test_rca_missing_start_time(client):
    response = client.post(
        "/rca",
        data=json.dumps({"end_time": 1_700_000_060.0}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "start_time" in response.get_json()["error"]


def test_rca_missing_end_time(client):
    response = client.post(
        "/rca",
        data=json.dumps({"start_time": 1_700_000_000.0}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert "end_time" in response.get_json()["error"]


def test_rca_end_before_start(client):
    response = client.post(
        "/rca",
        data=json.dumps({"start_time": 1_700_000_060.0, "end_time": 1_700_000_000.0}),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_rca_non_numeric_times(client):
    response = client.post(
        "/rca",
        data=json.dumps({"start_time": "bad", "end_time": 1_700_000_060.0}),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_rca_empty_body(client):
    response = client.post("/rca", content_type="application/json")
    assert response.status_code == 400
    err = response.get_json()["error"]
    assert "start_time" in err
    assert "end_time" in err


# ---------------------------------------------------------------------------
# Error propagation from subsystems
# ---------------------------------------------------------------------------

@patch("proxy.routes.rca.CorrelationEngine")
def test_rca_correlation_failure_returns_500(MockEngine, client):
    """If CorrelationEngine raises, /rca returns 500 with an error key."""
    mock_engine = MagicMock()
    mock_engine.correlate.side_effect = RuntimeError("ClickHouse unreachable")
    MockEngine.return_value = mock_engine

    response = client.post(
        "/rca",
        data=json.dumps({"start_time": 1_700_000_000.0, "end_time": 1_700_000_060.0}),
        content_type="application/json",
    )
    assert response.status_code == 500
    data = response.get_json()
    assert "error" in data
    assert "Correlation" in data["error"]


@patch("proxy.routes.rca.create_llm_client")
@patch("proxy.routes.rca.CorrelationEngine")
def test_rca_llm_failure_returns_500(MockEngine, MockLLMFactory, client):
    """If LLM generate() raises, /rca returns 500 with an error key."""
    mock_engine = MagicMock()
    mock_engine.correlate.return_value = _make_correlation_payload()
    MockEngine.return_value = mock_engine

    mock_llm = MagicMock()
    mock_llm.generate.side_effect = RuntimeError("LLM API rate limit")
    MockLLMFactory.return_value = mock_llm

    response = client.post(
        "/rca",
        data=json.dumps({"start_time": 1_700_000_000.0, "end_time": 1_700_000_060.0}),
        content_type="application/json",
    )
    assert response.status_code == 500
    data = response.get_json()
    assert "error" in data
    assert "LLM" in data["error"]
