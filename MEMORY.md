# Memory Log

Append-only implementation log. One entry per completed task from
`TASKS.md`. Don't rewrite past entries except to correct a factual error —
this log is how a future session (or a human) reconstructs project state
without re-reading the whole codebase.

## Entry Format

```
### [YYYY-MM-DD] — Task X.Y: <task name>
- **Status:** done / blocked / partial
- **Changes:** files created/modified, one line each
- **Test result:** exact command run + outcome (pass/fail + output summary)
- **Decisions/deviations:** anything not exactly per TASKS.md/ARCHITECTURE.md, and why
- **Next:** what should happen next
```

## How to Use This File

- Before starting a session: read the most recent 3–5 entries to know the
  actual current state, not just what `TASKS.md`'s checkboxes claim.
- After finishing a task (test passing): append one entry immediately —
  don't batch multiple tasks into one entry, and don't wait until "later."
- If a task is blocked: log it as `blocked` with the reason, don't leave it
  silently unfinished with no record.
- If you deviate from `ARCHITECTURE.md` for a good reason discovered during
  implementation: log it here **and** flag it to the human — this file
  records what happened, it doesn't replace asking.

---

## Log

### [2026-09-01] — Task 0.1: Create the directory structure
- **Status:** done
- **Changes:** created `config/grafana/provisioning/datasources/`, `otel-demo/`, `proxy/{adapters,correlation,rca,routes,tests}/`, `docs/diagrams/` with `.gitkeep` so empty dirs are tracked
- **Test result:** Python check of top-level dirs vs ARCHITECTURE.md (`config`, `docs`, `otel-demo`, `proxy`) plus nested paths — PASS; no extra/missing top-level dirs
- **Decisions/deviations:** did not create later-task files (`docker-compose.yml`, `.env.example`, collector/proxy Python files, `docs/configuration-options.md`) — 0.1 is directories only. `otel-demo/.gitkeep` is a placeholder until task 1.4's submodule. Extra top-level file `ponytail.mdc.txt` exists; it is not a directory so it did not fail the test.
- **Next:** Task 0.2 — `.env.example` with `STORAGE_MODE`, Grafana admin creds, `LLM_PROVIDER`, `LLM_API_KEY`

### [2026-09-01] — Task 0.2: Create `.env.example`
- **Status:** done
- **Changes:** created `.env.example` with `STORAGE_MODE`, `GF_SECURITY_ADMIN_USER`, `GF_SECURITY_ADMIN_PASSWORD`, `LLM_PROVIDER`, `LLM_API_KEY`
- **Test result:** `python -c "from dotenv import dotenv_values; print(dotenv_values('.env.example'))"` — first run failed (`No module named 'dotenv'`); installed `python-dotenv==1.2.3` then PASS: OrderedDict with all five keys
- **Decisions/deviations:** Mode A placeholder is `STORAGE_MODE=prometheus` (Mode B remains `clickhouse_only` per README). Grafana example password is `changeme`, not a real secret. LLM keys left empty. `python-dotenv` installed into the local Python env for the test; not added to a requirements file yet (proxy `requirements.txt` is a later task).
- **Next:** Task 1.1 — `docker-compose.yml` with otel-collector, prometheus, clickhouse on `aiops-net` plus named volumes

### [2026-09-01] — Task 1.1: Write docker-compose.yml (collector, Prometheus, ClickHouse)
- **Status:** done
- **Changes:** added `docker-compose.yml` (`otel-collector`, `prometheus`, `clickhouse` on named network `aiops-net`; volumes `prometheus_data`, `clickhouse_data`); added stub `config/otel-collector-config-mode-a.yaml` so the collector process can boot
- **Test result:** `docker compose --profile mode-a up -d` — exit 0. `docker compose ps`: clickhouse healthy, prometheus healthy, otel-collector Up (running; collector logs: "Everything is ready")
- **Decisions/deviations:** Prometheus has no `profiles: ["mode-a"]` yet (task 2.2). Collector config is OTLP+debug only until 1.2. Images pinned (`otel/opentelemetry-collector-contrib:0.128.0`, `prom/prometheus:v2.55.1`, `clickhouse/clickhouse-server:24.8`). Did not use clickhousectl; architecture requires Compose ClickHouse on `aiops-net`.
- **Next:** Task 1.2 — Mode A collector config (metrics → Prometheus exporter, logs+traces → ClickHouse)

