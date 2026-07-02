# Morning handoff — MOSYS NRILDIM Tweak Tool (autonomous build)

> ## Follow-up fix (2026-07-02) — offline behaviour of the new pages
> **Symptom you hit:** with the DB unreachable, `/measurements` / `/spc-tweaks`
> showed a spinning tab then an empty screen, while the old `/index` "worked"
> (it silently shows hardcoded fake rows — that's what fooled you into thinking
> the DB had connected).
>
> **Two root causes, both fixed:**
> 1. **Slow failure.** The PSQL/Actian ODBC driver *ignores* pyodbc's `timeout=`
>    and `SQL_ATTR_LOGIN_TIMEOUT` — a failing connect took **43 s** (verified),
>    so `/spc-tweaks` (two connects) hung ~86 s. Now every connect is bounded on
>    a worker thread (`mosys._bounded_connect`, `MOSYS_DB_CONNECT_TIMEOUT`,
>    default **6 s**) → fast, clear "database unreachable" error instead of a hang.
> 2. **No offline data path.** Unlike `routes.py`, the new pages had no mock
>    fallback. Added an **opt-in OFFLINE DEMO mode** (NOT a silent fallback):
>    - Enable with env `MOSYS_OFFLINE_DEMO=true`. Default **OFF**.
>    - Serves fabricated data from `app/data/mock_mosys_synthetic.sqlite`
>      (run `python scripts/make_synthetic_mock.py` first if missing) — the live
>      DB is never contacted, so no timeout wait.
>    - Every page shows a loud **"OFFLINE SAMPLE DATA"** banner.
>    - **Hard safety interlock:** demo is force-disabled whenever
>      `MOSYS_WRITE_ENABLED` is true — mock data is never served on a page that
>      can write to production. Covered by tests (now **32/32**).
>
> To click-test the UI on a laptop with no DB:
> `MOSYS_OFFLINE_DEMO=true ./venv/Scripts/python.exe app.py` → open
> `/measurements?articolo=ART-1&numero_riferimento=5001`.
>
> **Go-live CLI:** `scripts/mosys_cli.py` runs the go-live gate from a terminal
> on the RDP (DSN live). It reuses the app's real read + safe-write code, so a
> green run proves the actual code against pyodbc. Dry-run is the default;
> `--commit` needs a tweak + typed confirmation + refuses >`--max-write` rows
> (default 1) for the supervised one-row smoke. Examples in its module docstring.
> `.\venv\Scripts\python.exe scripts\mosys_cli.py --articolo ART-1 --from-date 2025-01-01 --to-date 2025-03-30`


**Date:** 2026-07-01 (overnight autonomous session)
**Plan executed:** `IMPLEMENTATION-PLAN.md` (all 6 phases)
**Status:** All phases implemented. **29/29 offline tests pass.** Production
writes remain **disabled** (dry-run) — the go-live gate is still yours to run.

**Git state:** committed to branch **`feature/nrildim-tweak-tool`** (commit
`c7cb9d6`), **not pushed**. `main` is untouched. Stay on this branch to see the
work — `git checkout main` will hide all new files.

> ### 🚨 THE go-live gate (do this before enabling writes broadly)
> The write logic is proven only against SQLite. `pyodbc` differs from `sqlite3`
> on `cursor.rowcount`, mid-connection `autocommit=False`, and MIS integer/decimal
> coercion. **Do NOT flip `MOSYS_WRITE_ENABLED` broadly until you have watched a
> single-row round-trip succeed on the live DB: write → verify → rollback from the
> journal.** The `rowcount==1` guard + post-commit verify mean a driver surprise
> fails safe (no corruption), but you must see it work once first.

---

## TL;DR — what to do when you wake up

1. **See it render** (no DB needed):
   ```
   ! python scripts/make_synthetic_mock.py      # already run, writes app/data/mock_mosys_synthetic.sqlite
   ! ./venv/Scripts/python.exe -m unittest discover -s tests
   ```
   The route tests already render both new pages against a canned DataFrame.
2. **Run the app against the real DSN** and click through `/measurements` and
   `/spc-tweaks` (`! ./venv/Scripts/python.exe app.py`, then open
   `http://127.0.0.1:5001/measurements`).
3. **Before ANY live write**, run the read-only scale/key gate against the real DSN:
   ```
   ! ./venv/Scripts/python.exe scripts/build_mock_data.py
   ```
   Then read `scripts/mock_report.md` and confirm: (a) natural key is unique,
   (b) `raw / 10000` sits near `VALORE_NOMINALE` (not 10× off).
4. **Only then** enable production writes by setting the env var and restarting:
   ```
   MOSYS_WRITE_ENABLED=true
   ```
   Do a supervised one-row smoke test and prove rollback from the journal.

---

## What was built (by phase)

