#!/usr/bin/env python3
"""End-to-end smoke test — Task 7.1.

Sequence
--------
1.  Ensure the Docker Compose stack is up (idempotent `docker compose up -d`).
2.  Wait for ClickHouse to be reachable (HTTP ping).
3.  Start the Flask proxy in a subprocess (on port 5000).
4.  Wait for proxy /health to return 200.
5.  Wait for real telemetry to appear in ClickHouse otel_traces
    (load generator drives continuous traffic; we just need ≥1 row).
6.  POST /correlate — assert the response has the expected top-level shape.
7.  POST /rca      — assert the response contains id + all four RCA fields,
                     status="pending".
8.  POST /rca/<id>/approve — assert status transitions to "approved".
9.  GET  /rca/<id>          — assert persisted state is "approved".
10. Print a success banner and exit 0.

Exit codes
----------
0  all assertions passed
1  any step failed (error message printed to stderr)

Usage
-----
    python scripts/smoke_test.py [--proxy-port 5000] [--timeout 120]

The script is intentionally self-contained (stdlib + requests only) so it
can be run immediately after `pip install requests` with no other deps.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import requests
except ImportError:
    print("ERROR: 'requests' is required. Run: pip install requests", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
PROXY_BASE = "http://localhost:{port}"
CLICKHOUSE_HTTP = "http://localhost:8123"
COMPOSE_FILES = [
    str(REPO_ROOT / "docker-compose.yml"),
    str(REPO_ROOT / "docker-compose.otel-demo-override.yml"),
]
COMPOSE_PROFILE = "mode-a"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    print(f"[smoke] {msg}", flush=True)


def _fail(msg: str) -> None:
    print(f"[smoke] FAIL: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def _wait_for(
    label: str,
    check_fn,
    timeout: float,
    interval: float = 2.0,
) -> None:
    """Poll check_fn() until it returns True or timeout expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if check_fn():
                _log(f"✓ {label}")
                return
        except Exception:
            pass
        time.sleep(interval)
    _fail(f"Timed out waiting for: {label} (timeout={timeout}s)")


def _get(url: str, **kwargs) -> requests.Response:
    return requests.get(url, timeout=10, **kwargs)


def _post(url: str, payload: Optional[Dict[str, Any]] = None, **kwargs) -> requests.Response:
    return requests.post(url, json=payload or {}, timeout=30, **kwargs)


# ---------------------------------------------------------------------------
# Step 1 — bring up the stack
# ---------------------------------------------------------------------------

def step_compose_up() -> None:
    _log("Step 1: docker compose up -d (idempotent)")
    cmd = [
        "docker", "compose",
        "-f", COMPOSE_FILES[0],
        "-f", COMPOSE_FILES[1],
        "--profile", COMPOSE_PROFILE,
        "up", "-d",
    ]
    result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    if result.returncode != 0:
        _fail(f"docker compose up failed:\n{result.stderr}")
    _log("✓ docker compose up completed")


# ---------------------------------------------------------------------------
# Step 2 — wait for ClickHouse
# ---------------------------------------------------------------------------

def step_wait_clickhouse(timeout: float) -> None:
    _log("Step 2: waiting for ClickHouse HTTP API…")

    def _ch_ready() -> bool:
        r = requests.get(f"{CLICKHOUSE_HTTP}/ping", timeout=5)
        return r.status_code == 200 and r.text.strip() == "Ok."

    _wait_for("ClickHouse /ping → Ok.", _ch_ready, timeout)


# ---------------------------------------------------------------------------
# Step 3 — start the proxy
# ---------------------------------------------------------------------------

def step_start_proxy(port: int) -> subprocess.Popen:
    _log(f"Step 3: starting Flask proxy on port {port}…")
    env = {**os.environ, "PROXY_PORT": str(port), "FLASK_APP": "proxy.app"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "flask", "run", "--host", "0.0.0.0", "--port", str(port)],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc


# ---------------------------------------------------------------------------
# Step 4 — wait for proxy /health
# ---------------------------------------------------------------------------

def step_wait_proxy(port: int, timeout: float) -> str:
    base = PROXY_BASE.format(port=port)
    _log(f"Step 4: waiting for proxy {base}/health…")

    def _proxy_ready() -> bool:
        r = _get(f"{base}/health")
        return r.status_code == 200 and r.json().get("status") == "healthy"

    _wait_for("proxy /health → healthy", _proxy_ready, timeout, interval=1.0)
    return base


# ---------------------------------------------------------------------------
# Step 5 — wait for real telemetry in ClickHouse
# ---------------------------------------------------------------------------

def step_wait_telemetry(timeout: float) -> None:
    _log("Step 5: waiting for trace data in ClickHouse otel_traces…")

    def _has_traces() -> bool:
        query = "SELECT count() FROM otel_traces"
        r = requests.post(
            f"{CLICKHOUSE_HTTP}/",
            data=f"{query} FORMAT JSON".encode(),
            timeout=10,
        )
        r.raise_for_status()
        count = int(r.json()["data"][0]["count()"])
        return count > 0

    _wait_for("otel_traces has ≥1 row", _has_traces, timeout)


# ---------------------------------------------------------------------------
# Step 6 — POST /correlate
# ---------------------------------------------------------------------------

