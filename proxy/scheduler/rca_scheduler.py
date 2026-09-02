"""RCA Scheduler using APScheduler (Task 9.1).

Runs the correlate -> LLM flow on the most recent time window at a configured
interval, only when RCA_TRIGGER_MODE=automatic.

NOTE: Per ARCHITECTURE.md, this is scheduled polling, not event-driven
anomaly detection.
"""

import logging
import time
from typing import Optional
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask

from proxy.correlation.engine import CorrelationEngine
from proxy.rca.llm_client import create_llm_client

logger = logging.getLogger(__name__)


class RCAScheduler:
    """Manages periodic automatic RCA evaluation using APScheduler."""

    def __init__(self, app: Optional[Flask] = None) -> None:
        self.app: Optional[Flask] = None
        self.scheduler: BackgroundScheduler = BackgroundScheduler(daemon=True)
        self.job_id: str = "automatic_rca_job"
        if app is not None:
            self.init_app(app)

    def init_app(self, app: Flask) -> None:
        """Initialize scheduler with Flask app."""
        self.app = app
        app.rca_scheduler = self
        self.sync_with_config()

    def _get_config_value(self, key: str, default: any) -> any:
        """Get config value checking wizard_config first, then app.config."""
        if not self.app:
            return default
        lower_key = key.lower()
        if hasattr(self.app, "wizard_config") and lower_key in self.app.wizard_config:
            return self.app.wizard_config[lower_key]
        return self.app.config.get(key, default)

    def is_automatic_mode(self) -> bool:
        """Check if automatic RCA mode is enabled."""
        mode = self._get_config_value("RCA_TRIGGER_MODE", "manual")
        return str(mode).lower() == "automatic"

    def get_interval_minutes(self) -> int:
        """Return configured interval in minutes."""
        interval = self._get_config_value("RCA_INTERVAL_MINUTES", 15)
        try:
            return max(1, int(interval))
        except (ValueError, TypeError):
            return 15

    def run_job(self, window_seconds: Optional[int] = None) -> Optional[str]:
        """Execute one RCA analysis cycle on the most recent time window."""
        if not self.app:
            logger.warning("RCAScheduler run_job called without Flask app")
            return None

        with self.app.app_context():
            now = time.time()
            if window_seconds is None:
                # Default window: match the interval or minimum 300s (5m)
                interval_secs = self.get_interval_minutes() * 60
                window = max(interval_secs, 300)
            else:
                window = window_seconds

            start_time = now - window
            end_time = now

            try:
                ch_url = self.app.config.get("CLICKHOUSE_URL", "http://localhost:8123")
                engine = CorrelationEngine(
                    metrics_adapter=self.app.metrics_adapter,
                    clickhouse_url=ch_url,
                )
                payload = engine.correlate(start_time=start_time, end_time=end_time)

                llm_provider = self._get_config_value("LLM_PROVIDER", "mock")
                llm_api_key = self._get_config_value("LLM_API_KEY", "")

                llm_client = create_llm_client(provider=llm_provider, api_key=llm_api_key)
                rca_result = llm_client.generate(payload.to_dict())

                stored = self.app.rca_store.save(rca_result)
                logger.info(
                    "Automatic RCA generated: id=%s cause=%s confidence=%.2f",
                    stored.id,
                    stored.cause,
                    stored.confidence,
                )
                return stored.id
            except Exception as exc:
                logger.exception("Automatic RCA job failed: %s", exc)
                return None

    def sync_with_config(self, interval_seconds: Optional[int] = None) -> None:
        """Sync scheduled jobs with active configuration."""
        if not self.app:
            return

        # Ensure scheduler is running if not started
        if not self.scheduler.running:
            try:
                self.scheduler.start()
            except Exception as exc:
                logger.error("Failed to start APScheduler: %s", exc)

        # Remove existing job if present
        if self.scheduler.get_job(self.job_id):
            self.scheduler.remove_job(self.job_id)

        if self.is_automatic_mode():
            if interval_seconds is not None:
                trigger_kwargs = {"seconds": interval_seconds}
            else:
                trigger_kwargs = {"minutes": self.get_interval_minutes()}

            self.scheduler.add_job(
                func=self.run_job,
                trigger="interval",
                id=self.job_id,
                name="Automatic RCA Evaluation",
                replace_existing=True,
                **trigger_kwargs,
            )
            logger.info("Scheduled automatic RCA job with kwargs: %s", trigger_kwargs)

    def shutdown(self, wait: bool = False) -> None:
        """Shut down the background scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=wait)
