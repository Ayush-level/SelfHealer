"""Tests for proxy/scheduler/rca_scheduler.py (Phase 9 — Tasks 9.1, 9.2, 9.3)."""

import time
from unittest.mock import MagicMock, patch
import pytest

from proxy.app import create_app
from proxy.correlation.engine import CorrelationPayload, TraceCorrelation
from proxy.rca.llm_client import RCAResult


def _mock_payload():
    return CorrelationPayload(
        time_window={"start": time.time() - 300, "end": time.time()},
        services_impacted=["productcatalogservice"],
        total_traces=1,
        error_traces=1,
        metrics=[],
        correlated_traces=[
            TraceCorrelation(
                trace_id="trace-abc",
                root_service="productcatalogservice",
                services_involved=["productcatalogservice"],
                has_errors=True,
                spans=[],
                logs=[],
            )
        ],
    )



@pytest.fixture
def app_manual():
    app = create_app({
        "TESTING": True,
        "STORAGE_MODE": "prometheus",
        "RCA_TRIGGER_MODE": "manual",
        "RCA_INTERVAL_MINUTES": 1,
    })
    yield app
    if hasattr(app, "rca_scheduler") and app.rca_scheduler:
        app.rca_scheduler.shutdown(wait=False)


@pytest.fixture
def app_automatic():
    app = create_app({
        "TESTING": True,
        "STORAGE_MODE": "prometheus",
        "RCA_TRIGGER_MODE": "automatic",
        "RCA_INTERVAL_MINUTES": 1,
    })
    yield app
    if hasattr(app, "rca_scheduler") and app.rca_scheduler:
        app.rca_scheduler.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Task 9.1 — Automatic RCA Scheduler
# ---------------------------------------------------------------------------

def test_scheduler_automatic_mode_detected(app_automatic):
    assert app_automatic.rca_scheduler.is_automatic_mode() is True
    assert app_automatic.rca_scheduler.get_interval_minutes() == 1


def test_scheduler_manual_mode_detected(app_manual):
    assert app_manual.rca_scheduler.is_automatic_mode() is False


@patch("proxy.scheduler.rca_scheduler.CorrelationEngine")
@patch("proxy.scheduler.rca_scheduler.create_llm_client")
def test_scheduler_run_job_produces_rca_result(mock_create_llm, mock_engine_cls, app_automatic):
    """Test that a single scheduler run_job cycle runs correlate -> LLM -> saves to rca_store."""
    mock_engine = MagicMock()
    mock_engine.correlate.return_value = _mock_payload()
    mock_engine_cls.return_value = mock_engine

    mock_llm = MagicMock()
    mock_llm.generate.return_value = RCAResult(
        cause="Database connection timeout",
        confidence=0.92,
        evidence=["Log error: timeout connecting to DB"],
        playbook=["Check DB replica health", "Restart pool"],
    )
    mock_create_llm.return_value = mock_llm

    result_id = app_automatic.rca_scheduler.run_job()
    assert result_id is not None

    stored = app_automatic.rca_store.get(result_id)
    assert stored is not None
    assert stored.cause == "Database connection timeout"
    assert stored.confidence == 0.92
    assert stored.status == "pending"


@patch("proxy.scheduler.rca_scheduler.CorrelationEngine")
@patch("proxy.scheduler.rca_scheduler.create_llm_client")
def test_scheduler_automatic_two_results_interval(mock_create_llm, mock_engine_cls, app_automatic):
    """Task 9.1 test: with a fast interval and mocked LLM, confirm two results appear with distinct timestamps."""
    mock_engine = MagicMock()
    mock_engine.correlate.return_value = _mock_payload()
    mock_engine_cls.return_value = mock_engine

    mock_llm = MagicMock()
    mock_llm.generate.side_effect = [
        RCAResult(
            cause="Error spike in product catalog (cycle 1)",
            confidence=0.88,
            evidence=["High error rate"],
            playbook=["Scale service"],
        ),
        RCAResult(
            cause="Error spike in product catalog (cycle 2)",
            confidence=0.90,
            evidence=["High error rate continuing"],
            playbook=["Scale service"],
        ),
    ]
    mock_create_llm.return_value = mock_llm

    # Configure scheduler with 1-second interval for test
    app_automatic.rca_scheduler.sync_with_config(interval_seconds=1)

    # Trigger first execution and wait for the second interval
    res1 = app_automatic.rca_scheduler.run_job()
    assert res1 is not None

    time.sleep(1.1)
    # Check that jobs run automatically
    results = app_automatic.rca_store.list_all()
    assert len(results) >= 2
    causes = [r.cause for r in results]
    assert any("cycle 1" in c for c in causes)
    assert any("cycle 2" in c for c in causes)


# ---------------------------------------------------------------------------
# Task 9.2 — Manual mode still works independently
# ---------------------------------------------------------------------------

