"""Routes package."""

from proxy.routes.health import health_bp
from proxy.routes.correlate import correlate_bp

__all__ = ["health_bp", "correlate_bp"]
