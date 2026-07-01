"""JS<->Python transform parity (advisor note #4).

Feeds an identical row-average series through the Python transform (spc.py) and
the JS transform (app/static/spc_transform.js, via Node) and asserts they agree.
This guards against drift between the client-side Preview and the authoritative
server-side commit. Skips gracefully if Node is unavailable.
"""

import json
import os
import shutil
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd  # noqa: E402

from app.functions import spc  # noqa: E402

_RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'js_parity_runner.js')

# A series with a clean pick (figura '2', idx 2) so both squeeze and flatten fire.
SERIES = {
    '1': {'labels': ['2025-01-01', '2025-01-02', '2025-01-03', '2025-01-04'],
          'values': [10.0, 10.02, 9.98, 10.0]},
    '2': {'labels': ['2025-01-01', '2025-01-02', '2025-01-03', '2025-01-04'],
          'values': [10.0, 10.0, 13.0, 10.0]},
}
NOMINAL = 10.0


def _series_to_df(series):
    """Build a df whose MIS_AVG equals the series values exactly (single MIS
    column), so the Python transform starts from the identical inputs as JS."""
    rows = []
    for figura, s in series.items():
        for label, value in zip(s['labels'], s['values']):
            rows.append({'NUMERO_FIGURA': figura, 'DATETIME': label, 'MIS01': value})
    return pd.DataFrame(rows)


@unittest.skipIf(shutil.which('node') is None, "node not available")
class JsParityTests(unittest.TestCase):
    def _run_js(self, s, flatten, threshold, nominal):
        payload = json.dumps({'series': SERIES, 's': s, 'flatten': flatten,
                              'threshold': threshold, 'nominal': nominal})
        proc = subprocess.run(['node', _RUNNER], input=payload, capture_output=True,
                              text=True, timeout=30)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def _assert_parity(self, s, flatten, threshold=0.25, nominal=NOMINAL):
        df = _series_to_df(SERIES)
        py = spc.tweaked_series(df, s, flatten=flatten, threshold=threshold, nominal=nominal)
        js = self._run_js(s, flatten, threshold, nominal)
        self.assertEqual(set(py.keys()), set(js.keys()))
        for figura in py:
            pv, jv = py[figura]['values'], js[figura]['values']
            self.assertEqual(len(pv), len(jv))
            for a, b in zip(pv, jv):
                self.assertAlmostEqual(a, b, places=3,
                                       msg=f"figura {figura}: py={pv} js={jv}")

    def test_parity_squeeze_only(self):
        self._assert_parity(0.5, False)

    def test_parity_flatten_only(self):
        self._assert_parity(0.0, True)

    def test_parity_squeeze_and_flatten(self):
        self._assert_parity(0.6, True)

    def test_parity_no_op(self):
        self._assert_parity(0.0, False)


if __name__ == '__main__':
    unittest.main()
