from __future__ import annotations

import json
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

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

ACT_SYSTEM_PROMPT = """You are a home plant care assistant performing a regular check.

Check instructions and current status (plants, devices, weather, time) are provided below.
Your job: analyse the status and take automated actions via call_ha_api.

Before acting, call get_recent_actions to understand what you already did recently
(e.g. lights turned on/off, humidifier changed) — avoid redundant state changes.

Be decisive — act first. Do not ask for confirmation.

{current_status}
"""

DEFINE_MANUAL_ACTIONS_PROMPT = """You are reviewing a plant care session log to extract issues that require human attention.

The agent has already taken automated actions (grow lights, humidifier, valves).
Your job: extract only problems that humans need to act on.

Rules:
- Humidifier ON but humidity still 🔴 → "Humidifier is on but humidity too low for [plants] — check humidifier settings/water level"
- Unavailable sensors (❓) → one item: "Sensors unavailable: Plant A, Plant B"
- Broken/unconfigured devices
- Temperature issues
- Do NOT include: green zones, successful automated actions, per-plant status table

Return JSON only:
{"manual_actions": ["issue 1", "issue 2"]}
If nothing requires human attention — return {"manual_actions": []}"""

DEFINE_NOTIFICATIONS_SYSTEM = """You are deciding which plant care issues to notify the user about.

You will receive:
1. A list of issues found in THIS check (from the current session)
2. Issues YOU reported in PREVIOUS checks (your own history — not someone else's)

Your job: return only issues that are GENUINELY NEW compared to what you already reported.
Compare semantically — minor wording differences don't matter. Skip if same underlying
problem was already reported (same affected plants, same root cause).

Previous issues you reported:
{previous_issues}
"""

DEFINE_NOTIFICATIONS_HUMAN = """Issues found in this check:
{current_issues}

Return JSON only:
{{"notifications": ["issue 1", "issue 2"]}}
If no new issues compared to previous — return {{"notifications": []}}"""

# ---------------------------------------------------------------------------
# Structured outputs
# ---------------------------------------------------------------------------


class ManualActions(BaseModel):
    manual_actions: List[str] = Field(default_factory=list)


class Notifications(BaseModel):
    notifications: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class RegularCheckState(BaseModel):
    # act_agent loop messages
    messages: Annotated[List[AnyMessage], add_messages] = Field(default_factory=list)
    # pre-fetched context injected into act_agent system prompt
    current_status: str = Field(default="")
    # output of define_manual_actions
    manual_actions: List[str] = Field(default_factory=list)
    # output of define_notifications
    notifications: List[str] = Field(default_factory=list)
    # trigger override (optional, for manual runs)
    trigger_message: Optional[str] = Field(default=None)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def fetch_context(state: RegularCheckState) -> dict:
    """Non-AI node: fetch current plant status and check instructions before the agent runs."""
    client = get_mcp_client()
    tools = await client.get_tools()
    tool_map = {t.name: t for t in tools}

    status_tool = tool_map.get("get_current_status")
    if not status_tool:
        log.warning("get_current_status tool not found, proceeding with empty context")
        return {"current_status": "{}"}

    instructions_tool = tool_map.get("get_regular_check_instructions")
    instructions = ""
    if instructions_tool:
        try:
            instructions = await instructions_tool.ainvoke({})
        except Exception as exc:
            log.warning("Could not fetch check instructions: %s", exc)

    result = await status_tool.ainvoke({})
    status_json = json.dumps(result, ensure_ascii=False)

    combined = status_json
    if instructions:
        combined = f"{instructions}\n\n--- CURRENT STATUS ---\n{status_json}"

    return {"current_status": combined}


async def act_agent(state: RegularCheckState) -> dict:
    """AI node #1: analyse current status and take automated actions."""
    client = get_mcp_client()
    tools = await client.get_tools()
    # Only expose tools relevant to this node
    allowed = {"call_ha_api", "get_recent_actions", "get_all_devices"}
    act_tools = [t for t in tools if t.name in allowed]

    model = llm.bind_tools(act_tools)
    history = list(state.messages or [])

    if not history:
        system = ACT_SYSTEM_PROMPT.format(current_status=state.current_status)
        trigger = state.trigger_message or "Please perform the regular plant check now."
        history = [
            SystemMessage(content=system),
            HumanMessage(content=trigger),
        ]

    response = await model.ainvoke(history)
    return {"messages": [response]}


