---
name: project_action_icons_right_align_gotcha
description: "Right-aligning .action-icons inside a refined-table <td> needs width:100% on the flex container, not just justify-content:flex-end"
metadata: 
  node_type: memory
  type: project
  originSessionId: 9772a7a2-db24-44e6-866f-a3b33bf6b2c8
---

Right-aligning the `.action-icons` icon-button group inside a `.refined-table` `<td>` (employees list, absences/management) needs TWO things, and the SECOND was the real culprit the user caught after I missed it twice:

1. `.action-icons { display:flex; width:100%; justify-content:flex-end; }` — a block flex container in a `<td>` can shrink-to-fit and sit left with no internal free space for justify-end; `width:100%` makes it fill the cell. (text-align:right on the cell does nothing to a block child.)
2. **Order any hover-reveal / role-gated button (`.danger-reveal`, opacity:0 on load — NOT display:none) FIRST in the markup.** Such a button still occupies its flex slot while invisible. Ordered LAST, that invisible slot lands at the right edge and pushes the always-visible buttons ~2rem inboard → looks left-aligned even though the group is right-aligned. Placing it first puts the empty slot on the LEFT so visible actions sit flush right.

**Symptom:** superuser sees a gap between the right column edge and the visible icon-buttons; non-superuser (no hover button) looks fine. That asymmetry = trailing invisible button, not a flex/width problem.

When splitting a combined `{% if superuser %}…{% elif %}—placeholder{% endif %}` to move the hover button out, re-guard the `—` placeholder with `and current_user.role != 'superuser'` or the superuser row shows a stray dash.

Burned 3 deploys (260623) before the user pointed at the invisible-trailing-button cause. Lesson: when a right-align fix "doesn't take" but the CSS is provably live, check for invisible-but-slot-occupying elements (opacity:0 hover reveals) before re-theorizing about flex/table layout.

Related: [[project_design_system_state.md]] (.stack-cards), [[feedback_no_browser_verification]] (couldn't see the gap — diagnosed from CSS reasoning, which is exactly why I missed the real cause and the user had to spot it).
