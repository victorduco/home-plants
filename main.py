"""FastMCP entrypoint."""

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.server.providers.skills import ClaudeSkillsProvider

from plants_mcp.prompts import register_prompts
from plants_mcp.resources import register_resources
from plants_mcp.tools import register_tools

load_dotenv()

mcp = FastMCP("My MCP Server")
mcp.add_provider(ClaudeSkillsProvider())
register_tools(mcp)
register_prompts(mcp)
register_resources(mcp)

if __name__ == "__main__":
    mcp.run(transport="http")
