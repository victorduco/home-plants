"""Tool: get_recent_issues."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastmcp import FastMCP

from .common import ha_request

# Ledger of issues already pushed to the user. Lines look like:
#   [2026-08-01T09:01:12Z] humidifier:no_water | Humidifier reservoir is empty
# The timestamp and the stable key are what deduplication runs on; the trailing text is
# only there so the raw sensor stays readable on the dashboard.
NOTIFIED_SENSOR = "sensor.agent_log_plant_check_notified"


def parse_line(line: str) -> dict[str, Any] | None:
    """Split one ledger line into {notified_at, key, text}. Returns None if unparseable."""
    if not line.startswith("["):
        return None
    try:
        close = line.index("]")
    except ValueError:
        return None
    try:
        ts = datetime.fromisoformat(line[1:close].replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    key, _, text = line[close + 1 :].strip().partition("|")
    return {"notified_at": ts.isoformat(), "key": key.strip(), "text": text.strip()}


def register(mcp: FastMCP) -> None:
    @mcp.tool
    async def get_recent_issues(hours: int = 48) -> dict[str, Any]:
        """Return issues that YOU (this agent) already notified the user about in the last N hours (default 48).

        Each item is {notified_at, key, text}. `key` is a stable identifier such as
        "humidifier:no_water" or "humidity_low:Rubber Plant" — deduplicate on it rather
        than on the wording, which is regenerated every run.
        """
        _, data, error = await ha_request("GET", f"/api/states/{NOTIFIED_SENSOR}")
        if error:
            return {"status": "error", "error": error}
        if not isinstance(data, dict):
            return {"status": "success", "items": [], "hours": hours}

        raw_items: list[str] = data.get("attributes", {}).get("items", []) or []
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        items: list[dict[str, Any]] = []
        for line in raw_items:
            entry = parse_line(line)
            # Unparseable lines are dropped rather than kept. An entry with no usable
            # timestamp cannot take part in a time-windowed decision, and keeping it
            # would suppress a genuinely new notification forever.
            if entry is None:
                continue
            if datetime.fromisoformat(entry["notified_at"]) >= cutoff:
                items.append(entry)

        return {"status": "success", "items": items, "hours": hours}
