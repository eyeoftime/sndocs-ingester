import asyncio
import logging
from typing import List

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/embeddings"


async def embed_texts(texts: List[str], client: httpx.AsyncClient) -> List[List[float]]:
    """Embed a list of texts in batches, returning one vector per text."""
    if not texts:
        return []

    all_vectors: list[list[float]] = []
    batch_size = settings.embedding_batch_size

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        vectors = await _embed_batch(batch, client)
        all_vectors.extend(vectors)

    return all_vectors


async def _embed_batch(texts: List[str], client: httpx.AsyncClient) -> List[List[float]]:
    # Hard-truncate any individual text that is still too long (> ~24000 chars ≈ 6000 tokens)
    MAX_INPUT_CHARS = 24000
    for i, t in enumerate(texts):
        if len(t) > MAX_INPUT_CHARS:
            logger.warning("Truncating input[%d] from %d chars to %d", i, len(t), MAX_INPUT_CHARS)
            texts[i] = t[:MAX_INPUT_CHARS]

    payload = {"model": settings.embedding_model, "input": texts}
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }

    for attempt in range(3):
        try:
            resp = await client.post(
                OPENROUTER_URL, json=payload, headers=headers, timeout=120
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = 2 ** attempt
                logger.warning("Embedding API returned %s, retrying in %ss", resp.status_code, wait)
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            if "data" not in data:
                # OpenRouter returns {"error": {...}} on quota/model errors
                error = data.get("error", data)
                code = error.get("code", "") if isinstance(error, dict) else ""
                msg = error.get("message", str(error)) if isinstance(error, dict) else str(error)
                # Retry on rate-limit codes; fail fast on others
                if code in (429, "rate_limit_exceeded") or "rate limit" in str(msg).lower():
                    wait = 2 ** attempt
                    logger.warning("Rate limited by embedding API, retrying in %ss: %s", wait, msg)
                    await asyncio.sleep(wait)
                    continue
                raise RuntimeError(f"Embedding API error: {msg}")
            return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]
        except httpx.TimeoutException:
            logger.warning("Embedding request timed out (attempt %s)", attempt + 1)
            await asyncio.sleep(2 ** attempt)

    raise RuntimeError("Embedding API failed after 3 attempts")
