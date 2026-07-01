# GUI Golden Book — Flask / Jinja2 / Tailwind CSS
## Design & UX Specification for Python-Flask-Jinja Webview Applications

> This document is the single source of truth for all visual, interaction, and structural decisions.
> Follow it exactly when building new pages or components. Do not deviate unless you update this spec first.

---

## 0. Mandatory Design Law & Component Library

**This design system is mandatory, and the shared components are non-negotiable.**

Every authenticated page is built from the tokens, classes, and components defined here and in the
**[GUI Components Golden Book](GUI-COMPONENTS-GOLDEN-BOOK.md)**. **Redundant hand-work is forbidden** —
do **not** hand-roll a raw `<input>`, a bespoke `<svg>`, a private modal `<div>`, an ad-hoc
`confirm()`, or a one-off table when a documented token, class, or component already covers it.

Why this is a rule, not a preference:

- **Consistency** — every screen inherits identical radii, tokens, focus rings, and motion. A
  hand-rolled control drifts the instant tokens change.
- **Accessibility** — the components already carry `aria-*`, focus traps, `role`, and focus rings.
  A bespoke copy almost always drops one.
- **Deployment safety** — each component already picks the correct CSS delivery strategy
  (token `@layer` vs. inline `<style>`); a clone usually leaks styles that never reach the server.
- **One source of truth** — a fix in the component propagates everywhere; a fix in a clone fixes nothing.

> If a component lacks a variant you need, **extend the component and update its doc** — never fork
> it inline. Updating the spec precedes deviating from it.

### Component sub-documents (precise design + integration, portable to fresh projects)

| Component | Source | Spec |
|---|---|---|
| **Sidebar** ★ | `templates/components/sidebar.html` (+ `macros/sidebar_macros.html`) | [`gui-components/sidebar.md`](gui-components/sidebar.md) |
| **Icons** | `templates/components/icons.html` | [`gui-components/icons.md`](gui-components/icons.md) |
| **Form fields** | `templates/components/form_fields.html` | [`gui-components/form-fields.md`](gui-components/form-fields.md) |
| **Scrollable table** | `templates/components/scrollable_table.html` | [`gui-components/scrollable-table.md`](gui-components/scrollable-table.md) |
| **Confirm modal** | `templates/components/confirm_modal.html` | [`gui-components/confirm-modal.md`](gui-components/confirm-modal.md) |
| **Flash messages** | `templates/components/flash_messages.html` | [`gui-components/flash-messages.md`](gui-components/flash-messages.md) |
| **Undo toast** | `templates/components/undo_toast.html` | [`gui-components/undo-toast.md`](gui-components/undo-toast.md) |

General component rules, the dependency graph, the CSS-delivery-strategy table, and the per-component
porting ritual live in **[GUI-COMPONENTS-GOLDEN-BOOK.md](GUI-COMPONENTS-GOLDEN-BOOK.md)**.

---

## 1. Technology Stack

| Layer | Technology |
|---|---|
| CSS framework | Tailwind CSS (compiled via CLI, `input.css` → `output.css`) |
| Font | Inter (Google Fonts), weights 300/400/500/600/700 |
| Icons | Material Icons (Google CDN legacy) + inline SVG heroicons |
| JS utilities | Vanilla ES6 modules in `static/js/` |
| Template engine | Jinja2 with `base.html` inheritance |

**Critical deployment note:** `output.css` is gitignored. Any styles that must reach a deploy server without a build step **must** be inline `<style>` blocks inside `base.html`, not in `input.css`.

---

## 2. Design Philosophy — Refined Minimal

The current preferred aesthetic is **"refined minimal"**: sharp edges (2px radius), low-weight typography (Inter 300), restrained color use with only the content needing attention carrying color. The gold accent (`#c9a227`) is used sparingly as a highlight, not as a primary action color.

**Anti-patterns to avoid:**
- Gradient fill buttons on list/table pages
- Rounded-2xl (16px) radius outside of modals
- Heavy shadows on content cards
- Multiple competing accent colors on a single page

---

## 3. CSS Custom Properties (Design Tokens)