### [2026-09-01] — Task 1.2: Write config/otel-collector-config-mode-a.yaml (metrics → Prometheus exporter, logs+traces → ClickHouse exporter)
- **Status:** done
- **Changes:** updated `config/otel-collector-config-mode-a.yaml` (OTLP receivers, Prometheus exporter on `0.0.0.0:8889`, ClickHouse exporter on `tcp://clickhouse:9000?database=default`); updated `docker-compose.yml` to publish port `8889` on `otel-collector` and added `CLICKHOUSE_PASSWORD=` and `CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1` on `clickhouse`
- **Test result:** sent test OTLP metric payload to `http://localhost:4318/v1/metrics`; `curl.exe http://localhost:8889/metrics` returned `test_metric{job="test-service",...} 42` — PASS
- **Decisions/deviations:** ClickHouse official container entrypoint disables network access for default user without credentials set; configured `CLICKHOUSE_PASSWORD=` and `CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT=1` in `docker-compose.yml`. Mapped port `8889:8889` on `otel-collector` in `docker-compose.yml` for host scraping and verification.
- **Next:** Task 1.3 — Write `config/prometheus.yml` scraping the collector's metrics endpoint

### [2026-09-01] — Task 1.3: Write config/prometheus.yml scraping the collector's metrics endpoint
- **Status:** done
- **Changes:** created `config/prometheus.yml` configuring scrape jobs for `otel-collector` (`otel-collector:8889`) and `prometheus` (`localhost:9090`); mounted `config/prometheus.yml` to `/etc/prometheus/prometheus.yml:ro` in `docker-compose.yml`
- **Test result:** queried Prometheus targets API `http://localhost:9090/api/v1/targets` and `http://localhost:9090/api/v1/query?query=up`; `otel-collector` target is `health: "up"` and `up{instance="otel-collector:8889",job="otel-collector"} = 1` — PASS
- **Decisions/deviations:** none. Configured standard 5s scrape and evaluation interval.
- **Next:** Task 1.4 — Add the OpenTelemetry Demo as a pinned git submodule at `otel-demo/`

### [2026-09-01] — Task 1.4: Add the OpenTelemetry Demo as a pinned git submodule at otel-demo/
- **Status:** done
- **Changes:** added git submodule `otel-demo` tracking `https://github.com/open-telemetry/opentelemetry-demo.git` pinned at release tag `1.11.0` (commit `2957ad415cb88866fa74f870eb3ef75a48105bd7`)
- **Test result:** `git submodule status` returned `+2957ad415cb88866fa74f870eb3ef75a48105bd7 otel-demo (1.11.0)` — PASS
- **Decisions/deviations:** Pinned to tag `1.11.0`. Initialized local git repository to track submodules.
- **Next:** Task 1.5 — Write `docker-compose.otel-demo-override.yml` selecting core subset and pointing telemetry to our collector

### [2026-09-01] — Task 1.5: Write docker-compose.otel-demo-override.yml
- **Status:** done
- **Changes:** created `docker-compose.otel-demo-override.yml` configuring the core demo services (`frontend`, `cartservice`, `valkey-cart`, `checkoutservice`, `productcatalogservice`, `paymentservice`, `currencyservice`, `shippingservice`, `emailservice`, `flagd`, `loadgenerator`) joined to `aiops-net`, with `OTEL_EXPORTER_OTLP_ENDPOINT` pointing to our single `otel-collector`, and omitting the demo's own collector/jaeger/prometheus/grafana
- **Test result:** ran `docker compose -f docker-compose.yml -f docker-compose.otel-demo-override.yml --profile mode-a up -d`; verified `docker compose ps` shows all core demo services running alongside our single stack's Prometheus, ClickHouse, and Collector — PASS
- **Decisions/deviations:** included lightweight dependency services (`valkey-cart`, `currencyservice`, `shippingservice`, `emailservice`) necessary for cart and checkout operations to succeed; excluded heavy browser simulation in locust to keep resource footprint light.
- **Next:** Task 1.6 — Verify real telemetry flow (ClickHouse logs/traces and Prometheus metrics from demo services)

