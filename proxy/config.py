"""Application configuration."""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    STORAGE_MODE: str = os.getenv("STORAGE_MODE", "prometheus")
    PROMETHEUS_URL: str = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
    CLICKHOUSE_URL: str = os.getenv("CLICKHOUSE_URL", "http://localhost:8123")
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "mock")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    ENABLE_SIGNOZ: str = os.getenv("ENABLE_SIGNOZ", "false")
    SIGNOZ_PORT: int = int(os.getenv("SIGNOZ_PORT", "8080"))
    RCA_TRIGGER_MODE: str = os.getenv("RCA_TRIGGER_MODE", "manual")
    RCA_INTERVAL_MINUTES: int = int(os.getenv("RCA_INTERVAL_MINUTES", "15"))
    PROXY_PORT: int = int(os.getenv("PROXY_PORT", "5000"))
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1")

