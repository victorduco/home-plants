"""Regression tests for the server-side tablet render_template guard."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest


def _load_guard_module():
    trackers = []

    homeassistant = types.ModuleType("homeassistant")
    components = types.ModuleType("homeassistant.components")
    websocket_api = types.ModuleType("homeassistant.components.websocket_api")
    websocket_const = types.ModuleType("homeassistant.components.websocket_api.const")
    websocket_const.ERR_TEMPLATE_ERROR = "template_error"
    websocket_messages = types.ModuleType(
        "homeassistant.components.websocket_api.messages"
    )
    websocket_messages.event_message = (
        lambda subscription_id, payload: {
            "id": subscription_id,
            "type": "event",
            "event": payload,
        }
    )
    websocket_api.const = websocket_const
    websocket_api.messages = websocket_messages
    components.websocket_api = websocket_api

    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    core.callback = lambda function: function

    exceptions = types.ModuleType("homeassistant.exceptions")

    class TemplateError(Exception):
        pass

    exceptions.TemplateError = TemplateError

    helpers = types.ModuleType("homeassistant.helpers")
    template_module = types.ModuleType("homeassistant.helpers.template")

    class Template:
        def __init__(self, content, hass):
            self.content = content
            self.hass = hass

    template_module.Template = Template

    event_module = types.ModuleType("homeassistant.helpers.event")

    class TrackTemplate:
        def __init__(self, template, variables):
            self.template = template
            self.variables = variables

    class TrackTemplateResult:
        def __init__(self, result):
            self.result = result

    class FakeTrackInfo:
        def __init__(self, tracked, listener):
            self.tracked = tracked
            self.listener = listener
            self.listeners = {"all": False}
            self.remove_calls = 0

        def async_refresh(self):
            self.emit(f"render:{self.tracked[0].template.content}")

        def emit(self, result):
            self.listener(None, [TrackTemplateResult(result)])

        def async_remove(self):
            self.remove_calls += 1

    def async_track_template_result(hass, tracked, listener, strict=False):
        info = FakeTrackInfo(tracked, listener)
        trackers.append(info)
        return info

    event_module.TrackTemplate = TrackTemplate
    event_module.TrackTemplateResult = TrackTemplateResult
    event_module.async_track_template_result = async_track_template_result
    helpers.template = template_module
    helpers.event = event_module

    homeassistant.components = components
    homeassistant.core = core
    homeassistant.exceptions = exceptions
    homeassistant.helpers = helpers
    sys.modules.update(
        {
            "homeassistant": homeassistant,
            "homeassistant.components": components,
            "homeassistant.components.websocket_api": websocket_api,
            "homeassistant.components.websocket_api.const": websocket_const,
            "homeassistant.components.websocket_api.messages": websocket_messages,
            "homeassistant.core": core,
            "homeassistant.exceptions": exceptions,
            "homeassistant.helpers": helpers,
            "homeassistant.helpers.template": template_module,
            "homeassistant.helpers.event": event_module,
        }
    )

    path = (
        Path(__file__).parents[1]
        / "ha/custom_components/render_template_guard/__init__.py"
    )
    spec = importlib.util.spec_from_file_location("render_template_guard_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module._test_trackers = trackers
    return module


guard = _load_guard_module()


def tablet_template(suffix: str = "") -> str:
    return " ".join((*guard._TARGET_MARKERS, suffix))


class FakeConnection:
    def __init__(self) -> None:
        self.subscriptions = {}
        self.results = []
        self.events = []
        self.errors = []

    def send_result(self, subscription_id, result=None):
        self.results.append(subscription_id)

    def send_message(self, message):
        self.events.append(message)

    def send_error(self, subscription_id, code, message):
        self.errors.append((subscription_id, code, message))


class FakeTimerHandle:
    def __init__(self, when, callback) -> None:
        self.when = when
        self.callback = callback
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class FakeLoop:
    """Small deterministic scheduler for refresh and debounce callbacks."""

    def __init__(self) -> None:
        self.now = 0.0
        self.soon = []
        self.timers = []

    def call_soon_threadsafe(self, callback):
        self.soon.append(callback)

    def call_later(self, delay, callback):
        handle = FakeTimerHandle(self.now + delay, callback)
        self.timers.append(handle)
        return handle

    def run_soon(self):
        while self.soon:
            callbacks, self.soon = self.soon, []
            for callback in callbacks:
                callback()

    def advance(self, seconds):
        target = self.now + seconds
        self.run_soon()
        while True:
            due = [
                handle
                for handle in self.timers
                if not handle.cancelled and handle.when <= target
            ]
            if not due:
                break
            handle = min(due, key=lambda item: item.when)
            self.timers.remove(handle)
            self.now = handle.when
            handle.callback()
            self.run_soon()
        self.now = target

    @property
    def pending_timer_count(self):
        return sum(not handle.cancelled for handle in self.timers)


class FakeHass:
    def __init__(self, handler) -> None:
        self.data = {"websocket_api": {"render_template": (handler, "schema")}}
        self.loop = FakeLoop()


def core_handler_fixture():
    calls = []

    def handler(hass, connection, msg):
        calls.append(msg["id"])

    return handler, calls


class RenderTemplateGuardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        guard._test_trackers.clear()
        handler, self.core_calls = core_handler_fixture()
        self.hass = FakeHass(handler)
        self.connection = FakeConnection()
        self.assertTrue(await guard.async_setup(self.hass, {}))
        self.handler, self.schema = self.hass.data["websocket_api"]["render_template"]

    def message(self, subscription_id, template=None, **overrides):
        message = {
            "id": subscription_id,
            "type": "render_template",
            "template": template or tablet_template(),
            "strict": False,
            "report_errors": False,
        }
        message.update(overrides)
        return message

    async def test_rapid_duplicate_batch_is_bounded_and_latest_wins(self):
        for subscription_id in range(1, 175):
            self.handler(self.hass, self.connection, self.message(subscription_id))
        self.hass.loop.run_soon()

        self.assertEqual(self.core_calls, [])
        self.assertEqual(len(guard._test_trackers), 1)
        self.assertEqual(len(self.connection.subscriptions), 2)
        self.assertEqual(list(self.connection.subscriptions), [173, 174])
        self.assertEqual(self.connection.results, list(range(1, 175)))
        self.assertEqual(
            [event["id"] for event in self.connection.events],
            [174],
        )
        groups = {
            id(getattr(remove, guard._GROUP_ATTRIBUTE))
            for remove in self.connection.subscriptions.values()
        }
        self.assertEqual(len(groups), 1)

    async def test_late_alias_gets_one_cached_render_after_quiet_period(self):
        self.handler(self.hass, self.connection, self.message(1))
        self.hass.loop.run_soon()
        self.connection.events.clear()

        self.handler(self.hass, self.connection, self.message(2))

        self.assertEqual(self.connection.results[-1], 2)
        self.assertEqual(self.connection.events, [])
        self.assertEqual(self.hass.loop.pending_timer_count, 1)
        self.hass.loop.advance(guard._REPLAY_DEBOUNCE_SECONDS - 0.001)
        self.assertEqual(self.connection.events, [])
        self.hass.loop.advance(0.001)
        self.assertEqual([event["id"] for event in self.connection.events], [2])
        self.assertIn("render:", self.connection.events[0]["event"]["result"])

    async def test_stale_remover_cannot_stop_latest_subscriber(self):
        self.handler(self.hass, self.connection, self.message(1))
        self.handler(self.hass, self.connection, self.message(2))
        self.hass.loop.run_soon()
        tracker = guard._test_trackers[0]
        self.connection.events.clear()

        self.connection.subscriptions.pop(1)()
        self.assertEqual(tracker.remove_calls, 0)
        tracker.emit("next")
        self.assertEqual([event["id"] for event in self.connection.events], [2])
        self.assertEqual(self.connection.events[0]["event"]["result"], "next")

        self.connection.subscriptions.pop(2)()
        self.assertEqual(tracker.remove_calls, 1)
        self.assertEqual(self.connection.subscriptions, {})

    async def test_active_unsubscribe_cleans_retired_tombstone(self):
        self.handler(self.hass, self.connection, self.message(1))
        self.handler(self.hass, self.connection, self.message(2))
        self.hass.loop.run_soon()
        tracker = guard._test_trackers[0]

        self.connection.subscriptions.pop(2)()

        self.assertEqual(tracker.remove_calls, 1)
        self.assertEqual(self.connection.subscriptions, {})
        self.assertEqual(self.hass.data[guard.DOMAIN]["groups"], set())

    async def test_ten_thousand_replacements_keep_at_most_two_protocol_entries(self):
        self.handler(self.hass, self.connection, self.message(1))
        self.hass.loop.run_soon()
        self.connection.events.clear()

        for subscription_id in range(2, 10_002):
            self.handler(self.hass, self.connection, self.message(subscription_id))

        self.assertEqual(len(guard._test_trackers), 1)
        self.assertEqual(list(self.connection.subscriptions), [10_000, 10_001])
        self.assertEqual(self.connection.results, list(range(1, 10_002)))
        self.assertEqual(self.connection.events, [])
        self.assertEqual(self.hass.loop.pending_timer_count, 1)

        self.hass.loop.advance(guard._REPLAY_DEBOUNCE_SECONDS)

        self.assertEqual(len(self.connection.events), 1)
        self.assertEqual(self.connection.events[0]["id"], 10_001)

    async def test_live_publish_cancels_redundant_cached_replay(self):
        self.handler(self.hass, self.connection, self.message(1))
        self.hass.loop.run_soon()
        tracker = guard._test_trackers[0]
        self.connection.events.clear()

        self.handler(self.hass, self.connection, self.message(2))
        tracker.emit("fresh")

        self.assertEqual(self.hass.loop.pending_timer_count, 0)
        self.assertEqual([event["id"] for event in self.connection.events], [2])
        self.assertEqual(self.connection.events[0]["event"]["result"], "fresh")
        self.hass.loop.advance(guard._REPLAY_DEBOUNCE_SECONDS)
        self.assertEqual(len(self.connection.events), 1)

    async def test_connection_close_does_not_mutate_subscription_dict(self):
        for subscription_id in range(1, 20):
            self.handler(self.hass, self.connection, self.message(subscription_id))
        self.hass.loop.run_soon()
        tracker = guard._test_trackers[0]
        self.connection.events.clear()
        self.handler(self.hass, self.connection, self.message(20))
        self.assertEqual(self.hass.loop.pending_timer_count, 1)

        for remove in self.connection.subscriptions.values():
            remove()
        self.connection.subscriptions.clear()
        self.assertEqual(tracker.remove_calls, 1)
        self.assertEqual(self.hass.data[guard.DOMAIN]["groups"], set())
        self.assertEqual(self.hass.loop.pending_timer_count, 0)
        self.hass.loop.advance(guard._REPLAY_DEBOUNCE_SECONDS)
        self.assertEqual(self.connection.events, [])

    async def test_unload_cancels_pending_replay_and_restores_core_handler(self):
        original_handler = self.hass.data[guard.DOMAIN]["original_handler"]
        self.handler(self.hass, self.connection, self.message(1))
        self.hass.loop.run_soon()
        tracker = guard._test_trackers[0]
        self.connection.events.clear()
        self.handler(self.hass, self.connection, self.message(2))

        self.assertEqual(self.hass.loop.pending_timer_count, 1)
        self.assertTrue(await guard.async_unload(self.hass))

        self.assertEqual(tracker.remove_calls, 1)
        self.assertEqual(self.hass.loop.pending_timer_count, 0)
        self.assertIs(
            self.hass.data["websocket_api"]["render_template"][0],
            original_handler,
        )
        self.hass.loop.advance(guard._REPLAY_DEBOUNCE_SECONDS)
        self.assertEqual(self.connection.events, [])

    async def test_different_templates_have_separate_bounded_trackers(self):
        self.handler(self.hass, self.connection, self.message(1, tablet_template("a")))
        self.handler(self.hass, self.connection, self.message(2, tablet_template("b")))
        self.hass.loop.run_soon()

        self.assertEqual(len(guard._test_trackers), 2)
        self.assertEqual(self.core_calls, [])

    async def test_unrelated_or_advanced_requests_keep_core_behavior(self):
        self.handler(
            self.hass,
            self.connection,
            self.message(1, "{{ states('sun.sun') }}"),
        )
        self.handler(self.hass, self.connection, self.message(2, strict=True))
        self.handler(
            self.hass,
            self.connection,
            self.message(3, entity_ids=["sensor.dracaena_soil_moisture_state"]),
        )
        self.handler(self.hass, self.connection, self.message(4, variables={"x": 1}))

        self.assertEqual(self.core_calls, [1, 2, 3, 4])
        self.assertEqual(guard._test_trackers, [])

    async def test_setup_is_idempotent(self):
        installed = self.handler
        self.assertTrue(await guard.async_setup(self.hass, {}))
        self.assertIs(self.hass.data["websocket_api"]["render_template"][0], installed)


if __name__ == "__main__":
    unittest.main()
