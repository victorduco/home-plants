from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, List, Optional, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langsmith import get_current_run_tree
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from . import dedup
from .issues import (
    PUSH_SEVERITIES,
    Issue,
    evaluate,
    parse_log_keys,
    render_log_lines,
    render_message,
)
from .mcp_tools import get_tool_map, get_tools
from .prompts import ACT_SYSTEM_PROMPT

log = logging.getLogger("g_regular_check")

llm = ChatOpenAI(model="gpt-4.1-2025-04-14", temperature=0.2)

# The agent decides humidifier and thermostat only. Grow lights are a pure function of
# the clock and are applied by control_lights instead.
ACT_TOOLS = {"call_ha_api", "get_all_devices", "no_action"}

GROW_LIGHTS = ("horizontal_grow_light", "vertical_grow_light")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class RegularCheckState(TypedDict, total=False):
    messages: List[AnyMessage]  # plain list, nodes manage accumulation manually
    current_status: str
    status: dict
    issues: List[dict]
    notified_entries: List[dict]
    previous_keys: Optional[List[str]]
    new_issues: List[dict]
    actions_taken: List[str]
    trigger_message: Optional[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_mcp_response(resp) -> str:
    """Extract plain text from MCP tool response (list of content blocks or raw string/dict)."""
    if isinstance(resp, list) and resp:
        resp = resp[0].get("text", "") if isinstance(resp[0], dict) else str(resp[0])
    if isinstance(resp, dict):
        return json.dumps(resp, ensure_ascii=False)
    return str(resp) if resp is not None else ""


def _loads(raw: Any) -> dict:
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def _call_ha(method: str, path: str, reason: str, body: dict | None = None) -> Any:
    tool = (await get_tool_map()).get("call_ha_api")
    if tool is None:
        raise RuntimeError("call_ha_api tool not available")
    return await tool.ainvoke({"method": method, "path": path, "reason": reason, "body": body or {}})


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def fetch_context(state: RegularCheckState) -> dict:
    """Non-AI node: fetch current plant status before the agent runs."""
    status_tool = (await get_tool_map()).get("get_current_status")
    if not status_tool:
        log.warning("get_current_status tool not found, proceeding with empty context")
        return {"current_status": "{}", "status": {}}

    status_json = _parse_mcp_response(await status_tool.ainvoke({}))
    return {"current_status": status_json, "status": _loads(status_json), "messages": []}


async def control_lights(state: RegularCheckState) -> dict:
    """Non-AI node: hold the grow lights at whatever the time of day requires.

    The schedule has no judgement in it, and leaving it to the model produced 42 confirmed
    night-time switch-ons — some from misreading the hour, some where the model narrated
    "no action needed" and issued turn_on anyway. Doing it here makes the wrong action
    unreachable.
    """
    status = state.get("status") or {}
    desired = ((status.get("time") or {}).get("grow_lights_should_be"))
    if desired not in ("on", "off"):
        log.warning("No grow_lights_should_be in status; leaving lights untouched")
        return {}

    devices = status.get("devices") or {}
    actions: List[str] = []
    for name in GROW_LIGHTS:
        device = devices.get(name) or {}
        entity_id = device.get("entity_id")
        if not entity_id:
            continue
        if str(device.get("state") or "").lower() == desired:
            continue
        period = (status.get("time") or {}).get("period")
        await _call_ha(
            "POST",
            f"/api/services/switch/turn_{desired}",
            f"Grow light schedule: period is {period}, lights must be {desired}.",
            {"entity_id": entity_id},
        )
        actions.append(f"Turned {name.replace('_', ' ')} {desired} ({period})")

    if actions:
        log.info("control_lights: %s", actions)
    return {"actions_taken": list(state.get("actions_taken") or []) + actions}


async def act_agent(state: RegularCheckState) -> dict:
    """AI node: judgement calls on humidifier and thermostat."""
    act_tools = [t for t in await get_tools() if t.name in ACT_TOOLS]

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
        system = ACT_SYSTEM_PROMPT.format(current_status=state.get("current_status", ""))
        trigger = state.get("trigger_message") or "Please perform the regular plant check now."
        init_messages = [SystemMessage(content=system), HumanMessage(content=trigger)]

        run = get_current_run_tree()
        if run:
            run.name = f"regular check: {trigger[:60]}"
            run.tags = list(run.tags or []) + ["regular-check"]

        response = await model.ainvoke(init_messages)
        log.info("act_agent (init): messages=%d", len(init_messages))
        return {"messages": init_messages + [response]}

    history = all_messages[last_system_idx:]
    response = await model.ainvoke(history)
    return {"messages": all_messages + [response]}


_LIGHTS_ARE_NOT_YOURS = (
    '{"status":"error","error":"Grow lights run on a fixed schedule and were already '
    'applied automatically this run. Do not call switch services for them."}'
)


def _withhold_grow_light_calls(messages: list) -> tuple[list, list]:
    """Strip grow-light calls from the pending tool calls, answering them with a refusal.

    The prompt already tells the agent lights are not its concern, but the same prompt
    told it to leave them off at night and it issued 42 switch-ons anyway. Enforcing it
    here means a regression in the model's behaviour cannot reach the switch.
    """
    if not messages:
        return messages, []
    last = messages[-1]
    calls = list(getattr(last, "tool_calls", None) or [])
    if not calls:
        return messages, []

    allowed, blocked = [], []
    for call in calls:
        entity = str(((call.get("args") or {}).get("body") or {}).get("entity_id") or "")
        (blocked if call.get("name") == "call_ha_api" and "grow_light" in entity else allowed).append(call)

    if not blocked:
        return messages, []

    log.warning("Withheld %d grow-light call(s) from act_agent", len(blocked))
    refusals = [
        ToolMessage(tool_call_id=c.get("id"), name=c.get("name"), content=_LIGHTS_ARE_NOT_YOURS)
        for c in blocked
    ]
    trimmed = last.model_copy(update={"tool_calls": allowed})
    return messages[:-1] + [trimmed], refusals


async def act_tools(state: RegularCheckState) -> dict:
    """Non-AI node: execute tool calls from act_agent."""
    tools = [t for t in await get_tools() if t.name in ACT_TOOLS]
    # handle_tool_errors keeps a malformed call (a bad argument name, a missing
    # entity_id) as a message the model can correct, instead of raising through
    # Pregel and killing the whole run.
    tool_node = ToolNode(tools, handle_tool_errors=True)
    current = list(state.get("messages", []))

    to_execute, refusals = _withhold_grow_light_calls(current)
    if to_execute and getattr(to_execute[-1], "tool_calls", None):
        result = await tool_node.ainvoke({"messages": to_execute})
        tool_messages = list(result.get("messages", [])) + refusals
    else:
        tool_messages = refusals

    actions = list(state.get("actions_taken") or [])
    by_id = {}
    for message in reversed(current):
        for call in getattr(message, "tool_calls", None) or []:
            by_id.setdefault(call.get("id"), call)

    # Withheld calls never reached a device, so they are not something the user did or
    # the agent achieved — control_lights already reported whatever it changed.
    withheld = {r.tool_call_id for r in refusals}

    for m in tool_messages:
        if getattr(m, "tool_call_id", None) in withheld:
            continue
        call = by_id.get(getattr(m, "tool_call_id", None)) or {}
        if call.get("name") != "call_ha_api":
            continue
        args = call.get("args") or {}
        path = str(args.get("path") or "")
        if "/api/services/" not in path or "update_agent_log" in path or "/notify/" in path:
            continue
        entity = (args.get("body") or {}).get("entity_id", "")
        service = path.split("/api/services/")[-1]
        content = str(getattr(m, "content", ""))
        outcome = "failed: " if '"status": "error"' in content or '"status":"error"' in content else ""
        actions.append(f"{outcome}{service}{' → ' + entity if entity else ''}")

    return {"messages": current + tool_messages, "actions_taken": actions}


def should_continue(state: RegularCheckState) -> str:
    messages = state.get("messages", [])
    last = messages[-1] if messages else None
    if last and getattr(last, "tool_calls", None):
        return "act_tools"
    return "evaluate_issues"


async def evaluate_issues(state: RegularCheckState) -> dict:
    """Non-AI node: derive the issue list arithmetically from the status snapshot.

    Re-reads the status so device changes made by control_lights and act_agent are
    reflected, and so the humidifier state quoted to the user is the state after the
    agent acted rather than before.
    """
    status_tool = (await get_tool_map()).get("get_current_status")
    status = state.get("status") or {}
    if status_tool:
        refreshed = _loads(_parse_mcp_response(await status_tool.ainvoke({})))
        if refreshed.get("status") == "success":
            status = refreshed

    issues = evaluate(status)
    log.info("Issues: %d — %s", len(issues), [i.key for i in issues])
    return {"issues": [i.__dict__ for i in issues], "status": status}


async def load_notified(state: RegularCheckState) -> dict:
    """Non-AI node: read the notification ledger and the previous run's issue snapshot."""
    tools = await get_tool_map()
    result: dict = {"notified_entries": [], "previous_keys": None}

    issues_tool = tools.get("get_recent_issues")
    if issues_tool:
        try:
            resp = json.loads(_parse_mcp_response(
                await issues_tool.ainvoke({"hours": dedup.LEDGER_RETENTION_HOURS})
            ))
            result["notified_entries"] = resp.get("items", []) if isinstance(resp, dict) else []
            log.info("Notification ledger: %d entries", len(result["notified_entries"]))
        except Exception as exc:
            log.warning("Could not read notification ledger: %s", exc)

    # previous_keys stays None if the snapshot cannot be read, which disables the
    # persistence requirement rather than silently swallowing every issue.
    try:
        resp = _loads(_parse_mcp_response(await _call_ha(
            "GET",
            "/api/states/sensor.agent_log_plant_check_issues",
            "Read the previous run's issue snapshot for notification debouncing",
        )))
        items = ((resp.get("data") or {}).get("attributes") or {}).get("items") or []
        result["previous_keys"] = sorted(parse_log_keys(items))
    except Exception as exc:
        log.warning("Could not read previous issue snapshot: %s", exc)

    return result


async def decide_notifications(state: RegularCheckState) -> dict:
    """Non-AI node: suppress anything already pushed inside the re-notify window."""
    issues = [Issue(**i) for i in state.get("issues") or []]
    pushable = [i for i in issues if i.severity in PUSH_SEVERITIES]
    new = dedup.select_new(
        pushable,
        state.get("notified_entries") or [],
        previous_keys=state.get("previous_keys"),
    )
    log.info("New notifications: %d of %d pushable issues (%d total)",
             len(new), len(pushable), len(issues))
    return {"new_issues": [i.__dict__ for i in new]}


async def notify(state: RegularCheckState) -> dict:
    """Non-AI node: push the grouped message and update both logs."""
    issues = [Issue(**i) for i in state.get("issues") or []]
    new_issues = [Issue(**i) for i in state.get("new_issues") or []]

    try:
        await _call_ha(
            "POST",
            "/api/services/plants/update_agent_log",
            "Persist the current issue snapshot for the dashboard",
            {"field": "plant_check_issues", "items": render_log_lines(issues)},
        )
    except Exception as exc:
        log.warning("Failed to write issues log: %s", exc)

    if not new_issues:
        log.info("No new notifications to send (%d issues, all within re-notify window).", len(issues))
        return {}

    message = render_message(new_issues, state.get("actions_taken") or [])
    try:
        await _call_ha(
            "POST",
            "/api/services/notify/mobile_app_iphone_2",
            "Send plant check notification to user",
            {"title": "🌿 Plant Check", "message": message},
        )
        log.info("Notification sent: %d issue(s).", len(new_issues))
    except Exception as exc:
        log.warning("Failed to send notification: %s", exc)
        return {}

    # Only record what actually went out, so a failed push retries next run.
    try:
        await _call_ha(
            "POST",
            "/api/services/plants/update_agent_log",
            "Record pushed notifications for deduplication",
            {
                "field": "plant_check_notified",
                "items": dedup.build_ledger(
                    state.get("notified_entries") or [], new_issues, datetime.now(timezone.utc)
                ),
            },
        )
    except Exception as exc:
        log.warning("Failed to update notification ledger: %s", exc)

    return {}


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------

builder = StateGraph(RegularCheckState)
builder.add_node("fetch_context", fetch_context)
builder.add_node("control_lights", control_lights)
builder.add_node("act_agent", act_agent)
builder.add_node("act_tools", act_tools)
builder.add_node("evaluate_issues", evaluate_issues)
builder.add_node("load_notified", load_notified)
builder.add_node("decide_notifications", decide_notifications)
builder.add_node("notify", notify)

builder.add_edge(START, "fetch_context")
builder.add_edge("fetch_context", "control_lights")
builder.add_edge("control_lights", "act_agent")
builder.add_conditional_edges("act_agent", should_continue, ["act_tools", "evaluate_issues"])
builder.add_edge("act_tools", "act_agent")
builder.add_edge("evaluate_issues", "load_notified")
builder.add_edge("load_notified", "decide_notifications")
builder.add_edge("decide_notifications", "notify")
builder.add_edge("notify", END)

graph_regular_check = builder.compile()
