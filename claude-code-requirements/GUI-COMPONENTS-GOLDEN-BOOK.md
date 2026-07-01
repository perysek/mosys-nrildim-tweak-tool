# GUI Components Golden Book — Flask / Jinja2 / Tailwind

## The mandatory, reusable component library

> This is the **component-level** companion to [`GUI-GOLDEN-BOOK.md`](GUI-GOLDEN-BOOK.md)
> (which owns the page/system-level design language). This book owns the **seven shared
> components** that live in `templates/components/`. Each component has a dedicated
> sub-document under [`gui-components/`](gui-components/) that describes its design, full
> API, exact dependencies, and a copy-paste integration recipe for a **fresh project**.

---

## 0. The Iron Rule — use these, never re-invent them

**This component set is mandatory. Hand-rolling a one-off equivalent is forbidden.**

If a page needs a modal, a form field, a toast, an icon, a table, a flash banner, or a
sidebar link, you **import the component** — you do not write a bespoke `<input>`, a custom
`<svg>`, an ad-hoc `confirm()`, or a private `<div class="my-modal">`. Redundant hand-work
is a defect, not a style choice, because:

1. **Consistency** — every screen inherits the same tokens, radii, focus rings, and motion.
   A hand-rolled input drifts the moment the design tokens change.
2. **Accessibility** — the components already carry `aria-*`, focus traps, `role`, and
   `:focus-visible` rings. A bespoke copy almost always drops one of these.
3. **Deployment safety** — the components already pick the correct CSS delivery strategy
   (token `@layer` vs. inline `<style>`); a hand-rolled copy usually leaks styles that
   never reach the server (see §3).
4. **One source of truth** — a bug fixed in the component is fixed everywhere. A bug in a
   copy-pasted clone is fixed nowhere.

> **If a component is missing a variant you need, extend the component** (add a parameter,
> add a token-scoped class) **and document it here** — do not fork it inline. Updating the
> spec precedes deviating from it.

---

## 1. The seven components

| Component | Source file | Sub-document | One-line role |
|---|---|---|---|
| **Sidebar** ★ | `templates/components/sidebar.html` + `templates/macros/sidebar_macros.html` | [`gui-components/sidebar.md`](gui-components/sidebar.md) | App shell navigation rail: accordion sections, active-pill, mobile drawer with focus trap |
| **Icons** | `templates/components/icons.html` (+ `static/js/icons.js`) | [`gui-components/icons.md`](gui-components/icons.md) | Inline-SVG glyph system (Material Symbols paths), `icon()` macro + JS twin |
| **Form fields** | `templates/components/form_fields.html` | [`gui-components/form-fields.md`](gui-components/form-fields.md) | Token-based input/select/textarea/checkbox/currency macros + actions bar |
| **Scrollable table** | `templates/components/scrollable_table.html` | [`gui-components/scrollable-table.md`](gui-components/scrollable-table.md) | Table card, accessible sortable headers, empty state, status/OCR badges, skeleton |
| **Confirm modal** | `templates/components/confirm_modal.html` | [`gui-components/confirm-modal.md`](gui-components/confirm-modal.md) | Single global confirm/destructive dialog (`showConfirmModal`/`confirmDelete`) |
| **Flash messages** | `templates/components/flash_messages.html` | [`gui-components/flash-messages.md`](gui-components/flash-messages.md) | Server-side flash banners (rendered once by `base.html`) |
| **Undo toast** | `templates/components/undo_toast.html` | [`gui-components/undo-toast.md`](gui-components/undo-toast.md) | Soft-delete "Cofnij" toast that POSTs a restore endpoint |

★ = read the sidebar doc most carefully; it is the most integration-heavy component.

---

## 2. The dependency graph (read before porting anything)

Components are **not** standalone files you can copy in isolation. Edges that must travel
with them:

```
icons.html ─────────────► form_fields.html      (imports `icon`)
          └─────────────► scrollable_table.html  (imports `icon`)

ui_messages (config/ui_messages.py + msg()/MSG()) ──► confirm_modal.html

sidebar_macros.html ────► sidebar.html           (imports link/section macros)
--sidebar-* tokens ─────► sidebar.html  + input.css .sidebar-link* rules

input.css @layer components (form-*, btn-press, skeleton, th-sort*, animate-*)
   ──► form_fields, scrollable_table   (these classes MUST exist in the target project)

base.html  ──includes once──► flash_messages, confirm_modal, undo_toast
```

**Practical consequence:** porting `form_fields.html` into a fresh project that lacks the
`form-input` / `form-label` / `form-btn-primary` classes and the `--color-*` tokens yields
unstyled inputs. Each sub-document lists the exact tokens and classes to port first.

---

## 3. CSS delivery strategy — the single most important porting fact

There are **two** ways styling reaches the browser, and each component deliberately picks one:

| Strategy | Who uses it | Why | Porting note |
|---|---|---|---|
| **Token `@layer components`** (in `input.css`, compiled to `output.css`) | `form_fields`, `scrollable_table`, sidebar link/section classes | Reusable, themeable, purged/minified | Requires a Tailwind build step on deploy. Port the `@layer` rules + `:root` tokens. |
| **Inline `<style>` / `id`-scoped CSS** (inside the component file or `base.html`) | `confirm_modal`, `undo_toast`, toasts, SearchableSelect | Must work against a **pre-built `output.css` with no rebuild** | Self-contained — the `<style>` block travels with the component. Do **not** move it into `input.css`. |

> **Rule of thumb:** if a component ships its own `<style>` block, that block is load-bearing
> and deployment-critical — keep it inline. If it relies on `form-*`/`th-sort*`/`animate-*`
> classes, those must already exist (or be ported) in the target's `input.css`.

`output.css` is **gitignored** and rebuilt on the server at deploy. Never hand-edit it.
Build with `npm run build:css` after editing `input.css`.

---

## 4. Shared token contract (port these to a new project first)

Every component assumes these CSS custom properties exist in `:root` (in `input.css`).
This is the minimum viable token set; per-component docs note any extras.

```css
/* Ink / text */
--color-ink:        #1a1a1a;
--color-ink-muted:  #525252;
--color-ink-subtle: #8a8a8a;
/* Surfaces */
--color-surface:      #fafafa;
--color-surface-warm: #f7f6f3;
/* Borders */
--color-border:        #e8e6e1;
--color-border-subtle: #f0eeea;
/* Brand */
--color-accent:        #c9a227;
--color-accent-muted:  rgba(201,162,39,0.12);
/* Semantic */
--color-success: #2d6a4f;
--color-warning: #9a6700;
--color-error:   #9b2c2c;
--color-focus-ring: #2563eb;   /* used by :focus-visible rings + cm-info modal */
/* Status (confirm modal danger/warning/info button fills) */
--color-status-cancelled:      #dc2626;
--color-status-cancelled-dark: #b91c1c;
--color-status-in-progress:    #d97706;
--color-chart-blue:      #2563eb;
--color-chart-blue-dark: #1d4ed8;
--color-info-bg: #eff6ff;
/* Radius */
--radius-sm: 2px;
/* Typography */
--font-body:    'Inter', system-ui, sans-serif;
--font-display: 'Inter', system-ui, sans-serif;
/* Motion */
--ease-out-expo:  cubic-bezier(0.16, 1, 0.3, 1);
--ease-out-quart: cubic-bezier(0.25, 1, 0.5, 1);
```

Sidebar adds its own `--sidebar-*` block — see [`gui-components/sidebar.md`](gui-components/sidebar.md).

---

## 5. Shared JS globals the components expect

Loaded globally by `base.html` (order matters — see GUI-GOLDEN-BOOK §15). Components bind to:

| Global | Provided by | Consumed by |
|---|---|---|
| `pasteToField(id)` | `static/js/utils.js` | form_fields paste buttons |
| `msg(id)` / `MSG(id, vars)` | `ui_messages` (Jinja `msg`, JS `MSG`) | confirm_modal copy |
| `sortTable(key)` | page-owned sorter (per CLAUDE.md, `table-utils.js` was deleted) | scrollable_table `sortable_header` |
| `filterTable(el, idx)` | page-owned | scrollable_table `search_row` |
| `toggleTableSearch(id)` | page-owned | scrollable_table `search_toggle_button` |
| `Notifications.*` | `static/js/notifications.js` | runtime toasts (see GUI-GOLDEN-BOOK §13) |
| `Modals.*` | `static/js/modals.js` | generic overlay modals |
| `showConfirmModal` / `closeConfirmModal` / `confirmDelete` | confirm_modal.html (self) | delete flows app-wide |
| `showUndoToast(msg, url, ms)` | undo_toast.html (self) | soft-delete flows |

---

## 6. Universal accessibility contract

Every component already satisfies these — preserve them when integrating:

1. Icon-only buttons carry `aria-label` **and** `title`.
2. Dialogs use `role="dialog"`, `aria-modal="true"`, `aria-labelledby`, focus the safe
   default (Cancel), trap Tab, and close on Escape.
3. Sortable headers expose `aria-sort` and a real focusable `<button>` (Enter/Space work).
4. Active nav link has `aria-current="page"`.
5. Inputs are tied to labels via `for`/`id`.
6. Motion respects `@media (prefers-reduced-motion: reduce)`.

---

## 7. Per-component porting checklist (the 6-step ritual)

For each component, a fresh-session integration is always:

1. **Copy the component file** into `templates/components/` (and any macro/JS twin).
2. **Port its tokens** (§4 + the component's own token list) into `input.css :root`.
3. **Port its `@layer` classes** if it uses token classes (`form-*`, `th-sort*`, …).
4. **Wire its JS globals** (either it self-provides, or you supply `sortTable`, `pasteToField`, …).
5. **Include once in `base.html`** if it is a singleton (flash, confirm modal, undo toast).
6. **Build + verify**: `npm run build:css`, then Jinja-parse / grep — never browser-spot-check
   blindly; confirm the class names and macro signatures resolve.

Each sub-document gives the component-specific version of this ritual.

---

*Companion to GUI-GOLDEN-BOOK.md. Generated from a live codebase audit of `templates/components/`.*
