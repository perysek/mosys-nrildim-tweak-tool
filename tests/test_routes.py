"""Flask route tests for the new pages (offline, get_pervasive monkeypatched).

The advisor's highest-value offline check: renders the actual Jinja templates and
wires the routes with a canned DataFrame, catching template-variable typos and
route bugs that the pure-module tests cannot. No DB access.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

from app import app  # noqa: E402
from app.functions import mosys_data, auth_db  # noqa: E402
from app.functions.auth_repo import UserRepository, EmployeeRepository  # noqa: E402
from app import spc_routes  # noqa: E402
from tests import fixtures  # noqa: E402


def _login_test_superuser(client):
    """Every route below is now @login_required (commit is additionally
    @full_access_required) — these tests exercise template rendering / JSON
    contracts, not RBAC itself, so they just need a real authenticated
    session. Isolated temp SQLite (see tests/test_auth.py for why the
    get_connection monkeypatch discards the incoming path rather than relying
    on a rebound default). Returns (orig_get_connection, tmpdir) for teardown.
    """
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, 'auth_test.sqlite')
    orig_get_connection = auth_db.get_connection
    auth_db.get_connection = lambda *a, **k: orig_get_connection(db_path)
    auth_db.initialize_database(path=db_path)

    employee_repo = EmployeeRepository()
    user_repo = UserRepository()
    employee_repo.sync_from_mosys([{'mosys_id': '9999', 'full_name': 'Test Superuser'}])
    employee = employee_repo.get_all_with_user()[0]
    user_id = user_repo.create_user('9999@mosys.local', 'irrelevant-temp-pw',
                                     'Test Superuser', role='superuser')
    employee_repo.link_user(employee['id'], user_id)

    with client.session_transaction() as sess:
        sess['_user_id'] = str(user_id)
        sess['_fresh'] = True

    return orig_get_connection, tmpdir


def _fake_get_pervasive(query, params=None):
    if 'COUNT(*)' in query:                       # count_nrildim volume guard
        return pd.DataFrame([{'n': len(fixtures.joined_dataframe())}])
    if 'DISTINCT CODICE_ARTICOLO' in query:        # fetch_part_numbers (dropdown #1)
        return pd.DataFrame([{'a': 'ART-1'}, {'a': 'ART-2'}])
    if 'DISTINCT NUMERO_RIFERIMENTO' in query:     # fetch_measured_dimensions (dropdown #2)
        return pd.DataFrame([{'r': str(fixtures.NUMERO_RIFERIMENTO)}])
    if 'SCHEDIM1' in query:                        # per-dimension tolerance lookup
        # Versioned SCHEDIM1: two SUPERSEDED rows (FLAG_RIMOSSO='1') with a stale
        # placeholder nominal of 0, then the LIVE row (FLAG_RIMOSSO='0') with the
        # real nominal. fetch_tolerance must resolve to the live row, not iloc[0].
        base = {'CODICE_ARTICOLO': 'ART-1', 'RIF_MISURA': fixtures.NUMERO_RIFERIMENTO,
                'UN_MIS': 'mm', 'SEGNO_TOLL_INF': '-', 'TOLL_INF': 0.5,
                'SEGNO_TOLL_SUP': '+', 'TOLL_SUP': 0.5}
        return pd.DataFrame([
            dict(base, VALORE_NOMINALE=0.0, FLAG_RIMOSSO='1'),
            dict(base, VALORE_NOMINALE=0.0, FLAG_RIMOSSO='1'),
            dict(base, VALORE_NOMINALE=fixtures.NOMINAL, FLAG_RIMOSSO='0'),
        ])
    if 'NSCHEDIM' in query:                        # dimension-metadata enrichment lookup
        # Return the dimension caption WITH FAN-OUT (3 identical rows for the same
        # NUMERO_RIFERIMENTO) — mirrors live NSCHEDIM, where the join key is not
        # unique. The enrichment must collapse this to ONE row per NRILDIM row.
        return pd.DataFrame([
            {'NUMERO_RIFERIMENTO': str(fixtures.NUMERO_RIFERIMENTO),
             'DESCRIZIONE': 'Test dimension', 'VALORE_NOMINALE': fixtures.NOMINAL}
            for _ in range(3)])
    # Main NRILDIM read — now NO join, so strip the columns the enrichment supplies.
    return fixtures.joined_dataframe().drop(columns=['DESCRIZIONE', 'VALORE_NOMINALE'])


class RouteTests(unittest.TestCase):
    def setUp(self):
        app.testing = True
        self.client = app.test_client()
        self._orig = mosys_data.get_pervasive
        mosys_data.get_pervasive = _fake_get_pervasive
        self._orig_get_connection, self._tmpdir = _login_test_superuser(self.client)

    def tearDown(self):
        mosys_data.get_pervasive = self._orig
        auth_db.get_connection = self._orig_get_connection
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_measurements_renders(self):
        # A table renders only when BOTH dropdowns are chosen (part + dimension).
        resp = self.client.get('/measurements?articolo=ART-1&numero_riferimento=%d'
                               % fixtures.NUMERO_RIFERIMENTO)
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('Measurements', html)
        self.assertIn('id="measTable"', html)
        self.assertIn('Total rows', html)
        self.assertIn('SPC tweaks', html)          # cross-link button
        self.assertIn('Measurement 1', html)       # column label

    def test_measurements_shows_dropdowns(self):
        # Initial load (no selection): the two comboboxes + Get data, no table.
        resp = self.client.get('/measurements')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('id="part-input"', html)      # part-number combobox
        self.assertIn('id="dim-input"', html)       # dimension combobox
        self.assertIn('id="get-data-btn"', html)    # Get data button
        self.assertIn('"ART-1"', html)              # embedded part number
        self.assertNotIn('id="measTable"', html)    # no table until a selection
        self.assertIn('Select a', html)             # prompt

    def test_measured_dimensions_endpoint(self):
        # AJAX endpoint powering dropdown #2: measured dims for a part number.
        resp = self.client.get('/measurements/dimensions?articolo=ART-1')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn('dimensions', data)
        self.assertEqual(len(data['dimensions']), 1)
        self.assertEqual(data['dimensions'][0]['numero_riferimento'],
                         str(fixtures.NUMERO_RIFERIMENTO))
        self.assertEqual(data['dimensions'][0]['descrizione'], 'Test dimension')

    def test_measured_dimensions_endpoint_requires_articolo(self):
        resp = self.client.get('/measurements/dimensions')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()['dimensions'], [])

    def test_spc_tweaks_renders(self):
        resp = self.client.get('/spc-tweaks?articolo=ART-1&numero_riferimento=%d'
                               % fixtures.NUMERO_RIFERIMENTO)
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('SPC Tweaks', html)
        self.assertIn('id="spcChart"', html)
        self.assertIn('flatten picks', html)
        self.assertIn('Preview', html)
        self.assertIn('spc_transform.js', html)
        self.assertIn('Production writes are disabled', html)  # WRITE_ENABLED off

    def test_measurements_partial_selection_shows_no_table(self):
        # A part number alone (no dimension) is NOT enough to fetch — no table,
        # no whole-table query. Guards the "both dropdowns required" contract.
        called = {'main': False}
        real = _fake_get_pervasive

        def spy(query, params=None):
            if 'NRILDIM.*' in query:
                called['main'] = True
            return real(query, params)
        mosys_data.get_pervasive = spy
        resp = self.client.get('/measurements?articolo=ART-1')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertNotIn('id="measTable"', html)
        self.assertFalse(called['main'])            # no measurement fetch

    def test_spc_requires_part_number(self):
        # The SPC route fires COUNT(*) before its guard — on an unfiltered live
        # visit that scans the whole table. Gate it: no part number, no DB call.
        def forbidden(query, params=None):
            raise AssertionError("no-filter visit must not query the DB")
        mosys_data.get_pervasive = forbidden
        resp = self.client.get('/spc-tweaks')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('part number', html)
        self.assertNotIn('id="spcChart"', html)    # chart + scripts skipped

    def test_measurements_db_error_is_graceful(self):
        def boom(query, params=None):
            raise RuntimeError("DB down")
        mosys_data.get_pervasive = boom
        resp = self.client.get('/measurements?articolo=ART-1&numero_riferimento=%d'
                               % fixtures.NUMERO_RIFERIMENTO)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('Could not load measurement data', resp.get_data(as_text=True))

    def test_measurements_truncation_notice(self):
        # Row cap: when the dimension has more than the cap, show the loud notice.
        orig = mosys_data.BROWSE_ROW_CAP
        mosys_data.BROWSE_ROW_CAP = 1            # fixture has >1 row -> truncated
        try:
            resp = self.client.get('/measurements?articolo=ART-1&numero_riferimento=%d'
                                   % fixtures.NUMERO_RIFERIMENTO)
            html = resp.get_data(as_text=True)
            self.assertIn('most recent rows', html)
            self.assertIn('this dimension has more', html)
        finally:
            mosys_data.BROWSE_ROW_CAP = orig

    def test_enrichment_maps_metadata_without_row_fanout(self):
        # The old NSCHEDIM LEFT JOIN multiplied every measurement row by the
        # fan-out (~half of live dimensions have >1 NSCHEDIM row). The .map()
        # enrichment must attach the caption 1-to-1: same row count, no dup keys.
        df = mosys_data.fetch_measurements({'articolo': 'ART-1'}, offline_demo=False)
        self.assertEqual(len(df), len(fixtures.raw_records()))     # no multiplication
        self.assertTrue((df['DESCRIZIONE'] == 'Test dimension').all())
        keys = df[mosys_data.NATURAL_KEY_COLS].astype(str).agg('|'.join, axis=1)
        self.assertEqual(keys.nunique(), len(df))                 # keys still unique

    def test_spc_refuses_oversized_selection(self):
        # Volume ceiling: an over-large selection is refused (no tweak built),
        # so the preview can never diverge from what commit would recompute.
        orig = mosys_data.SPC_MAX_ROWS
        mosys_data.SPC_MAX_ROWS = 0             # any non-empty selection is "too many"
        try:
            resp = self.client.get('/spc-tweaks?articolo=ART-1&numero_riferimento=%d'
                                   % fixtures.NUMERO_RIFERIMENTO)
            self.assertEqual(resp.status_code, 200)
            self.assertIn('too many to tweak safely', resp.get_data(as_text=True))
        finally:
            mosys_data.SPC_MAX_ROWS = orig


class CommitRouteTests(unittest.TestCase):
    """The commit route's JSON/toast contract (write mechanics are covered by
    test_write.py). execute_nrildim_updates is stubbed to isolate route logic."""

    def setUp(self):
        app.testing = True
        self.client = app.test_client()
        self._orig_get = mosys_data.get_pervasive
        self._orig_exec = spc_routes.execute_nrildim_updates
        mosys_data.get_pervasive = _fake_get_pervasive
        self._orig_get_connection, self._tmpdir = _login_test_superuser(self.client)

    def tearDown(self):
        mosys_data.get_pervasive = self._orig_get
        spc_routes.execute_nrildim_updates = self._orig_exec
        auth_db.get_connection = self._orig_get_connection
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_commit_dry_run_contract(self):
        spc_routes.execute_nrildim_updates = lambda updates, **kw: {
            'status': 'dry_run', 'planned': [{'x': 1}], 'updated_rows': 0}
        resp = self.client.post('/spc-tweaks/commit', json={
            'articolo': 'ART-1', 'numero_riferimento': str(fixtures.NUMERO_RIFERIMENTO),
            'squeeze': 0.5, 'flatten': '0'})
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertTrue(data['dry_run'])
        self.assertIn('disabled', data['message'])

    def test_commit_success_contract(self):
        spc_routes.execute_nrildim_updates = lambda updates, **kw: {
            'status': 'committed', 'planned': [], 'updated_rows': 3}
        resp = self.client.post('/spc-tweaks/commit', json={
            'articolo': 'ART-1', 'numero_riferimento': str(fixtures.NUMERO_RIFERIMENTO), 'squeeze': 0.5})
        data = resp.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['message'], 'MOSYS records updated')

    def test_commit_requires_part_number(self):
        # A commit with no part number is refused before any COUNT/fetch/write.
        spc_routes.execute_nrildim_updates = lambda updates, **kw: (_ for _ in ()).throw(
            AssertionError("commit without a part number must not reach the write path"))
        resp = self.client.post('/spc-tweaks/commit', json={
            'numero_riferimento': str(fixtures.NUMERO_RIFERIMENTO), 'squeeze': 0.5})
        data = resp.get_json()
        self.assertFalse(data['success'])
        self.assertIn('part number', data['error'])

    def test_commit_refuses_oversized_selection(self):
        # The write path is guarded by the SAME ceiling as the preview: never
        # recompute a squeeze mean (and write) over a set too large to preview.
        orig = mosys_data.SPC_MAX_ROWS
        mosys_data.SPC_MAX_ROWS = 0
        # execute must NOT be reached if the guard fires.
        spc_routes.execute_nrildim_updates = lambda updates, **kw: (_ for _ in ()).throw(
            AssertionError("guard should have blocked the write"))
        try:
            resp = self.client.post('/spc-tweaks/commit', json={
                'articolo': 'ART-1', 'numero_riferimento': str(fixtures.NUMERO_RIFERIMENTO), 'squeeze': 0.5})
            data = resp.get_json()
            self.assertFalse(data['success'])
            self.assertIn('too many to tweak safely', data['error'])
        finally:
            mosys_data.SPC_MAX_ROWS = orig

    def test_commit_error_is_non_technical(self):
        from app.functions.mosys import WriteError
        def boom(updates, **kw):
            raise WriteError("odbc: internal state 42000 blah")
        spc_routes.execute_nrildim_updates = boom
        resp = self.client.post('/spc-tweaks/commit', json={
            'articolo': 'ART-1', 'numero_riferimento': str(fixtures.NUMERO_RIFERIMENTO), 'squeeze': 0.5})
        data = resp.get_json()
        self.assertFalse(data['success'])
        self.assertNotIn('odbc', data['error'].lower())
        self.assertNotIn('42000', data['error'])


class OfflineDemoTests(unittest.TestCase):
    """Opt-in offline demo mode: serves fabricated sample data WITHOUT touching
    the live DB, banners it loudly, and is hard-disabled when writes are on."""

    def setUp(self):
        app.testing = True
        self.client = app.test_client()
        self._demo = app.config.get('OFFLINE_DEMO')
        self._write = app.config.get('WRITE_ENABLED')
        # Guard: the demo path must NEVER call get_pervasive (would hit the DB).
        self._orig_get = mosys_data.get_pervasive

        def _forbidden(query, params=None):
            raise AssertionError("offline demo must not touch the live DB")
        self._forbidden = _forbidden
        self._orig_get_connection, self._tmpdir = _login_test_superuser(self.client)

    def tearDown(self):
        app.config['OFFLINE_DEMO'] = self._demo
        app.config['WRITE_ENABLED'] = self._write
        mosys_data.get_pervasive = self._orig_get
        auth_db.get_connection = self._orig_get_connection
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_demo_serves_sample_data_without_db(self):
        app.config['OFFLINE_DEMO'] = True
        app.config['WRITE_ENABLED'] = False
        mosys_data.get_pervasive = self._forbidden  # would raise if the DB were hit
        resp = self.client.get('/measurements?articolo=ART-1&numero_riferimento=5001')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertIn('OFFLINE SAMPLE DATA', html)   # loud banner
        self.assertIn('10.000', html)                # fabricated MIS value rendered

    def test_write_enabled_forces_demo_off(self):
        # Safety interlock: never serve mock on a write-capable page.
        app.config['OFFLINE_DEMO'] = True
        app.config['WRITE_ENABLED'] = True

        def boom(query, params=None):
            raise RuntimeError("DB down")
        mosys_data.get_pervasive = boom
        resp = self.client.get('/measurements?articolo=ART-1&numero_riferimento=5001')
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self.assertNotIn('OFFLINE SAMPLE DATA', html)      # demo suppressed
        self.assertIn('Could not load measurement data', html)  # real error surfaced

    def test_config_resolution_fails_closed_with_writes(self):
        from config import _truthy
        # Mirror config.py's rule: demo only when opted-in AND writes are off.
        self.assertTrue(_truthy('true') and not _truthy(''))
        self.assertFalse(_truthy('true') and not _truthy('true'))


if __name__ == '__main__':
    unittest.main()