All tokens live in `:root` inside `input.css`. Use them via `var()` — never hardcode hex values in templates.

### Text / Ink

```css
--color-ink:        #1a1a1a   /* body text, headings */
--color-ink-muted:  #525252   /* secondary text, labels */
--color-ink-subtle: #8a8a8a   /* placeholders, helper text, table headers */
```

### Surfaces

```css
--color-surface:      #fafafa   /* panel backgrounds, dropdown panels */
--color-surface-warm: #f7f6f3   /* page body background */
```

### Borders

```css
--color-border:        #e8e6e1   /* standard dividers, input borders */
--color-border-subtle: #f0eeea   /* very light separators */
```

### Brand / Accent

```css
--color-accent:       #c9a227                   /* gold highlight */
--color-accent-muted: rgba(201, 162, 39, 0.12)  /* gold tinted background */
```

### Semantic (state colors)

```css
--color-success: #2d6a4f
--color-warning: #9a6700
--color-error:   #9b2c2c
--color-info:    #1e6091
```

### Appointment Status Colors

```css
--color-status-scheduled:    #2563eb / bg #eff6ff
--color-status-confirmed:    #059669 / bg #ecfdf5
--color-status-in-progress:  #d97706 / bg #fffbeb
--color-status-completed:    #2d6a4f / bg #f0fdf4
--color-status-cancelled:    #dc2626 / bg #fef2f2
--color-status-no-show:      #6b7280
```

### Chart Palette

```css
--color-chart-blue:   #2563eb
--color-chart-green:  #16a34a
--color-chart-orange: #ea580c
--color-chart-red:    #ef4444
--color-chart-purple: #7c3aed
--color-chart-pink:   #db2777
--color-chart-teal:   #14b8a6
--color-chart-amber:  #f59e0b
--color-chart-slate:  #64748b
--color-chart-sky:    #0ea5e9
```

### Sidebar Tokens

> **Current theme = warm light + gold** (a shade darker than the body surface). The old dark-slate
> values were retired. Full sidebar spec: [`gui-components/sidebar.md`](gui-components/sidebar.md).

```css
--sidebar-bg:            #dedad3   /* warm light rail */
--sidebar-bg-deep:       #d2cec6   /* user-info footer (slightly deeper) */
--sidebar-text:          #525252   /* default link text (= --color-ink-muted) */
--sidebar-text-hover:    #1a1a1a   /* = --color-ink */
--sidebar-text-active:   #1a1a1a   /* ink; gold reserved for pill/icon */
--sidebar-heading:       #595959   /* section header — darkened for WCAG AA (~5:1) */
--sidebar-border:        #ccc7be
--sidebar-hover-bg:      #e6e2db
--sidebar-active-bg:     var(--color-accent-muted)   /* rgba(201,162,39,.12) gold tint */
--sidebar-active-border: var(--color-accent)         /* #c9a227 gold pill + active icon */
```

---

## 4. Typography

| Use | Font | Weight | Size | Class / Var |
|---|---|---|---|---|
| Page title | Inter | 600 | 1.75rem | `.page-title` |
| Page subtitle | Inter | 300 | 0.8125rem | `.page-subtitle` |
| Stat value | Inter | 600 | 1.25rem | `.stat-value` |
| Stat label | Inter | 500 | 0.6875rem uppercase | `.stat-label` |
| Body / paragraph | Inter | 300–400 | 0.875rem | default |
| Table cell | Inter | 300–400 | 0.8125rem | `text-sm` |
| Table header | Inter | 500 | 0.6875rem uppercase | letter-spacing 0.12em |
| Form label | Inter | 500 | 0.875rem | `text-sm font-medium text-slate-700` |
| Input text | Inter | 300 | 0.8125rem | `font-weight: 300` |
| Button text | Inter | 400 | 0.75rem | letter-spacing 0.02em |

Letter-spacing on table headers: `0.12em`. On stat labels: `0.08em`. On button text: `0.02em`.

---

## 5. Border Radius — Two Systems (Pick One Per Project)

There are two border-radius conventions in the codebase. **New projects must choose one and apply it everywhere.**

