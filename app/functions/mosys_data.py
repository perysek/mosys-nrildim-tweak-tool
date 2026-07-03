"""Shared NRILDIM fetch + format pipeline.

Single source of truth for the read side of the Measurements and SPC-Tweaks
pages, so the table and the chart provably read identical data (advisor note:
one shared helper, not two copies). Every formatting rule here is reused
**1-to-1 from app/routes.py** (IMPLEMENTATION-PLAN.md §3.4) — divergence from
routes.py is a bug, not a choice.

Crucially, this helper preserves the *raw* key columns
(ARTICOLO, DATA_RILEVAMENTO, ORA_RILEVAMENTO, NUMERO_RIFERIMENTO,
NUMERO_STAMPATA, NUMERO_FIGURA) alongside the display-formatted columns, because
the safe-write path must target rows on their raw natural key — never on the
display-formatted values (§2.4).
"""

import logging
import os
import sqlite3

import pandas as pd

from app.functions.mosys import get_pervasive

logger = logging.getLogger(__name__)

# Offline-demo data source (see config.OFFLINE_DEMO). Fabricated sample data for
# click-testing the UI WITHOUT the Pervasive DSN. Never a stand-in for real data
# — callers must pass offline_demo=True explicitly, and the pages banner it.
_OFFLINE_DB = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'app', 'data', 'mock_mosys_synthetic.sqlite')

# MIS raw<->display scale factor. Authoritative = 10000 (routes.py L176/L268);
# spec.md's "1000" was a documentation typo (IMPLEMENTATION-PLAN.md §2.1).
MIS_SCALE = 10000.0

MIS_COLS = ['MIS01', 'MIS02', 'MIS03', 'MIS04', 'MIS05',
            'MIS06', 'MIS07', 'MIS08', 'MIS09', 'MIS10']

# Natural-key columns (RAW, DB-stored form) used to target a single NRILDIM row
# for updates. Confirmed/narrowed against the mock in Phase 1 (§2.4).
NATURAL_KEY_COLS = ['ARTICOLO', 'DATA_RILEVAMENTO', 'ORA_RILEVAMENTO',
                    'NUMERO_RIFERIMENTO', 'NUMERO_STAMPATA', 'NUMERO_FIGURA']

# User-friendly captions (routes.py COLUMN_LABELS + spec.md aliases).
COLUMN_LABELS = {
    'DATA_RILEVAMENTO': 'Measurement date',
    'ORA_RILEVAMENTO': 'Measurement time',
    'DESCRIZIONE': 'Drawing specification',
    'NUMERO_STAMPATA': 'Shot number',
    'NUMERO_FIGURA': 'Cavity number',
    'MIS01': 'Measurement 1', 'MIS02': 'Measurement 2', 'MIS03': 'Measurement 3',
    'MIS04': 'Measurement 4', 'MIS05': 'Measurement 5', 'MIS06': 'Measurement 6',
    'MIS07': 'Measurement 7', 'MIS08': 'Measurement 8', 'MIS09': 'Measurement 9',
    'MIS10': 'Measurement 10',
}

# Display columns shown in the Measurements table, in order (ARTICOLO removed per
# spec.md; DESCRIZIONE from the NSCHEDIM join replaces NUMERO_RIFERIMENTO).
DISPLAY_COLUMNS = ['DATA_RILEVAMENTO', 'ORA_RILEVAMENTO', 'DESCRIZIONE',
                   'NUMERO_STAMPATA', 'NUMERO_FIGURA'] + MIS_COLS

# Volume guards for the live DB (~4.5M NRILDIM rows). The Measurements browse
# table pulls at most BROWSE_ROW_CAP rows (newest first) so a no/broad-filter
# visit can never drag the whole table into pandas/the browser. The SPC page
# refuses to build OR commit a tweak whose selection exceeds SPC_MAX_ROWS — the
# preview and the authoritative commit MUST see identical data, so both are
# bounded by the same ceiling (never by a silent TOP, which would corrupt the
# squeeze mean). Both are env-overridable for tuning on the RDP.
BROWSE_ROW_CAP = int(os.environ.get('MOSYS_BROWSE_ROW_CAP', '5000') or '5000')
SPC_MAX_ROWS = int(os.environ.get('MOSYS_SPC_MAX_ROWS', '50000') or '50000')


