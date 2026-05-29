import logging
from pathlib import Path

import git

from app.config import settings

logger = logging.getLogger(__name__)


def _repo_path(branch: str) -> Path:
    safe = branch.replace("/", "__")
    return Path(settings.repos_dir) / safe


def clone_or_pull(branch: str) -> git.Repo:
    path = _repo_path(branch)
    url = f"https://github.com/{settings.github_repo}.git"
    if settings.github_token:
        url = f"https://{settings.github_token}@github.com/{settings.github_repo}.git"

    if path.exists():
        logger.info("Pulling branch %s", branch)
        repo = git.Repo(path)
        repo.remotes.origin.fetch()
        repo.git.checkout(branch)
        repo.git.reset("--hard", f"origin/{branch}")
    else:
        logger.info("Cloning branch %s", branch)
        path.mkdir(parents=True, exist_ok=True)
        repo = git.Repo.clone_from(url, path, branch=branch, depth=None)

    return repo


def get_head_sha(repo: git.Repo) -> str:
    return repo.head.commit.hexsha


def get_changed_files(repo: git.Repo, old_sha: str, new_sha: str) -> list[tuple[str, str]]:
    """Return list of (status, file_path) for .md files changed between two SHAs.
    Status: 'A' added, 'M' modified, 'D' deleted, 'R' renamed (treated as modify).
    """
    old_commit = repo.commit(old_sha)
    new_commit = repo.commit(new_sha)
    diffs = old_commit.diff(new_commit)

    results = []
    for d in diffs:
        if d.change_type == "D":
            if d.a_blob and d.a_path.endswith(".md"):
                results.append(("D", d.a_path))
        elif d.change_type == "R":
            if d.a_path.endswith(".md"):
                results.append(("D", d.a_path))
            if d.b_path.endswith(".md"):
                results.append(("A", d.b_path))
        else:
            path = d.b_path or d.a_path
            if path.endswith(".md"):
                results.append((d.change_type, path))

    return results


def walk_md_files(repo: git.Repo) -> list[Path]:
    repo_path = Path(repo.working_dir)
    return [p for p in repo_path.rglob("*.md") if p.name != "index.md"]
