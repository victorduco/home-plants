from __future__ import annotations

import json
import logging
from typing import List, Optional, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field  # BaseModel/Field still used for ManualActions, Notifications

from .mcp_tools import get_mcp_client

log = logging.getLogger("g_regular_check")

llm = ChatOpenAI(model="gpt-4.1-2025-04-14", temperature=0.2)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

ACT_SYSTEM_PROMPT = """You are a home plant care assistant performing a regular check.
Be decisive — act first. Do not ask for confirmation. Do not write a report.

## Current status
{current_status}

## Time of day

Use `time.current`, `sunrise`, and `sunset` from current status to determine the time of day:
- **Daytime**: from sunrise to sunset
- **Evening/Night**: from sunset to midnight
- **Night**: midnight to ~5:00
- **Morning**: from ~5:00 to sunrise

## How to read plant data

Each plant has:
- `soil_moisture.zone` — `green` (fine) / `yellow` (getting dry, water soon) / `red` (critically dry, water now) / `unknown` (sensor unavailable)
- `air_humidity.zone` — `green` (fine) / `yellow` (too dry) / `red` (way too dry OR way too high — check actual value vs needed range)
- `air_temperature.zone` — `green` (fine) / `yellow` or `red` (too cold or hot)
- `care_history` — list of recent days with watering counts; if watered today or yesterday, treat moisture as less urgent

**Important for humidity**: `air_humidity.zone` can be red both when humidity is too LOW and too HIGH. Always check the actual measured humidity value against the plant's `needed_min` / `needed_max`. If humidity is above `needed_max` — the zone is red because it's TOO HIGH, not too dry.

## Available actions via `call_ha_api`

**Water a plant** — find `valve.*` entity_id in the plant's `entities`, then call:
- method: POST, path: /api/services/valve/open_valve, body: {{"entity_id": "<valve_entity_id>"}}
- method: POST, path: /api/services/valve/close_valve, body: {{"entity_id": "<valve_entity_id>"}}

**Humidifier** — call `get_all_devices` first to get entity_id and which plants are nearby:
- method: POST, path: /api/services/switch/turn_on, body: {{"entity_id": "<humidifier_entity_id>"}}
- method: POST, path: /api/services/switch/turn_off, body: {{"entity_id": "<humidifier_entity_id>"}}

Humidifier decision rules (check actual humidity value against plant `needed_min` / `needed_max`):
1. If current humidity is ABOVE any nearby plant's `needed_max` → turn OFF humidifier regardless of zone color
2. **Night / Evening (after sunset, before 5:00)**: turn OFF humidifier UNLESS current humidity is critically low (below `needed_min` by more than 10%) for ALL nearby plants that need high humidity
3. **Daytime / Morning**: turn ON if any nearby plant's humidity is below `needed_min` (zone red or yellow due to low humidity); turn OFF if all are at or above `needed_max`

**Thermostat** — available in `devices.thermostat` in current status. Use `climate_entity_id` from there:
- Set temperature: method: POST, path: /api/services/climate/set_temperature, body: {{"entity_id": "<climate_entity_id>", "temperature": <target_f>}}
- Set mode: method: POST, path: /api/services/climate/set_hvac_mode, body: {{"entity_id": "<climate_entity_id>", "hvac_mode": "heat"|"cool"|"heat_cool"|"off"}}

Thermostat decision rules:
- **Night (after sunset, before 5:00)**: maintain temperature ~2°F (1°C) BELOW the plant's daytime minimum — cooler nights are beneficial for plants
- **Daytime / Morning**: act if any plant's `air_temperature` zone is "red". Adjust target_temperature toward the plant's needed range. Don't change if all zones are green.

**Grow lights** — time-based, use `time.current` / `sunrise` / `sunset` from current status:
- method: POST, path: /api/services/switch/turn_on, body: {{"entity_id": "<light_entity_id>"}}
- method: POST, path: /api/services/switch/turn_off, body: {{"entity_id": "<light_entity_id>"}}

Grow light rules:
- **Daytime (sunrise to sunset)**: turn ON — always, this is the required grow period
- **Morning (5:00 to sunrise)**: turn ON — supplement light before sunrise
- **Evening / Night (after sunset)**: turn OFF — no exceptions, plants need dark rest
- If the light is already in the correct state, skip the action.
"""

