import asyncio
import json
import unittest
from datetime import date

import httpx
from app.miniapp.cdo import CdoError, CdoSessions, normalize_schedule


class CdoTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        self.now = 0
        self.mode = "ok"

        async def upstream(request):
            self.requests.append(request)
            if self.mode == "timeout":
                raise httpx.ReadTimeout("secret upstream detail", request=request)
            path = request.url.path
            if path.endswith("/login"):
                body = json.loads(request.content)
                if body["password"] != "valid":
                    return httpx.Response(401, json={"error": "sensitive body"})
                return httpx.Response(200, json={
                    "token": "private-token-" + body["username"],
                    "user": {"firstname": body["username"], "lastname": "Студент"},
                }, headers={"set-cookie": "sid=" + body["username"] + "; Secure; Path=/"})
            if self.mode == "expired":
                return httpx.Response(401, json={})
            if path.endswith("/students/me"):
                return httpx.Response(200, json={"student": {"id": 42}, "group": {"name": "204гму"}})
            if path.endswith("/timetable/student"):
                if self.mode == "malformed":
                    return httpx.Response(200, json={"unexpected": True})
                return httpx.Response(200, json=[{
                    "date": "2026-11-14", "lessons": [{"number": 2, "periods": [{
                        "timeStart": "11:25", "timeEnd": "12:55",
                        "disciplineFullName": "Личная дисциплина", "teachersNameFull": "Преподаватель",
                        "classroom": "А 716", "typeStr": "Сем", "groups": "Моя подгруппа",
                    }]}],
                }])
            return httpx.Response(404)

        self.sessions = CdoSessions(transport=httpx.MockTransport(upstream), clock=lambda: self.now)

    async def asyncTearDown(self):
        await self.sessions.close()

    async def test_login_is_private_and_users_are_isolated(self):
        profile = await self.sessions.login(7, "alice", "valid")
        await self.sessions.login(8, "bob", "valid")
        self.assertEqual(profile["name"], "alice Студент")
        self.assertEqual(profile["group"], "204гму")
        self.assertNotIn("private-token", json.dumps(profile))
        self.assertFalse((await self.sessions.status(9))["connected"])
        data = await self.sessions.schedule(7, date(2026, 11, 14))
        self.assertEqual(data[0]["subject"], "Личная дисциплина")
        request = self.requests[-1]
        self.assertEqual(request.headers["authorization"], "Bearer private-token-alice")
        self.assertIn("sid=alice", request.headers["cookie"])
        self.assertNotIn("bob", str(request.headers))
        self.assertEqual(json.loads(request.content)["studentId"], "42")
        await self.sessions.logout(7)
        self.assertFalse((await self.sessions.status(7))["connected"])
        self.assertTrue((await self.sessions.status(8))["connected"])
        with self.assertRaises(CdoError) as error:
            await self.sessions.schedule(7, date(2026, 11, 14))
        self.assertEqual(error.exception.status, 401)

    async def test_invalid_password_timeout_and_invalid_payload_are_distinct(self):
        with self.assertRaises(CdoError) as error:
            await self.sessions.login(7, "alice", "wrong")
        self.assertEqual(error.exception.status, 401)
        self.assertNotIn("sensitive", str(error.exception))
        self.mode = "timeout"
        with self.assertRaises(CdoError) as error:
            await self.sessions.login(7, "alice", "valid")
        self.assertEqual(error.exception.status, 503)
        self.assertNotIn("secret", str(error.exception))
        self.mode = "ok"
        await self.sessions.login(7, "alice", "valid")
        self.mode = "malformed"
        with self.assertRaises(CdoError) as error:
            await self.sessions.schedule(7, date(2026, 11, 14))
        self.assertEqual(error.exception.status, 502)

    async def test_local_and_upstream_expiry_clear_connection(self):
        await self.sessions.login(7, "alice", "valid")
        self.now = 3601
        self.assertFalse((await self.sessions.status(7))["connected"])
        await self.sessions.login(7, "alice", "valid")
        self.mode = "expired"
        with self.assertRaises(CdoError):
            await self.sessions.schedule(7, date(2026, 11, 14))
        self.assertFalse((await self.sessions.status(7))["connected"])

    async def test_login_rate_limit_and_validation_do_not_call_source(self):
        for _ in range(5):
            with self.assertRaises(CdoError):
                await self.sessions.login(7, "alice", "wrong")
        total = len(self.requests)
        with self.assertRaises(CdoError) as error:
            await self.sessions.login(7, "alice", "valid")
        self.assertEqual(error.exception.status, 429)
        self.assertEqual(total, len(self.requests))
        with self.assertRaises(CdoError):
            await self.sessions.login(8, "", "valid")
        self.assertEqual(total, len(self.requests))

    async def test_logout_waits_for_inflight_login_then_removes_it(self):
        started, release = asyncio.Event(), asyncio.Event()

        async def slow_upstream(request):
            if request.url.path.endswith("/login"):
                started.set()
                await release.wait()
                return httpx.Response(200, json={"token": "PRIVATE", "user": {"firstname": "Дени"}})
            return httpx.Response(200, json={"student": {"id": 42}})

        sessions = CdoSessions(transport=httpx.MockTransport(slow_upstream))
        try:
            login = asyncio.create_task(sessions.login(7, "alice", "valid"))
            await started.wait()
            logout = asyncio.create_task(sessions.logout(7))
            await asyncio.sleep(0)
            release.set()
            await asyncio.gather(login, logout)
            self.assertFalse((await sessions.status(7))["connected"])
        finally:
            await sessions.close()


class NormalizationTests(unittest.TestCase):
    def test_empty_day_is_not_an_invalid_response(self):
        day = date(2026, 11, 14)
        self.assertEqual(normalize_schedule([], day), [])
        with self.assertRaises(CdoError):
            normalize_schedule({"error": "offline"}, day)
        with self.assertRaises(CdoError):
            normalize_schedule([{"date": "2026-11-14", "lessons": [{"number": 1, "periods": [{}]}]}], day)
        with self.assertRaises(CdoError):
            normalize_schedule([{"date": "invalid", "lessons": []}], day)

    def test_numbering_and_source_subgroups_survive(self):
        data = [{"date": "2026-11-14", "lessons": [{"number": 1, "periods": [{
            "timeStart": "11:25:00", "timeEnd": "12:55:00", "disciplineFullName": "История",
            "teachersNameFull": "Иванов", "groups": "подгруппа 1", "classroom": "А 716",
        }]}]}]
        lesson = normalize_schedule(data, date(2026, 11, 14))[0]
        self.assertEqual(lesson["pair_number"], 2)
        self.assertEqual(lesson["groups"], "подгруппа 1")
        self.assertEqual(lesson["start_time"], "11:25")


if __name__ == "__main__":
    unittest.main()
