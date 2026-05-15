"""Trigger graph_regular_check and wait for completion.

Used by Heroku Scheduler (every 4 hours) and manually via:
  python runner.py
  make agent-run
"""

import asyncio
import logging
import os
import sys
import uuid

from langgraph_sdk import get_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("runner")

LANGGRAPH_API_URL = os.environ["LANGGRAPH_API_URL"]
GRAPH_ID = "graph_regular_check"
THREAD_ID = "plant-regular-check-singleton"


async def run() -> None:
    client = get_client(url=LANGGRAPH_API_URL)

    # Reuse a fixed thread so LangGraph Platform tracks history.
    await client.threads.create(thread_id=THREAD_ID, if_exists="do_nothing")

    log.info("Triggering %s on thread %s", GRAPH_ID, THREAD_ID)

    run_result = await client.runs.create(
        thread_id=THREAD_ID,
        assistant_id=GRAPH_ID,
        input={},
    )
    run_id = run_result["run_id"]
    log.info("Run created: %s", run_id)

    # Poll until done (timeout 10 min).
    finished = await client.runs.join(thread_id=THREAD_ID, run_id=run_id)
    status = finished.get("status", "unknown")
    log.info("Run finished: status=%s", status)

    if status == "error":
        log.error("Run errored: %s", finished)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run())
