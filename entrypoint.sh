#!/bin/sh
set -e

PORT="${PORT:-8080}"
echo "Starting LangGraph API server on PORT=$PORT"

cd /app/langgraph-app
exec python3 -m langgraph_api.cli \
  --host 0.0.0.0 \
  --port "$PORT" \
  --config langgraph.json \
  --no-reload
