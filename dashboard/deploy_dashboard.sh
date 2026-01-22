#!/bin/bash
set -e

# Deploy dashboard to Home Assistant
echo "🌱 Deploying Plants Dashboard to Home Assistant..."

# Create dashboards directory if it doesn't exist
echo "Creating dashboards directory..."
ssh -i ~/.ssh/id_ed25519 -p 22 hassio@192.168.1.151 "sudo mkdir -p /config/dashboards"

# Copy dashboard file to HA server using rsync
echo "Copying dashboard file..."
rsync -av -e "ssh -i ~/.ssh/id_ed25519 -p 22" \
  --rsync-path="sudo rsync" \
  ./dashboard/dashboard_plants.yaml \
  hassio@192.168.1.151:/config/dashboards/plants.yaml

echo ""
echo "✅ Dashboard deployed successfully!"
echo ""
echo "📋 Dashboard is configured at: /config/dashboards/plants.yaml"
echo ""
echo "🔄 The dashboard should appear in Home Assistant sidebar as 'Растения' with flower icon"
echo ""
echo "If you don't see it, make sure configuration.yaml has:"
echo ""
echo "lovelace:"
echo "  mode: storage"
echo "  dashboards:"
echo "    plants-dashboard:"
echo "      mode: yaml"
echo "      title: Растения"
echo "      icon: mdi:flower"
echo "      show_in_sidebar: true"
echo "      filename: dashboards/plants.yaml"
echo ""
echo "Then restart Home Assistant or reload dashboards."
