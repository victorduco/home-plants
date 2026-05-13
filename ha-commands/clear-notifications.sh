#!/usr/bin/env bash
# Clear all persistent notifications in Home Assistant
source "$(dirname "$0")/../.env"

echo "→ Clearing notifications..."
curl -sf -X POST "$HA_URL/api/services/persistent_notification/dismiss_all" \
  -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}' > /dev/null
echo "✓ Notifications cleared"
