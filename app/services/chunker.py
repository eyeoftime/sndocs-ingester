import re
import uuid
from dataclasses import dataclass
from pathlib import Path


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")
FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
# Approximate token limit per chunk — text-embedding-3-small supports 8191 tokens
MAX_CHARS = 1500


@dataclass
class Chunk:
    chunk_id: str
    branch: str
    file_path: str
    heading_path: str
    title: str
    body: str
    url: str
    chunk_index: int


def _build_url(branch: str, file_path: str) -> str:
    # Strip the leading path component (e.g. "markdown/") and swap .md → .html
    parts = Path(file_path).parts
    relative = Path(*parts[1:]) if len(parts) > 1 else Path(file_path)
    html_path = relative.with_suffix(".html")
    return f"https://www.servicenow.com/docs/r/{branch}/{html_path}"


def _deterministic_id(branch: str, file_path: str, chunk_index: int) -> str:
    key = f"{branch}:{file_path}:{chunk_index}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def _split_long_body(body: str) -> list[str]:
    if len(body) <= MAX_CHARS:
        return [body]

    # Split on blank lines first, then hard-split any paragraph still over the limit
    raw_paragraphs: list[str] = []
    for para in body.split("\n\n"):
        if len(para) <= MAX_CHARS:
            raw_paragraphs.append(para)
        else:
            # Hard-split on newlines, then by character if still too long
            for line in para.split("\n"):
                while len(line) > MAX_CHARS:
                    raw_paragraphs.append(line[:MAX_CHARS])
                    line = line[MAX_CHARS:]
                if line:
                    raw_paragraphs.append(line)

    parts: list[str] = []
    current = ""
    for para in raw_paragraphs:
        if current and len(current) + len(para) + 2 > MAX_CHARS:
            parts.append(current.strip())
            current = para
        else:
            current = (current + "\n\n" + para) if current else para
    if current.strip():
        parts.append(current.strip())
    return parts or [body[:MAX_CHARS]]


def chunk_file(file_path: Path, branch: str, repo_root: Path) -> list[Chunk]:
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    text = FRONTMATTER_RE.sub("", text, count=1)

    rel_path = str(file_path.relative_to(repo_root))
    url = _build_url(branch, rel_path)

    # Parse into raw sections: each section is (heading_stack, body_lines)
    sections: list[tuple[list[str], list[str]]] = []
    heading_stack: list[tuple[int, str]] = []
    current_body: list[str] = []
    current_title: str = ""

    for line in text.splitlines():
        m = HEADING_RE.match(line)
        if m:
            # Save previous section
            if current_title or current_body:
                sections.append((
                    [t for _, t in heading_stack[:-1]] + [current_title],
                    current_body,
                ))
            level = len(m.group(1))
            current_title = m.group(2).strip()
            current_body = []
            # Trim heading stack to current level
            heading_stack = [(l, t) for l, t in heading_stack if l < level]
            heading_stack.append((level, current_title))
        else:
            current_body.append(line)

    # Final section
    if current_title or current_body:
        sections.append((
            [t for _, t in heading_stack[:-1]] + [current_title],
            current_body,
        ))

    # If file has no headings at all, split by MAX_CHARS and return
    if not sections:
        body = text.strip()
        if not body:
            return []
        return [
            Chunk(
                chunk_id=_deterministic_id(branch, rel_path, idx),
                branch=branch,
                file_path=rel_path,
                heading_path="",
                title=file_path.stem,
                body=part,
                url=url,
                chunk_index=idx,
            )
            for idx, part in enumerate(_split_long_body(body))
        ]

    chunks: list[Chunk] = []
    chunk_index = 0
    for heading_list, body_lines in sections:
        body = "\n".join(body_lines).strip()
        title = heading_list[-1] if heading_list else file_path.stem
        heading_path = " > ".join(heading_list)

        for part in _split_long_body(body) if body else [""]:
            chunks.append(Chunk(
                chunk_id=_deterministic_id(branch, rel_path, chunk_index),
                branch=branch,
                file_path=rel_path,
                heading_path=heading_path,
                title=title,
                body=part,
                url=url,
                chunk_index=chunk_index,
            ))
            chunk_index += 1

    return chunks
