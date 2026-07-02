r"""MOSYS NRILDIM command-line tool - run on the RDP where DSN=STAAMP_DB is live.

Purpose
-------
A terminal harness for the go-live gate: inspect real NRILDIM data (with the
same query/format code the web app uses), sanity-check the MIS scale and the
natural-key uniqueness, preview a squeeze/flatten tweak, and - only under an
explicit, confirmed, one-row-capped opt-in - perform a real write through the
full safe-write path (pre-image journal, atomic txn, rowcount==1, post-commit
verify + rollback).

It deliberately reuses the production modules (app.functions.mosys /
mosys_data / spc) rather than re-implementing anything, so a green run here
means the actual application code works against the live pyodbc driver.

Safety
------
* DRY-RUN IS THE DEFAULT. Nothing is ever written unless you pass --commit.
* --commit additionally requires a tweak (--squeeze / --flatten), an
  interactive typed confirmation, and refuses to touch more than --max-write
  rows (default 1) so the first live test is a single, supervised row.
* --dry-run and --commit are mutually exclusive.

PowerShell usage (on the RDP, venv active, STAAMP_DB reachable)
--------------------------------------------------------------
    # 1) Inspect data + scale/key gate (read-only, safe):
    .\venv\Scripts\python.exe scripts\mosys_cli.py `
        --articolo ART-1 --from-date 2025-01-01 --to-date 2025-03-30

    # 2) Preview a tweak without writing (read-only):
    .\venv\Scripts\python.exe scripts\mosys_cli.py `
        --articolo ART-1 --from-date 2025-01-01 --to-date 2025-03-30 `
        --numero-riferimento 5001 --squeeze 0.3 --dry-run

    # 3) Supervised ONE-ROW live write (writes to production; asks to confirm):
    .\venv\Scripts\python.exe scripts\mosys_cli.py `
        --articolo ART-1 --from-date 2025-06-01 --to-date 2025-06-01 `
        --numero-riferimento 5001 --squeeze 0.3 --commit
"""

import argparse
import logging
import os
import sys

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from app.functions import mosys, mosys_data, spc  # noqa: E402

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Quieten the app's own INFO chatter; keep the write path's messages visible.
logging.getLogger('app.functions.mosys_data').setLevel(logging.WARNING)


def _hr(title=''):
    line = '-' * 78
    print(f"\n{line}")
    if title:
        print(title)
        print(line)


def _parse_args(argv):
    p = argparse.ArgumentParser(
        prog='mosys_cli.py',
        description='Inspect / tweak / (optionally) write NRILDIM data on STAAMP_DB.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument('--articolo', help='ARTICOLO prefix filter (LIKE "value%%").')
    p.add_argument('--from-date', dest='from_date',
                   help='Earliest DATA_RILEVAMENTO, YYYY-MM-DD.')
    p.add_argument('--to-date', dest='to_date',
                   help='Latest DATA_RILEVAMENTO, YYYY-MM-DD.')
    p.add_argument('--numero-riferimento', dest='numero_riferimento',
                   help='NUMERO_RIFERIMENTO (dimension) - required for tolerance and any tweak.')
    p.add_argument('--squeeze', type=float, default=0.0,
                   help='Spread-squeeze fraction 0..0.9 (0 = no squeeze).')
    p.add_argument('--flatten', action='store_true',
                   help='Flatten picks (needs a nominal value).')
    p.add_argument('--threshold', type=float, default=spc.DEFAULT_PICK_THRESHOLD,
                   help=f'Pick threshold (default {spc.DEFAULT_PICK_THRESHOLD}).')
    p.add_argument('--limit', type=int, default=100,
                   help='Max rows to print in the data table (default 100).')
    p.add_argument('--max-write', type=int, default=1,
                   help='Refuse to write more than this many rows (default 1).')

    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true',
                      help='Show data / planned changes only. Never writes. (Default.)')
    mode.add_argument('--commit', action='store_true',
                      help='Perform a REAL write to production (asks to confirm).')
    return p.parse_args(argv)


def _fetch_raw(filters):
    """Raw NRILDIM+join frame (raw MIS ints + VALORE_NOMINALE) via the app's query."""
    query, params = mosys_data.build_nrildim_query(filters)
    print(f"Query : {query}")
    print(f"Params: {params}")
    return mosys.get_pervasive(query, params=params)


