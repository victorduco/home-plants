"""FastMCP entrypoint."""

from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv()

from plants_mcp.tools import register_tools

mcp = FastMCP("My MCP Server")
register_tools(mcp)

if __name__ == "__main__":
    mcp.run(transport="http")
