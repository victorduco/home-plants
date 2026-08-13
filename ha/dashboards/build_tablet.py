#!/usr/bin/env python3
"""Build ha/dashboards/tablet.yaml from tablet.base.yaml.

The tablet grid is one Jinja template card, and Home Assistant templates cannot read
history, so the soil sparklines cannot live inside it. They are apexcharts cards laid
over the bottom of each row-1 cell by absolute position. Out-of-flow positioning is
what makes the per-zone conditionals safe: a hidden card cannot shift its neighbours
the way a collapsing grid column would.

Sizes are pixels, not percentages. ApexCharts measures itself once at init, before
card_mod has sized the card, so a percentage height resolves against nothing and it
falls back to a 300x156 default — four times the card, with everything below the first
third clipped away. Card and chart therefore carry the same explicit pixel size,
derived from the tablet's 1280x800 CSS viewport.

Thresholds are annotations rather than series: an annotation is a line at a fixed
height that renders regardless of what history the number entity has. The axis is
pinned to contain both the readings and those lines, because a scale fitted to the
reading alone puts a bound tens of percent below it out of view.

Re-run after retuning a threshold or when a plant's weekly range moves:
    python3 ha/dashboards/build_tablet.py
"""

from pathlib import Path

import yaml

HERE = Path(__file__).parent
BASE = HERE / "tablet.base.yaml"
OUT = HERE / "tablet.yaml"

VIEWPORT_W, VIEWPORT_H = 1280, 800  # Galaxy Tab S6, landscape
COLS, ROWS = 9, 3
CELL_W = VIEWPORT_W / COLS
ROW_H = VIEWPORT_H / ROWS

CHART_W = round(CELL_W * 0.60)  # 60% of the cell across
CHART_H = round(ROW_H * 0.20)   # 20% of the cell down
CHART_PAD_LEFT = 6              # leaves the cell's right edge for the current reading
CHART_PAD_BOTTOM = 10

WHITE = "#ffffff"
BOUND_OPACITY = 0.45  # the reading leads; the bounds are reference marks behind it
AXIS_MARGIN = 5.0

# Plant -> the meter behind it. Plotting the meter rather than the integration's mirror
# avoids "Stale" and "No soil moisture meter near the plant." appearing as states, each
# of which is a break in the line; the meter also carries state_class, so Home Assistant
# keeps long-term statistics for it.
METERS = {
    "dracaena": "sensor.gw1200b_soil_moisture_1",
    "ficus_robusta_darker": "sensor.gw1200b_soil_moisture_3",
    "ficus_tineke_lighter": "sensor.gw1200b_soil_moisture_8",
    "liana": "sensor.gw1200b_soil_moisture_7",
    "malcolm_ficus": "sensor.gw1200b_soil_moisture_6",
    "olive_tree": "sensor.gw1200b_soil_moisture_4",
    "rubber_plant": "sensor.gw1200b_soil_moisture_2",
    "triangularis_ficus": "sensor.gw1200b_soil_moisture_5",
    "yucca": "sensor.gw1200b_soil_moisture_9",
}

# Read from Home Assistant when this was generated.
THRESHOLDS = {
    "dracaena": {"yellow": 25.0, "red": 15.0},
    "ficus_robusta_darker": {"yellow": 35.0, "red": 18.0},
    "ficus_tineke_lighter": {"yellow": 35.0, "red": 18.0},
    "liana": {"yellow": 45.0, "red": 22.0},
    "malcolm_ficus": {"yellow": 35.0, "red": 18.0},
    "olive_tree": {"yellow": 25.0, "red": 12.0},
    "rubber_plant": {"yellow": 35.0, "red": 18.0},
    "triangularis_ficus": {"yellow": 35.0, "red": 18.0},
    "yucca": {"yellow": 20.0, "red": 10.0},
}

# Span of the daily means over the last week, from long-term statistics.
DAILY_RANGE = {
    "dracaena": (48.0, 49.0),
    "ficus_robusta_darker": (45.1, 47.0),
    "ficus_tineke_lighter": (33.5, 75.0),
    "liana": (31.2, 37.0),
    "malcolm_ficus": (23.3, 38.0),
    "olive_tree": (40.0, 43.0),
    "rubber_plant": (31.0, 43.0),
    "triangularis_ficus": (41.7, 66.0),
    "yucca": (39.3, 48.0),
}

# Green needs to see where it would turn yellow; yellow sits between two bounds; red
# only needs the floor it fell through. Stale gets no chart — the reading is not
# trustworthy there, so a line ending in a frozen tail would mislead.
ZONE_LINES = {"green": ["yellow"], "yellow": ["yellow", "red"], "red": ["red"]}

ORDER = list(METERS)