### System A — Refined Minimal (recommended for data-heavy apps)

```
2px   — inputs, buttons, table containers, dropdowns, toast notifications
2px   — SearchableSelect panels and triggers
```

### System B — Rounded (form-heavy, friendlier UX)

```
rounded-xl  (0.75rem / 12px)  — form inputs, cards, action buttons
rounded-2xl (1rem    / 16px)  — modals, confirm dialogs, page section cards
```

**Confirm/generic modals** use rounded-2xl regardless of which system is chosen — they are overlay UI, not content UI.

---

## 6. Buttons

### Refined Minimal Buttons (match System A)

```css
/* Base */
.btn-refined {
    display: inline-flex; align-items: center; gap: 0.375rem;
    padding: 0.5rem 0.875rem;
    font-family: var(--font-body); font-size: 0.75rem; font-weight: 400;
    letter-spacing: 0.02em; border-radius: 2px;
    transition: all 0.25s var(--ease-out-expo); cursor: pointer;
}

/* Primary — dark fill */
.btn-refined-primary {
    background: var(--color-ink); color: white; border: none;
}
.btn-refined-primary:hover {
    background: var(--color-ink-muted);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

/* Secondary — white with border */
.btn-refined-secondary {
    background: white; color: var(--color-ink);
    border: 1px solid var(--color-border);
}
.btn-refined-secondary:hover {
    border-color: var(--color-ink-muted); background: var(--color-surface);
}

/* Ghost — for icon-only or low-emphasis */
.btn-refined-ghost {
    background: transparent; color: var(--color-ink-muted); border: none; padding: 0.5rem;
}
.btn-refined-ghost:hover { color: var(--color-ink); background: var(--color-surface); }
```

### Rounded Buttons (match System B, used in form macros)

```html
<!-- Primary -->
<button class="px-6 py-3 bg-gradient-to-r from-primary-500 to-primary-600 text-white 
               font-medium rounded-xl shadow-lg shadow-primary-500/20 btn-press
               hover:from-primary-600 hover:to-primary-700 transition-all">

<!-- Secondary -->
<button class="px-6 py-3 bg-white border border-slate-300 text-slate-700 
               font-medium rounded-xl hover:bg-slate-50 transition-colors btn-press">
```

### Danger Button (modal footers, both systems)

```css
/* Rounded variant in modals */
background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
border-radius: 0.625rem;
box-shadow: 0 1px 3px rgba(220,38,38,0.3);
```

### Table Action Buttons

```css
.table-action-btn {
    display: inline-flex; align-items: center; justify-content: center;
    padding: 6px 10px; border-radius: 6px; font-size: 13px; font-weight: 500;
    transition: all 0.2s ease; gap: 4px; text-decoration: none;
}
/* View / Edit */
.table-action-btn-view, .table-action-btn-edit {
    color: #4472C4; background: transparent; border: 1px solid #4472C4;
}
/* Delete */
.table-action-btn-delete { color: #DC3545; border: 1px solid #DC3545; }
/* Hover: fill with the border color, text turns white */
```

### Micro-interaction: `.btn-press`

Add `.btn-press` to any clickable button to get tactile press feedback:

```css
.btn-press:active { transform: scale(0.97); transition: transform 100ms ease-out; }
```

---

## 7. Form Fields

All form macros are in `templates/components/form_fields.html`. Use those macros — do not hand-roll form inputs.

### Base input styling

```python
# Jinja2 variable (defined in form_fields.html)
input_base_classes = 'w-full px-4 py-2 rounded-xl border border-slate-300 
  focus:ring-2 focus:ring-primary-500 focus:border-primary-500 outline-none 
  transition-all text-sm placeholder:text-slate-400 bg-white'
```

If using System A (2px radius), override `rounded-xl` with `border-radius: 2px` in the page's `<style>` block.

### Label styling

```html
<label class="block text-sm font-medium text-slate-700 mb-1">
    Field name <span class="text-red-500">*</span>  <!-- required indicator -->
</label>
```

### Available macros

