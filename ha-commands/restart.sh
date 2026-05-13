#!/usr/bin/env bash
# Restart Home Assistant
source "$(dirname "$0")/../.env"

echo "→ Restarting Home Assistant..."
curl -sf -X POST "$HA_URL/api/services/homeassistant/restart" \
  -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' > /dev/null
echo "✓ Restart triggered"
