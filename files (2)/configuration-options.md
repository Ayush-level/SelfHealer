# Configuration Options Reference

This document lists every configuration option the setup wizard could expose,
grouped by section. Each option has a **Status** tag:

- **Active** — buildable and functional in the current build.
- **Disabled (roadmap)** — shown in the UI for completeness/vision, but not
  functional yet; greyed out or marked "coming soon."

---

## 1. Root Account Setup

**Status: Active (stubbed backend for now)**

| Option | Description | Values |
|---|---|---|
| Username / Email | Identifies the admin account | Free text |
| Password | Account password | Free text, min-length + complexity rule once real auth exists |
| Confirm Password | Re-entry to catch typos | Free text, must match Password |
| Organization / Instance Name | Display label for this install | Free text, optional |

---

## 2. Visualization Tool Selection

**Status: Active — independent toggles, not a single choice**

| Option | Description | Values |
|---|---|---|
| Enable Grafana | Whether Grafana is provisioned and linked | On/Off, default On |
| Grafana Admin Username | Login for the Grafana instance itself (separate from platform root account) | Free text |
| Grafana Admin Password | Login password for Grafana | Free text |
| Grafana Port | Port to expose Grafana on | Default `3000`, editable |
| Enable Prometheus GUI | Whether Prometheus's own web UI is published/linked — independent of using Prometheus as storage in Mode A | On/Off, default On |
| Prometheus Port | Port to expose Prometheus's UI on | Default `9090`, editable |
| Enable SigNoz | Whether the SigNoz stack (dedicated collector + query service + frontend) is provisioned and linked | On/Off, default Off |
| SigNoz Port | Port to expose the SigNoz frontend on | Default `8080`, editable |

SigNoz uses a dual-collector design — a second, dedicated OTel Collector
receives a forwarded copy of all telemetry and writes it into its own
`signoz_*` ClickHouse schema, separate from the `otel_*` schema Grafana and
the correlation engine use. See `ARCHITECTURE.md`'s SigNoz Integration
section for the full mechanism.

---

## 3. Telemetry Ingestion Settings

**Status: Active**

| Option | Description | Values |
|---|---|---|
| Signal Types to Collect | Which telemetry types the collector accepts | Checkboxes: `Metrics` · `Logs` · `Traces` |
| OTLP gRPC Port | Port for gRPC OTLP receiver | Default `4317`, editable |
| OTLP HTTP Port | Port for HTTP OTLP receiver | Default `4318`, editable |
| Trace Sampling Rate | Fraction of traces actually stored | `100%` · `10%` · `1%` · `Custom %` |

---

## 4. Storage Configuration

**Status: Active**

### Prometheus (Metrics)

| Option | Description | Values |
|---|---|---|
| Scrape Interval | How often Prometheus pulls from the OTel Collector's metrics endpoint | `5s` · `15s` (Prometheus default) · `30s` · `60s` |
| Retention Period | How long metric history is kept | `7 days` · `15 days` · `30 days` · `Custom` |

### ClickHouse (Logs & Traces)

| Option | Description | Values |
|---|---|---|
| Retention (TTL) | How long logs/traces are kept before deletion | `3 days` · `7 days` · `30 days` · `Custom` |
| Storage Source | Whether the platform provisions ClickHouse or connects to an existing one | `Let platform provision ClickHouse` · `Connect to existing instance` |
| External Host *(conditional)* | ClickHouse host, only shown if "existing instance" chosen | Free text (hostname/IP) |
| External Port *(conditional)* | ClickHouse port | Default `9000`, editable |
| External Database Name *(conditional)* | Target database on the external instance | Free text |
| External Credentials *(conditional)* | Auth for the external instance | Username / password fields |

---

## 5. Service Registration

**Status: Active (limited — fixed simulator names for now)**

| Option | Description | Values |
|---|---|---|
| Service Name(s) | Identifies each monitored service; used as the `service.name` tag | Free text, one or more entries |
| Environment Tag | Separates environments within one install | `Production` · `Staging` · `Development` |

---

## 6. Correlation Engine Settings

**Status: Active**

| Option | Description | Values |
|---|---|---|
| Correlation Time Window | How wide a window the correlation engine searches around an anomaly timestamp | `±30 seconds` · `±1 minute` · `±5 minutes` · `Custom` |
| Join Key | Field used to match logs/traces to a metric anomaly | `trace_id` (fixed, not user-editable at this stage) |

