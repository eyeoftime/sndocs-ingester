import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from app.config import settings


def init_db() -> None:
    schema = (Path(__file__).parent / "schema.sql").read_text()
    with _conn() as conn:
        conn.executescript(schema)
        # Migrations for existing databases
        for col, definition in [("files_done", "INTEGER NOT NULL DEFAULT 0"),
                                 ("files_total", "INTEGER NOT NULL DEFAULT 0"),
                                 ("tokens_used", "INTEGER NOT NULL DEFAULT 0"),
                                 ("cost_usd", "REAL NOT NULL DEFAULT 0.0")]:
            try:
                conn.execute(f"ALTER TABLE branch_state ADD COLUMN {col} {definition}")
            except sqlite3.OperationalError:
                pass  # Column already exists


@contextmanager
def _conn():
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --- branch_state ---

def get_branch(branch: str) -> Optional[sqlite3.Row]:
    with _conn() as conn:
        return conn.execute(
            "SELECT * FROM branch_state WHERE branch = ?", (branch,)
        ).fetchone()


def list_branches() -> list[sqlite3.Row]:
    with _conn() as conn:
        return conn.execute("SELECT * FROM branch_state ORDER BY branch").fetchall()


def upsert_branch(branch: str, collection: str) -> None:
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO branch_state (branch, collection)
            VALUES (?, ?)
            ON CONFLICT(branch) DO UPDATE SET collection = excluded.collection
            """,
            (branch, collection),
        )


def set_branch_status(branch: str, status: str, error_msg: str = None) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE branch_state SET status = ?, error_msg = ? WHERE branch = ?",
            (status, error_msg, branch),
        )


def set_branch_progress(branch: str, files_done: int, files_total: int,
                        tokens_used: int = 0, cost_usd: float = 0.0) -> None:
    with _conn() as conn:
        conn.execute(
            """UPDATE branch_state
               SET files_done = ?, files_total = ?, tokens_used = ?, cost_usd = ?
               WHERE branch = ?""",
            (files_done, files_total, tokens_used, cost_usd, branch),
        )


def set_branch_synced(branch: str, head_sha: str) -> None:
    with _conn() as conn:
        conn.execute(
            """
            UPDATE branch_state
            SET head_sha = ?, status = 'done', error_msg = NULL,
                last_synced_at = datetime('now')
            WHERE branch = ?
            """,
            (head_sha, branch),
        )


# --- file_chunks ---

def get_chunk_ids_for_file(branch: str, file_path: str) -> list[str]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT chunk_id FROM file_chunks WHERE branch = ? AND file_path = ?",
            (branch, file_path),
        ).fetchall()
        return [r["chunk_id"] for r in rows]


def save_chunk_ids(branch: str, file_path: str, chunk_ids: list[str]) -> None:
    with _conn() as conn:
        conn.execute(
            "DELETE FROM file_chunks WHERE branch = ? AND file_path = ?",
            (branch, file_path),
        )
        conn.executemany(
            "INSERT INTO file_chunks (branch, file_path, chunk_id, chunk_index) VALUES (?, ?, ?, ?)",
            [(branch, file_path, cid, idx) for idx, cid in enumerate(chunk_ids)],
        )


def delete_file_chunks(branch: str, file_path: str) -> list[str]:
    chunk_ids = get_chunk_ids_for_file(branch, file_path)
    with _conn() as conn:
        conn.execute(
            "DELETE FROM file_chunks WHERE branch = ? AND file_path = ?",
            (branch, file_path),
        )
    return chunk_ids


def delete_branch(branch: str) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM file_chunks WHERE branch = ?", (branch,))
        conn.execute("DELETE FROM branch_state WHERE branch = ?", (branch,))


def delete_all_chunks_for_branch(branch: str) -> list[str]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT chunk_id FROM file_chunks WHERE branch = ?", (branch,)
        ).fetchall()
        chunk_ids = [r["chunk_id"] for r in rows]
        conn.execute("DELETE FROM file_chunks WHERE branch = ?", (branch,))
    return chunk_ids
