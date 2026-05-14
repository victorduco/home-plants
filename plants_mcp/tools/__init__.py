"""Tool registrations."""

from fastmcp import FastMCP

from .analyze import register_analyze_tools
from .automation import register_automation_tools
from .devices import register_devices_tools
from .manage import register_manage_tools
from .plant_care import register_plant_care_tools
from .plants import register_plants_tools


def register_tools(mcp: FastMCP) -> None:
    """Register all tools."""
    register_plant_care_tools(mcp)
    register_analyze_tools(mcp)
    register_manage_tools(mcp)
    register_automation_tools(mcp)
    register_devices_tools(mcp)
    register_plants_tools(mcp)
