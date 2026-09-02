#!/usr/bin/env python3
"""Task 11.1 — End-to-end smoke test (full demo stack).

Brings up the complete demo stack — Mode A (Prometheus + ClickHouse),
Grafana, SigNoz, OTel Demo services + load generator — confirms every
component is reachable and healthy, verifies the load generator is
producing real telemetry, runs a manual RCA trigger via /api/rca/trigger,
and approves the result.  Exits 0 with no manual intervention.

Sequence
--------
 1. docker compose up (Mode A + demo override + SigNoz) — idempotent
 2. npm run build inside frontend/ — confirm SPA bundles cleanly
 3. Wait for ClickHouse /ping
 4. Wait for Grafana /api/health
 5. Wait for SigNoz /api/v1/health
 6. Wait for OTel Collector health_check extension (:13133)
 7. Start the Flask proxy subprocess (port 5100 to avoid conflicts)
 8. Wait for proxy GET /health → {"status": "healthy"}
 9. Wait for load generator: otel_traces row count ≥ 50
10. Wait for spanmetrics: calls_total appears in Prometheus (Mode A)
11. Verify Grafana dashboards: 4 provisioned dashboards pre-loaded
12. Verify SigNoz has traces in signoz_traces.signoz_index_v3
13. POST /api/rca/trigger → pending result, all four RCA fields present
14. POST /api/rca/<id>/approve → status transitions to "approved"
15. GET  /api/rca/results → result appears in list with status="approved"

Exit codes
----------
0  all 15 steps passed
1  any step failed

Usage
-----
    python scripts/e2e_smoke_test.py [--skip-compose] [--skip-build]
                                     [--proxy-port 5100] [--timeout 180]
"""

import argparse
import base64
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
# Paths and constants
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"

COMPOSE_BASE       = str(REPO_ROOT / "docker-compose.yml")
COMPOSE_DEMO       = str(REPO_ROOT / "docker-compose.otel-demo-override.yml")
COMPOSE_SIGNOZ     = str(REPO_ROOT / "docker-compose.signoz.yml")
COMPOSE_PROM_UI    = str(REPO_ROOT / "docker-compose.prometheus-ui.yml")

CLICKHOUSE_HTTP    = "http://localhost:8123"
GRAFANA_URL        = "http://localhost:3000"
SIGNOZ_URL         = "http://localhost:8080"
COLLECTOR_HEALTH   = "http://localhost:13133"

# Read Grafana creds from .env (never hardcode)
_GRAFANA_USER      = os.getenv("GF_SECURITY_ADMIN_USER", "admin")
_GRAFANA_PASS      = os.getenv("GF_SECURITY_ADMIN_PASSWORD", "changeme")

