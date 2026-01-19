"""Prompt registrations."""

from fastmcp import FastMCP

from .notifications import register_notification_prompts
from .plants import register_plants_prompts


def register_prompts(mcp: FastMCP) -> None:
    """Register all prompts."""
    register_notification_prompts(mcp)
    register_plants_prompts(mcp)
