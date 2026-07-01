# Flask RBAC Golden Book
## DMC_validate Pattern — Complete Implementation Reference

This document captures every decision, pattern, and line of code needed to implement
the full RBAC + Flask-Login system from this project. Starting from zero, a fresh
session can follow this book with **0 decision breakpoints** and **0 implementation doubts**.

---

## Architecture Overview

```
auth/login.html  (standalone — NO {% extends %})
     │
     ├── Regular login:      POST /auth/login      → authenticate_by_employee_id()
     └── First-login form:   POST /auth/first-login → update_password() + clear_must_change_password()

app.py (create_app factory)
  ├── initialize_database()     → db.py  (SQLite, schema + migrations inline)
  ├── LoginManager setup        → user_loader → UserRepository.get_by_id()
  ├── context_processor         → injects user_permissions + current_mosys_employee_id
  └── register_blueprint × 7   → main, api, auth, users, roles, employees, audit

config/auth_config.py
  ├── ROLE_HIERARCHY            (display/sorting only)
  ├── MODULE_PERMISSIONS        (static fallback dict)
  ├── role_required(*roles)     → decorator: exact role name match, no DB
  ├── module_permission_required(*modules) → decorator: DB lookup, OR logic, fallback
  └── get_user_module_permissions(role)    → used by context processor

repositories/
  ├── users/user_repository.py  → bcrypt, CRUD, mosys_id lookup, employee link
  ├── roles/role_repository.py  → ALL_MODULES, permissions upsert
  └── employees/employee_repository.py → MOSYS sync, CRUD

services/auth/auth_service.py  → authenticate, authenticate_by_employee_id, change_password

database/
  ├── db.py   → get_connection(), initialize_database(), log_event(), seed_roles()
  └── models.py → User (UserMixin), Employee, DmcScan, OrderInfo dataclasses
```

### Key Differentiator: MOSYS-ID-Based Login

Login is by **employee ID number** (4-digit string from STAAMPDB.OPERATORI), not email.
Email is auto-generated as `{mosys_id}@dmc.local` and never shown to users.
Authentication looks up the user via `employees.mosys_employee_id → users.id`.

---

## Questions to Answer for a New Project (Scope Only)

1. **What are the module names?** → `ALL_MODULES` list in `role_repository.py`
2. **What built-in roles?** → seed in `_seed_roles_and_permissions()` in `db.py`
3. **Login by email or employee ID?** → determines `authenticate()` vs `authenticate_by_employee_id()`
4. **Is MOSYS/external DB linking needed?** → `employees.mosys_employee_id` FK + sync endpoint
5. **Password reset: on-screen token or email SMTP?** → this project uses on-screen token, no SMTP

---

## 1. Database Schema — SQLite (inline in db.py)

All tables created in `initialize_database()` using `CREATE TABLE IF NOT EXISTS`.
Safe migrations appended after the `executescript` block as `ALTER TABLE ... ADD COLUMN` in
individual `try/except` blocks (column-already-exists error = no-op).

```sql
-- ── Roles ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS roles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT UNIQUE NOT NULL,       -- system key: 'superuser', 'operator'
    display_name TEXT NOT NULL,              -- human label: 'Owner/Superuser'
    is_protected INTEGER DEFAULT 0,          -- 1 = cannot be deleted via UI
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Module permissions (RBAC pivot) ───────────────────────────────────
CREATE TABLE IF NOT EXISTS role_permissions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id     INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    module_name TEXT NOT NULL,               -- must match ALL_MODULES in code
    has_access  INTEGER DEFAULT 1,
    UNIQUE (role_id, module_name)            -- upsert key
);
CREATE INDEX IF NOT EXISTS idx_role_permissions_role ON role_permissions(role_id);

-- ── Users ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    email               TEXT UNIQUE NOT NULL,  -- auto-generated: {mosys_id}@dmc.local
    password_hash       TEXT NOT NULL,
    full_name           TEXT NOT NULL,
    role                TEXT NOT NULL DEFAULT 'operator',
    is_active           INTEGER NOT NULL DEFAULT 1,
    last_login          TIMESTAMP,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);

-- ── Employees (links users ↔ MOSYS OPERATORI) ─────────────────────────
CREATE TABLE IF NOT EXISTS employees (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name        TEXT NOT NULL,
    last_name         TEXT NOT NULL,
    employee_no       TEXT,                  -- optional internal HR number
    user_id           INTEGER UNIQUE REFERENCES users(id) ON DELETE SET NULL,
    mosys_employee_id TEXT,                  -- CODICE from STAAMPDB.OPERATORI
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_employees_mosys_id
    ON employees(mosys_employee_id) WHERE mosys_employee_id IS NOT NULL;

-- ── Password reset tokens ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token      TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    used       INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_prt_token ON password_reset_tokens(token);

-- ── Audit log ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    user_email   TEXT,
    user_name    TEXT,
    event_type   TEXT NOT NULL,   -- 'login_ok', 'login_failed', 'user_create', …
    entity_type  TEXT,            -- 'user', 'role', 'employee'
    entity_id    INTEGER,
    detail       TEXT,
    ip_address   TEXT
);
CREATE INDEX IF NOT EXISTS ix_audit_occurred ON audit_log(occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_audit_user     ON audit_log(user_id);
```

### Safe Migration Pattern

```python
# After the executescript block — each in its own try/except
migrations = [
    "ALTER TABLE employees ADD COLUMN mosys_employee_id TEXT",
    "ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE dmc_scans ADD COLUMN scanned_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL",
]
for sql in migrations:
    try:
        conn.execute(sql)
    except Exception:
        pass  # column already exists — no-op
```

### Built-in Role Seed (idempotent)

```python
def _seed_roles_and_permissions():
    roles = [
        ('superuser', 'Owner/Superuser', 1),  # is_protected=1
        ('operator',  'Operator',        0),
    ]
    role_module_access = {
        'superuser': {'dmc_validation': 1, 'history': 1, 'admin': 1, 'audit': 1,
                      'manual_mode': 1, 'tryb_korekty': 1},
        'operator':  {'dmc_validation': 1, 'history': 1, 'admin': 0, 'audit': 0,
                      'manual_mode': 0, 'tryb_korekty': 0},
    }
    with get_connection() as conn:
        for name, display_name, is_protected in roles:
            conn.execute(
                "INSERT OR IGNORE INTO roles (name, display_name, is_protected) VALUES (?, ?, ?)",
                (name, display_name, is_protected),
            )
        for role_name, perms in role_module_access.items():
            row = conn.execute("SELECT id FROM roles WHERE name = ?", (role_name,)).fetchone()
            if row:
                for module, has_access in perms.items():
                    conn.execute(
                        "INSERT OR IGNORE INTO role_permissions (role_id, module_name, has_access) VALUES (?, ?, ?)",
                        (row['id'], module, has_access),
                    )
```

---

## 2. Database Connection — db.py

```python
import sqlite3
from pathlib import Path
from config.settings import DATABASE_PATH

def get_connection() -> sqlite3.Connection:
    Path(DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row   # dict-like rows: row['column_name']
    conn.execute("PRAGMA journal_mode=WAL")
    return conn
```

**Critical**: always use `sqlite3.Row` — rows accessed as `row['column']`, not positional.

### Audit Log Helper (module-level function, not a class)

```python
def log_event(
    event_type: str,
    user_id: int | None = None,
    user_email: str | None = None,
    user_name: str | None = None,
    detail: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    ip_address: str | None = None,
) -> None:
    from datetime import datetime
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    try:
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO audit_log
                   (occurred_at, user_id, user_email, user_name, event_type,
                    entity_type, entity_id, detail, ip_address)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (now, user_id, user_email, user_name, event_type,
                 entity_type, entity_id, detail, ip_address),
            )
    except Exception:
        pass  # audit failures must never break the main flow
```

