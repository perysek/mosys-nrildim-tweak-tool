"""Tests for the RBAC layer: schema/repos/service (isolated SQLite) + route
gating (Flask test client). No MOSYS DB access — fetch_operatori is exercised
indirectly only via EmployeeRepository.sync_from_mosys with a canned list.

Isolation: auth_db.get_connection() is monkeypatched per-test to always
resolve to a throwaway temp-file DB, regardless of what path a caller passes
(log_event()'s ``path=DEFAULT_DB_PATH`` default is bound at import time, so a
naive patch that only changes the *default* would still leak to the real
app/data/auth.sqlite — the replacement below discards whatever path it's
given instead of relying on default-argument rebinding).
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402
from app.functions import auth_db  # noqa: E402
from app.functions.auth_repo import UserRepository, RoleRepository, EmployeeRepository  # noqa: E402
from app.functions.auth_service import AuthService  # noqa: E402


class AuthTestBase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, 'auth_test.sqlite')
        self._orig_get_connection = auth_db.get_connection
        auth_db.get_connection = lambda *a, **k: self._orig_get_connection(self.db_path)
        auth_db.initialize_database(path=self.db_path)

        self.user_repo = UserRepository()
        self.role_repo = RoleRepository()
        self.employee_repo = EmployeeRepository()

    def tearDown(self):
        auth_db.get_connection = self._orig_get_connection
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_employee_and_user(self, mosys_id='9001', full_name='Test Operator', role='operator'):
        self.employee_repo.sync_from_mosys([{'mosys_id': mosys_id, 'full_name': full_name}])
        employee = next(e for e in self.employee_repo.get_all_with_user()
                         if e['mosys_employee_id'] == mosys_id)
        user_id = self.user_repo.create_user(f'{mosys_id}@mosys.local', 'irrelevant-temp-pw',
                                              full_name, role=role, must_change_password=True)
        self.employee_repo.link_user(employee['id'], user_id)
        return employee['id'], user_id


class SchemaTests(AuthTestBase):
    def test_seed_roles(self):
        roles = {r['name']: r for r in self.role_repo.get_all()}
        self.assertIn('superuser', roles)
        self.assertIn('operator', roles)
        self.assertEqual(roles['superuser']['is_protected'], 1)
        self.assertEqual(roles['superuser']['full_access'], 1)
        self.assertEqual(roles['operator']['is_protected'], 0)
        self.assertEqual(roles['operator']['full_access'], 1)  # day-1 rollout default

    def test_initialize_database_is_idempotent(self):
        auth_db.initialize_database(path=self.db_path)  # must not raise / duplicate seed rows
        roles = self.role_repo.get_all()
        names = [r['name'] for r in roles]
        self.assertEqual(names.count('superuser'), 1)


class UserRepositoryTests(AuthTestBase):
    def test_create_and_verify_password(self):
        user_id = self.user_repo.create_user('9001@mosys.local', 'S3cret!!', 'Jan Kowalski')
        user = self.user_repo.get_by_id(user_id)
        self.assertEqual(user.full_name, 'Jan Kowalski')
        self.assertTrue(self.user_repo.verify_password(user, 'S3cret!!'))
        self.assertFalse(self.user_repo.verify_password(user, 'wrong'))

    def test_create_user_rejects_unknown_role(self):
        with self.assertRaises(ValueError):
            self.user_repo.create_user('x@mosys.local', 'pw', 'X', role='not-a-role')

    def test_get_by_mosys_employee_id_via_join(self):
        _, user_id = self._make_employee_and_user(mosys_id='9002', full_name='Anna Nowak')
        user = self.user_repo.get_by_mosys_employee_id('9002')
        self.assertIsNotNone(user)
        self.assertEqual(user.id, user_id)
        self.assertIsNone(self.user_repo.get_by_mosys_employee_id('0000'))

    def test_set_active_and_delete(self):
        user_id = self.user_repo.create_user('9003@mosys.local', 'pw123456', 'Ola')
        self.user_repo.set_active(user_id, False)
        self.assertFalse(self.user_repo.get_by_id(user_id).is_active)
        self.assertTrue(self.user_repo.delete_user(user_id))
        self.assertIsNone(self.user_repo.get_by_id(user_id))

    def test_update_password_and_must_change_flag(self):
        user_id = self.user_repo.create_user('9004@mosys.local', 'oldpassword', 'X', must_change_password=True)
        self.assertTrue(self.user_repo.get_by_id(user_id).must_change_password)
        self.user_repo.update_password(user_id, 'newpassword')
        self.user_repo.clear_must_change_password(user_id)
        user = self.user_repo.get_by_id(user_id)
        self.assertFalse(user.must_change_password)
        self.assertTrue(self.user_repo.verify_password(user, 'newpassword'))


class RoleRepositoryTests(AuthTestBase):
    def test_toggle_full_access(self):
        operator = self.role_repo.get_by_name('operator')
        new_state = self.role_repo.toggle_full_access(operator['id'])
        self.assertFalse(new_state)
        self.assertFalse(self.role_repo.role_has_full_access('operator'))

    def test_cannot_toggle_protected_role(self):
        superuser = self.role_repo.get_by_name('superuser')
        with self.assertRaises(ValueError):
            self.role_repo.toggle_full_access(superuser['id'])

    def test_cannot_delete_protected_role(self):
        superuser = self.role_repo.get_by_name('superuser')
        with self.assertRaises(ValueError):
            self.role_repo.delete(superuser['id'])

    def test_cannot_delete_role_in_use(self):
        self._make_employee_and_user(role='operator')
        operator = self.role_repo.get_by_name('operator')
        with self.assertRaises(ValueError):
            self.role_repo.delete(operator['id'])

    def test_delete_unused_unprotected_role(self):
        # create() isn't exposed via routes (no create-role UI), but the repo
        # layer must still support cleanup of an orphaned role row.
        conn = auth_db.get_connection()
        try:
            conn.execute("INSERT INTO roles (name, display_name) VALUES ('temp_role', 'Temp')")
            conn.commit()
        finally:
            conn.close()
        role = self.role_repo.get_by_name('temp_role')
        self.assertTrue(self.role_repo.delete(role['id']))


class EmployeeRepositoryTests(AuthTestBase):
    def test_sync_from_mosys_add_then_update(self):
        result = self.employee_repo.sync_from_mosys([{'mosys_id': '9010', 'full_name': 'First Name'}])
        self.assertEqual(result, {'added': 1, 'updated': 0})
        result = self.employee_repo.sync_from_mosys([{'mosys_id': '9010', 'full_name': 'Renamed'}])
        self.assertEqual(result, {'added': 0, 'updated': 1})
        employees = self.employee_repo.get_all_with_user()
        self.assertEqual(employees[0]['full_name'], 'Renamed')


class AuthServiceTests(AuthTestBase):
    def setUp(self):
        super().setUp()
        self.service = AuthService(self.user_repo)

    def test_authenticate_success_updates_last_login(self):
        self.employee_repo.sync_from_mosys([{'mosys_id': '9020', 'full_name': 'Ok User'}])
        employee = self.employee_repo.get_all_with_user()[0]
        user_id = self.user_repo.create_user('9020@mosys.local', 'goodpassword', 'Ok User')
        self.employee_repo.link_user(employee['id'], user_id)

        ok, user, error = self.service.authenticate_by_employee_id('9020', 'goodpassword')
        self.assertTrue(ok)
        self.assertIsNone(error)
        self.assertIsNotNone(self.user_repo.get_by_id(user_id).last_login)

    def test_authenticate_wrong_password(self):
        self.employee_repo.sync_from_mosys([{'mosys_id': '9021', 'full_name': 'X'}])
        employee = self.employee_repo.get_all_with_user()[0]
        user_id = self.user_repo.create_user('9021@mosys.local', 'goodpassword', 'X')
        self.employee_repo.link_user(employee['id'], user_id)

        ok, user, error = self.service.authenticate_by_employee_id('9021', 'wrong')
        self.assertFalse(ok)
        self.assertIsNone(user)
        self.assertIsNotNone(error)

    def test_authenticate_inactive_user_blocked(self):
        self.employee_repo.sync_from_mosys([{'mosys_id': '9022', 'full_name': 'X'}])
        employee = self.employee_repo.get_all_with_user()[0]
        user_id = self.user_repo.create_user('9022@mosys.local', 'goodpassword', 'X')
        self.employee_repo.link_user(employee['id'], user_id)
        self.user_repo.set_active(user_id, False)

        ok, user, error = self.service.authenticate_by_employee_id('9022', 'goodpassword')
        self.assertFalse(ok)
        self.assertIn('inactive', error.lower())

    def test_authenticate_unknown_id(self):
        ok, user, error = self.service.authenticate_by_employee_id('0000', 'x')
        self.assertFalse(ok)
        self.assertIsNotNone(error)

    def test_change_password_wrong_old_password(self):
        user_id = self.user_repo.create_user('9023@mosys.local', 'correctold', 'X')
        ok, error = self.service.change_password(user_id, 'wrongold', 'newpassword')
        self.assertFalse(ok)

    def test_change_password_too_short(self):
        user_id = self.user_repo.create_user('9024@mosys.local', 'correctold', 'X')
        ok, error = self.service.change_password(user_id, 'correctold', 'short')
        self.assertFalse(ok)

    def test_change_password_success(self):
        user_id = self.user_repo.create_user('9025@mosys.local', 'correctold', 'X')
        ok, error = self.service.change_password(user_id, 'correctold', 'newlongpassword')
        self.assertTrue(ok)
        self.assertTrue(self.user_repo.verify_password(self.user_repo.get_by_id(user_id), 'newlongpassword'))


class RouteGatingTests(AuthTestBase):
    """Flask test client — verifies @login_required / @role_required /
    @full_access_required actually gate the routes they're attached to."""

    def setUp(self):
        super().setUp()
        app.testing = True
        self.client = app.test_client()

    def _login_as(self, user_id):
        # Standard Flask-Login test shortcut: seed the session directly rather
        # than exercising the real POST /login form.
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(user_id)
            sess['_fresh'] = True

    def test_unauthenticated_redirects_to_login(self):
        for path in ('/', '/graph', '/measurements', '/system/users'):
            resp = self.client.get(path)
            self.assertEqual(resp.status_code, 302, path)
            self.assertIn('/login', resp.headers['Location'])

    def test_operator_cannot_reach_admin_pages(self):
        _, user_id = self._make_employee_and_user(mosys_id='9030', role='operator')
        self._login_as(user_id)
        resp = self.client.get('/system/users')
        self.assertEqual(resp.status_code, 302)
        self.assertNotIn('/login', resp.headers['Location'])  # redirected to index, not login

    def test_superuser_can_reach_admin_pages(self):
        _, user_id = self._make_employee_and_user(mosys_id='9031', role='superuser')
        self._login_as(user_id)
        resp = self.client.get('/system/users')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Users', resp.get_data(as_text=True))

    def test_commit_blocked_for_read_only_role_even_if_write_enabled(self):
        self.role_repo.toggle_full_access(self.role_repo.get_by_name('operator')['id'])  # -> read-only
        _, user_id = self._make_employee_and_user(mosys_id='9032', role='operator')
        self._login_as(user_id)

        orig_write_enabled = app.config.get('WRITE_ENABLED')
        app.config['WRITE_ENABLED'] = True
        try:
            resp = self.client.post('/spc-tweaks/commit', json={'articolo': 'ART-1'})
        finally:
            app.config['WRITE_ENABLED'] = orig_write_enabled
        self.assertEqual(resp.status_code, 302)  # full_access_required redirected before the view ran

    def test_commit_reaches_view_for_full_access_role(self):
        _, user_id = self._make_employee_and_user(mosys_id='9033', role='operator')  # full_access=1 by default
        self._login_as(user_id)
        # No articolo -> the view's own early-return fires, proving the decorator
        # let the request through (a redirect would mean it was blocked instead).
        resp = self.client.post('/spc-tweaks/commit', json={})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.get_json()['success'])


if __name__ == '__main__':
    unittest.main()
