"""Screen transitions independent of Telegram I/O and state persistence."""

import logging
import secrets
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from html import escape

from aiogram.types import InlineKeyboardMarkup

from app.formatting import DAYS, format_pages, shift_date, today_moscow
from app.keyboards.inline import build_keyboard
from app.models.schedule import Option
from app.services.parser import SourceError

log = logging.getLogger(__name__)


class StaleCallback(Exception):
    pass


@dataclass
class Selection:
    faculty: Option | None = None
    course: Option | None = None
    group: Option | None = None
    day: date | None = None
    view: str = "faculties"
    page: int = 0


@dataclass
class Screen:
    text: str
    keyboard: InlineKeyboardMarkup
    actions: dict
    selection: Selection
    message_id: int | None = None


def make_screen(text, rows, selection):
    keyboard, actions = build_keyboard(rows, secrets.token_hex(8))
    return Screen(text, keyboard, actions, deepcopy(selection))


class Controller:
    def __init__(self, service, *, today=today_moscow):
        self.service = service
        self.today = today

    async def start(self):
        return await self._transition(Selection(), ("reset", None))

    async def act(self, screen: Screen, callback: str):
        if callback not in screen.actions:
            raise StaleCallback()
        return await self._transition(deepcopy(screen.selection), screen.actions[callback])

    async def _transition(self, state, action):
        original = deepcopy(state)
        name, value = action
        refresh = False
        if name == "retry":
            name, value = value
            refresh = True
        try:
            if name == "reset":
                state = Selection()
            elif name == "faculty":
                state = Selection(faculty=value, view="courses")
            elif name == "course":
                state.course, state.group, state.view, state.page = value, None, "groups", 0
            elif name == "group":
                state.group, state.day, state.view, state.page = value, self.today(), "schedule", 0
            elif name == "back":
                state.view, state.page = value, 0
            elif name == "date":
                state.day, state.page = value, 0
            elif name == "page":
                state.page = value
            else:
                raise StaleCallback()
            return await self._render(state, refresh=refresh)
        except SourceError as exc:
            log.warning("MSU source failure: %s", exc)
            return make_screen(
                "⚠️ Не удалось получить расписание с сайта МГУ.\n"
                "Попробуйте ещё раз чуть позже. Если группа исчезла с сайта, выберите её заново.",
                [[("🔄 Повторить", ("retry", (name, value)))], [("🔄 Сменить группу", ("reset", None))]],
                original,
            )

    async def _render(self, s, *, refresh=False):
        rows = []
        if s.view == "schedule":
            schedule = await self.service.get_schedule(
                s.group.id, s.day, s.faculty.id, s.course.id, refresh=refresh
            )
            pages = format_pages(schedule, s.group.name)
            s.page = min(max(s.page, 0), len(pages) - 1)
            text = pages[s.page]
            if len(pages) > 1:
                text += f"\n\nСтраница {s.page + 1}/{len(pages)}"
                pager = []
                if s.page:
                    pager.append(("← Страница", ("page", s.page - 1)))
                if s.page + 1 < len(pages):
                    pager.append(("Страница →", ("page", s.page + 1)))
                rows.append(pager)
            nav = []
            for step in (-1, 1):
                try:
                    target = shift_date(s.day, step)
                except OverflowError:
                    continue
                label = (
                    "Сегодня"
                    if target == self.today()
                    else ("Завтра" if step == 1 and s.day == self.today() else DAYS[target.weekday()])
                )
                nav.append((f"← {label}" if step < 0 else f"{label} →", ("date", target)))
            rows += [nav, [("🔄 Сменить группу", ("reset", None))]]
        else:
            if s.view == "faculties":
                options = await self.service.get_faculties(refresh=refresh)
                text = "👋 <b>Расписание МГУ</b>\n\nВыберите факультет:"
                action = "faculty"
            elif s.view == "courses":
                options = await self.service.get_courses(s.faculty.id, refresh=refresh)
                text = f"<b>Факультет:</b> {escape(s.faculty.name)}\n\nВыберите курс:"
                action = "course"
            else:
                options = await self.service.get_groups(s.faculty.id, s.course.id, refresh=refresh)
                text = f"<b>Факультет:</b> {escape(s.faculty.name)}\n<b>Курс:</b> {escape(s.course.name)}\n\nВыберите группу:"
                action = "group"
            if not options:
                raise SourceError("Empty catalog or expired selection")
            count = 20
            s.page = min(max(s.page, 0), (len(options) - 1) // count)
            buttons = [
                ((o.name + " курс") if action == "course" else o.name, (action, o))
                for o in options[s.page * count : (s.page + 1) * count]
            ]
            width = 1 if action == "faculty" else 2
            rows = [buttons[i : i + width] for i in range(0, len(buttons), width)]
            pager = []
            if s.page:
                pager.append(("← Страница", ("page", s.page - 1)))
            if (s.page + 1) * count < len(options):
                pager.append(("Страница →", ("page", s.page + 1)))
            if pager:
                rows.append(pager)
            if s.view != "faculties":
                rows.append([("← Назад", ("back", "faculties" if s.view == "courses" else "courses"))])
        return make_screen(text, rows, s)
