import unittest
from datetime import date

from app.formatting import format_pages
from app.models.schedule import DaySchedule, Lesson


class FormatPagesTests(unittest.TestCase):
    def test_numbers_time_slots_and_keeps_same_number_for_multiple_rows(self):
        schedule = DaySchedule(
            date(2026, 9, 11),
            lessons=[
                Lesson("11:25", "12:55", "Социология", "Осипов Егор", "В3", "Лк", pair_number=2),
                Lesson("13:10", "14:40", "Английский язык", "Мокричук Елизавета", "Г 809", "Пз", pair_number=3),
                Lesson("13:10", "14:40", "Английский язык", "Другой преподаватель", "Г 810", "Пз", pair_number=3),
            ],
        )

        page = format_pages(schedule, "2025_ГМУ-3-2")[0]

        self.assertIn("<b>2. 11:25–12:55</b>", page)
        self.assertIn("<b>3. 13:10–14:40</b>", page)
        self.assertEqual(page.count("<b>3. 13:10–14:40</b>"), 1)
        self.assertIn("Английский язык (Пз)", page)
        self.assertIn("👨‍🏫 Другой преподаватель", page)


if __name__ == "__main__":
    unittest.main()
