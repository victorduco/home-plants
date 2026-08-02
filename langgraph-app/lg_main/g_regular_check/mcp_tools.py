from __future__ import annotations

import os
from langchain_mcp_adapters.client import MultiServerMCPClient

PLANTS_MCP_URL = os.getenv("PLANTS_MCP_URL", "http://127.0.0.1:8000/mcp")
PLANTS_MCP_API_KEY = os.getenv("FASTMCP_API_KEY", "")

# Every node used to build its own client and re-run the MCP handshake, which cost about
# a third of each run's wall time for a tool list that never changes. Both the client and
# the tool list are process-scoped now.
_client: MultiServerMCPClient | None = None
_tools: list | None = None


def get_mcp_client() -> MultiServerMCPClient:
    global _client
    if _client is None:
        headers = {}
        if PLANTS_MCP_API_KEY:
            headers["Authorization"] = f"Bearer {PLANTS_MCP_API_KEY}"

        _client = MultiServerMCPClient(
            {
                "plants": {
                    "transport": "streamable_http",
                    "url": PLANTS_MCP_URL,
                    "headers": headers,
                }
            }
        )
    return _client


async def get_tools() -> list:
    """Return the MCP tool list, fetching it once per process."""
    global _tools
    if _tools is None:
        _tools = await get_mcp_client().get_tools()
    return _tools


async def get_tool_map() -> dict:
    return {t.name: t for t in await get_tools()}