Call pattern in routes:
```python
from database.db import log_event
log_event('login_ok', user_id=user.id, user_email=user.email,
          user_name=user.full_name, ip_address=request.remote_addr)
```

---

## 3. Data Models — database/models.py

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from flask_login import UserMixin

@dataclass
class User(UserMixin):
    email: str
    password_hash: str
    full_name: str
    role: str = 'operator'
    is_active: bool = True
    must_change_password: bool = False
    id: Optional[int] = None
    last_login: Optional[datetime] = None
    created_at: Optional[datetime] = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = field(default_factory=datetime.now)

    def get_id(self):           # required by Flask-Login
        return str(self.id)

    @property
    def is_authenticated(self): # always True — Flask-Login requirement
        return True

    @property
    def is_anonymous(self):     # always False
        return False

    def has_role(self, *roles):
        return self.role in roles

@dataclass
class Employee:
    first_name: str
    last_name: str
    employee_no: Optional[str] = None
    mosys_employee_id: Optional[str] = None
    user_id: Optional[int] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = field(default_factory=datetime.now)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
```

---

## 4. Config — config/auth_config.py

```python
from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user

ROLE_HIERARCHY = {
    'superuser': 2,
    'operator': 1,
}

# Static fallback — DB role_permissions is the real source of truth
MODULE_PERMISSIONS = {
    'dmc_validation': ['superuser', 'operator'],
    'history':        ['superuser', 'operator'],
    'admin':          ['superuser'],
    'audit':          ['superuser'],
    'manual_mode':    ['superuser'],
    'tryb_korekty':   ['superuser'],
}


def role_required(*roles):
    """Exact role name match — no DB query, fast. Use for admin/management pages."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Musisz być zalogowany', 'error')
                return redirect(url_for('auth.login'))
            if current_user.role not in roles:
                flash('Brak uprawnień', 'error')
                return redirect(url_for('main.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def module_permission_required(*module_names):
    """DB lookup (OR logic across modules) with static fallback on DB error."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Musisz być zalogowany', 'error')
                return redirect(url_for('auth.login'))

            has_access = False
            try:
                from repositories.roles.role_repository import RoleRepository
                repo = RoleRepository()
                for mod in module_names:
                    if repo.role_has_module_access(current_user.role, mod):
                        has_access = True
                        break
            except Exception:
                for mod in module_names:
                    if current_user.role in MODULE_PERMISSIONS.get(mod, []):
                        has_access = True
                        break

            if not has_access:
                flash(f'Brak dostępu do modułu: {module_names[0]}', 'error')
                return redirect(url_for('main.index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def get_user_module_permissions(role_name: str) -> dict:
    """Returns {module: bool} for a role — used by context processor."""
    try:
        from repositories.roles.role_repository import RoleRepository
        return RoleRepository().get_user_module_permissions(role_name)
    except Exception:
        return {
            module: role_name in allowed_roles
            for module, allowed_roles in MODULE_PERMISSIONS.items()
        }
```

### Decorator Stack Rules

| Page type | Decorators |
|-----------|-----------|
| Login, forgot-password, reset-password | none (public) |
| App pages (scanner, history) | `@login_required` + `@module_permission_required('module')` |
| Admin management (users, roles, employees) | `@login_required` + `@role_required('superuser')` |
| Audit log | `@login_required` + `@module_permission_required('audit')` |

---

## 5. Repositories

### 5a. UserRepository — repositories/users/user_repository.py

```python
import bcrypt
from datetime import datetime
from typing import Optional, Any
from database.db import get_connection
from database.models import User

class UserRepository:

    _columns = ('id, email, password_hash, full_name, role, is_active, '
                'must_change_password, last_login, created_at, updated_at')

    def _validate_role(self, role: str):
        with get_connection() as conn:
            row = conn.execute("SELECT 1 FROM roles WHERE name = ?", (role,)).fetchone()
            if not row:
                raise ValueError(f"Rola '{role}' nie istnieje")

    def row_to_user(self, row: Any) -> User:
        return User(
            id=row['id'], email=row['email'], password_hash=row['password_hash'],
            full_name=row['full_name'], role=row['role'],
            is_active=bool(row['is_active']),
            must_change_password=bool(row['must_change_password']),
            last_login=row['last_login'],
            created_at=row['created_at'], updated_at=row['updated_at'],
        )

    def create_user(self, email: str, password: str, full_name: str,
                    role: str = 'operator', must_change_password: bool = False) -> int:
        self._validate_role(role)
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO users (email, password_hash, full_name, role, must_change_password) "
                "VALUES (?, ?, ?, ?, ?)",
                (email.strip().lower(), password_hash, full_name.strip(),
                 role, int(must_change_password)),
            )
            return cursor.lastrowid

    def get_by_id(self, user_id: int) -> Optional[Any]:
        with get_connection() as conn:
            return conn.execute(
                f"SELECT {self._columns} FROM users WHERE id = ?", (user_id,)
            ).fetchone()

    def get_by_email(self, email: str) -> Optional[User]:
        with get_connection() as conn:
            row = conn.execute(
                f"SELECT {self._columns} FROM users WHERE email = ?",
                (email.strip().lower(),)
            ).fetchone()
        return self.row_to_user(row) if row else None

    def get_by_mosys_employee_id(self, mosys_id: str) -> Optional[User]:
        """Primary login lookup — joins employees table."""
        cols = ', '.join(f'u.{c.strip()}' for c in self._columns.split(','))
        with get_connection() as conn:
            row = conn.execute(
                f"SELECT {cols} FROM users u "
                "INNER JOIN employees e ON e.user_id = u.id "
                "WHERE e.mosys_employee_id = ?",
                (mosys_id,),
            ).fetchone()
        return self.row_to_user(row) if row else None

    def get_all(self) -> list:
        with get_connection() as conn:
            return conn.execute(
                f"SELECT {self._columns} FROM users ORDER BY full_name"
            ).fetchall()

    def get_all_with_employee(self) -> list:
        """For admin list view — includes linked employee data."""
        with get_connection() as conn:
            return conn.execute("""
                SELECT u.id, u.email, u.full_name, u.role, u.is_active,
                       u.last_login, u.created_at,
                       e.id AS employee_id,
                       e.mosys_employee_id AS employee_mosys_id,
                       e.first_name AS employee_first_name,
                       e.last_name  AS employee_last_name
                FROM users u LEFT JOIN employees e ON e.user_id = u.id
                ORDER BY u.full_name
            """).fetchall()

    def get_employee_for_user(self, user_id: int) -> Optional[Any]:
        with get_connection() as conn:
            return conn.execute(
                "SELECT id, first_name, last_name, employee_no, mosys_employee_id "
                "FROM employees WHERE user_id = ?", (user_id,)
            ).fetchone()

    def get_available_employees(self) -> list:
        """Employees not yet linked to any user account."""
        with get_connection() as conn:
            return conn.execute(
                "SELECT id, first_name, last_name, employee_no, mosys_employee_id "
                "FROM employees WHERE user_id IS NULL ORDER BY last_name"
            ).fetchall()

    def get_login_employees(self) -> list:
        """Active user-linked employees for login dropdown datalist."""
        with get_connection() as conn:
            return conn.execute("""
                SELECT e.mosys_employee_id, u.full_name
                FROM employees e INNER JOIN users u ON u.id = e.user_id
                WHERE e.mosys_employee_id IS NOT NULL AND e.mosys_employee_id != ''
                  AND u.is_active = 1
                ORDER BY e.mosys_employee_id
            """).fetchall()

    def verify_password(self, user: User, password: str) -> bool:
        return bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8'))

    def update_last_login(self, user_id: int):
        with get_connection() as conn:
            conn.execute(
                "UPDATE users SET last_login = ? WHERE id = ?",
                (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id),
            )

    def update_password(self, user_id: int, new_password: str):
        password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        with get_connection() as conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (password_hash, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id),
            )

    def clear_must_change_password(self, user_id: int):
        with get_connection() as conn:
            conn.execute(
                "UPDATE users SET must_change_password = 0, updated_at = ? WHERE id = ?",
                (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id),
            )

    def update_user(self, user_id: int, full_name: str, role: str, is_active: bool):
        self._validate_role(role)
        with get_connection() as conn:
            conn.execute(
                "UPDATE users SET full_name = ?, role = ?, is_active = ?, updated_at = ? WHERE id = ?",
                (full_name.strip(), role, int(is_active),
                 datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id),
            )

    def toggle_active(self, user_id: int) -> bool:
        with get_connection() as conn:
            row = conn.execute("SELECT is_active FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                raise ValueError('Użytkownik nie istnieje')
            new_state = 0 if row['is_active'] else 1
            conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (new_state, user_id))
            return bool(new_state)

    def link_employee(self, employee_id: int, user_id: int):
        with get_connection() as conn:
            conn.execute("UPDATE employees SET user_id = ? WHERE id = ?", (user_id, employee_id))

    def unlink_employee(self, user_id: int):
        with get_connection() as conn:
            conn.execute("UPDATE employees SET user_id = NULL WHERE user_id = ?", (user_id,))