| Macro | Purpose |
|---|---|
| `text_input(name, label, ...)` | Text field with optional paste button |
| `number_input(name, label, ...)` | Number field with optional paste button |
| `date_input(name, label, ...)` | Date picker (YYYY-MM-DD) |
| `select_input(name, label, options, ...)` | Native dropdown |
| `textarea_input(name, label, ...)` | Multi-line text |
| `checkbox_input(name, label, ...)` | Checkbox with label |
| `currency_input(amount_name, currency_name, ...)` | Amount + currency pair |
| `form_actions(submit_label, ...)` | Submit + cancel button bar |
| `field_error(field_name, error_message)` | Inline validation error |
| `field_helper(text)` | Helper/hint text below field |
| `readonly_field(label, value, ...)` | Non-editable display value |
| `form_section(title, icon, description)` | Card wrapper for field groups |

### Paste button (OCR workflow)

Forms that receive data from invoice scanning include a paste button on fields:

```python
text_input('invoice_number', 'Nr faktury', with_paste=True)
```

The button calls `pasteToField('field_id')` from `utils.js`.

---

## 8. SearchableSelect (Custom Dropdown)

All `<select>` elements with more than ~5 options should be enhanced with `SearchableSelect`.

### HTML setup

```html
<select id="client-select" name="client_id">
    <option value="">Wybierz klienta...</option>
    <!-- options -->
</select>
```

### JS wiring

**Jinja-rendered options (options already in HTML at page load):**

```javascript
document.addEventListener('DOMContentLoaded', function() {
    SearchableSelect.enhance('#client-select');
});
```

**Dynamically populated options (async fetch):**

```javascript
async function loadClients() {
    const data = await fetch('/api/clients').then(r => r.json());
    const sel = document.getElementById('client-select');
    sel.innerHTML = '<option value="">Wybierz...</option>';
    data.forEach(c => {
        const o = document.createElement('option');
        o.value = c.id; o.textContent = c.name;
        sel.appendChild(o);
    });
    SearchableSelect.sync('client-select');  // MUST be called after options are populated
}
```

### API

```javascript
SearchableSelect.enhance(el)       // wrap a native <select>, call once
SearchableSelect.sync(el)          // re-read options after dynamic population
SearchableSelect.setValue(el, val) // set value programmatically, updates trigger label
```

### CSS

SearchableSelect CSS lives in an **inline `<style>` block** in `base.html` — not in `input.css`. This is intentional (deployment safety). Classes: `.ss-wrap`, `.ss-trigger`, `.ss-panel`, `.ss-search`, `.ss-list`, `.ss-item`, `.ss-item--selected`, `.ss-item--focused`, `.ss-item--disabled`, `.ss-no-results`, `.ss-chevron`.

Key styling values: `border-radius: 2px`, `font-weight: 300`, `font-size: 0.8125rem`. The search highlight uses `background: rgba(201,162,39,.25)` (gold).

---

## 9. Layout Structure

### Shell

```html
<div class="flex h-full">
    <!-- Sidebar: w-64, dark, fixed left on desktop -->
    <aside class="w-64 flex-col shadow-xl hidden lg:flex" 
           style="background: var(--sidebar-bg);">
        <!-- Logo, Nav, User info, Logout -->
    </aside>

    <!-- Main content column -->
    <div class="flex-1 flex flex-col min-h-screen overflow-hidden">
        <header class="flex items-center gap-4 px-4 py-2">
            <!-- Mobile menu toggle (lg:hidden) -->
            <!-- page_actions block (right-aligned) -->
        </header>

        <!-- Flash messages — rendered by base.html, DO NOT re-render in child templates -->
        {% include 'components/flash_messages.html' %}

        <main class="flex-1 overflow-auto p-0" id="main-content">
            {% block content %}{% endblock %}
        </main>

        <footer class="bg-white/50 border-t border-slate-200 px-6 py-3 text-center text-xs text-slate-500">
            &copy; {{ now().year }} App Name.
        </footer>
    </div>
</div>
```

### Page content — two patterns

**Pattern A: Refined full-height page (list/table pages)**

