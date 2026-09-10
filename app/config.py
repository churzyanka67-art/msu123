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
        token = (values.get("BOT_TOKEN") or "").strip()
        if not token or token == "...":
            raise ValueError("Добавьте BOT_TOKEN в .env (см. .env.example и README.md).")
        return cls(token, (values.get("CACHE_ENABLED") or "true").lower() not in {"false", "0", "no"})
