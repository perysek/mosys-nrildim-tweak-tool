# Component: Sidebar Navigation ★ (app-shell rail + mobile drawer)

**Source:** `templates/components/sidebar.html`
**Macros:** `templates/macros/sidebar_macros.html` (`sidebar_link`, `sidebar_section_start`, `sidebar_section_end`)
**Tokens + CSS:** `--sidebar-*` block and `.sidebar-link*` rules in `static/css/input.css`
**Type:** Markup + inline responsive `<style>` + inline `<script>` (accordion, drawer, focus trap).
**This is the most integration-heavy component — read all of it before porting.**

> **⚠️ The old `GUI-GOLDEN-BOOK.md` is stale on this component.** It documents a **dark slate**
> sidebar (`--sidebar-bg: #0f172a`, blue-400 active). The **live** sidebar is a **warm light
> theme** (`#dedad3`, gold `#c9a227` active). This document reflects the current `input.css`.

---

## 1. Purpose & anatomy

The fixed left navigation rail of the authenticated shell. Four stacked regions:

```
┌──────────────────────────┐
│ Logo + tagline           │  ← brand block, bottom-bordered
├──────────────────────────┤
│ <nav> accordion sections │  ← Finanse / Salon / Zarządzanie / Korekta / System
│   single-open accordion  │     each = a button header + collapsible link list
│   active link = gold pill │
├──────────────────────────┤
│ User info (avatar+role)  │  ← gold gradient avatar, full name, role label
├──────────────────────────┤
│ Logout (red on hover)    │
└──────────────────────────┘
```

- **Desktop (≥ lg / 1024px):** always-on `w-[17rem]` column (`hidden lg:flex`).
- **Mobile (< lg):** slide-in **drawer** over a dimmed backdrop, toggled by `#sidebar-toggle`
  (lives in the page header), with a **focus trap** and Escape-to-close.

Permission gating: every section/link is wrapped in `{% if user_permissions.* %}` (and role flags
`is_supervisor`, `has_linked_employee`) so users only see what they may use.

---

## 2. Token contract — the warm-light theme (port verbatim)

Defined in `input.css :root`. **These are the current values** (a shade darker than the app's warm
body surface so the rail reads as a distinct panel):

```css
/* Sidebar — warm light theme (matches app surface, a shade darker) */
--sidebar-bg:            #dedad3;   /* rail background */
--sidebar-bg-deep:       #d2cec6;   /* user-info footer (slightly deeper) */
--sidebar-text:          #525252;   /* default link text  (= --color-ink-muted) */
--sidebar-text-hover:    #1a1a1a;   /* hover link text     (= --color-ink) */
--sidebar-text-active:   #1a1a1a;   /* active link text (ink; gold reserved for pill/icon) */
--sidebar-heading:       #595959;   /* section header label — darkened for WCAG AA (~5:1) */
--sidebar-border:        #ccc7be;   /* region dividers */
--sidebar-hover-bg:      #e6e2db;   /* link hover background */
--sidebar-active-bg:     var(--color-accent-muted);   /* rgba(201,162,39,.12) gold tint */
--sidebar-active-border: var(--color-accent);         /* #c9a227 gold pill + active icon */
```

> **Accessibility note baked into the source:** the design originally used `#8a8a8a` for the section
> heading (~2.5:1 on `#dedad3` — **fails** WCAG AA). It was darkened to `#595959` (~5:1). Keep that
> value; visual hierarchy vs. links is preserved via uppercase + size, not via a lighter color.

---

## 3. The `@layer components` CSS (port verbatim)

```css
.sidebar-link--default        { color: var(--sidebar-text); }
.sidebar-link--default:hover  { background: var(--sidebar-hover-bg); color: var(--sidebar-text-hover); }

.sidebar-link--active {
    position: relative;
    background: var(--sidebar-active-bg);
    color: var(--sidebar-text-active);
    animation: sidebar-link-enter 0.35s var(--ease-out-expo) both;   /* non-VT fallback */
}
/* Gold left-edge pill indicator */
.sidebar-link--active::before {
    content: ''; position: absolute; left: 0; top: 20%; bottom: 20%;
    width: 3px; border-radius: 0 3px 3px 0;
    background: var(--sidebar-active-border);
    animation: pill-enter 0.4s var(--ease-out-expo) both;
}
.sidebar-link--active svg { color: var(--sidebar-active-border); }   /* active icon goes gold */
```

