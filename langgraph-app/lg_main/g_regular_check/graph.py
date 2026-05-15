from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Annotated, List, Optional

import httpx
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from .mcp_tools import get_mcp_client

log = logging.getLogger("g_regular_check")

llm = ChatOpenAI(model="gpt-4.1-2025-04-14", temperature=0.2)

SYSTEM_PROMPT = """You are a home plant care assistant performing a regular check.

Follow these steps:
1. Call get_regular_check_instructions to get the full check protocol.
2. Call get_current_status to see plant zones, device states, and current time/sun state.
3. Call get_all_devices to see which devices serve which plants.
4. Evaluate each plant (soil moisture, air humidity, air temperature zones).
5. Take automated actions via call_ha_api:

GROW LIGHTS (you manage these — no automation exists):
- If sun is above horizon → turn ON both grow lights (switch.horizontal_grow_light_control, switch.vertical_grow_light_control)
- If sun is below horizon → turn OFF both grow lights
- Always check and act, even if they're already in the correct state (no-op is fine)

HUMIDIFIER (you manage this — no automation exists):
- Daytime (sun above horizon): if any plant has humidity 🔴 → turn ON humidifier
- Nighttime (sun below horizon): humidity naturally rises, so turn OFF humidifier unless many plants are critically dry
- If humidifier is ON but humidity is still 🔴 after checking → user needs to manually adjust humidifier settings

SOIL MOISTURE:
- Open/close valves for plants with red/yellow soil moisture zones

Be decisive — act first. Do not ask for confirmation."""

SUMMARIZE_PROMPT = """Based on the plant check above, extract issues needing human attention.

Rules:
- Humidifier ON but humidity still 🔴 → "Humidifier is on but humidity too low for [plants] — check humidifier settings/water level"
- Unavailable sensors (❓) → one item: "Sensors unavailable: Plant A, Plant B"
- Broken/unconfigured devices
- Temperature issues
- Do NOT include: green zones, successful automated actions, per-plant status table

Previous notifications (last 2 days) are provided below. If an issue is already listed there and nothing has changed — SKIP it (don't repeat).

{previous_notifications}

Return JSON only:
{{"issues": ["issue 1", "issue 2"]}}
If no new issues — return {{"issues": []}}"""


class CheckResult(BaseModel):
    issues: List[str] = Field(default_factory=list)


class RegularCheckState(BaseModel):
    messages: Annotated[List[AnyMessage], add_messages] = Field(default_factory=list)
    trigger_message: Optional[str] = Field(default=None)
    previous_notifications: str = Field(default="")
    result: Optional[CheckResult] = Field(default=None)


async def fetch_previous_notifications(state: RegularCheckState) -> dict:
    """Fetch persistent notifications from HA for the last 2 days."""
    ha_url = os.environ.get("HA_URL", "http://homeassistant.local:8123").rstrip("/")
    ha_token = os.environ.get("HA_TOKEN", "")
    headers = {"Authorization": f"Bearer {ha_token}"}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Get logbook for persistent_notification domain over last 48h
            r = await client.get(
                f"{ha_url}/api/logbook",
                headers=headers,
                params={"hours_to_show": 48, "entity_id": "persistent_notification.plant_regular_check"},
            )
            r.raise_for_status()
            entries = r.json()

        if not entries:
            return {"previous_notifications": "No previous plant check notifications in the last 2 days."}

        lines = []
        for e in entries:
            when = e.get("when", "")
            msg = e.get("message", e.get("state", ""))
            if msg:
                lines.append(f"[{when}] {msg}")

        text = "\n".join(lines) if lines else "No previous plant check notifications in the last 2 days."
        log.info("Fetched %d previous notification entries.", len(lines))
        return {"previous_notifications": text}

    except Exception as e:
        log.warning("Could not fetch previous notifications: %s", e)
        return {"previous_notifications": "Could not fetch previous notifications."}


async def agent(state: RegularCheckState) -> dict:
    client = get_mcp_client()
    tools = await client.get_tools()

    model = llm.bind_tools(tools)
    history = list(state.messages or [])

    if not history:
        trigger = state.trigger_message or "Please do a regular plant check now."
        history = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=trigger),
        ]

    response = await model.ainvoke(history)
    return {"messages": [response]}


async def call_tools(state: RegularCheckState) -> dict:
    client = get_mcp_client()
    tools = await client.get_tools()
    tool_node = ToolNode(tools)
    return await tool_node.ainvoke(state)


async def summarize(state: RegularCheckState) -> dict:
    structured_llm = llm.with_structured_output(CheckResult)
    history = list(state.messages or [])
    prompt = SUMMARIZE_PROMPT.format(previous_notifications=state.previous_notifications)
    history.append(HumanMessage(content=prompt))
    result = await structured_llm.ainvoke(history)
    log.info("Issues found: %d — %s", len(result.issues), result.issues)
    return {"result": result}


def should_continue(state: RegularCheckState) -> str:
    last = state.messages[-1] if state.messages else None
    if last and getattr(last, "tool_calls", None):
        return "tools"
    return "summarize"


builder = StateGraph(RegularCheckState)
builder.add_node("fetch_history", fetch_previous_notifications)
builder.add_node("agent", agent)
builder.add_node("tools", call_tools)
builder.add_node("summarize", summarize)

builder.add_edge(START, "fetch_history")
builder.add_edge("fetch_history", "agent")
builder.add_conditional_edges("agent", should_continue)
builder.add_edge("tools", "agent")
builder.add_edge("summarize", END)

graph_regular_check = builder.compile()
