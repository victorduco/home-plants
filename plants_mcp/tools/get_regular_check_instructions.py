"""Tool: get_regular_check_instructions."""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP

_SKILL_PATH = Path(__file__).parent.parent.parent / "skills" / "regular-check" / "SKILL.md"


def register(mcp: FastMCP) -> None:
    @mcp.tool
    def get_regular_check_instructions() -> str:
        """Return step-by-step instructions for performing a regular plant check and care routine."""
        return _SKILL_PATH.read_text()