EXPECTED_DASHBOARDS = {
    "Demo Dashboard",
    "Spanmetrics Demo Dashboard",
    "OpenTelemetry Collector",
    "Opentelemetry Collector Data Flow",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    print(f"[e2e] {msg}", flush=True)


def _fail(step: str, reason: str) -> None:
    print(f"\n[e2e] FAIL — Step {step}: {reason}", file=sys.stderr, flush=True)
    sys.exit(1)


def _wait_for(label: str, check_fn, timeout: float, interval: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        try:
            if check_fn():
                _log(f"  ✓ {label}")
                return
        except Exception:
            pass
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(interval, remaining))
    _fail(label, f"timed out after {timeout:.0f}s ({attempt} attempts)")


def _grafana_get(path: str) -> Any:
    creds = base64.b64encode(f"{_GRAFANA_USER}:{_GRAFANA_PASS}".encode()).decode()
    r = requests.get(
        f"{GRAFANA_URL}{path}",
        headers={"Authorization": f"Basic {creds}"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def _ch_query(sql: str) -> list:
    r = requests.post(
        f"{CLICKHOUSE_HTTP}/",
        data=f"{sql} FORMAT JSON".encode(),
        headers={"Content-Type": "text/plain; charset=utf-8"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json().get("data", [])


def _post(url: str, payload: Optional[Dict] = None, **kwargs) -> requests.Response:
    return requests.post(url, json=payload or {}, timeout=30, **kwargs)


def _get(url: str, **kwargs) -> requests.Response:
    return requests.get(url, timeout=10, **kwargs)

# ---------------------------------------------------------------------------
# Step 1 — docker compose up (full stack)
# ---------------------------------------------------------------------------

def step_compose_up() -> None:
    _log("Step 1: docker compose up -d (Mode A + demo + SigNoz + Prometheus UI) …")
    cmd = [
        "docker", "compose",
        "-f", COMPOSE_BASE,
        "-f", COMPOSE_DEMO,
        "-f", COMPOSE_SIGNOZ,
        "-f", COMPOSE_PROM_UI,
        "--profile", "mode-a",
        "up", "-d",
    ]
    r = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    if r.returncode != 0:
        _fail("1", f"docker compose up failed:\n{r.stderr}")
    _log("  ✓ docker compose up completed")


# ---------------------------------------------------------------------------
# Step 2 — npm run build (frontend SPA)
# ---------------------------------------------------------------------------

def step_frontend_build() -> None:
    _log("Step 2: npm run build (React SPA) …")
    if not (FRONTEND_DIR / "package.json").exists():
        _fail("2", f"frontend/package.json not found at {FRONTEND_DIR}")

    # Install if node_modules missing
    if not (FRONTEND_DIR / "node_modules").exists():
        _log("  node_modules absent — running npm install …")
        r = subprocess.run(
            ["npm", "install", "--prefer-offline"],
            cwd=str(FRONTEND_DIR),
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            _fail("2", f"npm install failed:\n{r.stderr}")

    r = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(FRONTEND_DIR),
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        _fail("2", f"npm run build failed:\n{r.stderr}\n{r.stdout}")

    dist_dir = FRONTEND_DIR / "dist"
    if not dist_dir.exists() or not list(dist_dir.glob("**/*.js")):
        _fail("2", "Build produced no JS artefacts in frontend/dist/")

    _log(f"  ✓ npm run build succeeded — dist artefacts at {dist_dir}")


# ---------------------------------------------------------------------------
# Steps 3-6 — infrastructure readiness
# ---------------------------------------------------------------------------

def step_wait_clickhouse(timeout: float) -> None:
    _log("Step 3: waiting for ClickHouse …")
    _wait_for(
        "ClickHouse /ping → Ok.",
        lambda: requests.get(f"{CLICKHOUSE_HTTP}/ping", timeout=5).text.strip() == "Ok.",
        timeout,
    )


def step_wait_grafana(timeout: float) -> None:
    _log("Step 4: waiting for Grafana …")
    _wait_for(
        "Grafana /api/health → ok",
        lambda: requests.get(f"{GRAFANA_URL}/api/health", timeout=5).json().get("database") == "ok",
        timeout,
    )


def step_wait_signoz(timeout: float) -> None:
    _log("Step 5: waiting for SigNoz …")
    _wait_for(
        "SigNoz /api/v1/health → 200",
        lambda: requests.get(f"{SIGNOZ_URL}/api/v1/health", timeout=5).status_code == 200,
        timeout,
    )


def step_wait_collector(timeout: float) -> None:
    _log("Step 6: waiting for OTel Collector health_check …")
    _wait_for(
        "Collector :13133 → 200",
        lambda: requests.get(COLLECTOR_HEALTH, timeout=5).status_code == 200,
        timeout,
    )


# ---------------------------------------------------------------------------
# Steps 7-8 — proxy
# ---------------------------------------------------------------------------

def step_start_proxy(port: int) -> subprocess.Popen:
    _log(f"Step 7: starting Flask proxy on :{port} …")
    env = {
        **os.environ,
        "PROXY_PORT": str(port),
        "FLASK_APP": "proxy.app",
        # Prometheus port is published via docker-compose.prometheus-ui.yml
        "PROMETHEUS_URL": "http://localhost:9090",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "flask", "run", "--host", "0.0.0.0", "--port", str(port)],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc


def step_wait_proxy(port: int, timeout: float) -> str:
    base = f"http://localhost:{port}"
    _log(f"Step 8: waiting for proxy {base}/health …")
    _wait_for(
        "proxy /health → healthy",
        lambda: _get(f"{base}/health").json().get("status") == "healthy",
        timeout,
        interval=1.0,
    )
    return base


# ---------------------------------------------------------------------------
# Step 9 — load generator producing real traces
# ---------------------------------------------------------------------------

def step_wait_telemetry(timeout: float) -> None:
    _log("Step 9: waiting for load generator traffic (otel_traces ≥ 50) …")

    def _has_traffic() -> bool:
        rows = _ch_query("SELECT count() AS n FROM otel_traces")
        return rows and int(rows[0]["n"]) >= 50

    _wait_for("otel_traces has ≥ 50 rows", _has_traffic, timeout)


# ---------------------------------------------------------------------------
# Step 10 — spanmetrics in Prometheus
# ---------------------------------------------------------------------------

def step_wait_spanmetrics(timeout: float) -> None:
    _log("Step 10: waiting for spanmetrics in Prometheus (calls_total) …")

    def _has_spanmetrics() -> bool:
        sql = "SELECT count() AS n FROM otel_traces WHERE ServiceName != ''"
        rows = _ch_query(sql)
        if not rows or int(rows[0]["n"]) == 0:
            return False
        # Query Prometheus via docker exec (port not published by default)
        result = subprocess.run(
            [
                "docker", "exec", "selfhealer-prometheus-1",
                "wget", "-qO-",
                "http://localhost:9090/api/v1/query?query=calls_total",
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return False
        data = json.loads(result.stdout)
        return len(data.get("data", {}).get("result", [])) > 0

    _wait_for("calls_total present in Prometheus", _has_spanmetrics, timeout)


# ---------------------------------------------------------------------------
# Step 11 — Grafana dashboards pre-loaded
# ---------------------------------------------------------------------------

def step_verify_grafana_dashboards() -> None:
    _log("Step 11: verifying 4 Grafana dashboards pre-loaded …")
    try:
        dashboards = _grafana_get("/api/search?type=dash-db")
    except Exception as e:
        _fail("11", f"Grafana API error: {e}")

    found = {d["title"] for d in dashboards}
    missing = EXPECTED_DASHBOARDS - found
    if missing:
        _fail("11", f"Dashboards missing from Grafana: {missing}")
    _log(f"  ✓ All {len(EXPECTED_DASHBOARDS)} dashboards pre-loaded: {sorted(found)}")


# ---------------------------------------------------------------------------
# Step 12 — SigNoz has traces
# ---------------------------------------------------------------------------

def step_verify_signoz_traces(timeout: float) -> None:
    _log("Step 12: verifying SigNoz has traces in signoz_traces.signoz_index_v3 …")

    def _signoz_has_data() -> bool:
        rows = _ch_query(
            "SELECT count() AS n FROM signoz_traces.signoz_index_v3"
        )
        return rows and int(rows[0]["n"]) > 0

    _wait_for("signoz_traces.signoz_index_v3 has ≥ 1 row", _signoz_has_data, timeout)


# ---------------------------------------------------------------------------
# Step 13 — POST /api/rca/trigger
# ---------------------------------------------------------------------------

def step_rca_trigger(base: str) -> str:
    _log("Step 13: POST /api/rca/trigger …")
    end_time = time.time()
    start_time = end_time - 300  # 5-minute window of real traffic

    r = _post(f"{base}/api/rca/trigger", {
        "start_time": start_time,
        "end_time": end_time,
    })
    if r.status_code != 200:
        _fail("13", f"/api/rca/trigger returned {r.status_code}: {r.text[:400]}")

    data = r.json()
    for key in ("id", "cause", "confidence", "evidence", "playbook", "status"):
        if key not in data:
            _fail("13", f"/api/rca/trigger response missing key: '{key}'")

    if data["status"] != "pending":
        _fail("13", f"Expected status='pending', got '{data['status']}'")
    if not data["cause"]:
        _fail("13", "RCA 'cause' field is empty")
    if not isinstance(data["evidence"], list) or len(data["evidence"]) == 0:
        _fail("13", "RCA 'evidence' is empty")
    if not isinstance(data["playbook"], list) or len(data["playbook"]) == 0:
        _fail("13", "RCA 'playbook' is empty")
    if not (0.0 <= float(data["confidence"]) <= 1.0):
        _fail("13", f"RCA 'confidence' out of range: {data['confidence']}")

    rca_id = data["id"]
    _log(
        f"  ✓ /api/rca/trigger OK — id={rca_id} "
        f"confidence={data['confidence']:.2f} "
        f"cause={data['cause'][:70]!r}"
    )
    return rca_id


# ---------------------------------------------------------------------------
# Step 14 — POST /api/rca/<id>/approve
# ---------------------------------------------------------------------------

def step_approve(base: str, rca_id: str) -> None:
    _log(f"Step 14: POST /api/rca/{rca_id}/approve …")
    r = _post(
        f"{base}/api/rca/{rca_id}/approve",
        {"note": "e2e smoke-test approval"},
    )
    if r.status_code != 200:
        _fail("14", f"/api/rca/{rca_id}/approve returned {r.status_code}: {r.text}")

    data = r.json()
    if data.get("status") != "approved":
        _fail("14", f"Expected status='approved', got '{data.get('status')}'")
    _log(f"  ✓ approved — status={data['status']} note={data.get('note')!r}")


# ---------------------------------------------------------------------------
# Step 15 — GET /api/rca/results contains the approved entry
# ---------------------------------------------------------------------------

def step_verify_results(base: str, rca_id: str) -> None:
    _log("Step 15: GET /api/rca/results — approved entry present …")
    r = _get(f"{base}/api/rca/results")
    if r.status_code != 200:
        _fail("15", f"/api/rca/results returned {r.status_code}: {r.text}")

    results = r.json().get("results", [])
    match = next((x for x in results if x.get("id") == rca_id), None)
    if match is None:
        _fail("15", f"RCA id={rca_id} not found in /api/rca/results")
    if match.get("status") != "approved":
        _fail("15", f"Expected approved, got '{match.get('status')}'")

    _log(f"  ✓ /api/rca/results contains id={rca_id} status=approved")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Task 11.1 — Full-stack end-to-end smoke test"
    )
    parser.add_argument("--skip-compose", action="store_true",
                        help="Skip docker compose up (stack already running)")
    parser.add_argument("--skip-build", action="store_true",
                        help="Skip npm run build (dist/ already present)")
    parser.add_argument("--proxy-port", type=int, default=5100,
                        help="Port to run Flask proxy on (default 5100, avoids conflicts)")
    parser.add_argument("--timeout", type=float, default=180,
                        help="Max seconds per readiness wait (default 180)")
    args = parser.parse_args()

    _log("=" * 64)
    _log("Self-Healer  —  Task 11.1 full-stack end-to-end smoke test")
    _log("=" * 64)

    proxy_proc: Optional[subprocess.Popen] = None

    try:
        # ── Infrastructure ──────────────────────────────────────────────
        if not args.skip_compose:
            step_compose_up()
        else:
            _log("Step 1: skipped (--skip-compose)")

        if not args.skip_build:
            step_frontend_build()
        else:
            _log("Step 2: skipped (--skip-build)")

        step_wait_clickhouse(args.timeout)
        step_wait_grafana(args.timeout)
        step_wait_signoz(args.timeout)
        step_wait_collector(args.timeout)

        # ── Proxy ───────────────────────────────────────────────────────
        proxy_proc = step_start_proxy(args.proxy_port)
        base = step_wait_proxy(args.proxy_port, timeout=30)

        # ── Telemetry pipeline ──────────────────────────────────────────
        step_wait_telemetry(args.timeout)
        step_wait_spanmetrics(args.timeout)

        # ── Observability stack ─────────────────────────────────────────
        step_verify_grafana_dashboards()
        step_verify_signoz_traces(args.timeout)

        # ── RCA pipeline ────────────────────────────────────────────────
        rca_id = step_rca_trigger(base)
        step_approve(base, rca_id)
        step_verify_results(base, rca_id)

    finally:
        if proxy_proc is not None and proxy_proc.poll() is None:
            proxy_proc.terminate()
            proxy_proc.wait(timeout=5)

    _log("=" * 64)
    _log("ALL 15 STEPS PASSED — exit 0")
    _log("=" * 64)
    sys.exit(0)


if __name__ == "__main__":
    main()
