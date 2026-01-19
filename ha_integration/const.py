"""Constants for the Plants integration."""

from homeassistant.const import Platform

DOMAIN = "plants"
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.NUMBER, Platform.DATETIME]
STORAGE_VERSION = 1
DEFAULT_SOIL_MOISTURE = 50.0
DEFAULT_LOCATION_X = 0.0
DEFAULT_LOCATION_Y = 0.0
