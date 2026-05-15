"""Trigger graph_regular_check via LangGraph HTTP API.

Used by Heroku Scheduler (every 4 hours) and manually via:
  python langgraph-app/runner.py
  make agent-run

Requires LANGGRAPH_API_URL env var.
"""

import asyncio
import logging
import os

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("runner")

ASSISTANT_ID = "graph_regular_check"


def _base_url() -> str:
    url = os.environ.get("LANGGRAPH_API_URL", "").strip()
    if not url:
        raise RuntimeError("LANGGRAPH_API_URL is not set")
    return url.rstrip("/")


async def run() -> None:
    base = _base_url()
    async with httpx.AsyncClient(timeout=300) as http:
        r = await http.post(f"{base}/threads", json={})
        r.raise_for_status()
        thread_id = r.json()["thread_id"]
        log.info("Created thread %s", thread_id)

        r = await http.post(
            f"{base}/threads/{thread_id}/runs/wait",
            json={"assistant_id": ASSISTANT_ID, "input": {}},
        )
        r.raise_for_status()
        log.info("Plant regular check complete (thread_id=%s)", thread_id)


if __name__ == "__main__":
    asyncio.run(run())