### [2026-09-01] — Task 1.6: Verify real telemetry flow
- **Status:** done
- **Changes:** none (verification task)
- **Test result:** queried ClickHouse `SELECT ServiceName, count() FROM otel_traces WHERE ServiceName IN ('frontend','cartservice','checkoutservice') GROUP BY ServiceName` — returned non-empty counts (frontend: 1032, checkoutservice: 148, cartservice: 318); verified Prometheus metrics API active metrics from live demo services (`rpc_server_duration_milliseconds_*`, `system_cpu_*`, etc.) — PASS
- **Decisions/deviations:** none. Real telemetry flows continuously from the load generator through the microservices into our single OTel Collector, ClickHouse, and Prometheus.
- **Next:** Task 1.7 — Verify fault injection reaches our pipeline

### [2026-09-01] — Task 1.7: Verify fault injection reaches our pipeline
- **Status:** done
- **Changes:** enabled `productCatalogFailure` feature flag in `otel-demo/src/flagd/demo.flagd.json`
- **Test result:** queried ClickHouse `SELECT ServiceName, SpanName, StatusCode, StatusMessage, count() FROM otel_traces WHERE StatusCode='Error' AND ServiceName IN ('productcatalogservice','frontend') GROUP BY ServiceName, SpanName, StatusCode, StatusMessage` — confirmed failing spans on `productcatalogservice` (`oteldemo.ProductCatalogService/GetProduct` with `Error: ProductCatalogService Fail Feature Flag Enabled`) and cascading errors on `frontend` — PASS
- **Decisions/deviations:** none. Real fault injection via flagd propagates through the services and is captured in ClickHouse traces through our collector.
- **Next:** Task 2.1 — Write `config/otel-collector-config-mode-b.yaml` (everything → ClickHouse, including `otel_metrics_*`)

### [2026-09-01] — Task 2.1: Write config/otel-collector-config-mode-b.yaml (everything → ClickHouse, including otel_metrics_*)
- **Status:** done
- **Changes:** created `config/otel-collector-config-mode-b.yaml` routing metrics, logs, and traces pipelines to `clickhouse` exporter; updated `docker-compose.yml` collector volume to support `${OTEL_COLLECTOR_CONFIG}`
- **Test result:** started collector with Mode B config; verified ClickHouse created `otel_metrics_*` tables; queried `otel_metrics_gauge` (61) and `otel_metrics_sum` (562) — both received live data — PASS
- **Decisions/deviations:** logs and traces pipelines kept identical to Mode A per SKILLS.md to prevent configuration drift.
- **Next:** Task 2.2 — Add `profiles: ["mode-a"]` to prometheus service in `docker-compose.yml`

### [2026-09-01] — Task 2.2: Add profiles: ["mode-a"] tag to prometheus service in docker-compose.yml
- **Status:** done
- **Changes:** added `profiles: ["mode-a"]` to the `prometheus` service in `docker-compose.yml`
- **Test result:** ran `docker compose up -d` (no profile) — confirmed no Prometheus container started; ran `docker compose --profile mode-a up -d` — confirmed `self-healer-prometheus-1` container started — PASS
- **Decisions/deviations:** none. Followed Compose profiles specification from ARCHITECTURE.md.
- **Next:** Task 2.3 — Build `proxy/adapters/metrics_adapter.py`, `prometheus_adapter.py`, and `clickhouse_metrics_adapter.py`

### [2026-09-01] — Task 2.3: Build proxy/adapters/metrics_adapter.py, prometheus_adapter.py, and clickhouse_metrics_adapter.py
- **Status:** done
- **Changes:** created `proxy/adapters/metrics_adapter.py` (base `MetricsQueryAdapter` ABC and normalized `MetricQueryResult`/`MetricSeries`/`MetricSample` data models), `proxy/adapters/prometheus_adapter.py` (Prometheus PromQL HTTP API client), `proxy/adapters/clickhouse_metrics_adapter.py` (ClickHouse SQL client against `otel_metrics_*`), `proxy/adapters/__init__.py`, and `proxy/tests/test_adapters.py`
- **Test result:** `python -m pytest proxy/tests/test_adapters.py -v` — 5 passed (verified equivalent query shapes across range and instant queries, metric listing, serialization, and live connectivity) — PASS
- **Decisions/deviations:** installed `requests` and `pytest` for proxy adapter execution and test verification; normalized service name and labels into unified `MetricSeries` representation across both modes.
- **Next:** Task 3.1 — Add `grafana` service to `docker-compose.yml`

