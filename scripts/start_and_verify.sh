#!/bin/zsh
set -e
cd /Users/tannukumari/Desktop/sih/SelfHealer

echo "=== Starting Prometheus (mode-a profile) ==="
docker compose --profile mode-a up -d prometheus
sleep 10

echo "=== Container status ==="
docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "prometheus|otel-collector|grafana" || true

echo "=== Prometheus health ==="
curl -sf http://localhost:9090/-/healthy && echo " OK" || echo " NOT READY"

echo "=== Running verification script ==="
python3 scripts/check_dashboards.py
