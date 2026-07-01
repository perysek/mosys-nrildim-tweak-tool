---
name: feedback-regex-backreference-trap
description: Python re.sub replacement strings emitted literal \x01 bytes into templates — always node --check inline JS after scripted edits
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 2ae33770-25f2-4d44-bd18-15703c5e1561
---

During the 260610 UI plan, a Python `re.subn` replacement string containing `\1` adjacent to other text emitted literal `\x01` control bytes into two templates, silently killing entire inline `<script>` blocks (functions hoisted from OTHER files masked the breakage — pages looked alive).

**Why:** Scripted multi-file edits can corrupt files in ways that don't throw and don't show in console errors.

**How to apply:** After any scripted (regex/sed/python) edit of templates: (1) grep for control chars (`[\x00-\x08]`), (2) run `node --check` on every extracted inline script block, (3) verify behavior via real browser click on prod/dev, not just "no console errors". Prefer `re.sub` with a replacement FUNCTION (lambda m: ...) over string backreferences.
