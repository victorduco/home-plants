"""Logbook integration for Plants — suppress default event entries."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant, callback


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Any,
) -> None:
    """Describe logbook events — return None to suppress the default entry."""

    @callback
    def _describe(event: Any) -> dict | None:
        return None

    async_describe_event("plants", "custom", _describe)
    async_describe_event("plants", "watered", _describe)
    async_describe_event("plants", "showered", _describe)
    async_describe_event("plants", "auto_watered", _describe)
