"""Base metrics adapter interface and data models."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MetricSample:
    timestamp: float  # Unix epoch in seconds
    value: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": float(self.timestamp),
            "value": float(self.value),
        }


@dataclass
class MetricSeries:
    metric_name: str
    labels: Dict[str, str] = field(default_factory=dict)
    samples: List[MetricSample] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "labels": self.labels,
            "samples": [s.to_dict() for s in self.samples],
        }


@dataclass
class MetricQueryResult:
    metric_name: str
    series: List[MetricSeries] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_name": self.metric_name,
            "series": [s.to_dict() for s in self.series],
        }


class MetricsQueryAdapter(ABC):
    """Abstract interface for querying metrics across storage modes."""

    @abstractmethod
    def query_range(
        self,
        metric_name: str,
        start_time: float,
        end_time: float,
        step_seconds: int = 15,
        service_name: Optional[str] = None,
    ) -> MetricQueryResult:
        """Query a time series range for a specific metric."""
        pass

    @abstractmethod
    def query_instant(
        self,
        metric_name: str,
        timestamp: Optional[float] = None,
        service_name: Optional[str] = None,
    ) -> MetricQueryResult:
        """Query instant point-in-time value for a metric."""
        pass

    @abstractmethod
    def get_available_metrics(self) -> List[str]:
        """List available metric names in the storage engine."""
        pass
