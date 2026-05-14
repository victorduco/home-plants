"""Resource registrations."""

from fastmcp import FastMCP

from .notifications import register_notification_resources


def register_resources(mcp: FastMCP) -> None:
    """Register all resources."""
    register_notification_resources(mcp)