```html
{% block content %}
<div class="refined-page">  <!-- padding 1rem 1.5rem, flex column, height 100% -->
    <div class="page-header">  <!-- flex, space-between -->
        <div>
            <h1 class="page-title">Title</h1>
            <p class="page-subtitle">Subtitle text</p>
        </div>
        <div class="flex gap-2"><!-- actions --></div>
    </div>

    <div class="actions-bar">  <!-- search + filter bar -->
        <!-- search input, filter dropdowns -->
    </div>

    <div class="table-container">  <!-- fills remaining height -->
        <table class="refined-table">...</table>
    </div>
</div>
{% endblock %}
```

**Pattern B: Card-based form/detail page**

```html
{% block content %}
<div class="p-6 space-y-6">
    <div class="flex items-center gap-4">
        <h1 class="page-title">Title</h1>
    </div>
    
    {% call form_section('Section Name', 'edit') %}
        {{ text_input('field', 'Label') }}
    {% endcall %}

    {{ form_actions('Save', 'save', url_for('route.cancel')) }}
</div>
{% endblock %}
```

---

## 10. Sidebar Navigation

### Structure

The sidebar uses collapsible accordion sections. Only one section can be expanded at a time (JavaScript-driven `maxHeight` animation).

```html
<!-- Sections defined via Jinja macros -->
{% from 'macros/sidebar_macros.html' import sidebar_link, sidebar_section_start, sidebar_section_end %}

{{ sidebar_section_start('section-id', 'Section Label', is_active_boolean) }}
    {{ sidebar_link(url_for('route'), 'Link Label', 'svg_path_d', is_current_boolean) }}
{{ sidebar_section_end() }}
```

### Active link indicator

Active link uses a left-edge **gold** pill (3px wide, `var(--color-accent)` = `#c9a227`) over a gold
tint background (`--sidebar-active-bg`), and the active icon also turns gold. The CSS uses
`view-transition-name: sidebar-active-link` to morph the highlight between page navigations via the
View Transitions API (progressive enhancement), with a `sidebar-link-enter` keyframe fallback and a
`prefers-reduced-motion` guard.

### User footer

Bottom of sidebar: avatar circle (**gold** gradient `linear-gradient(135deg, var(--color-accent), #a07d1a)`),
full name, Polish role label. Logout link turns red on hover via inline `onmouseenter`/`onmouseleave`
(not Tailwind), so it works without those exact utility classes in the build.

> Full structure, accordion/drawer JS, focus trap, `nav-mobile-hide` trim, and porting checklist:
> **[`gui-components/sidebar.md`](gui-components/sidebar.md)**.

---

## 11. Tables

### Refined table (preferred for new pages)

```html
<div class="table-container">
    <div class="table-scroll-wrapper">
        <table class="refined-table sortable-table" id="resultsTable">
            <thead>
                <tr>
                    <th class="sortable" onclick="sortTable(0)">
                        Header <span class="sort-icon">⇅</span>
                    </th>
                    <!-- no-sort column -->
                    <th class="no-sort">Actions</th>
                </tr>
            </thead>
            <tbody>
                <tr class="stagger-item table-row-hover">
                    <td>...</td>
                </tr>
            </tbody>
        </table>
    </div>
</div>
```

**Table header styling:** font-size 0.6875rem, font-weight 500, text-transform uppercase, letter-spacing 0.12em, color `var(--color-ink-subtle)`, border-bottom `var(--color-border)`.

**Row hover:** `.table-row-hover:hover { background-color: #f8fafc; }` from `input.css`.

**Stagger animation:** Add `.stagger-item` to `<tr>` elements — first 10 rows get delayed `fade-up` entrance.

### Column search / filter row

```html
<tr>
    <th>
        <div class="th-content">
            <div class="th-header">
                <span>Column</span>
                <span class="sort-icon">⇅</span>
            </div>
            <input type="text" class="column-search" placeholder="Szukaj..."
                   oninput="applyAllFilters()" />
        </div>
    </th>
</tr>
```

`applyAllFilters()` from `table-utils.js` handles all `.column-search` inputs simultaneously.

