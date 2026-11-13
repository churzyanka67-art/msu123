import asyncio
import logging
import sys

import httpx
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.types import MenuButtonWebApp, WebAppInfo
from aiogram.utils.token import TokenValidationError
from aiohttp import web

from app.config import Config
from app.controller import Controller
from app.handlers.flow import FlowHandlers, create_router
from app.miniapp.server import create_app
from app.services.msu_schedule import MsuScheduleService
from app.storage import MemoryStore


async def run(config: Config):
    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    runner = None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=10), follow_redirects=True) as client:
            service = MsuScheduleService(client, cache_enabled=config.cache_enabled)
            if config.mini_app_enabled:
                runner = web.AppRunner(create_app(service, config.bot_token), access_log=None)
                await runner.setup()
                await web.TCPSite(runner, "0.0.0.0", config.port).start()
                logging.getLogger(__name__).info("Mini App server listening on port %s", config.port)
            if config.mini_app_url:
                await bot.set_chat_menu_button(
                    menu_button=MenuButtonWebApp(
                        text="Расписание", web_app=WebAppInfo(url=config.mini_app_url)
                    )
                )
            dispatcher = Dispatcher()
            controller = Controller(service, widgets=config.widgets_enabled)
            store = MemoryStore()
            handlers = FlowHandlers(
                controller, store, widgets=config.widgets_enabled, mini_app_url=config.mini_app_url
            )
            dispatcher.include_router(create_router(controller, store, handlers=handlers))
            dispatcher.update.outer_middleware(handlers.widget_update)
            updates = ["message", "callback_query"]
            if config.widgets_enabled:
                updates.append("widget_query")
            await dispatcher.start_polling(bot, close_bot_session=False, allowed_updates=updates)
    finally:
        if runner:
            await runner.cleanup()
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
    except TelegramUnauthorizedError:
        logging.getLogger(__name__).error(
            "Telegram отклонил BOT_TOKEN (401). Обновите токен в локальном .env или переменных окружения."
        )
        return 1
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
