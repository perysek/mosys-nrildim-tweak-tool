# Component: Undo Toast (soft-delete "Cofnij")

**Source:** `templates/components/undo_toast.html`
**Type:** Self-contained `<script>` exposing one global function. No markup, no macro.
**CSS delivery:** 100% inline (styles set via `element.style.cssText` in JS) — **zero**
CSS/token/build dependency. This component works in any project as-is.

---

## 1. Purpose & when to use

After a **soft delete** (record flagged deleted, restorable), call `showUndoToast()` to show a
bottom-right toast with a **"Cofnij"** (Undo) button that POSTs to a restore endpoint. It is the
forgiving counterpart to the hard-delete [`confirm-modal.md`](confirm-modal.md): confirm modal
*prevents* mistakes up front; undo toast *reverses* them after the fact.

Use undo-toast when deletion is reversible server-side. Use confirm-modal when it is not.

---

## 2. Public API

```javascript
showUndoToast(message, restoreUrl, duration = 8000);
```

| Param | Meaning |
|---|---|
| `message` | Confirmation text shown in the toast (e.g. `'Klient usunięty'`). |
| `restoreUrl` | **POST** URL that restores the record. Must return JSON `{ success: bool, message?, error? }`. |
| `duration` | Visible time in ms before auto-hide. Default `8000`. |

Behaviour:

- Only **one** undo toast at a time — a new call removes the previous (`#undo-toast`).
- Clicking **Cofnij**: `POST restoreUrl` → on `success`, shows the returned `message`, removes the
  Undo button, then **reloads the page** (~2.2 s later) to surface the restored row. On failure it
  shows `error` and re-enables the button.
- Clicking **×** dismisses immediately.
- **Hovering the toast cancels the auto-hide timer** (so users reading it don't lose the chance).
- Fades via `opacity` transition (200 ms).

---

## 3. Server contract

The restore endpoint **must**:

- Accept `POST`.
- Return JSON: `{ "success": true, "message": "Przywrócono klienta" }`
  or `{ "success": false, "error": "Nie można przywrócić" }`.

```python
@bp.route('/api/clients/<int:id>/restore', methods=['POST'])
def restore_client(id):
    ok = clients.restore(id)
    if ok:
        return jsonify(success=True, message='Przywrócono klienta')
    return jsonify(success=False, error='Nie można przywrócić'), 400
```

Typical caller (after a successful soft-delete AJAX call):

```javascript
showUndoToast('Klient usunięty', `/api/clients/${id}/restore`, 8000);
```

---

## 4. Styling (informational — nothing to port)

All styles are inlined in JS. Notable values, in case you want to align them with your tokens:

- White bg, **green left border (4px)** via `var(--pp-success, #10b981)` — note the **fallback**:
  if `--pp-success` is undefined the literal `#10b981` is used, so it renders correctly with no
  tokens at all.
- `border-radius: 0.75rem` (this component predates the 2–3px refined radius and keeps a softer
  pill — see Gotchas).
- "Cofnij" button blue via `var(--pp-blue, #3b82f6)`; hover tint `rgba(59,130,246,0.1)`.
- Fixed `bottom:1.5rem; right:1.5rem; z-index:9999; max-width:400px`.

---

## 5. Fresh-project integration

1. Copy `templates/components/undo_toast.html`.
2. Include it **once** in `base.html` (or only on pages with soft-delete):
   ```jinja2
   {% include 'components/undo_toast.html' %}
   ```
3. Nothing else — no tokens, no `@layer` classes, no build step. The `var(--pp-*, fallback)`
   pattern means it is correct even in a project with no design tokens.
4. Implement a `POST` restore endpoint returning the JSON contract above.

---

## 6. Gotchas

- **Radius mismatch.** It uses `0.75rem`/`0.375rem` radii (legacy soft pill), not the app's 2–3px
  refined radius. If you want it on-system, change the inlined `border-radius` values — but only if
  the project standardizes on the refined radius for toasts.
- **Token names differ** from the rest of the app: it references `--pp-success` / `--pp-blue`
  (with safe fallbacks) rather than `--color-success` / `--color-focus-ring`. If you want it to
  follow the shared palette, either define those `--pp-*` aliases or edit the inlined colors.
- **It reloads the page on undo** — fine for server-rendered list pages, but in an SPA-ish flow
  you'd replace `location.reload()` with a targeted row re-insert.
- Don't stack it with toast `Notifications.*` for the same action; pick one feedback channel.
