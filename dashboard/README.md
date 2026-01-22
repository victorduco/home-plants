# 🌿 Plants Dashboard

Modern Home Assistant dashboard for plant monitoring and care.

## Features

✨ **4 Moisture Sensors** with real-time gauges

- Alocasia (70%)
- Majesty Palm (54%)
- Malcolm Ficus (26%)
- Olive Tree (36%)

🌡️ **Climate Monitoring**

- Temperature and humidity sensors
- Real-time environment tracking

🌱 **14 Plants Tracking**

- Individual cards for each plant
- Sensor readings
- Light and watering controls
- Care recommendations
- History graphs

📊 **Historical Data**

- 48-hour moisture graphs
- Trends and patterns

## Files

- `dashboard_plants.yaml` - Main dashboard configuration
- `deploy_dashboard.sh` - Deployment script to Home Assistant

## Deployment

Deploy the dashboard to Home Assistant:

```bash
cd /Users/vitya/Repos/home-plants
bash dashboard/deploy_dashboard.sh
```

The dashboard will be available at:

- **Location**: `/config/dashboards/plants.yaml`
- **UI**: Home Assistant → "🌿 Мои Растения"

## Configuration

Make sure your Home Assistant `configuration.yaml` includes:

```yaml
lovelace:
  mode: storage
  dashboards:
    plants-dashboard:
      mode: yaml
      title: Растения
      icon: mdi:flower
      show_in_sidebar: true
      filename: dashboards/plants.yaml
```

## Structure

### Pages

1. **Главная (Home)** - Quick overview with moisture gauges
2. **Все растения (All Plants)** - Detailed view of all 14 plants
3. **Графики (Graphs)** - Historical moisture data

### Plants

- Alocasia
- Dracaena
- Ficus Elastica Robusta
- Ficus Elastica Tineke
- Liana
- Majesty Palm
- Malcolm Ficus
- Maranta
- Olive Tree
- Philodendron
- Rubber Plant
- Triangularis Ficus
- Yucca

## Technical Details

- Uses only standard Home Assistant cards (no custom components required)
- Gauge cards for visual moisture monitoring
- History graphs for trend analysis
- Entity controls for lights, watering, and humidifiers
- Care recommendations from plant sensors