### Phase 0 — Foundation (app shell + design system)
- `app/templates/base.html` — new sidebar app-shell (header blocks, content, scripts).
- `app/static/tokens.css` — GUI-Golden-Book tokens + refined-minimal classes as
  **plain CSS** (no Tailwind build; System A 2px radius, warm-light + gold #c9a227).
- `app/templates/components/sidebar.html` — ported, plain CSS, auth/macros stripped,
  MOSYS nav (Measurements, SPC Tweaks, Records table, Chart).
- `app/templates/components/confirm_modal.html` — ported, plain CSS, English literals.
- `app/templates/components/toasts.html` — runtime toast + English undo toast.
- `cc-project-memory-files/spec.md` — MIS scale typo fixed **1000 → 10000**.
- Existing `routes.py` / `index.html` / `graph.html` untouched (blast-radius limit).

### Phase 1 — Mock harness
- `scripts/build_mock_data.py` — **read-only**, run against the real DSN by you.
  Pulls latest 100 NRILDIM + linked NSCHEDIM/SCHEDIM1 → `app/data/mock_mosys.sqlite`,
  emits `scripts/mock_report.md` (columns/dtypes, natural-key uniqueness, §2.1 scale
  sanity table). **I did NOT run this** (no DSN access; it's your process gate).
- `scripts/make_synthetic_mock.py` — offline fabricated mock for UI smoke/tests.

### Phase 2 — Measurements page (`/measurements`)
- Full-width, sticky-header, **horizontal-only** scroll table; per-column search +
  asc/desc **aria icon buttons**; 2-line clamp; 2px radius; footer with total rows +
  avg per-cavity (min/max/range) over the **whole** result set; top-right **SPC tweaks**
  button carrying the current filters.

### Phase 3 — SPC Tweaks page (`/spc-tweaks`)
- Chart.js line chart per cavity + USL/LSL/nominal reference lines; Cp/Cpk +
  min/avg/max/range **badges**; **spread-squeeze** slider; **`flatten picks`** toggle
  (disabled + noted when nominal unavailable); **date-range dual-handle slider**
  `[now−30d, now]` two-way bound to start/end pickers with per-picker **time-precision
  toggles**; **Preview** toggle animating current⇄tweaked (Chart.js 500 ms + badge
  transitions). Local-time date parsing per your date-formatting rule.

### Phase 4 — Safe-write backend (dry-run)
- `app/functions/spc.py` — pure transforms (squeeze §3.3, flatten §3.3.1), stats,
  Cp/Cpk, `compute_tweaked_updates` (raw ints via `round(x*10000)`, skips empty cells).
- `app/functions/mosys.py :: execute_nrildim_updates(..., dry_run=True)` — reuses
  `pervasive_connection(readonly=False)`; integrity gate (SCHEDIM1↔NSCHEDIM, FLAG_RIMOSSO),
  1-row COUNT probe, pre-image journal, `autocommit=False`, `rowcount==1` guard,
  post-commit verify, atomic rollback, journal purge/retain.
- `app/functions/nrildim_journal.py` — SQLite pre-image journal.
- `app/functions/mosys_data.py` — the **single shared** fetch/format pipeline both new
  pages import (÷10000, date/time, last-digit, drop-empty-MIS), preserving **RAW key
  columns** for write targeting. Reused from `routes.py` 1-to-1.

### Phase 5 — Commit wiring (`/spc-tweaks/commit`, POST)
- Confirm modal → `fetch` → recompute **server-side authoritatively** → dry-run-gated
  write → toast (`MOSYS records updated` / non-technical error). `config.WRITE_ENABLED`
  **fails closed** (only exact truthy env opt-in enables writes).

---

## Verification done offline (no DB)

`./venv/Scripts/python.exe -m unittest discover -s tests` → **29 passed**:
- `test_spc.py` — scale round-trip, MIS_AVG skip-empty, footer stats, squeeze
  shrinks spread by (1−s) + preserves group mean, flatten pulls only the pick to
  nb±10%, updates skip empty cells, Cp/Cpk.
- `test_write.py` — dry-run writes nothing + reports 1-row targeting, atomic commit +
  journal purge, **atomic rollback** keeps a valid row's original value + retains the
  journal, integrity gate aborts on removed characteristic, guards, **fail-closed flag**.
- `test_routes.py` — Flask test client renders `/measurements` + `/spc-tweaks`
  (200 + key markers), graceful DB-error page, commit JSON/toast contract incl.
  **non-technical** error scrubbing.
- `test_js_parity.py` — **JS (`spc_transform.js`) == Python (`spc.py`)** transform,
  exact across squeeze / flatten / both / no-op (via Node).

## What is NOT verified (needs you + the real DSN)
- **§2.1 scale gate** — the tests use a fabricated mock, so ÷10000 passes trivially.
  Real confirmation requires `scripts/build_mock_data.py` against the DSN.
- **Real NRILDIM natural-key uniqueness** — same; the report asserts it on the 100-row
  real snapshot.
- **Live UI rendering against real data** and the **one-row live write + rollback** smoke.

## Known caveats to check first if something errors
- `scripts/build_mock_data.py` uses `SELECT TOP 100 …` — Pervasive/Actian PSQL
  generally supports `TOP n`, but `routes.py` never uses it, so it's an unverified
  dialect assumption. If that script throws a syntax error, that's the first place
  to look (swap for the DB's row-limit syntax) — it does **not** mean the build is broken.
- `/spc-tweaks` passes `overall`/`capability` to the template but the badges
  recompute client-side; those two template vars are currently unused (harmless,
  flagged for later cleanup).

## Notes / small decisions I made
- Time-of-day filtering: the date-range control reloads the server fetch by **date**
  (routes.py filters date only); finer time precision is a UI affordance refining the
  client-side view. Flagged for you if you want true server-side `ORA_RILEVAMENTO`
  filtering next.
- `app/data/` and `scripts/mock_report.md` are gitignored (generated artifacts).
- pytest isn't installed; tests use stdlib `unittest` (zero-install).

## Suggested next steps
1. Run the DSN mock gate, review `mock_report.md`.
2. Click-test both pages against live data.
3. If the scale/key checks pass, enable `MOSYS_WRITE_ENABLED=true`, do the supervised
   one-row smoke + rollback, then it's production-ready.
