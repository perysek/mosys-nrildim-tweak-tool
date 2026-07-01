# Component: Scrollable Table (table card + sortable headers + states)

**Source:** `templates/components/scrollable_table.html`
**Type:** Jinja macro library. **Depends on** [`icons.md`](icons.md) (imports `icon`).
**CSS delivery:** mixes Tailwind arbitrary-token utilities (`bg-[var(--color-surface)]`) with
`@layer` classes (`th-sortable`, `th-sort-btn`, `th-sort-icon`, `skeleton`, `scrollbar-thin`,
`form-input`, `form-btn-primary`, `btn-press`, `animate-*`).

---

## 1. Purpose & when to use

The building blocks for **list/index pages**: a card-framed table with optional header + count
badge, accessible sortable column headers, an empty state, status/OCR badges, an icon action
button, a filter row, and a loading skeleton. Use these instead of hand-built `<table>` chrome so
every list page shares the same surface, borders, sort affordance, and a11y wiring.

---

## 2. The macros

```jinja2
{% from 'components/scrollable_table.html' import
   table_card, sortable_header, table_header_classes, search_row,
   empty_state, status_badge, ocr_badge, action_button,
   search_toggle_button, loading_skeleton %}
```

| Macro | Renders | Key params |
|---|---|---|
| `table_card(title, count_label, full_height, id, extra_classes)` | Card wrapper (white, 3px radius, soft shadow); `caller()` holds the `<table>` | `full_height=true` makes it flex-fill + sticky-scroll for dashboards |
| `sortable_header(label, sort_key, current_sort, current_order, align, width_class)` | `<th class="th-sortable" aria-sort>` wrapping a focusable `.th-sort-btn` + `.th-sort-icon` (▲/▼) | `align='left'|'center'|'right'` |
| `table_header_classes(full_height, with_search)` | Class string for `<thead>` headers (sticky when `full_height`) | — |
| `search_row(columns, visible)` | A `<tr>` of per-column filter inputs (`filterTable(this, idx)`) | `columns=[{id,placeholder,type,searchable}]` |
| `empty_state(col_count, icon, title, message, action_url, action_label, action_icon)` | Centered empty placeholder spanning all columns | — |
| `status_badge(status, size)` | Invoice status pill (token semantic colors + icon) | `status ∈ {Opłacona, Nieopłacona, Przeterminowana}` |
| `ocr_badge(confidence, show_label)` | OCR confidence pill (green ≥80 / amber ≥60 / red <60) | — |
| `action_button(icon, title, onclick, href, color, size)` | Icon-only row action (keeps `aria-label`+`title`) | `color ∈ {default,primary,danger,success,warning}` |
| `search_toggle_button(target_id, active)` | Filter-row toggle button | — |
| `loading_skeleton(col_count, row_count)` | Shimmer skeleton rows (`stagger-item` delay) | — |

### Canonical list page

```jinja2
{% call table_card('Klienci', count_label='%d klientów'|format(total)) %}
<table class="w-full">
  <thead>
    <tr class="{{ table_header_classes() }}">
      {{ sortable_header('Imię', 'name', current_sort, current_order) }}
      {{ sortable_header('Wizyt', 'visits', current_sort, current_order, align='right') }}
      <th class="px-6 py-3 text-right">Akcje</th>
    </tr>
  </thead>
  <tbody>
    {% for c in clients %}
    <tr class="border-b border-[var(--color-border-subtle)]">
      <td class="px-6 py-3">{{ c.name }}</td>
      <td class="px-6 py-3 text-right">{{ c.visits }}</td>
      <td class="px-6 py-3 text-right">
        {{ action_button('visibility', 'Zobacz', href=url_for('main.view_client', id=c.id), color='primary') }}
        {{ action_button('delete', 'Usuń', onclick='confirmDelete(...)', color='danger') }}
      </td>
    </tr>
    {% else %}
      {{ empty_state(3, 'people', 'Brak klientów', 'Dodaj pierwszego klienta.',
                     url_for('main.create_client'), 'Dodaj klienta') }}
    {% endfor %}
  </tbody>
</table>
{% endcall %}
```

