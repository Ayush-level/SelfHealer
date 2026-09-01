# Skills Reference

Knowledge domains this project draws on, mapped to where they apply. Use
this to know what to look up or verify (via search or docs) when a task
touches an area you're not fully certain about — don't guess at syntax for
these, they're easy to get subtly wrong.

| Domain | Applies to | Notes |
|---|---|---|
| Docker Compose (profiles, networks, named volumes) | `docker-compose.yml`, Phase 1–2 tasks | Profiles gate Mode A's Prometheus service — get the `profiles:` key exactly right, it's easy to typo into "always runs." |
| Flask (app factory, blueprints) | `proxy/app.py`, all route files | Don't use a single flat `app.py` with all routes — blueprints per `ARCHITECTURE.md`'s file layout. |
| pytest | `proxy/tests/`, every task's test step | Every task needs a real, running test — not a manual "looks right" check. |
| OpenTelemetry Collector config (YAML pipelines/exporters) | `config/otel-collector-config-*.yaml` | Mode A and Mode B configs differ only in the metrics pipeline's exporter target — keep logs/traces pipelines identical between the two files to avoid silent drift. |
| PromQL | `PrometheusAdapter`, Mode A | Used only inside the adapter — nothing else in the codebase should assume PromQL is available. |
| ClickHouse SQL (incl. `otel_metrics_*` tables) | `ClickHouseMetricsAdapter`, Mode B | This is hand-written SQL replacing what PromQL would normally express — check actual `otel_metrics_gauge`/`otel_metrics_sum` schema before writing queries, don't assume column names. |
| Grafana provisioning (datasource YAML) | `config/grafana/provisioning/` | Standard admin login only — see the security note in `ARCHITECTURE.md` before touching auth-related env vars. |
| Structured LLM prompting (JSON-mode output) | `rca/llm_client.py` | The LLM must only ever receive correlated evidence, never a raw data dump — this is a correctness requirement, not a style preference. |
| OpenTelemetry Demo (Astronomy Shop) — compose structure, `OTEL_EXPORTER_OTLP_ENDPOINT` override, feature-flag fault injection | `otel-demo/`, `docker-compose.otel-demo-override.yml`, Tasks 1.4–1.7 | Don't run the demo's own collector/Jaeger/Prometheus/Grafana — only its microservices, load generator, and feature-flag service point at our collector. |

## Recommended MCP Servers

These aren't required, but if available they remove a lot of manual
context-fetching during implementation:

- **GitHub MCP server** — for repo/PR/issue operations if this project
  lives in a GitHub repo, instead of shelling out to `gh` or asking the
  human to paste diffs.
- **Docker MCP** — if available in your MCP directory, for inspecting
  running containers/logs directly instead of asking the human to paste
  `docker logs` output.
- **ClickHouse MCP server** (official: `ClickHouse/mcp-clickhouse`) — lets
  the agent run read-only `SELECT` queries against the running ClickHouse
  instance directly, useful for verifying `otel_logs`/`otel_traces`/
  `otel_metrics_*` actually contain what a task expects, without a human
  running `curl`/`clickhouse-client` manually.
- **Grafana MCP server** (official: `grafana/mcp-grafana`) — lets the agent
  verify a datasource is actually healthy or a dashboard actually renders,
  rather than asking the human to check the UI.

Check your own MCP directory for current availability/setup — server names
and install methods change; verify before assuming one is present.

## Recommended Skills (Claude Skills catalog)

If this project's Claude Code/Cowork setup has an organization skills
catalog, search it for: `docker`, `flask` or `python-api`, `pytest`/testing,
and `technical-documentation` before assuming none exist — a matching skill
usually encodes team-specific conventions worth following over generic
defaults. If none are found, the conventions in `AGENT.md` are the fallback.
