CREATE TABLE IF NOT EXISTS branch_state (
    branch         TEXT PRIMARY KEY,
    collection     TEXT NOT NULL,
    head_sha       TEXT,
    status         TEXT NOT NULL DEFAULT 'pending',
    error_msg      TEXT,
    last_synced_at TEXT,
    files_done     INTEGER NOT NULL DEFAULT 0,
    files_total    INTEGER NOT NULL DEFAULT 0,
    tokens_used    INTEGER NOT NULL DEFAULT 0,
    cost_usd       REAL    NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS file_chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    branch      TEXT NOT NULL,
    file_path   TEXT NOT NULL,
    chunk_id    TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    UNIQUE(branch, file_path, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_file_chunks_branch_file
    ON file_chunks(branch, file_path);
