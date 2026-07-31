from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.access import resolve_access


class AccessMiddleware(BaseMiddleware):
    """Кладе в data готовий Access — щоб хендлери не повторювали запит ролі.

    Реєструється ПІСЛЯ DbSessionMiddleware: залежить від data["session"].
    """

    def __init__(self, settings) -> None:
        self._settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        session = data.get("session")
        if user is not None and session is not None:
            data["access"] = await resolve_access(session, self._settings, user.id)
        return await handler(event, data)


class DbSessionMiddleware(BaseMiddleware):
    """Кладе окрему AsyncSession у data кожного апдейту.

    Завдяки цьому хендлери не імпортують глобальну фабрику сесій,
    і в тестах можна підставити фабрику на in-memory БД.
    """

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self._session_factory() as session:
            data["session"] = session
            return await handler(event, data)
