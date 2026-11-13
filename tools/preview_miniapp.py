"""Isolated browser QA server: saved fixtures, fake bot token, no polling."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from aiohttp import web
from app.miniapp.server import create_app

from app.models.schedule import DaySchedule
from app.services.parser import parse_options, parse_schedule

FIXTURES = Path(__file__).resolve().parents[1] / "tests/fixtures"


def main():
    service = AsyncMock()
    service.get_faculties.return_value = parse_options((FIXTURES / "faculties.html").read_text(), "facultyid")
    service.get_courses.return_value = parse_options((FIXTURES / "courses.html").read_text(), "course")
    service.get_groups.return_value = parse_options((FIXTURES / "groups.html").read_text(), "groupid")
    saved = (FIXTURES / "day.html").read_text()
    today = datetime(2026, 9, 9, 8, tzinfo=ZoneInfo("Europe/Moscow"))

    async def schedule(group, day, *args, **kwargs):
        if day == today.date():
            return parse_schedule(saved, day)
        return DaySchedule(day)

    service.get_schedule.side_effect = schedule
    web.run_app(
        create_app(service, "123456:MINIAPP_BROWSER_TEST", clock=lambda: today),
        host="127.0.0.1",
        port=8081,
        access_log=None,
    )


if __name__ == "__main__":
    main()
