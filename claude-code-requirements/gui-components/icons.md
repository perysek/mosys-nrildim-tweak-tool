# Component: Icons (inline-SVG glyph system)

**Source:** `templates/components/icons.html` — JS twin: `static/js/icons.js`
**Type:** Jinja macro library + parallel JS registry. **No external font.**
**CSS delivery:** none required (SVG inherits `currentColor`); only sizing utilities.

---

## 1. Purpose & when to use

The single icon system for the whole app. Renders **inline SVG** from a frozen dictionary of
Material Symbols (outlined) path data. **The Material Icons web-font is removed and forbidden** —
inline SVG means no FOUT, no extra network request, correct color via `currentColor`, and crisp
sizing via `font-size`/`width`.

Use it for **every** glyph: buttons, table actions, empty states, status badges, form labels.

---

## 2. Public API

```jinja2
{% from 'components/icons.html' import icon %}

{{ icon('save') }}                                  {# default size: 1em, currentColor #}
{{ icon('delete', class='text-base text-red-600') }}
{{ icon('expand_more', class='text-lg', style='color: var(--color-ink-subtle);') }}
{{ icon('search', size='20') }}                     {# explicit px width/height #}
```

Macro signature:

```jinja2
{% macro icon(name, class='', style='', size=None) %}
```

| Param | Effect |
|---|---|
| `name` | Key into the path dictionary. **Unknown name falls back to `info`** (never blank). |
| `class` | Appended after the base `icon` class. Size with `text-*`; color with `text-*` or `style`. |
| `style` | Inline style passthrough (e.g. token color). |
| `size` | Optional explicit `width`/`height` in px. Omit to size by font-size (`1em`). |

Rendered output:

```html
<svg class="icon {{ class }}" viewBox="0 -960 960 960" fill="currentColor"
     aria-hidden="true" focusable="false">…path…</svg>
```

> **Note the `viewBox="0 -960 960 960"`** — Material Symbols coordinate space. Do not mix paths
> from other icon sets without matching the viewBox, or they render off-canvas.

### JS twin

`static/js/icons.js` mirrors the same dictionary for runtime injection:

```javascript
Icons.svg('save', 'text-base');   // returns an <svg> string for innerHTML
```

**Both files must stay in sync** — adding a glyph means editing **both** `icons.html` and
`icons.js` (the header comment in each says so).

---

## 3. Sizing & color contract

- **Color:** the SVG uses `fill="currentColor"`, so it takes the element's text color. Set it
  with a Tailwind `text-*` class or a token `style="color: var(--color-…)"`.
- **Size:** `1em` by default → scales with surrounding font-size. Use `text-sm`/`text-lg`/`text-xl`
  to size, **not** width hacks, unless you pass `size=`.
- `aria-hidden="true"` + `focusable="false"` are baked in: icons are decorative. If an icon is
  the *only* content of a button, the **button** must carry `aria-label` (see other components).

---

## 4. Adding a new glyph (the only sanctioned extension)

1. Fetch the Material Symbols **outlined** path `d` for the glyph (viewBox `0 -960 960 960`).
2. Add `'glyph_name': '<path d="…"/>',` to `_ICON_PATHS` in `templates/components/icons.html`.
3. Add the identical entry to the registry in `static/js/icons.js`.
4. Rebuild not required (no CSS), but verify with a Jinja parse / grep that both keys exist.

Never hand-draw, never re-introduce the icon font, never inline a raw `<svg>` in a template when
a macro call will do.

---

## 5. Fresh-project integration

1. Copy **both** `templates/components/icons.html` and `static/js/icons.js`.
2. Ensure `static/js/icons.js` is loaded in `base.html` (before page scripts that call `Icons.svg`).
3. No tokens or `@layer` classes required — it is self-contained.
4. Import the macro in any template: `{% from 'components/icons.html' import icon %}`.

**Dependency note:** `form_fields.html` and `scrollable_table.html` both import `icon` from this
file. Port icons **first**.

---

## 6. Gotchas

- **Unknown name → `info` glyph**, not an error and not blank. Misspellings fail silently as an
  ℹ️ — grep your `icon('…')` names against `_ICON_PATHS` keys when something looks wrong.
- The dictionary has **two `info_outline` keys** (one empty, one real) in the current source; the
  later wins in Jinja. Harmless, but don't replicate the duplication when porting.
- Keep `icons.html` and `icons.js` byte-aligned on names — a glyph present in one but not the other
  breaks either server-render or JS-render depending on which is missing.
