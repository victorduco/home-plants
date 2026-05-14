#!/usr/bin/env bash
# Deploy local files to Home Assistant server
# Usage:
#   ./scripts/deploy.sh               — deploy everything (integration + dashboard)
#   ./scripts/deploy.sh integration   — deploy custom component + auto-restart HA
#   ./scripts/deploy.sh dashboard     — deploy dashboard only (refresh browser, no restart)
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$REPO_ROOT/.env"

HA_HOST="hassio@192.168.1.151"
SSH_OPTS="-i ~/.ssh/id_ed25519 -p 22"

deploy_integration() {
  echo "→ Deploying custom component (ha/custom_components/plants → /config/custom_components/plants)..."
  rsync -av --delete --exclude='__pycache__' \
    -e "ssh $SSH_OPTS" \
    --rsync-path="sudo rsync" \
    "$REPO_ROOT/ha/custom_components/plants/" \
    "$HA_HOST:/config/custom_components/plants/"
  echo "✓ Integration deployed"

  if [ -f "$REPO_ROOT/ha/configuration.yaml" ]; then
    echo "→ Deploying configuration.yaml..."
    rsync -av \
      -e "ssh $SSH_OPTS" \
      --rsync-path="sudo rsync" \
      "$REPO_ROOT/ha/configuration.yaml" \
      "$HA_HOST:/config/configuration.yaml"
    echo "✓ configuration.yaml deployed"
  fi

  echo "→ Restarting Home Assistant..."
  curl -s --max-time 10 -X POST "$HA_URL/api/services/homeassistant/restart" \
    -H "Authorization: Bearer $HA_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{}' > /dev/null || true

  echo "→ Waiting for HA to come back..."
  sleep 10
  for i in $(seq 1 30); do
    if curl -sf --max-time 3 "$HA_URL/api/" \
      -H "Authorization: Bearer $HA_TOKEN" > /dev/null 2>&1; then
      echo "✓ HA is online, waiting for integrations to load..."
      break
    fi
    echo "  ...still booting (${i}0s)"
    sleep 10
  done

  for i in $(seq 1 20); do
    count=$(curl -sf --max-time 5 "$HA_URL/api/states" \
      -H "Authorization: Bearer $HA_TOKEN" 2>/dev/null \
      | python3 -c "
import json,sys
s=json.load(sys.stdin)
print(len([e for e in s if 'plant' in e['entity_id'].lower()]))
" 2>/dev/null || echo 0)
    if [ "$count" -gt 0 ]; then
      echo "✓ All done — $count plant entities loaded"
      break
    fi
    echo "  ...loading integrations (${i}x)"
    sleep 3
  done
}

deploy_dashboard() {
  echo "→ Deploying dashboard (ha/dashboards/plants.yaml → /config/dashboards/plants.yaml)..."
  rsync -av \
    -e "ssh $SSH_OPTS" \
    "$REPO_ROOT/ha/dashboards/plants.yaml" \
    "$HA_HOST:/config/dashboards/plants.yaml"
  echo "✓ Dashboard deployed (refresh the browser to see changes)"
}

deploy_automations() {
  if [ ! -d "$REPO_ROOT/ha/automations" ]; then
    return
  fi
  echo "→ Deploying automations via HA API..."
  python3 "$REPO_ROOT/ha-commands/deploy_automations.py"
  echo "✓ Automations deployed"
}

case "${1:-all}" in
  integration) deploy_integration ;;
  dashboard)   deploy_dashboard ;;
  automations) deploy_automations ;;
  all)
    deploy_integration
    deploy_dashboard
    deploy_automations
    ;;
  *)
    echo "Usage: $0 [integration|dashboard|all]"
    exit 1
    ;;
esac
