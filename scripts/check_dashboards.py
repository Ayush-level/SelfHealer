#!/usr/bin/env python3
"""
Task 10.1 / 10.2 verification script.
Checks:
  1. All 4 dashboards are pre-loaded in Grafana (10.1 test)
  2. spanmetrics (duration_milliseconds, calls_total) are present in Prometheus (10.2)
  3. otelcol_* internal metrics are present in Prometheus (10.2)
"""
import sys
import time
import urllib.request
import urllib.error
import json
import base64

GRAFANA = "http://localhost:3000"
PROMETHEUS_CONTAINER = "selfhealer-prometheus-1"
GRAFANA_USER = "admin"
GRAFANA_PASS = "changeme"

EXPECTED_DASHBOARDS = {
    "Demo Dashboard",
    "Spanmetrics Demo Dashboard",
    "OpenTelemetry Collector",
    "Opentelemetry Collector Data Flow",
}

def grafana_get(path):
    creds = base64.b64encode(f"{GRAFANA_USER}:{GRAFANA_PASS}".encode()).decode()
    req = urllib.request.Request(
        GRAFANA + path,
        headers={"Authorization": f"Basic {creds}"}
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def prom_query(expr):
    """Query Prometheus via docker exec since port 9090 is not published to host by default."""
    import subprocess
    url = f"http://localhost:9090/api/v1/query?query={urllib.request.quote(expr)}"
    result = subprocess.run(
        ["docker", "exec", PROMETHEUS_CONTAINER, "wget", "-qO-", url],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        raise RuntimeError(f"docker exec wget failed: {result.stderr.strip()}")
    return json.loads(result.stdout)

def check_dashboards():
    print("\n=== Task 10.1: Grafana dashboards pre-loaded ===")
    data = grafana_get("/api/search?type=dash-db")
    found = {d["title"] for d in data}
    print(f"Dashboards found ({len(found)}): {sorted(found)}")
    missing = EXPECTED_DASHBOARDS - found
    if missing:
        print(f"FAIL — missing: {missing}")
        return False
    print("PASS — all 4 dashboards pre-loaded with zero manual import")
    return True

def check_prometheus_metrics(retries=8, wait=20):
    print("\n=== Task 10.2: Prometheus metrics non-empty ===")
    checks = {
        "spanmetrics calls_total":       'calls_total',
        "spanmetrics duration_ms_count": 'duration_milliseconds_count',
        "otelcol receiver spans":        'otelcol_receiver_accepted_spans_total',
        "otelcol process uptime":        'otelcol_process_uptime_seconds_total',
    }
    results = {}
    for attempt in range(retries):
        all_ok = True
        for label, metric in checks.items():
            try:
                r = prom_query(metric)
                count = len(r["data"]["result"])
                results[label] = count
                if count == 0:
                    all_ok = False
            except Exception as e:
                results[label] = f"error: {e}"
                all_ok = False
        if all_ok:
            break
        if attempt < retries - 1:
            print(f"  Attempt {attempt+1}: not all metrics present yet, waiting {wait}s...")
            time.sleep(wait)
    for label, count in results.items():
        status = "OK" if isinstance(count, int) and count > 0 else "MISSING"
        print(f"  [{status}] {label}: {count} series")
    all_present = all(isinstance(v, int) and v > 0 for v in results.values())
    if all_present:
        print("PASS — all panels have non-empty metric data")
    else:
        print("FAIL — some metrics missing (see above)")
    return all_present

def main():
    ok1 = check_dashboards()
    ok2 = check_prometheus_metrics()
    sys.exit(0 if (ok1 and ok2) else 1)

if __name__ == "__main__":
    main()
