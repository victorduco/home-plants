"""FastMCP entrypoint."""

import asyncio
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import Client, FastMCP
from fastmcp.server.providers.skills import SkillsDirectoryProvider
from fastmcp.utilities.skills import sync_skills

load_dotenv()

SKILLS_DIR = Path(__file__).parent / "skills"

# Vendor skill directories — add/remove as needed
VENDOR_SKILL_DIRS = [
    Path.home() / ".claude" / "skills",
    Path.home() / ".cursor" / "skills",
    Path.home() / ".copilot" / "skills",
    Path.home() / ".codex" / "skills",
    Path.home() / ".gemini" / "skills",
    Path.home() / ".config" / "agents" / "skills",
    Path.home() / ".config" / "opencode" / "skills",
]


async def _sync_skills_to_vendors(server: FastMCP) -> None:
    """Copy skills from repo into each vendor directory."""
    async with Client(server) as client:
        for target in VENDOR_SKILL_DIRS:
            target.mkdir(parents=True, exist_ok=True)
            await sync_skills(client, target, overwrite=True)


from plants_mcp.tools import register_tools

mcp = FastMCP("My MCP Server")
mcp.add_provider(SkillsDirectoryProvider(roots=SKILLS_DIR, reload=True))
register_tools(mcp)

if __name__ == "__main__":
    asyncio.run(_sync_skills_to_vendors(mcp))
    mcp.run(transport="http")
