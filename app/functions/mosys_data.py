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

# Display columns for the mosys_cli.py table printout, in order (ARTICOLO
# removed per spec.md; DESCRIZIONE from the NSCHEDIM enrichment replaces
# NUMERO_RIFERIMENTO).
DISPLAY_COLUMNS = ['DATA_RILEVAMENTO', 'ORA_RILEVAMENTO', 'DESCRIZIONE',
                   'NUMERO_STAMPATA', 'NUMERO_FIGURA'] + MIS_COLS

# Volume guard for the live DB (~4.5M NRILDIM rows). The SPC page refuses to
# build OR commit a tweak whose selection exceeds SPC_MAX_ROWS — the preview
# and the authoritative commit MUST see identical data, so both are bounded by
# the same ceiling (never by a silent TOP, which would corrupt the squeeze
# mean). Env-overridable for tuning on the RDP.
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
    """Build the NRILDIM SELECT and params from a filters dict.

    NO JOIN. The dimension caption (DESCRIZIONE / VALORE_NOMINALE) is attached
    afterwards by ``_enrich_dimension_metadata`` — NOT via a SQL join. The old
    inline ``LEFT JOIN STAAMPDB.NSCHEDIM`` was catastrophic on the live 4.5M-row
    table: the Pervasive/Actian optimizer ran the join BEFORE the WHERE filter,
    turning a small filtered read into a full-table join (multi-minute hang /
    endless spin). Verified empirically 2026-07-04 — every join variant timed out;
    every no-join variant returned in ~4–5s. (It was also silently WRONG:
    NSCHEDIM.NUMERO_RIFERIMENTO fans out — ~half the dimensions have >1 row — so
    the join multiplied every measurement row.)

    ``limit`` optionally caps the result to the newest ``limit`` rows (``TOP n``
    + descending order) — unused by the SPC page itself, which always needs
    the full chronological selection (kept safe by the caller's COUNT guard,
    not by truncation) since the chart and flatten-picks neighbour logic
    require chronological order.
    """
    where, params = _nrildim_where(filters)
    top = f"TOP {int(limit)} " if limit else ""
    order = ("ORDER BY NRILDIM.DATA_RILEVAMENTO DESC, NRILDIM.ORA_RILEVAMENTO DESC"
             if limit else
             "ORDER BY NRILDIM.DATA_RILEVAMENTO, NRILDIM.ORA_RILEVAMENTO")
    query = (
        f"SELECT {top}NRILDIM.* "
        "FROM STAAMPDB.NRILDIM NRILDIM "
        f"{where} {order}"
    )
    return query, tuple(params)


def _dimension_metadata():
    """The small NSCHEDIM dimension catalogue (~2,587 rows), de-duplicated to one
    row per NUMERO_RIFERIMENTO and indexed by it. Replaces the old inline NSCHEDIM
    LEFT JOIN (see build_nrildim_query). Fetched whole (param-less, ~0.4s warm)
    rather than by an IN-list so the query never scales with the number of
    dimensions in a result (which could blow a Pervasive parameter limit)."""
    look = get_pervasive(
        "SELECT NUMERO_RIFERIMENTO, DESCRIZIONE, VALORE_NOMINALE "
        "FROM STAAMPDB.NSCHEDIM NSCHEDIM")
    if look is None or look.empty or 'NUMERO_RIFERIMENTO' not in look.columns:
        return None
    look = look.copy()
    look['NUMERO_RIFERIMENTO'] = look['NUMERO_RIFERIMENTO'].astype(str).str.strip()
    # keep='first': collapse the fan-out to one caption per dimension. NEVER a
    # pandas merge / SQL join here — either would re-introduce the row multiplication.
    return look.drop_duplicates(subset='NUMERO_RIFERIMENTO', keep='first').set_index('NUMERO_RIFERIMENTO')


