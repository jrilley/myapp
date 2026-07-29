import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.applications import router as applications_router
from app.bot.bot import create_bot, create_dispatcher
from app.bot.publisher import NullPublisher, TelegramPublisher
from app.config import env_file_for, get_settings
from app.db import SessionFactory

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Бот і API живуть в одному процесі та в одному event loop.

    Причина — SQLite: у неї один writer, і два окремі процеси регулярно
    ловили б `database is locked`. Плюс це один юніт деплою.
    """
    settings = get_settings()
    bot = None
    polling_task = None

    # Явно друкуємо, який саме інстанс піднявся: переплутати робочого бота
    # з тестовим — найдорожча помилка в цій схемі.
    logger.warning(
        "Інстанс: %s | конфіг: %s | БД: %s | група: %s",
        settings.env_label,
        env_file_for(),
        settings.database_url,
        settings.telegram_group_chat_id,
    )

    if settings.run_bot and settings.telegram_bot_token:
        bot = create_bot(settings.telegram_bot_token)
        publisher = TelegramPublisher(bot, settings.telegram_group_chat_id)
        dispatcher = create_dispatcher(SessionFactory, publisher, settings)
        polling_task = asyncio.create_task(dispatcher.start_polling(bot))
        logger.info("Telegram-бот запущено (polling)")
    else:
        publisher = NullPublisher()
        logger.warning(
            "Бот вимкнено (RUN_BOT=false або порожній TELEGRAM_BOT_TOKEN) — "
            "працює лише API"
        )

    app.state.publisher = publisher

    try:
        yield
    finally:
        if polling_task is not None:
            polling_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await polling_task
        if bot is not None:
            await bot.session.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="myapp — заявки з Telegram", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "DELETE", "OPTIONS"],
        allow_headers=["X-Admin-Token", "Content-Type"],
    )
    app.include_router(applications_router)
    return app


app = create_app()
