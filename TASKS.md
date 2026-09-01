# Tasks

Work top to bottom. Each task's checkbox only gets checked after its Test
line passes — see `AGENT.md` for the full working loop.

## Phase 0 — Repo Scaffolding

- [x] **0.1** Create the directory structure exactly as listed in
  `ARCHITECTURE.md`'s Filing Structure section.
  **Test:** structure matches the doc, no extra/missing top-level dirs.
- [x] **0.2** Create `.env.example` covering: `STORAGE_MODE`,
  `GF_SECURITY_ADMIN_USER`, `GF_SECURITY_ADMIN_PASSWORD`, `LLM_PROVIDER`,
  `LLM_API_KEY`.
  **Test:** `python -c "from dotenv import dotenv_values; print(dotenv_values('.env.example'))"` runs without error and shows all keys.

## Phase 1 — Storage & Ingestion (Mode A baseline)

- [x] **1.1** Write `docker-compose.yml` with `otel-collector`, `prometheus`,
  `clickhouse` on the `aiops-net` network, with named volumes for Prometheus
  and ClickHouse.
  **Test:** `docker compose --profile mode-a up -d` — all three containers reach a healthy/running state.
- [x] **1.2** Write `config/otel-collector-config-mode-a.yaml` (metrics →
  Prometheus exporter, logs+traces → ClickHouse exporter).
  **Test:** send a test OTLP payload, `curl localhost:8889/metrics` returns it.
- [x] **1.3** Write `config/prometheus.yml` scraping the collector's metrics endpoint.
  **Test:** Prometheus UI → Status → Targets shows `otel-collector` as UP.
- [x] **1.4** Add the OpenTelemetry Demo as a pinned git submodule at `otel-demo/`.
  **Test:** `git submodule status` shows it checked out at the pinned commit/tag.
- [x] **1.5** Write `docker-compose.otel-demo-override.yml`: select the core
  service subset (frontend, cart, checkout, product-catalog, payment,
  load-generator, feature-flag-service), set each service's
  `OTEL_EXPORTER_OTLP_ENDPOINT` to our `otel-collector`, join `aiops-net`,
  and exclude the demo's own `otel-collector`/`jaeger`/`prometheus`/`grafana`.
  **Test:** `docker compose -f docker-compose.yml -f docker-compose.otel-demo-override.yml --profile mode-a up -d` — only our stack's Prometheus/ClickHouse/Grafana appear, no duplicate demo-owned copies.
- [x] **1.6** Verify real telemetry flow: with the combined stack up and the
  load generator running, confirm `otel_logs`/`otel_traces` in ClickHouse
  and service-level metrics in Prometheus (or `otel_metrics_*` in Mode B)
  are populated by the demo's actual services, not placeholder data.
  **Test:** query ClickHouse for `ServiceName IN ('frontend','cartservice','checkoutservice')` — non-empty within 60s of load-generator start.
- [x] **1.7** Verify fault injection reaches our pipeline: enable one feature
  flag via the feature-flag-service UI (e.g., product catalog failure),
  confirm the resulting errors/anomalous spans are visible in ClickHouse/Prometheus.
  **Test:** query for the expected elevated error rate or failing spans on the affected service after toggling the flag.

## Phase 2 — Mode B Toggle

- [x] **2.1** Write `config/otel-collector-config-mode-b.yaml` (everything → ClickHouse, including `otel_metrics_*`).
  **Test:** with `STORAGE_MODE=clickhouse_only`, run the simulator; confirm `otel_metrics_gauge`/`otel_metrics_sum` tables receive data.
- [x] **2.2** Add the `profiles: ["mode-a"]` tag to the `prometheus` service in `docker-compose.yml`.
  **Test:** `docker compose up -d` (no profile flag) starts without a Prometheus container; `docker compose --profile mode-a up -d` does start one.
- [x] **2.3** Build `proxy/adapters/metrics_adapter.py` (base interface),
  `prometheus_adapter.py`, and `clickhouse_metrics_adapter.py`.
  **Test:** unit tests feed both adapters an equivalent query and assert they return the same normalized shape.

## Phase 3 — Visualization

- [x] **3.1** Add `grafana` service to `docker-compose.yml`: persistent
  volume, published port, `GF_SECURITY_ADMIN_USER`/`PASSWORD` from `.env` —
  **no** auth-proxy env vars (see `ARCHITECTURE.md` security note).
  **Test:** Grafana UI reachable at `localhost:3000`, logs in with `.env` credentials.
- [x] **3.2** Add `config/grafana/provisioning/datasources/prometheus.yaml` auto-pointing at Prometheus.
  **Test:** on fresh container start, Grafana's datasource shows healthy with zero manual configuration.

## Phase 4 — Proxy Server Core

- [x] **4.1** Scaffold Flask app factory + `/health` route.
  **Test:** `GET /health` returns `200`.
- [x] **4.2** Build `proxy/correlation/engine.py`: given a time window, query
  the active metrics adapter + ClickHouse logs/traces by `trace_id`, merge
  into one structured payload.
  **Test:** unit test against seeded fake data returns the expected merged shape.
- [x] **4.3** Build `POST /correlate` route wrapping the engine.
  **Test:** integration test posts a time window, asserts the response JSON shape.

## Phase 5 — LLM RCA

- [x] **5.1** Build `proxy/rca/llm_client.py`, provider-agnostic per `.env`'s `LLM_PROVIDER`.
  **Test:** with a mocked LLM response, confirm the client parses cause/confidence/evidence/playbook correctly.
- [x] **5.2** Build `POST /rca`: on-demand trigger → correlate → LLM → return structured result.
  **Test:** integration test with a mocked LLM runs end-to-end and returns the expected shape.

## Phase 6 — Human Approval

- [x] **6.1** Add an approval endpoint/state for RCA suggestions (in-memory store is fine for this phase).
  **Test:** `POST /rca/<id>/approve` and `/reject` change the stored status accordingly.

## Phase 7 — Demo Readiness

- [x] **7.1** Write an end-to-end smoke test script: bring up the stack,
  run the simulator, hit `/correlate`, hit `/rca`, approve the result.
  **Test:** script exits `0` with no manual intervention.
- [x] **7.2** Update `README.md`'s Quick Start with the final, verified commands.
  **Test:** a clean checkout + the README's exact commands reproduces a working demo.
