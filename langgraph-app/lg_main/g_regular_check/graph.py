from __future__ import annotations

import logging
import os
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

Previous issues from the last check are provided below. Compare SEMANTICALLY — minor wording differences don't matter. Skip an issue if the same underlying problem was already reported (same affected plants, same root cause). Only include an issue if it's genuinely new or the affected set of plants has changed significantly.

{previous_notifications}

Return JSON only:
{{"issues": ["issue 1", "issue 2"]}}
If no new issues compared to last check — return {{"issues": []}}"""


class CheckResult(BaseModel):
    issues: List[str] = Field(default_factory=list)


class RegularCheckState(BaseModel):
    messages: Annotated[List[AnyMessage], add_messages] = Field(default_factory=list)
    trigger_message: Optional[str] = Field(default=None)
    previous_notifications: str = Field(default="")
    result: Optional[CheckResult] = Field(default=None)


async def _ha_get(path: str) -> dict | None:
    """GET from HA REST API, return parsed JSON or None on error."""
    ha_url = os.environ.get("HA_URL", "http://homeassistant.local:8123").rstrip("/")
    ha_token = os.environ.get("HA_TOKEN", "")
    headers = {"Authorization": f"Bearer {ha_token}"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{ha_url}{path}", headers=headers)
            r.raise_for_status()
            return r.json()
    except Exception as exc:
        log.warning("HA GET %s failed: %s", path, exc)
        return None



async def fetch_previous_notifications(state: RegularCheckState) -> dict:
    """Read last issues from plant_check_issues text entity in HA."""
    data = await _ha_get("/api/states/text.agent_log_plant_check_issues")
    if not data:
        return {"previous_notifications": "No previous plant check data available."}
    value = data.get("state", "")
    if not value or value == "unknown":
        return {"previous_notifications": "No previous plant check notifications recorded."}
    log.info("Loaded previous issues from HA: %s", value[:120])
    return {"previous_notifications": f"Previous issues (last check):\n{value}"}


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
