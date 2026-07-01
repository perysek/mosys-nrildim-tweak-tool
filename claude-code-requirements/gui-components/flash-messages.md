# Component: Flash Messages (server-side banners)

**Source:** `templates/components/flash_messages.html`
**Type:** Jinja partial (no macro — a direct `{% with %}` render block).
**CSS delivery:** Tailwind utility classes only (no custom `<style>`, no JS).

---

## 1. Purpose & when to use

Renders Flask's server-side `flash()` queue as dismissible banner pills at the top of the content
area, on full page loads. Four categories: `success`, `error`, `warning`, `info` — each with its
own color set and inline SVG icon.

Use it for **post-redirect-get** feedback ("Zapisano", "Błąd zapisu"). For **runtime/JS** feedback
(no page reload), use toast `Notifications.*` instead (GUI-GOLDEN-BOOK §13); for **soft-delete with
undo**, use [`undo-toast.md`](undo-toast.md).

---

## 2. The single-read rule (critical)

`get_flashed_messages()` **drains** Flask's flash queue — it can be read only once per request.
Therefore:

> **`base.html` includes this component exactly once. Child templates MUST NOT call
> `get_flashed_messages()` again, and MUST NOT re-include `flash_messages.html`.**

A second read returns an empty list (banners vanish) or, worse, double-renders if ordering shifts.
This is the #1 flash bug — treat the single include as inviolable.

---

## 3. Markup contract

```jinja2
{% with messages = get_flashed_messages(with_categories=true) %}
  {% if messages %}
  <div class="px-6 pt-4 space-y-2">
    {% for category, message in messages %}
    <div class="flex items-center gap-3 px-4 py-3 rounded-[3px] shadow-sm border …" role="alert">
      …category icon (inline SVG)…
      <p class="text-sm font-medium flex-1">{{ message }}</p>
      <button onclick="this.parentElement.remove()" aria-label="Zamknij powiadomienie">×</button>
    </div>
    {% endfor %}
  </div>
  {% endif %}
{% endwith %}
```

Category → palette (Tailwind classes, all flat, 3px radius):

| Category | bg / border / text |
|---|---|
| `success` | `emerald-50` / `emerald-200` / `emerald-800` (icon `emerald-500`) |
| `error` | `red-50` / `red-200` / `red-800` (icon `red-500`) |
| `warning` | `amber-50` / `amber-200` / `amber-800` (icon `amber-500`) |
| `info` *(default/else)* | `blue-50` / `blue-200` / `blue-800` (icon `blue-500`) |

- `role="alert"` so screen readers announce it.
- The close button is pure inline JS (`this.parentElement.remove()`) — no library dependency.

---

## 4. Producing flashes (Flask side)

```python
flash('Zapisano zmiany', 'success')
flash('Nie udało się zapisać', 'error')
flash('Sprawdź dane', 'warning')
flash('Ładowanie…', 'info')   # any non-matching category falls through to the info palette
```

---

## 5. Fresh-project integration

1. Copy `templates/components/flash_messages.html`.
2. In `base.html`, render it **once**, inside the main content column, above `{% block content %}`:
   ```jinja2
   {% include 'components/flash_messages.html' %}
   <main id="main-content">{% block content %}{% endblock %}</main>
   ```
3. No tokens, no `@layer` classes, no JS to port — it uses raw Tailwind color utilities, so just
   ensure those colors are in the Tailwind build (they're standard palette → always present).
4. **Never** add a second include or a child-template `get_flashed_messages()` call.

---

## 6. Gotchas

- **Double-read = disappearing banners.** If flashes "randomly don't show", grep for a stray
  `get_flashed_messages` in child templates.
- Colors are **literal Tailwind palette classes** (`emerald-50`, not tokens) — this is the one
  component that intentionally bypasses the `--color-*` token system, so it has zero token
  dependency and ports cleanly anywhere Tailwind is present.
- Banners are **not** auto-dismissed; they persist until the user closes them or the next
  navigation. For timed dismissal use toast `Notifications.*` instead.