Plus `@keyframes sidebar-link-enter` and `pill-enter`, the View-Transitions block (§6), and a
`prefers-reduced-motion` guard that disables both animations.

---

## 4. Markup API (the macros)

```jinja2
{% from 'macros/sidebar_macros.html' import
   sidebar_link, sidebar_section_start, sidebar_section_end %}

{{ sidebar_section_start('finanse', 'Finanse', finanse_active) }}
    {{ sidebar_link(url_for('main.invoices_list'), 'Lista faktur', '<svg path d>',
                    request.endpoint == 'main.invoices_list') }}
    {{ sidebar_link(url_for('main.dashboard'), 'Koszty', '<svg path d>',
                    request.endpoint == 'main.dashboard', extra_class='nav-mobile-hide') }}
{{ sidebar_section_end() }}
```

| Macro | Params | Notes |
|---|---|---|
| `sidebar_section_start(id, title, is_active, extra_class='')` | `id` = unique slug; `is_active` pre-expands the section; `extra_class` e.g. `nav-mobile-hide` | Emits `.sidebar-section[data-active]` + a `.sidebar-section-header` button (chevron, `aria-expanded`, `aria-controls`) + opens `.sidebar-section-items[role=region]` |
| `sidebar_link(url, label, icon_path, is_active=false, extra_class='')` | `icon_path` = the **raw `d` attribute** of a 24×24 stroke SVG; `is_active` adds the pill + `aria-current="page"` | Min 44px tap target on mobile (`min-h-[44px] lg:min-h-0`) |
| `sidebar_section_end()` | — | Closes the items region + section |

**Active-state computation** is done once at the top of `sidebar.html` with `{% set …_active = request.endpoint in [...] %}` per section, then each link compares `request.endpoint`. A link whose
icon needs **two SVG paths** (e.g. Settings) is written inline instead of via the macro (the macro
takes a single path string).

> **Icon note:** the sidebar uses **24×24 `viewBox="0 0 24 24"` stroke icons** (Heroicons-style,
> `stroke="currentColor"`), passed as a raw `d` string — this is **separate** from the
> [`icons.md`](icons.md) `0 -960 960 960` filled-glyph system. Don't mix the two coordinate spaces.

---

## 5. Behaviour — the inline `<script>` (accordion + drawer)

All logic is vanilla JS in `sidebar.html`, bound on `DOMContentLoaded`:

**Accordion (single-open):**
- On load, sections with `data-active="true"` **expand**, others **collapse** (`max-height` set to
  `scrollHeight` px vs `0`).
- Clicking a header toggles it; opening one **collapses all others** (single-open).
- The chevron rotates 180° via `.sidebar-chevron`; `aria-expanded` is kept in sync.
- **Resize recompute:** because `max-height` is pinned to a px snapshot, a viewport/font reflow can
  clip an open section — a debounced (120ms) `resize` handler re-measures expanded sections.

**Mobile drawer:**
- `#sidebar-toggle` (in the page header, `lg:hidden`) opens/closes the drawer; `#sidebar-overlay`
  is the dim backdrop (click to close).
- `openMobileSidebar()` reveals the rail (`fixed inset-y-0 left-0 z-40`), locks body scroll
  (`scroll-lock`), focuses the first link, and installs a **Tab focus trap** (`trapTab`) so keyboard
  focus cannot escape to the page behind the overlay.
- `closeMobileSidebar()` only runs below 1024px, restores scroll, removes the trap, and **returns
  focus to the toggle**.
- **Escape** closes the drawer and calls `e.stopImmediatePropagation()` — deliberately, so the
  global `keyboard-shortcuts.js` Esc handler doesn't *also* fire and blur the toggle we just
  refocused. (One Esc = one layer.)

---

## 6. View Transitions (progressive enhancement)

```css
@view-transition { navigation: auto; }                 /* enable cross-document VT for MPA nav */
.sidebar-link--active { view-transition-name: sidebar-active-link; }
::view-transition-new(sidebar-active-link) { animation: sidebar-vt-in  0.3s var(--ease-out-expo) both; }
::view-transition-old(sidebar-active-link) { animation: sidebar-vt-out 0.2s ease-in both; }
```

All active links share **one** transition name, so on navigation the browser **cross-fades the gold
highlight** from the old page's active link to the new one — the highlight appears to morph between
pages. Browsers without the View Transitions API fall back to the `sidebar-link-enter` keyframe.
Both are disabled under `prefers-reduced-motion`.

