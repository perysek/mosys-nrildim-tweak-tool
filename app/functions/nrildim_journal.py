"""Pre-image journal for NRILDIM safe writes (IMPLEMENTATION-PLAN.md §3.1 #4/#6/#7).

Every affected row's natural key + original raw MIS ints are persisted to a local
SQLite journal under a ``batch_id`` BEFORE the production DB is touched. On
verified success the batch is purged; on failure it is retained to drive a
rollback / undo path. This module is deliberately DB-agnostic (SQLite only) and
never touches Pervasive.
"""

import json
import os
import sqlite3

# Default journal location (git-ignored data dir).
_DEFAULT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
DEFAULT_JOURNAL_PATH = os.path.join(_DEFAULT_DIR, 'pending_updates.sqlite')


def _connect(path):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pending_update (
            batch_id     TEXT NOT NULL,
            seq          INTEGER NOT NULL,
            table_name   TEXT NOT NULL,
            key_json     TEXT NOT NULL,
            preimage_json TEXT NOT NULL,
            created_at   TEXT NOT NULL,
            PRIMARY KEY (batch_id, seq)
        )
        """
    )
    conn.commit()
    return conn


def write_preimage(batch_id, entries, *, path=DEFAULT_JOURNAL_PATH, created_at=''):
    """Persist pre-images for a batch.

    ``entries`` = list of ``{'key': {...}, 'preimage': {'MIS0k': raw_int, ...}}``.
    Writing happens in its own committed SQLite transaction so the journal
    survives even if the subsequent production write crashes the process.
    """
    conn = _connect(path)
    try:
        for seq, entry in enumerate(entries):
            conn.execute(
                "INSERT INTO pending_update (batch_id, seq, table_name, key_json, preimage_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (batch_id, seq, 'NRILDIM',
                 json.dumps(entry['key'], default=str),
                 json.dumps(entry['preimage'], default=str),
                 created_at),
            )
        conn.commit()
    finally:
        conn.close()


def load_batch(batch_id, *, path=DEFAULT_JOURNAL_PATH):
    """Return the pre-image entries for a batch (for verification / rollback)."""
    if not os.path.exists(path):
        return []
    conn = _connect(path)
    try:
        rows = conn.execute(
            "SELECT key_json, preimage_json FROM pending_update WHERE batch_id = ? ORDER BY seq",
            (batch_id,),
        ).fetchall()
    finally:
        conn.close()
    return [{'key': json.loads(k), 'preimage': json.loads(p)} for k, p in rows]


def purge_batch(batch_id, *, path=DEFAULT_JOURNAL_PATH):
    """Remove a batch from the journal (called after verified success)."""
    if not os.path.exists(path):
        return
    conn = _connect(path)
    try:
        conn.execute("DELETE FROM pending_update WHERE batch_id = ?", (batch_id,))
        conn.commit()
    finally:
        conn.close()


def list_batches(*, path=DEFAULT_JOURNAL_PATH):
    """List retained batch ids (failed/pending) with row counts."""
    if not os.path.exists(path):
        return []
    conn = _connect(path)
    try:
        rows = conn.execute(
            "SELECT batch_id, COUNT(*), MIN(created_at) FROM pending_update GROUP BY batch_id"
        ).fetchall()
    finally:
        conn.close()
    return [{'batch_id': b, 'rows': n, 'created_at': c} for b, n, c in rows]
