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

mcp = FastMCP(
    "SNDocs",
    instructions=(
        "This server provides semantic search over ServiceNow documentation. "
        "When the user asks about ServiceNow features, always search the docs. "
        "If the user has not specified a release/version, call list_releases first "
        "to see what is available, then use the most recently synced release unless "
        "the user's question implies a specific one. "
        "ServiceNow releases are named alphabetically (e.g. xanadu, yokohama, zurich) "
        "— the latest release is the one that comes last alphabetically or has the most "
        "recent last_synced_at date returned by list_releases."
    ),
)

class BearerTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path.startswith("/.well-known/"):
            return JSONResponse({"error": "OAuth not supported"}, status_code=404)
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {MCP_TOKEN}":
            return Response("Forbidden", status_code=403)
        return await call_next(request)


async def _get_releases(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get(
        f"{APP_URL}/branches",
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    ingested = data.get("ingested", {})
    done = [v for v in ingested.values() if v.get("status") == "done"]
    # Default branch first, then sort by last_synced_at
    return sorted(done, key=lambda x: (not x.get("is_default"), x.get("last_synced_at") or ""), reverse=False)


@mcp.tool()
async def list_releases() -> list[dict]:
    """List all available ServiceNow documentation releases that can be searched.

    Returns releases sorted by most recently synced first. Call this when the
    user has not specified a release, or when you need to find the latest release.
    Each result includes the branch name (use this in search_docs) and last_synced_at.
    """
    async with httpx.AsyncClient() as client:
        return await _get_releases(client)


@mcp.tool()
async def search_docs(query: str, branch: str | None = None, limit: int = 10) -> list[dict]:
    """Search the ServiceNow documentation for a given query.

    If branch is not specified, the most recently synced release is used automatically.
    Call list_releases first if you need to search a specific version or want to inform
    the user which release is being searched.

    Args:
        query: The search query.
        branch: The release branch to search (e.g. 'xanadu', 'australia').
                If omitted, defaults to the most recently synced release.
        limit: Maximum number of results to return (default 10).
    """
    async with httpx.AsyncClient() as client:
        if not branch:
            releases = await _get_releases(client)
            if not releases:
                return [{"error": "No ingested releases available. Please ingest a branch first."}]
            branch = releases[0]["branch"]

        resp = await client.post(
            f"{APP_URL}/query",
            json={"query": query, "branch": branch, "limit": limit},
            headers={"Authorization": f"Bearer {API_KEY}"},
            timeout=30,
        )
        resp.raise_for_status()
        results = resp.json()["results"]
        # Annotate results with the branch used so Claude can inform the user
        for r in results:
            r["release"] = branch
        return results


if __name__ == "__main__":
    mcp_app = mcp.http_app(transport="streamable-http")
    mcp_app.add_middleware(BearerTokenMiddleware)
    uvicorn.run(mcp_app, host="0.0.0.0", port=8080)