```

### 5b. RoleRepository — repositories/roles/role_repository.py

```python
from typing import Any, Optional
from database.db import get_connection

ALL_MODULES = ['dmc_validation', 'history', 'admin', 'audit', 'manual_mode', 'tryb_korekty']

MODULE_DISPLAY_NAMES = {
    'dmc_validation': 'Skaner DMC',
    'history':        'Historia skanów',
    'admin':          'Administracja',
    'audit':          'Dziennik zdarzeń',
    'manual_mode':    'Tryb manualny',
    'tryb_korekty':   'Tryb korekty',
}


class RoleRepository:

    def get_all(self) -> list:
        with get_connection() as conn:
            return conn.execute("""
                SELECT r.id, r.name, r.display_name, r.is_protected, r.created_at,
                       COUNT(rp.id) FILTER (WHERE rp.has_access = 1) AS access_count
                FROM roles r
                LEFT JOIN role_permissions rp ON rp.role_id = r.id
                GROUP BY r.id ORDER BY r.id
            """).fetchall()

    def get_by_id(self, role_id: int) -> Optional[Any]:
        with get_connection() as conn:
            return conn.execute("SELECT * FROM roles WHERE id = ?", (role_id,)).fetchone()

    def create(self, name: str, display_name: str) -> int:
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO roles (name, display_name, is_protected) VALUES (?, ?, 0)",
                (name, display_name),
            )
            return cursor.lastrowid

    def update(self, role_id: int, display_name: str):
        with get_connection() as conn:
            conn.execute("UPDATE roles SET display_name = ? WHERE id = ?", (display_name, role_id))

    def delete(self, role_id: int) -> bool:
        with get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM roles WHERE id = ? AND is_protected = 0", (role_id,)
            )
            return cursor.rowcount > 0

    def get_permissions(self, role_id: int) -> dict:
        """Returns {module: bool} — missing modules default to False."""
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT module_name, has_access FROM role_permissions WHERE role_id = ?",
                (role_id,),
            ).fetchall()
        db_perms = {row['module_name']: bool(row['has_access']) for row in rows}
        return {m: db_perms.get(m, False) for m in ALL_MODULES}

    def set_permissions(self, role_id: int, permissions: dict):
        """Upsert all known modules — INSERT OR REPLACE pattern."""
        with get_connection() as conn:
            for module in ALL_MODULES:
                conn.execute(
                    "INSERT INTO role_permissions (role_id, module_name, has_access) VALUES (?, ?, ?)"
                    " ON CONFLICT (role_id, module_name) DO UPDATE SET has_access = excluded.has_access",
                    (role_id, module, int(bool(permissions.get(module, False)))),
                )

    def role_has_module_access(self, role_name: str, module_name: str) -> bool:
        """Used by module_permission_required decorator."""
        with get_connection() as conn:
            row = conn.execute("""
                SELECT rp.has_access FROM role_permissions rp
                JOIN roles r ON r.id = rp.role_id
                WHERE r.name = ? AND rp.module_name = ?
            """, (role_name, module_name)).fetchone()
        if row is None:
            from config.auth_config import MODULE_PERMISSIONS
            return role_name in MODULE_PERMISSIONS.get(module_name, [])
        return bool(row['has_access'])

    def get_user_module_permissions(self, role_name: str) -> dict:
        """Returns {module_name: bool} — used by context processor."""
        with get_connection() as conn:
            rows = conn.execute("""
                SELECT rp.module_name, rp.has_access FROM role_permissions rp
                JOIN roles r ON r.id = rp.role_id WHERE r.name = ?
            """, (role_name,)).fetchall()
        db_perms = {row['module_name']: bool(row['has_access']) for row in rows}
        from config.auth_config import MODULE_PERMISSIONS
        return {
            m: db_perms[m] if m in db_perms else (role_name in MODULE_PERMISSIONS.get(m, []))
            for m in ALL_MODULES
        }
```

### 5c. EmployeeRepository — repositories/employees/employee_repository.py

```python
from typing import Any, Optional
from database.db import get_connection

class EmployeeRepository:

    def get_all(self) -> list:
        with get_connection() as conn:
            return conn.execute("""
                SELECT e.id, e.first_name, e.last_name, e.employee_no, e.mosys_employee_id,
                       e.user_id, e.created_at,
                       u.full_name AS user_full_name, u.email AS user_email
                FROM employees e LEFT JOIN users u ON u.id = e.user_id
                ORDER BY e.last_name, e.first_name
            """).fetchall()

    def get_by_mosys_id(self, mosys_id: str) -> Optional[Any]:
        with get_connection() as conn:
            return conn.execute(
                "SELECT * FROM employees WHERE mosys_employee_id = ?", (mosys_id,)
            ).fetchone()

    def create(self, first_name: str, last_name: str,
               employee_no: Optional[str] = None,
               mosys_employee_id: Optional[str] = None) -> int:
        with get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO employees (first_name, last_name, employee_no, mosys_employee_id) "
                "VALUES (?, ?, ?, ?)",
                (first_name.strip(), last_name.strip(),
                 employee_no.strip() if employee_no else None,
                 mosys_employee_id.strip() if mosys_employee_id else None),
            )
            return cursor.lastrowid

    def update(self, employee_id: int, first_name: str, last_name: str,
               employee_no: Optional[str], mosys_employee_id: Optional[str]):
        with get_connection() as conn:
            conn.execute(
                "UPDATE employees SET first_name=?, last_name=?, employee_no=?, mosys_employee_id=? WHERE id=?",
                (first_name.strip(), last_name.strip(),
                 employee_no.strip() if employee_no else None,
                 mosys_employee_id.strip() if mosys_employee_id else None,
                 employee_id),
            )

    def delete(self, employee_id: int) -> bool:
        with get_connection() as conn:
            row = conn.execute("SELECT user_id FROM employees WHERE id=?", (employee_id,)).fetchone()
            if not row:
                return False
            if row['user_id']:
                raise ValueError("Nie można usunąć pracownika powiązanego z kontem użytkownika")
            cursor = conn.execute("DELETE FROM employees WHERE id=?", (employee_id,))
            return cursor.rowcount > 0

    def sync_from_mosys(self, mosys_employees: list[dict]) -> dict:
        """
        Upsert employees by mosys_employee_id.
        Input: list of {mosys_id, first_name, last_name, full_name}
        Returns: {added: int, updated: int}
        """
        added = updated = 0
        with get_connection() as conn:
            for emp in mosys_employees:
                mosys_id = emp['mosys_id']
                existing = conn.execute(
                    "SELECT id FROM employees WHERE mosys_employee_id=?", (mosys_id,)
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE employees SET first_name=?, last_name=? WHERE mosys_employee_id=?",
                        (emp['first_name'], emp['last_name'], mosys_id),
                    )
                    updated += 1
                else:
                    conn.execute(
                        "INSERT INTO employees (first_name, last_name, mosys_employee_id) VALUES (?,?,?)",
                        (emp['first_name'], emp['last_name'], mosys_id),
                    )
                    added += 1
        return {'added': added, 'updated': updated}
