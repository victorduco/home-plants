"""Run graph_regular_check directly (no LangGraph server needed).

Used by Heroku Scheduler (every 4 hours) and manually via:
  python langgraph-app/runner.py
  make agent-run
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lg_main.g_regular_check.graph import graph_regular_check
from lg_main.g_regular_check.mcp_tools import get_mcp_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("runner")


async def send_notification_via_mcp(message: str) -> None:
    client = get_mcp_client()
    tools = await client.get_tools()
    tool = next((t for t in tools if t.name == "call_ha_api"), None)
    if not tool:
        log.error("call_ha_api tool not found")
        return
    await tool.ainvoke({
        "method": "POST",
        "path": "/api/services/persistent_notification/create",
        "body": {
            "title": "🌿 Plant Check",
            "message": message,
            "notification_id": "plant_regular_check",
        },
    })
    await tool.ainvoke({
        "method": "POST",
        "path": "/api/services/notify/mobile_app_iphone_2",
        "body": {
            "title": "🌿 Plant Check",
            "message": message,
        },
    })
    log.info("Notification sent.")


async def write_issues_to_ha(issues: list[str]) -> None:
    """Write current issues to plant_check_issues sensor for deduplication."""
    client = get_mcp_client()
    tools = await client.get_tools()
    tool = next((t for t in tools if t.name == "call_ha_api"), None)
    if not tool:
        log.warning("call_ha_api not found, cannot write plant_check_issues")
        return
    resp = await tool.ainvoke({
        "method": "POST",
        "path": "/api/services/plants/update_agent_log",
        "body": {"field": "plant_check_issues", "items": issues},
    })
    log.info("Wrote %d issue(s) to plant_check_issues. Response: %s", len(issues), resp)


async def run() -> None:
    log.info("Starting plant regular check...")
    result = await graph_regular_check.ainvoke({})

    check_result = result.get("result")
    if not check_result or not check_result.issues:
        log.info("No issues found, skipping notification.")
        await write_issues_to_ha([])
        return

    log.info("Issues found: %d — %s", len(check_result.issues), check_result.issues)
    log.info("Issues: %s", check_result.issues)
    message = "\n".join(f"- {issue}" for issue in check_result.issues)
    await send_notification_via_mcp(message)
    await write_issues_to_ha(check_result.issues)


if __name__ == "__main__":
    asyncio.run(run())
