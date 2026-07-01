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

import pandas as pd

from app.functions.mosys import get_pervasive

logger = logging.getLogger(__name__)

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


def build_nrildim_query(filters):
    """Build the NRILDIM+NSCHEDIM SELECT and params from a filters dict.

    Mirrors routes.py index()/graph() query construction 1-to-1, including the
    default ``DATA_RILEVAMENTO LIKE '2025%'`` guard when no filter is supplied.
    Results are ordered chronologically (required for the chart and for
    flatten-picks neighbour ordering).
    """
    articolo = filters.get('articolo')
    numero_riferimento = filters.get('numero_riferimento')
    date_from = filters.get('date_from')
    date_to = filters.get('date_to')

    parts = [
        "SELECT NRILDIM.*, NSCHEDIM.DESCRIZIONE, NSCHEDIM.VALORE_NOMINALE ",
        "FROM STAAMPDB.NRILDIM NRILDIM ",
        "LEFT JOIN STAAMPDB.NSCHEDIM NSCHEDIM ON NRILDIM.NUMERO_RIFERIMENTO = NSCHEDIM.NUMERO_RIFERIMENTO ",
        "WHERE 1=1",
    ]
    params = []

    if articolo:
        parts.append("AND NRILDIM.ARTICOLO LIKE ?")
        params.append(f"{articolo}%")
    if numero_riferimento:
        parts.append("AND NRILDIM.NUMERO_RIFERIMENTO = ?")
        params.append(numero_riferimento)
    if date_from:
        parts.append("AND NRILDIM.DATA_RILEVAMENTO >= ?")
        params.append(str(date_from).replace('-', ''))
    if date_to:
        parts.append("AND NRILDIM.DATA_RILEVAMENTO <= ?")
        params.append(str(date_to).replace('-', ''))

    if not any([articolo, numero_riferimento, date_from, date_to]):
        parts.append("AND NRILDIM.DATA_RILEVAMENTO LIKE '2025%'")

    parts.append("ORDER BY NRILDIM.DATA_RILEVAMENTO, NRILDIM.ORA_RILEVAMENTO")
    return " ".join(parts), tuple(params)


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


def fetch_measurements(filters):
    """Fetch + format the filtered NRILDIM data. Returns a formatted DataFrame."""
    query, params = build_nrildim_query(filters)
    logger.info("fetch_measurements query=%s params=%s", query, params)
    df = get_pervasive(query, params=params)
    return format_measurements(df)


def fetch_tolerance(numero_riferimento):
    """Fetch VALORE_NOMINALE + USL/LSL from SCHEDIM1 for one dimension.

    Reuses the tolerance-operator math from routes.py L288-336 verbatim. Returns
    a dict ``{'nominal', 'usl', 'lsl'}`` with None values when unavailable.
    """
    result = {'nominal': None, 'usl': None, 'lsl': None}
    if not numero_riferimento:
        return result

    query = (
        "SELECT CODICE_ARTICOLO, RIF_MISURA, UN_MIS, VALORE_NOMINALE, "
        "SEGNO_TOLL_INF, TOLL_INF, SEGNO_TOLL_SUP, TOLL_SUP "
        "FROM STAAMPDB.SCHEDIM1 SCHEDIM1 WHERE SCHEDIM1.RIF_MISURA = ?"
    )
    tol = get_pervasive(query, params=(numero_riferimento,))
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
