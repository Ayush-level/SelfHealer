"""Tests for proxy/rca/llm_client.py — Task 5.1.

All tests use MockLLMClient or a mocked requests.post so no real API calls
are made.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from proxy.rca.llm_client import (
    RCAResult,
    MockLLMClient,
    OpenAILLMClient,
    AnthropicLLMClient,
    create_llm_client,
    _build_user_message,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_correlation_dict(has_errors: bool = True) -> dict:
    """Minimal but realistic CorrelationPayload dict for test inputs."""
    span = {
        "trace_id": "trace-abc",
        "span_id": "s001",
        "parent_span_id": "",
        "service_name": "productcatalogservice",
        "span_name": "GetProduct",
        "status_code": "Error" if has_errors else "Ok",
        "status_message": "ProductCatalogService Fail Feature Flag Enabled" if has_errors else "",
        "duration_ns": 50_000_000,
        "timestamp": 1_700_000_000.0,
        "attributes": {},
    }
    log = {
        "timestamp": 1_700_000_000.05,
        "trace_id": "trace-abc",
        "span_id": "s001",
        "service_name": "productcatalogservice",
        "severity": "ERROR" if has_errors else "INFO",
        "body": "Failed to load product due to feature flag" if has_errors else "OK",
        "attributes": {},
    }
    trace = {
        "trace_id": "trace-abc",
        "root_service": "frontend",
        "services_involved": ["frontend", "productcatalogservice"],
        "has_errors": has_errors,
        "spans": [span],
        "logs": [log] if has_errors else [],
    }
    return {
        "time_window": {"start": 1_700_000_000.0, "end": 1_700_000_060.0},
        "services_impacted": ["frontend", "productcatalogservice"] if has_errors else [],
        "total_traces": 10,
        "error_traces": 7 if has_errors else 0,
        "metrics": [
            {
                "metric_name": "rpc_server_duration_milliseconds",
                "series": [
                    {
                        "metric_name": "rpc_server_duration_milliseconds",
                        "labels": {"service_name": "frontend"},
                        "samples": [{"timestamp": 1_700_000_000.0, "value": 310.5}],
                    }
                ],
            }
        ],
        "correlated_traces": [trace],
    }


# ---------------------------------------------------------------------------
# RCAResult dataclass
# ---------------------------------------------------------------------------

def test_rca_result_valid():
    r = RCAResult(
        cause="Cache failure in cartservice",
        confidence=0.85,
        evidence=["cartservice/GetCart: redis unavailable"],
        playbook=["Check Redis health", "Restart cartservice pod"],
    )
    assert r.cause == "Cache failure in cartservice"
    assert r.confidence == 0.85
    assert len(r.evidence) == 1
    assert len(r.playbook) == 2
    assert len(r.id) > 0  # uuid assigned


def test_rca_result_to_dict_has_all_keys():
    r = RCAResult(
        cause="x", confidence=0.5, evidence=["e1"], playbook=["p1"]
    )
    d = r.to_dict()
    for key in ("id", "cause", "confidence", "evidence", "playbook"):
        assert key in d, f"Missing key: {key}"


def test_rca_result_from_dict_roundtrip():
    original = RCAResult(
        cause="Deployment caused OOMKill",
        confidence=0.9,
        evidence=["OOMKill event on paymentservice"],
        playbook=["Increase memory limit", "Roll back deployment"],
    )
    restored = RCAResult.from_dict(original.to_dict())
    assert restored.cause == original.cause
    assert restored.confidence == original.confidence
    assert restored.evidence == original.evidence
    assert restored.playbook == original.playbook
    assert restored.id == original.id


def test_rca_result_invalid_confidence():
    with pytest.raises(ValueError, match="confidence"):
        RCAResult(cause="x", confidence=1.5, evidence=["e"], playbook=[])


def test_rca_result_empty_evidence():
    with pytest.raises(ValueError, match="evidence"):
        RCAResult(cause="x", confidence=0.5, evidence=[], playbook=[])


def test_rca_result_empty_cause():
    with pytest.raises(ValueError, match="cause"):
        RCAResult(cause="", confidence=0.5, evidence=["e"], playbook=[])


# ---------------------------------------------------------------------------
# MockLLMClient
# ---------------------------------------------------------------------------

def test_mock_client_returns_rca_result():
    client = MockLLMClient()
    result = client.generate(_make_correlation_dict())
    assert isinstance(result, RCAResult)


def test_mock_client_parses_cause_confidence_evidence_playbook():
    """Core Task 5.1 requirement: all four fields present and valid."""
    client = MockLLMClient()
    result = client.generate(_make_correlation_dict())
    assert result.cause
    assert 0.0 <= result.confidence <= 1.0
    assert len(result.evidence) >= 1
    assert len(result.playbook) >= 1


def test_mock_client_harvests_error_evidence_from_payload():
    """Evidence strings drawn from the payload, not fabricated."""
    client = MockLLMClient()
    result = client.generate(_make_correlation_dict(has_errors=True))
    # At least one evidence item should mention the failing service
    combined = " ".join(result.evidence)
    assert "productcatalogservice" in combined or "ProductCatalogService" in combined


def test_mock_client_fixed_response():
    fixed = {
        "cause": "Hardcoded test cause",
        "confidence": 0.77,
        "evidence": ["Evidence A", "Evidence B"],
        "playbook": ["Step 1", "Step 2"],
    }
    client = MockLLMClient(fixed_response=fixed)
    result = client.generate(_make_correlation_dict())
    assert result.cause == "Hardcoded test cause"
    assert result.confidence == 0.77
    assert result.evidence == ["Evidence A", "Evidence B"]
    assert result.playbook == ["Step 1", "Step 2"]


def test_mock_client_no_errors_payload():
    """Client handles a payload with no error traces without crashing."""
    client = MockLLMClient()
    result = client.generate(_make_correlation_dict(has_errors=False))
    assert isinstance(result, RCAResult)
    assert len(result.evidence) >= 1


# ---------------------------------------------------------------------------
# create_llm_client factory
# ---------------------------------------------------------------------------

def test_factory_mock():
    client = create_llm_client("mock")
    assert isinstance(client, MockLLMClient)


def test_factory_mock_empty_string():
    client = create_llm_client("")
    assert isinstance(client, MockLLMClient)


def test_factory_openai():
    client = create_llm_client("openai", api_key="sk-test")
    assert isinstance(client, OpenAILLMClient)


def test_factory_anthropic():
    client = create_llm_client("anthropic", api_key="ant-test")
    assert isinstance(client, AnthropicLLMClient)


def test_factory_unknown_provider():
    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        create_llm_client("nonexistent_provider")


def test_factory_openai_requires_api_key():
    with pytest.raises(ValueError, match="LLM_API_KEY"):
        create_llm_client("openai", api_key="")


def test_factory_anthropic_requires_api_key():
    with pytest.raises(ValueError, match="LLM_API_KEY"):
        create_llm_client("anthropic", api_key="")


# ---------------------------------------------------------------------------
# OpenAILLMClient — mocked HTTP
# ---------------------------------------------------------------------------

def test_openai_client_parses_response():
    """OpenAI client correctly parses a mocked JSON-mode response."""
    mock_response_body = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "cause": "Feature flag enabled on productcatalogservice",
                        "confidence": 0.93,
                        "evidence": ["GetProduct returned Error for all requests"],
                        "playbook": ["Disable productCatalogFailure flag", "Verify recovery"],
                    })
                }
            }
        ]
    }
    with patch("proxy.rca.llm_client.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value=mock_response_body),
            raise_for_status=MagicMock(),
        )
        client = OpenAILLMClient(api_key="sk-test")
        result = client.generate(_make_correlation_dict())

    assert result.cause == "Feature flag enabled on productcatalogservice"
    assert result.confidence == 0.93
    assert result.evidence == ["GetProduct returned Error for all requests"]
    assert result.playbook == ["Disable productCatalogFailure flag", "Verify recovery"]


# ---------------------------------------------------------------------------
# AnthropicLLMClient — mocked HTTP
# ---------------------------------------------------------------------------

def test_anthropic_client_parses_response():
    """Anthropic client reconstructs JSON from the prefill + response body."""
    # The prefill sends "{", so the API returns the rest of the JSON object
    inner = (
        '"cause": "Redis eviction policy misconfiguration", '
        '"confidence": 0.81, '
        '"evidence": ["cartservice OOMKill after cache miss storm"], '
        '"playbook": ["Set maxmemory-policy to allkeys-lru", "Monitor eviction rate"]'
        "}"
    )
    mock_response_body = {
        "content": [{"text": inner}]
    }
    with patch("proxy.rca.llm_client.requests.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value=mock_response_body),
            raise_for_status=MagicMock(),
        )
        client = AnthropicLLMClient(api_key="ant-test")
        result = client.generate(_make_correlation_dict())

    assert result.cause == "Redis eviction policy misconfiguration"
    assert result.confidence == 0.81
    assert "cartservice OOMKill after cache miss storm" in result.evidence


# ---------------------------------------------------------------------------
# Prompt builder sanity check
# ---------------------------------------------------------------------------

def test_build_user_message_includes_key_fields():
    msg = _build_user_message(_make_correlation_dict())
    assert "1700000000" in msg        # time window
    assert "productcatalogservice" in msg
    assert "Error" in msg or "ERROR" in msg
