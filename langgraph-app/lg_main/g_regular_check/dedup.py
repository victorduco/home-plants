"""Notification deduplication against the ledger of what was already pushed.

The previous design compared this run's issue wording against the previous run's wording
with an LLM, and the store it read from was overwritten every run. That gave a memory of
exactly one run: whenever a problem went undetected for a single check — a humidifier
switched off overnight, say — the ledger was wiped and the next detection looked new.

Here the ledger is append-only and timestamped, matching is on stable keys, and a key
stays suppressed for RENOTIFY_AFTER_HOURS from the moment it was last pushed, whether or
not it was visible in between.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from .issues import Issue

# How long a given issue key stays quiet after being pushed. Chosen so a persistent
# problem (an empty reservoir) reminds once a day rather than every run.
RENOTIFY_AFTER_HOURS = 24

# Some classes of issue deserve a longer silence. A plant with no thresholds configured
# is a one-off setup task, not something to re-raise daily, and a chronically humid room
# cannot be fixed on the timescale of a check.
RENOTIFY_BY_KIND = {
    "unconfigured": 24 * 7,
    "humidity_high": 72,
    "sensor": 48,
}

# Ledger hygiene: entries older than this can never suppress anything, and the sensor
# attribute should not grow without bound.
LEDGER_RETENTION_HOURS = 24 * 7
LEDGER_MAX_LINES = 200


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def last_notified_at(entries: Iterable[dict[str, Any]]) -> dict[str, datetime]:
    """Most recent push time per issue key."""
    latest: dict[str, datetime] = {}
    for entry in entries or []:
        key = (entry or {}).get("key")
        ts = _parse_ts((entry or {}).get("notified_at"))
        if not key or ts is None:
            continue
        if key not in latest or ts > latest[key]:
            latest[key] = ts
    return latest


def select_new(
    issues: Iterable[Issue],
    notified_entries: Iterable[dict[str, Any]],
    now: datetime | None = None,
    previous_keys: Iterable[str] | None = None,
) -> list[Issue]:
    """Return the issues that should be pushed now.

    A non-critical issue must have been seen in the previous check too. A single poll
    that comes back empty briefly marks every sensor unavailable, and without this a
    momentary blip becomes a push. `previous_keys` of None disables the check, so the
    very first run after a restart still reports.
    """
    now = now or datetime.now(timezone.utc)
    latest = last_notified_at(notified_entries)
    never = datetime.min.replace(tzinfo=timezone.utc)
    seen_before = set(previous_keys) if previous_keys is not None else None

    selected: list[Issue] = []
    for issue in issues:
        if (
            seen_before is not None
            and issue.severity != "critical"
            and issue.key not in seen_before
        ):
            continue
        window = RENOTIFY_BY_KIND.get(issue.kind, RENOTIFY_AFTER_HOURS)
        if (latest.get(issue.key) or never) < now - timedelta(hours=window):
            selected.append(issue)
    return selected


def build_ledger(
    existing_entries: Iterable[dict[str, Any]],
    pushed: Iterable[Issue],
    now: datetime | None = None,
) -> list[str]:
    """Append the pushed issues to the ledger and drop anything past retention.

    Takes the parsed entries returned by get_recent_issues and re-serialises them, so
    legacy undated rows from the old overwrite-based store fall away on first write.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=LEDGER_RETENTION_HOURS)

    lines: list[str] = []
    for entry in existing_entries or []:
        ts = _parse_ts((entry or {}).get("notified_at"))
        key = (entry or {}).get("key")
        if ts is None or not key or ts < cutoff:
            continue
        stamp = ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        lines.append(f"[{stamp}] {key} | {(entry or {}).get('text', '')}".rstrip())

    stamp = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines.extend(f"[{stamp}] {i.key} | {i.headline}" for i in pushed)
    return lines[-LEDGER_MAX_LINES:]
