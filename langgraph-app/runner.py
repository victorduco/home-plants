"""Run graph_regular_check directly (no LangGraph server needed).

Used by Heroku Scheduler (every 4 hours) and manually via:
  python langgraph-app/runner.py
  make agent-run
"""

import asyncio
import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lg_main.g_regular_check.graph import graph_regular_check

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("runner")


async def run() -> None:
    thread_id = str(uuid.uuid4())
    log.info("Starting plant regular check (thread_id=%s)...", thread_id)
    await graph_regular_check.ainvoke({}, config={"configurable": {"thread_id": thread_id}})
    log.info("Plant regular check complete.")


if __name__ == "__main__":
    asyncio.run(run())
