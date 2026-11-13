"""MyFGU integration. Passwords are used once; sessions remain server-side."""

import asyncio
import re
from collections import deque
from dataclasses import dataclass
from datetime import date, time
from time import monotonic
from weakref import WeakValueDictionary

import httpx

ORIGIN = "https://my.spa.msu.ru"
PAIR_STARTS = ("09:40", "11:25", "13:10", "15:40", "17:25", "19:10", "20:55")


class CdoError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def normalize_schedule(data, day):
    """Normalize the day/slot/period response used by MyFGU's web client."""
    if not isinstance(data, list):
        raise CdoError("ЦДО вернуло неожиданный формат расписания.")
    result = []
    for entry in data:
        if not isinstance(entry, dict) or not isinstance(entry.get("date"), str):
            raise CdoError("Не удалось прочитать дату личного расписания.")
        try:
            entry_day = date.fromisoformat(entry["date"])
        except ValueError:
            raise CdoError("ЦДО вернуло некорректную дату расписания.") from None
        if entry_day != day:
            continue
        slots = entry.get("lessons")
        if not isinstance(slots, list):
            raise CdoError("Не удалось прочитать пары личного расписания.")
        for slot in slots:
            if not isinstance(slot, dict) or not isinstance(slot.get("periods"), list):
                raise CdoError("Не удалось прочитать пары личного расписания.")
            for period in slot["periods"]:
                if not isinstance(period, dict):
                    raise CdoError("Не удалось прочитать занятие.")
                start, end = period.get("timeStart", ""), period.get("timeEnd", "")
                subject = period.get("disciplineFullName") or period.get("disciplineShortName")
                try:
                    if not isinstance(start, str) or not isinstance(end, str):
                        raise TypeError
                    start, end = time.fromisoformat(start).strftime("%H:%M"), time.fromisoformat(end).strftime("%H:%M")
                    if end <= start or not isinstance(subject, str) or not subject.strip():
                        raise ValueError
                except (ValueError, TypeError):
                    raise CdoError("В личном расписании не хватает времени или названия пары.") from None
                number = PAIR_STARTS.index(start) + 1 if start in PAIR_STARTS else slot.get("number")
                lesson = {"start_time": start, "end_time": end, "subject": subject,
                          "pair_number": number if type(number) is int and 1 <= number <= 12 else None}
                for target, value in {
                    "teacher": period.get("teachersNameFull") or period.get("teachersName") or "",
                    "classroom": period.get("classroom") or "",
                    "lesson_type": period.get("typeStr") or "",
                    "groups": period.get("groups") or "",
                }.items():
                    if not isinstance(value, str):
                        raise CdoError("ЦДО вернуло неожиданные данные занятия.")
                    lesson[target] = value
                result.append(lesson)
    return sorted(result, key=lambda lesson: lesson["start_time"])


@dataclass
class Session:
    client: httpx.AsyncClient
    student_id: str
    profile: dict
    expires: float


