"""Tool: get_recent_issues."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastmcp import FastMCP

from .common import ha_request


def register(mcp: FastMCP) -> None:
    @mcp.tool
    async def get_recent_issues(hours: int = 48) -> dict[str, Any]:
        """Return issues that YOU (this agent) logged during the last N hours (default 48).

        These are problems written by this agent itself in previous runs — not external
        data. Use this to understand what issues you identified and reported last time,
        so you can decide what is genuinely new vs already known.
        """
        _, data, error = await ha_request(
            "GET", "/api/states/sensor.agent_log_plant_check_issues"
        )
        if error:
            return {"status": "error", "error": error}
        if not isinstance(data, dict):
            return {"status": "success", "items": []}

        items: list[str] = data.get("attributes", {}).get("items", []) or []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        filtered: list[str] = []
        for item in items:
            # items are plain strings (no timestamp prefix), include all
            # if timestamp prefix present, filter by it
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
