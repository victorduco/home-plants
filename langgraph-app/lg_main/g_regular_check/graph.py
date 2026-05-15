from __future__ import annotations

import logging
from typing import Annotated, List, Optional

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
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
2. Call get_current_status to see plant zones and device states.
3. Call get_all_devices to see which devices serve which plants.
4. Evaluate each plant (soil moisture, air humidity, air temperature zones).
5. Take automated actions via call_ha_api where possible:
   - Turn humidifier on/off based on nearby plants' humidity zones
   - Turn grow lights on/off based on time of day
   - Open/close valves to water plants with red/yellow soil moisture zones
6. Send the final report as a Home Assistant persistent notification using call_ha_api:
   POST /api/services/persistent_notification/create
   body: {"title": "🌿 Plant Check", "message": "<your report>", "notification_id": "plant_regular_check"}
7. The report in the notification should be split into two sections:
   - **Done automatically:** every action you took, zone status per plant (🟢🟡🔴)
   - **Needs your attention:** temperature issues, repotting, unavailable sensors, anything you couldn't fix

Be decisive — act first, report after. Do not ask for confirmation before taking actions."""


class RegularCheckState(BaseModel):
    messages: Annotated[List[AnyMessage], add_messages] = Field(default_factory=list)
    trigger_message: Optional[str] = Field(default=None)


async def _send_ha_notification(title: str, message: str) -> None:
    ha_url = os.getenv("HA_URL", "http://homeassistant.local:8123").rstrip("/")
    ha_token = os.getenv("HA_TOKEN", "")
    headers = {"Authorization": f"Bearer {ha_token}", "Content-Type": "application/json"}
    body = {
        "title": title,
        "message": message,
        "notification_id": "plant_regular_check",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{ha_url}/api/services/persistent_notification/create",
                headers=headers,
                json=body,
            )
            r.raise_for_status()
            log.info("HA notification sent: %s", title)
    except Exception:
        log.exception("Failed to send HA notification")


async def agent(state: RegularCheckState) -> dict:
    async with get_mcp_client() as client:
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
    async with get_mcp_client() as client:
        tools = await client.get_tools()

    tool_node = ToolNode(tools)
    return await tool_node.ainvoke(state)


def should_continue(state: RegularCheckState) -> str:
    last = state.messages[-1] if state.messages else None
    if last and getattr(last, "tool_calls", None):
        return "tools"
    return END


builder = StateGraph(RegularCheckState)
builder.add_node("agent", agent)
builder.add_node("tools", call_tools)

builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", should_continue)
builder.add_edge("tools", "agent")

graph_regular_check = builder.compile()
