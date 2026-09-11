from datetime import date, datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

from app.models.schedule import DaySchedule

DAYS = ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье")
MONTHS = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


def today_moscow(now: datetime | None = None) -> date:
    return (now or datetime.now(ZoneInfo("Europe/Moscow"))).astimezone(ZoneInfo("Europe/Moscow")).date()


def shift_date(day: date, step: int) -> date:
    return day + timedelta(days=step)


def date_label(day: date) -> str:
    return f"{DAYS[day.weekday()]}, {day.day} {MONTHS[day.month - 1]} {day.year}"


def escaped_chunks(text: str, limit: int = 2500) -> list[str]:
    """Split before escaping so entities and Unicode characters stay intact."""
    chunks, current, length = [], [], 0
    for char in text:
        encoded = escape(char)
        size = len(encoded.encode("utf-16-le")) // 2
        if current and length + size > limit:
            chunks.append("".join(current))
            current, length = [], 0
        current.append(encoded)
        length += size
    if current:
        chunks.append("".join(current))
    return chunks or [""]


def format_pages(schedule: DaySchedule, group: str) -> list[str]:
    header = f"📅 <b>{date_label(schedule.date)}</b>\n🎓 <b>Группа {escape(group[:120])}</b>"
    pair_blocks = []
    for lesson in schedule.lessons:
        text = f"{lesson.subject}"
        if lesson.lesson_type:
            text += f" ({lesson.lesson_type})"
        if lesson.teacher:
            text += f"\n👨‍🏫 {lesson.teacher}"
        if lesson.classroom:
            text += f"\n📍 {lesson.classroom}"
        if lesson.groups and lesson.groups != group:
            text += f"\nГруппы: {lesson.groups}"
        for chunk in escaped_chunks(text):
            if pair_blocks and pair_blocks[-1][0] == lesson.pair_number:
                pair_blocks[-1][1].append(chunk)
            else:
                pair_blocks.append(
                    (
                        lesson.pair_number,
                        [
                            f"<b>{lesson.pair_number}. {escape(lesson.start_time)}–{escape(lesson.end_time)}</b>\n{chunk}"
                        ],
                    )
                )
    blocks = []
    for _, entries in pair_blocks:
        heading = entries[0].split("\n", 1)[0]
        details = [entry.split("\n", 1)[1] for entry in entries]
        blocks.append(heading + "\n" + "\n\n".join(details))
    if not blocks:
        blocks = ["😴 В этот день занятий нет."]
    pages, current = [], header
    for block in blocks:
        if len((current + "\n\n" + block).encode("utf-16-le")) // 2 > 3900:
            pages.append(current)
            current = header
        current += "\n\n" + block
    pages.append(current)
    return pages