class CdoSessions:
    def __init__(self, *, transport=None, clock=monotonic):
        self._transport = transport
        self._clock = clock
        self._sessions = {}
        self._locks = WeakValueDictionary()
        self._attempts = {}

    def _lock(self, user_id):
        lock = self._locks.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[user_id] = lock
        return lock

    async def _drop(self, user_id):
        session = self._sessions.pop(user_id, None)
        if session:
            await session.client.aclose()

    async def _session(self, user_id):
        session = self._sessions.get(user_id)
        if session and session.expires <= self._clock():
            await self._drop(user_id)
            return None
        return session

    async def _request(self, client, method, path, *, login=False, **kwargs):
        try:
            response = await client.request(method, ORIGIN + path, **kwargs)
        except httpx.HTTPError:
            raise CdoError("Сайт ЦДО не отвечает. Попробуй чуть позже.", 503) from None
        if response.status_code in {401, 403}:
            raise CdoError("Неверный логин или пароль." if login else "Сессия ЦДО закончилась. Войди заново.", 401)
        if response.status_code == 429:
            raise CdoError("Слишком много попыток входа. Подожди минуту.", 429)
        if response.status_code >= 500:
            raise CdoError("Сайт ЦДО временно недоступен.", 503)
        if response.status_code == 404 and path.endswith("/students/me"):
            raise CdoError("Аккаунт ЦДО не связан с карточкой студента. Личное расписание недоступно.", 422)
        if not response.is_success:
            raise CdoError("ЦДО не разрешило получить эти данные.")
        try:
            return response.json()
        except ValueError:
            raise CdoError("ЦДО вернуло нечитаемый ответ.") from None

    async def login(self, user_id, username, password):
        if not isinstance(username, str) or not isinstance(password, str):
            raise CdoError("Введи логин и пароль ЦДО.", 400)
        username = username.strip()
        if not username or len(username) > 150 or not password or len(password) > 1024:
            raise CdoError("Проверь логин и пароль ЦДО.", 400)
        async with self._lock(user_id):
            now = self._clock()
            self._attempts = {key: values for key, values in self._attempts.items() if values and values[-1] > now - 60}
            if user_id not in self._attempts and len(self._attempts) >= 512:
                raise CdoError("Вход сейчас занят. Попробуй через минуту.", 429)
            attempts = self._attempts.setdefault(user_id, deque())
            while attempts and attempts[0] <= now - 60:
                attempts.popleft()
            if len(attempts) >= 5:
                raise CdoError("Слишком много попыток входа. Подожди минуту.", 429)
            attempts.append(now)
            for key in list(self._sessions):
                await self._session(key)
            if user_id not in self._sessions and len(self._sessions) >= 256:
                raise CdoError("Сейчас слишком много подключений ЦДО. Попробуй позже.", 503)
            client = httpx.AsyncClient(transport=self._transport, timeout=20, follow_redirects=False)
            try:
                auth = await self._request(client, "POST", "/api/auth/login", login=True,
                                           json={"username": username, "password": password})
                if not isinstance(auth, dict) or not isinstance(auth.get("user"), dict) or not isinstance(auth.get("token"), str) or not auth["token"]:
                    raise CdoError("ЦДО не вернуло сессию. Попробуй войти ещё раз.")
                client.headers["Authorization"] = "Bearer " + auth["token"]
                student = await self._request(client, "GET", "/api/web/students/me")
                record = student.get("student") if isinstance(student, dict) else None
                student_id = record.get("id") if isinstance(record, dict) else None
                if isinstance(student_id, bool) or not isinstance(student_id, (int, str)) or not re.fullmatch(r"[0-9A-Za-z_-]{1,64}", str(student_id)):
                    raise CdoError("Аккаунт ЦДО не связан с карточкой студента. Личное расписание недоступно.", 422)
                user = auth["user"]
                name = " ".join(value for value in (user.get("firstname"), user.get("lastname")) if isinstance(value, str)) or username
                group = student.get("group")
                group_name = group.get("name", "") if isinstance(group, dict) else ""
                profile = {"connected": True, "name": name, "group": group_name if isinstance(group_name, str) else ""}
                await self._drop(user_id)
                self._sessions[user_id] = Session(client, str(student_id), profile, now + 3600)
                return dict(profile)
            except BaseException:
                await client.aclose()
                raise

    async def status(self, user_id):
        async with self._lock(user_id):
            session = await self._session(user_id)
            return dict(session.profile) if session else {"connected": False}

    async def schedule(self, user_id, day):
        async with self._lock(user_id):
            session = await self._session(user_id)
            if not session:
                raise CdoError("Войди через ЦДО, чтобы открыть личное расписание.", 401)
            try:
                data = await self._request(session.client, "POST", "/api/web/timetable/student", json={
                    "studentId": session.student_id, "dateStart": day.isoformat(), "dateEnd": day.isoformat(),
                })
            except CdoError as error:
                if error.status == 401:
                    await self._drop(user_id)
                raise
            return normalize_schedule(data, day)

    async def logout(self, user_id):
        async with self._lock(user_id):
            await self._drop(user_id)

    async def close(self):
        for user_id in list(self._sessions):
            await self._drop(user_id)
