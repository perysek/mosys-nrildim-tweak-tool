---
name: feedback-deploy-then-user-verifies
description: "Don't use Playwright to self-verify UI changes — commit/push/deploy without asking, then have the user check visually"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: df5a41ca-d7b7-4b07-9bb9-3c99578d9b08
---

When a GUI task is finished, do NOT use Playwright (or other browser automation) to take screenshots and self-assess visual success. Instead: commit the change, push to `origin/main`, and deploy to the company server (see [[server-deployment]]) without asking for confirmation first — then tell the user it's deployed and ask them to manually check the updated UI themselves.

**Why:** the user would rather review the real result once on the live server than have the assistant burn time/tokens taking and inspecting screenshots, and they're fine with repo+server updates for this project happening without a pre-action confirmation gate.

**How to apply:** for this project (staamp-actions-management) specifically — once a UI/feature change is implemented and looks correct by code-reading (and a local dev-server smoke check if needed to confirm no crash), go straight to: `git add` the relevant files → commit → push → deploy via the `windows-server-deploy` skill's git-pull procedure ([[server-deployment]]) → report done and ask the user to verify visually on `http://10.52.10.101:8093/`. Skip Playwright screenshot review as the completion gate. This overrides the general "ask before push/deploy" caution from the base instructions for this specific repo.