def _print_data(formatted, limit):
    cols = [c for c in mosys_data.DISPLAY_COLUMNS if c in formatted.columns]
    view = formatted[cols].head(limit)
    with pd.option_context('display.max_rows', None, 'display.width', 200,
                           'display.max_columns', None):
        print(view.to_string(index=False))
    if len(formatted) > limit:
        print(f"... ({len(formatted) - limit} more rows not shown; raise --limit)")


def _scale_and_key_gate(raw_df):
    """2.1 scale sanity (raw / 10000 ~ nominal) + natural-key uniqueness (plan 2.1)."""
    _hr('SCALE SANITY (raw vs raw/10000 vs nominal)')
    mis_cols = [c for c in mosys_data.MIS_COLS if c in raw_df.columns]
    nominal = None
    if 'VALORE_NOMINALE' in raw_df.columns and raw_df['VALORE_NOMINALE'].notna().any():
        nominal = float(raw_df['VALORE_NOMINALE'].dropna().iloc[0])
    print(f"{'MIS':<7}{'raw (first)':>14}{'raw/10000':>14}{'nominal':>12}{'  flag'}")
    for c in mis_cols:
        series = pd.to_numeric(raw_df[c], errors='coerce').dropna()
        if series.empty:
            continue
        raw0 = float(series.iloc[0])
        disp = raw0 / mosys_data.MIS_SCALE
        flag = ''
        if nominal:
            ratio = disp / nominal if nominal else 0
            if not (0.5 <= ratio <= 2.0):
                flag = '  <-- CHECK: not near nominal (scale?)'
        nom_str = f"{nominal:.4f}" if nominal is not None else '-'
        print(f"{c:<7}{raw0:>14.0f}{disp:>14.4f}{nom_str:>12}{flag}")
    if nominal is None:
        print("nominal unavailable (no VALORE_NOMINALE / numero_riferimento) - scale flag skipped")

    _hr('NATURAL-KEY UNIQUENESS')
    key_cols = [c for c in mosys_data.NATURAL_KEY_COLS if c in raw_df.columns]
    if not key_cols:
        print("no natural-key columns present")
        return
    dup = raw_df.duplicated(subset=key_cols, keep=False)
    n_dup = int(dup.sum())
    if n_dup == 0:
        print(f"OK - {len(raw_df)} rows are unique on {key_cols}")
    else:
        print(f"WARNING - {n_dup} rows share a natural key (write targeting would be ambiguous).")
        print(raw_df.loc[dup, key_cols].to_string(index=False))


def _raw_index(raw_df):
    """Map stripped-string natural-key tuple -> {MIS: raw int} for before/after."""
    key_cols = [c for c in mosys_data.NATURAL_KEY_COLS if c in raw_df.columns]
    mis_cols = [c for c in mosys_data.MIS_COLS if c in raw_df.columns]
    idx = {}
    for _, row in raw_df.iterrows():
        k = tuple(str(row[c]).strip() for c in key_cols)
        idx[k] = {c: row[c] for c in mis_cols}
    return key_cols, idx


def _print_planned(updates, raw_df):
    _hr(f'PLANNED CHANGES ({len(updates)} row(s))')
    if not updates:
        print("No cells change at these settings.")
        return
    key_cols, idx = _raw_index(raw_df)
    for u in updates:
        key = u['key']
        ktuple = tuple(str(key.get(c, '')).strip() for c in key_cols)
        before = idx.get(ktuple, {})
        keystr = ' | '.join(f"{c}={key.get(c)}" for c in key_cols)
        print(f"\n  {keystr}")
        for mis, new_raw in sorted(u['new_raw'].items()):
            old_raw = before.get(mis)
            old_disp = (float(old_raw) / mosys_data.MIS_SCALE) if old_raw is not None else None
            new_disp = float(new_raw) / mosys_data.MIS_SCALE
            old_s = f"{old_disp:.4f}" if old_disp is not None else '?'
            print(f"    {mis}: {old_s} -> {new_disp:.4f}   (raw {old_raw} -> {new_raw})")


