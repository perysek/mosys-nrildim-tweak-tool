"""Admin — Users: view / edit / delete. Superuser-only.

No manual "create user" route by design — every account originates from
Employees -> Activate (see app/employees_routes.py).
"""

from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app import app
from app.functions import auth_db
from app.functions.auth_repo import UserRepository, RoleRepository
from auth_config import role_required

_user_repo = UserRepository()
_role_repo = RoleRepository()


@app.route('/system/users')
@login_required
@role_required('superuser')
def users_list():
    users = _user_repo.get_all_with_employee()
    return render_template('admin/users_list.html', users=users)


@app.route('/system/users/<int:user_id>')
@login_required
@role_required('superuser')
def user_view(user_id):
    user = _user_repo.get_by_id(user_id)
    if not user:
        flash('User does not exist.', 'error')
        return redirect(url_for('users_list'))
    employee = _user_repo.get_employee_for_user(user_id)
    return render_template('admin/user_view.html', user=user, employee=employee)


@app.route('/system/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('superuser')
def user_edit(user_id):
    user = _user_repo.get_by_id(user_id)
    if not user:
        flash('User does not exist.', 'error')
        return redirect(url_for('users_list'))
    # A superuser account can only be edited by itself — prevents one
    # superuser from demoting/renaming another out from under them.
    if user.role == 'superuser' and current_user.id != user_id:
        flash('You cannot edit another superuser account.', 'error')
        return redirect(url_for('users_list'))

    roles = _role_repo.get_all()
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        role = request.form.get('role', '')
        if not full_name or not role:
            flash('Name and role are required.', 'error')
        else:
            try:
                _user_repo.update_user(user_id, full_name, role)
                auth_db.log_event('user_update', user_id=current_user.id, user_email=current_user.email,
                                   user_name=current_user.full_name, entity_type='user', entity_id=user_id,
                                   detail=full_name, ip_address=request.remote_addr)
                flash('User updated.', 'success')
                return redirect(url_for('users_list'))
            except ValueError as e:
                flash(str(e), 'error')
    return render_template('admin/user_edit.html', user=user, roles=roles)


@app.route('/system/users/<int:user_id>/delete', methods=['POST'])
@login_required
@role_required('superuser')
def user_delete(user_id):
    user = _user_repo.get_by_id(user_id)
    if not user:
        flash('User does not exist.', 'error')
    elif user.role == 'superuser':
        flash('Superuser accounts cannot be deleted from the UI.', 'error')
    elif user_id == current_user.id:
        flash('You cannot delete your own account.', 'error')
    else:
        _user_repo.delete_user(user_id)
        auth_db.log_event('user_delete', user_id=current_user.id, user_email=current_user.email,
                           user_name=current_user.full_name, entity_type='user', entity_id=user_id,
                           detail=user.full_name, ip_address=request.remote_addr)
        flash('User deleted.', 'success')
    return redirect(url_for('users_list'))