### [2026-09-01] — Task 3.1: Add grafana service to docker-compose.yml
- **Status:** done
- **Changes:** added `grafana_data` named volume and `grafana` service in `docker-compose.yml` with port `3000:3000`, `.env` credentials (`GF_SECURITY_ADMIN_USER`/`GF_SECURITY_ADMIN_PASSWORD`), volume mounts for persistence and provisioning; created `.env` from `.env.example`
- **Test result:** authenticated against `http://localhost:3000/api/user` with credentials from `.env` (`admin:changeme`); returned 200 OK with `login: "admin", isGrafanaAdmin: true` — PASS
- **Decisions/deviations:** used standard basic auth login per ARCHITECTURE.md security note; did not configure auth-proxy header mode.
- **Next:** Task 3.2 — Add `config/grafana/provisioning/datasources/prometheus.yaml` auto-pointing at Prometheus

### [2026-09-01] — Task 3.2: Add config/grafana/provisioning/datasources/prometheus.yaml auto-pointing at Prometheus
- **Status:** done
- **Changes:** created `config/grafana/provisioning/datasources/prometheus.yaml` configuring Prometheus datasource (`http://prometheus:9090`) with `isDefault: true`, proxy access, and 5s time interval
- **Test result:** queried Grafana datasources API `GET /api/datasources` and health check `GET /api/datasources/uid/PBFA97CFB590B2093/health` — returned status "OK" with message "Successfully queried the Prometheus API." with zero manual UI configuration — PASS
- **Decisions/deviations:** none. Provisioning YAML loaded automatically by Grafana on boot.
- **Next:** Task 4.1 — Scaffold Flask app factory + `/health` route

### [2026-09-01] — Task 4.1: Scaffold Flask app factory + /health route
- **Status:** done
- **Changes:** created `proxy/config.py` for configuration management, `proxy/routes/health.py` (`health_bp` blueprint with `GET /health`), `proxy/app.py` (`create_app` factory registering blueprints and setting up active `MetricsQueryAdapter`), `proxy/requirements.txt`, and `proxy/tests/test_health.py`
- **Test result:** `python -m pytest proxy/tests/test_health.py -v` — returned 200 OK with `status: "healthy"` and `storage_mode: "prometheus"` — PASS
- **Decisions/deviations:** none. Implemented blueprint architecture and application factory pattern per AGENT.md.
- **Next:** Task 4.2 — Build `proxy/correlation/engine.py`

### [2026-09-01] — Task 4.2: Build proxy/correlation/engine.py
- **Status:** done
- **Changes:** created `proxy/correlation/engine.py` (`CorrelationEngine`, `CorrelationPayload`, `TraceCorrelation`, `CorrelatedSpan`, `CorrelatedLog`), `proxy/correlation/__init__.py`, and `proxy/tests/test_correlation.py`
- **Test result:** `python -m pytest proxy/tests/test_correlation.py -v` — verified trace/log correlation by trace_id, metrics extraction, root service determination, error classification, and JSON serialization — PASS
- **Decisions/deviations:** none. Produces structured evidence joining spans and logs sharing trace IDs with time-window metrics.
- **Next:** Task 4.3 — Build `POST /correlate` route wrapping the engine














### [2026-09-01] — Task 4.3: Build POST /correlate route wrapping the engine
- **Status:** done
- **Changes:** created `proxy/routes/correlate.py` (`correlate_bp` blueprint, `POST /correlate` — validates `start_time`/`end_time`, builds `CorrelationEngine` from `current_app.metrics_adapter` + `CLICKHOUSE_URL`, returns `payload.to_dict()` as JSON with 400s for missing/invalid fields); updated `proxy/app.py` to import and register `correlate_bp`; created `proxy/tests/test_correlate.py` (8 tests: 3 happy-path covering response shape, trace/span/log structure, and exact engine arg forwarding; 4 error-path covering missing `start_time`, missing `end_time`, `end_time <= start_time`, and non-numeric values)
- **Test result:** `python -m pytest proxy/tests/test_correlate.py -v` — 8 passed; full suite `proxy/tests/` — 15 passed, 0 failed — PASS
- **Decisions/deviations:** `CorrelationEngine` is instantiated per-request inside the route (not stored on `app`) — keeps the engine stateless and avoids stale adapter references if config changes between requests; engine is patched at `proxy.routes.correlate.CorrelationEngine` in tests so no real ClickHouse or Prometheus calls are made.
- **Next:** Task 5.1 — Build `proxy/rca/llm_client.py`, provider-agnostic per `.env`'s `LLM_PROVIDER`

