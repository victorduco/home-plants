"""Constants for the Plants integration."""

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "plants"
# A reading is trusted only while both hold: the source is still reporting, and its
# value has moved at some point recently. Reports without movement mean a frozen probe;
# movement without reports means the device went quiet.
STALE_AFTER = timedelta(hours=6)
STALE_UNCHANGED_AFTER = timedelta(days=4)
# Staleness is time-based, so entities must re-render on their own — no source event
# arrives at the moment a reading crosses either threshold.
STALE_RECHECK_INTERVAL = timedelta(minutes=5)
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
