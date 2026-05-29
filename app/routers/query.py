import logging

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.db import repository as repo
from app.dependencies import require_auth
from app.services import embedder, qdrant_manager

router = APIRouter(dependencies=[Depends(require_auth)])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)


class QueryRequest(BaseModel):
    branch: str
    query: str
    limit: int = 10


@router.get("/query", response_class=HTMLResponse)
async def query_page(request: Request):
    branches = [row["branch"] for row in repo.list_branches() if row["status"] == "done"]
    return templates.TemplateResponse("query.html", {"request": request, "branches": branches})


@router.post("/query")
async def run_query(req: QueryRequest):
    state = repo.get_branch(req.branch)
    if not state or state["status"] != "done":
        return JSONResponse({"error": "Branch not available"}, status_code=400)

    async with httpx.AsyncClient() as http:
        vectors = await embedder.embed_texts([req.query], http)

    if not vectors:
        return JSONResponse({"error": "Failed to embed query"}, status_code=500)

    qdrant = qdrant_manager.get_client()
    results = qdrant.search(
        collection_name=state["collection"],
        query_vector=vectors[0],
        limit=req.limit,
        with_payload=True,
    )

    hits = [
        {
            "score": round(r.score, 4),
            "title": r.payload.get("title", ""),
            "heading_path": r.payload.get("heading_path", ""),
            "url": r.payload.get("url", ""),
            "body": r.payload.get("body", "")[:500],
        }
        for r in results
    ]
    return JSONResponse({"results": hits})
