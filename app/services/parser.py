"""Pure parser for the site's HTML (no network or Telegram dependencies)."""

import re
from datetime import date, datetime

from bs4 import BeautifulSoup

from app.models.schedule import DaySchedule, Lesson, Option


class SourceError(Exception):
    """Unavailable source, expired selection, or unrecognised source format."""


def parse_options(html: str, field: str) -> list[Option]:
    select = BeautifulSoup(html, "html.parser").find("select", id=f"timetableform-{field}")
    if select is None:
        raise SourceError(f"Missing select: {field}")
    return [
        Option(str(o["value"]), o.get_text(" ", strip=True))
        for o in select.find_all("option")
        if o.get("value")
    ]


def parse_schedule(html: str, selected: date) -> DaySchedule:
    table = BeautifulSoup(html, "html.parser").find("table", id="timeTable")
    if table is None:
        raise SourceError("Missing schedule table")
    result = DaySchedule(selected)
    dates = []
    found = False
    for row in table.find_all("tr"):
        headers = row.select("th.headdate")
        if headers:
            try:
                dates = [datetime.strptime(h.get_text(strip=True), "%d.%m.%Y").date() for h in headers]  # noqa: DTZ007
            except ValueError as exc:
                raise SourceError("Invalid date header") from exc
            continue
        if selected not in dates:
            continue
        cells = row.find_all("td", recursive=False)
        if len(cells) != len(dates):
            raise SourceError("Unexpected column count")
        cell = cells[dates.index(selected)]
        if "closed" in cell.get("class", []):
            raise SourceError("Date outside returned range")
        found = True
        start, end = row.select_one(".start"), row.select_one(".end")
        if start is None or end is None:
            raise SourceError("Missing lesson time")
        cards = cell.select('[data-toggle="popover"][data-content]')
        if not cards and cell.get_text(strip=True).replace("\xa0", ""):
            raise SourceError("Unrecognised lesson markup")
        for card in cards:
            content = BeautifulSoup(card["data-content"], "html.parser")
            for br in content.find_all("br"):
                br.replace_with("\n")
            lines = [line.strip() for line in content.get_text().splitlines() if line.strip()]
            lines = [
                line for line in lines if not re.match(r"^(Добавлено|Изменено|Обновлено|Удалено):", line)
            ]
            if not lines:
                raise SourceError("Empty lesson card")
            begin, finish = start.get_text(strip=True), end.get_text(strip=True)
            custom = re.fullmatch(r"(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})", lines[0])
            if custom:
                begin, finish = (x.zfill(5) for x in custom.groups())
                lines.pop(0)
            if not lines:
                raise SourceError("Missing subject")
            subject = lines.pop(0)
            kind = re.search(r"\[([^]]+)\]$", subject)
            if kind:
                subject = subject[: kind.start()].strip()
            room = next((line for line in lines if re.match(r"^ауд\.", line, re.IGNORECASE)), None)
            if room:
                lines.remove(room)
            # Source puts the group/subgroup line before the full teacher name.
            groups = lines.pop(0) if lines else None
            teacher = ", ".join(lines) or None
            result.lessons.append(
                Lesson(
                    begin,
                    finish,
                    subject,
                    teacher,
                    re.sub(r"^ауд\.\s*", "", room, flags=re.IGNORECASE) if room else None,
                    kind[1] if kind else None,
                    groups,
                )
            )
    if not found:
        raise SourceError("Requested date missing from table")
    result.lessons.sort(key=lambda lesson: lesson.start_time)
    return result
