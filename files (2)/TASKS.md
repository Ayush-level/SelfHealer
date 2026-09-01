# Tasks

Work top to bottom. Each task's checkbox only gets checked after its Test
line passes — see `AGENT.md` for the full working loop.

## Phase 0 — Repo Scaffolding

- [ ] **0.1** Create the directory structure exactly as listed in
  `ARCHITECTURE.md`'s Filing Structure section.
  **Test:** structure matches the doc, no extra/missing top-level dirs.
- [ ] **0.2** Create `.env.example` covering: `STORAGE_MODE`,
  `GF_SECURITY_ADMIN_USER`, `GF_SECURITY_ADMIN_PASSWORD`, `LLM_PROVIDER`,
  `LLM_API_KEY`.
  **Test:** `python -c "from dotenv import dotenv_values; print(dotenv_values('.env.example'))"` runs without error and shows all keys.

## Phase 1 — Storage & Ingestion (Mode A baseline)

- [ ] **1.1** Write `docker-compose.yml` with `otel-collector`, `prometheus`,
  `clickhouse` on the `aiops-net` network, with named volumes for Prometheus
  and ClickHouse.
  **Test:** `docker compose --profile mode-a up -d` — all three containers reach a healthy/running state.
- [ ] **1.2** Write `config/otel-collector-config-mode-a.yaml` (metrics →
  Prometheus exporter, logs+traces → ClickHouse exporter).
  **Test:** send a test OTLP payload, `curl localhost:8889/metrics` returns it.
- [ ] **1.3** Write `config/prometheus.yml` scraping the collector's metrics endpoint.
  **Test:** Prometheus UI → Status → Targets shows `otel-collector` as UP.
- [ ] **1.4** Add the OpenTelemetry Demo as a pinned git submodule at `otel-demo/`.
  **Test:** `git submodule status` shows it checked out at the pinned commit/tag.
- [ ] **1.5** Write `docker-compose.otel-demo-override.yml`: select the core
  service subset (frontend, cart, checkout, product-catalog, payment,
  load-generator, feature-flag-service), set each service's
  `OTEL_EXPORTER_OTLP_ENDPOINT` to our `otel-collector`, join `aiops-net`,
  and exclude the demo's own `otel-collector`/`jaeger`/`prometheus`/`grafana`.
  **Test:** `docker compose -f docker-compose.yml -f docker-compose.otel-demo-override.yml --profile mode-a up -d` — only our stack's Prometheus/ClickHouse/Grafana appear, no duplicate demo-owned copies.
- [ ] **1.6** Verify real telemetry flow: with the combined stack up and the
  load generator running, confirm `otel_logs`/`otel_traces` in ClickHouse
  and service-level metrics in Prometheus (or `otel_metrics_*` in Mode B)
  are populated by the demo's actual services, not placeholder data.
  **Test:** query ClickHouse for `ServiceName IN ('frontend','cartservice','checkoutservice')` — non-empty within 60s of load-generator start.
- [ ] **1.7** Verify fault injection reaches our pipeline: enable one feature
  flag via the feature-flag-service UI (e.g., product catalog failure),
  confirm the resulting errors/anomalous spans are visible in ClickHouse/Prometheus.
  **Test:** query for the expected elevated error rate or failing spans on the affected service after toggling the flag.

## Phase 2 — Mode B Toggle

- [ ] **2.1** Write `config/otel-collector-config-mode-b.yaml` (everything → ClickHouse, including `otel_metrics_*`).
  **Test:** with `STORAGE_MODE=clickhouse_only`, run the simulator; confirm `otel_metrics_gauge`/`otel_metrics_sum` tables receive data.
- [ ] **2.2** Add the `profiles: ["mode-a"]` tag to the `prometheus` service in `docker-compose.yml`.
  **Test:** `docker compose up -d` (no profile flag) starts without a Prometheus container; `docker compose --profile mode-a up -d` does start one.
- [ ] **2.3** Build `proxy/adapters/metrics_adapter.py` (base interface),
  `prometheus_adapter.py`, and `clickhouse_metrics_adapter.py`.
  **Test:** unit tests feed both adapters an equivalent query and assert they return the same normalized shape.

## Phase 3 — Visualization

- [ ] **3.1** Add `grafana` service to `docker-compose.yml`: persistent
  volume, published port, `GF_SECURITY_ADMIN_USER`/`PASSWORD` from `.env` —
  **no** auth-proxy env vars (see `ARCHITECTURE.md` security note).
  **Test:** Grafana UI reachable at `localhost:3000`, logs in with `.env` credentials.
- [ ] **3.2** Add `config/grafana/provisioning/datasources/prometheus.yaml` auto-pointing at Prometheus.
  **Test:** on fresh container start, Grafana's datasource shows healthy with zero manual configuration.
