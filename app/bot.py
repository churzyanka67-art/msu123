import asyncio
import logging
import sys

import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.utils.token import TokenValidationError

from app.config import Config
from app.controller import Controller
from app.handlers.flow import FlowHandlers, create_router
from app.services.msu_schedule import MsuScheduleService
from app.storage import MemoryStore


async def run(config: Config):
    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=10), follow_redirects=True) as client:
            service = MsuScheduleService(client, cache_enabled=config.cache_enabled)
            dispatcher = Dispatcher()
            controller = Controller(service, widgets=config.widgets_enabled)
            store = MemoryStore()
            handlers = FlowHandlers(controller, store, widgets=config.widgets_enabled)
            dispatcher.include_router(create_router(controller, store, handlers=handlers))
            dispatcher.update.outer_middleware(handlers.widget_update)
            updates = ["message", "callback_query"]
            if config.widgets_enabled:
                updates.append("widget_query")
            await dispatcher.start_polling(bot, close_bot_session=False, allowed_updates=updates)
    finally:
        await bot.session.close()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        config = Config.load()
        asyncio.run(run(config))
    except (ValueError, TokenValidationError) as exc:
        # TokenValidationError may contain input; never print the supplied token.
        logging.getLogger(__name__).error(
            "Проверьте BOT_TOKEN в локальном .env." if isinstance(exc, TokenValidationError) else str(exc)
        )
        return 1
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