---

## 7. Responsive trim system — `nav-mobile-hide`

The mobile drawer shows a **deliberately reduced** link set (phone-relevant only). Mechanism:

- Tag any link or section with `extra_class='nav-mobile-hide'`.
- The component's inline `<style>` (a `@media (max-width: 1023px)` block) then:
  - `.nav-mobile-hide { display: none !important; }` — drops trimmed links on phones (they reappear
    on the always-on desktop rail).
  - Hides **section headers** and force-opens **all section bodies** (`max-height:none !important`)
    so the drawer reads as **one flat list**, not an accordion.
  - Tightens link height to ~40px and removes inter-section margins to fight vertical overflow.

> `!important` is required here specifically because the JS accordion pins `max-height` as an
> **inline style**, and only `!important` beats an inline declaration.

---

## 8. User footer & logout

- **Avatar:** `w-10 h-10 rounded-full`, gold gradient `linear-gradient(135deg, var(--color-accent), #a07d1a)`, showing `current_user.full_name[:2].upper()`.
- **Role label:** a Polish display map (`superuser→Superadmin`, `admin→Administrator`, `accountant→Księgowa`, `receptionist→Recepcjonistka`, `stylist→Stylistka`), fallback `role|capitalize`.
- **Logout** turns red on hover via inline `onmouseenter/onmouseleave` (sets `color: var(--color-error)` + `#fef2f2` bg) — intentionally **not** Tailwind hover, so it works without those exact utility classes being in the build.

---

## 9. Fresh-project integration (the full ritual)

1. **Copy three things:** `templates/components/sidebar.html`,
   `templates/macros/sidebar_macros.html`, and the `#sidebar-overlay` + toggle wiring expectation
   (the page header must contain a `#sidebar-toggle` button, `lg:hidden`).
2. **Port the `--sidebar-*` token block** (§2) into `input.css :root` — including the WCAG-driven
   `#595959` heading. These depend on `--color-accent` / `--color-accent-muted` / `--ease-out-expo`,
   so port those too.
3. **Port the `.sidebar-link*` `@layer components` rules + keyframes + View-Transitions block +
   reduced-motion guard** (§3, §6) into `input.css`.
4. **Provide the shell context** the markup expects: `current_user`, `user_permissions.*`,
   `is_supervisor`, `has_linked_employee`, `logo_data_uri`, and the per-section `request.endpoint`
   lists (rewrite these to *your* route names).
5. **Re-author the nav sections** for your app's routes using the macros; pass the right
   `nav-mobile-hide` trims for the phone link set.
6. **Add `scroll-lock`** (body overflow-hidden) utility/class if not present — the drawer relies on it.
7. `npm run build:css`, then verify with a Jinja parse + grep that `sidebar_link`/`sidebar_section_*`
   resolve and the `--sidebar-*` vars exist. Do **not** browser-spot-check blindly.

---

## 10. Gotchas (sidebar-specific, learned the hard way)

- **Stale-spec trap:** if you copy colors from the old GUI-GOLDEN-BOOK you'll build the *dark* theme.
  Use the `--sidebar-*` values in §2 (live `input.css`).
- **`max-height` accordion clips on reflow.** The px snapshot can under-measure after a font/viewport
  change; the debounced resize re-measure (§5) is load-bearing — keep it.
- **Escape double-handling.** Without `stopImmediatePropagation()`, the global shortcut handler also
  fires on Esc and steals the focus return. Preserve that call.
- **`!important` in the mobile block is required**, not lazy — it beats the JS-applied inline
  `max-height`. Don't "clean it up" to a plain rule.
- **Two icon systems.** Sidebar = 24×24 stroke `d` strings; rest of app = `icons.html` filled glyphs
  (`0 -960 960 960`). Passing one into the other renders off-canvas.
- **Heading contrast.** Don't lighten `--sidebar-heading` back toward `#8a8a8a` — it fails AA on the
  warm bg.
- **Section `id`s must be unique** (used to build `aria-controls`/`id="sidebar-<id>-items"`); a dup
  breaks the accordion's expand/collapse targeting.
- **Active highlight is per-`request.endpoint`.** If a route isn't in the section's `…_active` list
  and the link's comparison, the pill won't show on that page — add new endpoints to both.
