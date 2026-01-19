"""Resources describing Home Assistant notifications."""

import os
from typing import Any

import httpx
from fastmcp import FastMCP

NOTIFICATION_GUIDE = """Send a Home Assistant push notification using send_notification.

Before calling the tool, read mcp://notification/devices to get the exact device slug.
Use the exact slug in the tool call (not the full notify service name).
"""


def register_notification_resources(mcp: FastMCP) -> None:
    """Register notification-related resources."""

    @mcp.resource("mcp://notification/guide")
    def notification_guide() -> str:
        """Return a concise guide for crafting notifications."""
        return NOTIFICATION_GUIDE

    @mcp.resource("mcp://notification/devices")
    async def notification_devices() -> str:
        """Return a list of exact notify device slugs from Home Assistant."""
        ha_token = os.getenv("HA_TOKEN", "")
        ha_url = os.getenv("HA_URL", "http://homeassistant.local:8123")

        if not ha_token:
            return "HA_TOKEN is not set. Unable to list notify devices."

        headers = {
            "Authorization": f"Bearer {ha_token}",
            "Content-Type": "application/json",
        }
        url = f"{ha_url}/api/services"

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, headers=headers)

        if response.status_code != 200:
            return f"Failed to fetch services: HTTP {response.status_code}: {response.text}"

        services: list[dict[str, Any]] = response.json()
        notify_domain = next(
            (item for item in services if item.get("domain") == "notify"),
            None,
        )
        if not notify_domain:
            return "No notify services found in Home Assistant."

        raw_services = notify_domain.get("services", {})
        device_slugs = []
        full_names = []
        for service_name in sorted(raw_services.keys()):
            if not service_name.startswith("mobile_app_"):
                continue
            full_names.append(service_name)
            device_slugs.append(service_name.removeprefix("mobile_app_"))

        if not device_slugs:
            return "No mobile_app notify services found."

        lines = [
            "Home Assistant notify device list (exact slugs):",
            *[f"- {slug}" for slug in device_slugs],
            "",
            "Full notify service names:",
            *[f"- {name}" for name in full_names],
            "",
            "Tool guidance:",
            "- Use send_notification with device=<slug> from the list above.",
            "- The tool calls notify.mobile_app_<device> in Home Assistant.",
            "",
            "Prompt example:",
            'Create a short alert for the front door opening for device "<slug>".',
            "Return JSON with title, message, subtitle, sound, data.",
        ]
        return "\n".join(lines)
