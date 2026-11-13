"""Run the web server separately from Telegram polling: python -m app.miniapp."""

import httpx
from aiohttp import web

from app.config import Config
from app.miniapp.server import create_app
from app.services.msu_schedule import MsuScheduleService


def main():
    config = Config.load()
    client = httpx.AsyncClient(timeout=httpx.Timeout(20, connect=10), follow_redirects=True)
    app = create_app(MsuScheduleService(client, cache_enabled=config.cache_enabled), config.bot_token)

    async def cleanup(app):
        await client.aclose()

    app.on_cleanup.append(cleanup)
    web.run_app(app, host="0.0.0.0", port=config.port, access_log=None)


if __name__ == "__main__":
    main()