@patch("proxy.routes.api.CorrelationEngine")
@patch("proxy.routes.api.create_llm_client")
def test_manual_trigger_works_when_scheduler_manual(mock_create_llm, mock_engine_cls, app_manual):
    """Task 9.2 test: with RCA_TRIGGER_MODE=manual, manual POST /api/rca/trigger works."""
    mock_engine = MagicMock()
    mock_engine.correlate.return_value = _mock_payload()
    mock_engine_cls.return_value = mock_engine

    mock_llm = MagicMock()
    mock_llm.generate.return_value = RCAResult(
        cause="Manual analysis detected redis latency",
        confidence=0.85,
        evidence=["redis slowlog"],
        playbook=["Flush cache"],
    )
    mock_create_llm.return_value = mock_llm

    with app_manual.test_client() as client:
        r = client.post("/api/rca/trigger", json={
            "start_time": time.time() - 300,
            "end_time": time.time(),
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data["cause"] == "Manual analysis detected redis latency"
        assert data["status"] == "pending"


@patch("proxy.routes.api.CorrelationEngine")
@patch("proxy.routes.api.create_llm_client")
def test_manual_trigger_works_when_scheduler_automatic(mock_create_llm, mock_engine_cls, app_automatic):
    """Manual POST still works even when automatic scheduler is running."""
    mock_engine = MagicMock()
    mock_engine.correlate.return_value = _mock_payload()
    mock_engine_cls.return_value = mock_engine

    mock_llm = MagicMock()
    mock_llm.generate.return_value = RCAResult(
        cause="Manual analysis while scheduler active",
        confidence=0.91,
        evidence=["Trace logs"],
        playbook=["Review code"],
    )
    mock_create_llm.return_value = mock_llm

    with app_automatic.test_client() as client:
        r = client.post("/api/rca/trigger", json={
            "start_time": time.time() - 300,
            "end_time": time.time(),
        })
        assert r.status_code == 200
        data = r.get_json()
        assert data["cause"] == "Manual analysis while scheduler active"


# ---------------------------------------------------------------------------
# Task 9.3 — Both modes route through same approval flow
# ---------------------------------------------------------------------------

@patch("proxy.scheduler.rca_scheduler.CorrelationEngine")
@patch("proxy.scheduler.rca_scheduler.create_llm_client")
@patch("proxy.routes.api.CorrelationEngine")
@patch("proxy.routes.api.create_llm_client")
def test_both_modes_appear_in_results_and_approvable(
    mock_api_llm, mock_api_engine, mock_sched_llm, mock_sched_engine, app_automatic
):
    """Task 9.3 test: scheduler result & manual result both in /api/rca/results, both approvable/rejectable."""
    # 1. Generate automatic scheduler result
    mock_s_engine = MagicMock()
    mock_s_engine.correlate.return_value = _mock_payload()
    mock_sched_engine.return_value = mock_s_engine

    mock_s_llm = MagicMock()
    mock_s_llm.generate.return_value = RCAResult(
        cause="Scheduled auto cause",
        confidence=0.75,
        evidence=["Auto log"],
        playbook=["Auto fix"],
    )
    mock_sched_llm.return_value = mock_s_llm

    auto_id = app_automatic.rca_scheduler.run_job()

    # 2. Generate manual result via API
    mock_a_engine = MagicMock()
    mock_a_engine.correlate.return_value = _mock_payload()
    mock_api_engine.return_value = mock_a_engine

    mock_a_llm = MagicMock()
    mock_a_llm.generate.return_value = RCAResult(
        cause="Manual trigger cause",
        confidence=0.82,
        evidence=["Manual log"],
        playbook=["Manual fix"],
    )
    mock_api_llm.return_value = mock_a_llm

    with app_automatic.test_client() as client:
        r_manual = client.post("/api/rca/trigger", json={
            "start_time": time.time() - 300,
            "end_time": time.time(),
        })
        assert r_manual.status_code == 200
        manual_id = r_manual.get_json()["id"]

        # 3. Verify both appear in GET /api/rca/results
        r_list = client.get("/api/rca/results")
        assert r_list.status_code == 200
        results = r_list.get_json()["results"]
        result_ids = [r["id"] for r in results]
        assert auto_id in result_ids
        assert manual_id in result_ids

        # Verify shapes match exactly
        auto_entry = next(r for r in results if r["id"] == auto_id)
        manual_entry = next(r for r in results if r["id"] == manual_id)

        required_keys = {"id", "cause", "confidence", "evidence", "playbook", "status", "note"}
        assert required_keys.issubset(auto_entry.keys())
        assert required_keys.issubset(manual_entry.keys())

        # 4. Approve automatic result
        r_app = client.post(f"/rca/{auto_id}/approve", json={"note": "Approved auto RCA"})
        assert r_app.status_code == 200
        assert r_app.get_json()["status"] == "approved"

        # 5. Reject manual result
        r_rej = client.post(f"/rca/{manual_id}/reject", json={"note": "Rejected manual RCA"})
        assert r_rej.status_code == 200
        assert r_rej.get_json()["status"] == "rejected"