DEFINE_MANUAL_ACTIONS_PROMPT = """You are reviewing a plant care session log to extract issues that require human attention.

The agent has already taken automated actions (grow lights, humidifier, valves).
Your job: extract only problems that humans need to act on.

Rules:
- Humidifier is ON but a plant's air_humidity zone is "red" AND humidity is BELOW the plant's needed_min → "Humidifier is on but humidity too low for [plants] — check humidifier settings/water level"
- Humidifier is OFF but humidity is ABOVE needed_max → do NOT report (this is correct behavior, no action needed)
- Unavailable sensors (zone = "unknown") → one item: "Sensors unavailable: Plant A, Plant B"
- Broken/unconfigured devices
- Temperature issues (zone = "red") — if thermostat adjusted but temperature still red, report it
- Do NOT include: green zones, successful automated actions, per-plant status table
- Do NOT flag humidifier being off at night as an issue — that is the intended nighttime behavior

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


class RegularCheckState(TypedDict, total=False):
    messages: List[AnyMessage]  # plain list, nodes manage accumulation manually
    current_status: str
    previous_issues: List[str]
    manual_actions: List[str]
    notifications: List[str]
    trigger_message: Optional[str]


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def _parse_mcp_response(resp) -> str:
    """Extract plain text from MCP tool response (list of content blocks or raw string/dict)."""
    if isinstance(resp, list) and resp:
        resp = resp[0].get("text", "") if isinstance(resp[0], dict) else str(resp[0])
    if isinstance(resp, dict):
        return json.dumps(resp, ensure_ascii=False)
    return str(resp) if resp is not None else ""


async def fetch_context(state: RegularCheckState) -> dict:
    """Non-AI node: fetch current plant status and check instructions before the agent runs."""
    client = get_mcp_client()
    tools = await client.get_tools()
    tool_map = {t.name: t for t in tools}

    status_tool = tool_map.get("get_current_status")
    if not status_tool:
        log.warning("get_current_status tool not found, proceeding with empty context")
        return {"current_status": "{}"}

    status_json = _parse_mcp_response(await status_tool.ainvoke({}))
    return {"current_status": status_json, "messages": []}



async def act_agent(state: RegularCheckState) -> dict:
    """AI node #1: analyse current status and take automated actions."""
    client = get_mcp_client()
    tools = await client.get_tools()
    allowed = {"call_ha_api", "get_all_devices"}
    act_tools = [t for t in tools if t.name in allowed]

    all_messages = list(state.get("messages") or [])
    model = llm.bind_tools(act_tools)

    # Find the start of the current run: last SystemMessage in state.messages.
    # On the first call within a run it won't exist yet, so we inject one.
    # On subsequent calls (after tool execution) it's already there.
    last_system_idx = next(
        (i for i in range(len(all_messages) - 1, -1, -1) if isinstance(all_messages[i], SystemMessage)),
        None,
    )

    if last_system_idx is None:
        # First call in this run — build fresh history
        system = ACT_SYSTEM_PROMPT.format(current_status=state.get("current_status", ""))
        trigger = state.get("trigger_message") or "Please perform the regular plant check now."
        init_messages = [SystemMessage(content=system), HumanMessage(content=trigger)]
        response = await model.ainvoke(init_messages)
        log.info("act_agent (init): messages=%d", len(init_messages))
        return {"messages": init_messages + [response]}

    # Subsequent call — use history from current run only (from last SystemMessage onward)
    history = all_messages[last_system_idx:]
    log.info("act_agent: messages=%d types=%s", len(history), [type(m).__name__ for m in history])
    for i, m in enumerate(history):
        log.info("act_agent[%d]: type=%s tool_call_id=%s content=%.200s",
                 i, type(m).__name__, getattr(m, "tool_call_id", "-"), repr(m.content)[:200])
    response = await model.ainvoke(history)
    return {"messages": all_messages + [response]}