```

---

## 6. Auth Service — services/auth/auth_service.py

```python
from typing import Tuple, Optional
from database.models import User
from repositories.users.user_repository import UserRepository

class AuthService:
    def __init__(self, user_repo: UserRepository):
        self.user_repo = user_repo

    def authenticate(self, email: str, password: str) -> Tuple[bool, Optional[User], Optional[str]]:
        """Email-based login (fallback — primary login is by employee ID)."""
        user = self.user_repo.get_by_email(email)
        if not user:
            return False, None, "Nieprawidłowy e-mail lub hasło"
        if not user.is_active:
            return False, None, "Konto jest nieaktywne. Skontaktuj się z administratorem."
        if not self.user_repo.verify_password(user, password):
            return False, None, "Nieprawidłowy e-mail lub hasło"
        self.user_repo.update_last_login(user.id)
        return True, user, None

    def authenticate_by_employee_id(self, mosys_employee_id: str, password: str) -> Tuple[bool, Optional[User], Optional[str]]:
        """Primary login — looks up user via employees.mosys_employee_id."""
        user = self.user_repo.get_by_mosys_employee_id(mosys_employee_id.strip())
        if not user:
            return False, None, "Nieprawidłowy nr pracownika lub hasło"
        if not user.is_active:
            return False, None, "Konto jest nieaktywne. Skontaktuj się z administratorem."
        if not self.user_repo.verify_password(user, password):
            return False, None, "Nieprawidłowy nr pracownika lub hasło"
        self.user_repo.update_last_login(user.id)
        return True, user, None

    def change_password(self, user_id: int, old_password: str, new_password: str) -> Tuple[bool, Optional[str]]:
        row = self.user_repo.get_by_id(user_id)
        if not row:
            return False, "Użytkownik nie istnieje"
        user = self.user_repo.row_to_user(row)
        if not self.user_repo.verify_password(user, old_password):
            return False, "Nieprawidłowe aktualne hasło"
        if len(new_password) < 8:
            return False, "Hasło musi mieć co najmniej 8 znaków"
        self.user_repo.update_password(user_id, new_password)
        return True, None
```

---

## 7. App Factory — app.py

```python
import os
from flask import Flask
from flask_login import LoginManager
from dotenv import load_dotenv

load_dotenv()
login_manager = LoginManager()


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

    from database.db import initialize_database
    initialize_database()

    # Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Musisz być zalogowany, aby uzyskać dostęp do tej strony.'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        try:
            from repositories.users.user_repository import UserRepository
            repo = UserRepository()
            row = repo.get_by_id(int(user_id))
            return repo.row_to_user(row) if row else None
        except Exception:
            return None

    # Register blueprints
    from routes.main_routes import main_bp
    from routes.api_routes import api_bp
    from routes.auth.routes import auth_bp
    from routes.users.routes import users_bp
    from routes.roles.routes import roles_bp
    from routes.employees.routes import employees_bp
    from routes.audit.routes import audit_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(roles_bp)
    app.register_blueprint(employees_bp)
    app.register_blueprint(audit_bp)

    @app.context_processor
    def inject_globals():
        from datetime import datetime
        from flask_login import current_user
        from config.auth_config import get_user_module_permissions

        user_permissions = {}
        if current_user.is_authenticated:
            try:
                user_permissions = get_user_module_permissions(current_user.role)
            except Exception:
                pass

        # Expose current user's MOSYS employee ID for the scanner view
        current_mosys_employee_id = None
        if current_user.is_authenticated:
            try:
                from repositories.users.user_repository import UserRepository
                emp = UserRepository().get_employee_for_user(current_user.id)
                current_mosys_employee_id = emp['mosys_employee_id'] if emp else None
            except Exception:
                pass

        return {
            'now': datetime.now,
            'app_version': '1.0.0',
            'app_name': 'DMC Validator',
            'user_permissions': user_permissions,          # {module: bool} in every template
            'current_mosys_employee_id': current_mosys_employee_id,
        }

    return app
