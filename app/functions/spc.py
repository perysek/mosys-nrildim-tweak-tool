"""SPC statistics + tweak transforms (pure functions over pandas DataFrames).

Net-new business logic per IMPLEMENTATION-PLAN.md §3.3 / §3.3.1. Kept free of any
DB dependency so it is fully unit-testable offline against a synthetic mock.

Grouping is **NUMERO_FIGURA only** (§2.6 / D8), matching routes.py. All values
here are in *display scale* (MIS already ÷10000 by mosys_data.format_measurements);
raw-integer conversion for writes happens only in compute_tweaked_updates via
round(value * MIS_SCALE).
"""

import math

import pandas as pd

from app.functions.mosys_data import MIS_COLS, MIS_SCALE, NATURAL_KEY_COLS

# Flatten-picks constants (§3.3.1). A pick is DETECTED by neighbour deviation, but
# is FLATTENED onto the group's clean baseline (mean of the non-pick values) —
# user directive 2026-07-04, superseding the old neighbour-average +/-10% nudge.
DEFAULT_PICK_THRESHOLD = 0.25   # a point >25% off its neighbour average is a "pick"
_NB_EPS = 1e-9                  # guard against neighbour-average ~ 0 (advisor note)


def _mis_in(df):
    return [c for c in MIS_COLS if c in df.columns]


def group_series(df):
    """Per-NUMERO_FIGURA chart series of the row-average (MIS_AVG).

    Returns ``{figura: {'labels': [...datetime...], 'values': [...avg...]}}``,
    ordered chronologically, mirroring routes.py graph() chart_data.
    """
    out = {}
    if df is None or df.empty or 'NUMERO_FIGURA' not in df.columns:
        return out
    avg = df['MIS_AVG'] if 'MIS_AVG' in df.columns else df[_mis_in(df)].mean(axis=1, skipna=True)
    work = df.assign(_AVG=avg)
    for figura in work['NUMERO_FIGURA'].dropna().unique().tolist():
        sub = work[work['NUMERO_FIGURA'] == figura].dropna(subset=['_AVG'])
        if 'DATETIME' in sub.columns:
            sub = sub.sort_values('DATETIME')
        out[str(figura)] = {
            'labels': sub['DATETIME'].tolist() if 'DATETIME' in sub.columns else list(range(len(sub))),
            'values': [round(float(v), 3) for v in sub['_AVG'].tolist()],
        }
    return out


def footer_stats(df):
    """Footer statistics for the Measurements page (§Phase 2).

    Total row count + the average, across NUMERO_FIGURA groups, of each group's
    (min, max, range) of the row-average — computed over the ENTIRE result set,
    not just visible rows.
    """
    stats = {'total_rows': 0, 'avg_min': None, 'avg_max': None, 'avg_range': None}
    if df is None or df.empty:
        return stats
    stats['total_rows'] = int(len(df))
    if 'NUMERO_FIGURA' not in df.columns:
        return stats
    avg = df['MIS_AVG'] if 'MIS_AVG' in df.columns else df[_mis_in(df)].mean(axis=1, skipna=True)
    work = df.assign(_AVG=avg).dropna(subset=['_AVG'])
    if work.empty:
        return stats
    grouped = work.groupby('NUMERO_FIGURA')['_AVG']
    mins = grouped.min()
    maxs = grouped.max()
    ranges = maxs - mins
    stats['avg_min'] = round(float(mins.mean()), 3)
    stats['avg_max'] = round(float(maxs.mean()), 3)
    stats['avg_range'] = round(float(ranges.mean()), 3)
    return stats


