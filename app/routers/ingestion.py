import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.db import repository as repo
from app.dependencies import require_auth
from app.services import github as gh
from app.services.sync import ingest_branch
from app.services import qdrant_manager

router = APIRouter(dependencies=[Depends(require_auth)])
templates = Jinja2Templates(directory="app/templates")
logger = logging.getLogger(__name__)

# Track running ingest tasks to prevent double-trigger
_running: set[str] = set()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


@router.get("/branches")
async def list_branches():
    try:
        branches = await gh.list_branches()
        ingested = {row["branch"]: dict(row) for row in repo.list_branches()}
        return JSONResponse({"branches": branches, "ingested": ingested})
    except Exception as exc:
        raise HTTPException(502, f"GitHub API error: {exc}")


@router.post("/ingest/{branch:path}")
async def trigger_ingest(branch: str, background_tasks: BackgroundTasks):
    if branch in _running:
        return JSONResponse({"status": "already_running"}, status_code=409)

    _running.add(branch)
    background_tasks.add_task(_run_ingest, branch)
    return JSONResponse({"status": "started"})


@router.get("/status/{branch:path}")
async def branch_status(branch: str):
    row = repo.get_branch(branch)
    if not row:
        return JSONResponse({"status": "not_ingested"})
    return JSONResponse(dict(row))


@router.post("/default/{branch:path}")
async def set_default(branch: str):
    state = repo.get_branch(branch)
    if not state or state["status"] != "done":
        return JSONResponse({"error": "Branch not available"}, status_code=400)
    repo.set_default_branch(branch)
    return JSONResponse({"status": "ok", "default": branch})


@router.post("/resume/{branch:path}")
async def resume_ingest(branch: str, background_tasks: BackgroundTasks):
    if branch in _running:
        return JSONResponse({"status": "already_running"}, status_code=409)
    state = repo.get_branch(branch)
    if not state:
        return JSONResponse({"error": "Branch not found"}, status_code=404)
    if state["status"] not in ("error", "running"):
        return JSONResponse({"error": "Branch is not in a resumable state"}, status_code=400)

    _running.add(branch)
    background_tasks.add_task(_run_resume, branch)
    return JSONResponse({"status": "started"})


@router.post("/purge/{branch:path}")
async def purge_branch(branch: str):
    if branch in _running:
        return JSONResponse({"error": "Ingest is currently running for this branch"}, status_code=409)
    state = repo.get_branch(branch)
    if not state:
        return JSONResponse({"error": "Branch not found"}, status_code=404)
    try:
        qdrant = qdrant_manager.get_client()
        qdrant_manager.delete_collection(qdrant, state["collection"])
    except Exception as exc:
        logger.warning("Could not delete Qdrant collection for %s: %s", branch, exc)
    repo.delete_branch(branch)
    return JSONResponse({"status": "purged"})


async def _run_ingest(branch: str):
    try:
        await ingest_branch(branch)
    finally:
        _running.discard(branch)


async def _run_resume(branch: str):
    try:
        await ingest_branch(branch, resume=True)
    finally:
        _running.discard(branch)
