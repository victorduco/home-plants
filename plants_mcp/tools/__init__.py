"""Tool registrations."""

from fastmcp import FastMCP

from .call_ha_api import register as register_call_ha_api
from .get_all_devices import register as register_get_all_devices
from .get_all_plants import register as register_get_all_plants
from .get_current_status import register as register_get_current_status
from .get_recent_actions import register as register_get_recent_actions
from .get_recent_issues import register as register_get_recent_issues
def register_tools(mcp: FastMCP) -> None:
    """Register all tools."""
    register_call_ha_api(mcp)
    register_get_all_devices(mcp)
    register_get_all_plants(mcp)
    register_get_current_status(mcp)
    register_get_recent_actions(mcp)
    register_get_recent_issues(mcp)
