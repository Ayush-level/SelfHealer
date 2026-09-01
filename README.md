# Self-Healing AI Operations Controller

A self-hosted telemetry pipeline that collects metrics, logs, and traces,
correlates them automatically, and uses an LLM to suggest a root cause —
with a human approving before anything is acted on.

## Quick Start

### Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin) — v2.20+
- Python 3.11+ with `pip`
- Git (for submodule init)

### 1 — Clone and configure

```bash
git clone <repo-url> self-healer
cd self-healer
git submodule update --init --recursive   # pulls the OpenTelemetry Demo
cp .env.example .env
```

Edit `.env` and set at minimum:
- `GF_SECURITY_ADMIN_PASSWORD` — Grafana admin password (default `changeme`)
- `LLM_PROVIDER` — `mock` (no key needed) or `openai` / `anthropic`
- `LLM_API_KEY` — required only when `LLM_PROVIDER` is `openai` or `anthropic`

### 2 — Install proxy dependencies

```bash
pip install -r proxy/requirements.txt
```

### 3 — Start the stack

**Mode A** (default — Prometheus + ClickHouse, full Grafana metrics support):

```bash
docker compose -f docker-compose.yml -f docker-compose.otel-demo-override.yml --profile mode-a up -d
```

**Mode B** (ClickHouse-only, lower resource footprint):

```bash
STORAGE_MODE=clickhouse_only docker compose -f docker-compose.yml -f docker-compose.otel-demo-override.yml up -d
```

Wait ~30 seconds for ClickHouse and the OTel Collector to become healthy
before starting the proxy. The load generator starts driving traffic
automatically — no manual action needed.

### 4 — Start the proxy

```bash
FLASK_APP=proxy.app flask run --host 0.0.0.0 --port 5000
```

Or in the background (PowerShell):

```powershell
Start-Process python -ArgumentList "-m flask run --host 0.0.0.0 --port 5000" -NoNewWindow
```

Verify it is running:

```bash
curl http://localhost:5000/health
# → {"status": "healthy", "storage_mode": "prometheus"}
```

### 5 — Use the API

**Correlate telemetry over the last 2 minutes:**

```bash
curl -s -X POST http://localhost:5000/correlate \
  -H "Content-Type: application/json" \
  -d "{\"start_time\": $(python -c \"import time; print(int(time.time())-120)\"), \"end_time\": $(python -c \"import time; print(int(time.time()))\")}" \
  | python -m json.tool
```

**Run RCA (correlate → LLM → pending result):**

```bash
curl -s -X POST http://localhost:5000/rca \
  -H "Content-Type: application/json" \
  -d "{\"start_time\": $(python -c \"import time; print(int(time.time())-120)\"), \"end_time\": $(python -c \"import time; print(int(time.time()))\")}" \
  | python -m json.tool
# → {"id": "<uuid>", "cause": "...", "confidence": 0.xx, "evidence": [...], "playbook": [...], "status": "pending", "note": ""}
```

**Approve an RCA suggestion** (substitute the `id` from the previous response):

```bash
curl -s -X POST http://localhost:5000/rca/<id>/approve \
  -H "Content-Type: application/json" \
  -d '{"note": "Verified by on-call engineer"}' \
  | python -m json.tool
# → {"status": "approved", ...}
```

**Reject an RCA suggestion:**

```bash
curl -s -X POST http://localhost:5000/rca/<id>/reject \
  -H "Content-Type: application/json" \
  -d '{"note": "False positive"}' \
  | python -m json.tool
# → {"status": "rejected", ...}
```

**Retrieve a stored RCA by id:**

```bash
curl -s http://localhost:5000/rca/<id> | python -m json.tool
```

### 6 — Run the end-to-end smoke test

The smoke test brings up the stack (idempotent), starts the proxy, exercises
the full pipeline (`/correlate` → `/rca` → `/rca/<id>/approve`), and exits 0:

```bash
python scripts/smoke_test.py
```

If the Docker stack is already running, skip the compose step:

```bash
python scripts/smoke_test.py --skip-compose
```

### 7 — Observe in Grafana

Open `http://localhost:3000` and log in with the credentials from your `.env`
file (`GF_SECURITY_ADMIN_USER` / `GF_SECURITY_ADMIN_PASSWORD`).
The Prometheus datasource is auto-provisioned — no manual setup required.

### 8 — Trigger a real fault (optional demo step)

The OpenTelemetry Demo ships a feature-flag service. To inject a real
product-catalog failure:

1. Open `otel-demo/src/flagd/demo.flagd.json`
2. Find the `productCatalogFailure` flag and set `"defaultVariant": "on"`
3. Within ~30 seconds, error spans from `productcatalogservice` appear in
   ClickHouse and propagate to `frontend` — run `/rca` to see the LLM explain it

### Tear down

```bash
docker compose -f docker-compose.yml -f docker-compose.otel-demo-override.yml --profile mode-a down
# Add -v to also delete stored data (Prometheus, ClickHouse, Grafana volumes)
```

---

## Service URLs (when stack is running)

| Service | URL |
|---|---|
| Proxy API | `http://localhost:5000` |
| Proxy health | `http://localhost:5000/health` |
| Grafana | `http://localhost:3000` |
| Prometheus (Mode A) | `http://localhost:9090` |
| ClickHouse HTTP | `http://localhost:8123` |
| OTel Collector OTLP gRPC | `localhost:4317` |
| OTel Collector OTLP HTTP | `localhost:4318` |
| Frontend (demo shop) | `http://localhost:8080` |
| Load generator (Locust) | `http://localhost:8089` |
| Feature flags (flagd) | `http://localhost:8013` |

---

## Proxy API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check — returns `storage_mode` |
| `POST` | `/correlate` | Correlate metrics + logs + traces for a time window |
| `POST` | `/rca` | Run correlation then LLM RCA — returns a pending suggestion |
| `GET` | `/rca/<id>` | Retrieve a stored RCA suggestion |
| `POST` | `/rca/<id>/approve` | Approve a pending suggestion (optional `note` body field) |
| `POST` | `/rca/<id>/reject` | Reject a pending suggestion (optional `note` body field) |

All `POST` endpoints that accept a time window require:

```json
{
  "start_time": 1700000000.0,
  "end_time":   1700000060.0
}
```

Optional fields: `service_name` (string), `trace_id` (string),
`metric_names` (list of strings).

---

## Documentation

| File | What it covers |
|---|---|
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | System design, storage modes, network/volume layout, repo structure |
| [`TASKS.md`](./TASKS.md) | Phase-by-phase implementation plan, broken into testable tasks |
| [`AGENT.md`](./AGENT.md) | Instructions for an AI coding agent working in this repo |
| [`SKILLS.md`](./SKILLS.md) | Skills/knowledge areas the agent should draw on, plus recommended MCP servers |
| [`MEMORY.md`](./MEMORY.md) | Running implementation log, updated after each completed task |

## Running the test suite

```bash
pip install -r proxy/requirements.txt
python -m pytest proxy/tests/ -v
```

Expected: **81 tests, all pass** (unit + integration, no live infra required).

## Status

Hackathon build — all seven phases complete. Single-user (stubbed auth),
Grafana as the only visualization tool, both storage modes (A/B) implemented
behind a Compose profile switch. The proxy, correlation engine, LLM RCA
client, and human-approval flow are fully implemented and tested.
