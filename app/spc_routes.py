"""Routes for the new Measurements and SPC-Tweaks pages.

Kept in a separate module (imported by app/__init__.py) so the master-reference
app/routes.py stays untouched — blast-radius limit per IMPLEMENTATION-PLAN.md
§3.2. All data reads go through the shared app.functions.mosys_data pipeline so
the table and the chart provably read identical data; all SPC math is in
app.functions.spc; all production writes go through the dry-run-gated
mosys.execute_nrildim_updates.
"""

import datetime
import json
import logging

from flask import render_template, request, jsonify
from flask_login import login_required, current_user

from app import app
from app.functions import mosys_data, spc
from app.functions.mosys import execute_nrildim_updates, WriteError
from app.functions.auth_repo import RoleRepository
from auth_config import full_access_required

_role_repo = RoleRepository()

logger = logging.getLogger(__name__)

_FILTER_KEYS = ('articolo', 'numero_riferimento', 'date_from', 'date_to')


def _current_filters():
    return {k: (request.args.get(k) or None) for k in _FILTER_KEYS}


def _filter_querystring(filters):
    return '&'.join(f"{k}={v}" for k, v in filters.items() if v)


def _offline_demo():
    """True when the read pipeline should serve fabricated sample data.

    config.OFFLINE_DEMO is already force-disabled when WRITE_ENABLED is true;
    re-checking here keeps the safety rule local and obvious."""
    return bool(app.config.get('OFFLINE_DEMO')) and not bool(app.config.get('WRITE_ENABLED'))


@app.route('/measurements')
@login_required
def measurements():
    filters = _current_filters()
    demo = _offline_demo()
    error = None
    truncated = False
    cap = mosys_data.BROWSE_ROW_CAP
    rows, columns, footer = [], [], spc.footer_stats(None)

    # Part-number dropdown source (small spec table — instant). Always available so
    # the two-dropdown filter renders even before anything is selected.
    part_numbers = []
    try:
        part_numbers = mosys_data.fetch_part_numbers(offline_demo=demo)
    except Exception as exc:  # noqa: BLE001
        logger.error("measurements part-number list failed: %s", exc, exc_info=True)

    # A table is fetched ONLY once BOTH dropdowns are chosen (part number AND
    # dimension). That guarantees a fast, bounded article+dimension read and makes
    # an unfiltered whole-table scan impossible (the old endless-spin cause).
    has_selection = bool(filters.get('articolo')) and bool(filters.get('numero_riferimento'))
    selected_descrizione = ''
    if has_selection:
        try:
            # No TOP: article+dimension is bounded and fast (~5s); the reverse-scan
            # pathology of TOP+DESC is avoided. Newest-first + cap applied in-frame.
            df = mosys_data.fetch_measurements(filters, offline_demo=demo)
            if df is not None and not df.empty:
                df = df.sort_values(['DATA_RILEVAMENTO', 'ORA_RILEVAMENTO'], ascending=False)
                if len(df) > cap:
                    truncated = True
                    df = df.head(cap)
                if 'DESCRIZIONE' in df.columns and df['DESCRIZIONE'].notna().any():
                    selected_descrizione = str(df['DESCRIZIONE'].dropna().iloc[0])
                valid_mis = mosys_data.valid_mis_columns(df)
                columns = [c for c in mosys_data.DISPLAY_COLUMNS
                           if c in df.columns and (not c.startswith('MIS') or c in valid_mis)]
                rows = df[columns].to_dict(orient='records')
                footer = spc.footer_stats(df)
        except Exception as exc:  # noqa: BLE001
            logger.error("measurements route DB error: %s", exc, exc_info=True)
            error = "Could not load measurement data from the database."

    return render_template(
        'measurements.html',
        title='Measurements',
        columns=columns,
        column_labels=mosys_data.COLUMN_LABELS,
        rows=rows,
        footer=footer,
        filters=filters,
        spc_query=_filter_querystring(filters),
        offline_demo=demo,
        truncated=truncated,
        row_cap=cap,
        part_numbers=part_numbers,
        has_selection=has_selection,
        selected_descrizione=selected_descrizione,
        error=error,
    )


