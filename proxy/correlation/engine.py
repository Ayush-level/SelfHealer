"""Correlation engine combining metrics, logs, and traces into structured evidence."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
import requests

from proxy.adapters.metrics_adapter import MetricsQueryAdapter, MetricQueryResult


@dataclass
class CorrelatedSpan:
    trace_id: str
    span_id: str
    parent_span_id: str
    service_name: str
    span_name: str
    status_code: str
    status_message: str
    duration_ns: int
    timestamp: float
    attributes: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "service_name": self.service_name,
            "span_name": self.span_name,
            "status_code": self.status_code,
            "status_message": self.status_message,
            "duration_ns": self.duration_ns,
            "timestamp": self.timestamp,
            "attributes": self.attributes,
        }


@dataclass
class CorrelatedLog:
    timestamp: float
    trace_id: str
    span_id: str
    service_name: str
    severity: str
    body: str
    attributes: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "service_name": self.service_name,
            "severity": self.severity,
            "body": self.body,
            "attributes": self.attributes,
        }


@dataclass
class TraceCorrelation:
    trace_id: str
    root_service: str
    services_involved: List[str]
    has_errors: bool
    spans: List[CorrelatedSpan] = field(default_factory=list)
    logs: List[CorrelatedLog] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "root_service": self.root_service,
            "services_involved": self.services_involved,
            "has_errors": self.has_errors,
            "spans": [s.to_dict() for s in self.spans],
            "logs": [l.to_dict() for l in self.logs],
        }


@dataclass
class CorrelationPayload:
    time_window: Dict[str, float]
    services_impacted: List[str]
    total_traces: int
    error_traces: int
    metrics: List[Dict[str, Any]] = field(default_factory=list)
    correlated_traces: List[TraceCorrelation] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "time_window": self.time_window,
            "services_impacted": self.services_impacted,
            "total_traces": self.total_traces,
            "error_traces": self.error_traces,
            "metrics": self.metrics,
            "correlated_traces": [t.to_dict() for t in self.correlated_traces],
        }


class CorrelationEngine:
    """Orchestrates correlation between metrics, logs, and traces."""

    def __init__(
        self,
        metrics_adapter: MetricsQueryAdapter,
        clickhouse_url: str = "http://localhost:8123",
        timeout: float = 10.0,
    ) -> None:
        self.metrics_adapter = metrics_adapter
        self.clickhouse_url = clickhouse_url.rstrip("/")
        self.timeout = timeout

    def _format_datetime64(self, ts: float) -> str:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")

    def _execute_clickhouse_query(self, query: str) -> List[Dict[str, Any]]:
        url = f"{self.clickhouse_url}/"
        full_query = f"{query} FORMAT JSON"
        resp = requests.post(
            url,
            data=full_query.encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", [])

    def fetch_traces(
        self,
        start_time: float,
        end_time: float,
        service_name: Optional[str] = None,
        trace_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[CorrelatedSpan]:
        start_str = self._format_datetime64(start_time)
        end_str = self._format_datetime64(end_time)

        filters = [
            f"Timestamp >= toDateTime64('{start_str}', 9)",
            f"Timestamp <= toDateTime64('{end_str}', 9)",
        ]
        if service_name:
            filters.append(f"ServiceName = '{service_name}'")
        if trace_id:
            filters.append(f"TraceId = '{trace_id}'")

        where_clause = " AND ".join(filters)
        sql = f"""
        SELECT
            TraceId,
            SpanId,
            ParentSpanId,
            ServiceName,
            SpanName,
            StatusCode,
            StatusMessage,
            Duration,
            toUnixTimestamp64Milli(Timestamp) / 1000.0 AS ts,
            SpanAttributes
        FROM otel_traces
        WHERE {where_clause}
        ORDER BY Timestamp ASC
        LIMIT {limit}
        """
        rows = self._execute_clickhouse_query(sql)

        spans: List[CorrelatedSpan] = []
        for row in rows:
            attrs = row.get("SpanAttributes", {})
            if not isinstance(attrs, dict):
                attrs = {}
            spans.append(
                CorrelatedSpan(
                    trace_id=str(row.get("TraceId", "")),
                    span_id=str(row.get("SpanId", "")),
                    parent_span_id=str(row.get("ParentSpanId", "")),
                    service_name=str(row.get("ServiceName", "")),
                    span_name=str(row.get("SpanName", "")),
                    status_code=str(row.get("StatusCode", "")),
                    status_message=str(row.get("StatusMessage", "")),
                    duration_ns=int(row.get("Duration", 0)),
                    timestamp=float(row.get("ts", 0.0)),
                    attributes={str(k): str(v) for k, v in attrs.items()},
                )
            )
        return spans

    def fetch_logs(
        self,
        start_time: float,
        end_time: float,
        trace_ids: Optional[List[str]] = None,
        service_name: Optional[str] = None,
        limit: int = 200,
    ) -> List[CorrelatedLog]:
        start_str = self._format_datetime64(start_time)
        end_str = self._format_datetime64(end_time)

        filters = [
            f"Timestamp >= toDateTime64('{start_str}', 9)",
            f"Timestamp <= toDateTime64('{end_str}', 9)",
        ]
        if trace_ids:
            quoted_ids = ", ".join(f"'{tid}'" for tid in trace_ids if tid)
            if quoted_ids:
                filters.append(f"TraceId IN ({quoted_ids})")
        if service_name:
            filters.append(f"ServiceName = '{service_name}'")

        where_clause = " AND ".join(filters)
        sql = f"""
        SELECT
            toUnixTimestamp64Milli(Timestamp) / 1000.0 AS ts,
            TraceId,
            SpanId,
            ServiceName,
            SeverityText,
            Body,
            LogAttributes
        FROM otel_logs
        WHERE {where_clause}
        ORDER BY Timestamp ASC
        LIMIT {limit}
        """
        rows = self._execute_clickhouse_query(sql)

        logs: List[CorrelatedLog] = []
        for row in rows:
            attrs = row.get("LogAttributes", {})
            if not isinstance(attrs, dict):
                attrs = {}
            logs.append(
                CorrelatedLog(
                    timestamp=float(row.get("ts", 0.0)),
                    trace_id=str(row.get("TraceId", "")),
                    span_id=str(row.get("SpanId", "")),
                    service_name=str(row.get("ServiceName", "")),
                    severity=str(row.get("SeverityText", "")),
                    body=str(row.get("Body", "")),
                    attributes={str(k): str(v) for k, v in attrs.items()},
                )
            )
        return logs

    def correlate(
        self,
        start_time: float,
        end_time: float,
        service_name: Optional[str] = None,
        trace_id: Optional[str] = None,
        metric_names: Optional[List[str]] = None,
    ) -> CorrelationPayload:
        """Query metrics, logs, traces and merge them into structured correlation evidence."""
        # 1. Fetch Traces
        spans = self.fetch_traces(start_time, end_time, service_name=service_name, trace_id=trace_id)

        # Group spans by trace_id
        traces_map: Dict[str, List[CorrelatedSpan]] = {}
        for span in spans:
            traces_map.setdefault(span.trace_id, []).append(span)

        trace_ids = list(traces_map.keys())

        # 2. Fetch Logs correlated with these traces
        logs = self.fetch_logs(start_time, end_time, trace_ids=trace_ids, service_name=service_name)
        logs_map: Dict[str, List[CorrelatedLog]] = {}
        for log in logs:
            if log.trace_id:
                logs_map.setdefault(log.trace_id, []).append(log)

        # 3. Build trace correlation objects
        correlated_traces: List[TraceCorrelation] = []
        services_impacted: Set[str] = set()
        error_traces_count = 0

        for tid, t_spans in traces_map.items():
            t_logs = logs_map.get(tid, [])
            svcs = list({s.service_name for s in t_spans if s.service_name} | {l.service_name for l in t_logs if l.service_name})
            
            # Find root span (parent_span_id empty or not in t_spans)
            span_ids = {s.span_id for s in t_spans}
            root_candidates = [s for s in t_spans if not s.parent_span_id or s.parent_span_id not in span_ids]
            root_svc = root_candidates[0].service_name if root_candidates else (t_spans[0].service_name if t_spans else "unknown")

            has_error = any(s.status_code == "Error" for s in t_spans) or any(l.severity.upper() in ("ERROR", "FATAL") for l in t_logs)
            if has_error:
                error_traces_count += 1
                services_impacted.update(svcs)

            correlated_traces.append(
                TraceCorrelation(
                    trace_id=tid,
                    root_service=root_svc,
                    services_involved=svcs,
                    has_errors=has_error,
                    spans=t_spans,
                    logs=t_logs,
                )
            )

        # 4. Fetch metrics for the window
        metrics_payload: List[Dict[str, Any]] = []
        if metric_names is None:
            available = self.metrics_adapter.get_available_metrics()
            # Select key application metrics if available
            metric_names = [m for m in available if any(k in m for k in ("rpc", "cpu", "error", "duration", "test"))][:5]

        for m_name in metric_names:
            try:
                res = self.metrics_adapter.query_range(
                    m_name, start_time, end_time, step_seconds=15, service_name=service_name
                )
                metrics_payload.append(res.to_dict())
            except Exception:
                pass

        return CorrelationPayload(
            time_window={"start": start_time, "end": end_time},
            services_impacted=sorted(list(services_impacted)),
            total_traces=len(correlated_traces),
            error_traces=error_traces_count,
            metrics=metrics_payload,
            correlated_traces=correlated_traces,
        )