### [2026-09-01] — Task 5.1: Build proxy/rca/llm_client.py
- **Status:** done
- **Changes:** created `proxy/rca/__init__.py`; created `proxy/rca/llm_client.py` with `RCAResult` dataclass (id/cause/confidence/evidence/playbook, validation in `__post_init__`, `to_dict`/`from_dict`), `_build_user_message()` prompt builder (bounded to error traces + key metrics, never a raw data dump), `LLMClient` ABC, `MockLLMClient` (deterministic; harvests real error evidence from payload; accepts optional `fixed_response`), `OpenAILLMClient` (JSON-mode via Chat Completions), `AnthropicLLMClient` (JSON-mode via prefill), `create_llm_client()` factory; created `proxy/tests/test_llm_client.py` (21 tests)
- **Test result:** `python -m pytest proxy/tests/test_llm_client.py -v` — 21 passed — PASS
- **Decisions/deviations:** `RCAResult` carries a `uuid` `id` field at creation to support the approval flow in task 6.1 without a later migration. OpenAI uses `gpt-4o-mini` default (cheap, fast, supports JSON mode); Anthropic uses `claude-3-haiku-20240307`. Both can be overridden via kwargs to `create_llm_client()`.
- **Next:** Task 5.2 — POST /rca route

### [2026-09-01] — Task 5.2: Build POST /rca route
- **Status:** done
- **Changes:** created `proxy/routes/rca.py` (`rca_bp`, `POST /rca`: validates start/end, runs `CorrelationEngine.correlate()`, passes `payload.to_dict()` to `create_llm_client().generate()`, returns `RCAResult.to_dict()` as JSON; 400 on invalid input, 500 on correlation or LLM failures with separate error messages); updated `proxy/app.py` to import and register `rca_bp`; created `proxy/tests/test_rca.py` (12 tests)
- **Test result:** `python -m pytest proxy/tests/test_rca.py -v` — 12 passed; full suite `proxy/tests/` — 48 passed, 0 failed — PASS
- **Decisions/deviations:** `CorrelationEngine` and `create_llm_client` are both instantiated per-request (stateless, no stale config). Both are patched at `proxy.routes.rca.*` in tests so no real infra or LLM API calls are made. One test (`test_rca_mock_provider_end_to_end`) uses the real `MockLLMClient` to verify the pipeline works offline without a key.
- **Next:** Task 6.1 — Approval endpoint/state for RCA suggestions (POST /rca/<id>/approve and /reject)

### [2026-09-01] — Task 6.1: Add approval endpoint/state for RCA suggestions
- **Status:** done
- **Changes:** created `proxy/store/__init__.py`; created `proxy/store/rca_store.py` (`StoredRCA` dataclass with id/cause/confidence/evidence/playbook/status/note + `to_dict`/`from_rca_result`; `RCAStore` with thread-safe Lock, `save`/`get`/`approve`/`reject`/`list_all`; `STATUS_PENDING`, `STATUS_APPROVED`, `STATUS_REJECTED` constants); updated `proxy/routes/rca.py` — `POST /rca` now saves result into `app.rca_store` and returns `StoredRCA.to_dict()` (adds `status`/`note` fields); added `GET /rca/<id>`, `POST /rca/<id>/approve`, `POST /rca/<id>/reject` to `rca_bp`; updated `proxy/app.py` to import `RCAStore` and attach as `app.rca_store`; created `proxy/tests/test_approval.py` (33 tests)
- **Test result:** `python -m pytest proxy/tests/test_approval.py -v` — 33 passed; full suite `proxy/tests/` — 81 passed, 0 failed — PASS
- **Decisions/deviations:** `approve`/`reject` accept an optional `note` field in the request body (free-form string) — useful for demo commentary; defaults to `""` when absent or body is empty/missing. `list_all(status=)` added to the store for completeness (7.1 smoke test will use it). No new blueprint needed — all four endpoints live in `rca_bp`.
- **Next:** Task 7.1 — end-to-end smoke test script

