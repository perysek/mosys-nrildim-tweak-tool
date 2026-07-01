# Plan Review: MOSYS SPC Feature — Implementation Plan & DB-Safe UPDATE Design

**Date:** 2026-07-01
**File:** new-feature-implementation-plan.md
**Verdict:** FAIL

> **Note on scope:** This document was reviewed against the `create-plan` skill's `PLAN-TEMPLATE.md`, which is written for Next.js/Supabase multi-phase projects (RLS, Server Actions, Zod, phase folders). This repo is a Flask + Pervasive/pyodbc application with a single, monolithic proposal document — not a phased plan folder. Template sections are graded by **intent** rather than literal header match, per the review process. Low template scores below reflect a genuine stack/format mismatch, not a verdict on engineering quality. The substantive findings are in **Critical Issues**, grounded in this repo's actual code (`app/routes.py`, `app/functions/mosys.py`, `cc-project-memory-files/spec.md`) and the governing `new-feature-PRD.txt`.

---

## Template Compliance

| # | Section | Status | Notes |
|---|---------|--------|-------|
| 1 | YAML Frontmatter | fail | No frontmatter at all (title/status/priority/tags/dates absent). |
| 2 | Executive Summary | pass | Mission and deliverables are conveyed via "Insight" + "What I'm going to implement" (Feature 1 / Feature 2), even though not in the literal Mission/Big Shift/Deliverables format. |
| 3 | Phasing Strategy | fail | No phase breakdown. Two substantial features plus a production DB-write path are bundled into one document with no size/scope/dependency structure. |
| 4 | Phase Table | fail | No phases exist to table. |
| 5 | Architectural North Star | fail | The "DB-safe UPDATE architecture" (8 numbered principles) covers backend write-safety intent well, but there is no equivalent stated architecture for the frontend (state management for Preview toggle, how ported `sidebar.html`/`confirm_modal.html`/`undo_toast.html` will be structured as reusable patterns). |
| 6 | Project Framework Alignment | fail | PRD (`new-feature-PRD.txt` line 13) explicitly requires applying rules from `./claude-code-requirements/*`. The plan only cites `spec.md` and three HTML partials — it does not confirm it read `GUI-GOLDEN-BOOK.md` or `GUI-COMPONENTS-GOLDEN-BOOK.md`. See Critical Issue #2. |
| 7 | Security Requirements | pass | The "DB-safe UPDATE architecture" section functionally covers this intent (integrity gate via `SCHEDIM1↔NSCHEDIM`, blast-radius bounding, pre-image journal, atomic rollback, dry-run default) — arguably stronger than a boilerplate RLS section for this project's actual risk (irreversible production data mutation). |
| 8 | Implementation Standards | fail | "Mock-first development" (step 1) is a reasonable test-strategy analog, but no documentation-update step is mentioned and no test framework/tooling is named. |
| 9 | Success Metrics & Quality Gates | fail | No explicit measurable success criteria or quality-gate checklist; the "Why UPDATE-safe confidence is HIGH" bullets are narrative justification, not gates. |
| 10 | Global Decision Log | fail | The two "confirmations" at the end function as pending decisions but aren't recorded in Status/Context/Decision/Consequences form. |
| 11 | Resources & References | fail | No references section; `spec.md` and the three HTML partials are only cited inline in prose. |

**Template Score:** 2/11 sections

---

## Critical Issues

1. **[Structural] No phase breakdown for a high-risk, multi-feature change.** The document bundles a new full-width results page, a new SPC-tweaks page with live chart preview, and a production database write path into one undivided plan. Given the write path mutates shop-floor measurement records irreversibly, splitting into phases (e.g., read-only Measurements page → SPC Tweaks UI/preview → mock-validated write path → live write path) would let each risk tier be reviewed and approved independently, consistent with the PRD's own request for a separate confirmation gate on "CRUD functions code-approach" (`new-feature-PRD.txt` line 31).

