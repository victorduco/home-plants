"""Bound the broken legacy tablet card to one debounced exact-state renderer.

The unmaintained html-template-card v1.0.2 opens a new ``render_template``
subscription on every Home Assistant update and loses the unsubscribe callback.
Long-lived Android WebViews can consequently restore thousands of subscriptions,
including subscriptions for several historical versions of the same dashboard.

This guard is intentionally narrow: it only recognizes the known full-screen
plant-tablet template. All matching versions on one WebSocket connection share one
latest-wins group. The group renders once initially, listens only to the exact
entity IDs discovered by that render, and trailing-debounces subsequent renders.
It does not use Home Assistant's synchronous-per-event template tracker. Requests
whose initial render needs all-state, domain, lifecycle, or time listeners fall
back to the unmodified core handler.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from homeassistant.components.websocket_api import messages
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import TemplateError
from homeassistant.helpers import template
from homeassistant.helpers.event import async_track_state_change_event

DOMAIN = "render_template_guard"
_WEBSOCKET_DOMAIN = "websocket_api"
_COMMAND = "render_template"
_GROUP_ATTRIBUTE = "_render_template_guard_group"
_TARGET_GROUP_KEY = "plant-tablet-full-screen"
_REPLAY_DEBOUNCE_SECONDS = 0.2
_RENDER_DEBOUNCE_SECONDS = 0.5
_RENDER_MAX_WAIT_SECONDS = 5.0
_TARGET_MARKERS = (
    ".tablet-wrap",
    "{% set plants = [",
    "_soil_moisture_zone",
    "_air_humidity_zone",
    "_air_temperature_zone",
)

_LOGGER = logging.getLogger(__name__)


class _SubscriptionGroup:
    """One exact-state renderer with one latest logical WS subscriber."""

    __slots__ = (
        "active_id",
        "connection",
        "current_template_str",
        "dependency_entities",
        "dependency_remove",
        "desired_template_str",
        "hass",
        "key",
        "last_payload",
        "loop",
        "max_wait_handle",
        "on_remove",
        "removed",
        "render_handle",
        "replacement_count",
        "replay_handle",
        "retired_id",
    )

    def __init__(
        self,
        hass: HomeAssistant,
        connection: Any,
        key: str,
        on_remove: Callable[[_SubscriptionGroup], None],
    ) -> None:
        self.hass = hass
        self.connection = connection
        self.key = key
        self.loop = hass.loop
        self.on_remove = on_remove
        self.active_id: int | None = None
        self.current_template_str: str | None = None
        self.dependency_entities: frozenset[str] = frozenset()
        self.dependency_remove: Callable[[], Any] | None = None
        self.desired_template_str: str | None = None
        self.last_payload: dict[str, Any] | None = None
        self.max_wait_handle: Any | None = None
        self.render_handle: Any | None = None
        self.replacement_count = 0
        self.replay_handle: Any | None = None
        self.retired_id: int | None = None
        self.removed = False

    @callback
    def prepare_initial(self, template_str: str) -> bool:
        """Render once and install an exact listener before claiming a request."""
        rendered = self._render_exact(template_str)
        if rendered is None:
            return False
        result, entities = rendered
        self.current_template_str = template_str
        self.desired_template_str = template_str
        self._replace_dependency_listener(entities)
        self.last_payload = self._payload(result, entities)
        return True

    @callback
    def add(self, subscription_id: int, template_str: str) -> None:
        """Hand the group to the newest ID and schedule only necessary work."""
        previous_desired = self.desired_template_str
        self.desired_template_str = template_str

        if self.retired_id is not None:
            # At most one delayed-unsubscribe tombstone is retained.
            self.connection.subscriptions.pop(self.retired_id, None)
            self.retired_id = None
        if self.active_id is not None:
            old_active_id = self.active_id
            self.connection.subscriptions[old_active_id] = self._retired_remover(
                old_active_id
            )
            self.retired_id = old_active_id
            self.replacement_count += 1
        self.active_id = subscription_id
        self.connection.subscriptions[subscription_id] = self._active_remover(
            subscription_id
        )
        self.connection.send_result(subscription_id)

        if template_str == self.current_template_str:
            # If a pending historical version was superseded by the currently
            # rendered version, that pending replacement is no longer wanted.
            if previous_desired != self.current_template_str:
                self._cancel_render_timers()
            if self.last_payload is not None:
                self._schedule_cached_replay()
        else:
            self._cancel_cached_replay()
            self._schedule_render()

        if self.replacement_count == 1 or (
            self.replacement_count and self.replacement_count % 100 == 0
        ):
            _LOGGER.warning(
                "Coalesced %s duplicate tablet render_template subscription(s)",
                self.replacement_count,
            )

    @callback
    def send_initial(self) -> None:
        """Send the prepared first result after its protocol acknowledgement."""
        self._cancel_cached_replay()
        if self.removed or self.active_id is None or self.last_payload is None:
            return
        self.connection.send_message(
            messages.event_message(self.active_id, self.last_payload)
        )

    @callback
    def remove_backend(self) -> None:
        """Cancel exact listeners and all deferred work exactly once."""
        if self.removed:
            return
        self.removed = True
        self.active_id = None
        self._cancel_cached_replay()
        self._cancel_render_timers()
        try:
            self._clear_dependency_listener()
        finally:
            self.on_remove(self)

    @callback
    def _state_changed(self, event: Any) -> None:
        """Coalesce exact dependency changes without rendering in this callback."""
        self._schedule_render()

    @callback
    def _schedule_render(self) -> None:
        if self.removed or self.desired_template_str is None:
            return
        if self.render_handle is not None:
            self.render_handle.cancel()
        elif self.max_wait_handle is None:
            # The max-wait deadline belongs to the first event in this burst and
            # is deliberately not extended by later state changes.
            self.max_wait_handle = self.loop.call_later(
                _RENDER_MAX_WAIT_SECONDS,
                self._render_at_max_wait,
            )
        self.render_handle = self.loop.call_later(
            _RENDER_DEBOUNCE_SECONDS,
            self._render_after_quiet_period,
        )

    @callback
    def _render_after_quiet_period(self) -> None:
        self.render_handle = None
        if self.max_wait_handle is not None:
            self.max_wait_handle.cancel()
            self.max_wait_handle = None
        self._render_latest()

    @callback
    def _render_at_max_wait(self) -> None:
        self.max_wait_handle = None
        if self.render_handle is not None:
            self.render_handle.cancel()
            self.render_handle = None
        self._render_latest()

    @callback
    def _render_latest(self) -> None:
        if self.removed or self.desired_template_str is None:
            return
        template_str = self.desired_template_str
        rendered = self._render_exact(template_str)
        if rendered is None:
            # Keep the last known exact dependency listener. report_errors=False
            # suppresses template-error events in core as well. A later event or a
            # newer template subscription may recover the render.
            return

        result, entities = rendered
        self.current_template_str = template_str
        self._replace_dependency_listener(entities)
        self.last_payload = self._payload(result, entities)
        self._cancel_cached_replay()
        if self.active_id is not None:
            self.connection.send_message(
                messages.event_message(self.active_id, self.last_payload)
            )

    @callback
    def _render_exact(self, template_str: str) -> tuple[Any, frozenset[str]] | None:
        """Render and reject anything requiring broader-than-entity tracking."""
        template_obj = template.Template(template_str, self.hass)
        try:
            info = template_obj.async_render_to_info(None, strict=False)
        except TemplateError:
            _LOGGER.warning("Tablet template render failed; retaining safe listener")
            return None

        if getattr(info, "exception", None) is not None:
            _LOGGER.warning("Tablet template render failed; retaining safe listener")
            return None

        entities_value = getattr(info, "entities", None)
        if (
            entities_value is None
            or getattr(info, "all_states", True)
            or getattr(info, "all_states_lifecycle", True)
            or bool(getattr(info, "domains", True))
            or bool(getattr(info, "domains_lifecycle", True))
            or getattr(info, "has_time", True)
        ):
            _LOGGER.warning(
                "Tablet template requires non-exact listeners; guard declined it"
            )
            return None

        try:
            if any(not isinstance(entity_id, str) for entity_id in entities_value):
                return None
            entities = frozenset(entity_id.lower() for entity_id in entities_value)
            if any("." not in entity_id for entity_id in entities):
                return None
            result = info.result()
        except (AttributeError, TemplateError):
            _LOGGER.warning("Tablet template render failed; retaining safe listener")
            return None
        return result, entities

    @callback
    def _replace_dependency_listener(self, entities: frozenset[str]) -> None:
        if self.dependency_remove is not None and entities == self.dependency_entities:
            return
        self._clear_dependency_listener()
        self.dependency_entities = entities
        self.dependency_remove = async_track_state_change_event(
            self.hass,
            entities,
            self._state_changed,
        )

    @callback
    def _clear_dependency_listener(self) -> None:
        if self.dependency_remove is None:
            return
        dependency_remove = self.dependency_remove
        self.dependency_remove = None
        try:
            dependency_remove()
        except Exception:
            _LOGGER.exception("Failed to remove tablet template state listener")

    @staticmethod
    def _payload(result: Any, entities: frozenset[str]) -> dict[str, Any]:
        return {
            "result": result,
            "listeners": {
                "all": False,
                "entities": set(entities),
                "domains": set(),
                "time": False,
            },
        }

    @callback
    def _cancel_render_timers(self) -> None:
        if self.render_handle is not None:
            self.render_handle.cancel()
            self.render_handle = None
        if self.max_wait_handle is not None:
            self.max_wait_handle.cancel()
            self.max_wait_handle = None

    @callback
    def _cancel_cached_replay(self) -> None:
        if self.replay_handle is None:
            return
        self.replay_handle.cancel()
        self.replay_handle = None

    @callback
    def _schedule_cached_replay(self) -> None:
        self._cancel_cached_replay()
        if self.removed or self.active_id is None or self.last_payload is None:
            return
        self.replay_handle = self.loop.call_later(
            _REPLAY_DEBOUNCE_SECONDS,
            self._replay_cached,
        )

    @callback
    def _replay_cached(self) -> None:
        self.replay_handle = None
        if self.removed or self.active_id is None or self.last_payload is None:
            return
        # A distinct desired template must never receive stale HTML from the
        # previously rendered historical version.
        if self.desired_template_str != self.current_template_str:
            return
        self.connection.send_message(
            messages.event_message(self.active_id, self.last_payload)
        )

    def _retired_remover(self, subscription_id: int) -> Callable[[], None]:
        @callback
        def remove() -> None:
            if self.retired_id == subscription_id:
                self.retired_id = None

        setattr(remove, _GROUP_ATTRIBUTE, self)
        return remove

    def _active_remover(self, subscription_id: int) -> Callable[[], None]:
        @callback
        def remove() -> None:
            # Explicit unsubscribe pops this callable first; connection shutdown
            # invokes dictionary values in place. Do not mutate on shutdown.
            explicit_unsubscribe = subscription_id not in self.connection.subscriptions
            if self.active_id != subscription_id or self.removed:
                return

            self.remove_backend()
            if explicit_unsubscribe and self.retired_id is not None:
                self.connection.subscriptions.pop(self.retired_id, None)
                self.retired_id = None

        setattr(remove, _GROUP_ATTRIBUTE, self)
        return remove


def _guard_key(msg: dict[str, Any]) -> str | None:
    """Return one per-connection key for simple legacy tablet requests only."""
    if msg.get("type") != _COMMAND:
        return None
    if any(name in msg for name in ("timeout", "variables", "entity_ids")):
        return None
    if msg.get("strict") or msg.get("report_errors"):
        return None
    template_str = msg.get("template")
    if not isinstance(template_str, str):
        return None
    if not all(marker in template_str for marker in _TARGET_MARKERS):
        return None
    return _TARGET_GROUP_KEY


def _find_group(connection: Any, key: str) -> _SubscriptionGroup | None:
    for remove in tuple(connection.subscriptions.values()):
        group = getattr(remove, _GROUP_ATTRIBUTE, None)
        if group is not None and group.key == key and not group.removed:
            return group
    return None


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Wrap the registered websocket handler after websocket_api setup."""
    handlers = hass.data[_WEBSOCKET_DOMAIN]
    original_handler, schema = handlers[_COMMAND]
    if getattr(original_handler, "_render_template_guard_installed", False):
        return True

    groups: set[_SubscriptionGroup] = set()

    @callback
    def guarded_handler(
        current_hass: HomeAssistant, connection: Any, msg: dict[str, Any]
    ) -> None:
        key = _guard_key(msg)
        if key is None:
            original_handler(current_hass, connection, msg)
            return

        template_str = msg["template"]
        if (group := _find_group(connection, key)) is not None:
            group.add(msg["id"], template_str)
            return

        group = _SubscriptionGroup(
            current_hass,
            connection,
            key,
            groups.discard,
        )
        if not group.prepare_initial(template_str):
            # No protocol acknowledgement has been sent yet, so core can safely
            # preserve full behavior for an unexpected non-exact target.
            original_handler(current_hass, connection, msg)
            return

        groups.add(group)
        group.add(msg["id"], template_str)
        group.send_initial()

    guarded_handler._render_template_guard_installed = True  # type: ignore[attr-defined]
    handlers[_COMMAND] = (guarded_handler, schema)
    hass.data[DOMAIN] = {
        "groups": groups,
        "guarded_handler": guarded_handler,
        "original_handler": original_handler,
        "schema": schema,
    }
    _LOGGER.info("Installed debounced exact-state tablet template guard")
    return True


async def async_unload(hass: HomeAssistant) -> bool:
    """Restore the core handler and cancel listeners/timers on unload."""
    runtime = hass.data.pop(DOMAIN, None)
    if runtime is None:
        return True

    handlers = hass.data[_WEBSOCKET_DOMAIN]
    current_handler, _ = handlers[_COMMAND]
    if current_handler is runtime["guarded_handler"]:
        handlers[_COMMAND] = (runtime["original_handler"], runtime["schema"])

    for group in tuple(runtime["groups"]):
        group.remove_backend()
    return True
