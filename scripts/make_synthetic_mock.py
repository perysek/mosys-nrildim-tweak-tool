"""Generate a synthetic offline SQLite mock (no DSN required).

For local UI smoke-testing WITHOUT the Pervasive DSN. Writes
app/data/mock_mosys_synthetic.sqlite from the fabricated dataset in
tests/fixtures.py. This is MECHANICS-ONLY fabricated data — it does NOT stand in
for the §2.1 scale/natural-key gate, which requires the REAL DSN via
scripts/build_mock_data.py.

Optional manual smoke recipe (monkeypatch the reader to serve the synthetic DB),
kept out of production code — see MORNING-HANDOFF.md.

    ! python scripts/make_synthetic_mock.py
"""

import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from tests import fixtures  # noqa: E402

OUT = os.path.join(_ROOT, 'app', 'data', 'mock_mosys_synthetic.sqlite')


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if os.path.exists(OUT):
        os.remove(OUT)
    conn = sqlite3.connect(OUT)
    try:
        fixtures.populate(conn)
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ('NRILDIM', 'NSCHEDIM', 'SCHEDIM1')}
    finally:
        conn.close()
    print(f"Wrote synthetic mock -> {OUT}")
    print("Row counts:", counts)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
