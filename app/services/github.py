import httpx
from app.config import settings


async def list_branches() -> list[str]:
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    branches = []
    page = 1
    async with httpx.AsyncClient() as client:
        while True:
            resp = await client.get(
                f"https://api.github.com/repos/{settings.github_repo}/branches",
                headers=headers,
                params={"per_page": 100, "page": page},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data:
                break
            branches.extend(b["name"] for b in data)
            page += 1
    return sorted(branches)
