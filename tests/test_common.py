"""Regression tests for shared MCP tool helpers."""

import unittest

from plants_mcp.tools.common import entity_object_id


class EntityObjectIdTests(unittest.TestCase):
    def test_matches_home_assistant_punctuation_handling(self) -> None:
        self.assertEqual(
            entity_object_id("Ficus Robusta (darker)"),
            "ficus_robusta_darker",
        )
        self.assertEqual(
            entity_object_id("Ficus Tineke (lighter)"),
            "ficus_tineke_lighter",
        )

    def test_collapses_separators(self) -> None:
        self.assertEqual(entity_object_id("  Aloe -- Vera  "), "aloe_vera")
