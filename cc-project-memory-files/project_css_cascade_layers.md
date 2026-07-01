---
name: project-css-cascade-layers
description: input.css compiles to real CSS @layers; page <style> blocks are UNLAYERED and always beat @layer components — key to safe chrome consolidation
metadata: 
  node_type: memory
  type: project
  originSessionId: 2e961903-2c82-4a66-813b-98814002bc49
---

`static/css/input.css` compiles (Tailwind) to **real CSS cascade layers**
(`@layer base/utilities/components`). Page-local `<style>` blocks in templates
are **UNLAYERED author CSS**, which **always beats any layered rule regardless of
specificity** — only an `!important` layered declaration can win. Evidence: the
iOS input-zoom guard at `input.css` ~line 150 uses `font-size:16px !important`
*specifically because* page `.refined-input { font-size:0.8125rem }` (unlayered)
would otherwise override a non-important layered rule. The comment there spells
this out.

**CRITICAL CAVEAT — layers resolve PER-DECLARATION, not per-rule.** An unlayered
page rule only beats the layered one for properties it ACTUALLY declares. Any
property that exists ONLY in the layered canonical rule still applies to pages that
kept an inline copy lacking it. So lifting an OVERLOADED class name to `@layer
components` LEAKS its extra properties onto every page that reuses the name
differently. Two real leaks from the e635a27 pilot (fixed in 699c9eb):
- `.refined-input` (list SEARCH input: flex:1/min-width) leaked onto FORM inputs
  that reuse `.refined-input` (services/categories, invoice create/edit). Fix:
  scoped the canonical to `.search-card .refined-input`.
- `.refined-page` (centered `max-width:1400px`) leaked onto ~10 FULL-WIDTH pages
  (`*_refined` lists, calendars, dashboards) that use `.refined-page` as a
  full-height flex wrapper → capped them at 1400px on wide screens. Fix: REMOVED
  `.refined-page` from the shared layer entirely (too overloaded); re-added inline
  to the 3 centered list pages.

**How to apply:** only lift a class that is (a) used the SAME way everywhere, and
(b) strip a page's inline copy only when that block is BYTE-IDENTICAL to canonical
(then adopting the shared rule is a guaranteed no-op). For overloaded names
(`.refined-page`, `.refined-input`, `.table-container`) either don't share them or
scope them to a context class (`.search-card …`). Before lifting, grep the repo to
see if the class is reused for a different component.

**Tier-1 status: CLOSED by user 2026-06-30** (a91e8fc). Remaining items below are
OPEN/deferred, NOT in-progress — do not auto-resume; the user explicitly stopped
here. Open if asked: (a) a separate "dense-list" shared component set for the
full-height `*_refined` pages (sellers/invoices/history); (b) trimming the 15 inline
`.refined-table` copies down to just their page deltas; (c) migrating the ~27 other
templates that still hold inline chrome copies.

Round 1 (e635a27) — employees list chrome lifted to `@layer
components`. Round 2 (699c9eb, 2026-06-30) — clients/list + services/list migrated
(stripped byte-identical chrome; kept divergent bits like pink stat variant,
inline-flex `.action-icons`, `overflow:hidden` container); plus the two leak fixes
above. NOT migrated: sellers/list_refined + invoices/list_refined + history/list_refined
are a DIFFERENT full-height flex design (`.stats-bar`/`.search-input`/`.action-btn`,
not the stat-card pattern) — leave them. ~27 other templates still hold inline chrome
copies. `.refined-table` base UPGRADED slate→token (a91e8fc, 2026-06-30): the shared
`.refined-table` at input.css ~627 is now token-based (`var(--color-surface/border/
ink/ink-subtle)`, 0.75rem 1rem padding), no longer the slate `@apply` version. This
fixed the 2 fall-through pages (analytics/dashboard, services/view) that had no inline
copy, and de-slated leaked properties on the 15 inline definers. th has NO global
text-align (kept slate behaviour: first-child left, numeric `.text-right` utilities
untouched). The 15 inline `.refined-table` copies still diverge (table-layout, padding,
td-wrapping, min-width) and were NOT stripped — they keep their page overrides.
Related: [[project_design_system_state]], [[project_font_swap_pinned_display_selectors]].
