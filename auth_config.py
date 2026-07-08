"""RBAC decorators — sits alongside config.py at the repo root.

Two behavioral gates only (this app has no per-module permission grid):
``role_required`` for the superuser-only Admin settings pages, and
``full_access_required`` for the SPC-Tweaks write path, layered on top of
(never instead of) the existing ``config.WRITE_ENABLED`` dry-run gate.
"""

from functools import wraps

from flask import flash, redirect, url_for
from flask_login import current_user

from app.functions.auth_repo import RoleRepository

_role_repo = RoleRepository()


def role_required(*role_names):
    """Exact role-name match. Use for admin/management pages."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Please log in to access this page.', 'info')
                return redirect(url_for('login'))
            if current_user.role not in role_names:
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated
    return decorator


def full_access_required(f):
    """Blocks write-path routes for roles without full_access — independent
    of (and in addition to) config.WRITE_ENABLED, which the route checks
    separately."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'info')
            return redirect(url_for('login'))
        if not _role_repo.role_has_full_access(current_user.role):
            flash('Your role has read-only access — writes are not permitted.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


def role_display_name(role_name: str) -> str:
    row = _role_repo.get_by_name(role_name)
    return row['display_name'] if row else role_name.capitalize()
