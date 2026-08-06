import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot import constants
from app.bot import errors
from app.bot.handlers import build_router
from app.bot.middlewares import AccessMiddleware, DbSessionMiddleware
from app.bot.publisher import Publisher
from app.config import Settings

logger = logging.getLogger(__name__)

# Список для кнопки ☰ у клієнті Telegram. Основна навігація — inline-кнопки,
# але так команди теж можна вибрати зі списку, а не набирати вручну.
BOT_COMMANDS = [
    BotCommand(command="start", description="Головне меню"),
    *(
        [
            BotCommand(command="new", description="Нова заявка"),
            BotCommand(command="my", description="Мої заявки"),
        ]
        if constants.SHOW_APPLICATIONS
        else []
    ),
    BotCommand(command="cancel", description="Перервати заповнення"),
    BotCommand(command="help", description="Довідка"),
]


def create_bot(token: str) -> Bot:
    return Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


async def setup_bot_commands(bot: Bot) -> None:
    try:
        await bot.set_my_commands(BOT_COMMANDS)
    except TelegramAPIError:
        # Не критично: бот працює й без списку команд.
        logger.exception("Не вдалося встановити список команд")


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

    # Порядок важливий: AccessMiddleware читає сесію, яку кладе перша.
    dispatcher.update.middleware(DbSessionMiddleware(session_factory))
    dispatcher.update.middleware(AccessMiddleware(settings))
    dispatcher.include_router(build_router())
    # Останнім: він ловить те, що не спіймали хендлери вище.
    dispatcher.include_router(errors.router)
    dispatcher.startup.register(setup_bot_commands)
    return dispatcher
