"""Prometheus Metrics Query Adapter (Mode A)."""

from typing import Any, Dict, List, Optional
import requests

from proxy.adapters.metrics_adapter import (
    MetricQueryResult,
    MetricSample,
    MetricSeries,
    MetricsQueryAdapter,
)


class PrometheusAdapter(MetricsQueryAdapter):
    """Queries metrics from Prometheus using PromQL HTTP API."""

    def __init__(self, base_url: str = "http://prometheus:9090", timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _build_selector(self, metric_name: str, service_name: Optional[str] = None) -> str:
        if service_name:
            return f'{metric_name}{{job=~"{service_name}|.*{service_name}.*"}}'
        return metric_name

    def query_range(
        self,
        metric_name: str,
        start_time: float,
        end_time: float,
        step_seconds: int = 15,
        service_name: Optional[str] = None,
    ) -> MetricQueryResult:
        query = self._build_selector(metric_name, service_name)
        url = f"{self.base_url}/api/v1/query_range"
        params = {
            "query": query,
            "start": str(start_time),
            "end": str(end_time),
            "step": f"{step_seconds}s",
        }
        resp = requests.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()

        series_list: List[MetricSeries] = []
        if data.get("status") == "success" and "data" in data:
            results = data["data"].get("result", [])
            for res in results:
                metric_labels = res.get("metric", {})
                labels = {k: v for k, v in metric_labels.items() if k != "__name__"}
                if "job" in labels and "service_name" not in labels:
                    labels["service_name"] = labels["job"]
                samples = [
                    MetricSample(timestamp=float(val[0]), value=float(val[1]))
                    for val in res.get("values", [])
                ]
                series_list.append(
                    MetricSeries(metric_name=metric_name, labels=labels, samples=samples)
                )

        return MetricQueryResult(metric_name=metric_name, series=series_list)

    def query_instant(
        self,
        metric_name: str,
        timestamp: Optional[float] = None,
        service_name: Optional[str] = None,
    ) -> MetricQueryResult:
        query = self._build_selector(metric_name, service_name)
        url = f"{self.base_url}/api/v1/query"
        params: Dict[str, Any] = {"query": query}
        if timestamp is not None:
            params["time"] = str(timestamp)
        resp = requests.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()

        series_list: List[MetricSeries] = []
        if data.get("status") == "success" and "data" in data:
            results = data["data"].get("result", [])
            for res in results:
                metric_labels = res.get("metric", {})
                labels = {k: v for k, v in metric_labels.items() if k != "__name__"}
                if "job" in labels and "service_name" not in labels:
                    labels["service_name"] = labels["job"]
                value_tuple = res.get("value")
                samples = []
                if value_tuple and len(value_tuple) == 2:
                    samples.append(
                        MetricSample(timestamp=float(value_tuple[0]), value=float(value_tuple[1]))
                    )
                series_list.append(
                    MetricSeries(metric_name=metric_name, labels=labels, samples=samples)
                )

        return MetricQueryResult(metric_name=metric_name, series=series_list)

    def get_available_metrics(self) -> List[str]:
        url = f"{self.base_url}/api/v1/label/__name__/values"
        resp = requests.get(url, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "success" and "data" in data:
            return list(data["data"])
        return []