def _print_report(report):
    _hr(f"WRITE REPORT - status: {report['status'].upper()}")
    print(f"batch_id       : {report['batch_id']}")
    print(f"requested      : {report['requested']}")
    print(f"planned        : {len(report['planned'])}")
    print(f"updated_rows   : {report['updated_rows']}")
    if report['integrity_failures']:
        print(f"integrity_fail : {report['integrity_failures']}")
    if report['error']:
        print(f"note           : {report['error']}")
    for p in report['planned']:
        mark = 'ok' if p['would_match'] == 1 else f"** would match {p['would_match']} rows **"
        print(f"  - matches {p['would_match']} row(s) [{mark}]  {p['key']}")


def main(argv=None):
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    filters = {
        'articolo': args.articolo,
        'numero_riferimento': args.numero_riferimento,
        'date_from': args.from_date,
        'date_to': args.to_date,
    }
    writing = bool(args.commit)  # dry-run is the default for everything else

    print("MOSYS NRILDIM CLI")
    print(f"Mode  : {'COMMIT (LIVE WRITE)' if writing else 'DRY-RUN (read-only)'}")
    print(f"Filter: articolo={args.articolo!r} from={args.from_date!r} "
          f"to={args.to_date!r} numero_riferimento={args.numero_riferimento!r}")

    _hr('FETCHING FROM STAAMP_DB')
    try:
        raw_df = _fetch_raw(filters)
    except Exception as exc:  # noqa: BLE001
        print(f"\nERROR: could not read from STAAMP_DB: {exc}")
        print("Check the DSN, that the database engine is running, and network reachability.")
        return 2

    if raw_df is None or raw_df.empty:
        print("\nNo rows matched the filters - nothing to show or write.")
        return 0
    print(f"\nFetched {len(raw_df)} row(s).")

    formatted = mosys_data.format_measurements(raw_df)

    _hr('DATA (display values, MIS / 10000)')
    _print_data(formatted, args.limit)

    _scale_and_key_gate(raw_df)

    # ---- Tweak preview (if requested) ----
    tweak_requested = args.squeeze > 0 or args.flatten
    updates = []
    if tweak_requested:
        tol = mosys_data.fetch_tolerance(args.numero_riferimento) if args.numero_riferimento \
            else {'nominal': None, 'usl': None, 'lsl': None}
        updates = spc.compute_tweaked_updates(
            formatted, args.squeeze, flatten=args.flatten,
            threshold=args.threshold, nominal=tol['nominal'])
        _print_planned(updates, raw_df)
    else:
        _hr('TWEAK')
        print("No --squeeze / --flatten given - inspection only.")

    # ---- Dry-run: show the plan via the real write path, never writing ----
    if not writing:
        if updates:
            try:
                report = mosys.execute_nrildim_updates(updates, dry_run=True)
                _print_report(report)
            except Exception as exc:  # noqa: BLE001 - dry-run must never crash
                print(f"\n(planned-write probe could not run: {exc})")
        _hr()
        print("DRY-RUN complete. Nothing was written. Add --commit to write for real.")
        return 0

    # ---- Commit path: guard rails ----
    if not tweak_requested:
        print("\nRefusing to --commit without a tweak (--squeeze and/or --flatten). Nothing written.")
        return 2
    if not updates:
        print("\nThe tweak changes no cells at these settings - nothing to write.")
        return 0
    if len(updates) > args.max_write:
        print(f"\nRefusing to write {len(updates)} rows (--max-write={args.max_write}).")
        print("Narrow the filters (article + single date + numero-riferimento) for a one-row")
        print("smoke test, or raise --max-write once you have proven a single row round-trips.")
        return 2

    _hr('CONFIRM LIVE WRITE TO PRODUCTION')
    print(f"About to update {len(updates)} NRILDIM row(s) on STAAMP_DB.")
    print("The safe-write path will journal pre-images, apply atomically, verify, and")
    print("roll back on any anomaly. This still modifies PRODUCTION data.")
    answer = input("Type 'WRITE' (all caps) to proceed, anything else to abort: ").strip()
    if answer != 'WRITE':
        print("Aborted by user. Nothing was written.")
        return 1

    try:
        report = mosys.execute_nrildim_updates(updates, dry_run=False)
    except mosys.WriteError as exc:
        print(f"\nWRITE FAILED (rolled back, pre-image journal retained): {exc}")
        return 3
    _print_report(report)
    _hr()
    if report['status'] == 'committed':
        print(f"COMMITTED - {report['updated_rows']} row(s) updated and verified.")
    else:
        print(f"Finished with status: {report['status']}. No partial commit occurred.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