def _enrich_dimension_metadata(df):
    """Attach DESCRIZIONE + VALORE_NOMINALE to a raw NRILDIM frame by mapping the
    de-duplicated NSCHEDIM catalogue onto NUMERO_RIFERIMENTO (1-to-1, never a
    join). Missing dimensions map to None — the callers are None-safe."""
    if df is None or df.empty:
        return df
    df = df.copy()
    if 'NUMERO_RIFERIMENTO' not in df.columns:
        df['DESCRIZIONE'] = None
        df['VALORE_NOMINALE'] = None
        return df
    meta = _dimension_metadata()
    key = df['NUMERO_RIFERIMENTO'].astype(str).str.strip()
    if meta is None:
        df['DESCRIZIONE'] = None
        df['VALORE_NOMINALE'] = None
    else:
        df['DESCRIZIONE'] = key.map(meta['DESCRIZIONE'])
        df['VALORE_NOMINALE'] = key.map(meta['VALORE_NOMINALE'])
    return df


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


def fetch_part_numbers(offline_demo=False):
    """Distinct part numbers for the Measurements part-number dropdown.

    Sourced from the small SCHEDIM1 spec table (CODICE_ARTICOLO) so the initial
    page load is instant — NRILDIM's 4.5M rows are never scanned here. Returns a
    sorted list of strings. NB: this is the spec master, so some parts may have no
    measurements yet — the dependent dimension dropdown (measured-only) surfaces
    that by coming back empty."""
    if offline_demo:
        return _offline_part_numbers()
    df = get_pervasive("SELECT DISTINCT CODICE_ARTICOLO AS a FROM STAAMPDB.SCHEDIM1 SCHEDIM1")
    if df is None or df.empty or 'a' not in df.columns:
        return []
    return sorted({str(a).strip() for a in df['a'].dropna() if str(a).strip()})


def fetch_measured_dimensions(articolo, offline_demo=False):
    """Dimensions that ACTUALLY have measurements for a part number.

    Distinct NRILDIM.NUMERO_RIFERIMENTO for the article (an article-scoped scan,
    ~3-6s on the live 4.5M-row table — hence served by an on-demand AJAX endpoint,
    not the initial page load), captioned via the small NSCHEDIM catalogue. Only
    listing measured dimensions guarantees the subsequent 'Get data' fetch returns
    rows. Returns a list of ``{'numero_riferimento', 'descrizione'}`` sorted by
    caption."""
    if not articolo:
        return []
    if offline_demo:
        return _offline_measured_dimensions(articolo)
    df = get_pervasive(
        "SELECT DISTINCT NUMERO_RIFERIMENTO AS r FROM STAAMPDB.NRILDIM NRILDIM "
        "WHERE NRILDIM.ARTICOLO LIKE ?", params=(f"{articolo}%",))
    if df is None or df.empty or 'r' not in df.columns:
        return []
    meta = _dimension_metadata()
    return _caption_dimensions(df['r'], meta)


def _caption_dimensions(rif_series, meta):
    """Build sorted [{'numero_riferimento','descrizione'}] from a series of raw
    NUMERO_RIFERIMENTO values, captioning via the de-duplicated NSCHEDIM catalogue
    (falls back to the raw id when a dimension has no caption)."""
    out = []
    seen = set()
    for r in rif_series.dropna():
        rif = str(r).strip()
        if not rif or rif in seen:
            continue
        seen.add(rif)
        caption = rif
        if meta is not None and rif in meta.index:
            v = meta.loc[rif, 'DESCRIZIONE']
            if pd.notna(v) and str(v).strip():
                caption = str(v).strip()
        out.append({'numero_riferimento': rif, 'descrizione': caption})
    out.sort(key=lambda d: (str(d['descrizione']).lower(), d['numero_riferimento']))
    return out


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


def fetch_measurements(filters, offline_demo=False):
    """Fetch + format the filtered NRILDIM data. Returns a formatted DataFrame.

    Always the whole chronological selection — the SPC page is the only
    caller, and it must see everything it will preview/commit (kept safe by a
    COUNT guard, not truncation). When ``offline_demo`` is True the data comes
    from the fabricated synthetic SQLite (config.OFFLINE_DEMO) instead of the
    live DB — the live DB is never contacted in that mode.
    """
    if offline_demo:
        return format_measurements(_offline_measurements(filters))
    query, params = build_nrildim_query(filters)
    logger.info("fetch_measurements query=%s params=%s", query, params)
    df = get_pervasive(query, params=params)
    df = _enrich_dimension_metadata(df)   # replaces the removed NSCHEDIM join
    return format_measurements(df)


