import logging
from pathlib import Path

import httpx

from app.config import settings
from app.db import repository as repo
from app.services import chunker, embedder, git_manager, qdrant_manager

logger = logging.getLogger(__name__)


async def ingest_branch(branch: str, resume: bool = False) -> None:
    """Full ingest (or resume) of a branch.

    When resume=True, files already present in file_chunks are skipped so an
    interrupted ingest can continue without purging existing vectors.
    """
    collection = qdrant_manager.collection_name(branch)
    repo.upsert_branch(branch, collection)
    repo.set_branch_status(branch, "running")

    try:
        git_repo = git_manager.clone_or_pull(branch)
        repo_root = Path(git_repo.working_dir)
        head_sha = git_manager.get_head_sha(git_repo)

        qdrant = qdrant_manager.get_client()
        qdrant_manager.ensure_collection(qdrant, collection)

        if not resume:
            old_ids = repo.delete_all_chunks_for_branch(branch)
            if old_ids:
                qdrant_manager.delete_points(qdrant, collection, old_ids)

        md_files = git_manager.walk_md_files(git_repo)
        if settings.ingest_limit:
            md_files = md_files[: settings.ingest_limit]

        if resume:
            already_done = repo.get_all_ingested_files(branch)
            md_files = [f for f in md_files
                        if str(f.relative_to(repo_root)) not in already_done]
            logger.info("Resuming branch %s — %d files remaining", branch, len(md_files))

        total = len(md_files)
        done_so_far = repo.count_ingested_files(branch) if resume else 0
        grand_total = done_so_far + total
        logger.info("Ingesting %d .md files for branch %s", total, branch)
        repo.set_branch_progress(branch, done_so_far, grand_total)

        existing_tokens = (repo.get_branch(branch) or {}).get("tokens_used") or 0
        total_tokens = existing_tokens if resume else 0

        async with httpx.AsyncClient() as http:
            for i, md_file in enumerate(md_files):
                tokens = await _process_file(branch, collection, md_file, repo_root, qdrant, http)
                total_tokens += tokens
                repo.set_branch_progress(
                    branch, done_so_far + i + 1, grand_total,
                    total_tokens, embedder.tokens_to_cost(total_tokens),
                )

        repo.set_branch_synced(branch, head_sha)
        logger.info("Ingest complete for branch %s @ %s (tokens: %d, cost: $%.4f)",
                    branch, head_sha[:8], total_tokens, embedder.tokens_to_cost(total_tokens))

    except Exception as exc:
        logger.exception("Ingest failed for branch %s", branch)
        repo.set_branch_status(branch, "error", str(exc))
        raise


async def sync_branch(branch: str) -> None:
    """Incremental sync — only process changed files since last ingest."""
    state = repo.get_branch(branch)
    if not state or state["status"] not in ("done",):
        logger.info("Branch %s not yet ingested, running full ingest", branch)
        await ingest_branch(branch)
        return

    old_sha = state["head_sha"]
    collection = state["collection"]
    repo.set_branch_status(branch, "running")

    try:
        git_repo = git_manager.clone_or_pull(branch)
        new_sha = git_manager.get_head_sha(git_repo)

        if old_sha == new_sha:
            logger.info("Branch %s is up to date", branch)
            repo.set_branch_status(branch, "done")
            return

        repo_root = Path(git_repo.working_dir)
        qdrant = qdrant_manager.get_client()
        changed = git_manager.get_changed_files(git_repo, old_sha, new_sha)
        logger.info("%d changed .md files in branch %s", len(changed), branch)

        # Carry over existing token/cost totals and accumulate sync costs on top
        existing_tokens = state["tokens_used"] or 0
        sync_tokens = 0

        async with httpx.AsyncClient() as http:
            for status, file_path in changed:
                if Path(file_path).name == "index.md":
                    continue
                if status == "D":
                    old_ids = repo.delete_file_chunks(branch, file_path)
                    qdrant_manager.delete_points(qdrant, collection, old_ids)
                else:
                    abs_path = repo_root / file_path
                    if abs_path.exists():
                        old_ids = repo.delete_file_chunks(branch, file_path)
                        qdrant_manager.delete_points(qdrant, collection, old_ids)
                        tokens = await _process_file(branch, collection, abs_path, repo_root, qdrant, http)
                        sync_tokens += tokens

        total_tokens = existing_tokens + sync_tokens
        repo.set_branch_synced(branch, new_sha)
        repo.set_branch_progress(
            branch,
            state["files_done"] or 0, state["files_total"] or 0,
            total_tokens, embedder.tokens_to_cost(total_tokens),
        )
        logger.info("Sync complete for branch %s @ %s (sync tokens: %d, cost: $%.4f)",
                    branch, new_sha[:8], sync_tokens, embedder.tokens_to_cost(sync_tokens))

    except Exception as exc:
        logger.exception("Sync failed for branch %s", branch)
        repo.set_branch_status(branch, "error", str(exc))
        raise


async def _process_file(branch, collection, md_file, repo_root, qdrant, http) -> int:
    """Process a single file and return the number of tokens used."""
    chunks = chunker.chunk_file(md_file, branch, repo_root)
    if not chunks:
        return 0

    texts = [f"{c.title}\n\n{c.body}" for c in chunks]
    vectors, tokens = await embedder.embed_texts(texts, http)

    qdrant_manager.upsert_chunks(qdrant, collection, chunks, vectors)
    repo.save_chunk_ids(branch, chunks[0].file_path, [c.chunk_id for c in chunks])
    return tokens