### Table utilities (table-utils.js)

```javascript
sortTable(columnIndex, tableId)        // toggle asc/desc, handles dates & numbers
applyAllFilters(tableId)               // apply all column-search filters
clearFilters(tableId)                  // reset all filter inputs
exportToCSV(tableId, filename)         // download visible rows as CSV
initializeTable(tableId)              // auto-init event listeners
```

Tables with class `.sortable-table` and an `id` are auto-initialized on DOMContentLoaded.

---

## 12. Modal System

There are two modal implementations. Use them in the appropriate context.

### Confirm Modal (delete/destructive actions)

Defined in `components/confirm_modal.html`, included once by `base.html`. Call it via:

```javascript
// Low-level function
showConfirmModal(formEl, title, message, confirmBtnText, type, callbackFn);

// High-level: confirm delete (form submit)
confirmDelete(form, itemName);

// High-level: JS callback-based (use this for AJAX actions)
Modals.confirm({
    title: 'Potwierdź usunięcie',
    message: 'Czy na pewno chcesz usunąć ten element?',
    confirmText: 'Usuń',
    onConfirm: () => { /* do the action */ }
});
```

**Types:** `'danger'` (red icon + button), `'warning'` (amber), `'info'` (blue).

### Generic Modal (data panels, forms in overlays)

```javascript
const overlay = Modals.show({
    title: 'Modal Title',
    content: '<p>HTML content here</p>',
    size: 'medium',   // 'small' | 'medium' | 'large'
    buttons: [
        { text: 'Anuluj', type: 'secondary', onClick: (e, overlay) => Modals.close(overlay) },
        { text: 'Zapisz', type: 'primary', onClick: (e, overlay) => { /* action */ } }
    ],
    onClose: () => {},
    closeOnOverlay: true
});

// Other shortcuts
Modals.alert({ title, message, type: 'info' });
Modals.loading('Przetwarzanie...');
Modals.closeAll();
```

**Button types:** `'primary'` (blue gradient), `'secondary'` (white bordered), `'danger'` (red gradient), `'success'` (green gradient). All use `border-radius: 0.625rem`.

### CSS classes (defined in input.css)

```
.modal-overlay    — full-screen backdrop, blur(4px), z-index 9999
.modal-content    — white panel, border-radius 1rem, max-height calc(100vh - 2rem)
.modal-header     — flex, border-bottom, gradient bg
.modal-body       — scrollable content area, padding 1.5rem
.modal-footer     — flex end, border-top, bg #f8fafc
.modal-close      — close button, rounded-lg, hover bg
```

---

## 13. Notifications

### Flash Messages (server-side, page load)

**Rendered once by `base.html` via `components/flash_messages.html`.** Never call `get_flashed_messages()` again in child templates — Flask's flash queue is single-read.

```python
# Flask route
flash('Operation successful', 'success')  # categories: success | error | warning | info
flash('Something went wrong', 'error')
```

The component renders gradient-background pills with SVG icons and a close (×) button.

### Toast Notifications (runtime, JS)

```javascript
Notifications.success('Saved successfully');
Notifications.error('Connection failed');
Notifications.warning('Check your input');
Notifications.info('Loading data...');

// Custom duration (ms), 0 = persistent
Notifications.show('Custom message', 'success', 8000);
Notifications.clear();  // remove all
```

Toast container: `fixed bottom-4 right-4 space-y-2 z-50`. Max 3 stacked — oldest removed automatically.

**Toast colors (inline in base.html):**

```
success: bg #f0f9f4, border #c8e8d4, icon #2d6a4f
error:   bg #fdf3f3, border #f0c8c8, icon #9b2c2c
warning: bg #fdf9ed, border #eddcaa, icon #9a6700
info:    bg #f2f6fd, border #c5d8f5, icon #1e6091
```

Border-radius: 2px. Animation: `toast-slide-up` 0.18s. Hover lifts box-shadow.

### Undo Toast (soft-delete pattern)

```javascript
showUndoToast('Record deleted', '/api/records/123/restore', 8000);
```

