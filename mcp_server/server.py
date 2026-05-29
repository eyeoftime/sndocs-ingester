import os
import uvicorn
import httpx
from fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

APP_URL = os.environ["APP_URL"]
API_KEY = os.environ["API_KEY"]
MCP_TOKEN = os.environ["MCP_TOKEN"]
SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:8080")

mcp = FastMCP("SNDocs")

OAUTH_PATHS = {
    "/.well-known/oauth-authorization-server",
    "/.well-known/oauth-protected-resource",
}


class BearerTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in OAUTH_PATHS:
            return JSONResponse({"error": "OAuth not supported"}, status_code=404)
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {MCP_TOKEN}":
            return Response("Forbidden", status_code=403)
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
    mcp_app = mcp.http_app(transport="streamable-http")
    mcp_app.add_middleware(BearerTokenMiddleware)
    uvicorn.run(mcp_app, host="0.0.0.0", port=8080)
