import unittest
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from app.controller import Controller, Selection
from app.models.schedule import DaySchedule, Lesson, Option
from app.services.parser import SourceError

TODAY = date(2026, 11, 10)
TOMORROW = TODAY + timedelta(days=1)
GROUP = Option("1", "101")


class DefaultDateTests(unittest.IsolatedAsyncioTestCase):
    def controller(self, clock, lessons):
        today_schedule = DaySchedule(TODAY, lessons)
        service = AsyncMock()
        service.get_schedule.side_effect = lambda _, day, *args, **kwargs: (
            today_schedule if day == TODAY else DaySchedule(day)
        )
        controller = Controller(
            service,
            today=lambda: TODAY,
            now=lambda: datetime.fromisoformat(clock).replace(tzinfo=ZoneInfo("Europe/Moscow")),
        )
        state = Selection(faculty=Option("5", "ФГУ"), course=Option("1", "1"))
        return controller, state

    async def test_opens_tomorrow_at_and_after_last_lesson_end(self):
        for clock in ("2026-11-10T15:40:00", "2026-11-10T21:00:00"):
            with self.subTest(clock=clock):
                controller, state = self.controller(
                    clock, [Lesson("14:10", "15:40", "Предмет", pair_number=4)]
                )
                screen = await controller._transition(state, ("group", GROUP))
                self.assertEqual(screen.selection.day, TOMORROW)
                self.assertIn("11 ноября", screen.text)
                self.assertIn(("date", TODAY), screen.actions.values())

    async def test_keeps_today_while_last_lesson_is_running(self):
        controller, state = self.controller(
            "2026-11-10T15:39:59", [Lesson("14:10", "15:40", "Предмет", pair_number=4)]
        )
        screen = await controller._transition(state, ("group", GROUP))
        self.assertEqual(screen.selection.day, TODAY)
        controller.service.get_schedule.assert_awaited_once()

    async def test_uses_latest_end_even_for_overlapping_lessons(self):
        controller, state = self.controller(
            "2026-11-10T16:00:00",
            [
                Lesson("13:10", "17:00", "Длинная пара", pair_number=3),
                Lesson("15:00", "15:40", "Подгруппа", pair_number=4),
            ],
        )
        screen = await controller._transition(state, ("group", GROUP))
        self.assertEqual(screen.selection.day, TODAY)

    async def test_can_manually_return_to_today_after_auto_advance(self):
        controller, state = self.controller(
            "2026-11-10T20:00:00", [Lesson("14:10", "15:40", "Предмет", pair_number=4)]
        )
        screen = await controller._transition(state, ("group", GROUP))
        callback = next(key for key, action in screen.actions.items() if action == ("date", TODAY))
        screen = await controller.act(screen, callback)
        self.assertEqual(screen.selection.day, TODAY)

    async def test_empty_today_does_not_skip_days(self):
        controller, state = self.controller("2026-11-10T20:00:00", [])
        screen = await controller._transition(state, ("group", GROUP))
        self.assertEqual(screen.selection.day, TODAY)

    async def test_retry_repeats_automatic_date_selection(self):
        controller, state = self.controller(
            "2026-11-10T20:00:00", [Lesson("14:10", "15:40", "Предмет", pair_number=4)]
        )
        load = controller.service.get_schedule.side_effect

        def fail_tomorrow_once(*args, **kwargs):
            if args[1] == TOMORROW:
                controller.service.get_schedule.side_effect = load
                raise SourceError("Temporary failure")
            return load(*args, **kwargs)

        controller.service.get_schedule.side_effect = fail_tomorrow_once
        screen = await controller._transition(state, ("group", GROUP))
        retry = next(key for key, action in screen.actions.items() if action[0] == "retry")
        screen = await controller.act(screen, retry)
        self.assertEqual(screen.selection.day, TOMORROW)


if __name__ == "__main__":
    unittest.main()
