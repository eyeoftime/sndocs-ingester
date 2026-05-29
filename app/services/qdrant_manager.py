import logging
import re

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
    PayloadSchemaType,
)

from app.config import settings
from app.services.chunker import Chunk

logger = logging.getLogger(__name__)


def collection_name(branch: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", branch)[:64]


def get_client() -> QdrantClient:
    kwargs = {"host": settings.qdrant_host, "port": settings.qdrant_port, "https": False}
    if settings.qdrant_api_key:
        kwargs["api_key"] = settings.qdrant_api_key
    return QdrantClient(**kwargs)


def ensure_collection(client: QdrantClient, name: str) -> None:
    existing = {c.name for c in client.get_collections().collections}
    if name not in existing:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(
                size=settings.embedding_dimension,
                distance=Distance.COSINE,
                on_disk=True,
            ),
        )
        client.create_payload_index(name, "file_path", PayloadSchemaType.KEYWORD)
        logger.info("Created collection %s", name)


def upsert_chunks(
    client: QdrantClient,
    collection: str,
    chunks: list[Chunk],
    vectors: list[list[float]],
) -> None:
    points = [
        PointStruct(
            id=chunk.chunk_id,
            vector=vector,
            payload={
                "branch": chunk.branch,
                "file_path": chunk.file_path,
                "heading_path": chunk.heading_path,
                "title": chunk.title,
                "body": chunk.body,
                "url": chunk.url,
                "chunk_index": chunk.chunk_index,
            },
        )
        for chunk, vector in zip(chunks, vectors)
    ]
    # Upsert in batches of 256
    batch_size = 256
    for i in range(0, len(points), batch_size):
        client.upsert(collection_name=collection, points=points[i : i + batch_size])


def delete_points(client: QdrantClient, collection: str, point_ids: list[str]) -> None:
    if not point_ids:
        return
    client.delete(collection_name=collection, points_selector=point_ids)


def delete_collection(client: QdrantClient, name: str) -> None:
    client.delete_collection(name)