```

---

## 8. Auth Routes — routes/auth/routes.py

### Blueprint setup

```python
import secrets
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from repositories.users.user_repository import UserRepository
from services.auth.auth_service import AuthService
from database.db import get_connection, log_event

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')
_user_repo = UserRepository()
_auth_service = AuthService(_user_repo)
```

### Login (mosys_employee_id-based, with first-login redirect)

```python
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    employee_id = ''
    if request.method == 'POST':
        employee_id = request.form.get('employee_id', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        ok, user, error = _auth_service.authenticate_by_employee_id(employee_id, password)
        if ok:
            login_user(user, remember=remember)
            log_event('login_ok', user_id=user.id, user_email=user.email,
                      user_name=user.full_name, ip_address=request.remote_addr)
            if user.must_change_password:
                return redirect(url_for('auth.set_first_password'))  # force password setup
            next_page = request.args.get('next')
            return redirect(next_page or url_for('main.index'))

        log_event('login_failed', detail=f"employee_id={employee_id}: {error}",
                  ip_address=request.remote_addr)
        flash(error, 'error')

    login_employees = _user_repo.get_login_employees()
    return render_template('auth/login.html', employee_id=employee_id,
                           login_employees=login_employees)
```

### First-login check API (called by JS on the login page)

```python
@auth_bp.route('/api/needs-setup')
def api_needs_setup():
    """Returns {needs_setup: bool} — polled by JS when 4 digits typed in login form."""
    mosys_id = request.args.get('mosys_id', '').strip()
    if not mosys_id:
        return jsonify({'needs_setup': False})
    user = _user_repo.get_by_mosys_employee_id(mosys_id)
    if user and user.is_active and user.must_change_password:
        return jsonify({'needs_setup': True, 'full_name': user.full_name})
    return jsonify({'needs_setup': False})
```

### First-login form submission (no session required — happens before full login)

```python
@auth_bp.route('/first-login', methods=['POST'])
def first_login():
    mosys_id = request.form.get('mosys_id', '').strip()
    new_pw = request.form.get('new_password', '')
    confirm = request.form.get('confirm_password', '')

    user = _user_repo.get_by_mosys_employee_id(mosys_id)
    if not user or not user.is_active or not user.must_change_password:
        flash('Nieprawidłowe żądanie zmiany hasła.', 'error')
        return redirect(url_for('auth.login'))

    if len(new_pw) < 8:
        flash('Hasło musi mieć co najmniej 8 znaków.', 'error')
        return redirect(url_for('auth.login'))
    if new_pw != confirm:
        flash('Hasła nie są identyczne.', 'error')
        return redirect(url_for('auth.login'))

    _user_repo.update_password(user.id, new_pw)
    _user_repo.clear_must_change_password(user.id)
    login_user(user)  # log them in after password is set
    log_event('password_set_first', user_id=user.id, user_email=user.email,
              user_name=user.full_name, ip_address=request.remote_addr)
    flash('Hasło zostało ustawione. Witaj w systemie!', 'success')
    return redirect(url_for('main.index'))
```

### Set first password (if user already logged in but must_change_password=True)

```python
@auth_bp.route('/set-first-password', methods=['GET', 'POST'])
@login_required
def set_first_password():
    if not current_user.must_change_password:
        return redirect(url_for('main.index'))

    if request.method == 'POST':
        new_pw = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        if len(new_pw) < 8:
            flash('Hasło musi mieć co najmniej 8 znaków', 'error')
        elif new_pw != confirm:
            flash('Hasła nie są identyczne', 'error')
        else:
            _user_repo.update_password(current_user.id, new_pw)
            _user_repo.clear_must_change_password(current_user.id)
            log_event('password_set_first', user_id=current_user.id,
                      user_email=current_user.email, user_name=current_user.full_name,
                      ip_address=request.remote_addr)
            flash('Hasło zostało ustawione. Witaj w systemie!', 'success')
            return redirect(url_for('main.index'))

    return render_template('auth/set_first_password.html')
```

### Logout

```python
@auth_bp.route('/logout')
@login_required
def logout():
    log_event('logout', user_id=current_user.id, user_email=current_user.email,
              user_name=current_user.full_name, ip_address=request.remote_addr)
    logout_user()
    flash('Wylogowano pomyślnie', 'success')
    return redirect(url_for('auth.login'))
```

### Forgot / Reset password (on-screen token, no email)

```python
@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    reset_url = None
    if request.method == 'POST':
        mosys_id = request.form.get('mosys_employee_id', '').strip()
        user = _user_repo.get_by_mosys_employee_id(mosys_id)
        if user:
            with get_connection() as conn:
                conn.execute("UPDATE password_reset_tokens SET used=1 WHERE user_id=? AND used=0", (user.id,))
                token = secrets.token_urlsafe(32)
                expires_at = datetime.now() + timedelta(hours=1)
                conn.execute(
                    "INSERT INTO password_reset_tokens (user_id, token, expires_at) VALUES (?,?,?)",
                    (user.id, token, expires_at),
                )
            reset_url = url_for('auth.reset_password', token=token, _external=True)
        # Always the same message — prevents user enumeration
        flash('Jeśli nr pracownika istnieje w systemie, link jest widoczny poniżej.', 'info')
    return render_template('auth/forgot_password.html', reset_url=reset_url)


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token: str):
    with get_connection() as conn:
        token_row = conn.execute(
            "SELECT * FROM password_reset_tokens "
            "WHERE token=? AND used=0 AND expires_at > datetime('now','localtime')",
            (token,),
        ).fetchone()

    if not token_row:
        flash('Link wygasł lub został już wykorzystany.', 'error')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        if len(new_password) < 8:
            flash('Hasło musi mieć co najmniej 8 znaków', 'error')
        elif new_password != confirm:
            flash('Hasła nie są identyczne', 'error')
        else:
            _user_repo.update_password(token_row['user_id'], new_password)
            with get_connection() as conn:
                conn.execute("UPDATE password_reset_tokens SET used=1 WHERE token=?", (token,))
            flash('Hasło zostało zmienione. Możesz się teraz zalogować.', 'success')
            return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token)
```

---

## 9. Users Routes — routes/users/routes.py

```python
import secrets
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from config.auth_config import role_required
from repositories.users.user_repository import UserRepository
from repositories.roles.role_repository import RoleRepository
from database.db import log_event

users_bp = Blueprint('users', __name__, url_prefix='/system/users')
_user_repo = UserRepository()
_role_repo = RoleRepository()


@users_bp.route('/')
@login_required
@role_required('superuser')
def users_list():
    return render_template('users/list.html')


@users_bp.route('/create')
@login_required
@role_required('superuser')
def create_user():
    roles = _role_repo.get_all()
    available_employees = [dict(e) for e in _user_repo.get_available_employees()]
    return render_template('users/create.html', roles=roles, available_employees=available_employees)


@users_bp.route('/<int:user_id>/edit')
@login_required
@role_required('superuser')
def edit_user(user_id: int):
    user_row = _user_repo.get_by_id(user_id)
    if not user_row:
        flash('Użytkownik nie istnieje', 'error')
        return redirect(url_for('users.users_list'))
    # Superuser cannot be edited by another superuser (only by themselves)
    if user_row['role'] == 'superuser' and current_user.id != user_id:
        flash('Nie możesz edytować konta właściciela', 'error')
        return redirect(url_for('users.users_list'))
    roles = _role_repo.get_all()
    available_employees = _user_repo.get_available_employees()
    current_employee = _user_repo.get_employee_for_user(user_id)
    return render_template('users/edit.html', user=user_row, roles=roles,
                           available_employees=available_employees,
                           current_employee=current_employee)


# ── API ──────────────────────────────────────────────────────────────────────

@users_bp.route('/api', methods=['GET'])
@login_required
@role_required('superuser')
def api_list():
    rows = _user_repo.get_all_with_employee()
    users = []
    for r in rows:
        emp_name = f"{r['employee_first_name']} {r['employee_last_name']}" if r['employee_first_name'] else None
        users.append({
            'id': r['id'], 'email': r['email'], 'full_name': r['full_name'],
            'role': r['role'], 'is_active': bool(r['is_active']),
            'last_login': r['last_login'], 'created_at': r['created_at'],
            'employee_id': r['employee_id'],
            'employee_mosys_id': r['employee_mosys_id'],
            'employee_name': emp_name,
        })
    return jsonify({'users': users, 'count': len(users)})


@users_bp.route('/api', methods=['POST'])
@login_required
@role_required('superuser')
def api_create():
    data = request.get_json() or {}
    mosys_employee_id = data.get('mosys_employee_id', '').strip()
    full_name = data.get('full_name', '').strip()
    role = data.get('role', '')
    employee_id = data.get('employee_id')

    if not all([mosys_employee_id, full_name, role]):
        return jsonify({'success': False, 'error': 'Wszystkie pola są wymagane'}), 400

    email = f"{mosys_employee_id}@dmc.local"       # auto-generated, never shown to user
    temp_password = secrets.token_urlsafe(12)       # user will change on first login

    try:
        user_id = _user_repo.create_user(email, temp_password, full_name, role,
                                         must_change_password=True)
        if employee_id:
            _user_repo.link_employee(int(employee_id), user_id)
        log_event('user_create', user_id=current_user.id, user_email=current_user.email,
                  user_name=current_user.full_name, entity_type='user', entity_id=user_id,
                  detail=f'nr {mosys_employee_id} ({full_name})', ip_address=request.remote_addr)
        return jsonify({'success': True, 'user_id': user_id}), 201
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        if 'UNIQUE' in str(e):
            return jsonify({'success': False, 'error': 'Ten numer pracownika jest już zajęty'}), 409
        return jsonify({'success': False, 'error': 'Błąd tworzenia użytkownika'}), 500


@users_bp.route('/api/<int:user_id>', methods=['PUT'])
@login_required
@role_required('superuser')
def api_update(user_id: int):
    existing = _user_repo.get_by_id(user_id)
    if not existing:
        return jsonify({'success': False, 'error': 'Użytkownik nie istnieje'}), 404
    if existing['role'] == 'superuser' and current_user.id != user_id:
        return jsonify({'success': False, 'error': 'Nie możesz edytować konta właściciela'}), 403

    data = request.get_json() or {}
    full_name = data.get('full_name', '').strip()
    role = data.get('role', '')
    is_active = bool(data.get('is_active', True))
    employee_id = data.get('employee_id')

    if not all([full_name, role]):
        return jsonify({'success': False, 'error': 'Wymagane pola są puste'}), 400

    try:
        _user_repo.unlink_employee(user_id)
        _user_repo.update_user(user_id, full_name, role, is_active)
        if employee_id:
            _user_repo.link_employee(int(employee_id), user_id)
        log_event('user_update', user_id=current_user.id, user_email=current_user.email,
                  user_name=current_user.full_name, entity_type='user', entity_id=user_id,
                  detail=full_name, ip_address=request.remote_addr)
        return jsonify({'success': True})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        return jsonify({'success': False, 'error': 'Błąd aktualizacji użytkownika'}), 500


