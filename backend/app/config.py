import os
from functools import lru_cache
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def env_file_for(app_env: str | None = None) -> str:
    """Обирає файл конфігурації за APP_ENV.

    APP_ENV не заданий → `.env`      (робочий бот, робоча БД, робоча група)
    APP_ENV=test       → `.env.test` (тестовий бот, окрема БД, окрема група)

    Так одна кодова база обслуговує два повністю ізольовані інстанси, і
    тестування ніяк не торкається робочого бота.
    """
    suffix = (app_env if app_env is not None else os.getenv("APP_ENV", "")).strip()
    return f".env.{suffix}" if suffix else ".env"


class Settings(BaseSettings):
    """Конфігурація сервісу. Читається з backend/.env* та змінних оточення."""

    model_config = SettingsConfigDict(
        env_file=env_file_for(),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Порожній рядок = робочий інстанс. Використовується лише для логів,
    # вибір файлу конфігурації робить env_file_for() ще до створення Settings.
    app_env: str = ""

    telegram_bot_token: str = ""
    telegram_group_chat_id: int | None = None
    admin_api_token: str = ""
    database_url: str = "sqlite+aiosqlite:///./applications.db"
    run_bot: bool = True

    # Списки тримаємо рядками: pydantic-settings за замовчуванням розбирає
    # складені типи як JSON, і "1,2" з .env впало б із помилкою парсингу.
    admin_telegram_ids: str = ""
    cors_origins: str = "http://localhost:3000"

    # .env.example ships with blank values, and copying it must not crash the
    # app. pydantic would otherwise try to parse "" as int/bool and fail.
    @field_validator("telegram_group_chat_id", mode="before")
    @classmethod
    def _blank_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("run_bot", mode="before")
    @classmethod
    def _blank_to_true(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return True
        return value

    @property
    def admin_ids(self) -> set[int]:
        ids: set[int] = set()
        for part in self.admin_telegram_ids.split(","):
            part = part.strip()
            if part:
                ids.add(int(part))
        return ids

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def is_admin(self, telegram_user_id: int) -> bool:
        return telegram_user_id in self.admin_ids

    @property
    def env_label(self) -> str:
        return self.app_env or "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()
