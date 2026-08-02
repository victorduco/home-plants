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

# The checkpointer connection pool times out at 15s under load and fails the run before
# the first node executes. Retrying in-process turns those into a single successful run
# instead of leaving the slot lost or relying on the platform to re-fire it.
MAX_ATTEMPTS = int(os.environ.get("RUNNER_MAX_ATTEMPTS", "3"))
RETRY_BACKOFF_SECONDS = 20

# Guard against a misconfigured scheduler firing more often than intended. The graph is
# designed around a 4-hour cadence; running it hourly multiplies cost, push volume and
# pool-timeout failures without adding information.
MIN_INTERVAL_MINUTES = int(os.environ.get("RUNNER_MIN_INTERVAL_MINUTES", "225"))


def _base_url() -> str:
    url = os.environ.get("LANGGRAPH_API_URL", "").strip()
    if not url:
        raise RuntimeError("LANGGRAPH_API_URL is not set")
    return url.rstrip("/")


async def _too_soon(http: httpx.AsyncClient, base: str) -> bool:
    """True if a run already succeeded inside the minimum interval."""
    if MIN_INTERVAL_MINUTES <= 0:
        return False
    try:
        r = await http.post(
            f"{base}/runs/search",
            json={"assistant_id": ASSISTANT_ID, "status": "success", "limit": 1},
        )
        r.raise_for_status()
        runs = r.json()
    except Exception as exc:  # never let the guard itself block a scheduled run
        log.warning("Could not check last run time (%s); proceeding.", exc)
        return False

    if not runs:
        return False

    from datetime import datetime, timedelta, timezone

    raw = (runs[0] or {}).get("created_at")
    if not raw:
        return False
    try:
        last = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)

    age = datetime.now(timezone.utc) - last
    if age < timedelta(minutes=MIN_INTERVAL_MINUTES):
        log.info(
            "Last successful run was %s ago (< %d min minimum) — skipping.",
            age, MIN_INTERVAL_MINUTES,
        )
        return True
    return False


async def _run_once(http: httpx.AsyncClient, base: str) -> None:
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


async def run() -> None:
    base = _base_url()
    async with httpx.AsyncClient(timeout=300) as http:
        if await _too_soon(http, base):
            return

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                await _run_once(http, base)
                return
            except Exception as exc:
                if attempt == MAX_ATTEMPTS:
                    log.error("Run failed after %d attempts: %s", attempt, exc)
                    raise
                delay = RETRY_BACKOFF_SECONDS * attempt
                log.warning("Attempt %d/%d failed (%s); retrying in %ds",
                            attempt, MAX_ATTEMPTS, exc, delay)
                await asyncio.sleep(delay)


if __name__ == "__main__":
    asyncio.run(run())
