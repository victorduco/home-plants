"""Deterministic evaluation of plant-care issues from a current_status snapshot.

This replaces the LLM node that used to read current_status and describe what was wrong.
Deciding whether 54% is below a minimum of 50% is arithmetic, not judgement, and routing
it through a model produced notifications that inverted "too dry" and "too humid",
flagged green-zone plants, and asserted device states that contradicted the payload.

Every Issue carries a stable `key`. Deduplication compares keys, never wording, so the
model rephrasing itself between runs can no longer look like a new problem.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

# Severity drives ordering in the push message.
CRITICAL = "critical"
WARNING = "warning"
INFO = "info"
_SEVERITY_ORDER = {CRITICAL: 0, WARNING: 1, INFO: 2}

# INFO issues are recorded on the dashboard but never pushed to the phone.
PUSH_SEVERITIES = (CRITICAL, WARNING)

# Zones that mean "no trustworthy reading", so range comparisons must not run.
_UNUSABLE_ZONES = {None, "", "unknown", "unavailable", "stale"}


@dataclass(frozen=True)
class Issue:
    key: str
    kind: str
    subject: str
    severity: str
    headline: str
    detail: str = ""
    remedy: str = ""


@dataclass
class Metric:
    """One measured value plus the bounds it is judged against.

    `low`/`high` are hard bounds. `warn` is a soft lower bound used by soil moisture,
    where the configured thresholds are "green at or above X, critical below Y" with no
    upper limit at all — wet soil after watering is not a problem to report.
    """

    value: float | None
    low: float | None
    high: float | None
    unit: str
    warn: float | None = None
    stale: bool = False
    stale_age_hours: float | None = None
    stale_reason: str | None = None
    zone: str | None = None

    @property
    def usable(self) -> bool:
        return self.value is not None and not self.stale and self.zone not in _UNUSABLE_ZONES

    @property
    def configured(self) -> bool:
        return self.low is not None or self.high is not None or self.warn is not None

    def fmt(self) -> str:
        if self.value is None:
            return "no reading"
        shown = f"{self.value:g}{self.unit}"
        if self.low is not None and self.high is not None:
            return f"{shown} (target {self.low:g}–{self.high:g}{self.unit})"
        bound = self.warn if self.warn is not None else self.low
        if bound is not None:
            return f"{shown} (min {bound:g}{self.unit})"
        if self.high is not None:
            return f"{shown} (max {self.high:g}{self.unit})"
        return shown


def parse_measure(raw: Any) -> float | None:
    """Pull a number out of values like '54%', '71.06°F', 54, None."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    match = re.search(r"-?\d+(?:\.\d+)?", str(raw))
    return float(match.group()) if match else None


def _metric(
    block: dict[str, Any] | None,
    low_key: str | None,
    high_key: str | None,
    unit: str,
    warn_key: str | None = None,
) -> Metric:
    block = block or {}
    return Metric(
        value=parse_measure(block.get("value")),
        low=block.get(low_key) if low_key else None,
        high=block.get(high_key) if high_key else None,
        unit=unit,
        warn=block.get(warn_key) if warn_key else None,
        stale=bool(block.get("is_stale")),
        stale_age_hours=block.get("stale_age_hours"),
        stale_reason=block.get("stale_reason"),
        zone=block.get("zone"),
    )


def _plant_metrics(plant: dict[str, Any]) -> dict[str, Metric]:
    # Soil thresholds are not a band: `green_above` is the floor for "fine" and
    # `red_below` the floor for "critical". There is no upper bound, so a high reading
    # right after watering must not surface as a problem.
    return {
        "soil moisture": _metric(
            plant.get("soil_moisture"), "red_below", None, "%", warn_key="green_above"
        ),
        "air humidity": _metric(plant.get("air_humidity"), "needed_min", "needed_max", "%"),
        "air temperature": _metric(plant.get("air_temperature"), "needed_min_f", "needed_max_f", "°F"),
    }


def _humidifier_state(status: dict[str, Any]) -> str:
    devices = status.get("devices") or {}
    return str((devices.get("humidifier") or {}).get("state") or "unknown").lower()


