"""Flask application factory."""

from typing import Any, Dict, Optional
from flask import Flask

from proxy.config import Config
from proxy.adapters import PrometheusAdapter, ClickHouseMetricsAdapter
from proxy.routes.health import health_bp
from proxy.routes.correlate import correlate_bp
from proxy.routes.rca import rca_bp
from proxy.store.rca_store import RCAStore


def create_app(test_config: Optional[Dict[str, Any]] = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Default configuration
    app.config.from_object(Config)

    if test_config:
        app.config.update(test_config)

    # Initialize metrics adapter according to STORAGE_MODE
    storage_mode = app.config.get("STORAGE_MODE", "prometheus")
    if storage_mode == "clickhouse_only" or storage_mode == "mode-b":
        app.metrics_adapter = ClickHouseMetricsAdapter(
            base_url=app.config.get("CLICKHOUSE_URL", "http://localhost:8123")
        )
    else:
        app.metrics_adapter = PrometheusAdapter(
            base_url=app.config.get("PROMETHEUS_URL", "http://localhost:9090")
        )

    # In-memory RCA approval store (one instance per app, survives requests)
    app.rca_store = RCAStore()

    # Register blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(correlate_bp)
    app.register_blueprint(rca_bp)

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=app.config.get("PROXY_PORT", 5000), debug=app.config.get("DEBUG", False))
