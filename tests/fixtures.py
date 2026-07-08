"""Synthetic offline fixtures for the NRILDIM feature tests.

IMPORTANT: this is a *fabricated* dataset (advisor note #2). It exercises the
transform + write *mechanics* only. Because the numbers are chosen here, the
÷10000 round-trip passes trivially — that does NOT verify production actually
stores MIS at scale 10000. The §2.1 scale gate stays open until
scripts/build_mock_data.py runs against the real DSN.

MIS values are in RAW integer form (display = raw / 10000). Nominal = 10.0, so
raw ~ 100000 sits near nominal after scaling.
"""

import sqlite3
from contextlib import contextmanager

import pandas as pd

NUMERO_RIFERIMENTO = 5001
ARTICOLO = 'ART-1'
NOMINAL = 10.0
USL = 10.5
LSL = 9.5

# Raw NRILDIM rows: two cavities, chronological. Cavity 002 row at 20250103 is a
# deliberate upward "pick" (~+30% off neighbours) for flatten testing.
# MIS raw ints; MIS03 intentionally empty on some rows to test skip-empty-cell.
_RAW_ROWS = [
    # ARTICOLO, DATA(YYYYMMDD), ORA(HHMMSS), RIF, STAMPATA, FIGURA, MIS01, MIS02, MIS03
    (ARTICOLO, '20250101', '080000', NUMERO_RIFERIMENTO, '001', '001', 100000, 100200, 99800),
    (ARTICOLO, '20250102', '080000', NUMERO_RIFERIMENTO, '002', '001', 100400, 100000, None),
    (ARTICOLO, '20250103', '080000', NUMERO_RIFERIMENTO, '003', '001', 99600, 99800, 100000),
    (ARTICOLO, '20250104', '080000', NUMERO_RIFERIMENTO, '004', '001', 100200, 100400, 99900),
    (ARTICOLO, '20250101', '090000', NUMERO_RIFERIMENTO, '001', '002', 100000, 100000, None),
    (ARTICOLO, '20250102', '090000', NUMERO_RIFERIMENTO, '002', '002', 100200, 99800, 100100),
    (ARTICOLO, '20250103', '090000', NUMERO_RIFERIMENTO, '003', '002', 130000, 130000, 130000),  # pick
    (ARTICOLO, '20250104', '090000', NUMERO_RIFERIMENTO, '004', '002', 100000, 100200, 99900),
]

_MIS_COLS = ['MIS01', 'MIS02', 'MIS03']


def raw_records():
    """List of raw NRILDIM row dicts (as stored in the DB)."""
    cols = ['ARTICOLO', 'DATA_RILEVAMENTO', 'ORA_RILEVAMENTO', 'NUMERO_RIFERIMENTO',
            'NUMERO_STAMPATA', 'NUMERO_FIGURA'] + _MIS_COLS
    return [dict(zip(cols, r)) for r in _RAW_ROWS]


def joined_dataframe():
    """A DataFrame shaped like get_pervasive() output for the NRILDIM+NSCHEDIM
    join (raw NRILDIM columns + DESCRIZIONE + VALORE_NOMINALE)."""
    df = pd.DataFrame(raw_records())
    df['DESCRIZIONE'] = 'Test dimension'
    df['VALORE_NOMINALE'] = NOMINAL
    return df


def _create_schema(conn):
    # NUMERO_RIFERIMENTO / RIF_MISURA are TEXT: the raw natural key produced by
    # compute_tweaked_updates carries them as strings, so the WHERE clause must
    # compare text-to-text (SQLite type affinity would otherwise miss).
    conn.execute(
        "CREATE TABLE NRILDIM (ARTICOLO TEXT, DATA_RILEVAMENTO TEXT, ORA_RILEVAMENTO TEXT, "
        "NUMERO_RIFERIMENTO TEXT, NUMERO_STAMPATA TEXT, NUMERO_FIGURA TEXT, "
        "MIS01 INTEGER, MIS02 INTEGER, MIS03 INTEGER)"
    )
    conn.execute("CREATE TABLE NSCHEDIM (NUMERO_RIFERIMENTO TEXT, FLAG_RIMOSSO INTEGER, DESCRIZIONE TEXT)")
    # SCHEDIM1 is versioned: FLAG_RIMOSSO='0' = live spec, non-'0' = superseded.
    conn.execute("CREATE TABLE SCHEDIM1 (RIF_MISURA TEXT, VALORE_NOMINALE REAL, "
                 "SEGNO_TOLL_INF TEXT, TOLL_INF REAL, SEGNO_TOLL_SUP TEXT, TOLL_SUP REAL, "
                 "FLAG_RIMOSSO TEXT)")


def populate(conn, *, removed_ref=None):
    """Create + fill NRILDIM / NSCHEDIM / SCHEDIM1 in a sqlite connection.

    If ``removed_ref`` is given, that NUMERO_RIFERIMENTO is marked removed
    (minority FLAG_RIMOSSO value) to exercise the integrity gate.
    """
    _create_schema(conn)
    for r in _RAW_ROWS:
        row = list(r)
        row[3] = str(row[3])  # NUMERO_RIFERIMENTO as TEXT
        conn.execute("INSERT INTO NRILDIM VALUES (?,?,?,?,?,?,?,?,?)", row)

    # FLAG_RIMOSSO: majority 0 (live), 1 = removed (kept a clear minority even
    # after removed_ref marks one more row, so "least-occurring" stays == 1).
    conn.execute("INSERT INTO NSCHEDIM VALUES (?,?,?)", (str(NUMERO_RIFERIMENTO), 0, 'Test dimension'))
    for ref in ('5002', '5003', '5004', '5005', '5006'):
        conn.execute("INSERT INTO NSCHEDIM VALUES (?,?,?)", (ref, 0, 'Live dim ' + ref))
    conn.execute("INSERT INTO NSCHEDIM VALUES (?,?,?)", ('9999', 1, 'Removed dim'))
    if removed_ref is not None:
        conn.execute("UPDATE NSCHEDIM SET FLAG_RIMOSSO = 1 WHERE NUMERO_RIFERIMENTO = ?", (str(removed_ref),))

    # Two superseded rows (FLAG_RIMOSSO='1') carrying a stale placeholder nominal
    # of 0, plus the LIVE row (FLAG_RIMOSSO='0') with the real nominal — mirrors
    # production SCHEDIM1 and exercises _select_tolerance_row (must pick the live row).
    conn.execute("INSERT INTO SCHEDIM1 VALUES (?,?,?,?,?,?,?)",
                 (str(NUMERO_RIFERIMENTO), 0.0, '-', 0.5, '+', 0.5, '1'))
    conn.execute("INSERT INTO SCHEDIM1 VALUES (?,?,?,?,?,?,?)",
                 (str(NUMERO_RIFERIMENTO), 0.0, '-', 0.5, '+', 0.5, '1'))
    conn.execute("INSERT INTO SCHEDIM1 VALUES (?,?,?,?,?,?,?)",
                 (str(NUMERO_RIFERIMENTO), NOMINAL, '-', 0.5, '+', 0.5, '0'))
    conn.commit()


def sqlite_factory(conn):
    """Wrap an open sqlite connection as a connection_factory (context manager)."""
    @contextmanager
    def factory():
        yield conn
    return factory


def new_populated_connection(**kwargs):
    conn = sqlite3.connect(':memory:')
    populate(conn, **kwargs)
    return conn
