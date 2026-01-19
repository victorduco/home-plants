"""State storage for Plants."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_LOCATION_X,
    DEFAULT_LOCATION_Y,
    DEFAULT_SOIL_MOISTURE,
    DOMAIN,
    STORAGE_VERSION,
)


@dataclass
class PlantData:
    """Persisted plant data."""

    store: Store
    last_watered: datetime | None
    soil_moisture: float
    location_x: float
    location_y: float

    @classmethod
    async def async_load(cls, hass: HomeAssistant, entry_id: str) -> "PlantData":
        """Load plant data from storage."""
        store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry_id}")
        raw = await store.async_load() or {}
        last_watered = None
        if raw.get("last_watered"):
            last_watered = dt_util.parse_datetime(raw["last_watered"])
        return cls(
            store=store,
            last_watered=last_watered,
            soil_moisture=float(raw.get("soil_moisture", DEFAULT_SOIL_MOISTURE)),
            location_x=float(raw.get("location_x", DEFAULT_LOCATION_X)),
            location_y=float(raw.get("location_y", DEFAULT_LOCATION_Y)),
        )

    async def async_save(self) -> None:
        """Persist plant data."""
        payload = {
            "last_watered": self.last_watered.isoformat() if self.last_watered else None,
            "soil_moisture": self.soil_moisture,
            "location_x": self.location_x,
            "location_y": self.location_y,
        }
        await self.store.async_save(payload)
