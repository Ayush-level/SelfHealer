"""ClickHouse Metrics Query Adapter (Mode B)."""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
import requests

from proxy.adapters.metrics_adapter import (
    MetricQueryResult,
    MetricSample,
    MetricSeries,
    MetricsQueryAdapter,
)


class ClickHouseMetricsAdapter(MetricsQueryAdapter):
    """Queries metrics from ClickHouse otel_metrics_* tables (Mode B)."""

    def __init__(self, base_url: str = "http://clickhouse:8123", timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _format_datetime64(self, ts: float) -> str:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")

    def _execute_query(self, query: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/"
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

    def query_range(
        self,
        metric_name: str,
        start_time: float,
        end_time: float,
        step_seconds: int = 15,
        service_name: Optional[str] = None,
    ) -> MetricQueryResult:
        start_str = self._format_datetime64(start_time)
        end_str = self._format_datetime64(end_time)

        service_filter = ""
        if service_name:
            service_filter = f" AND ServiceName = '{service_name}'"

        sql = f"""
        SELECT
            MetricName,
            ServiceName,
            Attributes,
            toUnixTimestamp64Milli(TimeUnix) / 1000.0 AS timestamp,
            toFloat64(Value) AS value
        FROM (
            SELECT MetricName, ServiceName, Attributes, TimeUnix, Value
            FROM otel_metrics_gauge
            WHERE MetricName = '{metric_name}'
              AND TimeUnix >= toDateTime64('{start_str}', 9)
              AND TimeUnix <= toDateTime64('{end_str}', 9)
              {service_filter}
            UNION ALL
            SELECT MetricName, ServiceName, Attributes, TimeUnix, Value
            FROM otel_metrics_sum
            WHERE MetricName = '{metric_name}'
              AND TimeUnix >= toDateTime64('{start_str}', 9)
              AND TimeUnix <= toDateTime64('{end_str}', 9)
              {service_filter}
        )
        ORDER BY timestamp ASC
        """
        rows = self._execute_query(sql)

        # Group by series (ServiceName + Attributes)
        series_map: Dict[str, MetricSeries] = {}
        for row in rows:
            svc = row.get("ServiceName", "")
            raw_attrs = row.get("Attributes", {})
            labels: Dict[str, str] = {}
            if svc:
                labels["service_name"] = svc
                labels["job"] = svc
            if isinstance(raw_attrs, dict):
                for k, v in raw_attrs.items():
                    labels[str(k)] = str(v)

            labels_key = json.dumps(labels, sort_keys=True)
            if labels_key not in series_map:
                series_map[labels_key] = MetricSeries(
                    metric_name=metric_name,
                    labels=labels,
                    samples=[],
                )
            series_map[labels_key].samples.append(
                MetricSample(
                    timestamp=float(row["timestamp"]),
                    value=float(row["value"]),
                )
            )

        return MetricQueryResult(
            metric_name=metric_name,
            series=list(series_map.values()),
        )

    def query_instant(
        self,
        metric_name: str,
        timestamp: Optional[float] = None,
        service_name: Optional[str] = None,
    ) -> MetricQueryResult:
        if timestamp is None:
            ts_clause = "NOW()"
        else:
            ts_str = self._format_datetime64(timestamp)
            ts_clause = f"toDateTime64('{ts_str}', 9)"

        service_filter = ""
        if service_name:
            service_filter = f" AND ServiceName = '{service_name}'"

        sql = f"""
        SELECT
            MetricName,
            ServiceName,
            Attributes,
            toUnixTimestamp64Milli(TimeUnix) / 1000.0 AS timestamp,
            toFloat64(Value) AS value
        FROM (
            SELECT MetricName, ServiceName, Attributes, TimeUnix, Value
            FROM otel_metrics_gauge
            WHERE MetricName = '{metric_name}'
              AND TimeUnix <= {ts_clause}
              {service_filter}
            UNION ALL
            SELECT MetricName, ServiceName, Attributes, TimeUnix, Value
            FROM otel_metrics_sum
            WHERE MetricName = '{metric_name}'
              AND TimeUnix <= {ts_clause}
              {service_filter}
        )
        ORDER BY timestamp DESC
        LIMIT 100
        """
        rows = self._execute_query(sql)

        # Keep latest sample per series
        series_map: Dict[str, MetricSeries] = {}
        for row in rows:
            svc = row.get("ServiceName", "")
            raw_attrs = row.get("Attributes", {})
            labels: Dict[str, str] = {}
            if svc:
                labels["service_name"] = svc
                labels["job"] = svc
            if isinstance(raw_attrs, dict):
                for k, v in raw_attrs.items():
                    labels[str(k)] = str(v)

            labels_key = json.dumps(labels, sort_keys=True)
            if labels_key not in series_map:
                series_map[labels_key] = MetricSeries(
                    metric_name=metric_name,
                    labels=labels,
                    samples=[
                        MetricSample(
                            timestamp=float(row["timestamp"]),
                            value=float(row["value"]),
                        )
                    ],
                )

        return MetricQueryResult(
            metric_name=metric_name,
            series=list(series_map.values()),
        )

    def get_available_metrics(self) -> List[str]:
        sql = """
        SELECT DISTINCT MetricName FROM (
            SELECT DISTINCT MetricName FROM otel_metrics_gauge
            UNION DISTINCT
            SELECT DISTINCT MetricName FROM otel_metrics_sum
        )
        ORDER BY MetricName ASC
        """
        rows = self._execute_query(sql)
        return [row["MetricName"] for row in rows if "MetricName" in row]
