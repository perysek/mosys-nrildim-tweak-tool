"""Login, first-login password setup, logout, password reset, and profile.

Login is by MOSYS employee ID (no email field is ever shown). Plain
``@app.route`` on the shared ``app`` singleton, matching ``routes.py`` /
``spc_routes.py`` — this project does not use Flask blueprints.
"""

import secrets
from datetime import datetime, timedelta

from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user

from app import app
from app.functions import auth_db
from app.functions.auth_repo import UserRepository
from app.functions.auth_service import AuthService

_user_repo = UserRepository()
_auth_service = AuthService(_user_repo)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    employee_id = ''
    if request.method == 'POST':
        employee_id = request.form.get('employee_id', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        ok, user, error = _auth_service.authenticate_by_employee_id(employee_id, password)
        if ok:
            login_user(user, remember=remember)
            auth_db.log_event('login_ok', user_id=user.id, user_email=user.email,
                               user_name=user.full_name, ip_address=request.remote_addr)
            if user.must_change_password:
                return redirect(url_for('set_first_password'))
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))

        auth_db.log_event('login_failed', detail=f'employee_id={employee_id}: {error}',
                           ip_address=request.remote_addr)
        flash(error, 'error')

    return render_template('auth/login.html', employee_id=employee_id)


@app.route('/auth/api/needs-setup')
def auth_needs_setup():
    """Polled by login.html JS once 4 digits are typed."""
    mosys_id = request.args.get('mosys_id', '').strip()
    if not mosys_id:
        return jsonify({'needs_setup': False})
    user = _user_repo.get_by_mosys_employee_id(mosys_id)
    if user and user.is_active and user.must_change_password:
        return jsonify({'needs_setup': True, 'full_name': user.full_name})
    return jsonify({'needs_setup': False})


@app.route('/auth/first-login', methods=['POST'])
def first_login():
    """No session required — the whole point is setting a password before
    the user has ever logged in with one."""
    mosys_id = request.form.get('mosys_id', '').strip()
    new_pw = request.form.get('new_password', '')
    confirm = request.form.get('confirm_password', '')

    user = _user_repo.get_by_mosys_employee_id(mosys_id)
    if not user or not user.is_active or not user.must_change_password:
        flash('Invalid password setup request.', 'error')
        return redirect(url_for('login'))

    if len(new_pw) < 8:
        flash('Password must be at least 8 characters.', 'error')
        return redirect(url_for('login'))
    if new_pw != confirm:
        flash('Passwords do not match.', 'error')
        return redirect(url_for('login'))

    _user_repo.update_password(user.id, new_pw)
    _user_repo.clear_must_change_password(user.id)
    login_user(user)
    auth_db.log_event('password_set_first', user_id=user.id, user_email=user.email,
                       user_name=user.full_name, ip_address=request.remote_addr)
    flash('Password set. Welcome!', 'success')
    return redirect(url_for('index'))


@app.route('/auth/set-first-password', methods=['GET', 'POST'])
@login_required
def set_first_password():
    """Same flow as first_login, but for a user already in session whose
    must_change_password flag is still set (rare — belt and suspenders)."""
    if not current_user.must_change_password:
        return redirect(url_for('index'))

    if request.method == 'POST':
        new_pw = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        if len(new_pw) < 8:
            flash('Password must be at least 8 characters.', 'error')
        elif new_pw != confirm:
            flash('Passwords do not match.', 'error')
        else:
            _user_repo.update_password(current_user.id, new_pw)
            _user_repo.clear_must_change_password(current_user.id)
            auth_db.log_event('password_set_first', user_id=current_user.id,
                               user_email=current_user.email, user_name=current_user.full_name,
                               ip_address=request.remote_addr)
            flash('Password set. Welcome!', 'success')
            return redirect(url_for('index'))

    return render_template('auth/set_first_password.html')


@app.route('/logout')
@login_required
def logout():
    auth_db.log_event('logout', user_id=current_user.id, user_email=current_user.email,
                       user_name=current_user.full_name, ip_address=request.remote_addr)
    logout_user()
    flash('Logged out.', 'success')
    return redirect(url_for('login'))


@app.route('/auth/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """On-screen reset link — no SMTP is configured on this internal/LAN
    app. Always shows the same flash regardless of whether the employee
    number matched, to avoid account enumeration."""
    reset_url = None
    if request.method == 'POST':
        mosys_id = request.form.get('mosys_employee_id', '').strip()
        user = _user_repo.get_by_mosys_employee_id(mosys_id)
        if user:
            conn = auth_db.get_connection()
            try:
                conn.execute("UPDATE password_reset_tokens SET used = 1 WHERE user_id = ? AND used = 0",
                             (user.id,))
                token = secrets.token_urlsafe(32)
                expires_at = (datetime.now() + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
                conn.execute(
                    "INSERT INTO password_reset_tokens (user_id, token, expires_at) VALUES (?, ?, ?)",
                    (user.id, token, expires_at),
                )
                conn.commit()
            finally:
                conn.close()
            reset_url = url_for('reset_password', token=token, _external=True)
        flash('If that employee number exists, a reset link is shown below.', 'info')
    return render_template('auth/forgot_password.html', reset_url=reset_url)


@app.route('/auth/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    conn = auth_db.get_connection()
    try:
        token_row = conn.execute(
            "SELECT * FROM password_reset_tokens "
            "WHERE token = ? AND used = 0 AND expires_at > datetime('now', 'localtime')",
            (token,),
        ).fetchone()
    finally:
        conn.close()

    if not token_row:
        flash('This reset link has expired or was already used.', 'error')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        if len(new_password) < 8:
            flash('Password must be at least 8 characters.', 'error')
        elif new_password != confirm:
            flash('Passwords do not match.', 'error')
        else:
            _user_repo.update_password(token_row['user_id'], new_password)
            conn = auth_db.get_connection()
            try:
                conn.execute("UPDATE password_reset_tokens SET used = 1 WHERE token = ?", (token,))
                conn.commit()
            finally:
                conn.close()
            flash('Password changed. You can now log in.', 'success')
            return redirect(url_for('login'))

    return render_template('auth/reset_password.html', token=token)


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    employee = _user_repo.get_employee_for_user(current_user.id)
    if request.method == 'POST':
        old_pw = request.form.get('old_password', '')
        new_pw = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        if new_pw != confirm:
            flash('New passwords do not match.', 'error')
        else:
            ok, error = _auth_service.change_password(current_user.id, old_pw, new_pw)
            if ok:
                auth_db.log_event('password_changed', user_id=current_user.id,
                                   user_email=current_user.email, user_name=current_user.full_name,
                                   ip_address=request.remote_addr)
                flash('Password changed.', 'success')
                return redirect(url_for('profile'))
            flash(error, 'error')
    return render_template('profile.html', employee=employee)