def _nrildim_where(filters):
    """Shared WHERE clause + params for the NRILDIM filter (reused by the data
    query and the COUNT guard so they always agree on what a selection means)."""
    parts = ["WHERE 1=1"]
    params = []
    if filters.get('articolo'):
        parts.append("AND NRILDIM.ARTICOLO LIKE ?")
        params.append(f"{filters['articolo']}%")
    if filters.get('numero_riferimento'):
        parts.append("AND NRILDIM.NUMERO_RIFERIMENTO = ?")
        params.append(filters['numero_riferimento'])
    if filters.get('date_from'):
        parts.append("AND NRILDIM.DATA_RILEVAMENTO >= ?")
        params.append(str(filters['date_from']).replace('-', ''))
    if filters.get('date_to'):
        parts.append("AND NRILDIM.DATA_RILEVAMENTO <= ?")
        params.append(str(filters['date_to']).replace('-', ''))
    return " ".join(parts), params


def build_nrildim_query(filters, limit=None):
    """Build the NRILDIM+NSCHEDIM SELECT and params from a filters dict.

    Mirrors routes.py index()/graph() query construction. When ``limit`` is set
    (the Measurements browse path) the query returns at most that many rows,
    NEWEST first (``TOP n`` + descending order) — a bounded, recent-history view.
    When ``limit`` is None (the SPC path) results stay in chronological order,
    which the chart and flatten-picks neighbour logic require; that path is kept
    safe by the caller's COUNT guard, not by truncation.
    """
    where, params = _nrildim_where(filters)
    top = f"TOP {int(limit)} " if limit else ""
    order = ("ORDER BY NRILDIM.DATA_RILEVAMENTO DESC, NRILDIM.ORA_RILEVAMENTO DESC"
             if limit else
             "ORDER BY NRILDIM.DATA_RILEVAMENTO, NRILDIM.ORA_RILEVAMENTO")
    query = (
        f"SELECT {top}NRILDIM.*, NSCHEDIM.DESCRIZIONE, NSCHEDIM.VALORE_NOMINALE "
        "FROM STAAMPDB.NRILDIM NRILDIM "
        "LEFT JOIN STAAMPDB.NSCHEDIM NSCHEDIM ON NRILDIM.NUMERO_RIFERIMENTO = NSCHEDIM.NUMERO_RIFERIMENTO "
        f"{where} {order}"
    )
    return query, tuple(params)


def count_nrildim(filters):
    """COUNT(*) of NRILDIM rows matching the filter — a cheap pre-flight guard
    run before an uncapped SPC fetch/commit so we never pull (or write) a set
    that is too large to tweak safely. No join needed (WHERE is NRILDIM-only)."""
    where, params = _nrildim_where(filters)
    query = f"SELECT COUNT(*) AS n FROM STAAMPDB.NRILDIM NRILDIM {where}"
    df = get_pervasive(query, params=tuple(params))
    if df is None or df.empty:
        return 0
    return int(df.iloc[0]['n'])


