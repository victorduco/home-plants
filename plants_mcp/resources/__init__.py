"""Resource registrations."""

from fastmcp import FastMCP

from .notifications import register_notification_resources
from .plants import register_plants_resources


def register_resources(mcp: FastMCP) -> None:
    """Register all resources."""
    register_notification_resources(mcp)
    register_plants_resources(mcp)
