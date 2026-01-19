"""FastMCP entrypoint."""

from dotenv import load_dotenv
from fastmcp import FastMCP

from mcp.tools.plants import register_plants_tools

load_dotenv()

mcp = FastMCP("My MCP Server")
register_plants_tools(mcp)

if __name__ == "__main__":
    mcp.run(transport="http")
