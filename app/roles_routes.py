"""Admin — Roles: list, toggle read-only/full-access, delete. Superuser-only.

No 'create role' route: the app only has two behavioral gates (is-superuser,
has-full-access), so a third role has no code path to differentiate itself
today. Delete stays available for completeness — blocked on protected roles
and roles still assigned to users (see RoleRepository.delete).
"""

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app import app
from app.functions import auth_db
from app.functions.auth_repo import RoleRepository
from auth_config import role_required

_role_repo = RoleRepository()


@app.route('/system/roles')
@login_required
@role_required('superuser')
def roles_list():
    roles = _role_repo.get_all()
    return render_template('admin/roles_list.html', roles=roles)


@app.route('/system/roles/<int:role_id>/toggle-access', methods=['POST'])
@login_required
@role_required('superuser')
def role_toggle_access(role_id):
    try:
        new_state = _role_repo.toggle_full_access(role_id)
        auth_db.log_event('role_access_toggle', user_id=current_user.id, user_email=current_user.email,
                           user_name=current_user.full_name, entity_type='role', entity_id=role_id,
                           detail=f'full_access={new_state}', ip_address=request.remote_addr)
        flash('Role access level updated.', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    return redirect(url_for('roles_list'))


@app.route('/system/roles/<int:role_id>/delete', methods=['POST'])
@login_required
@role_required('superuser')
def role_delete(role_id):
    try:
        _role_repo.delete(role_id)
        auth_db.log_event('role_delete', user_id=current_user.id, user_email=current_user.email,
                           user_name=current_user.full_name, entity_type='role', entity_id=role_id,
                           ip_address=request.remote_addr)
        flash('Role deleted.', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    return redirect(url_for('roles_list'))
