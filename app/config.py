import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


@dataclass(frozen=True)
class Config:
    bot_token: str
    cache_enabled: bool = True

    @classmethod
    def load(cls):
        values = dotenv_values(ENV_PATH)

        token = (os.getenv("BOT_TOKEN") or values.get("BOT_TOKEN") or "").strip()

        if not token or token == "...":
            raise ValueError(
                "Добавьте BOT_TOKEN в .env или переменные окружения Bothost."
            )

        cache_value = (
            os.getenv("CACHE_ENABLED")
            or values.get("CACHE_ENABLED")
            or "true"
        )

        return cls(
            token,
            cache_value.lower() not in {"false", "0", "no"},
        )