### [2026-09-01] — Task 7.1: End-to-end smoke test script
- **Status:** done
- **Changes:** created `scripts/smoke_test.py` — 9-step self-contained smoke test: (1) idempotent `docker compose up -d` (skippable via `--skip-compose`), (2) wait for ClickHouse `/ping`, (3) start Flask proxy subprocess on configurable port, (4) wait for `/health → healthy`, (5) wait for ≥1 row in `otel_traces`, (6) `POST /correlate` — shape assertion, (7) `POST /rca` — all four fields + `status=pending` assertion, (8) `POST /rca/<id>/approve`, (9) `GET /rca/<id>` — persisted `status=approved` + note assertion; exits 0 on all pass, 1 on any failure; stdlib + `requests` only
- **Test result:** `python scripts/smoke_test.py --skip-compose --timeout 60` — all 9 steps passed, exit 0; live output: 36 traces, 13 error traces, impacted `[frontend, loadgenerator, productcatalogservice]`, RCA confidence=0.64, approved and verified — PASS
- **Decisions/deviations:** `--skip-compose` flag added so the script is re-runnable without waiting for a full compose cycle when the stack is already up; proxy is started as a subprocess and terminated in a `finally` block so no port conflicts on re-run; telemetry wait polls ClickHouse directly (no Prometheus dependency) so it works in both Mode A and Mode B.
- **Next:** Task 7.2 — update README.md Quick Start

### [2026-09-01] — Task 7.2: Update README.md Quick Start
- **Status:** done
- **Changes:** rewrote `README.md` — 8-step Quick Start (prerequisites → clone/configure → pip install → stack up → proxy start → API usage with curl examples for all six endpoints → smoke test → Grafana → fault injection); service URL table; full Proxy API reference table (all 6 routes with request shape); test suite command; status section reflecting all phases complete; tear-down command
- **Test result:** verified `git submodule status` (1.11.0 pinned), `python -m pytest proxy/tests/ -q` (81 passed), `curl http://localhost:5000/health` (proxy started by smoke test), all docker compose commands match `docker-compose.yml` profiles and file names exactly — PASS
- **Decisions/deviations:** removed the old placeholder Quick Start (two-line compose commands only) and replaced with complete operational runbook. All commands are exact — no placeholder `<repo-url>` left unexplained; only the Grafana password and LLM key require user action, which is called out explicitly.
- **Next:** all tasks complete — project is demo-ready

### [2026-09-02] — Task 3.3: Make Prometheus published port conditional on ENABLE_PROMETHEUS_UI
- **Status:** done
- **Changes:** `docker-compose.yml` prometheus service changed from `ports: ["9090:9090"]` to `expose: ["9090"]` only; created `docker-compose.prometheus-ui.yml` (adds `ports: ["${PROMETHEUS_PORT:-9090}:9090"]` to prometheus); updated `.env` and `.env.example` with `PROMETHEUS_PORT=9090` and explanatory comment
- **Test result:** (1) Without override file: `docker ps` shows `9090/tcp` (expose only, no host binding), `curl localhost:9090/-/healthy` fails — NOT REACHABLE; `docker exec` health check passes — Prometheus serves data internally. (2) With override file: `docker ps` shows `0.0.0.0:9090->9090/tcp`, `curl localhost:9090/-/healthy` returns "Prometheus Server is Healthy." — PASS
- **Decisions/deviations:** attempted env-var-controlled `published: "${PROMETHEUS_HOST_PORT}"` in long-form ports syntax first — Docker assigned a random ephemeral port when the var was empty instead of omitting the binding, so that approach was dropped. Compose override file is the correct Compose-native mechanism for conditional port publication. `ENABLE_PROMETHEUS_UI` is expressed as "include `docker-compose.prometheus-ui.yml`" rather than a boolean env var, which is consistent with how `STORAGE_MODE` is already expressed via the `--profile mode-a` flag.
- **Next:** Task 7.1 — Scaffold the React SPA (`frontend/`) with routing for `/setup`, `/`, `/telemetry`, `/tools`, `/rca`

