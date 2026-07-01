---
name: feedback-no-browser-verification
description: "Never launch a browser (gstack /browse, Playwright, screenshots) to verify UI results — the user checks the running app themselves"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 49b5e80f-70e9-4754-9935-4a243a1db60e
---

The user does NOT want Claude to spin up a browser to verify front-end changes — no gstack `/browse`, no Playwright, no screenshot-and-read loop to "confirm it looks right." They check the live app on their own machine/phone instead. Stated directly: "I will check myself. never run browser to check results."

**Why:** They have the running app in front of them and prefer to eyeball it themselves; the browser-driving round-trips are wasted effort from their point of view.

**How to apply:** Verify logic with non-browser means — `node --check` for JS syntax, a quick `node -e` to test a pure function's output, Jinja `env.parse()` for template syntax, Grep for dangling references. Then ship (commit+push+deploy per [[feedback-autodeploy]]) and let the user do the visual/interaction check. Do not open a browser, render fixtures, or take screenshots to self-confirm UI behavior unless the user explicitly asks for it. This sits alongside [[feedback-trust-internal-tooling]] — the user wants execution, not Claude-side validation theater.
