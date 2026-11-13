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
        self.cdo = AsyncMock()
        self.cdo.status.return_value = {"connected": True, "name": "Студент", "group": "204гму"}
        self.cdo.schedule.return_value = [{"start_time": "11:25", "end_time": "12:55", "subject": "Личные пары", "pair_number": 2}]
        self.service.get_faculties.return_value = [Option("5", "Бакалавриат")]
        self.service.get_courses.return_value = [Option("1", "1")]
        self.service.get_groups.return_value = [Option("7", "204гму")]
        self.now = datetime(2026, 11, 13, 18, tzinfo=ZoneInfo("Europe/Moscow"))

        async def schedule(group, day, *args, **kwargs):
            return DaySchedule(day, [Lesson("11:25", "15:40", "История", pair_number=2)])

        self.service.get_schedule.side_effect = schedule
        self.client = TestClient(TestServer(create_app(self.service, TOKEN, clock=lambda: self.now, cdo=self.cdo)))
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

    async def test_cdo_routes_require_signed_user_and_do_not_trust_student_id(self):
        response = await self.client.post("/api/cdo/session", json={"username": "alice", "password": "secret"})
        self.assertEqual(response.status, 401)
        self.cdo.login.assert_not_called()
        self.cdo.login.return_value = {"connected": True, "name": "Студент", "group": "204гму"}
        response = await self.client.post("/api/cdo/session", json={"username": "alice", "password": "secret"}, headers=self.headers)
        self.assertEqual(response.status, 200)
        self.cdo.login.assert_awaited_once_with(7, "alice", "secret")
        response = await self.client.get("/api/cdo/schedule?date=2026-11-13&studentId=999&user_id=8", headers=self.headers)
        self.assertEqual(response.status, 200)
        self.cdo.schedule.assert_awaited_once_with(7, self.now.date())
        self.assertEqual((await response.json())["lessons"][0]["subject"], "Личные пары")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        response = await self.client.delete("/api/cdo/session", headers=self.headers)
        self.assertEqual(response.status, 200)
        self.cdo.logout.assert_awaited_once_with(7)

    async def test_cdo_date_payload_and_expired_session_errors(self):
        from app.miniapp.cdo import CdoError
        for body in [[], None, {"username": 123, "password": "x"}]:
            response = await self.client.post("/api/cdo/session", json=body, headers=self.headers)
            self.assertEqual(response.status, 400)
        response = await self.client.get("/api/cdo/schedule?date=bad", headers=self.headers)
        self.assertEqual(response.status, 400)
        self.cdo.schedule.side_effect = CdoError("Войди заново.", 401)
        response = await self.client.get("/api/cdo/schedule", headers=self.headers)
        self.assertEqual(response.status, 401)
        self.assertEqual((await response.json())["error"], "Войди заново.")


if __name__ == "__main__":
    unittest.main()
