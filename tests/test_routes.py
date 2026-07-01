"""Flask route tests for the new pages (offline, get_pervasive monkeypatched).

The advisor's highest-value offline check: renders the actual Jinja templates and
wires the routes with a canned DataFrame, catching template-variable typos and
route bugs that the pure-module tests cannot. No DB access.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

from app import app  # noqa: E402
from app.functions import mosys_data  # noqa: E402
from app import spc_routes  # noqa: E402
from tests import fixtures  # noqa: E402


def _fake_get_pervasive(query, params=None):
    if 'SCHEDIM1' in query:
        return pd.DataFrame([{
            'CODICE_ARTICOLO': 'ART-1', 'RIF_MISURA': fixtures.NUMERO_RIFERIMENTO,
            'UN_MIS': 'mm', 'VALORE_NOMINALE': fixtures.NOMINAL,
            'SEGNO_TOLL_INF': '-', 'TOLL_INF': 0.5, 'SEGNO_TOLL_SUP': '+', 'TOLL_SUP': 0.5,
        }])
    return fixtures.joined_dataframe()


class RouteTests(unittest.TestCase):
    def setUp(self):
        app.testing = True
        self.client = app.test_client()
        self._orig = mosys_data.get_pervasive
        mosys_data.get_pervasive = _fake_get_pervasive

    def tearDown(self):
        mosys_data.get_pervasive = self._orig

    def test_measurements_renders(self):
        resp = self.client.get('/measurements')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('Measurements', html)
        self.assertIn('id="measTable"', html)
        self.assertIn('Total rows', html)
        self.assertIn('SPC tweaks', html)          # cross-link button
        self.assertIn('Measurement 1', html)       # column label

    def test_spc_tweaks_renders(self):
        resp = self.client.get('/spc-tweaks?numero_riferimento=%d' % fixtures.NUMERO_RIFERIMENTO)
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('SPC Tweaks', html)
        self.assertIn('id="spcChart"', html)
        self.assertIn('flatten picks', html)
        self.assertIn('Preview', html)
        self.assertIn('spc_transform.js', html)
        self.assertIn('Production writes are disabled', html)  # WRITE_ENABLED off

    def test_measurements_db_error_is_graceful(self):
        def boom(query, params=None):
            raise RuntimeError("DB down")
        mosys_data.get_pervasive = boom
        resp = self.client.get('/measurements')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Could not load measurement data', resp.get_data(as_text=True))


class CommitRouteTests(unittest.TestCase):
    """The commit route's JSON/toast contract (write mechanics are covered by
    test_write.py). execute_nrildim_updates is stubbed to isolate route logic."""

    def setUp(self):
        app.testing = True
        self.client = app.test_client()
        self._orig_get = mosys_data.get_pervasive
        self._orig_exec = spc_routes.execute_nrildim_updates
        mosys_data.get_pervasive = _fake_get_pervasive

    def tearDown(self):
        mosys_data.get_pervasive = self._orig_get
        spc_routes.execute_nrildim_updates = self._orig_exec

    def test_commit_dry_run_contract(self):
        spc_routes.execute_nrildim_updates = lambda updates, **kw: {
            'status': 'dry_run', 'planned': [{'x': 1}], 'updated_rows': 0}
        resp = self.client.post('/spc-tweaks/commit', json={
            'numero_riferimento': str(fixtures.NUMERO_RIFERIMENTO), 'squeeze': 0.5, 'flatten': '0'})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertTrue(data['dry_run'])
        self.assertIn('disabled', data['message'])

    def test_commit_success_contract(self):
        spc_routes.execute_nrildim_updates = lambda updates, **kw: {
            'status': 'committed', 'planned': [], 'updated_rows': 3}
        resp = self.client.post('/spc-tweaks/commit', json={
            'numero_riferimento': str(fixtures.NUMERO_RIFERIMENTO), 'squeeze': 0.5})
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['message'], 'MOSYS records updated')

    def test_commit_error_is_non_technical(self):
        from app.functions.mosys import WriteError
        def boom(updates, **kw):
            raise WriteError("odbc: internal state 42000 blah")
        spc_routes.execute_nrildim_updates = boom
        resp = self.client.post('/spc-tweaks/commit', json={
            'numero_riferimento': str(fixtures.NUMERO_RIFERIMENTO), 'squeeze': 0.5})
        data = resp.get_json()
        self.assertFalse(data['success'])
        self.assertNotIn('odbc', data['error'].lower())
        self.assertNotIn('42000', data['error'])


if __name__ == '__main__':
    unittest.main()
