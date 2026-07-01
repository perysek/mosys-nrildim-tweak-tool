---
title: MOSYS NRILDIM Tweak Tool — Measurements + SPC Tweaks Feature
status: APPROVED — ready to implement (production write path stays dry-run-gated per §3.1/§5)
priority: high
owner: perysek
created: 2026-07-01
supersedes: new-feature-implementation-plan.md (addresses reviews/planning/new-feature-implementation-plan.md FAIL findings)
tags: [flask, pervasive, spc, nrildim, ui, safe-write]
sources:
  - new-feature-PRD.txt
  - cc-project-memory-files/spec.md
  - reviews/planning/new-feature-implementation-plan.md
  - claude-code-requirements/GUI-GOLDEN-BOOK.md
  - claude-code-requirements/GUI-COMPONENTS-GOLDEN-BOOK.md
  - app/routes.py, app/functions/mosys.py
---

# MOSYS NRILDIM Tweak Tool — Implementation Plan

## 1. Executive Summary

**Mission.** Add two linked pages to the existing MOSYS Flask app, reachable from a new
left-sidebar shell:

1. **Measurements** — a full-width, sticky-header, horizontal-scroll results table of NRILDIM
   dimensional data with per-column semantic search + asc/desc sort and a statistics footer.
2. **SPC Tweaks** — a slider-driven "spread squeeze" tool with a live line chart, Cp/Cpk +
   min/avg/max/range badges, an animated **Preview** toggle (current ⇄ tweaked, 0.5 s), and a
   **Commit** action that writes the tweaked values back to the production Pervasive `NRILDIM`
   table through a heavily-guarded, reversible write path.

**The big shift.** The app becomes **read-write** for the first time. Today `app/functions/mosys.py`
only reads (`get_pervasive`). The core engineering risk is the irreversible mutation of shop-floor
measurement records, so this plan front-loads a mock-first, dry-run-default, journalled,
atomic-transaction write architecture and splits delivery into risk-isolated phases.

**Deliverables.** A sidebar app-shell (`base.html` + plain-CSS token layer ported from the GUI
Golden Book), two new routes + templates, a mock-data harness, a `NRILDIM` safe-write module, and a
Cp/Cpk/statistics module — all grouped by **`NUMERO_FIGURA` only**, reusing the grouping convention
already in `app/routes.py`/`graph.html` (see §2.6 for the `spec.md` reconciliation). The overriding
build principle is **reuse `app/routes.py` 1-to-1** (§3.4): everything except the new SPC business
logic and the safe write is copied/imported from the existing code, not re-derived.

---

## 2. Governing-Docs Reconciliation (resolves review FAIL findings)

The plan review (`reviews/planning/new-feature-implementation-plan.md`) returned **FAIL** with three
blocking findings plus structural notes. Each is resolved here explicitly:

### 2.1 MIS raw↔display scale factor — RESOLVED (finding #3)

- `app/routes.py` (L175-176, L267-268) divides `MIS01`–`MIS10` by **10000.0** for display.
- `spec.md` (L33-34) says "divided by 1000."
- **Ruling: 10000 is authoritative.** Evidence: `routes.py` L313 comments that `VALORE_NOMINALE`,
  `USL`, `LSL` are stored in final scale and are **not** divided; the running app compares
  `MIS/10000` against those limits and the green-in-tolerance / Cp / Cpk logic is coherent only at
  ÷10000. `spec.md`'s "1000" is treated as a documentation typo.
- **Round-trip contract for writes:** `raw_int = round(display_value * 10000)`; `display = raw_int / 10000`.
- **Hard gate:** Phase 1 of the mock harness prints, for a sample of rows, `raw MIS int`,
  `raw/10000`, and the linked `VALORE_NOMINALE` — and the write path stays disabled until a human
  confirms the magnitudes line up (a value near nominal, not 10× off). No write code ships before
  this check passes. `spec.md` will be corrected to "10000" as part of Phase 0 docs.

### 2.2 Reuse of `pervasive_connection()` — RESOLVED (finding #4)

- PRD L29 mandates reusing the existing context manager. It currently opens/closes only, with no
  `commit()`/`rollback()` (pyodbc implicitly rolls back uncommitted work on close).
