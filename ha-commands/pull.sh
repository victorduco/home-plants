#!/usr/bin/env bash
# Pull latest files from HA server → local
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HA_HOST="hassio@192.168.1.151"
SSH_OPTS="-i ~/.ssh/id_ed25519 -p 22"

echo "→ Pulling integration..."
rsync -av --exclude='__pycache__' -e "ssh $SSH_OPTS" \
  --rsync-path="sudo rsync" \
  "$HA_HOST:/config/custom_components/plants/" \
  "$REPO_ROOT/ha/custom_components/plants/"

echo "→ Pulling dashboard..."
rsync -av -e "ssh $SSH_OPTS" \
  "$HA_HOST:/config/dashboards/plants.yaml" \
  "$REPO_ROOT/ha/dashboards/plants.yaml"

echo "✓ Pull complete"