def evaluate(status: dict[str, Any]) -> list[Issue]:
    """Derive every issue that needs a human from a current_status payload."""
    issues: list[Issue] = []
    plants: list[dict[str, Any]] = status.get("plants") or []
    hum_state = _humidifier_state(status)

    # --- devices -----------------------------------------------------------------
    if hum_state == "no water":
        issues.append(Issue(
            key="humidifier:no_water",
            kind="humidifier",
            subject="Humidifier",
            severity=CRITICAL,
            headline="Humidifier reservoir is empty",
            detail="Reported state: 'no water' — it cannot raise humidity until refilled.",
            remedy="Refill the humidifier reservoir.",
        ))
    elif hum_state in ("unknown", "unavailable"):
        issues.append(Issue(
            key="humidifier:unavailable",
            kind="humidifier",
            subject="Humidifier",
            severity=WARNING,
            headline="Humidifier is not reporting its state",
            detail=f"Reported state: '{hum_state}'.",
            remedy="Check that the humidifier is powered and paired.",
        ))

    thermostat = (status.get("devices") or {}).get("thermostat") or {}
    if thermostat.get("status") == "unknown":
        issues.append(Issue(
            key="thermostat:unavailable",
            kind="thermostat",
            subject="Thermostat",
            severity=WARNING,
            headline="Thermostat is not reporting",
            detail="No climate entity was found in the current status.",
            remedy="Check the thermostat integration in Home Assistant.",
        ))

    # --- plants ------------------------------------------------------------------
    for plant in plants:
        name = plant.get("name") or "Unknown plant"
        metrics = _plant_metrics(plant)

        # A plant with no thresholds at all is a configuration gap, not a care problem.
        # Reporting it as such prevents the fabricated "humidity too low" verdicts that
        # were previously emitted for plants whose needed_min was null.
        if not any(m.configured for m in metrics.values()):
            issues.append(Issue(
                key=f"plant_unconfigured:{name}",
                kind="unconfigured",
                subject=name,
                severity=WARNING,
                headline=f"{name} has no care thresholds configured",
                detail="No min/max values are set, so its readings cannot be judged.",
                remedy=f"Set moisture/humidity/temperature limits for {name} in Home Assistant.",
            ))
            continue

        for label, m in metrics.items():
            if m.stale:
                age = f" for {m.stale_age_hours:g}h" if m.stale_age_hours else ""
                if m.stale_reason == "frozen":
                    headline = f"{name}: {label} sensor has read the same value{age}"
                    detail = "Readings still arrive but never move, so the sensor is being ignored."
                    remedy = "Check that the probe still sits in the soil and its battery is not dying."
                else:
                    headline = f"{name}: {label} sensor has not reported{age}"
                    detail = "No fresh readings are arriving, so the last value is frozen and is being ignored."
                    remedy = "Check the sensor battery and its gateway."
                issues.append(Issue(
                    key=f"sensor_stale:{name}:{label}",
                    kind="sensor",
                    subject=name,
                    severity=WARNING,
                    headline=headline,
                    detail=detail,
                    remedy=remedy,
                ))
                continue

            if m.value is None or m.zone in _UNUSABLE_ZONES:
                issues.append(Issue(
                    key=f"sensor_unavailable:{name}:{label}",
                    kind="sensor",
                    subject=name,
                    severity=WARNING,
                    headline=f"{name}: {label} sensor is unavailable",
                    detail="No reading is being reported.",
                    remedy="Check the sensor battery and its gateway.",
                ))
                continue

            # Range checks run only on a trustworthy reading against a real threshold.
            if label == "soil moisture":
                soil_issue = _soil_issue(name, m)
                if soil_issue:
                    issues.append(soil_issue)
            elif m.low is not None and m.value < m.low:
                issues.append(_range_issue(name, label, m, "low", hum_state))
            elif m.high is not None and m.value > m.high:
                issues.append(_range_issue(name, label, m, "high", hum_state))

    issues.sort(key=lambda i: (_SEVERITY_ORDER.get(i.severity, 9), i.key))
    return issues


def _soil_issue(name: str, m: Metric) -> Issue | None:
    """Soil only needs a human when it is drying out. Wet soil is not reportable."""
    if m.low is not None and m.value < m.low:
        return Issue(
            key=f"soil_dry:{name}",
            kind="soil",
            subject=name,
            severity=CRITICAL,
            headline=f"{name} is critically dry",
            detail=f"Soil moisture {m.fmt()}.",
            remedy=f"Water {name} now.",
        )
    if m.warn is not None and m.value < m.warn:
        return Issue(
            key=f"soil_low:{name}",
            kind="soil",
            subject=name,
            severity=WARNING,
            headline=f"{name} is getting dry",
            detail=f"Soil moisture {m.fmt()}.",
            remedy=f"Water {name} soon.",
        )
    return None


