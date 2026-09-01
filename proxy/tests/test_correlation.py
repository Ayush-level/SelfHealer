"""Unit tests for Correlation Engine."""

import pytest
from unittest.mock import MagicMock

from proxy.adapters.metrics_adapter import MetricQueryResult, MetricSeries, MetricSample
from proxy.correlation.engine import (
    CorrelationEngine,
    CorrelationPayload,
    TraceCorrelation,
    CorrelatedSpan,
    CorrelatedLog,
)


def test_correlation_engine_merges_seeded_data():
    """Unit test against seeded fake data returns the expected merged shape."""
    mock_adapter = MagicMock()
    mock_adapter.get_available_metrics.return_value = ["rpc_server_duration_milliseconds"]
    mock_adapter.query_range.return_value = MetricQueryResult(
        metric_name="rpc_server_duration_milliseconds",
        series=[
            MetricSeries(
                metric_name="rpc_server_duration_milliseconds",
                labels={"service_name": "productcatalogservice"},
                samples=[MetricSample(timestamp=1700000000.0, value=250.0)],
            )
        ],
    )

    engine = CorrelationEngine(
        metrics_adapter=mock_adapter,
        clickhouse_url="http://mock-ch:8123",
    )

    # Seeded fake traces
    fake_traces = [
        CorrelatedSpan(
            trace_id="trace-12345",
            span_id="span-001",
            parent_span_id="",
            service_name="frontend",
            span_name="GET /product/OLJCESPC7Z",
            status_code="Error",
            status_message="13 INTERNAL: Error: ProductCatalogService Fail",
            duration_ns=150000000,
            timestamp=1700000000.0,
            attributes={"http.status_code": "500"},
        ),
        CorrelatedSpan(
            trace_id="trace-12345",
            span_id="span-002",
            parent_span_id="span-001",
            service_name="productcatalogservice",
            span_name="GetProduct",
            status_code="Error",
            status_message="Error: ProductCatalogService Fail Feature Flag Enabled",
            duration_ns=50000000,
            timestamp=1700000000.05,
            attributes={"product.id": "OLJCESPC7Z"},
        ),
    ]

    # Seeded fake logs sharing the same trace_id
    fake_logs = [
        CorrelatedLog(
            timestamp=1700000000.06,
            trace_id="trace-12345",
            span_id="span-002",
            service_name="productcatalogservice",
            severity="ERROR",
            body="Failed to load product OLJCESPC7Z due to feature flag failure",
            attributes={"error": "ProductCatalogFailure"},
        )
    ]

    engine.fetch_traces = MagicMock(return_value=fake_traces)
    engine.fetch_logs = MagicMock(return_value=fake_logs)

    payload = engine.correlate(
        start_time=1700000000.0,
        end_time=1700000060.0,
    )

    assert isinstance(payload, CorrelationPayload)
    assert payload.time_window == {"start": 1700000000.0, "end": 1700000060.0}
    assert payload.total_traces == 1
    assert payload.error_traces == 1
    assert "frontend" in payload.services_impacted
    assert "productcatalogservice" in payload.services_impacted

    # Verify correlated traces structure
    assert len(payload.correlated_traces) == 1
    trace_corr = payload.correlated_traces[0]
    assert trace_corr.trace_id == "trace-12345"
    assert trace_corr.root_service == "frontend"
    assert trace_corr.has_errors is True
    assert len(trace_corr.spans) == 2
    assert len(trace_corr.logs) == 1
    assert trace_corr.logs[0].body == "Failed to load product OLJCESPC7Z due to feature flag failure"

    # Verify metrics included
    assert len(payload.metrics) == 1
    assert payload.metrics[0]["metric_name"] == "rpc_server_duration_milliseconds"

    # Verify serialization
    data_dict = payload.to_dict()
    assert data_dict["total_traces"] == 1
    assert len(data_dict["correlated_traces"][0]["spans"]) == 2
    assert len(data_dict["correlated_traces"][0]["logs"]) == 1
