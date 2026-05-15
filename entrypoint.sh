#!/bin/sh
set -e

PORT="${PORT:-8080}"
echo "Starting LangGraph API server on PORT=$PORT"

exec python3 -m langgraph_api \
  --host 0.0.0.0 \
  --port "$PORT" \
  --config /app/langgraph-app/langgraph.json