2. **[PRD compliance gap] `claude-code-requirements/*` rules are not confirmed as applied.** `new-feature-PRD.txt` line 13 states: *"apply requirements and rules defined in ./claude-code-requirements folder files. For conflicts with above spec-points - spec-points has priority."* The plan's UI section only discusses porting `sidebar.html`, `confirm_modal.html`, and `undo_toast.html` design language and references `spec.md`. It never confirms reading `GUI-GOLDEN-BOOK.md` (883 lines) or `GUI-COMPONENTS-GOLDEN-BOOK.md`, which are the canonical UI/UX rule sources per the PRD. Separately: `claude-code-requirements/STACK.md` currently describes an unrelated PostgreSQL/OCR/invoices/Docker stack (ports, `psycopg2`, Tesseract, `SQLAlchemy`/Alembic) that does not match this repo (Flask + `pyodbc` + Pervasive, no visible Alembic/Postgres usage in `app/functions/mosys.py` or `config.py`). This file appears to be stale/copied from a different project. The plan should explicitly flag `STACK.md` as non-authoritative for this app rather than silently treating "claude-code-requirements" as internally consistent.

3. **[Technical / data-integrity risk] The raw-value round-trip scale factor for MIS columns is never stated, and the two source-of-truth docs disagree.** `app/routes.py` (lines 175-176, 267-268) divides `MIS01`–`MIS10` by **10000** for display. `cc-project-memory-files/spec.md` (line 33-34) says values should be "divided by 1000." The squeeze transform (`x → M̄ + (x − M̄)(1 − s)`) operates on the *display-scale* value per the plan's own wording ("mean **M̄**... every measurement cell"), but the eventual `UPDATE` must write back the *raw* integer stored in `NRILDIM`. Using the wrong multiplier (1000 vs 10000) when converting the tweaked display value back to a raw integer would silently corrupt production measurement data by a factor of 10. This must be resolved and stated explicitly in the plan — ideally verified against the actual raw column type/values pulled from the mock — before any write-path code is built, not left to be "discovered."

4. **[Technical gap] PRD-mandated reuse of the existing DB context manager is not reconciled with the plan's stated transaction mechanics.** `new-feature-PRD.txt` line 29: *"For mosys CRUD, use existing context manager in ./functions/mosys.py."* The plan's "Insight" section describes `conn.autocommit = False` → `UPDATE` → `commit()`/`rollback()` as the transactional backbone. However, the existing `pervasive_connection()` context manager (`app/functions/mosys.py` lines 10-24) never calls `conn.commit()` or `conn.rollback()` — it only opens and closes the connection, relying on pyodbc's implicit rollback-on-close for anything uncommitted. The plan does not state whether it will extend `pervasive_connection` (e.g., a commit/rollback-aware write variant reusing the same connection-string/DSN logic) or add separate write plumbing. Left implicit, this risks either violating the PRD's explicit reuse instruction or duplicating connection logic inconsistently with `get_pervasive()`.

5. **[Minor / informational] "NRILDIM's true column set / natural key" is only partially unknown.** The plan frames discovering NRILDIM's schema and natural key as a goal of the mock-snapshot step. `cc-project-memory-files/spec.md` (lines 15-25) and `app/routes.py` (lines 86-88, 220-222) already show the queried NRILDIM columns in production use: `ARTICOLO, DATA_RILEVAMENTO, ORA_RILEVAMENTO, NUMERO_RIFERIMENTO, NUMERO_STAMPATA, NUMERO_FIGURA, MIS01`–`MIS10`. The mock is still useful for confirming there's no better DB-declared primary/unique key exposed via ODBC, but the plan should acknowledge this partial prior knowledge — it narrows, rather than starts from zero, the "discovery" framed in step 1.

6. **[Not a defect — recorded for completeness] Two confirmations gate implementation.** The plan explicitly asks the user to confirm (a) the squeeze-transform definition and (b) dry-run-by-default rollout before the write path is built. This correctly satisfies the PRD's line 31 instruction to seek confirmation on the CRUD code approach and should remain a hard gate — implementation should not proceed on the write path until both are answered, and until Critical Issues #3 and #4 above are resolved as part of that same gate.

---

## Verdict

**Template Score:** 2/11
**Ready:** No — Critical Issues #2, #3, and #4 must be resolved (PRD-required `claude-code-requirements` rules confirmed applied; MIS raw/display scale factor reconciled between `spec.md` and `app/routes.py`; write-path transaction mechanics reconciled with the PRD-mandated reuse of `pervasive_connection()`) before the write path is implemented. Structural issue #1 (no phase breakdown) should be addressed by splitting the plan before implementation begins, given the scope and the irreversible-write risk profile.
