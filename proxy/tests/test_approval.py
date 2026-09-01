"""Tests for Phase 6 — RCA approval flow.

Coverage:
  Unit  — RCAStore (save, get, approve, reject, list_all, 404-equiv None returns)
  Unit  — StoredRCA.to_dict shape
  Integ — POST /rca/<id>/approve changes status to "approved"
  Integ — POST /rca/<id>/reject  changes status to "rejected"
  Integ — GET  /rca/<id>         retrieves current state
  Integ — 404 for unknown ids
  Integ — note field stored and returned
  Integ — POST /rca now returns status="pending" + "note" fields
  Integ — full lifecycle: create → approve/reject → verify via GET
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from proxy.app import create_app
from proxy.rca.llm_client import RCAResult
from proxy.store.rca_store import (
    RCAStore,
    StoredRCA,
    STATUS_PENDING,
    STATUS_APPROVED,
    STATUS_REJECTED,
)


# ---------------------------------------------------------------------------
# Fixtures
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


@pytest.fixture
def store():
    """A fresh RCAStore for unit tests."""
    return RCAStore()


def _make_rca_result(cause: str = "Test cause") -> RCAResult:
    return RCAResult(
        cause=cause,
        confidence=0.88,
        evidence=["service/op: error msg"],
        playbook=["Step 1", "Step 2"],
    )


# ---------------------------------------------------------------------------
# RCAStore unit tests
# ---------------------------------------------------------------------------

class TestRCAStore:

    def test_save_returns_stored_rca_with_pending_status(self, store):
        result = _make_rca_result()
        stored = store.save(result)
        assert isinstance(stored, StoredRCA)
        assert stored.status == STATUS_PENDING
        assert stored.id == result.id

    def test_save_preserves_all_fields(self, store):
        result = _make_rca_result("Cache eviction fault")
        stored = store.save(result)
        assert stored.cause == "Cache eviction fault"
        assert stored.confidence == 0.88
        assert stored.evidence == ["service/op: error msg"]
        assert stored.playbook == ["Step 1", "Step 2"]

    def test_get_returns_saved_entry(self, store):
        result = _make_rca_result()
        store.save(result)
        fetched = store.get(result.id)
        assert fetched is not None
        assert fetched.id == result.id

    def test_get_returns_none_for_unknown_id(self, store):
        assert store.get("nonexistent-uuid") is None

    def test_approve_changes_status(self, store):
        result = _make_rca_result()
        store.save(result)
        updated = store.approve(result.id)
        assert updated.status == STATUS_APPROVED

    def test_approve_stores_note(self, store):
        result = _make_rca_result()
        store.save(result)
        updated = store.approve(result.id, note="Confirmed by SRE on-call")
        assert updated.note == "Confirmed by SRE on-call"

    def test_reject_changes_status(self, store):
        result = _make_rca_result()
        store.save(result)
        updated = store.reject(result.id)
        assert updated.status == STATUS_REJECTED

    def test_reject_stores_note(self, store):
        result = _make_rca_result()
        store.save(result)
        updated = store.reject(result.id, note="False positive — noise spike")
        assert updated.note == "False positive — noise spike"

    def test_approve_returns_none_for_unknown_id(self, store):
        assert store.approve("no-such-id") is None

    def test_reject_returns_none_for_unknown_id(self, store):
        assert store.reject("no-such-id") is None

    def test_approve_mutates_same_object_in_store(self, store):
        result = _make_rca_result()
        store.save(result)
        store.approve(result.id, note="ok")
        # get() must reflect the change
        assert store.get(result.id).status == STATUS_APPROVED

    def test_reject_mutates_same_object_in_store(self, store):
        result = _make_rca_result()
        store.save(result)
        store.reject(result.id, note="nope")
        assert store.get(result.id).status == STATUS_REJECTED

    def test_list_all_returns_all_entries(self, store):
        r1 = _make_rca_result("Cause A")
        r2 = _make_rca_result("Cause B")
        store.save(r1)
        store.save(r2)
        all_entries = store.list_all()
        assert len(all_entries) == 2

    def test_list_all_filtered_by_status(self, store):
        r1 = _make_rca_result("Cause A")
        r2 = _make_rca_result("Cause B")
        r3 = _make_rca_result("Cause C")
        store.save(r1)
        store.save(r2)
        store.save(r3)
        store.approve(r1.id)
        store.reject(r2.id)
        assert len(store.list_all(STATUS_PENDING)) == 1
        assert len(store.list_all(STATUS_APPROVED)) == 1
        assert len(store.list_all(STATUS_REJECTED)) == 1

    def test_len(self, store):
        assert len(store) == 0
        store.save(_make_rca_result())
        assert len(store) == 1


class TestStoredRCAToDict:

    def test_to_dict_has_all_required_keys(self, store):
        stored = store.save(_make_rca_result())
        d = stored.to_dict()
        for key in ("id", "cause", "confidence", "evidence", "playbook", "status", "note"):
            assert key in d, f"Missing key: {key}"

    def test_to_dict_status_is_pending_initially(self, store):
        stored = store.save(_make_rca_result())
        assert stored.to_dict()["status"] == STATUS_PENDING

    def test_to_dict_note_is_empty_initially(self, store):
        stored = store.save(_make_rca_result())
        assert stored.to_dict()["note"] == ""


# ---------------------------------------------------------------------------
# Route integration tests — approval endpoints
# ---------------------------------------------------------------------------

def _seed_rca(client) -> dict:
    """Create one RCA via POST /rca (with mocked engine + LLM) and return its JSON."""
    result = _make_rca_result("Payment processor timeout")

    with patch("proxy.routes.rca.CorrelationEngine") as MockEngine, \
         patch("proxy.routes.rca.create_llm_client") as MockFactory:

        mock_engine = MagicMock()
        mock_engine.correlate.return_value = MagicMock(
            to_dict=MagicMock(return_value={
                "time_window": {"start": 1_700_000_000.0, "end": 1_700_000_060.0},
                "services_impacted": ["paymentservice"],
                "total_traces": 5,
                "error_traces": 4,
                "metrics": [],
                "correlated_traces": [],
            })
        )
        MockEngine.return_value = mock_engine

        mock_llm = MagicMock()
        mock_llm.generate.return_value = result
        MockFactory.return_value = mock_llm

        resp = client.post(
            "/rca",
            data=json.dumps({"start_time": 1_700_000_000.0, "end_time": 1_700_000_060.0}),
            content_type="application/json",
        )

    assert resp.status_code == 200
    return resp.get_json()


class TestApprovalRoutes:

    def test_post_rca_returns_status_pending(self, client):
        data = _seed_rca(client)
        assert data["status"] == STATUS_PENDING
        assert data["note"] == ""
        assert "id" in data

    def test_approve_returns_200_and_approved_status(self, client):
        seeded = _seed_rca(client)
        rca_id = seeded["id"]

        resp = client.post(f"/rca/{rca_id}/approve", content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == STATUS_APPROVED
        assert data["id"] == rca_id

    def test_reject_returns_200_and_rejected_status(self, client):
        seeded = _seed_rca(client)
        rca_id = seeded["id"]

        resp = client.post(f"/rca/{rca_id}/reject", content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == STATUS_REJECTED
        assert data["id"] == rca_id

    def test_approve_stores_note(self, client):
        seeded = _seed_rca(client)
        rca_id = seeded["id"]

        resp = client.post(
            f"/rca/{rca_id}/approve",
            data=json.dumps({"note": "Verified by on-call SRE"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["note"] == "Verified by on-call SRE"

    def test_reject_stores_note(self, client):
        seeded = _seed_rca(client)
        rca_id = seeded["id"]

        resp = client.post(
            f"/rca/{rca_id}/reject",
            data=json.dumps({"note": "False positive — scheduled job noise"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["note"] == "False positive — scheduled job noise"

    def test_get_rca_returns_current_state(self, client):
        seeded = _seed_rca(client)
        rca_id = seeded["id"]

        resp = client.get(f"/rca/{rca_id}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == rca_id
        assert data["status"] == STATUS_PENDING

    def test_get_rca_reflects_approval(self, client):
        seeded = _seed_rca(client)
        rca_id = seeded["id"]

        client.post(f"/rca/{rca_id}/approve", content_type="application/json")

        resp = client.get(f"/rca/{rca_id}")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == STATUS_APPROVED

    def test_get_rca_reflects_rejection(self, client):
        seeded = _seed_rca(client)
        rca_id = seeded["id"]

        client.post(f"/rca/{rca_id}/reject", content_type="application/json")

        resp = client.get(f"/rca/{rca_id}")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == STATUS_REJECTED

    def test_approve_unknown_id_returns_404(self, client):
        resp = client.post("/rca/no-such-id/approve", content_type="application/json")
        assert resp.status_code == 404
        assert "error" in resp.get_json()

    def test_reject_unknown_id_returns_404(self, client):
        resp = client.post("/rca/no-such-id/reject", content_type="application/json")
        assert resp.status_code == 404
        assert "error" in resp.get_json()

    def test_get_unknown_id_returns_404(self, client):
        resp = client.get("/rca/no-such-id")
        assert resp.status_code == 404
        assert "error" in resp.get_json()

    def test_full_lifecycle_create_approve_get(self, client):
        """End-to-end: create → approve → GET shows approved."""
        seeded = _seed_rca(client)
        rca_id = seeded["id"]

        # Initial state
        assert seeded["status"] == STATUS_PENDING

        # Approve
        approve_resp = client.post(
            f"/rca/{rca_id}/approve",
            data=json.dumps({"note": "All clear"}),
            content_type="application/json",
        )
        assert approve_resp.status_code == 200
        assert approve_resp.get_json()["status"] == STATUS_APPROVED

        # GET confirms persisted state
        get_resp = client.get(f"/rca/{rca_id}")
        assert get_resp.status_code == 200
        final = get_resp.get_json()
        assert final["status"] == STATUS_APPROVED
        assert final["note"] == "All clear"
        assert final["cause"] == "Payment processor timeout"

    def test_full_lifecycle_create_reject_get(self, client):
        """End-to-end: create → reject → GET shows rejected."""
        seeded = _seed_rca(client)
        rca_id = seeded["id"]

        client.post(
            f"/rca/{rca_id}/reject",
            data=json.dumps({"note": "Not reproducible"}),
            content_type="application/json",
        )
        get_resp = client.get(f"/rca/{rca_id}")
        final = get_resp.get_json()
        assert final["status"] == STATUS_REJECTED
        assert final["note"] == "Not reproducible"

    def test_approve_no_body_uses_empty_note(self, client):
        """approve with no JSON body still works — note defaults to ''."""
        seeded = _seed_rca(client)
        resp = client.post(f"/rca/{seeded['id']}/approve")
        assert resp.status_code == 200
        assert resp.get_json()["note"] == ""

    def test_reject_no_body_uses_empty_note(self, client):
        seeded = _seed_rca(client)
        resp = client.post(f"/rca/{seeded['id']}/reject")
        assert resp.status_code == 200
        assert resp.get_json()["note"] == ""