async def act_tools(state: RegularCheckState) -> dict:
    """Non-AI node: execute tool calls from act_agent."""
    client = get_mcp_client()
    tools = await client.get_tools()
    allowed = {"call_ha_api", "get_recent_actions", "get_all_devices"}
    act_tools_list = [t for t in tools if t.name in allowed]
    tool_node = ToolNode(act_tools_list)
    return await tool_node.ainvoke(state)


def should_continue(state: RegularCheckState) -> str:
    last = state.messages[-1] if state.messages else None
    if last and getattr(last, "tool_calls", None):
        return "act_tools"
    return "define_manual_actions"


async def define_manual_actions(state: RegularCheckState) -> dict:
    """AI node #2: structured extraction of what humans need to do manually."""
    structured_llm = llm.with_structured_output(ManualActions)
    history = list(state.messages or [])
    history.append(HumanMessage(content=DEFINE_MANUAL_ACTIONS_PROMPT))
    result: ManualActions = await structured_llm.ainvoke(history)
    log.info("Manual actions: %d — %s", len(result.manual_actions), result.manual_actions)
    return {"manual_actions": result.manual_actions}


async def define_notifications(state: RegularCheckState) -> dict:
    """AI node #3: decide which manual_actions are new (not in recent issues log)."""
    client = get_mcp_client()
    tools = await client.get_tools()
    issues_tool = next((t for t in tools if t.name == "get_recent_issues"), None)

    previous_issues_text = "No previous issues recorded."
    if issues_tool:
        try:
            resp = await issues_tool.ainvoke({"hours": 48})
            items = resp.get("items", []) if isinstance(resp, dict) else []
            if items:
                previous_issues_text = "\n".join(f"- {i}" for i in items)
        except Exception as exc:
            log.warning("Could not fetch recent issues: %s", exc)

    if not state.manual_actions:
        return {"notifications": []}

    current_issues_text = "\n".join(f"- {a}" for a in state.manual_actions)

    structured_llm = llm.with_structured_output(Notifications)
    messages = [
        SystemMessage(
            content=DEFINE_NOTIFICATIONS_SYSTEM.format(
                previous_issues=previous_issues_text
            )
        ),
        HumanMessage(
            content=DEFINE_NOTIFICATIONS_HUMAN.format(
                current_issues=current_issues_text
            )
        ),
    ]
    result: Notifications = await structured_llm.ainvoke(messages)
    log.info("Notifications: %d — %s", len(result.notifications), result.notifications)
    return {"notifications": result.notifications}


async def notify(state: RegularCheckState) -> dict:
    """Non-AI node: send phone notification and write issues log to HA."""
    client = get_mcp_client()
    tools = await client.get_tools()
    call_tool = next((t for t in tools if t.name == "call_ha_api"), None)

    if not call_tool:
        log.error("call_ha_api tool not found, cannot notify")
        return {}

    # Write current manual_actions to issues log (even if empty — resets dedup state)
    try:
        await call_tool.ainvoke({
            "method": "POST",
            "path": "/api/services/plants/update_agent_log",
            "reason": "Persist current check issues for deduplication in next run",
            "body": {"field": "plant_check_issues", "items": state.manual_actions},
        })
        log.info("Wrote %d issue(s) to plant_check_issues.", len(state.manual_actions))
    except Exception as exc:
        log.warning("Failed to write issues log: %s", exc)

    if not state.notifications:
        log.info("No new notifications to send.")
        return {}

    message = "\n".join(f"- {n}" for n in state.notifications)
    try:
        await call_tool.ainvoke({
            "method": "POST",
            "path": "/api/services/notify/mobile_app_iphone_2",
            "reason": "Send plant check notification to user",
            "body": {
                "title": "🌿 Plant Check",
                "message": message,
            },
        })
        log.info("Notification sent.")
    except Exception as exc:
        log.warning("Failed to send notification: %s", exc)

    return {}


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

builder = StateGraph(RegularCheckState)
builder.add_node("fetch_context", fetch_context)
builder.add_node("act_agent", act_agent)
builder.add_node("act_tools", act_tools)
builder.add_node("define_manual_actions", define_manual_actions)
builder.add_node("define_notifications", define_notifications)
builder.add_node("notify", notify)

builder.add_edge(START, "fetch_context")
builder.add_edge("fetch_context", "act_agent")
builder.add_conditional_edges("act_agent", should_continue)
builder.add_edge("act_tools", "act_agent")
builder.add_edge("define_manual_actions", "define_notifications")
builder.add_edge("define_notifications", "notify")
builder.add_edge("notify", END)

graph_regular_check = builder.compile()