async def act_tools(state: RegularCheckState) -> dict:
    """Non-AI node: execute tool calls from act_agent."""
    client = get_mcp_client()
    tools = await client.get_tools()
    allowed = {"call_ha_api", "get_all_devices"}
    act_tools_list = [t for t in tools if t.name in allowed]
    tool_node = ToolNode(act_tools_list)
    current = list(state.get("messages", []))
    result = await tool_node.ainvoke({"messages": current})
    tool_messages = result.get("messages", [])
    for m in tool_messages:
        log.info("act_tools result: tool_call_id=%s content_type=%s content=%.200s",
                 getattr(m, "tool_call_id", "?"), type(m.content).__name__, repr(m.content))
    return {"messages": current + tool_messages}


def should_continue(state: RegularCheckState) -> str:
    messages = state.get("messages", [])
    last = messages[-1] if messages else None
    if last and getattr(last, "tool_calls", None):
        return "act_tools"
    return "define_manual_actions"


async def fetch_previous_issues(state: RegularCheckState) -> dict:
    """Non-AI node: fetch issues logged in previous runs for deduplication."""
    client = get_mcp_client()
    tools = await client.get_tools()
    issues_tool = next((t for t in tools if t.name == "get_recent_issues"), None)

    if not issues_tool:
        return {"previous_issues": []}

    try:
        resp = json.loads(_parse_mcp_response(await issues_tool.ainvoke({"hours": 48})))
        items = resp.get("items", []) if isinstance(resp, dict) else []
        log.info("Previous issues fetched: %d", len(items))
        return {"previous_issues": items}
    except Exception as exc:
        log.warning("Could not fetch recent issues: %s", exc)
        return {"previous_issues": []}


async def define_manual_actions(state: RegularCheckState) -> dict:
    """AI node #2: structured extraction of what humans need to do manually."""
    structured_llm = llm.with_structured_output(ManualActions)
    history = list(state.get("messages") or [])
    history.append(HumanMessage(content=DEFINE_MANUAL_ACTIONS_PROMPT))
    result: ManualActions = await structured_llm.ainvoke(history)
    log.info("Manual actions: %d — %s", len(result.manual_actions), result.manual_actions)
    return {"manual_actions": result.manual_actions}


async def define_notifications(state: RegularCheckState) -> dict:
    """AI node #3: decide which manual_actions are new (not in recent issues log)."""
    previous_issues_text = (
        "\n".join(f"- {i}" for i in state.get("previous_issues") or [])
        or "No previous issues recorded."
    )

    if not state.get("manual_actions"):
        return {"notifications": []}

    current_issues_text = "\n".join(f"- {a}" for a in state.get("manual_actions", []))

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
            "body": {"field": "plant_check_issues", "items": state.get("manual_actions", [])},
        })
        log.info("Wrote %d issue(s) to plant_check_issues.", len(state.get("manual_actions", [])))
    except Exception as exc:
        log.warning("Failed to write issues log: %s", exc)

    if not state.get("notifications"):
        log.info("No new notifications to send.")
        return {}

    message = "\n".join(f"- {n}" for n in state.get("notifications", []))
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
builder.add_node("fetch_previous_issues", fetch_previous_issues)
builder.add_node("define_notifications", define_notifications)
builder.add_node("notify", notify)

builder.add_edge(START, "fetch_context")
builder.add_edge("fetch_context", "act_agent")
builder.add_conditional_edges("act_agent", should_continue, ["act_tools", "define_manual_actions"])
builder.add_edge("act_tools", "act_agent")
builder.add_edge("define_manual_actions", "fetch_previous_issues")
builder.add_edge("fetch_previous_issues", "define_notifications")
builder.add_edge("define_notifications", "notify")
builder.add_edge("notify", END)

graph_regular_check = builder.compile()
