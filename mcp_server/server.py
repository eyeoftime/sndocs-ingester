import os
import uvicorn
import httpx
from fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

APP_URL = os.environ["APP_URL"]
API_KEY = os.environ["API_KEY"]
MCP_TOKEN = os.environ["MCP_TOKEN"]

mcp = FastMCP("SNDocs")


class BearerTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {MCP_TOKEN}":
            return Response("Unauthorized", status_code=401)
        return await call_next(request)


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


if __name__ == "__main__":
    app = mcp.http_app(transport="streamable-http")
    app.add_middleware(BearerTokenMiddleware)
    uvicorn.run(app, host="0.0.0.0", port=8080)
