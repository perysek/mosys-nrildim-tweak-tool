"""Read-only mock-data harness (IMPLEMENTATION-PLAN.md Phase 1).

Pulls the latest 100 NRILDIM rows + their linked NSCHEDIM / SCHEDIM1 rows from
the live Pervasive DSN using the existing READ-ONLY get_pervasive() path, writes
them to a local SQLite snapshot (app/data/mock_mosys.sqlite), and emits
scripts/mock_report.md with:

  * the real NRILDIM column list + dtypes,
  * a natural-key uniqueness assertion over the 100 rows,
  * the §2.1 scale sanity table (raw MIS int vs raw/10000 vs VALORE_NOMINALE).

This script performs NO writes to Pervasive. It is the human process gate that
must pass before the Phase 5 live-write flag (MOSYS_WRITE_ENABLED) is flipped.

Run it yourself against the DSN — e.g. from the project root:

    ! python scripts/build_mock_data.py
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.functions.mosys import get_pervasive  # noqa: E402
from app.functions.mosys_data import MIS_COLS, NATURAL_KEY_COLS, MIS_SCALE  # noqa: E402

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'app', 'data')
SQLITE_PATH = os.path.join(DATA_DIR, 'mock_mosys.sqlite')
REPORT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mock_report.md')


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    print("Fetching latest 100 NRILDIM rows (read-only)…")
    nrildim = get_pervasive(
        "SELECT TOP 100 * FROM STAAMPDB.NRILDIM NRILDIM "
        "ORDER BY NRILDIM.DATA_RILEVAMENTO DESC, NRILDIM.ORA_RILEVAMENTO DESC"
    )
    if nrildim is None or nrildim.empty:
        print("No NRILDIM rows returned — aborting.")
        return 1

    refs = [r for r in nrildim['NUMERO_RIFERIMENTO'].dropna().unique().tolist()] \
        if 'NUMERO_RIFERIMENTO' in nrildim.columns else []

    nschedim = pd.DataFrame()
    schedim1 = pd.DataFrame()
    if refs:
        placeholders = ', '.join('?' for _ in refs)
        print(f"Fetching linked NSCHEDIM / SCHEDIM1 for {len(refs)} dimensions…")
        try:
            nschedim = get_pervasive(
                f"SELECT * FROM STAAMPDB.NSCHEDIM WHERE NUMERO_RIFERIMENTO IN ({placeholders})",
                params=tuple(refs))
        except Exception as exc:  # noqa: BLE001
            print(f"  NSCHEDIM fetch failed: {exc}")
        try:
            schedim1 = get_pervasive(
                f"SELECT * FROM STAAMPDB.SCHEDIM1 WHERE RIF_MISURA IN ({placeholders})",
                params=tuple(refs))
        except Exception as exc:  # noqa: BLE001
            print(f"  SCHEDIM1 fetch failed: {exc}")

    # ---- Write SQLite snapshot ----
    import sqlite3
    if os.path.exists(SQLITE_PATH):
        os.remove(SQLITE_PATH)
    conn = sqlite3.connect(SQLITE_PATH)
    try:
        nrildim.to_sql('NRILDIM', conn, index=False)
        if not nschedim.empty:
            nschedim.to_sql('NSCHEDIM', conn, index=False)
        if not schedim1.empty:
            schedim1.to_sql('SCHEDIM1', conn, index=False)
    finally:
        conn.close()
    print(f"Wrote snapshot -> {SQLITE_PATH}")

    # ---- Natural-key uniqueness ----
    key_cols = [c for c in NATURAL_KEY_COLS if c in nrildim.columns]
    dup = nrildim.duplicated(subset=key_cols).sum() if key_cols else -1
    key_unique = (dup == 0)

    # ---- Scale sanity table ----
    nominal_by_ref = {}
    if not nschedim.empty and 'NUMERO_RIFERIMENTO' in nschedim.columns and 'VALORE_NOMINALE' in nschedim.columns:
        for _, r in nschedim.iterrows():
            nominal_by_ref[r['NUMERO_RIFERIMENTO']] = r['VALORE_NOMINALE']

    sample_rows = []
    mis_present = [c for c in MIS_COLS if c in nrildim.columns]
    for _, row in nrildim.head(15).iterrows():
        for col in mis_present:
            raw = row[col]
            if pd.isna(raw):
                continue
            try:
                raw_int = int(float(raw))
            except (TypeError, ValueError):
                continue
            nominal = nominal_by_ref.get(row.get('NUMERO_RIFERIMENTO'))
            sample_rows.append((col, raw_int, raw_int / MIS_SCALE, nominal))
            break

    lines = []
    lines.append("# Mock report — NRILDIM safe-write pre-flight\n")
    lines.append(f"- NRILDIM rows captured: **{len(nrildim)}**")
    lines.append(f"- Linked NSCHEDIM rows: **{len(nschedim)}**, SCHEDIM1 rows: **{len(schedim1)}**")
    lines.append(f"- SQLite snapshot: `{SQLITE_PATH}`\n")

    lines.append("## Columns & dtypes\n")
    for col in nrildim.columns:
        lines.append(f"- `{col}` — {nrildim[col].dtype}")
    lines.append("")

    lines.append("## Natural-key uniqueness (§2.4)\n")
    lines.append(f"- Key columns: `{key_cols}`")
    lines.append(f"- Duplicate rows on key: **{dup}**")
    lines.append(f"- **{'PASS' if key_unique else 'FAIL'}** — key {'uniquely targets 1 row' if key_unique else 'is NOT unique — DO NOT enable writes'}\n")

    lines.append("## Scale sanity (§2.1) — raw / 10000 should sit near nominal\n")
    lines.append("| MIS col | raw int | raw / 10000 | VALORE_NOMINALE |")
    lines.append("|---|---|---|---|")
    for col, raw_int, scaled, nominal in sample_rows:
        lines.append(f"| {col} | {raw_int} | {scaled:.4f} | {nominal} |")
    lines.append("")
    lines.append("> Confirm the `raw / 10000` column is the same order of magnitude as "
                 "`VALORE_NOMINALE` (not ~10x off). If it is off by 10x, the scale factor is "
                 "wrong and the write path must stay disabled.\n")

    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    print(f"Wrote report -> {REPORT_PATH}")
    print(f"\nNatural key unique: {key_unique}. Review {REPORT_PATH} before enabling writes.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