@users_bp.route('/api/<int:user_id>/toggle-active', methods=['PUT'])
@login_required
@role_required('superuser')
def api_toggle_active(user_id: int):
    if user_id == current_user.id:
        return jsonify({'success': False, 'error': 'Nie możesz dezaktywować swojego konta'}), 400
    try:
        new_state = _user_repo.toggle_active(user_id)
        log_event('user_toggle_active', user_id=current_user.id, user_email=current_user.email,
                  user_name=current_user.full_name, entity_type='user', entity_id=user_id,
                  detail=f'active={new_state}', ip_address=request.remote_addr)
        return jsonify({'success': True, 'is_active': new_state})
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 404


@users_bp.route('/api/<int:user_id>/reset-password', methods=['POST'])
@login_required
@role_required('superuser')
def api_reset_password(user_id: int):
    data = request.get_json() or {}
    new_password = data.get('password', '')
    if len(new_password) < 8:
        return jsonify({'success': False, 'error': 'Hasło musi mieć co najmniej 8 znaków'}), 400
    _user_repo.update_password(user_id, new_password)
    log_event('user_password_reset', user_id=current_user.id, user_email=current_user.email,
              user_name=current_user.full_name, entity_type='user', entity_id=user_id,
              ip_address=request.remote_addr)
    return jsonify({'success': True})
```

---

## 10. Roles Routes — routes/roles/routes.py

```python
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from config.auth_config import role_required
from repositories.roles.role_repository import RoleRepository, ALL_MODULES, MODULE_DISPLAY_NAMES
from database.db import log_event
import re

roles_bp = Blueprint('roles', __name__, url_prefix='/system/roles')
_role_repo = RoleRepository()


@roles_bp.route('/')
@login_required
@role_required('superuser')
def roles_list():
    return render_template('roles/list.html')


@roles_bp.route('/create')
@login_required
@role_required('superuser')
def create_role():
    return render_template('roles/create.html',
                           all_modules=ALL_MODULES, module_display_names=MODULE_DISPLAY_NAMES)


@roles_bp.route('/<int:role_id>/edit')
@login_required
@role_required('superuser')
def edit_role(role_id: int):
    role = _role_repo.get_by_id(role_id)
    if not role:
        flash('Rola nie istnieje', 'error')
        return redirect(url_for('roles.roles_list'))
    permissions = _role_repo.get_permissions(role_id)
    return render_template('roles/edit.html', role=role, permissions=permissions,
                           all_modules=ALL_MODULES, module_display_names=MODULE_DISPLAY_NAMES)


@roles_bp.route('/api', methods=['GET'])
@login_required
@role_required('superuser')
def api_list():
    rows = _role_repo.get_all()
    roles = [{
        'id': r['id'], 'name': r['name'], 'display_name': r['display_name'],
        'is_protected': bool(r['is_protected']),
        'permissions': _role_repo.get_permissions(r['id']),
        'access_count': r['access_count'],
    } for r in rows]
    return jsonify({'roles': roles})


@roles_bp.route('/api', methods=['POST'])
@login_required
@role_required('superuser')
def api_create():
    data = request.get_json() or {}
    name = data.get('name', '').strip().lower()
    display_name = data.get('display_name', '').strip()
    permissions = data.get('permissions', {})

    if not name or not display_name:
        return jsonify({'success': False, 'error': 'Nazwa i wyświetlana nazwa są wymagane'}), 400
    if not re.match(r'^[a-z_]+$', name):
        return jsonify({'success': False, 'error': 'Nazwa może zawierać tylko małe litery i podkreślenia'}), 400

    try:
        role_id = _role_repo.create(name, display_name)
        _role_repo.set_permissions(role_id, permissions)
        log_event('role_create', user_id=current_user.id, user_email=current_user.email,
                  user_name=current_user.full_name, entity_type='role', entity_id=role_id,
                  detail=name, ip_address=request.remote_addr)
        return jsonify({'success': True, 'role_id': role_id}), 201
    except Exception as e:
        if 'UNIQUE' in str(e):
            return jsonify({'success': False, 'error': 'Rola o tej nazwie już istnieje'}), 409
        return jsonify({'success': False, 'error': 'Błąd tworzenia roli'}), 500


@roles_bp.route('/api/<int:role_id>', methods=['PUT'])
@login_required
@role_required('superuser')
def api_update(role_id: int):
    role = _role_repo.get_by_id(role_id)
    if not role:
        return jsonify({'success': False, 'error': 'Rola nie istnieje'}), 404

    data = request.get_json() or {}
    display_name = data.get('display_name', '').strip()
    permissions = data.get('permissions', {})

    if not display_name:
        return jsonify({'success': False, 'error': 'Wyświetlana nazwa jest wymagana'}), 400

    _role_repo.update(role_id, display_name)
    _role_repo.set_permissions(role_id, permissions)
    log_event('role_update', user_id=current_user.id, user_email=current_user.email,
              user_name=current_user.full_name, entity_type='role', entity_id=role_id,
              detail=display_name, ip_address=request.remote_addr)
    return jsonify({'success': True})


@roles_bp.route('/api/<int:role_id>', methods=['DELETE'])
@login_required
@role_required('superuser')
def api_delete(role_id: int):
    deleted = _role_repo.delete(role_id)
    if not deleted:
        return jsonify({'success': False, 'error': 'Nie można usunąć chronionej lub nieistniejącej roli'}), 400
    log_event('role_delete', user_id=current_user.id, user_email=current_user.email,
              user_name=current_user.full_name, entity_type='role', entity_id=role_id,
              ip_address=request.remote_addr)
    return jsonify({'success': True})
```

---

## 11. Employees Routes — routes/employees/routes.py

Follows identical pattern to users/roles: page routes + JSON API.
Key endpoint: `POST /system/employees/api/sync-mosys` — fetches from STAAMPDB.OPERATORI
and calls `_emp_repo.sync_from_mosys()`.

```python
employees_bp = Blueprint('employees', __name__, url_prefix='/system/employees')

@employees_bp.route('/api/sync-mosys', methods=['POST'])
@login_required
@role_required('superuser')
def api_sync_mosys():
    from services.mosys_service import get_all_employees
    try:
        mosys_employees = get_all_employees()
    except Exception as e:
        return jsonify({'success': False, 'error': f'Błąd połączenia z MOSYS: {e}'}), 503

    result = _emp_repo.sync_from_mosys(mosys_employees)
    log_event('employee_sync_mosys', user_id=current_user.id, user_email=current_user.email,
              user_name=current_user.full_name,
              detail=f"added={result['added']}, updated={result['updated']}, total={len(mosys_employees)}",
              ip_address=request.remote_addr)
    return jsonify({'success': True, **result, 'total_mosys': len(mosys_employees)})
