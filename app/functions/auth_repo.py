"""RBAC data access: the User model + repositories for users/roles/employees.

Sits on top of ``auth_db.get_connection()``. Bcrypt hashing lives here (never
in routes). Mirrors the read/write shape already used by
``app.functions.mosys`` (small focused functions, ``sqlite3.Row`` dict access)
rather than the golden book's separate-package-per-repo layout, since this
project keeps related concerns in one module under ``app/functions/``.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import bcrypt
from flask_login import UserMixin

from app.functions import auth_db


@dataclass
class User(UserMixin):
    email: str
    password_hash: str
    full_name: str
    role: str = 'operator'
    is_active: bool = True
    must_change_password: bool = False
    id: Optional[int] = None
    last_login: Optional[str] = None
    created_at: Optional[str] = field(default_factory=lambda: None)
    updated_at: Optional[str] = field(default_factory=lambda: None)

    def get_id(self):
        return str(self.id)

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False


class UserRepository:

    _columns = ('id, email, password_hash, full_name, role, is_active, '
                'must_change_password, last_login, created_at, updated_at')

    def _validate_role(self, conn, role: str):
        row = conn.execute("SELECT 1 FROM roles WHERE name = ?", (role,)).fetchone()
        if not row:
            raise ValueError(f"Role '{role}' does not exist")

    def _row_to_user(self, row: Any) -> Optional[User]:
        if row is None:
            return None
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
        conn = auth_db.get_connection()
        try:
            self._validate_role(conn, role)
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            cursor = conn.execute(
                "INSERT INTO users (email, password_hash, full_name, role, must_change_password) "
                "VALUES (?, ?, ?, ?, ?)",
                (email.strip().lower(), password_hash, full_name.strip(),
                 role, int(must_change_password)),
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_by_id(self, user_id: int) -> Optional[User]:
        conn = auth_db.get_connection()
        try:
            row = conn.execute(f"SELECT {self._columns} FROM users WHERE id = ?", (user_id,)).fetchone()
        finally:
            conn.close()
        return self._row_to_user(row)

    def get_by_mosys_employee_id(self, mosys_id: str) -> Optional[User]:
        cols = ', '.join(f'u.{c.strip()}' for c in self._columns.split(','))
        conn = auth_db.get_connection()
        try:
            row = conn.execute(
                f"SELECT {cols} FROM users u "
                "INNER JOIN employees e ON e.user_id = u.id "
                "WHERE e.mosys_employee_id = ?",
                (mosys_id,),
            ).fetchone()
        finally:
            conn.close()
        return self._row_to_user(row)

    def get_all_with_employee(self) -> list:
        conn = auth_db.get_connection()
        try:
            return conn.execute("""
                SELECT u.id, u.email, u.full_name, u.role, u.is_active,
                       u.last_login, u.created_at,
                       e.id AS employee_id, e.mosys_employee_id AS employee_mosys_id
                FROM users u LEFT JOIN employees e ON e.user_id = u.id
                ORDER BY u.full_name
            """).fetchall()
        finally:
            conn.close()

    def get_employee_for_user(self, user_id: int) -> Optional[Any]:
        conn = auth_db.get_connection()
        try:
            return conn.execute(
                "SELECT id, full_name, mosys_employee_id FROM employees WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        finally:
            conn.close()

    def verify_password(self, user: User, password: str) -> bool:
        return bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8'))

    def update_last_login(self, user_id: int):
        conn = auth_db.get_connection()
        try:
            conn.execute("UPDATE users SET last_login = ? WHERE id = ?",
                         (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id))
            conn.commit()
        finally:
            conn.close()

    def update_password(self, user_id: int, new_password: str):
        password_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        conn = auth_db.get_connection()
        try:
            conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (password_hash, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id),
            )
            conn.commit()
        finally:
            conn.close()

    def clear_must_change_password(self, user_id: int):
        conn = auth_db.get_connection()
        try:
            conn.execute(
                "UPDATE users SET must_change_password = 0, updated_at = ? WHERE id = ?",
                (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id),
            )
            conn.commit()
        finally:
            conn.close()

    def update_user(self, user_id: int, full_name: str, role: str):
        conn = auth_db.get_connection()
        try:
            self._validate_role(conn, role)
            conn.execute(
                "UPDATE users SET full_name = ?, role = ?, updated_at = ? WHERE id = ?",
                (full_name.strip(), role, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id),
            )
            conn.commit()
        finally:
            conn.close()

    def set_active(self, user_id: int, is_active: bool):
        conn = auth_db.get_connection()
        try:
            conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (int(is_active), user_id))
            conn.commit()
        finally:
            conn.close()

    def delete_user(self, user_id: int) -> bool:
        """Hard delete. Unlinking the employee happens via ON DELETE SET NULL."""
        conn = auth_db.get_connection()
        try:
            cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


class RoleRepository:

    def get_all(self) -> list:
        conn = auth_db.get_connection()
        try:
            return conn.execute("""
                SELECT r.id, r.name, r.display_name, r.is_protected, r.full_access,
                       r.created_at, COUNT(u.id) AS user_count
                FROM roles r LEFT JOIN users u ON u.role = r.name
                GROUP BY r.id ORDER BY r.id
            """).fetchall()
        finally:
            conn.close()

    def get_by_id(self, role_id: int) -> Optional[Any]:
        conn = auth_db.get_connection()
        try:
            return conn.execute("SELECT * FROM roles WHERE id = ?", (role_id,)).fetchone()
        finally:
            conn.close()

    def get_by_name(self, name: str) -> Optional[Any]:
        conn = auth_db.get_connection()
        try:
            return conn.execute("SELECT * FROM roles WHERE name = ?", (name,)).fetchone()
        finally:
            conn.close()

    def role_has_full_access(self, role_name: str) -> bool:
        row = self.get_by_name(role_name)
        return bool(row['full_access']) if row else False

    def toggle_full_access(self, role_id: int) -> bool:
        conn = auth_db.get_connection()
        try:
            row = conn.execute("SELECT full_access, is_protected FROM roles WHERE id = ?", (role_id,)).fetchone()
            if not row:
                raise ValueError('Role does not exist')
            if row['is_protected']:
                raise ValueError('Cannot change access level of a protected role')
            new_state = 0 if row['full_access'] else 1
            conn.execute("UPDATE roles SET full_access = ? WHERE id = ?", (new_state, role_id))
            conn.commit()
            return bool(new_state)
        finally:
            conn.close()

    def delete(self, role_id: int) -> bool:
        conn = auth_db.get_connection()
        try:
            row = conn.execute("SELECT name, is_protected FROM roles WHERE id = ?", (role_id,)).fetchone()
            if not row:
                raise ValueError('Role does not exist')
            if row['is_protected']:
                raise ValueError('Cannot delete a protected role')
            in_use = conn.execute("SELECT COUNT(*) AS c FROM users WHERE role = ?", (row['name'],)).fetchone()['c']
            if in_use:
                raise ValueError(f'Cannot delete: {in_use} user(s) still have this role')
            cursor = conn.execute("DELETE FROM roles WHERE id = ?", (role_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


class EmployeeRepository:

    def get_all_with_user(self) -> list:
        conn = auth_db.get_connection()
        try:
            return conn.execute("""
                SELECT e.id, e.full_name, e.mosys_employee_id, e.synced_at,
                       u.id AS user_id, u.role AS user_role, u.is_active AS user_is_active
                FROM employees e LEFT JOIN users u ON u.id = e.user_id
                ORDER BY e.full_name
            """).fetchall()
        finally:
            conn.close()

    def get_by_id(self, employee_id: int) -> Optional[Any]:
        conn = auth_db.get_connection()
        try:
            return conn.execute("SELECT * FROM employees WHERE id = ?", (employee_id,)).fetchone()
        finally:
            conn.close()

    def link_user(self, employee_id: int, user_id: int):
        conn = auth_db.get_connection()
        try:
            conn.execute("UPDATE employees SET user_id = ? WHERE id = ?", (user_id, employee_id))
            conn.commit()
        finally:
            conn.close()

    def sync_from_mosys(self, mosys_employees: list) -> dict:
        """Upsert employees by mosys_employee_id.

        ``mosys_employees`` = list of {'mosys_id': str, 'full_name': str}.
        Returns {'added': int, 'updated': int}.
        """
        added = updated = 0
        conn = auth_db.get_connection()
        try:
            for emp in mosys_employees:
                mosys_id = emp['mosys_id']
                existing = conn.execute(
                    "SELECT id FROM employees WHERE mosys_employee_id = ?", (mosys_id,)
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE employees SET full_name = ?, synced_at = ? WHERE mosys_employee_id = ?",
                        (emp['full_name'], datetime.now().strftime('%Y-%m-%d %H:%M:%S'), mosys_id),
                    )
                    updated += 1
                else:
                    conn.execute(
                        "INSERT INTO employees (full_name, mosys_employee_id) VALUES (?, ?)",
                        (emp['full_name'], mosys_id),
                    )
                    added += 1
            conn.commit()
        finally:
            conn.close()
        return {'added': added, 'updated': updated}
