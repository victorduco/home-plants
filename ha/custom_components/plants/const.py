"""Constants for the Plants integration."""

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "plants"
STALE_AFTER = timedelta(hours=6)
PLATFORMS: list[Platform] = [
    Platform.TEXT,
    Platform.EVENT,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SELECT,
    Platform.SWITCH,
]
STORAGE_VERSION = 1
DEFAULT_SOIL_MOISTURE = 50.0
DEFAULT_LOCATION_X = 0.0
DEFAULT_LOCATION_Y = 0.0
DEFAULT_LAMP_POSITION_X = 0.0
DEFAULT_LAMP_POSITION_Y = 0.0
LAMP_PLANT_SLOTS = 4

STORAGE_GROW_LIGHTS = "plants_grow_lights"
STORAGE_HUMIDIFIERS = "plants_humidifiers"
STORAGE_AUTO_WATERERS = "plants_auto_waterers"
STORAGE_THERMOSTATS = "plants_thermostats"
