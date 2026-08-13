"""Regression tests for the server-side tablet render_template guard."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


def _load_guard_module():
    render_calls = []
    template_specs = {}
    state_trackers = []

    homeassistant = types.ModuleType("homeassistant")
    components = types.ModuleType("homeassistant.components")
    websocket_api = types.ModuleType("homeassistant.components.websocket_api")
    websocket_messages = types.ModuleType(
        "homeassistant.components.websocket_api.messages"
    )
    websocket_messages.event_message = lambda subscription_id, payload: {
        "id": subscription_id,
        "type": "event",
        "event": payload,
    }
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

    class FakeRenderInfo:
        def __init__(self, spec):
            self.all_states = spec.get("all_states", False)
            self.all_states_lifecycle = spec.get("all_states_lifecycle", False)
            self.domains = frozenset(spec.get("domains", ()))
            self.domains_lifecycle = frozenset(spec.get("domains_lifecycle", ()))
            self.entities = frozenset(spec.get("entities", {"sensor.default"}))
            self.has_time = spec.get("has_time", False)
            self.exception = spec.get("exception")
            self._result = spec.get("result")

        def result(self):
            if self.exception is not None:
                raise self.exception
            return self._result

    class Template:
        def __init__(self, content, hass):
            self.content = content
            self.hass = hass

        def async_render_to_info(self, variables=None, strict=False):
            render_calls.append(self.content)
            spec_value = template_specs.get(self.content, {})
            spec = spec_value() if callable(spec_value) else dict(spec_value)
            if spec.get("raise") is not None:
                raise spec["raise"]
            spec.setdefault("result", f"render:{self.content}")
            return FakeRenderInfo(spec)

    template_module.Template = Template

    event_module = types.ModuleType("homeassistant.helpers.event")

    class FakeStateTracker:
        def __init__(self, entity_ids, action):
            self.entities = frozenset(entity_ids)
            self.action = action
            self.active = True
            self.remove_calls = 0

        def emit(self, entity_id):
            if self.active and entity_id.lower() in self.entities:
                self.action(types.SimpleNamespace(data={"entity_id": entity_id}))

        def remove(self):
            if self.active:
                self.active = False
                self.remove_calls += 1

    def async_track_state_change_event(hass, entity_ids, action):
        tracker = FakeStateTracker(entity_ids, action)
        state_trackers.append(tracker)
        return tracker.remove

    event_module.async_track_state_change_event = async_track_state_change_event
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
    module._test_render_calls = render_calls
    module._test_template_specs = template_specs
    module._test_state_trackers = state_trackers
    module._test_template_error = TemplateError
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
    """Small deterministic scheduler for debounce and max-wait callbacks."""

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
        guard._test_render_calls.clear()
        guard._test_template_specs.clear()
        guard._test_state_trackers.clear()
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

    def active_state_trackers(self):
        return [tracker for tracker in guard._test_state_trackers if tracker.active]

    async def test_rapid_duplicate_batch_is_bounded_and_latest_wins(self):
        for subscription_id in range(1, 175):
            self.handler(self.hass, self.connection, self.message(subscription_id))

        self.assertEqual(self.core_calls, [])
        self.assertEqual(len(guard._test_render_calls), 1)
        self.assertEqual(len(self.active_state_trackers()), 1)
        self.assertEqual(list(self.connection.subscriptions), [173, 174])
        self.assertEqual(self.connection.results, list(range(1, 175)))
        self.assertEqual([event["id"] for event in self.connection.events], [1])

        self.hass.loop.advance(guard._REPLAY_DEBOUNCE_SECONDS)
        self.assertEqual([event["id"] for event in self.connection.events], [1, 174])

    async def test_ten_thousand_aliases_keep_two_ids_and_replay_once(self):
        self.handler(self.hass, self.connection, self.message(1))
        self.connection.events.clear()
        for subscription_id in range(2, 10_002):
            self.handler(self.hass, self.connection, self.message(subscription_id))

        self.assertEqual(len(guard._test_render_calls), 1)
        self.assertEqual(list(self.connection.subscriptions), [10_000, 10_001])
        self.assertEqual(self.connection.events, [])
        self.assertEqual(self.hass.loop.pending_timer_count, 1)
        self.hass.loop.advance(guard._REPLAY_DEBOUNCE_SECONDS)
        self.assertEqual([event["id"] for event in self.connection.events], [10_001])

    async def test_distinct_historical_templates_share_one_latest_renderer(self):
        first = tablet_template("version-0")
        self.handler(self.hass, self.connection, self.message(1, first))
        self.connection.events.clear()

        latest = None
        for subscription_id in range(2, 1002):
            latest = tablet_template(f"version-{subscription_id}")
            self.handler(
                self.hass,
                self.connection,
                self.message(subscription_id, latest),
            )

        self.assertEqual(len(guard._test_render_calls), 1)
        self.assertEqual(len(self.active_state_trackers()), 1)
        self.assertEqual(len(self.connection.subscriptions), 2)
        self.assertEqual(self.connection.events, [])
        self.hass.loop.advance(guard._RENDER_DEBOUNCE_SECONDS)

        self.assertEqual(len(guard._test_render_calls), 2)
        self.assertEqual(guard._test_render_calls[-1], latest)
        self.assertEqual(len(self.active_state_trackers()), 1)
        self.assertEqual([event["id"] for event in self.connection.events], [1001])
        self.assertEqual(
            self.connection.events[0]["event"]["result"], f"render:{latest}"
        )

    async def test_328_and_ten_thousand_state_events_each_render_once(self):
        target = tablet_template()
        guard._test_template_specs[target] = {
            "entities": {"sensor.default", *{f"sensor.e{i}" for i in range(328)}}
        }
        self.handler(self.hass, self.connection, self.message(1, target))
        tracker = self.active_state_trackers()[0]
        self.connection.events.clear()

        for index in range(328):
            tracker.emit(f"sensor.e{index}")
        self.assertEqual(len(guard._test_render_calls), 1)
        self.hass.loop.advance(guard._RENDER_DEBOUNCE_SECONDS)
        self.assertEqual(len(guard._test_render_calls), 2)
        self.assertEqual(len(self.connection.events), 1)

        tracker = self.active_state_trackers()[0]
        self.connection.events.clear()
        for index in range(10_000):
            tracker.emit(f"sensor.e{index % 328}")
        self.assertEqual(len(guard._test_render_calls), 2)
        self.hass.loop.advance(guard._RENDER_DEBOUNCE_SECONDS)
        self.assertEqual(len(guard._test_render_calls), 3)
        self.assertEqual(len(self.connection.events), 1)

    async def test_continuous_events_render_at_max_wait(self):
        self.handler(self.hass, self.connection, self.message(1))
        tracker = self.active_state_trackers()[0]
        self.connection.events.clear()

        for _ in range(12):
            tracker.emit("sensor.default")
            self.hass.loop.advance(0.4)
        self.assertEqual(len(guard._test_render_calls), 1)

        tracker.emit("sensor.default")
        self.hass.loop.advance(0.2)
        self.assertEqual(self.hass.loop.now, guard._RENDER_MAX_WAIT_SECONDS)
        self.assertEqual(len(guard._test_render_calls), 2)
        self.assertEqual(len(self.connection.events), 1)

    async def test_dependency_listener_is_replaced_after_render(self):
        first = tablet_template("first")
        second = tablet_template("second")
        guard._test_template_specs[first] = {
            "entities": {"sensor.old"},
            "result": "first",
        }
        guard._test_template_specs[second] = {
            "entities": {"sensor.new"},
            "result": "second",
        }
        self.handler(self.hass, self.connection, self.message(1, first))
        old_tracker = self.active_state_trackers()[0]
        self.handler(self.hass, self.connection, self.message(2, second))
        self.hass.loop.advance(guard._RENDER_DEBOUNCE_SECONDS)

        self.assertFalse(old_tracker.active)
        self.assertEqual(old_tracker.remove_calls, 1)
        new_tracker = self.active_state_trackers()[0]
        self.assertEqual(new_tracker.entities, frozenset({"sensor.new"}))
        self.connection.events.clear()
        old_tracker.emit("sensor.old")
        self.hass.loop.advance(guard._RENDER_DEBOUNCE_SECONDS)
        self.assertEqual(self.connection.events, [])
        new_tracker.emit("sensor.new")
        self.hass.loop.advance(guard._RENDER_DEBOUNCE_SECONDS)
        self.assertEqual(len(self.connection.events), 1)
        self.assertEqual(
            self.connection.events[0]["event"]["listeners"]["entities"],
            {"sensor.new"},
        )

    async def test_template_error_is_suppressed_and_can_recover(self):
        target = tablet_template()
        outcomes = [
            {"entities": {"sensor.default"}, "result": "healthy"},
            {
                "entities": {"sensor.default"},
                "exception": guard._test_template_error("boom"),
            },
            {"entities": {"sensor.default"}, "result": "recovered"},
        ]
        guard._test_template_specs[target] = lambda: outcomes.pop(0)
        self.handler(self.hass, self.connection, self.message(1, target))
        tracker = self.active_state_trackers()[0]
        self.connection.events.clear()

        tracker.emit("sensor.default")
        self.hass.loop.advance(guard._RENDER_DEBOUNCE_SECONDS)
        self.assertEqual(self.connection.events, [])
        self.assertEqual(len(self.active_state_trackers()), 1)

        tracker.emit("sensor.default")
        self.hass.loop.advance(guard._RENDER_DEBOUNCE_SECONDS)
        self.assertEqual(len(self.connection.events), 1)
        self.assertEqual(self.connection.events[0]["event"]["result"], "recovered")

    async def test_initial_error_or_non_exact_render_falls_back_to_core(self):
        errored = tablet_template("error")
        broad = tablet_template("broad")
        guard._test_template_specs[errored] = {
            "exception": guard._test_template_error("bad")
        }
        guard._test_template_specs[broad] = {"all_states": True}

        self.handler(self.hass, self.connection, self.message(1, errored))
        self.handler(self.hass, self.connection, self.message(2, broad))

        self.assertEqual(self.core_calls, [1, 2])
        self.assertEqual(self.connection.subscriptions, {})
        self.assertEqual(self.active_state_trackers(), [])

    async def test_stale_and_active_unsubscribe_lifecycle(self):
        self.handler(self.hass, self.connection, self.message(1))
        self.handler(self.hass, self.connection, self.message(2))
        tracker = self.active_state_trackers()[0]

        self.connection.subscriptions.pop(1)()
        self.assertTrue(tracker.active)
        self.connection.subscriptions.pop(2)()
        self.assertFalse(tracker.active)
        self.assertEqual(tracker.remove_calls, 1)
        self.assertEqual(self.connection.subscriptions, {})
        self.assertEqual(self.hass.data[guard.DOMAIN]["groups"], set())

    async def test_connection_close_and_unload_cancel_all_work(self):
        first = tablet_template("first")
        second = tablet_template("second")
        self.handler(self.hass, self.connection, self.message(1, first))
        self.handler(self.hass, self.connection, self.message(2, second))
        self.assertEqual(self.hass.loop.pending_timer_count, 2)
        tracker = self.active_state_trackers()[0]

        for remove in self.connection.subscriptions.values():
            remove()
        self.connection.subscriptions.clear()
        self.assertFalse(tracker.active)
        self.assertEqual(self.hass.loop.pending_timer_count, 0)
        self.hass.loop.advance(guard._RENDER_MAX_WAIT_SECONDS)
        self.assertEqual(len(guard._test_render_calls), 1)

        # A separate group verifies component unload and handler restoration.
        connection = FakeConnection()
        original_handler = self.hass.data[guard.DOMAIN]["original_handler"]
        self.handler(self.hass, connection, self.message(3, first))
        self.handler(self.hass, connection, self.message(4, second))
        self.assertTrue(await guard.async_unload(self.hass))
        self.assertEqual(self.hass.loop.pending_timer_count, 0)
        self.assertIs(
            self.hass.data["websocket_api"]["render_template"][0],
            original_handler,
        )

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
            self.message(3, entity_ids=["sensor.default"]),
        )
        self.handler(self.hass, self.connection, self.message(4, variables={"x": 1}))

        self.assertEqual(self.core_calls, [1, 2, 3, 4])
        self.assertEqual(guard._test_render_calls, [])

    async def test_setup_is_idempotent(self):
        installed = self.handler
        self.assertTrue(await guard.async_setup(self.hass, {}))
        self.assertIs(self.hass.data["websocket_api"]["render_template"][0], installed)


if __name__ == "__main__":
    unittest.main()
