import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.db.repository import init_db
from app.routers import auth, ingestion, query
from app.scheduler import start_scheduler

logging.basicConfig(level=settings.log_level)

Path(settings.repos_dir).mkdir(parents=True, exist_ok=True)
Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)


async def _wait_for_qdrant(retries: int = 20, delay: float = 3.0) -> None:
    import asyncio
    from qdrant_client import QdrantClient
    from qdrant_client.http.exceptions import UnexpectedResponse
    import httpx

    logger = logging.getLogger(__name__)
    for attempt in range(1, retries + 1):
        try:
            client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
            client.get_collections()
            logger.info("Qdrant is ready")
            return
        except Exception as exc:
            logger.info("Waiting for Qdrant (%d/%d): %s", attempt, retries, exc)
            await asyncio.sleep(delay)
    raise RuntimeError("Qdrant did not become ready in time")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _wait_for_qdrant()
    init_db()
    start_scheduler()
    yield


app = FastAPI(title="SNDocs Ingester", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(auth.router)
app.include_router(ingestion.router)
app.include_router(query.router)
