#!/usr/bin/env bash
# Reload Lovelace dashboards without restarting HA
source "$(dirname "$0")/../.env"

echo "→ Reloading dashboards..."
curl -sf -X POST "$HA_URL/api/services/lovelace/reload_resources" \
  -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' > /dev/null || true
echo "✓ Done (refresh browser)"
