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
from app.handlers.flow import create_router
from app.services.msu_schedule import MsuScheduleService
from app.storage import MemoryStore


async def run(config: Config):
    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=10), follow_redirects=True) as client:
            service = MsuScheduleService(client, cache_enabled=config.cache_enabled)
            dispatcher = Dispatcher()
            dispatcher.include_router(create_router(Controller(service), MemoryStore()))
            await dispatcher.start_polling(bot, close_bot_session=False)
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
