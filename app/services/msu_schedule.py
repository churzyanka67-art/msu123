"""Async access to the public Yii form; a lock isolates its session state."""

import asyncio
from datetime import date
from time import monotonic

import httpx
from bs4 import BeautifulSoup

from app.services.parser import SourceError, parse_options, parse_schedule

URL = "https://cacs.spa.msu.ru/time-table/group?type=0"


class MsuScheduleService:
    def __init__(self, client: httpx.AsyncClient, *, cache_enabled=True, catalog_ttl=1200, schedule_ttl=180):
        self.client = client
        self.cache_enabled = cache_enabled
        self.catalog_ttl = catalog_ttl
        self.schedule_ttl = schedule_ttl
        self._cache = {}
        self._lock = asyncio.Lock()

    async def _load(self, key, fields, parser, ttl, refresh=False):
        async with self._lock:
            now = monotonic()
            # Bound memory to live entries and at most 1024 cached responses.
            self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
            if self.cache_enabled and not refresh and key in self._cache:
                return self._cache[key][1]
            try:
                page = await self.client.get(URL)
                page.raise_for_status()
                if fields:
                    token = BeautifulSoup(page.text, "html.parser").find(
                        "input", attrs={"name": "_csrf-frontend"}
                    )
                    if token is None or not token.get("value"):
                        raise SourceError("Missing CSRF token")
                    data = {"_csrf-frontend": token["value"]}
                    data.update({f"TimeTableForm[{k}]": str(v) for k, v in fields.items()})
                    page = await self.client.post(URL, data=data)
                    page.raise_for_status()
                result = parser(page.text)
            except httpx.HTTPError as exc:
                raise SourceError(f"Source HTTP failure: {type(exc).__name__}") from exc
            if self.cache_enabled:
                if len(self._cache) >= 1024:
                    self._cache.pop(next(iter(self._cache)))
                self._cache[key] = (monotonic() + ttl, result)
            return result

    async def get_faculties(self, *, refresh=False):
        return await self._load(
            ("faculties",), {}, lambda h: parse_options(h, "facultyid"), self.catalog_ttl, refresh
        )

    async def get_courses(self, faculty_id, *, refresh=False):
        return await self._load(
            ("courses", faculty_id),
            {"facultyId": faculty_id, "course": "", "groupId": ""},
            lambda h: parse_options(h, "course"),
            self.catalog_ttl,
            refresh,
        )

    async def get_groups(self, faculty_id, course_id, *, refresh=False):
        return await self._load(
            ("groups", faculty_id, course_id),
            {"facultyId": faculty_id, "course": course_id, "groupId": ""},
            lambda h: parse_options(h, "groupid"),
            self.catalog_ttl,
            refresh,
        )

    async def get_schedule(
        self, group_id: str, date: date, faculty_id: str, course_id: str, *, refresh=False
    ):
        def parse(html):
            soup = BeautifulSoup(html, "html.parser")
            # Do not display another group's data if the server rejected our selection.
            for field, wanted in [("facultyid", faculty_id), ("course", course_id), ("groupid", group_id)]:
                selected = soup.select_one(f"#timetableform-{field} option[selected]")
                if selected is None or selected.get("value") != str(wanted):
                    raise SourceError("Source rejected selection")
            return parse_schedule(html, date)

        return await self._load(
            ("schedule", faculty_id, course_id, group_id, date),
            {
                "facultyId": faculty_id,
                "course": course_id,
                "groupId": group_id,
                "dateStart": date.strftime("%d.%m.%Y"),
                "dateEnd": date.strftime("%d.%m.%Y"),
            },
            parse,
            self.schedule_ttl,
            refresh,
        )
