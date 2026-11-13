# Mini App redesign verification — 2026-11-14

Implemented separate Schedule, Personal and Profile screens, a separate group selector, white/lime ring intro, existing fullscreen behavior and safe areas. Personal timetable adapter follows the observed MyFGU web protocol. The student's ID comes from the signed-in upstream account, not from client parameters.

Verified locally:

- `python -m unittest discover -s tests -q`: 30 tests pass.
- `python -m ruff check app tests tools`: all checks pass.
- `python -m compileall -q app`: exit 0.
- `node tools/check_miniapp.cjs`: browser flows pass at 320, 390, 1100 pixels; unavailable Telegram SDK does not block the intro.
- Browser flows include group selection/back without committing a draft, independent personal/group dates, bad password, cleared password field, personal loading retry after successful login, stale status arriving after login, disconnect and selection restored after reload.
- Adapter tests cover separate cookies/tokens for users, login/logout ordering, local and upstream expiry, invalid response/date handling, limits and safe error messages.
- Screenshots in local `preview/` inspected at phone width. They show controlled fixtures, not real personal data.

Boundaries:

- No real-account timetable comparison was performed. A user must sign in inside the app and compare their own classes.
- No claim that Bothost has deployed this commit or that the current Telegram menu reaches it.
- MyFGU's observed web protocol is not a documented third-party API and may change.
- Sessions remain only in server memory for up to one hour, so a server restart requires sign-in again. Passwords are not persisted.

## Automatic CDO group selection follow-up

The observed `/students/me` response is used by MyFGU's web client for `group.id` and `group.course`. Live public `GET /api/web/groups` confirmed the catalogue schema: `id`, `name`, `education_level_id`, `course`; for example `204гму` is ID `1320`, education level `5`, course `2` on the inspection date.

Login/status now includes a catalogue-validated `group_selection`. The browser applies it after login and session restoration, hydrates all three group selectors, loads that group's day and remembers it. Auth generation guards prevent an obsolete account response from overriding a later login/logout. Missing catalogue data does not cause guessing by name or prevent the personal student timetable.

Follow-up verification: 32 Python tests pass; browser checks at 320/390/1100 pixels pass including replacement of an old manual group selection. Separate students in one group retain different `studentId` timetable requests and subgroup responses in controlled upstream tests. Real account subgroup membership is still not independently inspected.

Hosting observation before publishing this follow-up: `/healthz` returned 200 `ok`; the public page already contained the redesigned tabs and ring intro; Telegram menu URL pointed to the Bothost domain. This confirms the earlier redesign was served, not that a phone's already-open Mini App had reloaded it.

## Profile group and personal-screen independence

Reproduced a browser regression: signing in as a student from 102гму, then manually selecting 103гму in the public timetable, overwrote the group shown in Profile. Removed the profile write from public timetable loading; the read-only profile group now updates only from the CDO session response, with an explicit sign-in state after logout. Clicking it no longer opens manual selection.

Browser regression coverage now includes manual group changes while signed in, an unchanged CDO profile group, unchanged personal group/date/subject, and clearing the profile after logout. Personal rendering continues to consume only `/api/cdo/schedule`. CSS uses `touch-action: manipulation` on the root and controls to suppress double-tap zoom while retaining scrolling/pinch zoom (W3C Pointer Events, section 8.3). Physical iPhone gesture behavior has not been independently exercised.
