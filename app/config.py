import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


@dataclass(frozen=True)
class Config:
    bot_token: str
    cache_enabled: bool = True
    widgets_enabled: bool = False
    mini_app_url: str = ""
    mini_app_enabled: bool = True
    port: int = 8080

    @classmethod
    def load(cls):
        values = dotenv_values(ENV_PATH)
        # Hosting platforms inject secrets as process environment variables;
        # local development can still use the .env file.
        token = (os.getenv("BOT_TOKEN") or values.get("BOT_TOKEN") or "").strip()
        if not token or token == "...":
            raise ValueError("Добавьте BOT_TOKEN в .env (см. .env.example и README.md).")
        cache_value = os.getenv("CACHE_ENABLED") or values.get("CACHE_ENABLED") or "true"
        widget_value = os.getenv("WIDGETS_ENABLED") or values.get("WIDGETS_ENABLED") or "false"
        app_url = (os.getenv("MINI_APP_URL") or values.get("MINI_APP_URL") or "").strip()
        if app_url and (
            urlsplit(app_url).scheme != "https"
            or not urlsplit(app_url).hostname
            or urlsplit(app_url).username
        ):
            raise ValueError("MINI_APP_URL должен быть публичным HTTPS-адресом приложения.")
        port = int(os.getenv("PORT") or values.get("PORT") or "8080")
        if not 1 <= port <= 65535:
            raise ValueError("PORT должен быть от 1 до 65535.")
        app_enabled = os.getenv("MINI_APP_ENABLED") or values.get("MINI_APP_ENABLED") or "true"
        return cls(
            token,
            cache_value.lower() not in {"false", "0", "no"},
            widget_value.lower() not in {"false", "0", "no"},
            app_url,
            app_enabled.lower() not in {"false", "0", "no"},
            port,
        )
