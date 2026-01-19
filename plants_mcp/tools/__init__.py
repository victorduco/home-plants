"""Tool registrations."""

from fastmcp import FastMCP

from .plants import register_plants_tools


def register_tools(mcp: FastMCP) -> None:
    """Register all tools."""
    register_plants_tools(mcp)
