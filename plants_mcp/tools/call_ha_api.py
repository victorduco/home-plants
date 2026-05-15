"""Tool: call_ha_api."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastmcp import FastMCP

from .common import ha_request

_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
async def _append_action_log(method: str, path: str, body: dict[str, Any] | None, reason: str) -> None:
    """Append one action line to plant_check_actions sensor (best-effort)."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{ts}] {method} {path} {body or ''} | reason: {reason}"
    _, existing, _ = await ha_request("GET", "/api/states/sensor.agent_log_plant_check_actions")
    items: list[str] = []
    if isinstance(existing, dict):
        items = existing.get("attributes", {}).get("items", []) or []
    items = list(items) + [line]
    items = items[-20:]  # keep last 20 actions
    await ha_request(
        "POST",
        "/api/services/plants/update_agent_log",
        json={"field": "plant_check_actions", "items": items},
    )


def register(mcp: FastMCP) -> None:
    @mcp.tool
    async def call_ha_api(method: str, path: str, reason: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call any Home Assistant REST API endpoint. method: GET/POST/etc, path: e.g. /api/services/switch/turn_on, reason: why this call is being made, body: optional JSON payload."""
        m = method.upper()
        _, data, error = await ha_request(m, path, json=body)
        if error:
            return {"status": "error", "error": error}
        # Log mutating calls, but skip the log-write itself to avoid recursion.
        if m in _MUTATING and path != "/api/services/plants/update_agent_log":
            try:
                await _append_action_log(m, path, body, reason)
            except Exception:
                pass
        return {"status": "success", "data": data}
