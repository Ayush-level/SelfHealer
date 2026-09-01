# Frontend

A React SPA under `frontend/`, talking to the Flask proxy exclusively
through its JSON API — no server-rendered pages. (React is the default here
since it wasn't pinned to a specific framework; swap for Vue by adjusting
the `frontend/` scaffold — the API contract below is framework-agnostic.)

## Pages

| Route | Purpose |
|---|---|
| `/setup` | First-run configuration wizard — ports, storage mode, which tools to enable, RCA trigger mode. Shown automatically when `GET /api/config` reports no saved config. |
| `/` (Home) | Overall health: which services are reachable, at a glance. |
| `/telemetry` | Overall analysis view of collected telemetry (recent volume, services seen, error rate trend). |
| `/tools` | Direct links to enabled tool GUIs — Grafana, Prometheus (if its GUI toggle is on), SigNoz (if enabled). |
| `/rca` | RCA results list, manual trigger control, approve/reject actions. |

## API Contract (Flask backend)

| Method & Path | Purpose |
|---|---|
| `GET /api/config` | Current saved configuration, or empty if first run. |
| `POST /api/config` | Save wizard config — writes to `.env`/config store. Does **not** restart anything (see below). |
| `GET /api/health` | Aggregated HTTP health-check results per service. |
| `GET /api/telemetry/summary` | Data for the Telemetry Analysis view. |
| `GET /api/tools` | List of enabled tool links + URLs, derived from saved config. |
| `POST /api/rca/trigger` | Manual RCA trigger for a given time window. |
| `GET /api/rca/results` | RCA result history. |
| `POST /api/rca/<id>/approve` | Approve a suggestion. |
| `POST /api/rca/<id>/reject` | Reject a suggestion. |

## First-Run Setup Wizard — and Its Real Limits

The wizard collects: ports for each service, storage mode (A/B), which
tools to enable (Grafana / Prometheus GUI / SigNoz, each an independent
toggle — not a single choice), and RCA trigger mode (manual, or automatic
with an interval in minutes).

**What it can actually do, given the proxy has no Docker socket access**
(see `ARCHITECTURE.md`'s Container Health Monitoring section for why):

- ✅ Validate the input and save it via `POST /api/config` (writes `.env`
  values and the Compose profile selection).
- ❌ It cannot itself run `docker compose up`, restart containers, or change
  which ports are actually published — that requires a command at the host
  level, outside any container, which nothing without Docker access can do.

**Resolution:** after saving, the wizard's confirmation screen displays the
exact command to run, assembled from the saved config, e.g.:

```
docker compose -f docker-compose.yml -f docker-compose.otel-demo-override.yml \
  -f docker-compose.signoz.yml --profile mode-a up -d
```

The user copies and runs it. This is a deliberate trade-off from choosing
HTTP-only health checks over Docker socket access, not a missing feature —
don't try to "fix" it by adding Docker socket access without revisiting
that decision explicitly first.

## Tool Links Page Logic

`/tools` renders whatever `GET /api/tools` returns — it doesn't hardcode
which tools exist. `GET /api/tools` itself just reads the saved config and
returns a URL for each `enabled: true` entry (Grafana, Prometheus GUI,
SigNoz). Adding a future tool means adding it to the config schema and the
adapter behind `/api/tools`, not touching the frontend.

## RCA Page Logic

Manual mode: the page's "Analyze" button posts a time window to
`/api/rca/trigger` and polls `/api/rca/results` for the outcome.

Automatic mode: the page just lists results from `/api/rca/results` as they
appear — the scheduler (`proxy/scheduler/rca_scheduler.py`) is producing
them in the background on the configured interval, the frontend doesn't
trigger anything itself in this mode.

Every result, regardless of trigger mode, shows Approve/Reject controls —
trigger mode changes how a suggestion is generated, never whether it needs
human approval.
