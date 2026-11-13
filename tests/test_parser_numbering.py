import unittest
from datetime import date

from app.services.parser import parse_schedule


def schedule_html(starts, content="Предмет"):
    rows = [
        f'<tr><th><span class="start">{start}</span><span class="end">21:00</span></th>'
        f'<td><a data-toggle="popover" data-content="{content}">Предмет</a></td></tr>'
        for start in starts
    ]
    return (
        '<table id="timeTable"><tr><th class="headdate">10.11.2026</th></tr>'
        + "".join(rows)
        + "</table>"
    )


class PairNumberTests(unittest.TestCase):
    def test_missing_earlier_rows_do_not_shift_numbers(self):
        for starts, numbers in [
            (["11:25"], [2]),
            (["09:40", "13:10", "17:25"], [1, 3, 5]),
            (["13:10", "13:10", "15:40"], [3, 3, 4]),
            (["19:10", "20:55"], [6, 7]),
        ]:
            with self.subTest(starts=starts):
                day = parse_schedule(schedule_html(starts), date(2026, 11, 10))
                self.assertEqual([lesson.pair_number for lesson in day.lessons], numbers)

    def test_custom_lesson_time_keeps_its_timetable_slot_number(self):
        day = parse_schedule(
            schedule_html(["15:40"], "15:00–17:00&lt;br&gt;Предмет"),
            date(2026, 11, 10),
        )
        self.assertEqual(day.lessons[0].start_time, "15:00")
        self.assertEqual(day.lessons[0].pair_number, 4)


if __name__ == "__main__":
    unittest.main()