def format_measurements(df):
    """Format a raw NRILDIM DataFrame for display, preserving raw key columns.

    Adds RAW_* copies of the key columns *before* mutating the display columns,
    so the write path can target rows on their true stored values. All display
    transforms (÷10000, date/time formatting, last-digit shot/cavity) are reused
    1-to-1 from routes.py.
    """
    if df is None or df.empty:
        return df

    df = df.copy()

    # Preserve RAW key columns for write-targeting (before any reformatting).
    for col in NATURAL_KEY_COLS:
        if col in df.columns:
            df['RAW_' + col] = df[col].astype(str).str.strip()

    # DATA_RILEVAMENTO: YYYYMMDD -> YYYY-MM-DD (routes.py L141-148).
    if 'DATA_RILEVAMENTO' in df.columns:
        df['DATA_RILEVAMENTO'] = df['DATA_RILEVAMENTO'].astype(str).str.strip()
        mask = df['DATA_RILEVAMENTO'].str.len() == 8
        df.loc[mask, 'DATA_RILEVAMENTO'] = (
            df.loc[mask, 'DATA_RILEVAMENTO'].str[:4] + '-'
            + df.loc[mask, 'DATA_RILEVAMENTO'].str[4:6] + '-'
            + df.loc[mask, 'DATA_RILEVAMENTO'].str[6:8]
        )

    # ORA_RILEVAMENTO: HHMMSS -> HH:MM:SS (routes.py L151-162).
    if 'ORA_RILEVAMENTO' in df.columns:
        df['ORA_RILEVAMENTO'] = df['ORA_RILEVAMENTO'].astype(str).str.strip()
        mask_t = df['ORA_RILEVAMENTO'].str.len() == 6
        df.loc[mask_t, 'ORA_RILEVAMENTO'] = (
            df.loc[mask_t, 'ORA_RILEVAMENTO'].str[:2] + ':'
            + df.loc[mask_t, 'ORA_RILEVAMENTO'].str[2:4] + ':'
            + df.loc[mask_t, 'ORA_RILEVAMENTO'].str[4:6]
        )

    # Last-digit shot / cavity (routes.py L166-169).
    if 'NUMERO_STAMPATA' in df.columns:
        df['NUMERO_STAMPATA'] = df['NUMERO_STAMPATA'].astype(str).str.strip().str[-1:]
    if 'NUMERO_FIGURA' in df.columns:
        df['NUMERO_FIGURA'] = df['NUMERO_FIGURA'].astype(str).str.strip().str[-1:]

    # MIS columns: numeric, ÷10000 (routes.py L173-176).
    mis_in_df = [c for c in MIS_COLS if c in df.columns]
    if mis_in_df:
        df[mis_in_df] = df[mis_in_df].apply(pd.to_numeric, errors='coerce') / MIS_SCALE

    # Per-row average of non-empty MIS cells (routes.py L271).
    if mis_in_df:
        df['MIS_AVG'] = df[mis_in_df].mean(axis=1, skipna=True)

    # Chronological datetime label (routes.py L274-276) — used by the chart and
    # flatten-picks ordering.
    if 'RAW_DATA_RILEVAMENTO' in df.columns and 'RAW_ORA_RILEVAMENTO' in df.columns:
        ora = df['RAW_ORA_RILEVAMENTO'].astype(str).str.strip().str.zfill(6)
        df['DATETIME'] = (
            df['DATA_RILEVAMENTO'].astype(str) + ' '
            + ora.str[:2] + ':' + ora.str[2:4] + ':' + ora.str[4:6]
        )

    return df


def valid_mis_columns(df):
    """MIS columns that are present and have at least one non-null value."""
    return [c for c in MIS_COLS if c in df.columns and df[c].notna().any()]


def fetch_measurements(filters, offline_demo=False, limit=None):
    """Fetch + format the filtered NRILDIM data. Returns a formatted DataFrame.

    ``limit`` bounds the browse path (newest ``limit`` rows); leave it None for
    the SPC path, which must see the whole chronological selection (kept safe by
    a COUNT guard, not truncation). When ``offline_demo`` is True the data comes
    from the fabricated synthetic SQLite (config.OFFLINE_DEMO) instead of the
    live DB — the live DB is never contacted in that mode.
    """
    if offline_demo:
        df = _offline_measurements(filters)
        if limit and df is not None and not df.empty:
            df = df.tail(int(limit)).reset_index(drop=True)  # newest rows
        return format_measurements(df)
    query, params = build_nrildim_query(filters, limit=limit)
    logger.info("fetch_measurements query=%s params=%s", query, params)
    df = get_pervasive(query, params=params)
    return format_measurements(df)


def _tolerance_from_frame(tol):
    """Shared tolerance-operator math (routes.py L288-336) over a 1-row frame."""
    result = {'nominal': None, 'usl': None, 'lsl': None}
    if tol is None or tol.empty:
        return result

    row = tol.iloc[0]
    nominal = float(row['VALORE_NOMINALE']) if pd.notna(row['VALORE_NOMINALE']) else None
    if nominal is None:
        return result

    seg_inf = str(row['SEGNO_TOLL_INF']).strip() if pd.notna(row['SEGNO_TOLL_INF']) else '+'
    toll_inf = float(row['TOLL_INF']) if pd.notna(row['TOLL_INF']) else 0.0
    seg_sup = str(row['SEGNO_TOLL_SUP']).strip() if pd.notna(row['SEGNO_TOLL_SUP']) else '+'
    toll_sup = float(row['TOLL_SUP']) if pd.notna(row['TOLL_SUP']) else 0.0

    limit_inf = nominal - toll_inf if seg_inf == '-' else nominal + toll_inf
    limit_sup = nominal - toll_sup if seg_sup == '-' else nominal + toll_sup

    result['nominal'] = nominal
    result['usl'] = max(limit_inf, limit_sup)
    result['lsl'] = min(limit_inf, limit_sup)
    return result


