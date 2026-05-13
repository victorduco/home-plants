#!/usr/bin/env bash
# Deploy local files to Home Assistant server
# Usage:
#   ./deploy.sh               — deploy everything (integration + dashboard)
#   ./deploy.sh integration   — deploy custom component and restart HA
#   ./deploy.sh dashboard     — deploy dashboard only (no restart needed)

set -e

HA_HOST="hassio@192.168.1.151"
HA_SSH_KEY="$HOME/.ssh/id_ed25519"
SSH_OPTS="-i $HA_SSH_KEY -p 22"

# Load HA_URL and HA_TOKEN from .env
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$REPO_ROOT/.env" ]; then
  export $(grep -v '^#' "$REPO_ROOT/.env" | xargs)
fi

deploy_integration() {
  echo "→ Deploying custom component (ha/custom_components/plants → /config/custom_components/plants)..."
  rsync -av --delete --exclude='__pycache__' \
    -e "ssh $SSH_OPTS" \
    --rsync-path="sudo rsync" \
    "$REPO_ROOT/ha/custom_components/plants/" \
    "$HA_HOST:/config/custom_components/plants/"
  echo "✓ Integration deployed"

  echo "→ Restarting Home Assistant..."
  curl -sf -X POST "$HA_URL/api/services/homeassistant/restart" \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{}' > /dev/null
  echo "✓ Restart triggered (HA will be back in ~30 seconds)"
}

deploy_dashboard() {
  echo "→ Deploying dashboard (ha/dashboards/plants.yaml → /config/dashboards/plants.yaml)..."
  rsync -av \
    -e "ssh $SSH_OPTS" \
    "$REPO_ROOT/ha/dashboards/plants.yaml" \
    "$HA_HOST:/config/dashboards/plants.yaml"
  echo "✓ Dashboard deployed (refresh the browser to see changes)"
}

case "${1:-all}" in
  integration) deploy_integration ;;
  dashboard)   deploy_dashboard ;;
  all)
    deploy_integration
    deploy_dashboard
    ;;
  *)
    echo "Usage: $0 [integration|dashboard|all]"
    exit 1
    ;;
esac
