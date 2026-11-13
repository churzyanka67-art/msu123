import hashlib
import hmac
import json
import time
import unittest
from datetime import datetime
from unittest.mock import AsyncMock
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from aiohttp.test_utils import TestClient, TestServer
from app.miniapp.server import create_app, validate_init_data

from app.models.schedule import DaySchedule, Lesson, Option
from app.services.parser import SourceError

TOKEN = "123456:FAKE_TEST_TOKEN"


def credentials(**changes):
    fields = {"user": json.dumps({"id": 7, "first_name": "Дени"}), "auth_date": str(int(time.time()))}
    fields.update(changes)
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


class AuthTests(unittest.TestCase):
    def test_accepts_signed_telegram_data(self):
        self.assertEqual(validate_init_data(credentials(), TOKEN)["id"], 7)

    def test_rejects_tampering_expiry_duplicates_and_future(self):
        for value in [
            credentials().replace("%3A+7", "%3A+8"),
            credentials(auth_date="1"),
            credentials() + "&user=another",
            credentials(auth_date=str(int(time.time()) + 3600)),
            "",
        ]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_init_data(value, TOKEN)


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = AsyncMock()
        self.service.get_faculties.return_value = [Option("5", "Бакалавриат")]
        self.service.get_courses.return_value = [Option("1", "1")]
        self.service.get_groups.return_value = [Option("7", "204гму")]
        self.now = datetime(2026, 11, 13, 18, tzinfo=ZoneInfo("Europe/Moscow"))

        async def schedule(group, day, *args, **kwargs):
            return DaySchedule(day, [Lesson("11:25", "15:40", "История", pair_number=2)])

        self.service.get_schedule.side_effect = schedule
        self.client = TestClient(TestServer(create_app(self.service, TOKEN, clock=lambda: self.now)))
        await self.client.start_server()
        self.headers = {"X-Telegram-Init-Data": credentials()}

    async def asyncTearDown(self):
        await self.client.close()

    async def test_api_requires_signature_but_static_app_is_public(self):
        response = await self.client.get("/")
        self.assertEqual(response.status, 200)
        self.assertIn("Моя группа", await response.text())
        response = await self.client.get("/api/options")
        self.assertEqual(response.status, 401)
        self.service.get_faculties.assert_not_called()

    async def test_catalog_and_selection_validation(self):
        response = await self.client.get("/api/options?faculty=5&course=1", headers=self.headers)
        self.assertEqual((await response.json())["options"][0]["name"], "204гму")
        response = await self.client.get("/api/options?faculty=other", headers=self.headers)
        self.assertEqual(response.status, 400)

    async def test_auto_tomorrow_and_explicit_today(self):
        args = {"faculty": "5", "course": "1", "group": "7"}
        response = await self.client.get("/api/schedule", params=args, headers=self.headers)
        data = await response.json()
        self.assertEqual(data["date"], "2026-11-14")
        self.assertTrue(data["advanced"])
        self.assertEqual(data["lessons"][0]["pair_number"], 2)
        response = await self.client.get(
            "/api/schedule", params={**args, "date": "2026-11-13"}, headers=self.headers
        )
        self.assertEqual((await response.json())["date"], "2026-11-13")

    async def test_source_failure_and_invalid_dates(self):
        args = {"faculty": "5", "course": "1", "group": "7"}
        response = await self.client.get(
            "/api/schedule", params={**args, "date": "invalid"}, headers=self.headers
        )
        self.assertEqual(response.status, 400)
        self.service.get_schedule.side_effect = SourceError("source offline")
        response = await self.client.get("/api/schedule", params=args, headers=self.headers)
        self.assertEqual(response.status, 503)
        self.assertNotIn(TOKEN, await response.text())


if __name__ == "__main__":
    unittest.main()
