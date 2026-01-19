"""Resources describing Home Assistant Plants tools."""

from fastmcp import FastMCP

PLANTS_GUIDE = """Plants tool guide.

Environment:
- HA_TOKEN must be set.
- HA_URL defaults to http://homeassistant.local:8123 (override as needed).

Tools:
- get_plants_status: list all plants and entity states.
- add_plant: create a new plant by name.
- water_plant: set last watered to now and soil moisture to 100%.
- edit_plant: rename a plant or update location coordinates.
- delete_plant: remove a plant entry.

Identifiers:
- Use config entry_id or the exact plant name (title).
"""


def register_plants_resources(mcp: FastMCP) -> None:
    """Register plant-related resources."""

    @mcp.resource("mcp://plants/guide")
    def plants_guide() -> str:
        """Return a concise guide for the Plants tools."""
        return PLANTS_GUIDE
