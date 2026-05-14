"""Tool: call_ha_api."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from .common import ha_request


def register(mcp: FastMCP) -> None:
    @mcp.tool
    async def call_ha_api(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call any Home Assistant REST API endpoint. method: GET/POST/etc, path: e.g. /api/services/switch/turn_on, body: optional JSON payload."""
        _, data, error = await ha_request(method.upper(), path, json=body)
        if error:
            return {"status": "error", "error": error}
        return {"status": "success", "data": data}
