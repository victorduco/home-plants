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


async def run() -> None:
    log.info("Starting plant regular check...")
    result = await graph_regular_check.ainvoke({})

    check_result = result.get("result")
    if not check_result or not check_result.issues:
        log.info("No issues found, skipping notification.")
        return

    log.info("Issues: %s", check_result.issues)
    message = "\n".join(f"- {issue}" for issue in check_result.issues)
    await send_notification_via_mcp(message)


if __name__ == "__main__":
    asyncio.run(run())
