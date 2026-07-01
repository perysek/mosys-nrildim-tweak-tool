# Component: Form Fields (input macro library)

**Source:** `templates/components/form_fields.html`
**Type:** Jinja macro library. **Depends on** [`icons.md`](icons.md) (imports `icon`).
**CSS delivery:** token-based `@layer components` classes in `input.css` (`form-*`, `btn-press`,
`animate-fade-*`). These classes **must exist** in the target project.

---

## 1. Purpose & when to use

The mandatory way to build forms. Every input, select, textarea, checkbox, currency pair, and the
submit/cancel bar comes from these macros — **never hand-roll a raw `<input>`**. They encode the
flat System-B language (2px radius, `--color-*` tokens, refined focus ring, ≥16px font on mobile to
prevent iOS zoom) and the OCR "paste" workflow in one place.

---

## 2. The macros

```jinja2
{% from 'components/form_fields.html' import
   text_input, number_input, date_input, select_input, textarea_input,
   checkbox_input, currency_input, form_actions, field_error, field_helper,
   readonly_field, form_section %}
```

| Macro | Renders | Key params |
|---|---|---|
| `text_input(name, label, …)` | Text field (+ optional paste btn) | `value, placeholder, required, with_paste, full_width, autocomplete, maxlength, pattern, readonly, extra_classes` |
| `number_input(name, label, …)` | Numeric field (`font-semibold`) | `min, max, step='0.01', with_paste, full_width, …` |
| `date_input(name, label, …)` | `type=date` (YYYY-MM-DD) | `min, max, with_paste, full_width` |
| `select_input(name, label, options, …)` | Native `<select>` + chevron icon | `options` = list of strings **or** `[{value,label,selected}]`; `selected_value, placeholder, onchange, full_width` |
| `textarea_input(name, label, …)` | Multi-line | `rows=3, maxlength, resize='none'|'vertical'|'horizontal'|'both', with_paste, full_width` |
| `checkbox_input(name, label, …)` | Checkbox + label (+ description) | `checked, value='1', description, full_width` |
| `currency_input(amount_name, currency_name, …)` | Amount + currency pair | `currencies=['PLN','EUR','USD','GBP'], with_paste, required` |
| `form_actions(submit_label, …)` | Submit + cancel bar | `submit_icon='save', cancel_url, cancel_label='Anuluj', is_loading` |
| `field_error(field_name, error_message)` | Inline validation error (red, `error_outline` icon) | — |
| `field_helper(text)` | Helper/hint text below a field | — |
| `readonly_field(label, value, …)` | Non-editable display chip | `icon, full_width` |
| `form_section(title, icon, description)` | **Card wrapper** (call-block) for a field group | wraps `caller()` in a `grid md:grid-cols-2` |

### Canonical page shape

```jinja2
{% call form_section('Dane klienta', 'badge', 'Podstawowe informacje') %}
    {{ text_input('first_name', 'Imię', required=true) }}
    {{ text_input('last_name', 'Nazwisko', required=true) }}
    {{ text_input('email', 'E-mail', full_width=true) }}
    {{ select_input('status', 'Status', [
        {'value':'active','label':'Aktywny'},
        {'value':'inactive','label':'Nieaktywny'}], selected_value='active') }}
{% endcall %}

{{ form_actions('Zapisz', cancel_url=url_for('main.clients_list')) }}
```

---

## 3. The class & token contract

The macros emit **token classes**, not inline styles, for the controls:

```jinja2
{% set input_base_classes = 'form-input' %}
{% set label_classes      = 'form-label' %}
{% set paste_btn_classes  = 'form-paste-btn btn-press' %}
```

Selects use `form-select`, textareas `form-textarea`, the section uses `form-card`, the actions use
`form-btn-primary` / `form-btn-secondary`. **All of these live in `input.css @layer components`** and
must be present in the target project. Required tokens referenced directly in the macros:
`--color-ink`, `--color-ink-muted`, `--color-ink-subtle`, `--color-surface`, `--color-border`,
`--color-error`, `--radius-sm`.

> **Why classes, not inline styles?** So a token change re-themes every form at once, and so the
> global iOS-zoom guard (`font-size:16px !important` at ≤1023px, defined in `input.css`) can reach
> these inputs. A hand-rolled `<input style="…">` escapes both — which is exactly why hand-rolling
> is banned.

---

## 4. Notable behaviours

- **Paste workflow (OCR):** `with_paste=true` renders a button calling `pasteToField('<name>')`
  (from `static/js/utils.js`) — used on invoice-scan forms to drop clipboard text into a field.
- **Required indicator:** `required=true` appends a `*` in `var(--color-error)`.
- **`full_width=true`** → `md:col-span-2` (spans both columns of the `form_section` grid).
- **`form_actions` cancel is a real `<a href>`** (not a JS back) so middle-click / open-in-new-tab /
  hover-preview work; the submit shows a spinner + "Zapisywanie…" when `is_loading=true`.
- **`select_input` chevron** is an absolutely-positioned `icon('expand_more')` (native arrow hidden
  via `form-select`).
- Section cards animate in with `animate-fade-up`.

---

## 5. Fresh-project integration

1. Copy `templates/components/form_fields.html` **and** `templates/components/icons.html`
   (hard dependency — it imports `icon`).
2. Ensure these `@layer components` classes exist in the target `input.css`:
   `form-input, form-label, form-select, form-textarea, form-paste-btn, form-card,
   form-btn-primary, form-btn-secondary, btn-press, animate-fade-up, animate-fade-in`.
   (Port them from this project's `input.css` if absent.)
3. Port the tokens listed in §3.
4. Provide `pasteToField(id)` in `utils.js` if you use `with_paste`.
5. `npm run build:css`, then verify the class names resolve (grep the built `output.css`).

---

## 6. Gotchas

- **Missing `@layer` classes = unstyled forms.** The macros reference `form-input` etc. by name; if
  the target project never had them, inputs render as raw browser controls. Port the classes first.
- **`select_input` is a *native* select.** For 5+ options, enhance it with `SearchableSelect`
  (GUI-GOLDEN-BOOK §8) after render — the macro itself does not do this.
- **Don't override radius with page `!important`.** The iOS-zoom font guard and the token radius are
  global by design; page-level overrides re-introduce the mobile zoom bug.
- `number_input` hard-codes `step='0.01'` default and adds `font-semibold` — pass an explicit `step`
  for integer fields.
