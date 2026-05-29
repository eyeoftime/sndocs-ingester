import asyncio
import logging
import time
from typing import List

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

OPENROUTER_URL = "https://openrouter.ai/api/v1/embeddings"

# Cost per token in USD (text-embedding-3-small via OpenRouter)
COST_PER_TOKEN = 0.02 / 1_000_000

# Shared backoff state — when any worker is rate limited, all workers pause
_backoff_until: float = 0.0
_backoff_lock = asyncio.Lock()


async def _wait_for_backoff() -> None:
    """Wait if a rate limit backoff is currently active."""
    remaining = _backoff_until - time.monotonic()
    if remaining > 0:
        logger.info("Rate limit backoff active — waiting %.1fs", remaining)
        await asyncio.sleep(remaining)


async def _set_backoff(delay: float) -> None:
    """Set a shared backoff period, extending any existing one."""
    global _backoff_until
    async with _backoff_lock:
        _backoff_until = max(_backoff_until, time.monotonic() + delay)
        logger.warning("Rate limit hit — backing off for %.1fs", delay)


async def embed_texts(texts: List[str], client: httpx.AsyncClient) -> tuple[List[List[float]], int]:
    """Embed a list of texts in batches. Returns (vectors, total_tokens_used)."""
    if not texts:
        return [], 0

    all_vectors: list[list[float]] = []
    total_tokens = 0
    batch_size = settings.embedding_batch_size

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        vectors, tokens = await _embed_batch(batch, client)
        all_vectors.extend(vectors)
        total_tokens += tokens

    return all_vectors, total_tokens


async def _embed_batch(texts: List[str], client: httpx.AsyncClient) -> tuple[List[List[float]], int]:
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

    for attempt in range(5):
        await _wait_for_backoff()

        try:
            resp = await client.post(
                OPENROUTER_URL, json=payload, headers=headers, timeout=120
            )

            if resp.status_code == 429 or resp.status_code >= 500:
                # Honour Retry-After header if present, else exponential backoff
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 2 ** attempt
                await _set_backoff(delay)
                continue

            resp.raise_for_status()
            data = resp.json()

            if "data" not in data:
                error = data.get("error", data)
                code = error.get("code", "") if isinstance(error, dict) else ""
                msg = error.get("message", str(error)) if isinstance(error, dict) else str(error)
                if code in (429, "rate_limit_exceeded") or "rate limit" in str(msg).lower():
                    delay = 2 ** attempt
                    await _set_backoff(delay)
                    continue
                raise RuntimeError(f"Embedding API error: {msg}")

            tokens = data.get("usage", {}).get("prompt_tokens", 0)
            vectors = [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]
            return vectors, tokens

        except httpx.TimeoutException:
            delay = 2 ** attempt
            logger.warning("Embedding request timed out (attempt %d) — retrying in %.0fs", attempt + 1, delay)
            await asyncio.sleep(delay)

    raise RuntimeError("Embedding API failed after 5 attempts")


def tokens_to_cost(tokens: int) -> float:
    return tokens * COST_PER_TOKEN