def capability(df, usl, lsl):
    """Per-NUMERO_FIGURA Cp/Cpk + mean/std over MIS_AVG (routes.py L348-379)."""
    out = {}
    if df is None or df.empty or usl is None or lsl is None or 'NUMERO_FIGURA' not in df.columns:
        return out
    avg = df['MIS_AVG'] if 'MIS_AVG' in df.columns else df[_mis_in(df)].mean(axis=1, skipna=True)
    work = df.assign(_AVG=avg)
    for figura in work['NUMERO_FIGURA'].dropna().unique().tolist():
        vals = work[work['NUMERO_FIGURA'] == figura]['_AVG'].dropna()
        if len(vals) <= 1:
            continue
        mean = float(vals.mean())
        std = float(vals.std())
        if std <= 0:
            continue
        cp = (usl - lsl) / (6 * std)
        cpk = min((usl - mean) / (3 * std), (mean - lsl) / (3 * std))
        out[str(figura)] = {
            'cp': round(cp, 3), 'cpk': round(cpk, 3),
            'mean': round(mean, 3), 'std': round(std, 3),
        }
    return out


def overall_capability(df, usl, lsl):
    """Single Cp/Cpk/min/avg/max/range summary over all rows (SPC badge header)."""
    summary = {'cp': None, 'cpk': None, 'min': None, 'avg': None, 'max': None, 'range': None}
    if df is None or df.empty:
        return summary
    avg = df['MIS_AVG'] if 'MIS_AVG' in df.columns else df[_mis_in(df)].mean(axis=1, skipna=True)
    vals = avg.dropna()
    if vals.empty:
        return summary
    vmin, vmax, vmean = float(vals.min()), float(vals.max()), float(vals.mean())
    summary.update({'min': round(vmin, 3), 'avg': round(vmean, 3),
                    'max': round(vmax, 3), 'range': round(vmax - vmin, 3)})
    if usl is not None and lsl is not None and len(vals) > 1:
        std = float(vals.std())
        if std > 0:
            summary['cp'] = round((usl - lsl) / (6 * std), 3)
            summary['cpk'] = round(min((usl - vals.mean()) / (3 * std),
                                       (vals.mean() - lsl) / (3 * std)), 3)
    return summary


def _flatten_delta_for_group(avg_values, threshold, nominal):
    """Per-row flatten delta for one chronologically-ordered group.

    ``avg_values`` is a list of row-averages in chronological order. Interior
    'picks' — a point more than ``threshold`` off its immediate-neighbour average
    — are pulled onto the group's CLEAN BASELINE: the mean of the group's NON-pick
    values (picks excluded so several spikes can't drag the target). Every non-pick
    row gets 0.0. No-op when nominal is None (flatten stays gated on a resolved
    tolerance, matching the UI's disabled state — the math itself no longer uses
    nominal). User directive 2026-07-04 (was: neighbour average +/-10% nudge).
    """
    n = len(avg_values)
    deltas = [0.0] * n
    if nominal is None:
        return deltas

    def _bad(x):
        return x is None or (isinstance(x, float) and math.isnan(x))

    # 1) Flag interior picks (deviating from their immediate-neighbour average).
    is_pick = [False] * n
    for i in range(1, n - 1):
        v, left, right = avg_values[i], avg_values[i - 1], avg_values[i + 1]
        if _bad(v) or _bad(left) or _bad(right):
            continue
        nb = (left + right) / 2.0
        if abs(nb) <= _NB_EPS:               # guard: neighbour avg ~ 0
            continue
        if abs(v - nb) / abs(nb) > threshold:
            is_pick[i] = True

    # 2) Baseline = mean of the present NON-pick values (picks excluded).
    baseline_vals = [avg_values[k] for k in range(n)
                     if not is_pick[k] and not _bad(avg_values[k])]
    if not baseline_vals:
        return deltas                        # no clean baseline (every point a pick)
    baseline = sum(baseline_vals) / len(baseline_vals)

    # 3) Pull each pick onto the baseline.
    for i in range(n):
        if is_pick[i]:
            deltas[i] = baseline - avg_values[i]
    return deltas