def style(index: int) -> str:
    """card-mod moves the card itself through :host.

    Styling only the inner ha-card leaves the card element in the stack's flow, below
    the 100vh grid, where the panel view's overflow:hidden swallows it. The offset stays
    proportional so the chart tracks its cell; the size stays in pixels so the chart and
    its card agree.
    """
    return (
        ":host {\n"
        "  position: absolute;\n"
        f"  left: calc({index * 100 / COLS:.4f}vw + {CHART_PAD_LEFT}px);\n"
        f"  top: calc({100 / ROWS:.4f}vh - {CHART_H}px - {CHART_PAD_BOTTOM}px);\n"
        f"  width: {CHART_W}px;\n"
        f"  height: {CHART_H}px;\n"
        "  z-index: 3;\n"
        "  pointer-events: none;\n"
        "}\n"
        "ha-card {\n"
        "  width: 100%;\n"
        "  height: 100%;\n"
        "  min-height: 0;\n"
        "  background: none !important;\n"
        "  border: none !important;\n"
        "  box-shadow: none !important;\n"
        "  padding: 0 !important;\n"
        "  margin: 0 !important;\n"
        "  overflow: hidden;\n"
        "}\n"
    )


def chart(plant: str, zone: str, index: int) -> dict:
    values = [THRESHOLDS[plant][kind] for kind in ZONE_LINES[zone]]
    lo_day, hi_day = DAILY_RANGE[plant]
    axis_lo = min([lo_day] + values) - AXIS_MARGIN
    axis_hi = max([hi_day] + values) + AXIS_MARGIN

    return {
        "type": "conditional",
        "conditions": [{"entity": f"sensor.{plant}_soil_moisture_zone", "state": zone}],
        "card": {
            "type": "custom:apexcharts-card",
            "graph_span": "7d",
            "chart_type": "line",
            "header": {"show": False},
            "show": {"loading": False},
            "card_mod": {"style": style(index)},
            "apex_config": {
                "chart": {
                    "sparkline": {"enabled": True},
                    "animations": {"enabled": False},
                    "background": "transparent",
                    "height": CHART_H,
                    "width": CHART_W,
                    "parentHeightOffset": 0,
                },
                "grid": {
                    "show": False,
                    "padding": {"left": 2, "right": 2, "top": 2, "bottom": 2},
                },
                "yaxis": [
                    {
                        "show": False,
                        "min": axis_lo,
                        "max": axis_hi,
                        "forceNiceScale": False,
                        "labels": {"show": False},
                        "axisBorder": {"show": False},
                        "axisTicks": {"show": False},
                    }
                ],
                "tooltip": {"enabled": False},
                "legend": {"show": False},
                "dataLabels": {"enabled": False},
                # One dot per daily mean, joined by straight segments.
                "markers": {"size": 2.2, "strokeWidth": 0, "colors": [WHITE]},
                "annotations": {
                    "yaxis": [
                        {
                            "y": v,
                            "borderColor": WHITE,
                            "borderWidth": 1,
                            "strokeDashArray": 0,
                            "opacity": BOUND_OPACITY,
                        }
                        for v in values
                    ]
                },
            },
            "series": [
                {
                    "entity": METERS[plant],
                    "color": WHITE,
                    "stroke_width": 2.4,
                    "curve": "straight",
                    "statistics": {"type": "mean", "period": "day"},
                    "show": {
                        "legend_value": False,
                        "in_header": False,
                        "extremas": False,
                    },
                }
            ],
        },
    }


class Dumper(yaml.SafeDumper):
    pass


Dumper.add_representer(
    str,
    lambda d, v: d.represent_scalar(
        "tag:yaml.org,2002:str", v, **({"style": "|"} if "\n" in v else {})
    ),
)


def main() -> None:
    lines = BASE.read_text().split("\n")
    idx = next(i for i, l in enumerate(lines) if l == "    cards:")
    head = lines[: idx + 1]
    kept = [("    " + l if l.strip() else l) for l in lines[idx + 1 :]]
    while kept and kept[-1].strip() == "":
        kept.pop()

    overlay = [
        chart(plant, zone, i)
        for i, plant in enumerate(ORDER)
        for zone in ("green", "yellow", "red")
    ]
    dumped = yaml.dump(
        overlay, Dumper=Dumper, sort_keys=False, default_flow_style=False, width=200
    )
    overlay_lines = [("          " + l if l.strip() else l) for l in dumped.split("\n")]
    while overlay_lines and overlay_lines[-1].strip() == "":
        overlay_lines.pop()

    wrapper = [
        "      - type: vertical-stack",
        "        card_mod:",
        "          style: |",
        "            #root {",
        "              position: relative;",
        "              height: 100vh;",
        "              margin: 0 !important;",
        "            }",
        "            #root > * { margin: 0 !important; }",
        "        cards:",
    ]

    OUT.write_text("\n".join(head + wrapper + kept + overlay_lines + [""]))
    print(f"{OUT.name}: {len(overlay)} charts, {CHART_W}x{CHART_H}px each")


if __name__ == "__main__":
    main()
