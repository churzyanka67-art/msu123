"""Generate browser previews using saved real source responses, without a token."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from app.widgets.presentation import state_fields, widget_html

from app.controller import Controller, Selection
from app.models.schedule import Option
from app.services.parser import parse_options, parse_schedule

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures"


async def main():
    output = ROOT / "preview"
    output.mkdir(exist_ok=True)
    now = datetime(2026, 9, 9, 8, tzinfo=ZoneInfo("Europe/Moscow"))
    service = AsyncMock()
    service.get_groups.return_value = parse_options((FIXTURES / "groups.html").read_text(), "groupid")
    service.get_schedule.return_value = parse_schedule((FIXTURES / "day.html").read_text(), now.date())
    controller = Controller(service, widgets=True, today=lambda: now.date(), now=lambda: now)
    state = Selection(Option("5", "Бакалавриат"), Option("1", "1"), view="groups")
    group_screen = await controller._render(state)
    group = service.get_groups.return_value[0]
    day_screen = await controller._transition(state, ("group", group))
    for name, screen in [("groups", group_screen), ("day", day_screen)]:
        fields = json.dumps(state_fields(screen), ensure_ascii=False).replace("<", "\\u003c")
        shim = """<script>
const previewFields=FIELDS;
window.TelegramWidget={chatData:previewFields.chat_data,publicData:previewFields.public_data,
onEvent(){},ready(){},request(){return Promise.resolve({result:JSON.stringify({error:'Это предпросмотр. Кнопки работают в Telegram.'})})}};
</script>""".replace("FIELDS", fields)
        html = widget_html().replace("<script>", shim + "<script>", 1)
        (output / f"{name}.html").write_text(html, encoding="utf-8")
    (output / "index.html").write_text(
        '<!doctype html><html lang="ru"><meta charset="utf-8"><title>Расписание ФГУ · Виджеты</title>'
        "<style>body{background:#ececf0;color:#18181b;font:16px system-ui;margin:40px}"
        "h1{font-size:34px}p{color:#71717a}.cards{display:flex;gap:28px;flex-wrap:wrap}"
        "iframe{border:0;border-radius:28px;width:390px;height:600px;background:#000}"
        "h2{font-size:14px;color:#71717a}</style><h1>Расписание. Ничего лишнего.</h1>"
        "<p>Предпросмотр на сохранённых данных сайта от 9 сентября 2026 года.</p>"
        '<div class="cards"><section><h2>МОЯ ГРУППА</h2><iframe src="groups.html" style="height:457px"></iframe></section>'
        '<section><h2>РАСПИСАНИЕ НА ДЕНЬ</h2><iframe src="day.html" style="height:561px"></iframe></section></div></html>',
        encoding="utf-8",
    )
    print(output / "index.html")


if __name__ == "__main__":
    asyncio.run(main())
