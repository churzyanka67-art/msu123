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
