# Mini App redesign implementation plan

> **For agentic workers:** Use superpowers:executing-plans for inline execution, with tests before behavior changes.

**Goal:** Three real screens, a white/lime ring introduction and authenticated personal schedules from MyFGU.
**Architecture:** Keep aiohttp and vanilla browser code. A separate CDO adapter owns per-user memory-only HTTP sessions; the existing Telegram signature authenticates all local API routes. Frontend tabs preserve group and personal date state independently.
**Tech Stack:** Python 3.12, aiohttp, httpx, HTML/CSS/JavaScript, unittest, Playwright.
**Spec:** ../specs/2026-11-14-miniapp-redesign-design.md (approved by user “давай”).

## Global Constraints

- Existing gray/black/white/lime palette; ring animation approximately 1.3 seconds, once per opening, reduced-motion support.
- Fullscreen and Telegram safe insets remain.
- No stored passwords, no upstream token in browser, separate sessions bound to verified Telegram ID.
- No personal-to-group silent fallback; real-account validation remains explicit.
- Preserve pair numbering and automatic next day.

## Review Focus

- Login/logout races and concurrent users must not share sessions or restore a logged-out account.
- Unsupported or malformed upstream responses must report an error, never an empty successful day.
- Expired login and source timeouts must remain distinct.
- Tabs and navigation must not make hidden fields or stale buttons act on another screen.
- Ring intro must finish even when SDK or schedule data fails.

### Task 1: CDO adapter and protected routes

**Files:** create app/miniapp/cdo.py, tests/test_cdo.py; modify app/miniapp/server.py, tests/test_miniapp.py.
**Interfaces:** CdoSessions.login(user_id, username, password), status(user_id), schedule(user_id, date), logout(user_id), close(). Routes /api/cdo/session GET/POST/DELETE and /api/cdo/schedule GET.

- [ ] Write tests with httpx MockTransport for observed login, /students/me, /timetable/student contracts, isolation, expiry, logout, invalid data, network errors and credential secrecy; run RED.
- [ ] Implement bounded memory-only sessions and source normalization to existing Lesson fields; derive student ID exclusively from the signed-in upstream profile.
- [ ] Protect routes with existing Telegram signature; add limits to login attempts and payload lengths, validate dates, close clients at app cleanup.
- [ ] Run adapter and whole Python suites GREEN.

### Task 2: Screens, ring intro and personal UI

**Files:** modify static/index.html, style.css, app.js; update tools/check_miniapp.cjs and preview server.
**Interfaces:** keep existing group API; consume Task 1 routes without saving username/password/upstream tokens to browser storage.

- [ ] Extend browser QA for actual hidden/shown screens, group selection/back navigation, personal login/error/logout, preserved dates, intro termination and reduced motion; observe RED.
- [ ] Add separate day, selection, personal and profile views with three-tab navigation. Retain current timetable renderer and implement a separate personal renderer using normalized source lessons.
- [ ] Animate the two rings into header branding; initialize intro independently of requests and handle unavailable Telegram SDK.
- [ ] Run QA at 320, 390 and desktop widths; inspect screenshots and animation frames; run Python suite.

### Task 3: Review and delivery

**Files:** update README.md and this progress record.
- [ ] Document memory-only CDO sessions, restart behavior, observed upstream contracts and real-account verification boundary.
- [ ] Run whole suite, lint, compile and browser checks; review code independently and fix material findings.
- [ ] Deliver local changes with verified evidence; do not claim Bothost deployment or real-account success without checking them.

## Execution record

Plan approved scope comes from user approval of the plain-language design. Implement inline without an additional approval loop, following the user's instruction to proceed. This directory is a source copy without Git metadata; edits stay here and no unrelated directory is changed.

Task 1 complete: adapter and authenticated routes, separate memory-only sessions, source normalization, bounded attempts and cleanup. Initial tests failed for missing adapter/routes, then passed.

Task 2 complete: separate screens, persistent bottom navigation, draft group selection committed only on Show, independent date state, ring intro and CDO form. Browser tests first failed on missing screens, then passed at 320/390/1100 pixels. SDK unavailable and reduced motion are covered.

Task 3 verification complete: 30 unittest tests pass; ruff and compileall pass; browser checks pass. Real credentials were not used to validate a personal timetable. Deployment is not declared complete.

Independent review found three important issues, all corrected: cancelled group drafts altered active requests; stale CDO status could reset a newer login; malformed source dates could be treated as empty days. Each was reproduced by a failing regression test before its fix. Added a further failing/passing browser regression for retrying schedule loading after successful login without retaining the password.

Ruling: keep CDO sessions in memory, with a one-hour local lifetime, rather than storing credentials or introducing a database encryption key. A restart requires sign-in again; upstream expiry can require it sooner.

Ruling: use the source copy already containing the Mini App, because no local Git checkout exists. GitHub publication updates only an explicit allowlist against the verified remote parent and excludes local secrets/runtime/preview data.
