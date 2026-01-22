"""Tool registrations."""

from fastmcp import FastMCP

from .analyze import register_analyze_tools
from .automation import register_automation_tools
from .manage import register_manage_tools
from .plant_care import register_plant_care_tools


def register_tools(mcp: FastMCP) -> None:
    """Register all tools."""
    register_plant_care_tools(mcp)
    register_analyze_tools(mcp)
    register_manage_tools(mcp)
    register_automation_tools(mcp)
