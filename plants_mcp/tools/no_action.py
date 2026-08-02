"""Tool: no_action."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool
    async def no_action(reason: str) -> dict[str, Any]:
        """Record that everything is already in the desired state and no device call is needed. reason: why nothing needs to change.

        Use this instead of calling call_ha_api when a device is already in the state you
        want. Calling turn_on/turn_off "just to confirm" actually changes the device.
        """
        return {"status": "success", "acknowledged": reason}