def _range_issue(name: str, label: str, m: Metric, side: str, hum_state: str) -> Issue:
    """Build the issue for a reading that fell outside its configured band."""
    if label == "air humidity":
        if side == "low":
            # The humidifier only deserves a mention when it genuinely cannot help.
            blocked = hum_state in ("no water", "unavailable", "unknown")
            return Issue(
                key=f"humidity_low:{name}",
                kind="humidity_low",
                subject=name,
                severity=WARNING,
                headline=f"{name}: air too dry",
                detail=f"Humidity {m.fmt()}.",
                remedy="Refill the humidifier." if blocked else "Humidifier is running; check its output.",
            )
        return Issue(
            key=f"humidity_high:{name}",
            kind="humidity_high",
            subject=name,
            severity=WARNING,
            headline=f"{name}: air too humid",
            detail=f"Humidity {m.fmt()}.",
            remedy="Ventilate the room or move the humidifier away.",
        )

    direction = "cold" if side == "low" else "hot"
    return Issue(
        key=f"temp_{side}:{name}",
        kind="temperature",
        subject=name,
        severity=WARNING,
        headline=f"{name}: too {direction}",
        detail=f"Temperature {m.fmt()}.",
        remedy="Check heating/cooling near this plant.",
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_KIND_TITLES = {
    "humidifier": "💧 Humidifier",
    "thermostat": "🌡 Thermostat",
    "sensor": "📡 Sensors",
    "soil": "🌱 Soil",
    "humidity_low": "🏜 Air too dry",
    "humidity_high": "💦 Air too humid",
    "temperature": "🌡 Temperature",
    "unconfigured": "⚙️ Setup",
}


def render_message(issues: Iterable[Issue], actions_taken: list[str] | None = None) -> str:
    """Render one push body: what happened, who it affects, what the agent did, what you do.

    Issues are grouped by kind so a single root cause produces a single block instead of
    one push per affected plant.
    """
    grouped: dict[str, list[Issue]] = {}
    for issue in issues:
        grouped.setdefault(issue.kind, []).append(issue)

    blocks: list[str] = []
    for kind, group in sorted(
        grouped.items(),
        key=lambda kv: min(_SEVERITY_ORDER.get(i.severity, 9) for i in kv[1]),
    ):
        title = _KIND_TITLES.get(kind, kind)
        lines = [title]

        if len(group) == 1:
            only = group[0]
            lines.append(f"  {only.headline}")
            if only.detail:
                lines.append(f"  {only.detail}")
            if only.remedy:
                lines.append(f"  → {only.remedy}")
        else:
            lines.append(f"  Affects {len(group)}:")
            for issue in group[:5]:
                lines.append(f"  · {issue.subject}: {issue.detail or issue.headline}")
            if len(group) > 5:
                remaining = ", ".join(i.subject for i in group[5:])
                lines.append(f"  · …and {len(group) - 5} more: {remaining}")
            remedies = list(dict.fromkeys(i.remedy for i in group if i.remedy))
            for remedy in remedies[:2]:
                lines.append(f"  → {remedy}")

        blocks.append("\n".join(lines))

    if actions_taken:
        shown = actions_taken[:4]
        block = ["🤖 Already done"] + [f"  · {a}" for a in shown]
        if len(actions_taken) > len(shown):
            block.append(f"  · …and {len(actions_taken) - len(shown)} more")
        blocks.append("\n".join(block))

    return "\n\n".join(blocks)


def render_log_lines(issues: Iterable[Issue]) -> list[str]:
    """Snapshot of the current issues, written every run.

    Each line is `key | text`. The key prefix makes the snapshot double as the record of
    "what was wrong last check", which deduplication uses to require an issue to persist
    across two checks before it is pushed. The dashboard strips the prefix for display.
    """
    return [f"{i.key} | {i.headline} — {i.detail}".strip(" —") for i in issues]


def parse_log_keys(items: Iterable[str]) -> set[str]:
    """Recover the issue keys from a snapshot written by render_log_lines."""
    keys: set[str] = set()
    for item in items or []:
        key, sep, _ = str(item).partition("|")
        if sep and key.strip():
            keys.add(key.strip())
    return keys