```

### MOSYS service — services/mosys_service.py

```python
def get_all_employees() -> list[dict]:
    """
    Fetch operators from MOSYS STAAMPDB.OPERATORI where CODICE LIKE '9%'.
    Returns list of {mosys_id, last_name, first_name, full_name}.
    DENOMINAZIONE stored as "COGNOME NOME" (surname first).
    """
    query = "SELECT CODICE, DENOMINAZIONE FROM STAAMPDB.OPERATORI WHERE CODICE LIKE ?"
    rows = _get_pervasive(query, ("9%",))   # Pervasive ODBC connection
    result = []
    for row in rows:
        code = str(row.get("CODICE", "")).strip()
        denom = str(row.get("DENOMINAZIONE", "")).strip()
        if not code:
            continue
        parts = denom.split(" ", 1)
        last_name = parts[0].title() if parts else denom
        first_name = parts[1].title() if len(parts) > 1 else ""
        result.append({'mosys_id': code, 'last_name': last_name,
                       'first_name': first_name, 'full_name': denom})
    return result
```

---

## 12. Audit Routes — routes/audit/routes.py

```python
audit_bp = Blueprint('audit', __name__, url_prefix='/system/audit')

@audit_bp.route('/')
@login_required
@module_permission_required('audit')   # NOT role_required — uses module system
def audit_list():
    events = [...]  # merge audit_log + dmc_bypass_log, sort by occurred_at DESC
    return render_template('audit/list.html', events=events)
```

**Event type constants** (used in `EVENT_LABELS` and `EVENT_CLASSES`):
```
login_ok, login_failed, logout, password_changed, password_set_first
employee_create, employee_update, employee_delete, employee_sync_mosys
user_create, user_update, user_toggle_active, user_password_reset
role_create, role_update, role_delete
```

**Badge CSS classes**: `badge-ok` (green), `badge-nok` (red), `badge-na` (grey)

---

## 13. Templates

### Design System Constants (shared by all templates)

```css
:root {
    --color-accent:       #c9a227;   /* golden yellow — buttons, focus rings */
    --color-border:       #e8e6e1;
    --color-ink:          #1a1a1a;
    --color-ink-muted:    #525252;
    --color-ink-subtle:   #8a8a8a;
    --color-surface-warm: #f7f6f3;   /* page background */
    --sidebar-bg:         #0f172a;   /* dark navy */
    --sidebar-text-active:#60a5fa;
    --sidebar-active-bg:  rgba(37,99,235,0.2);
}
```

All auth pages: `html { zoom: 1.4; }` — optimized for industrial touch screens.

### 13a. auth/login.html — Standalone (NO {% extends %})

The login page has **two forms** in one HTML — JS switches between them:

```html
<!DOCTYPE html>
<html lang="pl" class="h-full">
<head>
    <!-- No {% extends %} — standalone page -->
    <link rel="stylesheet" href="{{ url_for('static', filename='css/output.css') }}">
    <style>html { zoom: 1.4; }</style>
</head>
<body class="h-full flex items-center justify-center">
<div style="max-width:400px;width:100%;margin:0 1rem;">

    <!-- ── Regular login form ── -->
    <form id="login-form" method="POST" action="{{ url_for('auth.login') }}">
        <input type="text" id="employee_id" name="employee_id"
               inputmode="numeric" maxlength="4" placeholder="0000"
               list="employees-list">   <!-- datalist with known employees -->
        <datalist id="employees-list">
            {% for emp in login_employees %}
            <option value="{{ emp['mosys_employee_id'] }}">{{ emp['full_name'] }}</option>
            {% endfor %}
        </datalist>
        <input type="password" id="password" name="password">
        <input type="checkbox" name="remember"> Zapamiętaj mnie
        <button type="submit">Zaloguj się</button>
    </form>

    <!-- ── First-login form (hidden) — shown by JS when needs-setup=true ── -->
    <form id="first-login-form" method="POST" action="{{ url_for('auth.first_login') }}"
          style="display:none;">
        <input type="hidden" name="mosys_id" id="fl-mosys-id">
        <div id="fl-name"></div>  <!-- employee full name shown here -->
        <input type="password" name="new_password" id="fl-new-password" minlength="8">
        <input type="password" name="confirm_password" id="fl-confirm-password">
        <button type="submit">Ustaw hasło i zaloguj</button>
        <button type="button" id="fl-back-btn">← Wróć</button>
    </form>

</div>
<script>
// When 4 digits typed → check /auth/api/needs-setup
// If needs_setup → switch to first-login form
// If not → show regular login with focus on password field
empInput.addEventListener('input', function () {
    this.value = this.value.replace(/\D/g, '').slice(0, 4);
    if (this.value.length === 4) {
        fetch('/auth/api/needs-setup?mosys_id=' + encodeURIComponent(this.value))
            .then(r => r.json())
            .then(data => {
                if (data.needs_setup) {
                    flMosysId.value = this.value;
                    flName.textContent = data.full_name || ('Nr ' + this.value);
                    loginForm.style.display = 'none';
                    flForm.style.display = 'flex';
                    flNewPw.focus();
                } else {
                    loginForm.style.display = 'flex';
                    pwInput.focus();
                }
            });
    }
});
</script>
</body>
</html>
```

### 13b. auth/set_first_password.html — Standalone (for @login_required path)

Same standalone structure as login.html. Simple two-field form (new_password + confirm_password),
no employee ID needed since user is already in session.

### 13c. users/list.html — extends base.html, API-driven table

```html
{% extends "base.html" %}
{% block content %}
<div class="refined-page">
    <div class="page-header">
        <!-- search input + "Nowy użytkownik" link -->
    </div>
    <div class="table-container">
        <table class="refined-table" id="users-table" style="display:none;">
            <!-- columns: Imię i nazwisko | Rola | Nr prac. | Status | Ostatnie logowanie | [actions] -->
        </table>
    </div>
</div>

<!-- Reset password modal (inline HTML, JS-controlled) -->
{% endblock %}

{% block extra_scripts %}
<script>
async function loadUsers() {
    const data = await fetch('{{ url_for("users.api_list") }}').then(r=>r.json());
    // render rows with escHtml() for XSS safety
    // toggleActive() → PUT /api/<id>/toggle-active
    // openResetPwModal() → modal → POST /api/<id>/reset-password
}
loadUsers();
</script>
{% endblock %}
```

**Key JS patterns**:
- `escHtml(str)` — XSS-safe HTML escaping for all user-supplied strings rendered in `innerHTML`
- All mutations via `fetch()` JSON — never form POST
- `loadUsers()` called on page load + after each mutation to refresh table state

### 13d. users/create.html — extends base.html, MOSYS ID lookup

Flow: type 4-digit MOSYS ID → JS checks if ID is in `available_employees` list (server-rendered JSON) →
auto-fills full name field → enables submit button.

```html
<input type="text" id="mosys_employee_id" inputmode="numeric" maxlength="4">
<input type="text" id="full_name" readonly>  <!-- auto-filled from JS lookup -->
<select id="role">{% for role in roles %}<option>...</option>{% endfor %}</select>
<input type="hidden" id="employee_id">       <!-- employee.id, not mosys_id -->
```

```javascript
const EMPLOYEES = {};  // {mosys_id: {db_id, name}} built from {{ available_employees | tojson }}
// On 4-digit input → look up in EMPLOYEES → fill name, enable submit
// Submit → POST JSON to {{ url_for("users.api_create") }}
// Payload: {mosys_employee_id, full_name, role, employee_id (int or null)}
```

### 13e. roles/list.html — extends base.html, dot-matrix permission display

```javascript
const MODULE_LABELS = {dmc_validation: 'Skaner DMC', history: 'Historia', ...};

