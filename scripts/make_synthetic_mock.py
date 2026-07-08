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

import datetime
import os
import sqlite3
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from tests import fixtures  # noqa: E402

OUT = os.path.join(_ROOT, 'app', 'data', 'mock_mosys_synthetic.sqlite')


def _shift_dates_recent(conn):
    """Slide the fabricated dates so the newest lands on today.

    The SPC-Tweaks date slider spans a fixed [now-30d, now] window; with the
    fixtures' hard-coded 2025 dates, dragging the slider filters out every row
    and the chart goes blank. Shifting the whole set to the last few days keeps
    the demo coherent WITHOUT touching tests/fixtures.py (which assert on the
    original 2025 dates). Preserves the exact day-to-day spacing.
    """
    rows = [r[0] for r in conn.execute("SELECT DISTINCT DATA_RILEVAMENTO FROM NRILDIM")]
    dates = [(r, datetime.datetime.strptime(str(r), '%Y%m%d').date()) for r in rows]
    if not dates:
        return
    delta = datetime.date.today() - max(d for _, d in dates)
    for raw, d in dates:
        conn.execute("UPDATE NRILDIM SET DATA_RILEVAMENTO = ? WHERE DATA_RILEVAMENTO = ?",
                     ((d + delta).strftime('%Y%m%d'), raw))
    conn.commit()


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if os.path.exists(OUT):
        os.remove(OUT)
    conn = sqlite3.connect(OUT)
    try:
        fixtures.populate(conn)
        _shift_dates_recent(conn)
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ('NRILDIM', 'NSCHEDIM', 'SCHEDIM1')}
        span = conn.execute(
            "SELECT MIN(DATA_RILEVAMENTO), MAX(DATA_RILEVAMENTO) FROM NRILDIM").fetchone()
    finally:
        conn.close()
    print(f"Wrote synthetic mock -> {OUT}")
    print("Row counts:", counts, "| date span:", span)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
