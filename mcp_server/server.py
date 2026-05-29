import os
import httpx
from fastmcp import FastMCP

APP_URL = os.environ["APP_URL"]
API_KEY = os.environ["API_KEY"]

mcp = FastMCP("SNDocs")


@mcp.tool()
async def search_docs(query: str, branch: str, limit: int = 10) -> list[dict]:
    """Search the ServiceNow documentation for a given query.

    Args:
        query: The search query.
        branch: The documentation branch/release to search (e.g. 'xanadu', 'australia').
        limit: Maximum number of results to return (default 10).
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{APP_URL}/query",
            json={"query": query, "branch": branch, "limit": limit},
            headers={"Authorization": f"Bearer {API_KEY}"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["results"]
