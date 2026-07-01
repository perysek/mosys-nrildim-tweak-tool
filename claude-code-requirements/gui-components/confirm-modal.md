# Component: Confirm Modal (global destructive-action dialog)

**Source:** `templates/components/confirm_modal.html`
**Type:** Singleton markup + `<style>` + `<script>`, included **once** by `base.html`.
**CSS delivery:** **inline `id`-scoped `<style>`** — deliberately not in `input.css`, so it works
against a pre-built `output.css` **without a Tailwind rebuild** (matches the golden-master
`appointments/list.html`).

---

## 1. Purpose & when to use

The one and only confirmation dialog for destructive / irreversible actions (delete, deactivate,
discard). It supports two outcomes — **submit a form** or **run a JS callback** — and three visual
types: `danger` (red), `warning` (amber), `info` (blue).

- Hard delete / irreversible → **this**.
- Reversible soft delete → [`undo-toast.md`](undo-toast.md) instead.
- Rich content / multi-field overlay → generic `Modals.show()` (GUI-GOLDEN-BOOK §12).

> **Never use the native `confirm()`/`alert()`.** They are blocking, unstyled, and inaccessible.
> This component replaces them everywhere.

---

## 2. Public API

```javascript
// Low-level: full control
showConfirmModal(form, title, message, confirmBtnText, type /* 'danger'|'warning'|'info' */, callback);

// High-level: delete a record via a form submit (returns false to cancel default)
confirmDelete(formElement, itemName);

// Close programmatically
closeConfirmModal();
```

Two mutually exclusive outcomes, chosen by which argument you pass:

| Pattern | Pass | On confirm |
|---|---|---|
| **Form submit** | `form` = the `<form>` element, `callback` = null | `form.submit()` |
| **JS callback** | `form` = null, `callback` = a function | `callback()` runs (use for AJAX) |

### Usage examples

```html
<!-- A) Delete form, declarative -->
<form method="POST" action="/clients/12/delete"
      onsubmit="return confirmDelete(this, 'Jan Kowalski')">
  <button type="submit">Usuń</button>
</form>
```

```javascript
// B) AJAX delete via callback
showConfirmModal(
  null,
  'Dezaktywować klienta?',
  'Klient zniknie z aktywnej listy. Można go przywrócić później.',
  'Dezaktywuj',
  'warning',
  async () => {
    await fetch(`/api/clients/${id}/deactivate`, { method: 'POST' });
    location.reload();
  }
);
```

`confirmDelete()` pulls its copy from the `ui_messages` layer:
`MSG('modal.delete.title')`, `MSG('modal.delete.message', { item })`, `MSG('modal.delete.confirm_btn')`.

---

## 3. Design & motion contract

- **Backdrop** `#confirm-modal-backdrop`: `rgba(0,0,0,0.35)` + `backdrop-filter: blur(4px)`, fades
  in via `.is-open` (opacity, `--ease-out-expo`). Clicking it closes.
- **Panel** `#confirm-modal-panel`: white, `1px var(--color-border)`, **`border-radius: 3px`**,
  `box-shadow: 0 8px 32px rgba(0,0,0,.18)`; enters with `translateY(8px) scale(0.98)` → none.
- **Buttons** `.cm-btn` (id-scoped, flat, 2px radius): `.cm-btn-cancel` (white/bordered) and
  `.cm-btn-confirm` colored by type:
  - `cm-danger` → `var(--color-status-cancelled)` (hover `…-dark`)
  - `cm-warning` → `var(--color-status-in-progress)` (hover `#b45309`)
  - `cm-info` → `var(--color-focus-ring)` (hover `var(--color-chart-blue-dark)`)
- Type also swaps the **icon** (warning triangle / info circle) and its tinted container
  (`bg-red-100` / `bg-amber-100` / `bg-blue-100`).
- Focus ring: `.cm-btn:focus-visible { outline: 2px solid var(--color-focus-ring); }`.

---

## 4. Accessibility contract

- Root `role="dialog"`, `aria-modal="true"`, `aria-labelledby="modal-title"`.
- On open, focus moves to the **Cancel** button (safe default — prevents accidental confirm on
  Enter).
- **Escape closes.** **Tab is trapped** between the dialog's focusable buttons (the keydown handler
  filters to visible buttons and wraps first↔last).
- Body scroll is locked (`document.body.style.overflow = 'hidden'`) while open.

---

## 5. Required tokens (port these)

```css
--color-border;
--color-surface;
--color-ink;  --color-ink-muted;
--color-focus-ring;
--color-status-cancelled;  --color-status-cancelled-dark;
--color-status-in-progress;
--color-chart-blue-dark;
--ease-out-expo;
```

Also requires the **`ui_messages` layer**: the Jinja `msg('modal.confirm.*')` calls at render time
and the JS `MSG('modal.delete.*')` calls at click time. In a project without `ui_messages`, replace
`msg()`/`MSG()` with literal strings.

---

## 6. Fresh-project integration

1. Copy `templates/components/confirm_modal.html`.
2. Include it **once**, near the end of `base.html` `<body>` (so it overlays everything):
   ```jinja2
   {% include 'components/confirm_modal.html' %}
   ```
3. Port the tokens in §5 into `input.css :root`.
4. Provide `ui_messages` **or** replace the `msg()`/`MSG()` calls with literals
   (`modal.confirm.title`, `modal.confirm.message`, `modal.confirm.cancel_btn`,
   `modal.confirm.confirm_btn`, `modal.delete.title`, `modal.delete.message`,
   `modal.delete.confirm_btn`).
5. Replace every native `confirm()` in the app with `showConfirmModal`/`confirmDelete`.
6. The `<style>` block ships **inside** the component — do **not** relocate it to `input.css`
   (it must work without a rebuild). Verify by grepping that `#confirm-modal .cm-btn` rules exist
   in the rendered HTML.

---

## 7. Gotchas

- **Singleton.** Include it once. Two copies = duplicated IDs and the global functions act on the
  first match only.
- **`submitBtn.onclick` is rebound on every open** — intended (it captures the current
  form/callback). Don't add a second listener expecting it to persist.
- **Inline `<style>` is load-bearing.** If a "refactor" moves it into `input.css`, the modal will
  render unstyled on any deploy that didn't rebuild CSS. Keep it inline.
- The panel radius is **3px** (slightly softer than the 2px controls) — intentional for elevated
  overlay UI; don't "fix" it to 2px.
