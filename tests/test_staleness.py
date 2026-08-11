"""Regression tests for the sensor freshness rule.

A reading is trusted only while the meter is still reporting *and* its value has moved
at some point recently. Judging freshness by `last_updated` alone flagged every plant
whose soil moisture simply held steady overnight, so these tests pin both halves.
"""

import unittest
from datetime import datetime, timedelta, timezone

from plants_mcp.tools.get_current_status import staleness


def _ago(**kwargs) -> str:
    return (datetime.now(timezone.utc) - timedelta(**kwargs)).isoformat()


class StalenessTests(unittest.TestCase):
    def test_steady_value_is_not_stale_while_reports_arrive(self) -> None:
        """The regression: soil moisture can sit on one number for days and be fine."""
        verdict = staleness(
            "46",
            _ago(seconds=30),
            _ago(hours=51),
        )
        self.assertFalse(verdict["is_stale"])
        self.assertIsNone(verdict["reason"])

    def test_silence_beyond_six_hours_is_stale(self) -> None:
        verdict = staleness(
            "46",
            _ago(hours=7),
            _ago(hours=7),
        )
        self.assertTrue(verdict["is_stale"])
        self.assertEqual(verdict["reason"], "no_report")
        self.assertEqual(round(verdict["age_seconds"] / 3600), 7)

    def test_frozen_value_beyond_four_days_is_stale(self) -> None:
        verdict = staleness(
            "46",
            _ago(seconds=30),
            _ago(days=5),
        )
        self.assertTrue(verdict["is_stale"])
        self.assertEqual(verdict["reason"], "frozen")
        self.assertEqual(round(verdict["age_seconds"] / 3600), 120)

    def test_value_unchanged_just_under_four_days_is_fresh(self) -> None:
        verdict = staleness(
            "46",
            _ago(seconds=30),
            _ago(days=3, hours=23),
        )
        self.assertFalse(verdict["is_stale"])

    def test_report_age_is_measured_even_when_fresh(self) -> None:
        verdict = staleness("46", _ago(hours=2), _ago(hours=2))
        self.assertFalse(verdict["is_stale"])
        self.assertEqual(round(verdict["age_seconds"] / 3600), 2)

    def test_rendered_stale_state_is_honoured_without_timestamps(self) -> None:
        """The meter may be missing from the payload entirely; the integration's own
        verdict is still the last word, and must not be read back as a live number."""
        verdict = staleness("Stale")
        self.assertTrue(verdict["is_stale"])
        self.assertIsNone(verdict["age_seconds"])

    def test_missing_timestamps_and_a_real_value_are_not_stale(self) -> None:
        verdict = staleness("46")
        self.assertFalse(verdict["is_stale"])
        self.assertIsNone(verdict["age_seconds"])


if __name__ == "__main__":
    unittest.main()
