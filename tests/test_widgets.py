import json
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import Update
from app.widgets.api import AnswerWidgetQuery, EditMessageWidgetData
from app.widgets.presentation import state_fields, widget_html

from app.controller import Controller, Selection
from app.handlers.flow import FlowHandlers
from app.models.schedule import DaySchedule, Lesson, Option
from app.services.parser import parse_schedule
from app.storage import MemoryStore

NOW = datetime(2026, 9, 9, 8, tzinfo=ZoneInfo("Europe/Moscow"))


class WidgetTests(unittest.IsolatedAsyncioTestCase):
    def setup_controller(self, schedule=None):
        service = AsyncMock()
        service.get_faculties.return_value = [Option("5", "Бакалавриат")]
        service.get_courses.return_value = [Option("1", "1")]
        service.get_groups.return_value = [Option(str(i), f"{i}гму") for i in range(101, 121)]
        service.get_schedule.return_value = schedule or parse_schedule(
            (Path(__file__).resolve().parents[1] / "tests/fixtures/day.html").read_text(), NOW.date()
        )
        return Controller(service, widgets=True, today=lambda: NOW.date(), now=lambda: NOW)

    def payload(self, screen):
        fields = state_fields(screen)
        self.assertTrue(all(len(value.encode()) <= 1024 for value in fields.values()))
        return json.loads(fields["chat_data"] + fields["public_data"])

    async def choose(self, controller, screen, action):
        key = next(key for key, value in screen.actions.items() if value[0] == action)
        return await controller.act(screen, key)

    async def test_real_source_selection_and_all_schedule_pages_fit_protocol(self):
        controller = self.setup_controller()
        screen = await controller.start()
        self.payload(screen)
        screen = await self.choose(controller, screen, "faculty")
        self.payload(screen)
        screen = await self.choose(controller, screen, "course")
        self.payload(screen)
        catalog = screen
        screen = await self.choose(controller, screen, "group")
        subjects = []
        while True:
            data = self.payload(screen)
            subjects += [row[3] for row in data["l"]]
            next_key = next(
                (
                    key
                    for key, value in screen.actions.items()
                    if value == ("page", screen.selection.page + 1)
                ),
                None,
            )
            if next_key is None:
                break
            screen = await controller.act(screen, next_key)
        self.assertIn("История России", subjects)
        self.assertEqual(len(subjects), 4)
        catalog = await controller.act(
            catalog, next(key for key, action in catalog.actions.items() if action == ("page", 1))
        )
        self.payload(catalog)

    async def test_large_unicode_fields_are_preserved_across_pages(self):
        subject = "Длинное название 😀 <script>" * 100
        lesson = Lesson("09:40", "11:10", subject, "Учитель " * 100, "В3", pair_number=1)
        controller = self.setup_controller(DaySchedule(NOW.date(), [lesson]))
        state = Selection(Option("5", "ФГУ"), Option("1", "1"), Option("7", "101гму"), NOW.date(), "schedule")
        screen = await controller._render(state)
        subjects, teachers = [], []
        while True:
            data = self.payload(screen)
            subjects += [row[3] for row in data["l"]]
            teachers += [row[4] for row in data["l"]]
            key = next(
                (
                    key
                    for key, value in screen.actions.items()
                    if value == ("page", screen.selection.page + 1)
                ),
                None,
            )
            if key is None:
                break
            screen = await controller.act(screen, key)
        self.assertEqual("".join(subjects), subject)
        self.assertEqual("".join(teachers), lesson.teacher)

    async def test_new_update_reaches_handler_and_failed_edit_preserves_actions(self):
        controller = self.setup_controller()
        screen = await controller.start()
        screen.message_id = 5
        store = MemoryStore()
        await store.set((7, 7), screen)
        flow = FlowHandlers(controller, store, widgets=True)
        dispatcher = Dispatcher()
        dispatcher.update.outer_middleware(flow.widget_update)
        update = Update.model_validate(
            {
                "update_id": 1,
                "widget_query": {
                    "id": "q",
                    "from": {"id": 7, "is_bot": False, "first_name": "А"},
                    "chat": {"id": 7, "type": "private"},
                    "message_id": 5,
                    "data": next(iter(screen.actions)),
                },
            }
        )
        bot = Bot("123456:TEST_TOKEN")
        bot.session = AsyncMock()

        async def fail_edit(*args, **kwargs):
            method = args[1]
            if isinstance(method, EditMessageWidgetData):
                raise TelegramNetworkError(method=method, message="offline")
            return True

        bot.session.side_effect = fail_edit
        await dispatcher.feed_update(bot, update)
        self.assertIs(await store.get((7, 7)), screen)
        self.assertIsInstance(bot.session.call_args_list[0].args[1], AnswerWidgetQuery)
        bot.session.side_effect = None
        bot.session.return_value = True
        await dispatcher.feed_update(bot, update)
        self.assertEqual((await store.get((7, 7))).selection.view, "courses")
        # The same revision cannot select a faculty again on the new screen.
        bot.session.reset_mock()
        await dispatcher.feed_update(bot, update)
        self.assertEqual(bot.session.call_count, 1)
        self.assertIn("error", bot.session.call_args.args[1].data)
        await dispatcher.storage.close()

    def test_html_is_under_telegram_limits(self):
        self.assertIn("TelegramWidget", widget_html())


if __name__ == "__main__":
    unittest.main()
