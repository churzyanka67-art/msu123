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
        # Hosting platforms inject secrets as process environment variables;
        # local development can still use the .env file.
        token = (os.getenv("8907926808:AAH37fC1LFwbzr67rAaAdkM7IZXYsCmVkcE") or values.get("8907926808:AAH37fC1LFwbzr67rAaAdkM7IZXYsCmVkcE") or "").strip()
        if not token or token == "8907926808:AAH37fC1LFwbzr67rAaAdkM7IZXYsCmVkcE":
            raise ValueError("Добавьте BOT_TOKEN в .env (см. .env.example и README.md).")
        cache_value = os.getenv("CACHE_ENABLED") or values.get("CACHE_ENABLED") or "true"
        return cls(token, cache_value.lower() not in {"false", "0", "no"})
