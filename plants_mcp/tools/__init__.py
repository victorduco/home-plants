"""Tool registrations."""

from fastmcp import FastMCP

from .get_all_automations import register as register_get_all_automations
from .get_all_devices import register as register_get_all_devices
from .get_all_plants import register as register_get_all_plants
from .get_current_status import register as register_get_current_status


def register_tools(mcp: FastMCP) -> None:
    """Register all tools."""
    register_get_all_automations(mcp)
    register_get_all_devices(mcp)
    register_get_all_plants(mcp)
    register_get_current_status(mcp)
