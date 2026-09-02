# Self-Healing AI Operations Controller

A self-hosted telemetry pipeline that collects metrics, logs, and traces from
the [OpenTelemetry Demo](https://github.com/open-telemetry/opentelemetry-demo)
("Astronomy Shop"), correlates them automatically, and uses an LLM to suggest
a root cause — with a human approving before anything is acted on.

Observability stack: Prometheus + ClickHouse + Grafana + SigNoz.  
Storage modes: **Mode A** (Prometheus metrics, ClickHouse logs/traces) or
**Mode B** (ClickHouse only — lower resource footprint).

---

## Quick Start

### Prerequisites

- Docker Desktop ≥ 2.20 (or Docker Engine + Compose plugin)
- Python 3.11+
- Node.js 18+ with npm (for the React frontend)
- Git (for submodule init)

### 1 — Clone and configure

```bash
git clone <repo-url> self-healer
cd self-healer
git submodule update --init --recursive   # pulls the OpenTelemetry Demo at 1.11.0
cp .env.example .env
```

Edit `.env` and set:

| Variable | Required | Notes |
|---|---|---|
| `GF_SECURITY_ADMIN_PASSWORD` | yes | Grafana admin password (default `changeme`) |
| `LLM_PROVIDER` | yes | `mock` (no key), `openai`, or `anthropic` |
| `LLM_API_KEY` | if provider ≠ mock | API key for the chosen provider |
| `STORAGE_MODE` | no | `prometheus` (Mode A, default) or `clickhouse_only` (Mode B) |

### 2 — Install proxy dependencies

```bash
pip install -r proxy/requirements.txt
```

### 3 — Build the React frontend

```bash
cd frontend
npm install
npm run build   # produces frontend/dist/ — serve statically or use npm run dev
cd ..
```

### 4 — Start the full stack (Mode A)

Mode A includes Prometheus metrics, Grafana dashboards (auto-provisioned),
SigNoz, and the OTel Demo services with load generator:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.otel-demo-override.yml \
  -f docker-compose.signoz.yml \
  -f docker-compose.prometheus-ui.yml \
  --profile mode-a \
  up -d
```

Wait ~30 seconds for ClickHouse and the OTel Collector to become healthy.
The load generator starts driving realistic traffic automatically — no manual
action needed.

**Mode B** (ClickHouse only, lower RAM footprint — omit Prometheus and Grafana):

```bash
STORAGE_MODE=clickhouse_only docker compose \
  -f docker-compose.yml \
  -f docker-compose.otel-demo-override.yml \
  up -d
```

**Without SigNoz** (saves ~3 containers):

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.otel-demo-override.yml \
  -f docker-compose.prometheus-ui.yml \
  --profile mode-a \
  up -d
```

### 5 — Start the proxy

```bash
FLASK_APP=proxy.app flask run --host 0.0.0.0 --port 5000
```

Or in the background (macOS/Linux):

```bash
FLASK_APP=proxy.app flask run --host 0.0.0.0 --port 5000 &
```

Verify it is running:

```bash
curl http://localhost:5000/health
# → {"status": "healthy", "storage_mode": "prometheus"}
```

### 6 — Trigger an RCA

**Manual trigger — correlate the last 5 minutes:**

```bash
curl -s -X POST http://localhost:5000/api/rca/trigger \
  -H "Content-Type: application/json" \
  -d "{\"start_time\": $(python3 -c 'import time; print(int(time.time())-300)'), \"end_time\": $(python3 -c 'import time; print(int(time.time()))')}" \
  | python3 -m json.tool
# → {"id": "<uuid>", "cause": "...", "confidence": 0.xx,
#    "evidence": [...], "playbook": [...], "status": "pending", "note": ""}
```

**Approve the suggestion** (substitute the `id` from the previous response):

```bash
curl -s -X POST http://localhost:5000/rca/<id>/approve \
  -H "Content-Type: application/json" \
  -d '{"note": "Verified by on-call engineer"}' \
  | python3 -m json.tool
# → {"status": "approved", ...}
```

**Reject the suggestion:**

```bash
curl -s -X POST http://localhost:5000/rca/<id>/reject \
  -H "Content-Type: application/json" \
  -d '{"note": "False positive — expected behaviour during deployment"}' \
  | python3 -m json.tool
```

**List all RCA results:**

```bash
curl -s http://localhost:5000/api/rca/results | python3 -m json.tool
```

**Correlate without triggering RCA** (raw evidence payload):

```bash
curl -s -X POST http://localhost:5000/correlate \
  -H "Content-Type: application/json" \
  -d "{\"start_time\": $(python3 -c 'import time; print(int(time.time())-120)'), \"end_time\": $(python3 -c 'import time; print(int(time.time()))')}" \
  | python3 -m json.tool
```

### 7 — Run the end-to-end smoke test (Task 11.1)

The full-stack smoke test brings up all components, exercises the complete
pipeline, and exits 0 with no manual intervention:

```bash
python3 scripts/e2e_smoke_test.py
```

If the Docker stack is already running (idempotent):

```bash
python3 scripts/e2e_smoke_test.py --skip-compose --skip-build
```

The script runs 15 steps: compose up → frontend build → ClickHouse/Grafana/
SigNoz/Collector health → proxy start → telemetry flow → spanmetrics →
Grafana dashboards → SigNoz traces → `/api/rca/trigger` → approve → verify.

### 8 — Observe in Grafana

Open `http://localhost:3000` and log in with your `.env` credentials
(`GF_SECURITY_ADMIN_USER` / `GF_SECURITY_ADMIN_PASSWORD`).

Four dashboards are provisioned automatically (no manual import):
- **Demo Dashboard** — latency percentiles and error rates per service
- **Spanmetrics Demo Dashboard** — top services by request rate and duration
- **OpenTelemetry Collector** — collector receiver/exporter throughput
- **OpenTelemetry Collector Data Flow** — end-to-end pipeline data flow

The Prometheus datasource is auto-configured — no manual setup required.

### 9 — Observe in SigNoz

Open `http://localhost:8080` to access the SigNoz UI.  
SigNoz receives a forwarded copy of all telemetry from the same OTel
Collector (fan-out design) and stores it in its own `signoz_*` ClickHouse
schema. The `otel_*` tables (used by Grafana and the correlation engine)
are unaffected.

### 10 — Inject a real fault (demo step)

The OTel Demo ships a feature-flag service. To inject a real product-catalog
failure and watch it propagate through the pipeline:

1. Open `otel-demo/src/flagd/demo.flagd.json`
2. Find `productCatalogFailure` and set `"defaultVariant": "on"`
3. Within ~30 seconds, error spans from `productcatalogservice` appear in
   ClickHouse and cascade to `frontend`
4. Run `/api/rca/trigger` to see the LLM explain the root cause

Alternatively, use the feature-flag UI at `http://localhost:8013`.

### Tear down

```bash
# Stop all containers, preserve volumes (data survives restart)
docker compose \
  -f docker-compose.yml \
  -f docker-compose.otel-demo-override.yml \
  -f docker-compose.signoz.yml \
  -f docker-compose.prometheus-ui.yml \
  --profile mode-a \
  down

# Stop and delete all data (clean slate)
docker compose \
  -f docker-compose.yml \
  -f docker-compose.otel-demo-override.yml \
  -f docker-compose.signoz.yml \
  -f docker-compose.prometheus-ui.yml \
  --profile mode-a \
  down -v
```

---

## Service URLs

| Service | URL | Notes |
|---|---|---|
| Proxy API | `http://localhost:5000` | Flask proxy — all RCA and health endpoints |
| React SPA (dev server) | `http://localhost:5173` | `npm run dev` inside `frontend/` |
| Grafana | `http://localhost:3000` | Admin login from `.env` |
| Prometheus | `http://localhost:9090` | Mode A only, with `prometheus-ui.yml` |
| SigNoz | `http://localhost:8080` | Requires `docker-compose.signoz.yml` |
| ClickHouse HTTP | `http://localhost:8123` | Query API |
| OTel Collector OTLP gRPC | `localhost:4317` | |
| OTel Collector OTLP HTTP | `localhost:4318` | |
| OTel Collector health | `http://localhost:13133` | health_check extension |
| OTel Demo Shop (frontend) | `http://localhost:8085` | Demo microservices |
| Load generator (Locust) | `http://localhost:8089` | Traffic control |
| Feature flags | `http://localhost:8013` | Fault injection UI |

---

## Proxy API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness — returns `storage_mode` |
| `GET` | `/api/health` | Aggregated HTTP health checks per service |
| `GET` | `/api/config` | Current wizard configuration |
| `POST` | `/api/config` | Save wizard configuration |
| `GET` | `/api/tools` | Enabled tool URLs (Grafana, Prometheus, SigNoz) |
| `GET` | `/api/telemetry/summary` | Recent telemetry volume from ClickHouse |
| `POST` | `/api/rca/trigger` | Manual RCA trigger for a time window |
| `GET` | `/api/rca/results` | All RCA results, newest first |
| `POST` | `/correlate` | Raw correlation payload for a time window |
| `POST` | `/rca` | Correlate + LLM — returns pending suggestion |
| `GET` | `/rca/<id>` | Retrieve a stored RCA suggestion |
| `POST` | `/rca/<id>/approve` | Approve a pending suggestion |
| `POST` | `/rca/<id>/reject` | Reject a pending suggestion |

All time-window endpoints accept:

```json
{
  "start_time": 1700000000.0,
  "end_time":   1700000300.0
}
```

Optional: `service_name` (string), `trace_id` (string), `metric_names` (list).

---

## Running the test suite

```bash
pip install -r proxy/requirements.txt
python3 -m pytest proxy/tests/ -v
```

Expected: **116 tests, all pass** (unit + integration, no live infra required).

---

## Architecture overview

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the full design. The short version:

- **Single OTel Collector** ingests all telemetry from the demo services.  
  In Mode A it fans out to Prometheus (metrics) and ClickHouse (logs + traces).  
  In Mode B everything goes to ClickHouse.
- **SigNoz** receives a forwarded copy via a second exporter branch — same
  ClickHouse instance, separate `signoz_*` schema. No second collector ingestion path.
- **Grafana dashboards** are provisioned from the OTel Demo's own dashboard
  JSON, datasource UID updated to match our Prometheus instance, metric names
  updated for OTel Collector 0.128.0 naming conventions.
- **Flask proxy** runs on the host, queries the active storage backend through
  a `MetricsQueryAdapter` interface (Prometheus in Mode A, ClickHouse in Mode B),
  correlates evidence by `trace_id`, and sends structured payloads to the LLM.
- **Human approval** is required for every RCA suggestion — no auto-execution.

## Documentation

| File | What it covers |
|---|---|
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | System design, storage modes, network/volume layout |
| [`FRONTEND.md`](./FRONTEND.md) | React SPA pages, API contract, wizard limits |
| [`TASKS.md`](./TASKS.md) | Phase-by-phase implementation plan |
| [`AGENT.md`](./AGENT.md) | Instructions for an AI coding agent working in this repo |
| [`SKILLS.md`](./SKILLS.md) | Domain knowledge map + recommended MCP servers |
| [`MEMORY.md`](./MEMORY.md) | Running implementation log |
| [`docs/configuration-options.md`](./docs/configuration-options.md) | All wizard config options with Active/Disabled status |