- [ ] **3.3** Make Prometheus's own published port conditional on an
  `ENABLE_PROMETHEUS_UI` env var, independent of `STORAGE_MODE` (Prometheus
  can still be used as storage in Mode A even if its own UI isn't exposed).
  **Test:** `ENABLE_PROMETHEUS_UI=false` — Prometheus still receives/serves data via the adapter, but `localhost:9090` is not reachable.

## Phase 4 — Proxy Server Core

- [ ] **4.1** Scaffold Flask app factory + `/health` route.
  **Test:** `GET /health` returns `200`.
- [ ] **4.2** Build `proxy/correlation/engine.py`: given a time window, query
  the active metrics adapter + ClickHouse logs/traces by `trace_id`, merge
  into one structured payload.
  **Test:** unit test against seeded fake data returns the expected merged shape.
- [ ] **4.3** Build `POST /correlate` route wrapping the engine.
  **Test:** integration test posts a time window, asserts the response JSON shape.

## Phase 5 — LLM RCA

- [ ] **5.1** Build `proxy/rca/llm_client.py`, provider-agnostic per `.env`'s `LLM_PROVIDER`.
  **Test:** with a mocked LLM response, confirm the client parses cause/confidence/evidence/playbook correctly.
- [ ] **5.2** Build `POST /rca`: on-demand trigger → correlate → LLM → return structured result.
  **Test:** integration test with a mocked LLM runs end-to-end and returns the expected shape.

## Phase 6 — Human Approval

- [ ] **6.1** Add an approval endpoint/state for RCA suggestions (in-memory store is fine for this phase).
  **Test:** `POST /rca/<id>/approve` and `/reject` change the stored status accordingly.

## Phase 7 — Frontend & Setup Wizard

- [ ] **7.1** Scaffold the React SPA (`frontend/`) with routing for
  `/setup`, `/`, `/telemetry`, `/tools`, `/rca` per `FRONTEND.md`.
  **Test:** `npm run build` succeeds; each route renders without a console error against a mocked API.
- [ ] **7.2** Build `proxy/routes/config.py`: `GET/POST /api/config`, writing
  validated wizard input to `.env`/config store.
  **Test:** `POST /api/config` with valid input, then `GET /api/config` returns exactly what was saved.
- [ ] **7.3** Build the Setup wizard page: on save, display the exact
  `docker compose ...` command assembled from the saved config (see
  `FRONTEND.md` — the proxy cannot restart containers itself).
  **Test:** for a given saved config, the displayed command matches the expected flags/profiles exactly.
- [ ] **7.4** Build `proxy/routes/tools.py` (`GET /api/tools`) returning
  enabled tool URLs from saved config.
  **Test:** toggling a tool off in config removes it from the `/api/tools` response.
- [ ] **7.5** Build the Home page against `GET /api/health` and the
  Telemetry Analysis page against `GET /api/telemetry/summary`.
  **Test:** both pages render real data from a running stack, not placeholders.

## Phase 8 — SigNoz Integration

- [ ] **8.1** Write `config/signoz-otel-collector-config.yaml` and add
  `signoz-otel-collector`, `signoz-query-service`, `signoz-frontend` to
  `docker-compose.signoz.yml`, all writing to a separate `signoz_*`
  database in the shared ClickHouse instance.
  **Test:** `docker compose -f docker-compose.yml -f docker-compose.signoz.yml up -d` — SigNoz UI reachable and shows data after the load generator runs.
- [ ] **8.2** Add the forward-export branch to `otel-collector-config-mode-a.yaml`
  and `-mode-b.yaml`: a second exporter sending a copy of all signals to `signoz-otel-collector`.
  **Test:** with SigNoz enabled, `signoz_*` tables and `otel_*` tables both populate from the same load-generator run.
- [ ] **8.3** Add the `ENABLE_SIGNOZ` toggle to the config schema and wire it
  into `docker-compose.signoz.yml` (only started when enabled) and `/api/tools`.
  **Test:** `ENABLE_SIGNOZ=false` — no SigNoz containers start, and it's absent from `/api/tools`.

## Phase 9 — RCA Trigger Modes

- [ ] **9.1** Build `proxy/scheduler/rca_scheduler.py` using APScheduler:
  runs the correlate → LLM flow on the most recent window at a configured
  interval, only when `RCA_TRIGGER_MODE=automatic`.
  **Test:** with a 1-minute interval and a mocked LLM, confirm two RCA results appear roughly 60s apart with no manual trigger.
- [ ] **9.2** Ensure manual mode (`POST /api/rca/trigger`) still works
  identically regardless of the scheduler's on/off state.
  **Test:** with `RCA_TRIGGER_MODE=manual`, the scheduler never fires, but a manual POST still returns a result.
- [ ] **9.3** Confirm both modes route through the same approval flow.
  **Test:** a scheduler-generated result and a manually-triggered result both appear in `/api/rca/results` with identical shape, both approvable/rejectable.

## Phase 10 — Grafana Dashboards for OpenTelemetry Demo Data

- [ ] **10.1** Import the OpenTelemetry Demo repository's own Grafana
  dashboard JSON into `config/grafana/provisioning/dashboards/`, updating
  datasource UID references to match our provisioned datasource.
  **Test:** on fresh Grafana start, the dashboards appear pre-loaded with zero manual import.
- [ ] **10.2** Verify each dashboard actually renders data from the running
  OTel Demo services (not blank panels from a metric-name mismatch).
  **Test:** with the load generator running, every panel on the imported dashboard(s) shows non-empty data.

## Phase 11 — Demo Readiness

- [ ] **11.1** Write an end-to-end smoke test script: bring up the full
  stack (Mode A, Grafana, SigNoz, frontend), confirm the OpenTelemetry
  Demo's load generator is producing traffic, hit `/api/rca/trigger`,
  approve the result.
  **Test:** script exits `0` with no manual intervention.
- [ ] **11.2** Update `README.md`'s Quick Start with the final, verified commands.
  **Test:** a clean checkout + the README's exact commands reproduces a working demo.
