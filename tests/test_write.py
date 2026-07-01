"""Unit tests for the NRILDIM safe-write path (offline, SQLite mock).

Exercises IMPLEMENTATION-PLAN.md §3.1 guarantees: dry-run default, 1-row
targeting probe, integrity gate, atomic commit + rollback, pre-image journal
lifecycle, post-commit verify. NO Pervasive/production access.
"""

import copy
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.functions import mosys_data, spc, nrildim_journal  # noqa: E402
from app.functions.mosys import execute_nrildim_updates, WriteError  # noqa: E402
from tests import fixtures  # noqa: E402
import config  # noqa: E402


def _updates():
    df = mosys_data.format_measurements(fixtures.joined_dataframe())
    return spc.compute_tweaked_updates(df, 0.5)


class DryRunTests(unittest.TestCase):
    def setUp(self):
        self.conn = fixtures.new_populated_connection()
        self.factory = fixtures.sqlite_factory(self.conn)
        self.jpath = os.path.join(tempfile.mkdtemp(), 'j.sqlite')

    def tearDown(self):
        self.conn.close()

    def test_dry_run_is_default_and_writes_nothing(self):
        before = self.conn.execute("SELECT MIS01 FROM NRILDIM").fetchall()
        report = execute_nrildim_updates(_updates(), connection_factory=self.factory,
                                         schema_prefix='', journal_path=self.jpath)
        self.assertEqual(report['status'], 'dry_run')
        self.assertTrue(report['dry_run'])
        after = self.conn.execute("SELECT MIS01 FROM NRILDIM").fetchall()
        self.assertEqual(before, after)

    def test_dry_run_reports_single_row_targeting(self):
        report = execute_nrildim_updates(_updates(), connection_factory=self.factory,
                                         schema_prefix='', journal_path=self.jpath)
        self.assertTrue(report['planned'])
        for plan in report['planned']:
            self.assertEqual(plan['would_match'], 1)
        self.assertIsNone(report['error'])


class CommitTests(unittest.TestCase):
    def setUp(self):
        self.conn = fixtures.new_populated_connection()
        self.factory = fixtures.sqlite_factory(self.conn)
        self.jpath = os.path.join(tempfile.mkdtemp(), 'j.sqlite')

    def tearDown(self):
        self.conn.close()

    def test_commit_applies_and_purges_journal(self):
        updates = _updates()
        report = execute_nrildim_updates(updates, dry_run=False, connection_factory=self.factory,
                                         schema_prefix='', journal_path=self.jpath)
        self.assertEqual(report['status'], 'committed')
        self.assertEqual(report['updated_rows'], len(updates))
        # Values actually changed in the DB and match the intended raw ints.
        u = updates[0]
        col = sorted(u['new_raw'].keys())[0]
        stored = self.conn.execute(
            f"SELECT {col} FROM NRILDIM WHERE ARTICOLO=? AND DATA_RILEVAMENTO=? AND "
            f"ORA_RILEVAMENTO=? AND NUMERO_RIFERIMENTO=? AND NUMERO_STAMPATA=? AND NUMERO_FIGURA=?",
            (u['key']['ARTICOLO'], u['key']['DATA_RILEVAMENTO'], u['key']['ORA_RILEVAMENTO'],
             u['key']['NUMERO_RIFERIMENTO'], u['key']['NUMERO_STAMPATA'], u['key']['NUMERO_FIGURA']),
        ).fetchone()[0]
        self.assertEqual(int(stored), u['new_raw'][col])
        # Journal purged on success.
        self.assertEqual(nrildim_journal.load_batch(report['batch_id'], path=self.jpath), [])

    def test_rollback_is_atomic_and_keeps_journal(self):
        updates = _updates()
        # One valid update + one whose key matches no row -> whole batch must abort.
        valid = updates[0]
        bogus = copy.deepcopy(updates[1])
        bogus['key']['NUMERO_STAMPATA'] = '999'  # matches nothing

        valid_col = sorted(valid['new_raw'].keys())[0]
        original = self.conn.execute(
            f"SELECT {valid_col} FROM NRILDIM WHERE ARTICOLO=? AND DATA_RILEVAMENTO=? AND "
            f"ORA_RILEVAMENTO=? AND NUMERO_RIFERIMENTO=? AND NUMERO_STAMPATA=? AND NUMERO_FIGURA=?",
            (valid['key']['ARTICOLO'], valid['key']['DATA_RILEVAMENTO'], valid['key']['ORA_RILEVAMENTO'],
             valid['key']['NUMERO_RIFERIMENTO'], valid['key']['NUMERO_STAMPATA'], valid['key']['NUMERO_FIGURA']),
        ).fetchone()[0]

        with self.assertRaises(WriteError):
            execute_nrildim_updates([valid, bogus], dry_run=False, connection_factory=self.factory,
                                    schema_prefix='', journal_path=self.jpath)

        # The valid row must be reverted (atomic rollback).
        after = self.conn.execute(
            f"SELECT {valid_col} FROM NRILDIM WHERE ARTICOLO=? AND DATA_RILEVAMENTO=? AND "
            f"ORA_RILEVAMENTO=? AND NUMERO_RIFERIMENTO=? AND NUMERO_STAMPATA=? AND NUMERO_FIGURA=?",
            (valid['key']['ARTICOLO'], valid['key']['DATA_RILEVAMENTO'], valid['key']['ORA_RILEVAMENTO'],
             valid['key']['NUMERO_RIFERIMENTO'], valid['key']['NUMERO_STAMPATA'], valid['key']['NUMERO_FIGURA']),
        ).fetchone()[0]
        self.assertEqual(int(after), int(original))
        # Journal retained for the failed batch (drives undo/rollback path).
        self.assertTrue(nrildim_journal.list_batches(path=self.jpath))


class IntegrityGateTests(unittest.TestCase):
    def test_removed_characteristic_aborts_without_writes(self):
        conn = fixtures.new_populated_connection(removed_ref=fixtures.NUMERO_RIFERIMENTO)
        try:
            before = conn.execute("SELECT MIS01 FROM NRILDIM").fetchall()
            report = execute_nrildim_updates(_updates(), dry_run=False,
                                             connection_factory=fixtures.sqlite_factory(conn),
                                             schema_prefix='',
                                             journal_path=os.path.join(tempfile.mkdtemp(), 'j.sqlite'))
            self.assertEqual(report['status'], 'aborted')
            self.assertTrue(report['integrity_failures'])
            self.assertEqual(before, conn.execute("SELECT MIS01 FROM NRILDIM").fetchall())
        finally:
            conn.close()


class GuardTests(unittest.TestCase):
    def test_missing_key_column_raises(self):
        bad = [{'key': {'ARTICOLO': 'x'}, 'numero_riferimento': '5001', 'new_raw': {'MIS01': 1}}]
        with self.assertRaises(WriteError):
            execute_nrildim_updates(bad, dry_run=True, schema_prefix='')

    def test_empty_updates_is_noop(self):
        report = execute_nrildim_updates([], schema_prefix='')
        self.assertEqual(report['status'], 'noop')

    def test_write_flag_fails_closed(self):
        self.assertFalse(config._truthy(''))
        self.assertFalse(config._truthy(None))
        self.assertFalse(config._truthy('maybe'))
        self.assertFalse(config._truthy('0'))
        self.assertTrue(config._truthy('true'))
        self.assertTrue(config._truthy('1'))


if __name__ == '__main__':
    unittest.main()
