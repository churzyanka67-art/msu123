import asyncio
import logging
from weakref import WeakValueDictionary

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.controller import StaleCallback
from app.storage import StateStore

log = logging.getLogger(__name__)


class FlowHandlers:
    def __init__(self, controller, store: StateStore):
        self.controller, self.store = controller, store
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
                sent = await bot.send_message(message.chat.id, screen.text, reply_markup=screen.keyboard)
            except TelegramAPIError as exc:
                log.warning("Telegram start failed: %s", type(exc).__name__)
                return
            screen.message_id = sent.message_id
            await self.store.set(key, screen)

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
                log.warning("Telegram edit failed: %s", type(exc).__name__)
                return
            next_screen.message_id = screen.message_id
            await self.store.set(key, next_screen)


def create_router(controller, store):
    handlers = FlowHandlers(controller, store)
    router = Router(name="schedule")
    router.message.register(handlers.start, CommandStart())
    router.callback_query.register(handlers.callback)
    return router