// Each role row shows colored dot per module (green=has access, grey=no access)
const moduleDots = Object.entries(r.permissions).map(([mod, on]) =>
    `<span title="${MODULE_LABELS[mod]}"
           style="display:inline-block;width:9px;height:9px;border-radius:50%;
           background:${on ? '#22c55e' : '#d1d5db'}"></span>`
).join('');
```

### 13f. roles/create.html and roles/edit.html — toggle-switch UX

```css
.toggle { position:relative;display:inline-block;width:40px;height:22px; }
.toggle input { opacity:0;width:0;height:0; }
.toggle-slider { position:absolute;inset:0;background:#d1d5db;border-radius:11px; }
.toggle-slider::before { /* circle knob */ }
input:checked + .toggle-slider { background:var(--color-accent); }
input:checked + .toggle-slider::before { transform:translateX(18px); }
```

```html
{% for module in all_modules %}
<div class="module-row">
    <div>
        <div>{{ module_display_names[module] }}</div>
        <div style="font-family:monospace;font-size:.7rem;">{{ module }}</div>
    </div>
    <label class="toggle">
        <!-- edit.html adds: {% if permissions[module] %}checked{% endif %} -->
        <input type="checkbox" id="perm_{{ module }}">
        <span class="toggle-slider"></span>
    </label>
</div>
{% endfor %}
```

Submit collects `{module: checkbox.checked}` and sends to `POST /api` (create) or `PUT /api/<id>` (edit).

### 13g. Sidebar nav permission gates (base.html)

The context processor injects `user_permissions` = `{module_name: bool}` into every template.

```jinja2
{% if user_permissions.dmc_validation %}
    <!-- show scanner nav link -->
{% endif %}

{% if user_permissions.admin %}
    <!-- show system section -->
    <a href="{{ url_for('users.users_list') }}">Użytkownicy</a>
    <a href="{{ url_for('roles.roles_list') }}">Role</a>
    <a href="{{ url_for('employees.employees_list') }}">Pracownicy</a>
{% endif %}

{% if user_permissions.audit %}
    <a href="{{ url_for('audit.audit_list') }}">Dziennik zdarzeń</a>
{% endif %}
```

---

## 14. Audit Event Types Reference

| event_type | Trigger | badge CSS class |
|------------|---------|----------------|
| `login_ok` | Successful login | `badge-ok` |
| `login_failed` | Failed login attempt | `badge-nok` |
| `logout` | User logged out | `badge-na` |
| `password_changed` | Self-service password change | `badge-na` |
| `password_set_first` | First login password set | `badge-na` |
| `user_create` | Admin created user | `badge-ok` |
| `user_update` | Admin edited user | `badge-na` |
| `user_toggle_active` | Admin activated/deactivated account | `badge-na` |
| `user_password_reset` | Admin reset a user's password | `badge-na` |
| `employee_create` | Admin created employee | `badge-ok` |
| `employee_update` | Admin edited employee | `badge-na` |
| `employee_delete` | Admin deleted employee | `badge-nok` |
| `employee_sync_mosys` | Sync from MOSYS OPERATORI table | `badge-ok` |
| `role_create` | Admin created role | `badge-ok` |
| `role_update` | Admin edited role permissions | `badge-na` |
| `role_delete` | Admin deleted role | `badge-nok` |

---

## 15. MOSYS / OPERATORI Integration

The company Pervasive PSQL database (ODBC) contains production data.
Only `CODICE LIKE '9%'` entries are production operators who get app accounts.

```
STAAMPDB.OPERATORI
  CODICE        → employees.mosys_employee_id  (4-digit string, e.g. "9015")
  DENOMINAZIONE → "COGNOME NOME" split to employees.last_name / first_name
```

**Sync flow** (admin triggers via UI):
1. `POST /system/employees/api/sync-mosys`
2. → `get_all_employees()` in mosys_service.py (ODBC query)
3. → `EmployeeRepository.sync_from_mosys()` (upsert by mosys_employee_id)
4. → `log_event('employee_sync_mosys', ...)`

**Login flow** after sync:
1. Admin goes to `/system/users/create`
2. Types employee's MOSYS ID (4 digits)
3. JS finds employee in `available_employees` list (already synced)
4. Auto-fills name, enables submit
5. User account created with `must_change_password=True` and random temp password
6. Employee record linked via `employees.user_id = user.id`
7. On first login: JS detects `needs_setup=True`, shows first-login form
8. Employee sets permanent password → `must_change_password=0`

---

## 16. Seed Script — scripts/seed_users.py

```python
"""Dev/staging seed — creates default accounts. Run: python scripts/seed_users.py"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import initialize_database
from repositories.users.user_repository import UserRepository

initialize_database()

TEST_USERS = [
    {'email': 'owner@dmc.local',    'password': 'Super123!', 'full_name': 'Właściciel',    'role': 'superuser'},
    {'email': 'operator@dmc.local', 'password': 'Oper123!',  'full_name': 'Operator Zmiany', 'role': 'operator'},
]

repo = UserRepository()
for u in TEST_USERS:
    if not repo.get_by_email(u['email']):
        repo.create_user(**u)
        print(f"Utworzono: {u['email']} (rola: {u['role']})")
    else:
        print(f"Istnieje:  {u['email']}")
```

Note: seed users use direct email login (via `authenticate()`), not mosys_employee_id login,
because they are not linked to employee records. Used for dev only.

---

## 17. Requirements (relevant RBAC subset)

```
Flask==3.1.x
Flask-Login==0.6.x
bcrypt==4.x
python-dotenv
```

No Alembic — schema is managed inline in `db.py` with `CREATE TABLE IF NOT EXISTS` + safe `ALTER TABLE` migrations.

---

## 18. Implementation Order for a New Project

1. `config/settings.py` — `DATABASE_PATH`, env vars
2. `database/models.py` — `User(UserMixin)`, `Employee` dataclasses
3. `database/db.py` — `get_connection()`, `initialize_database()`, `_seed_roles_and_permissions()`, `log_event()`
4. `repositories/roles/role_repository.py` — define `ALL_MODULES`, `MODULE_DISPLAY_NAMES`, `RoleRepository`
5. `repositories/users/user_repository.py` — `UserRepository` with bcrypt
6. `repositories/employees/employee_repository.py` — `EmployeeRepository` with `sync_from_mosys()`
7. `services/auth/auth_service.py` — `authenticate_by_employee_id()`, `change_password()`
8. `config/auth_config.py` — `MODULE_PERMISSIONS`, `role_required`, `module_permission_required`, `get_user_module_permissions`
9. `app.py` — factory, `LoginManager`, `user_loader`, `context_processor`, register blueprints
10. `routes/auth/routes.py` — login, first_login, api_needs_setup, set_first_password, logout, forgot/reset
11. `routes/users/routes.py` — page routes + 6 API endpoints
12. `routes/roles/routes.py` — page routes + 5 API endpoints
13. `routes/employees/routes.py` — page routes + 5 API endpoints + sync-mosys
14. `routes/audit/routes.py` — single list view
15. Templates: `auth/login.html` → `auth/set_first_password.html` → `users/*` → `roles/*` → `employees/*` → `audit/list.html`
16. `scripts/seed_users.py` — dev seed

---

## 19. Critical Invariants — Never Break These

1. **`_validate_role()` on every user create/update** — prevents orphan role strings in users table
2. **`must_change_password=True` on every admin-created user** — forces self-service password setup
3. **Email auto-generated as `{mosys_id}@dmc.local`** — never exposed to UI, never user-supplied
4. **`bcrypt.hashpw()` on every password write** — use `user_repo.update_password()`, never raw SQL INSERT
5. **`log_event()` in try/except** — audit failures must never crash the main request
6. **`sqlite3.Row` as `row_factory`** — mandatory for `row['column']` dict access
7. **`is_protected=1` roles cannot be deleted** — enforced at DELETE endpoint with `AND is_protected=0`
8. **`escHtml(str)`** in all JS `innerHTML` rendering — prevents XSS from user-supplied names/emails
9. **`datetime('now','localtime')`** for token expiry check — NOT `datetime('now')` which is UTC
10. **Superuser protection** — `users_bp` edit/update blocks editing another superuser's account