Defined in `components/undo_toast.html`, included once by `base.html`. White bg, green left-border (4px), "Cofnij" button in blue. Auto-hides after `duration` ms.

---

## 14. Animations & Micro-interactions

All defined in `@layer components` in `input.css`. Add class to element.

| Class | Effect | Use case |
|---|---|---|
| `.btn-press` | scale(0.97) on `:active` | All clickable buttons |
| `.hover-lift` | translateY(-2px) + shadow on hover | Cards, panels |
| `.animate-fade-up` | opacity + translateY(10px) → normal | Page sections on load |
| `.animate-fade-in` | opacity 0 → 1 | Inline dynamic content |
| `.animate-scale-in` | scale(0.95) + opacity → normal | Dropdowns, popovers |
| `.animate-slide-down` | expandable sections | Accordion content |
| `.stagger-item` | nth-child delay on `.animate-fade-up` | Table rows |
| `.skeleton` | shimmer shimmer loading | Placeholder while loading |
| `.success-pulse` | green ring pulse | After save action |
| `.error-shake` | horizontal shake | Validation failure |
| `.animate-spin-slow` | 1.5s spin | Loading indicators |
| `.animate-bounce-subtle` | slight bounce | Attention grabber |

**Easing functions:**

```css
--ease-out-expo:  cubic-bezier(0.16, 1, 0.3, 1)   /* snappy deceleration */
--ease-out-quart: cubic-bezier(0.25, 1, 0.5, 1)   /* smooth deceleration */
```

**Reduced motion:** Sidebar animations, toast animations and modal entrance animations all respect `@media (prefers-reduced-motion: reduce)`.

---

## 15. JavaScript Library Reference

All scripts are loaded globally by `base.html` in this order:

```html
<script src="utils.js"></script>          <!-- escapeHtml, pasteToField, etc. -->
<script src="api.js"></script>            <!-- fetch wrapper with error handling -->
<script src="notifications.js"></script>  <!-- Notifications.show/success/error/etc. -->
<script src="modals.js"></script>         <!-- Modals.show/confirm/alert/loading -->
<script src="table-utils.js"></script>    <!-- sortTable, applyAllFilters, exportToCSV -->
<script src="keyboard-shortcuts.js"></script>
<script src="searchable-select.js"></script> <!-- SearchableSelect.enhance/sync/setValue -->
```

Always use `escapeHtml(str)` (from `utils.js`) when injecting user data into `innerHTML`.

---

## 16. Accessibility Requirements

Every page must satisfy these:

1. **Skip link** — provided by `base.html` targeting `#main-content`
2. **Icon-only buttons** — must have `aria-label="..."` 
3. **Active nav link** — `aria-current="page"` on the sidebar `<a>` for the current route
4. **Modals** — `role="dialog"`, `aria-modal="true"`, `aria-labelledby` pointing to modal title
5. **Form fields** — `<label for="...">` tied to `id="..."` on the input
6. **SR-only text** — `.sr-only` class available for screen-reader-only labels
7. **Focus management** — modals move focus to first focusable element; Escape closes
8. **Color contrast** — all body text on white backgrounds meets WCAG AA (ink `#1a1a1a` on `#ffffff` = 18.1:1)

---

## 17. Responsive Behavior

- **Sidebar:** `hidden lg:flex` — hidden below 1024px, shown as fixed left column above
- **Mobile toggle:** `#sidebar-toggle` button in header, shown only `lg:hidden`
- **Mobile overlay:** `#sidebar-overlay` — dark backdrop behind open mobile sidebar
- **Table responsive:** `.table-enhancements.css` hides lower-priority columns at 768px and 576px breakpoints
- **Form grid:** `grid-cols-1 md:grid-cols-2` — single column on mobile, two-column on md+
- **Full-width field:** `md:col-span-2` — spans both columns

---

## 18. Page Template Blocks

