"""Admin — Employees: the onboarding surface. Superuser-only.

'Activate' both creates the login account for a freshly-synced MOSYS
employee (temp password + must_change_password=1, per auth_repo.User) and
re-enables a previously-deactivated one. 'Deactivate' disables login without
deleting anything. There is no manual "add employee" — the roster comes
only from 'MOSYS sync' (STAAMPDB.OPERATORI).
"""

import secrets

from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from app import app
from app.functions import auth_db
from app.functions.mosys import fetch_operatori
from app.functions.auth_repo import EmployeeRepository, UserRepository, RoleRepository
from auth_config import role_required

_employee_repo = EmployeeRepository()
_user_repo = UserRepository()
_role_repo = RoleRepository()


@app.route('/system/employees')
@login_required
@role_required('superuser')
def employees_list():
    employees = _employee_repo.get_all_with_user()
    return render_template('admin/employees_list.html', employees=employees)


# MOSYS sync only onboards this ID range — STAAMPDB.OPERATORI carries some
# non-employee placeholder codes above 9500 (e.g. "!!! RETTIFICA" at 9999)
# that shouldn't show up as activatable people.
_SYNC_ID_MIN, _SYNC_ID_MAX = 9001, 9500


@app.route('/system/employees/sync-mosys', methods=['POST'])
@login_required
@role_required('superuser')
def employees_sync_mosys():
    try:
        mosys_employees = fetch_operatori()
    except Exception as e:
        flash(f'Could not connect to MOSYS: {e}', 'error')
        return redirect(url_for('employees_list'))

    in_range = []
    for e in mosys_employees:
        try:
            if _SYNC_ID_MIN <= int(e['mosys_id']) <= _SYNC_ID_MAX:
                in_range.append(e)
        except (TypeError, ValueError):
            continue

    result = _employee_repo.sync_from_mosys(in_range)
    auth_db.log_event('employee_sync_mosys', user_id=current_user.id, user_email=current_user.email,
                       user_name=current_user.full_name,
                       detail=f"added={result['added']}, updated={result['updated']}, "
                              f"in_range={len(in_range)}, fetched={len(mosys_employees)}",
                       ip_address=request.remote_addr)
    flash(f"MOSYS sync complete — {result['added']} added, {result['updated']} updated "
          f"({len(in_range)} operators in range {_SYNC_ID_MIN}–{_SYNC_ID_MAX}, "
          f"{len(mosys_employees)} fetched total).", 'success')
    return redirect(url_for('employees_list'))


@app.route('/system/employees/<int:employee_id>/activate', methods=['POST'])
@login_required
@role_required('superuser')
def employee_activate(employee_id):
    employee = _employee_repo.get_by_id(employee_id)
    if not employee:
        flash('Employee does not exist.', 'error')
        return redirect(url_for('employees_list'))

    if employee['user_id']:
        # Already has an account — this is a reactivation, not a fresh create.
        _user_repo.set_active(employee['user_id'], True)
        auth_db.log_event('employee_activate', user_id=current_user.id, user_email=current_user.email,
                           user_name=current_user.full_name, entity_type='employee', entity_id=employee_id,
                           detail=f"reactivated ({employee['full_name']})", ip_address=request.remote_addr)
        flash(f"{employee['full_name']} reactivated.", 'success')
        return redirect(url_for('employees_list'))

    email = f"{employee['mosys_employee_id']}@mosys.local"
    temp_password = secrets.token_urlsafe(12)  # unusable in practice — see first-login flow
    try:
        user_id = _user_repo.create_user(email, temp_password, employee['full_name'],
                                          role='operator', must_change_password=True)
        _employee_repo.link_user(employee_id, user_id)
        auth_db.log_event('employee_activate', user_id=current_user.id, user_email=current_user.email,
                           user_name=current_user.full_name, entity_type='employee', entity_id=employee_id,
                           detail=f"nr {employee['mosys_employee_id']} ({employee['full_name']})",
                           ip_address=request.remote_addr)
        flash(f"{employee['full_name']} activated — they can now log in with employee ID "
              f"{employee['mosys_employee_id']} and will be prompted to set a password.", 'success')
    except Exception as e:
        flash(f'Could not activate: {e}', 'error')
    return redirect(url_for('employees_list'))


@app.route('/system/employees/<int:employee_id>/deactivate', methods=['POST'])
@login_required
@role_required('superuser')
def employee_deactivate(employee_id):
    employee = _employee_repo.get_by_id(employee_id)
    if not employee or not employee['user_id']:
        flash('This employee has no account to deactivate.', 'error')
        return redirect(url_for('employees_list'))
    if employee['user_id'] == current_user.id:
        flash('You cannot deactivate your own account.', 'error')
        return redirect(url_for('employees_list'))

    _user_repo.set_active(employee['user_id'], False)
    auth_db.log_event('employee_deactivate', user_id=current_user.id, user_email=current_user.email,
                       user_name=current_user.full_name, entity_type='employee', entity_id=employee_id,
                       detail=employee['full_name'], ip_address=request.remote_addr)
    flash(f"{employee['full_name']} deactivated.", 'success')
    return redirect(url_for('employees_list'))


@app.route('/system/employees/<int:employee_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('superuser')
def employee_edit(employee_id):
    employee = _employee_repo.get_by_id(employee_id)
    if not employee:
        flash('Employee does not exist.', 'error')
        return redirect(url_for('employees_list'))
    if not employee['user_id']:
        flash('Activate this employee before editing their account.', 'error')
        return redirect(url_for('employees_list'))

    user = _user_repo.get_by_id(employee['user_id'])
    roles = _role_repo.get_all()
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        role = request.form.get('role', '')
        if not full_name or not role:
            flash('Name and role are required.', 'error')
        else:
            try:
                _user_repo.update_user(employee['user_id'], full_name, role)
                auth_db.log_event('employee_update', user_id=current_user.id, user_email=current_user.email,
                                   user_name=current_user.full_name, entity_type='employee', entity_id=employee_id,
                                   detail=full_name, ip_address=request.remote_addr)
                flash('Employee account updated.', 'success')
                return redirect(url_for('employees_list'))
            except ValueError as e:
                flash(str(e), 'error')
    return render_template('admin/employee_edit.html', employee=employee, user=user, roles=roles)
