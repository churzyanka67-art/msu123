import asyncio
import json
import logging
import re
from html import escape
from weakref import WeakValueDictionary

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from pydantic import ValidationError

from app.controller import StaleCallback
from app.storage import StateStore
from app.widgets.api import AnswerWidgetQuery, EditMessageWidgetData, SendWidget, WidgetQuery
from app.widgets.presentation import state_fields, widget_html

log = logging.getLogger(__name__)


def api_error_details(exc):
    """Log the API's description, never the method payload or a token in a URL."""
    description = re.sub(r"\d{5,}:[A-Za-z0-9_-]+", "[REDACTED]", exc.message)
    description = description.replace("\r", " ").replace("\n", " ")
    return f"{exc.method.__api_method__} / {type(exc).__name__}: {description[:1000]}"


class FlowHandlers:
    def __init__(self, controller, store: StateStore, *, widgets=False):
        self.controller, self.store = controller, store
        self.widgets = widgets
        self._locks = WeakValueDictionary()

    def _lock(self, key):
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    async def start(self, message: Message, bot: Bot):
        if message.from_user is None:
            return
        key = (message.chat.id, message.from_user.id)
        async with self._lock(key):
            screen = await self.controller.start()
            try:
                if self.widgets and message.chat.type == "private":
                    sent = await bot(
                        SendWidget(chat_id=message.chat.id, html=widget_html(), **state_fields(screen))
                    )
                else:
                    if self.widgets:
                        await bot.send_message(
                            message.chat.id, "Виджеты доступны в личке. Откройте бота и отправьте /start."
                        )
                        return
                    sent = await bot.send_message(message.chat.id, screen.text, reply_markup=screen.keyboard)
            except TelegramAPIError as exc:
                log.warning("Telegram start failed: %s", api_error_details(exc))
                if self.widgets and "INPUT_MEDIA_WIDGET_NOT_ALLOWED" in exc.message:
                    try:
                        await bot.send_message(
                            message.chat.id,
                            "Telegram отклонил виджет: INPUT_MEDIA_WIDGET_NOT_ALLOWED.\n"
                            "Для проверки минимального виджета отправь /widget_test.",
                        )
                    except TelegramAPIError as notice_error:
                        log.warning("Widget error notice failed: %s", api_error_details(notice_error))
                return
            screen.message_id = sent.message_id
            await self.store.set(key, screen)

    async def widget_test(self, message: Message, bot: Bot):
        """A minimal, static private-chat probe, independent of the schedule UI."""
        if message.from_user is None:
            return
        if message.chat.type != "private" or message.chat.id != message.from_user.id:
            await bot.send_message(message.chat.id, "Проверку виджетов нужно запускать в личке с ботом.")
            return
        try:
            await bot(
                SendWidget(
                    chat_id=message.chat.id,
                    html="<p>Проверка виджета ФГУ</p>",
                    allow_queries=False,
                    caption="Минимальный тест: без CSS, JavaScript, состояния и запросов",
                )
            )
        except TelegramAPIError as exc:
            details = api_error_details(exc)
            log.warning("Minimal widget probe failed: chat_type=private; %s", details)
            await bot.send_message(
                message.chat.id,
                "Минимальный виджет тоже отклонён. Ответ Telegram:\n"
                f"<code>{escape(details)}</code>\n"
                "Передай этот ответ для диагностики. Активное расписание сохранено.",
            )
            return
        log.info("Minimal widget probe succeeded: chat_type=private")
        await bot.send_message(
            message.chat.id,
            "Минимальный виджет отправлен. Значит, базовая отправка в эту личку разрешена; "
            "дальше проверим данные и интерактивность основной карточки.",
        )

    async def widget_update(self, handler, event, data):
        """Intercept the new update before aiogram's older event-type resolver."""
        raw = (event.model_extra or {}).get("widget_query")
        if raw is None:
            return await handler(event, data)
        if not self.widgets:
            return None
        try:
            query = WidgetQuery.model_validate(raw)
        except ValidationError:
            log.warning("Unsupported widget query context")
            return None
        await self.widget_query(query, data["bot"])
        return None

    async def widget_query(self, query, bot):
        key = (query.chat.id, query.from_user.id)
        if query.chat.type != "private" or key[0] != key[1]:
            await bot(
                AnswerWidgetQuery(
                    widget_query_id=query.id, data=json.dumps({"error": "Откройте бота в личке."})
                )
            )
            return
        # Answer before the site request (which can take longer than Telegram's 15s limit).
        # The UI waits for the pushed state after this acknowledgement.
        async with self._lock(key):
            screen = await self.store.get(key)
            if screen is None or screen.message_id != query.message_id or query.data not in screen.actions:
                await bot(
                    AnswerWidgetQuery(
                        widget_query_id=query.id, data=json.dumps({"error": "Экран устарел. Отправь /start."})
                    )
                )
                return
            try:
                await bot(AnswerWidgetQuery(widget_query_id=query.id))
                next_screen = await self.controller.act(screen, query.data)
                await bot(
                    EditMessageWidgetData(
                        chat_id=key[0], message_id=screen.message_id, **state_fields(next_screen)
                    )
                )
            except StaleCallback:
                return
            except TelegramAPIError as exc:
                log.warning("Telegram widget update failed: %s", api_error_details(exc))
                return
            next_screen.message_id = screen.message_id
            await self.store.set(key, next_screen)

    async def callback(self, query: CallbackQuery, bot: Bot):
        if not isinstance(query.message, Message):
            await bot.answer_callback_query(query.id, text="Откройте бота и отправьте /start.")
            return
        key = (query.message.chat.id, query.from_user.id)
        async with self._lock(key):
            screen = await self.store.get(key)
            if (
                screen is None
                or screen.message_id != query.message.message_id
                or query.data not in screen.actions
            ):
                await bot.answer_callback_query(
                    query.id, text="Кнопка устарела. Используйте последний экран или /start.", show_alert=True
                )
                return
            # Acknowledge before site requests so Telegram's spinner stops promptly.
            try:
                await bot.answer_callback_query(query.id)
            except TelegramAPIError:
                return
            try:
                next_screen = await self.controller.act(screen, query.data)
                await bot.edit_message_text(
                    chat_id=key[0],
                    message_id=screen.message_id,
                    text=next_screen.text,
                    reply_markup=next_screen.keyboard,
                )
            except StaleCallback:
                return
            except TelegramAPIError as exc:
                # Preserve the previous actions when the edit fails; another click can retry.
                log.warning("Telegram edit failed: %s", api_error_details(exc))
                return
            next_screen.message_id = screen.message_id
            await self.store.set(key, next_screen)


def create_router(controller, store, *, handlers=None):
    handlers = handlers or FlowHandlers(controller, store)
    router = Router(name="schedule")
    router.message.register(handlers.start, CommandStart())
    router.message.register(handlers.widget_test, Command("widget_test"))
    router.callback_query.register(handlers.callback)
    return router