def fetch_tolerance(numero_riferimento, offline_demo=False):
    """Fetch VALORE_NOMINALE + USL/LSL from SCHEDIM1 for one dimension.

    Reuses the tolerance-operator math from routes.py L288-336 verbatim. Returns
    a dict ``{'nominal', 'usl', 'lsl'}`` with None values when unavailable.
    """
    if not numero_riferimento:
        return {'nominal': None, 'usl': None, 'lsl': None}

    if offline_demo:
        return _tolerance_from_frame(_offline_tolerance(numero_riferimento))

    query = (
        "SELECT CODICE_ARTICOLO, RIF_MISURA, UN_MIS, VALORE_NOMINALE, "
        "SEGNO_TOLL_INF, TOLL_INF, SEGNO_TOLL_SUP, TOLL_SUP "
        "FROM STAAMPDB.SCHEDIM1 SCHEDIM1 WHERE SCHEDIM1.RIF_MISURA = ?"
    )
    tol = get_pervasive(query, params=(numero_riferimento,))
    return _tolerance_from_frame(tol)


# --------------------------------------------------------------------------
#  Offline demo readers (fabricated SQLite; only reached when offline_demo=True)
# --------------------------------------------------------------------------

def _offline_measurements(filters):
    """Read fabricated NRILDIM rows from the synthetic SQLite, shaped to match
    the live query (NRILDIM.* + DESCRIZIONE + VALORE_NOMINALE), then filtered."""
    if not os.path.exists(_OFFLINE_DB):
        logger.warning("offline demo requested but %s is missing", _OFFLINE_DB)
        return pd.DataFrame()

    with sqlite3.connect(_OFFLINE_DB) as conn:
        df = pd.read_sql(
            "SELECT n.*, s.DESCRIZIONE, sc.VALORE_NOMINALE "
            "FROM NRILDIM n "
            "LEFT JOIN NSCHEDIM s ON n.NUMERO_RIFERIMENTO = s.NUMERO_RIFERIMENTO "
            "LEFT JOIN SCHEDIM1 sc ON n.NUMERO_RIFERIMENTO = sc.RIF_MISURA "
            "ORDER BY n.DATA_RILEVAMENTO, n.ORA_RILEVAMENTO", conn)

    # Apply the same filters as build_nrildim_query, in-frame (small data set).
    articolo = filters.get('articolo')
    if articolo:
        df = df[df['ARTICOLO'].astype(str).str.startswith(str(articolo))]
    numero_riferimento = filters.get('numero_riferimento')
    if numero_riferimento:
        df = df[df['NUMERO_RIFERIMENTO'].astype(str) == str(numero_riferimento)]
    date_from = filters.get('date_from')
    if date_from:
        df = df[df['DATA_RILEVAMENTO'].astype(str) >= str(date_from).replace('-', '')]
    date_to = filters.get('date_to')
    if date_to:
        df = df[df['DATA_RILEVAMENTO'].astype(str) <= str(date_to).replace('-', '')]
    return df.reset_index(drop=True)


def _offline_tolerance(numero_riferimento):
    """Read SCHEDIM1 tolerance row for one dimension from the synthetic SQLite."""
    if not os.path.exists(_OFFLINE_DB):
        return pd.DataFrame()
    with sqlite3.connect(_OFFLINE_DB) as conn:
        return pd.read_sql(
            "SELECT RIF_MISURA, VALORE_NOMINALE, SEGNO_TOLL_INF, TOLL_INF, "
            "SEGNO_TOLL_SUP, TOLL_SUP FROM SCHEDIM1 WHERE RIF_MISURA = ?",
            conn, params=(str(numero_riferimento),))
