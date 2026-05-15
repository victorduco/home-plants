from __future__ import annotations

import os
from langchain_mcp_adapters.client import MultiServerMCPClient

PLANTS_MCP_URL = os.getenv("PLANTS_MCP_URL", "http://127.0.0.1:8000/mcp")
PLANTS_MCP_API_KEY = os.getenv("FASTMCP_API_KEY", "")


def get_mcp_client() -> MultiServerMCPClient:
    headers = {}
    if PLANTS_MCP_API_KEY:
        headers["X-API-Key"] = PLANTS_MCP_API_KEY

    return MultiServerMCPClient(
        {
            "plants": {
                "transport": "streamable_http",
                "url": PLANTS_MCP_URL,
                "headers": headers,
            }
        }
    )
