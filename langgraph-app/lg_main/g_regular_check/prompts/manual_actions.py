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
