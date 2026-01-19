"""FastMCP entrypoint."""

from dotenv import load_dotenv
from fastmcp import FastMCP

from mcp.prompts import register_prompts
from mcp.resources import register_resources
from mcp.tools import register_tools

load_dotenv()

mcp = FastMCP("My MCP Server")
register_tools(mcp)
register_prompts(mcp)
register_resources(mcp)

if __name__ == "__main__":
    mcp.run(transport="http")