---

## 7. LLM / RCA Configuration

**Status: Active**

| Option | Description | Values |
|---|---|---|
| LLM Provider | Which API generates the RCA output | `Claude` · `OpenAI` · `Other (custom endpoint)` |
| API Key | Credential for the chosen provider | Free text, stored securely, never re-displayed in plaintext |
| RCA Trigger Mode | When the LLM is invoked | `On-demand (manual "Analyze" click)` · `Automatic (scheduled polling)` |
| Automatic Interval *(conditional)* | How often the scheduler runs, only shown if Automatic is chosen | Minutes, e.g. `5` · `15` · `30` · `Custom` — this is scheduled polling, not anomaly-detection triggering (see Section 11) |
| Minimum Confidence to Display | Hides low-confidence RCA output as noise | Percentage slider, e.g. `0–100%`, default `0` (show all) |

---

## 8. Access Control

**Status: Disabled (roadmap) — single-user only for now**

| Option | Description | Values |
|---|---|---|
| Access Granularity | How fine-grained permissions are | `Coarse (Admin / Viewer)` · `Fine-grained (per-service, per-field)` |
| Role Assignment | Assign roles to additional users | User list with role dropdown per user |
| Field Masking | Redact sensitive log fields per role | Toggle per field, e.g. mask IP addresses, user IDs |

---

## 9. Multi-Tenancy

**Status: Disabled (roadmap) — undecided**

| Option | Description | Values |
|---|---|---|
| Deployment Mode | Whether one install serves one org or many | `Single-tenant` · `Multi-tenant` |
| Tenant Isolation Level *(conditional)* | How strictly tenant data is separated, only relevant if multi-tenant | `Shared storage, filtered queries` · `Fully separate storage per tenant` |

---

## 10. Notifications

**Status: Disabled (roadmap)**

| Option | Description | Values |
|---|---|---|
| Notification Channel | Where alerts/RCA results are sent | `Email` · `Slack webhook` · `None` |
| Notification Trigger | What causes a notification | `New RCA suggestion available` · `Anomaly detected` · `Both` |
| Webhook URL *(conditional)* | Destination for Slack/other webhook | Free text URL, only shown if a webhook channel is selected |

---

## 11. Alerting / Anomaly Detection

**Status: Disabled (roadmap)** — this is distinct from RCA's "Automatic"
trigger mode in Section 7, which is scheduled polling, not this. No
statistical or threshold-based anomaly trigger exists yet.

| Option | Description | Values |
|---|---|---|
| Detection Method | How an anomaly is flagged to trigger RCA | `Static threshold` · `Statistical (e.g. stddev from baseline)` · `None (manual only)` |
| Threshold Value *(conditional)* | The numeric trigger point, only shown for static thresholds | Free text / number input, per metric |

---

## 12. Backup & Data Export

**Status: Disabled (roadmap)**

| Option | Description | Values |
|---|---|---|
| Backup Schedule | How often stored data is backed up | `Off` · `Daily` · `Weekly` |
| Export Format | Format for manual data export | `CSV` · `JSON` · `Parquet` |

---

## 13. Branding / Theming

**Status: Disabled (roadmap) — low priority**

| Option | Description | Values |
|---|---|---|
| Instance Theme | Visual theme for the platform's own UI | `Light` · `Dark` · `System default` |
| Logo Upload | Custom logo for a white-labeled install | Image file upload |

---

## Summary Table — Status at a Glance

| Section | Status |
|---|---|
| 1. Root Account Setup | Active (stubbed backend) |
| 2. Visualization Tool Selection | Active (Grafana, Prometheus GUI, and SigNoz — independent toggles) |
| 3. Telemetry Ingestion Settings | Active |
| 4. Storage Configuration | Active |
| 5. Service Registration | Active (limited) |
| 6. Correlation Engine Settings | Active |
| 7. LLM / RCA Configuration | Active |
| 8. Access Control | Disabled (roadmap) |
| 9. Multi-Tenancy | Disabled (roadmap) |
| 10. Notifications | Disabled (roadmap) |
| 11. Alerting / Anomaly Detection | Disabled (roadmap) |
| 12. Backup & Data Export | Disabled (roadmap) |
| 13. Branding / Theming | Disabled (roadmap) |