def _select_tolerance_row(tol):
    """Pick the LIVE SCHEDIM1 spec row for a dimension.

    SCHEDIM1 is versioned: it keeps superseded revisions (``FLAG_RIMOSSO`` truthy)
    alongside the one active row (``FLAG_RIMOSSO`` = '0'). The stale rows routinely
    carry a placeholder ``VALORE_NOMINALE`` of 0, so a blind ``iloc[0]`` returned a
    nominal of 0 for real dimensions (e.g. SB4600555200C 'DIAM 8,1' → 0 instead of
    8.1). Prefer the active row. NB: use a FIXED convention ('0'/blank = active),
    NOT mosys._resolve_removed_flag_value — that computes 'removed = least-occurring'
    which INVERTS on a per-RIF filtered set (2 removed + 1 active → active looks
    rarest). '0' can be a legitimate active nominal (defect-count dims), so this
    only drops removed rows; it never prefers non-zero over a genuine active zero."""
    if tol is None or tol.empty:
        return None
    if 'FLAG_RIMOSSO' in tol.columns:
        flag = tol['FLAG_RIMOSSO'].astype(str).str.strip().str.lower()
        active = tol[flag.isin(('0', '', 'nan', 'none'))]
        if not active.empty:
            return active.iloc[0]
    return tol.iloc[0]


def _tolerance_from_frame(tol):
    """Shared tolerance-operator math (routes.py L288-336) over the LIVE spec row."""
    result = {'nominal': None, 'usl': None, 'lsl': None}
    if tol is None or tol.empty:
        return result

    row = _select_tolerance_row(tol)
    if row is None:
        return result
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
        "SEGNO_TOLL_INF, TOLL_INF, SEGNO_TOLL_SUP, TOLL_SUP, FLAG_RIMOSSO "
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


def _offline_part_numbers():
    """Distinct part numbers from the synthetic NRILDIM (data-driven, like live)."""
    if not os.path.exists(_OFFLINE_DB):
        return []
    with sqlite3.connect(_OFFLINE_DB) as conn:
        df = pd.read_sql("SELECT DISTINCT ARTICOLO AS a FROM NRILDIM", conn)
    if df is None or df.empty:
        return []
    return sorted({str(a).strip() for a in df['a'].dropna() if str(a).strip()})


def _offline_measured_dimensions(articolo):
    """Measured dimensions for a part number from the synthetic NRILDIM + NSCHEDIM."""
    if not os.path.exists(_OFFLINE_DB):
        return []
    with sqlite3.connect(_OFFLINE_DB) as conn:
        nr = pd.read_sql(
            "SELECT DISTINCT NUMERO_RIFERIMENTO AS r FROM NRILDIM WHERE ARTICOLO LIKE ?",
            conn, params=(f"{articolo}%",))
        nsched = pd.read_sql("SELECT NUMERO_RIFERIMENTO, DESCRIZIONE FROM NSCHEDIM", conn)
    if nr is None or nr.empty:
        return []
    meta = None
    if nsched is not None and not nsched.empty:
        nsched = nsched.copy()
        nsched['NUMERO_RIFERIMENTO'] = nsched['NUMERO_RIFERIMENTO'].astype(str).str.strip()
        meta = nsched.drop_duplicates('NUMERO_RIFERIMENTO').set_index('NUMERO_RIFERIMENTO')
    return _caption_dimensions(nr['r'], meta)


def _offline_tolerance(numero_riferimento):
    """Read SCHEDIM1 tolerance row for one dimension from the synthetic SQLite."""
    if not os.path.exists(_OFFLINE_DB):
        return pd.DataFrame()
    with sqlite3.connect(_OFFLINE_DB) as conn:
        return pd.read_sql(
            "SELECT RIF_MISURA, VALORE_NOMINALE, SEGNO_TOLL_INF, TOLL_INF, "
            "SEGNO_TOLL_SUP, TOLL_SUP FROM SCHEDIM1 WHERE RIF_MISURA = ?",
            conn, params=(str(numero_riferimento),))
