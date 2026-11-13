import hashlib
import hmac
import json
from dataclasses import asdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from time import time as timestamp
from urllib.parse import parse_qsl
from zoneinfo import ZoneInfo

from aiohttp import web

from app.formatting import DAYS, MONTHS
from app.services.parser import SourceError

STATIC = Path(__file__).with_name("static")
MOSCOW = ZoneInfo("Europe/Moscow")


def validate_init_data(raw, token, *, now=None, max_age=86400):
    if not raw or len(raw) > 8192:
        raise ValueError("Missing Telegram credentials")
    pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True, max_num_fields=30)
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise ValueError("Duplicate credentials")
    received = fields.pop("hash", "")
    check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise ValueError("Invalid Telegram signature")
    age = (timestamp() if now is None else now) - int(fields.get("auth_date", "0"))
    if not -30 <= age <= max_age:
        raise ValueError("Expired Telegram credentials")
    user = json.loads(fields.get("user", "{}"))
    if type(user.get("id")) is not int or user["id"] <= 0:
        raise ValueError("Invalid Telegram user")
    return user


def create_app(service, token, *, clock=None):
    clock = clock or (lambda: datetime.now(MOSCOW))

    @web.middleware
    async def security(request, handler):
        if request.path.startswith("/api/"):
            try:
                validate_init_data(request.headers.get("X-Telegram-Init-Data", ""), token)
            except (ValueError, TypeError, json.JSONDecodeError):
                return web.json_response(
                    {"error": "Открой миниап заново через кнопку в Telegram."}, status=401
                )
        try:
            response = await handler(request)
        except SourceError:
            response = web.json_response(
                {"error": "Сайт МГУ пока не отвечает. Попробуй ещё раз."}, status=503
            )
        except ValueError:
            response = web.json_response({"error": "Выбор устарел. Выбери группу заново."}, status=400)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store" if request.path.startswith("/api/") else "no-cache"
        return response

    async def options(request):
        refresh = request.query.get("refresh") == "1"
        faculty = request.query.get("faculty", "")
        course = request.query.get("course", "")
        faculties = await service.get_faculties(refresh=refresh)
        if not faculty:
            result = faculties
        else:
            if faculty not in {x.id for x in faculties}:
                raise ValueError("Unknown faculty")
            courses = await service.get_courses(faculty, refresh=refresh)
            if not course:
                result = courses
            else:
                if course not in {x.id for x in courses}:
                    raise ValueError("Unknown course")
                result = await service.get_groups(faculty, course, refresh=refresh)
        return web.json_response({"options": [asdict(x) for x in result]})

    async def schedule(request):
        q = request.query
        faculty, course, group = q.get("faculty", ""), q.get("course", ""), q.get("group", "")
        if any(not x or len(x) > 64 for x in (faculty, course, group)):
            raise ValueError("Missing selection")
        refresh = q.get("refresh") == "1"
        if faculty not in {x.id for x in await service.get_faculties(refresh=refresh)}:
            raise ValueError("Unknown faculty")
        if course not in {x.id for x in await service.get_courses(faculty, refresh=refresh)}:
            raise ValueError("Unknown course")
        groups = await service.get_groups(faculty, course, refresh=refresh)
        selected = next((x for x in groups if x.id == group), None)
        if selected is None:
            raise ValueError("Unknown group")
        now = clock().astimezone(MOSCOW)
        day = date.fromisoformat(q["date"]) if q.get("date") else now.date()
        if abs((day - now.date()).days) > 366:
            raise ValueError("Date outside range")
        result = await service.get_schedule(group, day, faculty, course, refresh=refresh)
        advanced = False
        if (
            not q.get("date")
            and result.lessons
            and now.time() >= max(time.fromisoformat(x.end_time) for x in result.lessons)
        ):
            day += timedelta(days=1)
            result = await service.get_schedule(group, day, faculty, course, refresh=refresh)
            advanced = True
        return web.json_response(
            {
                "date": day.isoformat(),
                "today": now.date().isoformat(),
                "now": now.isoformat(),
                "weekday": DAYS[day.weekday()],
                "label": f"{day.day} {MONTHS[day.month - 1]}",
                "group": asdict(selected),
                "lessons": [asdict(x) for x in result.lessons],
                "advanced": advanced,
            }
        )

    async def index(request):
        return web.FileResponse(STATIC / "index.html")

    async def health(request):
        return web.Response(text="ok")

    app = web.Application(middlewares=[security], client_max_size=16384)
    app.router.add_get("/", index)
    app.router.add_get("/healthz", health)
    app.router.add_get("/api/options", options)
    app.router.add_get("/api/schedule", schedule)
    app.router.add_static("/assets/", STATIC, show_index=False)
    return app
