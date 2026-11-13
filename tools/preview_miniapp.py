"""Isolated browser QA server: saved fixtures, fake bot token, no polling."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import httpx
from aiohttp import web
from app.miniapp.cdo import CdoSessions
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

    async def cdo_upstream(request):
        if request.url.path.endswith("/login"):
            if json.loads(request.content)["password"] != "valid":
                return httpx.Response(401, json={})
            return httpx.Response(200, json={"token": "PREVIEW_ONLY", "user": {"firstname": "Дени", "lastname": "Студент"}})
        if request.url.path.endswith("/students/me"):
            return httpx.Response(200, json={"student": {"id": 42}, "group": {"name": "204гму"}})
        if request.url.path.endswith("/timetable/student"):
            day = json.loads(request.content)["dateStart"]
            return httpx.Response(200, json=[{"date": day, "lessons": [{"number": 2, "periods": [{
                "timeStart": "11:25", "timeEnd": "12:55", "disciplineFullName": "Моя личная дисциплина",
                "teachersNameFull": "Преподаватель", "classroom": "А 716", "typeStr": "Сем", "groups": "Подгруппа 1",
            }]}]}])
        return httpx.Response(404)

    web.run_app(
        create_app(service, "123456:MINIAPP_BROWSER_TEST", clock=lambda: today,
                   cdo=CdoSessions(transport=httpx.MockTransport(cdo_upstream))),
        host="127.0.0.1",
        port=8081,
        access_log=None,
    )


if __name__ == "__main__":
    main()