def step_correlate(base: str) -> None:
    _log("Step 6: POST /correlate…")
    end_time = time.time()
    start_time = end_time - 120  # last 2 minutes of real traffic

    r = _post(f"{base}/correlate", {
        "start_time": start_time,
        "end_time": end_time,
    })
    if r.status_code != 200:
        _fail(f"/correlate returned {r.status_code}: {r.text}")

    data = r.json()
    for key in ("time_window", "services_impacted", "total_traces",
                "error_traces", "metrics", "correlated_traces"):
        if key not in data:
            _fail(f"/correlate response missing key: '{key}'")

    _log(
        f"✓ /correlate OK — {data['total_traces']} traces, "
        f"{data['error_traces']} errors, "
        f"impacted: {data['services_impacted']}"
    )


# ---------------------------------------------------------------------------
# Step 7 — POST /rca
# ---------------------------------------------------------------------------

def step_rca(base: str) -> str:
    _log("Step 7: POST /rca…")
    end_time = time.time()
    start_time = end_time - 120

    r = _post(f"{base}/rca", {
        "start_time": start_time,
        "end_time": end_time,
    })
    if r.status_code != 200:
        _fail(f"/rca returned {r.status_code}: {r.text}")

    data = r.json()
    for key in ("id", "cause", "confidence", "evidence", "playbook", "status", "note"):
        if key not in data:
            _fail(f"/rca response missing key: '{key}'")

    if data["status"] != "pending":
        _fail(f"Expected status='pending', got '{data['status']}'")
    if not data["cause"]:
        _fail("RCA 'cause' is empty")
    if not data["evidence"]:
        _fail("RCA 'evidence' is empty")
    if not (0.0 <= data["confidence"] <= 1.0):
        _fail(f"RCA 'confidence' out of range: {data['confidence']}")

    rca_id = data["id"]
    _log(
        f"✓ /rca OK — id={rca_id} status={data['status']} "
        f"confidence={data['confidence']:.2f} cause={data['cause'][:60]!r}"
    )
    return rca_id


# ---------------------------------------------------------------------------
# Step 8 — POST /rca/<id>/approve
# ---------------------------------------------------------------------------

def step_approve(base: str, rca_id: str) -> None:
    _log(f"Step 8: POST /rca/{rca_id}/approve…")
    r = _post(
        f"{base}/rca/{rca_id}/approve",
        {"note": "smoke-test approval"},
    )
    if r.status_code != 200:
        _fail(f"/rca/{rca_id}/approve returned {r.status_code}: {r.text}")

    data = r.json()
    if data.get("status") != "approved":
        _fail(f"Expected status='approved', got '{data.get('status')}'")

    _log(f"✓ /rca/{rca_id}/approve OK — status={data['status']}")


# ---------------------------------------------------------------------------
# Step 9 — GET /rca/<id> confirms persisted state
# ---------------------------------------------------------------------------

def step_verify_approval(base: str, rca_id: str) -> None:
    _log(f"Step 9: GET /rca/{rca_id} (verify persisted state)…")
    r = _get(f"{base}/rca/{rca_id}")
    if r.status_code != 200:
        _fail(f"GET /rca/{rca_id} returned {r.status_code}: {r.text}")

    data = r.json()
    if data.get("status") != "approved":
        _fail(f"Expected persisted status='approved', got '{data.get('status')}'")
    if data.get("note") != "smoke-test approval":
        _fail(f"Unexpected note: '{data.get('note')}'")

    _log(f"✓ GET /rca/{rca_id} OK — status={data['status']} note={data['note']!r}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Self-Healer end-to-end smoke test")
    parser.add_argument("--proxy-port", type=int, default=5000,
                        help="Port to run the Flask proxy on (default: 5000)")
    parser.add_argument("--timeout", type=float, default=120,
                        help="Max seconds to wait for each readiness check (default: 120)")
    parser.add_argument("--skip-compose", action="store_true",
                        help="Skip docker compose up (use when stack is already running)")
    args = parser.parse_args()

    _log("=" * 60)
    _log("Self-Healer end-to-end smoke test")
    _log("=" * 60)

    proxy_proc: Optional[subprocess.Popen] = None

    try:
        # 1. Stack up
        if not args.skip_compose:
            step_compose_up()
        else:
            _log("Step 1: skipped (--skip-compose)")

        # 2. ClickHouse ready
        step_wait_clickhouse(args.timeout)

        # 3+4. Proxy
        proxy_proc = step_start_proxy(args.proxy_port)
        base = step_wait_proxy(args.proxy_port, timeout=30)

        # 5. Telemetry
        step_wait_telemetry(args.timeout)

        # 6–9. API pipeline
        step_correlate(base)
        rca_id = step_rca(base)
        step_approve(base, rca_id)
        step_verify_approval(base, rca_id)

    finally:
        if proxy_proc is not None and proxy_proc.poll() is None:
            proxy_proc.terminate()
            proxy_proc.wait(timeout=5)

    _log("=" * 60)
    _log("ALL STEPS PASSED — smoke test exit 0")
    _log("=" * 60)
    sys.exit(0)


if __name__ == "__main__":
    main()