```jinja2
{% extends "base.html" %}

{% block title %}Page Title — App Name{% endblock %}

{% block extra_head %}
<!-- Additional <link> tags, meta tags -->
{% endblock %}

{% block extra_css %}
<style>
    /* Page-specific overrides — use sparingly */
</style>
{% endblock %}

{% block page_actions %}
<!-- Rendered inside <header>, right-aligned -->
<!-- Use for primary page CTAs like "Add New" buttons -->
{% endblock %}

{% block content %}
<!-- Main page content goes here -->
{% endblock %}

{% block scripts %}
<!-- Page-specific <script> blocks -->
{% endblock %}

{% block extra_scripts %}
<!-- Additional scripts loaded last -->
{% endblock %}
```

**Rules:**
- Never call `get_flashed_messages()` in child templates — `base.html` handles it
- Never add `{% block content %}` twice — only one content block per page
- `{% block page_actions %}` is optional and only for header-level actions

---

## 19. Status Badge Pattern

```html
<!-- Appointment status badge -->
<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
      style="background: var(--color-status-confirmed-bg); color: var(--color-status-confirmed);">
    Potwierdzona
</span>
```

Replace `confirmed` with the appropriate status name from section 3.

---

## 20. Info Panels

```html
<!-- Blue info panel -->
<div class="rounded-lg p-4"
     style="background: var(--color-info-bg); border: 1px solid var(--color-info-border);">
    <p class="text-sm" style="color: var(--color-info-text);">
        Info message here
    </p>
</div>
```

CSS vars: `--color-info-bg: #eff6ff`, `--color-info-border: #bfdbfe`, `--color-info-text: #1e40af`.

---

## 21. Scrollbar Styling

```css
/* Custom scrollbar — applied via .scrollbar-thin utility class */
.scrollbar-thin::-webkit-scrollbar { width: 8px; height: 8px; }
.scrollbar-thin::-webkit-scrollbar-track { background: #f1f5f9; }
.scrollbar-thin::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
.scrollbar-thin::-webkit-scrollbar-thumb:hover { background: #94a3b8; }

/* 5px thin variant inside SearchableSelect panel */
.ss-list::-webkit-scrollbar { width: 5px; }
.ss-list::-webkit-scrollbar-thumb { background: var(--color-border); border-radius: 2px; }
```

---

## 22. Known Design Inconsistencies (Do Not Replicate)

These inconsistencies exist in the current codebase due to iterative development. New projects should pick one convention and apply it everywhere.

| Issue | Legacy Pattern | Preferred Pattern |
|---|---|---|
| Border radius | `rounded-xl`/`2xl` on form inputs | `2px` everywhere |
| Button style | Tailwind gradient `from-primary-500` | `.btn-refined-primary` (dark fill) |
| Table button radius | `rounded-xl` | `border-radius: 6px` (table-enhancements.css) |
| Font weight on inputs | `text-sm` (no weight override) | explicit `font-weight: 300` |
| Card shadow | `shadow-md/lg` | `border: 1px solid var(--color-border)` only |

Modals are the **only exception** — they remain `rounded-2xl` regardless of the page's design system, because they are overlay UI that should feel elevated and distinct.

---

## 23. Deployment Checklist

- [ ] No raw Tailwind classes that depend on dynamic string interpolation (they won't be detected by purge)
- [ ] Critical UI styles (toasts, dropdowns, tables) are in `base.html` inline or in `table-enhancements.css`, not in `input.css` only
- [ ] `output.css` is built before deployment (`npx tailwindcss -i input.css -o output.css --minify`)
- [ ] Google Fonts preconnect is in `<head>` before the fonts `<link>`
- [ ] Flash messages called only once (in `base.html` via `flash_messages.html` include)
- [ ] All native `confirm()` / `alert()` replaced with `Modals.confirm()` / `Modals.alert()`
- [ ] All `<select>` with 5+ options enhanced with `SearchableSelect`
- [ ] `SearchableSelect.sync()` called after every async option-population function

---

*Last updated from codebase audit: 2026-06-30 — added §0 Mandatory Design Law + component
sub-document index; corrected sidebar tokens (dark slate → warm-light gold). Component-level specs:
[GUI-COMPONENTS-GOLDEN-BOOK.md](GUI-COMPONENTS-GOLDEN-BOOK.md).*
