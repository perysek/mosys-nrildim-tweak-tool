"""Local SQLite RBAC store — users/roles/employees/audit log.

Deliberately separate from the Pervasive MOSYS connection (``app.functions.mosys``):
this is app-local identity/authorization data, not production dimensional data.
Follows the same plain-sqlite3 idiom as ``nrildim_journal.py`` (git-ignored data
dir, explicit connect/commit/close, a ``path`` override for tests).
"""

import os
import sqlite3
from datetime import datetime

_DEFAULT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
DEFAULT_DB_PATH = os.path.join(_DEFAULT_DIR, 'auth.sqlite')

_SCHEMA = """
CREATE TABLE IF NOT EXISTS roles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    is_protected INTEGER NOT NULL DEFAULT 0,
    full_access  INTEGER NOT NULL DEFAULT 0,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    email                TEXT UNIQUE NOT NULL,
    password_hash        TEXT NOT NULL,
    full_name            TEXT NOT NULL,
    role                 TEXT NOT NULL DEFAULT 'operator',
    is_active            INTEGER NOT NULL DEFAULT 1,
    must_change_password INTEGER NOT NULL DEFAULT 0,
    last_login           TIMESTAMP,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);

CREATE TABLE IF NOT EXISTS employees (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name         TEXT NOT NULL,
    mosys_employee_id TEXT,
    user_id           INTEGER UNIQUE REFERENCES users(id) ON DELETE SET NULL,
    synced_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_employees_mosys_id
    ON employees(mosys_employee_id) WHERE mosys_employee_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token      TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used       INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_prt_token ON password_reset_tokens(token);

CREATE TABLE IF NOT EXISTS audit_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    user_email   TEXT,
    user_name    TEXT,
    event_type   TEXT NOT NULL,
    entity_type  TEXT,
    entity_id    INTEGER,
    detail       TEXT,
    ip_address   TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_occurred ON audit_log(occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_audit_user     ON audit_log(user_id);
"""

# ('name', 'display_name', is_protected, full_access)
# 'operator' seeds full_access=1 so day-1 rollout doesn't silently strip the
# write capability every existing SPC-tweaks user already had before RBAC
# shipped — a superuser can flip it read-only from the Roles page afterwards.
_SEED_ROLES = [
    ('superuser', 'Superuser', 1, 1),
    ('operator', 'Operator', 0, 1),
]


def get_connection(path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database(path: str = DEFAULT_DB_PATH) -> None:
    conn = get_connection(path)
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
        _seed_roles(conn)
        conn.commit()
    finally:
        conn.close()


def _seed_roles(conn: sqlite3.Connection) -> None:
    for name, display_name, is_protected, full_access in _SEED_ROLES:
        conn.execute(
            "INSERT OR IGNORE INTO roles (name, display_name, is_protected, full_access) "
            "VALUES (?, ?, ?, ?)",
            (name, display_name, is_protected, full_access),
        )


def log_event(event_type: str, *, user_id=None, user_email=None, user_name=None,
              detail=None, entity_type=None, entity_id=None, ip_address=None,
              path: str = DEFAULT_DB_PATH) -> None:
    """Best-effort audit trail write — must never break the calling request."""
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        conn = get_connection(path)
        try:
            conn.execute(
                """INSERT INTO audit_log
                   (occurred_at, user_id, user_email, user_name, event_type,
                    entity_type, entity_id, detail, ip_address)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (now, user_id, user_email, user_name, event_type,
                 entity_type, entity_id, detail, ip_address),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass
