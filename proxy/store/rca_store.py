"""In-memory store for RCA suggestions and their approval state.

Scoped to the current phase: single-process, no persistence across restarts.
Each RCA result lives here from the moment POST /rca produces it until the
process exits.  Thread-safe via a simple Lock — sufficient for the demo
workload (no high-concurrency requirement this phase).

States
------
pending   — produced by POST /rca, awaiting human decision
approved  — explicitly accepted via POST /rca/<id>/approve
rejected  — explicitly rejected via POST /rca/<id>/reject

No auto-execution happens on approval: ARCHITECTURE.md §Human Review &
Approval — every RCA suggestion requires explicit approval before anything
is considered actioned.
"""

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# Valid status values — kept as module-level constants so routes and tests
# can import them without hard-coding strings.
STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"

ALL_STATUSES = (STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED)


@dataclass
class StoredRCA:
    """An RCA result plus its approval metadata."""

    id: str
    cause: str
    confidence: float
    evidence: List[str]
    playbook: List[str]
    status: str = STATUS_PENDING
    # Free-form note supplied at approve/reject time (optional)
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "cause": self.cause,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "playbook": self.playbook,
            "status": self.status,
            "note": self.note,
        }

    @classmethod
    def from_rca_result(cls, rca_result: Any) -> "StoredRCA":
        """Construct from an RCAResult dataclass instance."""
        return cls(
            id=rca_result.id,
            cause=rca_result.cause,
            confidence=rca_result.confidence,
            evidence=list(rca_result.evidence),
            playbook=list(rca_result.playbook),
        )


class RCAStore:
    """Thread-safe in-memory store for RCA suggestions.

    Public API
    ----------
    save(rca_result)            -> StoredRCA  (status=pending)
    get(id)                     -> StoredRCA | None
    approve(id, note="")        -> StoredRCA | None
    reject(id, note="")         -> StoredRCA | None
    list_all(status=None)       -> List[StoredRCA]
    """

    def __init__(self) -> None:
        self._store: Dict[str, StoredRCA] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def save(self, rca_result: Any) -> StoredRCA:
        """Persist a new RCAResult as pending.  Returns the StoredRCA."""
        entry = StoredRCA.from_rca_result(rca_result)
        with self._lock:
            self._store[entry.id] = entry
        return entry

    def approve(self, rca_id: str, note: str = "") -> Optional[StoredRCA]:
        """Transition an entry to approved.  Returns None if id not found."""
        with self._lock:
            entry = self._store.get(rca_id)
            if entry is None:
                return None
            entry.status = STATUS_APPROVED
            entry.note = note
            return entry

    def reject(self, rca_id: str, note: str = "") -> Optional[StoredRCA]:
        """Transition an entry to rejected.  Returns None if id not found."""
        with self._lock:
            entry = self._store.get(rca_id)
            if entry is None:
                return None
            entry.status = STATUS_REJECTED
            entry.note = note
            return entry

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get(self, rca_id: str) -> Optional[StoredRCA]:
        """Return the stored entry for the given id, or None."""
        with self._lock:
            return self._store.get(rca_id)

    def list_all(self, status: Optional[str] = None) -> List[StoredRCA]:
        """Return all entries, optionally filtered by status."""
        with self._lock:
            entries = list(self._store.values())
        if status is not None:
            entries = [e for e in entries if e.status == status]
        return entries

    def __len__(self) -> int:
        with self._lock:
            return len(self._store)
