from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.handlers import build_router
from app.bot.middlewares import DbSessionMiddleware
from app.bot.publisher import Publisher
from app.config import Settings


def create_bot(token: str) -> Bot:
    return Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


def create_dispatcher(
    session_factory: async_sessionmaker,
    publisher: Publisher,
    settings: Settings,
) -> Dispatcher:
    """MemoryStorage достатньо: незавершена анкета — короткоживучий стан,
    її втрата при рестарті не критична. Для кількох реплік знадобиться Redis."""
    dispatcher = Dispatcher(storage=MemoryStorage())

    # Кладемо в workflow data — aiogram підставить це в хендлери за іменем.
    dispatcher["publisher"] = publisher
    dispatcher["settings"] = settings

    dispatcher.update.middleware(DbSessionMiddleware(session_factory))
    dispatcher.include_router(build_router())
    return dispatcher
