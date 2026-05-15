"""Tool: get_recent_actions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastmcp import FastMCP

from .common import ha_request


def register(mcp: FastMCP) -> None:
    @mcp.tool
    async def get_recent_actions(hours: int = 48) -> dict[str, Any]:
        """Return HA API calls that YOU (this agent) made during the last N hours (default 48).

        These are actions performed by this agent itself in previous runs — not external
        data. Each entry records the method, path, body and reason you provided.
        Use this to understand what you already did recently (e.g. turned on a light,
        sent a notification) so you avoid redundant actions and can reason about timing.
        """
        _, data, error = await ha_request(
            "GET", "/api/states/sensor.agent_log_plant_check_actions"
        )
        if error:
            return {"status": "error", "error": error}
        if not isinstance(data, dict):
            return {"status": "success", "items": []}

        items: list[str] = data.get("attributes", {}).get("items", []) or []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        filtered: list[str] = []
        for item in items:
            if item.startswith("["):
                try:
                    ts_str = item[1:item.index("]")]
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if ts >= cutoff:
                        filtered.append(item)
                except (ValueError, IndexError):
                    filtered.append(item)
            else:
                filtered.append(item)

        return {"status": "success", "items": filtered, "hours": hours}
