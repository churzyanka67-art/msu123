"""Compact presentation data: two UTF-8 state fields, at most 1024 bytes each."""

import json
import zlib
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo

from app.formatting import DAYS, MONTHS

HTML_PATH = Path(__file__).with_name("schedule.html")


def widget_html():
    html = HTML_PATH.read_text(encoding="utf-8")
    raw = html.encode("utf-8")
    if len(raw) > 32768 or len(zlib.compress(raw, 9)) > 4096:
        raise ValueError("Widget HTML exceeds Telegram limits")
    return html


def json_text(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def state_fields(screen):
    data = dict(screen.widget_data)
    data["b"] = [
        [[button.text, button.callback_data, screen.actions[button.callback_data][0]] for button in row]
        for row in screen.keyboard.inline_keyboard
    ]
    raw = json_text(data).encode("utf-8")
    # Both fields always change together. Split only at a UTF-8 boundary.
    cut = min(1024, len(raw))
    while cut < len(raw) and raw[cut] & 0xC0 == 0x80:
        cut -= 1
    first, second = raw[:cut].decode("utf-8"), raw[cut:].decode("utf-8")
    if len(second.encode("utf-8")) > 1024:
        raise ValueError("Widget state exceeds Telegram limits")
    return {"chat_data": first, "public_data": second}


def _fragments(lesson):
    """Split unusually long source fields into readable continuation pages."""
    base = [lesson.pair_number, lesson.start_time, lesson.end_time, "", "", "", "", ""]
    row = list(base)
    for index, value in enumerate(
        [lesson.subject, lesson.teacher, lesson.classroom, lesson.lesson_type, lesson.groups], 3
    ):
        for char in value or "":
            candidate = list(row)
            candidate[index] += char
            if len(json_text(candidate).encode("utf-8")) > 700:
                yield row
                row = list(base)
            row[index] += char
    yield row


def schedule_pages(schedule, group, now):
    now = now.astimezone(ZoneInfo("Europe/Moscow"))
    day = schedule.date
    base = {
        "v": "day",
        "g": group,
        "d": f"{day.day} {MONTHS[day.month - 1]}",
        "y": day.year,
        "w": DAYS[day.weekday()],
        "n": len({lesson.pair_number for lesson in schedule.lessons}),
        "range": "",
        "next": None,
    }
    if schedule.lessons:
        base["range"] = (
            min(x.start_time for x in schedule.lessons) + " — " + max(x.end_time for x in schedule.lessons)
        )
    # Nearest lesson belongs to the displayed day, never to a past date.
    nearest = next(
        (
            x
            for x in schedule.lessons
            if day > now.date() or (day == now.date() and time.fromisoformat(x.end_time) > now.time())
        ),
        None,
    )
    if nearest:
        base["next"] = [nearest.start_time, nearest.end_time, nearest.subject[:48], nearest.classroom or ""]
    pages, current = [], []
    for lesson in schedule.lessons:
        for row in _fragments(lesson):
            # Reserve space for headings, nearest card and revision-bound buttons.
            if current and (len(current) == 2 or len(json_text(current + [row]).encode("utf-8")) > 800):
                pages.append({**base, "l": current})
                current = []
            current.append(row)
    pages.append({**base, "l": current})
    for i, page in enumerate(pages):
        page["p"] = f"{i + 1}/{len(pages)}" if len(pages) > 1 else ""
    return pages
