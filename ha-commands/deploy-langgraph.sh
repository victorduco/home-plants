#!/usr/bin/env bash
# Deploy LangGraph agent to Heroku via Docker + langgraph CLI.
# Usage: ./ha-commands/deploy-langgraph.sh
# Env:   HEROKU_APP_NAME (default: home-plants-agent)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LANGGRAPH_DIR="$PROJECT_ROOT/langgraph-app"
HEROKU_APP_NAME="${HEROKU_APP_NAME:-home-plants-agent}"
TAG="registry.heroku.com/$HEROKU_APP_NAME/web"

echo "🌿 Deploying LangGraph agent → $HEROKU_APP_NAME"

for cmd in heroku docker; do
    command -v "$cmd" &>/dev/null || { echo "❌ $cmd not found"; exit 1; }
done

heroku auth:whoami &>/dev/null || { echo "❌ Not logged in to Heroku. Run: heroku login"; exit 1; }
heroku apps:info -a "$HEROKU_APP_NAME" &>/dev/null || { echo "❌ App '$HEROKU_APP_NAME' not found on Heroku"; exit 1; }

heroku container:login

export BUILDX_NO_DEFAULT_ATTESTATIONS=1
docker buildx build \
    --platform linux/amd64 \
    -f "$LANGGRAPH_DIR/Dockerfile.heroku" \
    -t "$TAG" \
    --provenance=false \
    --sbom=false \
    --load \
    "$PROJECT_ROOT"

IMG_ARCH="$(docker image inspect "$TAG" --format '{{.Architecture}}' 2>/dev/null || true)"
[[ "$IMG_ARCH" == "amd64" ]] || { echo "❌ Built image is $IMG_ARCH, expected amd64"; exit 1; }

docker push "$TAG"
heroku container:release web --app "$HEROKU_APP_NAME"

echo "✅ Deployed → https://$HEROKU_APP_NAME.herokuapp.com"
echo "📋 Logs: heroku logs --tail -a $HEROKU_APP_NAME"
