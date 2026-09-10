"""Read-only live smoke check; run with python -m app.smoke, no bot token needed."""

import asyncio
import json
import sys

import httpx

from app.controller import Controller
from app.formatting import today_moscow
from app.services.msu_schedule import MsuScheduleService
from app.services.parser import SourceError


def action_key(screen, kind, predicate=lambda value: True):
    for key, (name, value) in screen.actions.items():
        if name == kind and predicate(value):
            return key
    raise SourceError(f"Smoke check: expected {kind} action absent; screen: {screen.text}")


async def check_flow(service, today=today_moscow):
    controller = Controller(service, today=today)
    screen = await controller.start()
    screen = await controller.act(screen, action_key(screen, "faculty"))
    screen = await controller.act(screen, action_key(screen, "course"))
    screen = await controller.act(screen, action_key(screen, "group"))
    if screen.selection.view != "schedule":
        raise SourceError("Smoke check: schedule not reached")
    report = {"group": screen.selection.group.name, "days": [screen.selection.day.isoformat()]}
    for step in (1, 1, -1):
        before = screen.selection.day
        screen = await controller.act(
            screen,
            action_key(screen, "date", lambda value, before=before, step=step: (value - before).days == step),
        )
        if (screen.selection.day - before).days != step:
            raise SourceError("Smoke check: date navigation failed")
        report["days"].append(screen.selection.day.isoformat())
    screen = await controller.act(screen, action_key(screen, "reset"))
    report["reset"] = screen.selection.view == "faculties" and any(
        a[0] == "faculty" for a in screen.actions.values()
    )
    if not report["reset"]:
        raise SourceError("Smoke check: reset failed")
    return report


async def main():
    async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=10), follow_redirects=True) as client:
        report = await check_flow(MsuScheduleService(client, cache_enabled=False))
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except SourceError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
