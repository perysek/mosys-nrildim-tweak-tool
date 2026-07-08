"""Unit tests for app.functions.spc transforms + stats (offline, synthetic mock).

MECHANICS ONLY — see tests/fixtures.py: the ÷10000 round-trip passes here by
construction; it does not verify the production scale factor (§2.1 gate).
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

from app.functions import mosys_data, spc  # noqa: E402
from tests import fixtures  # noqa: E402


class SpcTransformTests(unittest.TestCase):
    def setUp(self):
        self.df = mosys_data.format_measurements(fixtures.joined_dataframe())

    # ---- formatting / scale ------------------------------------------------
    def test_scale_and_raw_key_preserved(self):
        # MIS01 raw 100000 -> display 10.0
        self.assertAlmostEqual(self.df.iloc[0]['MIS01'], 10.0, places=6)
        # Raw key columns kept for write targeting (unformatted).
        self.assertEqual(self.df.iloc[0]['RAW_DATA_RILEVAMENTO'], '20250101')
        self.assertEqual(self.df.iloc[0]['RAW_NUMERO_FIGURA'], '001')
        # Display cavity is last-digit.
        self.assertEqual(self.df.iloc[0]['NUMERO_FIGURA'], '1')

    def test_mis_avg_skips_empty(self):
        # Row 1 (index 1) has MIS03 empty -> avg over the two present cells.
        row = self.df.iloc[1]
        self.assertAlmostEqual(row['MIS_AVG'], (10.04 + 10.0) / 2, places=6)

    # ---- footer stats ------------------------------------------------------
    def test_footer_stats(self):
        stats = spc.footer_stats(self.df)
        self.assertEqual(stats['total_rows'], 8)
        for k in ('avg_min', 'avg_max', 'avg_range'):
            self.assertIsNotNone(stats[k])
        self.assertGreaterEqual(stats['avg_max'], stats['avg_min'])

    # ---- squeeze -----------------------------------------------------------
    def test_squeeze_shrinks_spread_by_factor(self):
        s = 0.5
        base = spc.group_series(self.df)
        tweaked = spc.tweaked_series(self.df, s)
        # Cavity '1' spread should shrink by (1 - s).
        base_vals = base['1']['values']
        tw_vals = tweaked['1']['values']
        base_range = max(base_vals) - min(base_vals)
        tw_range = max(tw_vals) - min(tw_vals)
        self.assertAlmostEqual(tw_range, base_range * (1 - s), places=3)

    def test_squeeze_preserves_group_mean(self):
        s = 0.7
        base = spc.group_series(self.df)['1']['values']
        tweaked = spc.tweaked_series(self.df, s)['1']['values']
        self.assertAlmostEqual(sum(base) / len(base), sum(tweaked) / len(tweaked), places=3)

    def test_zero_squeeze_no_updates(self):
        self.assertEqual(spc.compute_tweaked_updates(self.df, 0.0), [])

    # ---- flatten -----------------------------------------------------------
    def test_flatten_pulls_pick_only(self):
        deltas = spc.compute_row_deltas(self.df, 0.0, flatten=True,
                                        threshold=0.25, nominal=fixtures.NOMINAL)
        # The pick is cavity '2' row at 20250103 (index 6), value ~13.0.
        self.assertIn(6, deltas)
        self.assertLess(deltas[6], 0)  # pulled down toward neighbours
        # Non-pick interior points are untouched.
        self.assertNotIn(5, deltas)
        self.assertNotIn(7, deltas)

    def test_flatten_noop_without_nominal(self):
        deltas = spc.compute_row_deltas(self.df, 0.0, flatten=True, nominal=None)
        self.assertEqual(deltas, {})

    def test_flatten_target_is_non_pick_mean(self):
        # Discriminating series where the three candidate targets all differ:
        # non-pick mean = 10.5, neighbour-avg = 10.0, include-picks mean ≈ 10.857.
        # Only idx 2 (13.0) is a pick; it must land on the NON-pick mean (10.5).
        vals = [10.0, 10.0, 13.0, 10.0, 11.0, 11.0, 11.0]
        df = pd.DataFrame([
            {'NUMERO_FIGURA': '9', 'DATETIME': '2025-01-%02d' % (k + 1), 'MIS01': v}
            for k, v in enumerate(vals)
        ])
        deltas = spc.compute_row_deltas(df, 0.0, flatten=True, threshold=0.25,
                                        nominal=fixtures.NOMINAL)
        self.assertEqual(set(deltas.keys()), {2})          # only the pick moved
        self.assertAlmostEqual(vals[2] + deltas[2], 10.5, places=6)  # non-pick mean

    # ---- update payload ----------------------------------------------------
    def test_updates_skip_empty_cells_and_round_trip(self):
        updates = spc.compute_tweaked_updates(self.df, 0.5)
        self.assertTrue(updates)
        for u in updates:
            # Natural key fully present.
            for col in mosys_data.NATURAL_KEY_COLS:
                self.assertIn(col, u['key'])
            # Only integer raw values, no empty cells.
            for col, raw in u['new_raw'].items():
                self.assertIsInstance(raw, int)
        # Row index 1 had MIS03 empty -> its update must not include MIS03.
        row1_key = self.df.iloc[1]
        for u in updates:
            if (u['key']['DATA_RILEVAMENTO'] == row1_key['RAW_DATA_RILEVAMENTO'] and
                    u['key']['ORA_RILEVAMENTO'] == row1_key['RAW_ORA_RILEVAMENTO'] and
                    u['key']['NUMERO_FIGURA'] == row1_key['RAW_NUMERO_FIGURA']):
                self.assertNotIn('MIS03', u['new_raw'])

    def test_capability_present_with_limits(self):
        cap = spc.capability(self.df, fixtures.USL, fixtures.LSL)
        self.assertTrue(cap)
        for v in cap.values():
            self.assertIn('cp', v)
            self.assertIn('cpk', v)


class ToleranceRowSelectionTests(unittest.TestCase):
    """SCHEDIM1 is versioned — superseded revisions (FLAG_RIMOSSO != '0') sit
    beside the live one and often carry a placeholder nominal of 0. The tolerance
    resolution must read the LIVE row, not blindly iloc[0] (real bug: 'DIAM 8,1'
    showed nominal 0 because a removed 0-row sorted first)."""

    def _frame(self, rows):
        return pd.DataFrame(rows)

    def test_prefers_active_row_over_stale_zero(self):
        # Two removed rows (nominal 0) first, then the live row (nominal 8.1).
        frame = self._frame([
            {'VALORE_NOMINALE': 0.0, 'SEGNO_TOLL_INF': '+', 'TOLL_INF': 0.1,
             'SEGNO_TOLL_SUP': '-', 'TOLL_SUP': 0.0, 'FLAG_RIMOSSO': '1'},
            {'VALORE_NOMINALE': 0.0, 'SEGNO_TOLL_INF': '+', 'TOLL_INF': 0.1,
             'SEGNO_TOLL_SUP': '-', 'TOLL_SUP': 0.0, 'FLAG_RIMOSSO': '1'},
            {'VALORE_NOMINALE': 8.1, 'SEGNO_TOLL_INF': '+', 'TOLL_INF': 0.1,
             'SEGNO_TOLL_SUP': '-', 'TOLL_SUP': 0.0, 'FLAG_RIMOSSO': '0'},
        ])
        tol = mosys_data._tolerance_from_frame(frame)
        self.assertAlmostEqual(tol['nominal'], 8.1, places=6)
        self.assertAlmostEqual(tol['usl'], 8.2, places=6)   # 8.1 +0.1
        self.assertAlmostEqual(tol['lsl'], 8.1, places=6)   # 8.1 -0.0

    def test_preserves_genuine_zero_active_nominal(self):
        # A defect-count style dim: the LIVE row legitimately has nominal 0.
        frame = self._frame([
            {'VALORE_NOMINALE': 0.0, 'SEGNO_TOLL_INF': '+', 'TOLL_INF': 9.0,
             'SEGNO_TOLL_SUP': '-', 'TOLL_SUP': 0.0, 'FLAG_RIMOSSO': '0'},
        ])
        tol = mosys_data._tolerance_from_frame(frame)
        self.assertAlmostEqual(tol['nominal'], 0.0, places=6)
        self.assertAlmostEqual(tol['usl'], 9.0, places=6)

    def test_falls_back_when_no_flag_column(self):
        # Offline fixture path has no FLAG_RIMOSSO — must still work (iloc[0]).
        frame = self._frame([
            {'VALORE_NOMINALE': 3.3, 'SEGNO_TOLL_INF': '+', 'TOLL_INF': 0.1,
             'SEGNO_TOLL_SUP': '-', 'TOLL_SUP': 0.1},
        ])
        tol = mosys_data._tolerance_from_frame(frame)
        self.assertAlmostEqual(tol['nominal'], 3.3, places=6)

    def test_all_removed_falls_back_to_first(self):
        # Degenerate: every row removed — better to show something than nothing.
        frame = self._frame([
            {'VALORE_NOMINALE': 5.0, 'SEGNO_TOLL_INF': '+', 'TOLL_INF': 0.1,
             'SEGNO_TOLL_SUP': '-', 'TOLL_SUP': 0.0, 'FLAG_RIMOSSO': '1'},
        ])
        tol = mosys_data._tolerance_from_frame(frame)
        self.assertAlmostEqual(tol['nominal'], 5.0, places=6)


if __name__ == '__main__':
    unittest.main()
