"""Bound duplicate legacy tablet templates to one functional backend tracker.

The unmaintained html-template-card v1.0.2 starts a new ``render_template``
subscription for every relevant state update and never unsubscribes it. Long-lived
Android WebViews can restore thousands of those subscriptions after reconnecting.

This guard is deliberately narrow. Only the known full-screen plant-tablet template
is coalesced. Each new subscription supersedes the previous subscription for the
same connection/template and is acknowledged immediately. Cached-render replay is
trailing-debounced so a restored burst gets one render on only its final ID instead
of one large HTML event per alias. A connection/template pair therefore owns exactly
one Home Assistant tracker, one active protocol subscription, and one render fan-out.
Every other render_template request keeps core behavior unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any

from homeassistant.components.websocket_api import const, messages
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import TemplateError
from homeassistant.helpers import template
from homeassistant.helpers.event import (
    TrackTemplate,
    TrackTemplateResult,
    async_track_template_result,
)

DOMAIN = "render_template_guard"
_WEBSOCKET_DOMAIN = "websocket_api"
_COMMAND = "render_template"
_GROUP_ATTRIBUTE = "_render_template_guard_group"
_REPLAY_DEBOUNCE_SECONDS = 0.2
_TARGET_MARKERS = (
    ".tablet-wrap",
    "{% set plants = [",
    "_soil_moisture_zone",
    "_air_humidity_zone",
    "_air_temperature_zone",
)

_LOGGER = logging.getLogger(__name__)


class _SubscriptionGroup:
    """One backend tracker with a latest-wins logical websocket subscriber."""

    __slots__ = (
        "backend_remove",
        "connection",
        "active_id",
        "key",
        "last_payload",
        "loop",
        "on_remove",
        "replacement_count",
        "replay_handle",
        "retired_id",
        "removed",
    )

    def __init__(
        self,
        connection: Any,
        key: str,
        loop: Any,
        on_remove: Callable[["_SubscriptionGroup"], None],
    ) -> None:
        self.connection = connection
        self.key = key
        self.loop = loop
        self.on_remove = on_remove
        self.active_id: int | None = None
        self.backend_remove: Callable[[], Any] | None = None
        self.last_payload: dict[str, Any] | None = None
        self.replacement_count = 0
        self.replay_handle: Any | None = None
        self.retired_id: int | None = None
        self.removed = False

    @callback
    def add(self, subscription_id: int) -> None:
        """Hand the tracker to the newest subscriber and debounce cached replay."""
        if self.retired_id is not None:
            # Retain at most the immediately previous ID as a tombstone. This lets
            # a delayed, standards-compliant unsubscribe receive a normal success,
            # while the broken legacy client can still replace IDs indefinitely
            # without growing connection.subscriptions.
            self.connection.subscriptions.pop(self.retired_id, None)
            self.retired_id = None
        if self.active_id is not None:
            # The faulty card discards its unsubscribe handle, so keeping the old
            # protocol IDs would merely move the O(N) storm from Jinja into WebSocket
            # fan-out and client-side innerHTML work. The fixed card unsubscribes
            # before replacement and therefore never enters this handoff branch.
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
        if self.last_payload is not None:
            self._schedule_cached_replay()

        if self.replacement_count == 1 or (
            self.replacement_count and self.replacement_count % 100 == 0
        ):
            _LOGGER.warning(
                "Coalesced %s duplicate tablet render_template subscription(s)",
                self.replacement_count,
            )

    @callback
    def publish(self, payload: dict[str, Any]) -> None:
        """Cache one backend render and deliver it only to the latest subscriber."""
        if self.removed:
            return
        # A live tracker result is newer than any pending cached replay and already
        # initializes the current subscriber. Suppress the now-redundant timer.
        self._cancel_cached_replay()
        self.last_payload = payload
        if self.active_id is not None:
            self.connection.send_message(
                messages.event_message(self.active_id, payload)
            )

    @callback
    def remove_backend(self) -> None:
        """Stop the tracker and all deferred work without touching WS dictionaries."""
        if self.removed:
            return
        self.removed = True
        self.active_id = None
        self._cancel_cached_replay()
        if self.backend_remove is not None:
            backend_remove = self.backend_remove
            self.backend_remove = None
            try:
                backend_remove()
            finally:
                self.on_remove(self)
            return
        self.on_remove(self)

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
            # invokes the dictionary values in place. Never mutate the dictionary
            # here, so both paths remain safe.
            explicit_unsubscribe = (
                subscription_id not in self.connection.subscriptions
            )
            if self.active_id != subscription_id or self.removed:
                return

            self.remove_backend()
            if explicit_unsubscribe and self.retired_id is not None:
                self.connection.subscriptions.pop(self.retired_id, None)
                self.retired_id = None

        setattr(remove, _GROUP_ATTRIBUTE, self)
        return remove


def _guard_key(msg: dict[str, Any]) -> str | None:
    """Return a key only for the exact, simple legacy plant-tablet request."""
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
    return template_str


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

        if (group := _find_group(connection, key)) is not None:
            group.add(msg["id"])
            return

        group = _SubscriptionGroup(
            connection,
            key,
            current_hass.loop,
            groups.discard,
        )
        template_obj = template.Template(key, current_hass)

        @callback
        def template_listener(
            event: Any,
            updates: list[TrackTemplateResult],
        ) -> None:
            result = updates.pop().result
            # The guarded request explicitly has report_errors=False, matching
            # core's behavior of suppressing render-error events in that mode.
            if isinstance(result, TemplateError):
                return
            group.publish({"result": result, "listeners": info.listeners})

        try:
            info = async_track_template_result(
                current_hass,
                [TrackTemplate(template_obj, None)],
                template_listener,
                strict=False,
            )
        except TemplateError as err:
            connection.send_error(
                msg["id"], const.ERR_TEMPLATE_ERROR, str(err)
            )
            return

        group.backend_remove = info.async_remove
        groups.add(group)
        group.add(msg["id"])
        current_hass.loop.call_soon_threadsafe(info.async_refresh)

    guarded_handler._render_template_guard_installed = True  # type: ignore[attr-defined]
    handlers[_COMMAND] = (guarded_handler, schema)
    hass.data[DOMAIN] = {
        "groups": groups,
        "guarded_handler": guarded_handler,
        "original_handler": original_handler,
        "schema": schema,
    }
    _LOGGER.info("Installed functional tablet render_template subscription guard")
    return True


async def async_unload(hass: HomeAssistant) -> bool:
    """Restore the core handler and cancel trackers/timers on component unload."""
    runtime = hass.data.pop(DOMAIN, None)
    if runtime is None:
        return True

    handlers = hass.data[_WEBSOCKET_DOMAIN]
    current_handler, _ = handlers[_COMMAND]
    if current_handler is runtime["guarded_handler"]:
        handlers[_COMMAND] = (runtime["original_handler"], runtime["schema"])

    # remove_backend discards from the live set, hence the immutable snapshot.
    for group in tuple(runtime["groups"]):
        group.remove_backend()
    return True
