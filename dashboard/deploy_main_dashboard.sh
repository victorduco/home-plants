#!/bin/bash
set -e

echo "🏠 Deploying Main Dashboard to Home Assistant..."

# Backup current dashboard
echo "Creating backup..."
ssh -i ~/.ssh/id_ed25519 -p 22 hassio@192.168.1.151 "sudo cp /config/.storage/lovelace /config/.storage/lovelace.backup.$(date +%Y%m%d_%H%M%S)"

# Upload new dashboard
echo "Uploading clean dashboard..."
cat ./dashboard/lovelace_clean.json | ssh -i ~/.ssh/id_ed25519 -p 22 hassio@192.168.1.151 "sudo tee /config/.storage/lovelace > /dev/null"

echo ""
echo "✅ Main dashboard deployed successfully!"
echo ""
echo "📋 Changes:"
echo "  ✓ Removed duplicate music controls (was 4, now 1)"
echo "  ✓ Removed non-existing YouTube sensors (Victor Diukov, Jimmy Carr)"
echo "  ✓ Removed non-existing devices (plug_grow_light, plug_heater, reptile_mister, drip_irrigation)"
echo "  ✓ Removed unavailable media players"
echo "  ✓ Added weather forecast (OpenWeatherMap)"
echo "  ✓ Organized by rooms (Bedroom, Living Room)"
echo ""
echo "🎯 Kept working devices:"
echo "  ✓ Alarm buttons (Start/Stop)"
echo "  ✓ Roborock vacuum"
echo "  ✓ Vizio TV"
echo "  ✓ ViewFinity monitors & remotes"
echo "  ✓ Living room audio"
echo "  ✓ Smart diffuser"
echo "  ✓ Music search"
echo "  ✓ Lights (H6097)"
echo ""
echo "🔄 Refresh your browser (Ctrl+Shift+R) to see changes"
