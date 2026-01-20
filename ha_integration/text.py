"""Text platform for Plants recommendations."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .data import PlantsData

MAX_RECOMMENDATION_LENGTH = 120

FIELDS: list[tuple[str, str, int | None]] = [
    (
        "watering_frequency_recommendation",
        "Watering Frequency Recommendation (e.g., once a week)",
        MAX_RECOMMENDATION_LENGTH,
    ),
    (
        "soil_moisture_recommendation",
        "Minimum Soil Moisture for Watering Recommendation (e.g., 25%)",
        MAX_RECOMMENDATION_LENGTH,
    ),
    (
        "air_temperature_recommendation",
        "Air Temperature Recommendation (e.g., 20-24 C)",
        MAX_RECOMMENDATION_LENGTH,
    ),
    (
        "air_humidity_recommendation",
        "Air Humidity Recommendation (e.g., 50-60%)",
        MAX_RECOMMENDATION_LENGTH,
    ),
    (
        "other_recommendations",
        "Other Recommendations (e.g., - rotate weekly; - avoid drafts;)",
        None,
    ),
    (
        "todo_list",
        "Todo List (e.g., - repot in spring; - prune dry leaves;)",
        None,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up Plants text entities from a config entry."""
    data: PlantsData = hass.data[DOMAIN]["data"]
    entities: list[TextEntity] = []
    for plant_id in data.plants:
        for field_key, label, max_length in FIELDS:
            entities.append(
                PlantRecommendationText(data, plant_id, field_key, label, max_length)
            )
    if entities:
        async_add_entities(entities)


class PlantRecommendationText(TextEntity):
    """Text entity for plant recommendations."""

    def __init__(
        self,
        data: PlantsData,
        plant_id: str,
        field_key: str,
        label: str,
        max_length: int | None,
    ) -> None:
        self._data = data
        self._plant_id = plant_id
        self._field_key = field_key
        plant = data.plants[plant_id]
        self._attr_name = label
        self._attr_has_entity_name = True
        self._attr_unique_id = f"plant_{plant_id}_{field_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"plant_{plant_id}")},
            name=plant.name,
            manufacturer="Custom",
            model="Plant",
        )
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if max_length is not None:
            self._attr_native_max = max_length

    @property
    def native_value(self) -> str:
        value = getattr(self._data.plants[self._plant_id], self._field_key)
        return value or ""

    async def async_set_value(self, value: str) -> None:
        setattr(self._data.plants[self._plant_id], self._field_key, value)
        await self._data.async_save()
        self.async_write_ha_state()
