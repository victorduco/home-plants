from __future__ import annotations

import logging
from typing import Annotated, List, Optional

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
2. Call get_current_status to see plant zones and device states.
3. Call get_all_devices to see which devices serve which plants.
4. Evaluate each plant (soil moisture, air humidity, air temperature zones).
5. Take automated actions via call_ha_api where possible:
   - Turn humidifier on/off based on nearby plants' humidity zones
   - Turn grow lights on/off based on time of day
   - Open/close valves to water plants with red/yellow soil moisture zones

Be decisive — act first. Do not ask for confirmation before taking actions."""

SUMMARIZE_PROMPT = """Based on the plant check conversation above, return a JSON summary.

Rules for the "issues" list:
- Include ONLY problems that need human attention
- 🔴 humidity/soil zones that couldn't be fixed automatically
- Unavailable sensors (❓): one item like "Sensors unavailable: Plant A, Plant B"
- Broken/unconfigured devices (e.g. auto waterer not configured)
- Temperature issues
- Do NOT include: green zones, routine actions that worked, per-plant status table
- If everything is fine — return empty list

Return JSON only, no other text:
{"issues": ["issue 1", "issue 2"]}"""


class CheckResult(BaseModel):
    issues: List[str] = Field(default_factory=list)


class RegularCheckState(BaseModel):
    messages: Annotated[List[AnyMessage], add_messages] = Field(default_factory=list)
    trigger_message: Optional[str] = Field(default=None)
    result: Optional[CheckResult] = Field(default=None)


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
    history.append(HumanMessage(content=SUMMARIZE_PROMPT))
    result = await structured_llm.ainvoke(history)
    log.info("Issues found: %d — %s", len(result.issues), result.issues)
    return {"result": result}


def should_continue(state: RegularCheckState) -> str:
    last = state.messages[-1] if state.messages else None
    if last and getattr(last, "tool_calls", None):
        return "tools"
    return "summarize"


builder = StateGraph(RegularCheckState)
builder.add_node("agent", agent)
builder.add_node("tools", call_tools)
builder.add_node("summarize", summarize)

builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", should_continue)
builder.add_edge("tools", "agent")
builder.add_edge("summarize", END)

graph_regular_check = builder.compile()
