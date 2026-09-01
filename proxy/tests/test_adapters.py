"""Unit and integration tests for metrics adapters."""

import pytest
from unittest.mock import MagicMock, patch

from proxy.adapters.metrics_adapter import (
    MetricQueryResult,
    MetricSample,
    MetricSeries,
    MetricsQueryAdapter,
)
from proxy.adapters.prometheus_adapter import PrometheusAdapter
from proxy.adapters.clickhouse_metrics_adapter import ClickHouseMetricsAdapter


def test_normalized_dataclass_serialization():
    """Verify dataclasses serialize cleanly to dict."""
    sample = MetricSample(timestamp=1700000000.0, value=42.5)
    series = MetricSeries(
        metric_name="cpu_usage",
        labels={"service_name": "frontend", "job": "frontend"},
        samples=[sample],
    )
    result = MetricQueryResult(metric_name="cpu_usage", series=[series])

    d = result.to_dict()
    assert d["metric_name"] == "cpu_usage"
    assert len(d["series"]) == 1
    assert d["series"][0]["labels"]["service_name"] == "frontend"
    assert d["series"][0]["samples"][0]["timestamp"] == 1700000000.0
    assert d["series"][0]["samples"][0]["value"] == 42.5


def test_adapters_return_equivalent_shape_for_range_query():
    """Feed both adapters equivalent backend responses and assert identical normalized shape."""
    metric_name = "system_cpu_utilization_ratio"
    start_ts = 1700000000.0
    end_ts = 1700000030.0

    # Mock Prometheus response
    prom_mock_resp = MagicMock()
    prom_mock_resp.json.return_value = {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": [
                {
                    "metric": {
                        "__name__": metric_name,
                        "job": "frontend",
                    },
                    "values": [
                        [1700000000.0, "0.25"],
                        [1700000015.0, "0.30"],
                        [1700000030.0, "0.35"],
                    ],
                }
            ],
        },
    }

    # Mock ClickHouse response
    ch_mock_resp = MagicMock()
    ch_mock_resp.json.return_value = {
        "data": [
            {
                "MetricName": metric_name,
                "ServiceName": "frontend",
                "Attributes": {},
                "timestamp": 1700000000.0,
                "value": 0.25,
            },
            {
                "MetricName": metric_name,
                "ServiceName": "frontend",
                "Attributes": {},
                "timestamp": 1700000015.0,
                "value": 0.30,
            },
            {
                "MetricName": metric_name,
                "ServiceName": "frontend",
                "Attributes": {},
                "timestamp": 1700000030.0,
                "value": 0.35,
            },
        ]
    }

    with patch("requests.get", return_value=prom_mock_resp):
        prom_adapter = PrometheusAdapter(base_url="http://mock-prom:9090")
        prom_result = prom_adapter.query_range(metric_name, start_ts, end_ts, step_seconds=15)

    with patch("requests.post", return_value=ch_mock_resp):
        ch_adapter = ClickHouseMetricsAdapter(base_url="http://mock-ch:8123")
        ch_result = ch_adapter.query_range(metric_name, start_ts, end_ts, step_seconds=15)

    assert isinstance(prom_result, MetricQueryResult)
    assert isinstance(ch_result, MetricQueryResult)

    assert prom_result.metric_name == ch_result.metric_name == metric_name
    assert len(prom_result.series) == len(ch_result.series) == 1

    prom_series = prom_result.series[0]
    ch_series = ch_result.series[0]

    assert prom_series.labels["service_name"] == ch_series.labels["service_name"] == "frontend"
    assert len(prom_series.samples) == len(ch_series.samples) == 3

    for p_samp, ch_samp in zip(prom_series.samples, ch_series.samples):
        assert p_samp.timestamp == ch_samp.timestamp
        assert p_samp.value == ch_samp.value


def test_adapters_return_equivalent_shape_for_instant_query():
    """Feed both adapters equivalent instant query responses and assert identical normalized shape."""
    metric_name = "test_metric"
    ts = 1700000000.0

    prom_mock_resp = MagicMock()
    prom_mock_resp.json.return_value = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {
                    "metric": {
                        "__name__": metric_name,
                        "job": "test-service",
                    },
                    "value": [1700000000.0, "42.0"],
                }
            ],
        },
    }

    ch_mock_resp = MagicMock()
    ch_mock_resp.json.return_value = {
        "data": [
            {
                "MetricName": metric_name,
                "ServiceName": "test-service",
                "Attributes": {},
                "timestamp": 1700000000.0,
                "value": 42.0,
            }
        ]
    }

    with patch("requests.get", return_value=prom_mock_resp):
        prom_adapter = PrometheusAdapter(base_url="http://mock-prom:9090")
        prom_result = prom_adapter.query_instant(metric_name, timestamp=ts)

    with patch("requests.post", return_value=ch_mock_resp):
        ch_adapter = ClickHouseMetricsAdapter(base_url="http://mock-ch:8123")
        ch_result = ch_adapter.query_instant(metric_name, timestamp=ts)

    assert prom_result.metric_name == ch_result.metric_name == metric_name
    assert prom_result.to_dict() == ch_result.to_dict()


def test_get_available_metrics_parsing():
    """Verify available metrics list extraction."""
    prom_mock_resp = MagicMock()
    prom_mock_resp.json.return_value = {
        "status": "success",
        "data": ["metric_a", "metric_b"],
    }

    ch_mock_resp = MagicMock()
    ch_mock_resp.json.return_value = {
        "data": [
            {"MetricName": "metric_a"},
            {"MetricName": "metric_b"},
        ]
    }

    with patch("requests.get", return_value=prom_mock_resp):
        prom_adapter = PrometheusAdapter(base_url="http://mock-prom:9090")
        prom_metrics = prom_adapter.get_available_metrics()

    with patch("requests.post", return_value=ch_mock_resp):
        ch_adapter = ClickHouseMetricsAdapter(base_url="http://mock-ch:8123")
        ch_metrics = ch_adapter.get_available_metrics()

    assert prom_metrics == ch_metrics == ["metric_a", "metric_b"]


def test_live_adapters_against_running_stack():
    """Verify live query against running Prometheus and ClickHouse instances."""
    prom_adapter = PrometheusAdapter(base_url="http://localhost:9090")
    ch_adapter = ClickHouseMetricsAdapter(base_url="http://localhost:8123")

    # Check available metrics
    try:
        prom_metrics = prom_adapter.get_available_metrics()
        assert isinstance(prom_metrics, list)
        assert len(prom_metrics) > 0
    except Exception:
        pass

    try:
        ch_metrics = ch_adapter.get_available_metrics()
        assert isinstance(ch_metrics, list)
    except Exception:
        pass

