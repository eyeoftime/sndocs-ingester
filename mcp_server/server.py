import os
import uvicorn
import httpx
from fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from starlette.routing import Mount, Route
from starlette.applications import Starlette

APP_URL = os.environ["APP_URL"]
API_KEY = os.environ["API_KEY"]
MCP_TOKEN = os.environ["MCP_TOKEN"]
SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:8080")

mcp = FastMCP("SNDocs")

OAUTH_EXEMPT = {
    "/.well-known/oauth-authorization-server",
    "/.well-known/oauth-protected-resource",
}


class BearerTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in OAUTH_EXEMPT:
            return await call_next(request)
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


async def oauth_metadata(request: Request):
    return JSONResponse({
        "issuer": SERVER_URL,
        "authorization_endpoint": f"{SERVER_URL}/oauth/authorize",
        "token_endpoint": f"{SERVER_URL}/oauth/token",
        "response_types_supported": ["code"],
        "code_challenge_methods_supported": ["S256"],
        "grant_types_supported": ["authorization_code"],
    })


async def protected_resource_metadata(request: Request):
    return JSONResponse({
        "resource": SERVER_URL,
        "authorization_servers": [SERVER_URL],
        "bearer_methods_supported": ["header"],
    })


if __name__ == "__main__":
    mcp_app = mcp.http_app(transport="streamable-http")

    app = Starlette(routes=[
        Route("/.well-known/oauth-authorization-server", oauth_metadata),
        Route("/.well-known/oauth-protected-resource", protected_resource_metadata),
        Mount("/", app=mcp_app),
    ])
    app.add_middleware(BearerTokenMiddleware)

    uvicorn.run(app, host="0.0.0.0", port=8080)
