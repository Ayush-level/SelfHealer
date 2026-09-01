# Self-Healing AI Operations Controller

A self-hosted telemetry pipeline that collects metrics, logs, and traces,
correlates them automatically, and uses an LLM to suggest a root cause —
with a human approving before anything is acted on.

## Quick Start

```bash
git submodule update --init --recursive   # pulls in the OpenTelemetry Demo
cp .env.example .env                       # fill in LLM_API_KEY and Grafana admin creds

# Mode A — Prometheus + ClickHouse (default, recommended for demo)
docker compose -f docker-compose.yml -f docker-compose.otel-demo-override.yml --profile mode-a up -d

# Mode B — ClickHouse-only (lighter footprint, no Prometheus)
STORAGE_MODE=clickhouse_only docker compose -f docker-compose.yml -f docker-compose.otel-demo-override.yml up -d
```

Telemetry comes from the [OpenTelemetry Demo](https://github.com/open-telemetry/opentelemetry-demo)
(real microservices + load generator), not synthetic data — see
`ARCHITECTURE.md`'s Telemetry Source section for how it's wired in and how
to trigger a real fault via its feature-flag service.

Then:
- Grafana: `http://localhost:3000`
- Proxy API: `http://localhost:5000/health`
- Prometheus (Mode A only): `http://localhost:9090`
- ClickHouse HTTP: `http://localhost:8123`

## Documentation

| File | What it covers |
|---|---|
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | System design, storage modes, network/volume layout, repo structure |
| [`FRONTEND.md`](./FRONTEND.md) | React SPA pages, API contract, setup wizard flow and its real limits |
| [`TASKS.md`](./TASKS.md) | Phase-by-phase implementation plan, broken into testable tasks |
| [`AGENT.md`](./AGENT.md) | Instructions for an AI coding agent working in this repo |
| [`SKILLS.md`](./SKILLS.md) | Skills/knowledge areas the agent should draw on, plus recommended MCP servers |
| [`MEMORY.md`](./MEMORY.md) | Running implementation log, updated after each completed task |
| [`docs/configuration-options.md`](./docs/configuration-options.md) | Full setup-wizard configuration reference |

## Status

Hackathon build. Current scope: single-user (stubbed auth), Grafana and
SigNoz both active as independently-toggleable visualization tools, both
storage modes (A/B) implemented behind a Compose profile switch, a React
SPA frontend with a setup wizard, and manual/automatic (scheduled-polling)
RCA trigger modes. See `TASKS.md` for exact progress.