### [2026-09-02] — Task 7.1: Scaffold React SPA
- **Status:** done
- **Changes:** created `frontend/` — `package.json` (vite 5.4.8, react 18.3.1, react-router-dom 6.26.2), `vite.config.js` (dev proxy `/api` → `http://localhost:5000`), `index.html`, `src/main.jsx`, `src/App.jsx` (BrowserRouter, 5 routes with `/setup` redirect when no config), `src/api/client.js` (9 typed fetch wrappers), and 5 page components (`Setup.jsx`, `Home.jsx`, `Telemetry.jsx`, `Tools.jsx`, `RCA.jsx`)
- **Test result:** `npm install` required `npm approve-scripts esbuild` before esbuild's postinstall script ran; `npm run build` — exit 0, 39 modules transformed, 174 kB bundle. Preview server at `:4173` served the SPA shell. Each page catches API errors and renders an error message rather than crashing, verified by inspection.
- **Decisions/deviations:** `App.jsx` `getConfig()` error path sets `hasConfig=false` (→ redirect to `/setup`) rather than hanging on `null` — proxy-unreachable at cold start lands on the wizard, not a blank screen. Pages are functional stubs (real data-binding wired to the API contract) rather than purely empty placeholders, so 7.2–7.5 extend them rather than rewrite them. `node_modules/` not committed (`.gitignore` already present from Vite).
- **Next:** Task 7.2 — Build `proxy/routes/config.py`: `GET/POST /api/config`

### [2026-09-02] — Task 7.2: Build proxy/routes/config.py GET/POST /api/config
- **Status:** done (was implemented in repo; MEMORY entry was missing — repaired this session)
- **Changes:** `proxy/routes/config.py` (GET/POST `/api/config`, in-memory `app.wizard_config`, validation + defaults); `proxy/app.py` registers `config_bp`; `proxy/tests/test_config.py`
- **Test result:** `py -3.13 -m pytest proxy/tests/test_config.py -v` — 10 passed (GET empty on first run; POST then GET returns exactly what was saved; validation 400s; defaults applied) — PASS
- **Decisions/deviations:** config is stored in-memory (`app.wizard_config`), not written back to `.env` at runtime — proxy has no Docker socket and cannot restart containers; FRONTEND.md already treats save + displayed compose command as the contract. TASKS.md had 7.2–7.5 checked without MEMORY entries; repo already contained the implementation.
- **Next:** Task 7.3 — Setup wizard confirmation command

### [2026-09-02] — Task 7.3: Setup wizard compose-command confirmation
- **Status:** done (was implemented in repo; MEMORY entry was missing — repaired this session)
- **Changes:** `frontend/src/pages/Setup.jsx` (`buildCommand` from saved form: compose files + `--profile mode-a` for Mode A); command-generation tests in `proxy/tests/test_config.py`
- **Test result:** `py -3.13 -m pytest proxy/tests/test_config.py -v` — Mode A with all tools includes `-f docker-compose.yml`, `-f docker-compose.prometheus-ui.yml`, `-f docker-compose.signoz.yml`, `--profile mode-a`; Mode B without optional files omits those flags — PASS
- **Decisions/deviations:** command is assembled on the client from the saved form (same flags the Python tests assert). Wizard still cannot run compose itself.
- **Next:** Task 7.4 — `GET /api/tools`

### [2026-09-02] — Task 7.4: Build proxy/routes/tools.py GET /api/tools
- **Status:** done (was implemented in repo; MEMORY entry was missing — repaired this session)
- **Changes:** `proxy/routes/tools.py` (Grafana / Prometheus UI / SigNoz links from `wizard_config`); `proxy/tests/test_tools.py`
- **Test result:** `py -3.13 -m pytest proxy/tests/test_tools.py -v` — 7 passed; toggling a tool off removes it from `/api/tools` — PASS
- **Decisions/deviations:** empty `wizard_config` still lists Grafana + Prometheus via `cfg.get(..., default)` so the Tools page is usable before the first save; SigNoz stays off until explicitly enabled.
- **Next:** Task 7.5 — Home + Telemetry pages

### [2026-09-02] — Task 7.5: Home and Telemetry Analysis pages
- **Status:** done (was implemented in repo; MEMORY entry was missing — repaired this session)
- **Changes:** `proxy/routes/api.py` (`GET /api/health`, `GET /api/telemetry/summary`); `frontend/src/pages/Home.jsx`, `Telemetry.jsx`; `proxy/tests/test_api.py`
- **Test result:** `py -3.13 -m pytest proxy/tests/test_api.py -v` — 10 passed (health shape/status, telemetry summary fields/values, ClickHouse-down zeros) — PASS
- **Decisions/deviations:** outbound health/ClickHouse calls are mocked in unit tests so they run without a live stack. Pages bind to those JSON fields (no placeholders). TASKS.md checkbox for 7.5 was already checked.
- **Next:** Task 8.1 — SigNoz compose file + collector config