- **Approach:** the write path **reuses `pervasive_connection(readonly=False)`** (the `readonly`
  param already exists and flips the DSN flag) and adds transaction control *around* it — it does
  **not** duplicate connection/DSN logic. New function in `mosys.py`:
  `execute_nrildim_updates(updates, *, dry_run=True)` which does:
  `with pervasive_connection(readonly=False) as conn: conn.autocommit = False; …; conn.commit()`
  and `conn.rollback()` on any exception before re-raising. `get_pervasive()` is untouched.

### 2.3 `claude-code-requirements/*` applied — RESOLVED (finding #2)

- **Read and applied:** `GUI-GOLDEN-BOOK.md` (design law, tokens, refined-minimal system,
  table/modal/toast specs) and the component sub-docs (`sidebar`, `confirm-modal`, `undo-toast`,
  `scrollable-table`, `icons`, `flash-messages`, `form-fields`).
- **Design tokens adopted** (GUI-GOLDEN-BOOK §3): warm-light surfaces, gold accent `#c9a227`,
  **2px radius** (System A "refined minimal"), Inter 300/400/500/600, `--ease-out-expo`.
- **Toolchain reality:** the golden book assumes a Tailwind `input.css → output.css` build +
  `base.html` + macros that **do not exist in this repo** (plain `static/style.css`, standalone
  templates, no npm). Per PRD L28 ("apply the design **independently from existing templates
  design**") and the book's own deploy-safety rule ("styles must reach the server without a build
  step → inline `<style>`/plain CSS"), the design is ported as **hand-authored plain CSS tokens +
  classes** and a new `base.html`, not by introducing Tailwind. PRD spec-points win on conflicts
  (PRD L13).
- **`STACK.md` flagged NON-AUTHORITATIVE:** it describes a PostgreSQL/OCR/Tesseract/Alembic/Docker
  invoices app that does not match this Flask + pyodbc + Pervasive repo. It is stale/copied and is
  ignored for this feature.

### 2.4 NRILDIM natural key — partially known (finding #5)

`spec.md` + `routes.py` already expose the NRILDIM columns in production use:
`ARTICOLO, DATA_RILEVAMENTO, ORA_RILEVAMENTO, NUMERO_RIFERIMENTO, NUMERO_STAMPATA, NUMERO_FIGURA,
MIS01…MIS10`. The mock step **confirms/narrows** the natural key (and probes ODBC for any declared
PK/unique index) rather than discovering it from zero. Working key hypothesis:
`(NUMERO_RIFERIMENTO, DATA_RILEVAMENTO, ORA_RILEVAMENTO, NUMERO_STAMPATA, NUMERO_FIGURA)` +
`ARTICOLO`; validated by asserting uniqueness over the 100-row mock before any write.

### 2.5 Phase breakdown — ADDED (finding #1)

The single monolithic doc is replaced by the 6 risk-isolated phases in §4.

### 2.6 Statistics grouping — `NUMERO_FIGURA` only (reconciles spec vs code)

`spec.md` (L98-100) says group by the `NUMERO_STAMPATA + NUMERO_FIGURA` composite. **`app/routes.py`
(the master reference, L279 + L348-394) groups the chart and Cp/Cpk by `NUMERO_FIGURA` only.** Per
the directive to reuse `routes.py` 1-to-1, **`NUMERO_FIGURA` only is authoritative** for all SPC
grouping (chart series, Cp/Cpk, min/avg/max/range, and the squeeze). `NUMERO_STAMPATA` is still part
of the **row-identity natural key** for writes (§2.4) — it is dropped only from *statistics
grouping*, not from row targeting. `FIGURA` is compared last-digit-formatted
(`str.strip().str[-1:]`), exactly as `routes.py` does.

---

## 3. Architectural North Star

### 3.1 Backend — the safe-write doctrine (8 guarantees)

1. **Mock-first.** All write logic is developed and tested against a local SQLite snapshot of the
   latest 100 NRILDIM rows + linked NSCHEDIM/SCHEDIM1 rows. Production is never the test surface.
2. **Integrity gate.** Before any write, resolve `SCHEDIM1.RIF_MISURA → NSCHEDIM.NUMERO_RIFERIMENTO`
   for the dimension; refuse the write if it does not resolve to a live, non-removed characteristic
   (`FLAG_RIMOSSO` = least-occurring value per `spec.md`).
3. **Exact-scope targeting.** Candidate rows = exactly the filtered SELECT the user is viewing; each
   row matched on its full natural key → one row per statement.
4. **Pre-image journal.** Every affected row's key + original raw MIS ints are written to a local
   SQLite `pending_update` journal under a `batch_id` **before** the DB is touched.
5. **Atomic transaction.** `pervasive_connection(readonly=False)` + `autocommit=False`; each
   `UPDATE` asserts `cursor.rowcount == 1`; any anomaly → `rollback()` the whole batch.
6. **Post-commit verify + auto-restore.** Re-SELECT affected rows; if stored ≠ intended, restore
   from the journal.
7. **Lifecycle.** Verified success → purge journal batch; failure → retain journal + expose a
   rollback/undo path.
8. **Dry-run default.** `execute_nrildim_updates(..., dry_run=True)` logs SQL + rowcounts and
   executes nothing until a human flips the flag after mock validation + the §2.1 scale check.

### 3.2 Frontend — shell, state, motion

- **Shell:** new `app/templates/base.html` with the ported sidebar (self-contained plain-CSS,
  no Flask-Login/macros — the golden sidebar's auth gating is stripped since this app has no auth).
  Existing `index.html`/`graph.html` are **linked** from the sidebar; retrofitting them into the
  shell is out of scope (kept standalone to limit blast radius).
- **Design layer:** `app/static/tokens.css` = the GUI-GOLDEN-BOOK `:root` tokens + refined-minimal
  classes (`.btn-refined-*`, `.refined-table`, sidebar rules, toast/modal styles) as plain CSS.
- **SPC state model:** the SPC page holds three in-memory JS states — `current` (fetched),
  `tweaked` (recomputed on squeeze-slider input / flatten-picks toggle), and `preview` (boolean).
  Chart + badges render from `preview ? tweaked : current`; the toggle animates via Chart.js
  `update()` easing (500 ms) and CSS transitions on badge values.
- **Date-range control (SPC page):** two date-with-time pickers — **start-date** and **end-date** —
  each paired with an **on/off toggle switch** that enables/disables its time-of-day input
  (date-only when off; time precision when on). Below them, a **dual-handle range slider** spans
  `[now − 30 days, now]` — `minlimit = now − 30 days`, `maxlimit = now` (current date **and** time).
  The two handles are bound **two-way** to the start/end pickers: dragging a handle auto-refreshes
  the matching picker's value on change, and editing a picker repositions its handle. Any change
  re-runs the filtered NRILDIM fetch. Date/time parsing + `DATA_RILEVAMENTO` (`YYYYMMDD ⇄ YYYY-MM-DD`)
  and `ORA_RILEVAMENTO` (`HHMMSS ⇄ HH:MM:SS`, zero-padded via `zfill(6)`) formatting **reuse
  `routes.py`/`graph.html` logic 1-to-1**. Time-of-day filtering on `ORA_RILEVAMENTO` is net-new
  (routes.py filters date only) but is built on those reused formatters.
- **"Flatten picks" toggle (SPC page):** an on/off switch labelled **`flatten picks`** that, when ON,
  applies a peak-flattening pass **in addition to** the squeeze — it replaces each outlier "pick"
  with its neighbour average, nudged ±10% toward the correct tolerance side. Full algorithm in §3.3.1.
- **Data handoff Measurements → SPC:** the filter querystring (articolo/date_from/date_to/
  numero_riferimento, plus the SPC time-of-day bounds) is carried in the SPC route URL; SPC re-fetches
  server-side from the same filtered query so the two pages share one source of truth (no fragile
  client cache).

### 3.3 The squeeze transform (KEY SEMANTIC DECISION — needs sign-off)

**Grouping = `NUMERO_FIGURA` only** (§2.6, matching `routes.py`) — **STAMPATA removed**. The
candidate rows of a group are those in the **active filter scope**: the user's column-filter inputs
**plus any in-code fixed filters** (e.g. `routes.py`'s default `DATA_RILEVAMENTO LIKE '2025%'`, the
date-range/time bounds, `numero_riferimento`, etc.). The chart plots each row's **average of the
non-empty MIS01–10** (`MIS_AVG = mean(axis=1, skipna=True)`, per `routes.py`). The squeeze applies a
**uniform per-row offset to every non-empty MIS cell** (empty cells are skipped and left empty):

```
For each NUMERO_FIGURA group (within the active filter scope):
  M̄ = mean of the group's row-averages (MIS_AVG)
  For each row:
    row_avg = mean of the row's NON-EMPTY MIS cells
    delta_display = s * (M̄ - row_avg)               # s = squeeze-slider fraction in [0,1]
    for each MISk that is NOT empty:                 # empty (NaN) cells skipped entirely
        new_MISk  = old_MISk + delta_display
        new_raw_k = round(new_MISk * 10000)          # empty cells never written
```

Result: each row's new average = `M̄ + (row_avg − M̄)(1 − s)`; between-row std **per FIGURA** shrinks
by `(1 − s)`; Cp/Cpk rise by `1/(1 − s)`; within-row structure, empty cells, and the group mean are
preserved. Re-fetching tweaked data reproduces the previewed chart exactly. **Confirmation #1 (below)
gates this definition.** (If **"flatten picks"** is ON, its pass (§3.3.1) is applied **first**, then
the squeeze operates on the de-spiked series — both share the same FIGURA grouping and filter scope.)

### 3.3.1 The "flatten picks" transform (confirmed)

Operates per **`NUMERO_FIGURA`** series, ordered by `DATETIME` (same ordering as `graph.html`), on the
row-average series (`MIS_AVG`). It de-spikes isolated **picks** (peaks/dips) by pulling them to their
neighbour average, biased ±10% to the correct tolerance side. Requires `VALORE_NOMINALE` (reused from
the SCHEDIM1 tolerance fetch, §3.4); if nominal is unavailable the toggle is a no-op and is disabled
in the UI with a note.

```
Inputs per FIGURA group (interior points only; first/last skipped — need both neighbours):
  t   = pick threshold, default 0.25 (your "25% bigger" example; configurable)
  nom = VALORE_NOMINALE for the dimension (from SCHEDIM1, per routes.py)

For each interior point i with value v_i, left v_{i-1}, right v_{i+1}:
  nb = (v_{i-1} + v_{i+1}) / 2                       # neighbour average
  is_pick = |v_i - nb| / |nb| > t                    # e.g. v_i is >25% off the neighbour avg
  if is_pick:
    if v_i <= nom:      flattened = nb * (1 - 0.10)   # nominal→LOWER-tol zone  → −10%
    else:              flattened = nb * (1 + 0.10)    # nominal→UPPER-tol zone  → +10%
    # write-back uses the SAME per-row non-empty-cell offset as the squeeze:
    delta = flattened - v_i
    for each non-empty MISk in row i:  new_MISk = old_MISk + delta ; new_raw_k = round(new_MISk*10000)
```

Notes: zone is decided by the **pick's own value** vs `nom` (`≤ nom` = lower zone → −10%, `> nom` =
upper zone → +10%). Empty MIS cells are skipped (never written), identical to §3.3. When both toggles
are active: **flatten first**, then squeeze the resulting series.

### 3.4 Reuse `app/routes.py` 1-to-1 (implementation standard)

`app/routes.py` is the **master reference** and already encodes every non-new rule; `graph.html` and
`index.html` inline JS encode the rendering/table behaviour. **Reuse them verbatim (import or copy)
wherever feasible — divergence from `routes.py` is a bug, not a choice.** Explicitly reused, not
re-derived:

| Concern | Source to reuse |
|---|---|
| NRILDIM/NSCHEDIM/SCHEDIM1 queries + dynamic filter building | `routes.py` `index()` / `graph()` |
| MIS ÷10000 scaling, empty-MIS-column dropping | `routes.py` L173-182, L265-271 |
| `DATA_RILEVAMENTO` `YYYYMMDD⇄YYYY-MM-DD`, `ORA_RILEVAMENTO` `HHMMSS⇄HH:MM:SS` (`zfill(6)`) | `routes.py` L141-162, L274-276 |
| last-digit `NUMERO_STAMPATA`/`NUMERO_FIGURA` | `routes.py` L166-169 |
| `MIS_AVG`, per-FIGURA Cp/Cpk, USL/LSL from SCHEDIM1 tolerance operators | `routes.py` L270-379 |
| Chart.js datasets, USL/LSL/nominal reference lines, y-axis padding | `graph.html` |
| table sort/filter/search/export inline JS | `index.html` |
| column captions (`COLUMN_LABELS`) | `routes.py` L13-29 (+ `spec.md` aliases) |

**Net-new code is only:** (a) SPC business logic — squeeze transform, date-range slider, flatten
picks; (b) the safe MOSYS-db write path (`mosys.execute_nrildim_updates` + journal + integrity gate).

---

## 4. Phasing Strategy

| # | Phase | Deliverable | Risk | DB writes? | Gate to next |
|---|-------|-------------|------|-----------|--------------|
| 0 | Foundation & docs | `base.html` shell, `tokens.css`, sidebar, fix `spec.md` scale typo | Low | No | Shell renders, existing pages still work |
| 1 | Mock harness & discovery | `scripts/build_mock_data.py` (read-only), SQLite mock, natural-key + scale verification report | Low (read-only) | No | Human confirms key uniqueness + scale magnitudes |
| 2 | Measurements page | `/measurements` route + template: table, filters, sort, footer stats | Low | No | Table matches PRD UI reqs; footer stats correct vs pandas |
| 3 | SPC Tweaks UI | `/spc-tweaks` route + template: slider, chart, Cp/Cpk/stat badges, Preview toggle | Low | No | Preview animates 0.5 s; badges/chart correct on mock+live reads |
| 4 | Safe-write backend | `mosys.execute_nrildim_updates` + journal + integrity gate; validated on mock; **dry-run only** | Med (code, no live writes) | Dry-run | All write unit tests pass on mock; dry-run SQL reviewed |
| 5 | Commit wiring + go-live | Confirm modal → `/spc-tweaks/commit` → toast; enable live writes behind flag after validation | **High** | **Yes** | User flips flag; live smoke-test on one known row + rollback proven |

Phases 0-3 ship with **zero** production-write capability and can be reviewed/approved on their own.
Phase 5 is the only phase that mutates production and is separately gated (PRD L31).

---

## 5. Phase Detail

### Phase 0 — Foundation & Docs
- Create `app/templates/base.html`: shell (`flex h-full`), header with `{% block page_actions %}`,
  `{% block content %}`, `{% block scripts %}`.
- Create `app/static/tokens.css`: port GUI-GOLDEN-BOOK `:root` tokens + refined-minimal classes.
- Port `sidebar` (plain CSS, gold active-pill, accordion, mobile drawer JS) — strip Flask-Login/
  permission gating; nav links: Measurements, SPC Tweaks, + links to existing Records/Chart pages.
- Port `confirm_modal.html` and `undo_toast.html` into `app/templates/components/` (swap
  `msg()`/`MSG()` for English literals; keep id-scoped `<style>`; supply required CSS vars in tokens).
- Fix `spec.md` MIS scale "1000" → "10000" with a note.
- **No behavior change to existing routes.**

### Phase 1 — Mock Harness & Discovery (read-only)
- `scripts/build_mock_data.py`: uses `get_pervasive` (read-only) to pull latest 100 NRILDIM rows
  (`ORDER BY DATA_RILEVAMENTO DESC, ORA_RILEVAMENTO DESC`) + their NSCHEDIM/SCHEDIM1 rows via
  `RIF_MISURA/NUMERO_RIFERIMENTO`; writes `app/data/mock_mosys.sqlite`.
- Emit `scripts/mock_report.md`: column list, dtypes, natural-key uniqueness assertion, ODBC-declared
  PK/index probe, and the §2.1 scale sanity table (raw int vs /10000 vs nominal).
- **Human gate:** confirm key uniqueness + scale before Phase 4 write code.

### Phase 2 — Measurements Page (read-only)
- Route `/measurements` (GET): reuse `routes.py` query/format logic (same filters, ÷10000, HH:MM:SS,
  last-digit STAMPATA/FIGURA, drop empty MIS cols, English captions from `spec.md`).
- Template extends `base.html`. Table: full page-width, sticky headers, **horizontal-only** scroll
  (no vertical), `max-lines:2` clamp, minimal padding/row spacing, tuned font, **2px wrapper radius**.
  Per-column: search input (case-insensitive, type-to-filter) + asc/desc **aria icon buttons**.
- Footer: total row count + **avg of per-group (min, max, range)** over the **entire** result set
  (pandas, grouped by `NUMERO_FIGURA` only per §2.6), not just visible rows.
- Top-right **"SPC tweaks"** button → `/spc-tweaks?<current filters>`.

### Phase 3 — SPC Tweaks UI (read-only)
- Route `/spc-tweaks` (GET): re-fetch same filtered NRILDIM, compute per-**FIGURA** `MIS_AVG` series,
  Cp/Cpk (reuse SCHEDIM1 tolerance → USL/LSL logic from `routes.py`), min/avg/max/range.
- **Date-range control** (§3.2): start-date + end-date pickers, each with a time-precision on/off
  toggle switch, plus a dual-handle range slider clamped to `[now − 30 days, now]`, two-way bound to
  the pickers with auto-refresh on slider change. Reuses routes.py date/time formatters 1-to-1.
- Template: squeeze **slider** (0–~90%), **`flatten picks`** on/off switch, Chart.js line chart,
  Cp/Cpk + min/avg/max/range **badges**.
- **Preview** toggle (bottom-right): flips `preview` state; Chart.js `update()` 500 ms easing +
  CSS 0.5 s badge transitions between `current` ⇄ `tweaked` (tweaked computed client-side via the §3.3
  transform + flatten-picks pass; server recomputes authoritatively at commit).
- **Commit** button present but wired only in Phase 5.

### Phase 4 — Safe-Write Backend (dry-run only)
- `mosys.execute_nrildim_updates(updates, *, dry_run=True)` implementing §3.1 (integrity gate,
  journal, atomic txn, rowcount==1, verify, lifecycle). Journal = `app/data/pending_updates.sqlite`.
- Pure-function `spc.compute_tweaked_updates(rows, s)` → list of `{key, {MISk: new_raw}}`.
- Unit tests against the SQLite mock: transform correctness, key targeting, rowcount guard,
  rollback-on-failure, journal write/purge, scale round-trip. **No live writes.**

### Phase 5 — Commit Wiring + Go-Live (production writes)
- `/spc-tweaks/commit` (POST): validates filters, recomputes server-side, calls
  `execute_nrildim_updates(dry_run=WRITE_ENABLED_FLAG is False)`.
- Confirm modal → on success 2 s auto-dismiss toast **"MOSYS records updated"**; on error, toast with
  a **non-technical** message (technical detail logged, not shown).
- Go-live: flip `WRITE_ENABLED` (config/env) only after a supervised smoke test on one known row +
  demonstrated journal rollback. Undo-toast offers post-commit reversal from the journal.

---

## 6. Success Metrics & Quality Gates

- [ ] §2.1 scale check passed on mock (values near nominal, not 10× off); `spec.md` corrected.
- [ ] Natural key proven unique over the 100-row mock; write targets exactly 1 row/statement.
- [ ] Measurements table: sticky headers, horizontal-only scroll, per-column search + asc/desc,
      2px radius, 2-line clamp, no value overlap — verified visually.
- [ ] Footer stats equal an independent pandas computation over the full (unfiltered-by-UI) set.
- [ ] Preview toggle transitions in 0.5 s; tweaked chart matches server recompute at commit.
- [ ] Squeeze groups by `NUMERO_FIGURA` only; delta applied to non-empty MIS cells; empty cells never written.
- [ ] Date-range slider clamps to `[now − 30 days, now]`, two-way binds to both pickers, auto-refreshes fetch; time-precision toggles work per picker.
- [ ] `flatten picks` toggle applies its defined pass (Confirmation #3) on top of the squeeze.
- [ ] No SPC formatting/query logic re-derived — all reused from `routes.py`/`graph.html`/`index.html` per §3.4.
- [ ] Write unit tests green on mock: transform, targeting, rowcount guard, rollback, journal, scale.
- [ ] Dry-run SQL for a real filter reviewed by a human before `WRITE_ENABLED` is flipped.
- [ ] Live smoke test: one row updated, verified, then rolled back from journal.
- [ ] No `confirm()`/`alert()`; components used per golden book; a11y (`aria-*`, focus) intact.

---

## 7. Global Decision Log

| # | Status | Context | Decision | Consequence |
|---|--------|---------|----------|-------------|
| D1 | Accepted | scale 10000 (code) vs 1000 (spec) | Adopt **10000**; treat spec as typo; gate on mock | Wrong factor would 10× corrupt data — gated |
| D2 | Accepted | PRD mandates reusing `pervasive_connection` | Reuse `readonly=False` + add autocommit/commit/rollback around it | No duplicate DSN logic; `get_pervasive` untouched |
| D3 | Accepted | golden book assumes Tailwind build absent here | Port tokens/classes as plain CSS + `base.html` | Deploy-safe, no npm dependency |
| D4 | Accepted | `STACK.md` describes a different app | Flag non-authoritative, ignore | Avoids false stack assumptions |
| D5 | Accepted | existing pages vs new shell | New pages use shell; old pages only linked | Limits blast radius |
| D6 | **Accepted** | squeeze semantics | Per-row uniform offset, **FIGURA-only** grouping, skip empty cells (§3.3) | Confirmed by user 2026-07-01 |
| D7 | **Accepted** | rollout safety | Dry-run default, flag-gated go-live | Confirmed by user 2026-07-01 |
| D8 | Accepted | spec (STAMPATA+FIGURA) vs code (FIGURA) grouping | **FIGURA only** for all SPC stats, per routes.py reuse (§2.6) | STAMPATA stays in write row-key, not in grouping |
| D9 | Accepted | reuse of existing code | Reuse `routes.py`/`graph.html`/`index.html` 1-to-1 (§3.4) | Only SPC logic + safe write are net-new |
| D10 | **Accepted** | `flatten picks` behaviour | Pick = >25% off neighbour avg → set to `nb ± 10%` by tol zone (§3.3.1) | Confirmed by user 2026-07-01 |

---

## 8. Resources & References

- **PRD:** `new-feature-PRD.txt`
- **Spec:** `cc-project-memory-files/spec.md` (stats grouping, queries, captions, tolerance math)
- **Master reference code:** `app/routes.py` (queries, ÷10000, Cp/Cpk, tolerance), `app/functions/mosys.py`
- **Plan review:** `reviews/planning/new-feature-implementation-plan.md`
- **UI law:** `claude-code-requirements/GUI-GOLDEN-BOOK.md` + `gui-components/*` (sidebar, confirm-modal,
  undo-toast, scrollable-table, icons, flash-messages, form-fields)
- **Non-authoritative:** `claude-code-requirements/STACK.md` (stale — different app)

---

## 9. Confirmations — all RESOLVED (2026-07-01)

1. **Squeeze transform (D6):** ✅ Confirmed — per-row uniform offset `delta = s·(M̄ − row_avg)` on each
   **non-empty** MIS cell, grouped by **`NUMERO_FIGURA` only**, scoped to the active column + fixed
   filters (§3.3).
2. **Rollout (D7):** ✅ Confirmed — write function ships **dry-run-by-default**; live writes enabled
   only after mock validation + the §2.1 scale check + a supervised one-row smoke test.
3. **`flatten picks` (D10):** ✅ Confirmed — pick = value > ~25% off its left/right neighbour average;
   flattened to `avg(left,right)` **−10%** (nominal→lower-tol zone) or **+10%** (nominal→upper-tol
   zone), zone by pick value vs `VALORE_NOMINALE`; applied via the same non-empty-cell offset (§3.3.1).

**Remaining process gate (not a design question):** run `scripts/build_mock_data.py` (read-only)
against the Pervasive DSN once to generate the mock — runnable via `! python scripts/build_mock_data.py` —
then the §2.1 scale + natural-key checks must pass before the Phase 5 live-write flag is flipped.

**Plan approved — ready to implement.**