@app.route('/measurements/dimensions')
@login_required
def measurements_dimensions():
    """JSON endpoint powering the dependent dimension dropdown: the dimensions
    that ACTUALLY have measurements for a part number. Article-scoped NRILDIM scan
    (~3-6s) — deliberately on-demand so the initial page load stays instant."""
    articolo = request.args.get('articolo') or None
    if not articolo:
        return jsonify({'dimensions': []})
    demo = _offline_demo()
    try:
        dims = mosys_data.fetch_measured_dimensions(articolo, offline_demo=demo)
    except Exception as exc:  # noqa: BLE001
        logger.error("measured-dimensions lookup failed: %s", exc, exc_info=True)
        return jsonify({'dimensions': [], 'error': 'lookup failed'}), 200
    return jsonify({'dimensions': dims})


@app.route('/spc-tweaks')
@login_required
def spc_tweaks():
    filters = _current_filters()
    demo = _offline_demo()
    error = None
    # Same gate as /measurements: a part number is required before any DB read.
    # count_nrildim on an unfiltered selection scans the whole 4.5M-row table
    # (~4 min) — never run it on an empty filter.
    needs_filter = not filters.get('articolo')
    current_series, capability, overall, tol = {}, {}, spc.overall_capability(None, None, None), \
        {'nominal': None, 'usl': None, 'lsl': None}
    if not needs_filter:
        try:
            tol = mosys_data.fetch_tolerance(filters.get('numero_riferimento'), offline_demo=demo)
            # Volume guard: the SPC path is uncapped (preview must equal commit), so
            # refuse a selection too large to tweak safely BEFORE pulling it. Live
            # only — the offline sample set is tiny. Same ceiling as the commit path.
            too_many = None
            if not demo:
                n = mosys_data.count_nrildim(filters)
                if n > mosys_data.SPC_MAX_ROWS:
                    too_many = n
            if too_many is not None:
                error = (f"This selection matches {too_many:,} rows — too many to tweak "
                         f"safely (limit {mosys_data.SPC_MAX_ROWS:,}). Add a dimension "
                         f"(NUMERO_RIFERIMENTO) and/or a date range to narrow it.")
            else:
                df = mosys_data.fetch_measurements(filters, offline_demo=demo)
                if df is not None and not df.empty:
                    current_series = spc.group_series(df)
                    capability = spc.capability(df, tol['usl'], tol['lsl'])
                    overall = spc.overall_capability(df, tol['usl'], tol['lsl'])
        except Exception as exc:  # noqa: BLE001
            logger.error("spc_tweaks route DB error: %s", exc, exc_info=True)
            error = "Could not load measurement data from the database."

    # Date-range slider bounds: [now - 30 days, now] in LOCAL time (naive ISO).
    now = datetime.datetime.now()
    slider = {
        'min': (now - datetime.timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%S'),
        'max': now.strftime('%Y-%m-%dT%H:%M:%S'),
    }

    return render_template(
        'spc_tweaks.html',
        title='SPC Tweaks',
        filters=filters,
        measurements_query=_filter_querystring(filters),
        current_series=json.dumps(current_series),
        capability=json.dumps(capability),
        overall=overall,
        nominal=tol['nominal'],
        usl=tol['usl'],
        lsl=tol['lsl'],
        pick_threshold=spc.DEFAULT_PICK_THRESHOLD,
        mis_scale=mosys_data.MIS_SCALE,
        slider=slider,
        # UI-truthful gate: hide/disable Apply unless BOTH the server-wide safety
        # flag AND the current user's role allow writes. The commit route enforces
        # both independently (config gate inside execute_nrildim_updates,
        # role gate via @full_access_required) — this is display-only.
        write_enabled=bool(app.config.get('WRITE_ENABLED'))
                      and _role_repo.role_has_full_access(current_user.role),
        offline_demo=demo,
        selected_cavity=(request.args.get('cavity') or ''),
        needs_filter=needs_filter,
        error=error,
    )


@app.route('/spc-tweaks/commit', methods=['POST'])
@login_required
@full_access_required
def spc_tweaks_commit():
    """Recompute the tweak server-side (authoritative) and write via the
    dry-run-gated safe-write path. Returns JSON for the toast layer."""
    payload = request.get_json(silent=True) or request.form
    filters = {k: (payload.get(k) or None) for k in _FILTER_KEYS}
    # Same part-number gate as the GET routes: never let an unfiltered commit
    # reach count_nrildim (a full-table scan) — nor write to an unbounded set.
    if not filters.get('articolo'):
        return jsonify({'success': False,
                        'error': 'Select a part number before applying a tweak.'}), 200
    try:
        squeeze = float(payload.get('squeeze', 0) or 0)
    except (TypeError, ValueError):
        squeeze = 0.0
    try:
        shift = float(payload.get('shift', 0) or 0)
    except (TypeError, ValueError):
        shift = 0.0
    flatten = str(payload.get('flatten', '')).strip().lower() in {'1', 'true', 'on', 'yes'}
    try:
        threshold = float(payload.get('threshold', spc.DEFAULT_PICK_THRESHOLD))
    except (TypeError, ValueError):
        threshold = spc.DEFAULT_PICK_THRESHOLD
    cavity = (payload.get('cavity') or '').strip()

    write_enabled = bool(app.config.get('WRITE_ENABLED'))
    demo = _offline_demo()
    try:
        # Same volume ceiling as the preview path: never recompute a squeeze mean
        # (and write) over a selection too large to have been previewed safely.
        if not demo:
            n = mosys_data.count_nrildim(filters)
            if n > mosys_data.SPC_MAX_ROWS:
                return jsonify({'success': False,
                                'error': f'This selection matches {n:,} rows — too many to '
                                         f'tweak safely. Narrow the filter and try again.'}), 200
        df = mosys_data.fetch_measurements(filters, offline_demo=demo)
        tol = mosys_data.fetch_tolerance(filters.get('numero_riferimento'), offline_demo=demo)
        # Scope the write to the selected cavity (matches what the user saw on the
        # chart). Without this a commit would tweak every cavity in the filter.
        if cavity and df is not None and not df.empty and 'NUMERO_FIGURA' in df.columns:
            df = df[df['NUMERO_FIGURA'].astype(str) == cavity]
        updates = spc.compute_tweaked_updates(
            df, squeeze, shift=shift, flatten=flatten, threshold=threshold, nominal=tol['nominal'])
        # dry_run is True unless production writes are explicitly enabled.
        report = execute_nrildim_updates(updates, dry_run=(not write_enabled))
    except WriteError as exc:
        logger.error("commit write error: %s", exc)
        return jsonify({'success': False,
                        'error': 'The update could not be applied. No records were changed.'}), 200
    except Exception as exc:  # noqa: BLE001
        logger.error("commit failed: %s", exc, exc_info=True)
        return jsonify({'success': False,
                        'error': 'Something went wrong. No records were changed.'}), 200

    if report['status'] == 'committed':
        return jsonify({'success': True, 'message': 'MOSYS records updated',
                        'updated_rows': report['updated_rows']})
    if report['status'] == 'dry_run':
        planned = len(report['planned'])
        return jsonify({'success': True, 'dry_run': True,
                        'message': f'Preview only — writes are disabled. '
                                   f'{planned} record(s) would be updated.',
                        'planned': planned})
    if report['status'] == 'noop':
        return jsonify({'success': True, 'message': 'No changes to apply.', 'planned': 0})
    # aborted / other
    return jsonify({'success': False,
                    'error': 'The update was blocked by a safety check. No records were changed.'}), 200