---

## 3. The sort contract (the part most often gotten wrong)

`sortable_header` renders an accessible header:

- `<th class="th-sortable" aria-sort="ascending|descending|none" id="th-<key>">`
- a focusable inner `<button class="th-sort-btn" onclick="sortTable('<key>')">` (Enter/Space work)
- a glyph `<span class="th-sort-icon" id="si-<key>">` showing ▲/▼.

**Two sort modes — and your obligation differs:**

| Mode | `aria-sort` correctness | Your job |
|---|---|---|
| **Server-sorted** (`?sort=key` reload) | Correct at render time (Jinja sets it) | Just provide `current_sort`/`current_order` from the request |
| **Client-sorted** (JS reorders in place) | **Stale after a click** | Your `sortTable()` JS **must** update `aria-sort` on the clicked `<th>` and reset siblings to `none`, and flip the `.th-sort-icon` glyph |

```javascript
// client-sort: keep ARIA + glyph in sync (per CLAUDE.md, each list page owns its sorter)
th.setAttribute('aria-sort', dir === 'asc' ? 'ascending' : 'descending');
document.querySelectorAll('.th-sortable').forEach(o => { if (o !== th) o.setAttribute('aria-sort','none'); });
```

> Per CLAUDE.md the global `table-utils.js` was **deleted** — **each list page owns its own
> `sortTable()`** (and `filterTable`/`toggleTableSearch` if it uses the search row). The component
> provides the markup + a11y scaffold; the page provides the behaviour.

---

## 4. Badges & states

- **`status_badge`** maps Polish invoice statuses → token colors with an icon:
  `Opłacona`→success/`check_circle`, `Nieopłacona`→warning/`schedule`, `Przeterminowana`→error/`warning`;
  unknown → neutral surface + `help_outline`.
- **`ocr_badge`** thresholds confidence: ≥80 success, ≥60 warning, else error; optional `OCR` label.
- **`empty_state`** = circled icon + title + message + optional primary action link (`form-btn-primary`).
- **`loading_skeleton`** = `row_count`×`col_count` shimmer cells (`skeleton` class), staggered.
- **`action_button`** is icon-only but **keeps `aria-label` + `title`** — never strip these.

---

## 5. Fresh-project integration

1. Copy `templates/components/scrollable_table.html` **and** `icons.html` (it imports `icon`).
2. Ensure these `@layer`/utility classes exist in the target `input.css`:
   `th-sortable, th-sort-btn, th-sort-icon, th-sort-btn:focus-visible, skeleton, scrollbar-thin,
   form-input, form-btn-primary, btn-press, animate-fade-up, animate-fade-in` — plus the
   `--color-*` / `--color-border*` tokens used in the arbitrary-value utilities.
3. Implement page-local `sortTable(key)` (and `filterTable`, `toggleTableSearch` if used) — they are
   **not** shipped with the component.
4. `npm run build:css`. **Watch the purge:** arbitrary values like `bg-[var(--color-surface)]` and
   `bg-[rgba(45,106,79,0.12)]` are only kept if they appear literally in scanned source — they do
   here, but don't generate them via string interpolation.
5. For wide tables on mobile, opt into the shared **`.stack-cards`** pattern (GUI-GOLDEN-BOOK /
   DESIGN-TOKENS) rather than horizontal scroll.

---

## 6. Gotchas

- **`aria-sort` goes stale on client sort.** The single most common a11y regression — your JS must
  sync it (see §3).
- **No sorter is bundled.** Forgetting to add a page `sortTable()` yields buttons that do nothing.
- **Purge can drop arbitrary-value classes** if you build them dynamically. Keep them literal.
- **Status strings are Polish-literal keys.** `status_badge('Paid')` falls through to the neutral
  badge — pass the exact `Opłacona`/`Nieopłacona`/`Przeterminowana` strings (or extend the map).
- `table_card`'s `full_height=true` needs a flex-column page ancestor to actually fill height.
