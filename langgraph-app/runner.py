"""Run graph_regular_check directly (no LangGraph server needed).

Used by Heroku Scheduler (every 4 hours) and manually via:
  python langgraph-app/runner.py
  make agent-run
"""

import asyncio
import logging
import sys
from pathlib import Path

# Make langgraph-app importable when run from project root
sys.path.insert(0, str(Path(__file__).parent))

from lg_main.g_regular_check.graph import graph_regular_check

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("runner")


async def run() -> None:
    log.info("Starting plant regular check...")
    result = await graph_regular_check.ainvoke({})
    messages = result.get("messages", [])
    log.info("Check complete. %d messages exchanged.", len(messages))
    last = messages[-1] if messages else None
    if last:
        content = getattr(last, "content", str(last))
        log.info("Final message: %s", content[:500])


if __name__ == "__main__":
    asyncio.run(run())