def compute_row_deltas(df, s, shift=0.0, flatten=False, threshold=DEFAULT_PICK_THRESHOLD,
                       nominal=None):
    """Total per-row display-scale delta to apply to each non-empty MIS cell.

    Applies flatten first (if on), then the squeeze on the de-spiked series, then
    a uniform ``shift`` added to every present row (§3.3 / §3.3.1 + centering
    shift). ``shift`` is an absolute display-scale offset (the caller — the SPC
    page — derives it from the target centering, e.g. nominal - mean); it moves
    the whole cavity cloud without changing its spread, so it tunes Cpk (not Cp).
    Returns a dict ``{df_index: delta_float}``. Rows whose MIS_AVG is NaN (all
    cells empty) get no delta.
    """
    result = {}
    if df is None or df.empty or 'NUMERO_FIGURA' not in df.columns:
        return result
    mis_in = _mis_in(df)
    base_avg = df['MIS_AVG'] if 'MIS_AVG' in df.columns else df[mis_in].mean(axis=1, skipna=True)

    for figura in df['NUMERO_FIGURA'].dropna().unique().tolist():
        sub = df[df['NUMERO_FIGURA'] == figura]
        if 'DATETIME' in sub.columns:
            sub = sub.sort_values('DATETIME')
        idx = list(sub.index)
        avg = [None if pd.isna(base_avg[i]) else float(base_avg[i]) for i in idx]

        # 1) flatten pass
        if flatten:
            fdeltas = _flatten_delta_for_group(avg, threshold, nominal)
        else:
            fdeltas = [0.0] * len(idx)
        flattened_avg = [None if avg[k] is None else avg[k] + fdeltas[k] for k in range(len(idx))]

        # 2) squeeze pass on the de-spiked series
        present = [v for v in flattened_avg if v is not None]
        if present and s:
            mbar = sum(present) / len(present)
        else:
            mbar = None
        for k, i in enumerate(idx):
            if flattened_avg[k] is None:
                continue
            sdelta = s * (mbar - flattened_avg[k]) if (mbar is not None and s) else 0.0
            # 3) uniform centering shift (same value on every present row)
            total = fdeltas[k] + sdelta + shift
            if total != 0.0:
                result[i] = total
    return result


def tweaked_series(df, s, shift=0.0, flatten=False, threshold=DEFAULT_PICK_THRESHOLD, nominal=None):
    """Per-NUMERO_FIGURA chart series AFTER applying the tweak (for preview/verify)."""
    deltas = compute_row_deltas(df, s, shift=shift, flatten=flatten, threshold=threshold,
                                nominal=nominal)
    base_avg = df['MIS_AVG'] if 'MIS_AVG' in df.columns else df[_mis_in(df)].mean(axis=1, skipna=True)
    new_avg = base_avg.copy()
    for i, d in deltas.items():
        new_avg[i] = base_avg[i] + d
    return group_series(df.assign(MIS_AVG=new_avg))


def compute_tweaked_updates(df, s, shift=0.0, flatten=False, threshold=DEFAULT_PICK_THRESHOLD,
                            nominal=None):
    """Build the safe-write update payload from a tweak.

    Returns a list of update dicts::

        {'key': {<NATURAL_KEY_COLS>: raw_value, ...},
         'numero_riferimento': <int/str>,
         'new_raw': {'MIS0k': <int>, ...}}

    Only non-empty MIS cells of changed rows are included; raw ints are produced
    via ``round(new_display * MIS_SCALE)`` (§2.1 round-trip contract).
    """
    updates = []
    deltas = compute_row_deltas(df, s, shift=shift, flatten=flatten, threshold=threshold,
                                nominal=nominal)
    if not deltas:
        return updates
    mis_in = _mis_in(df)
    for i, delta in deltas.items():
        row = df.loc[i]
        new_raw = {}
        for col in mis_in:
            val = row[col]
            if pd.isna(val):
                continue                      # empty cell: never written
            new_raw[col] = int(round((float(val) + delta) * MIS_SCALE))
        if not new_raw:
            continue
        key = {}
        for col in NATURAL_KEY_COLS:
            raw_col = 'RAW_' + col
            if raw_col in df.columns:
                key[col] = row[raw_col]
            elif col in df.columns:
                key[col] = row[col]
        nr = row['RAW_NUMERO_RIFERIMENTO'] if 'RAW_NUMERO_RIFERIMENTO' in df.columns else row.get('NUMERO_RIFERIMENTO')
        updates.append({'key': key, 'numero_riferimento': nr, 'new_raw': new_raw})
    return updates
