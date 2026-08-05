import logging
from typing import Protocol

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError

from app.bot.formatting import format_for_group
from app.models import Application

logger = logging.getLogger(__name__)


class Publisher(Protocol):
    """Абстракція над відправкою в Telegram — щоб тести не ходили в мережу."""

    async def publish(self, application: Application) -> tuple[int, int] | None:
        """Повертає (chat_id, message_id) або None, якщо публікація не вдалась."""

    async def retract(
        self, chat_id: int, message_id: int, *, note: str | None = None
    ) -> None:
        """Прибрати опубліковане повідомлення (best-effort)."""

    async def send(self, chat_id: int, text: str) -> int | None:
        """Надіслати текст у довільний чат: робочий чат компанії або приватний
        чат водія. Повертає message_id або None, якщо не дійшло."""


class TelegramPublisher:
    def __init__(self, bot: Bot, chat_id: int | None) -> None:
        self._bot = bot
        self._chat_id = chat_id

    async def send(self, chat_id: int, text: str) -> int | None:
        try:
            message = await self._bot.send_message(chat_id, text)
        except TelegramForbiddenError:
            # Найчастіший випадок, і не помилка як така: людина не натискала
            # /start або заблокувала бота, або бота прибрали з чату. Telegram
            # не дозволяє писати першим — тут нічого не зробиш кодом.
            logger.warning("Немає доступу до чату %s — повідомлення не надіслано", chat_id)
            return None
        except TelegramAPIError:
            logger.exception("Не вдалося надіслати повідомлення в чат %s", chat_id)
            return None
        return message.message_id

    async def publish(self, application: Application) -> tuple[int, int] | None:
        if self._chat_id is None:
            logger.warning("TELEGRAM_GROUP_CHAT_ID не задано — публікацію пропущено")
            return None
        try:
            message = await self._bot.send_message(
                self._chat_id, format_for_group(application)
            )
        except TelegramAPIError:
            # Заявка вже збережена в БД — збій публікації не має її втрачати.
            logger.exception("Не вдалося опублікувати заявку #%s", application.id)
            return None
        return self._chat_id, message.message_id

    async def retract(
        self, chat_id: int, message_id: int, *, note: str | None = None
    ) -> None:
        """Telegram дозволяє боту видаляти повідомлення в групі лише ~48 годин.
        Після цього вікна відкочуємось на редагування тексту."""
        try:
            await self._bot.delete_message(chat_id, message_id)
            return
        except TelegramAPIError:
            logger.info("delete_message не вдався, пробуємо edit_message_text")

        try:
            await self._bot.edit_message_text(
                note or "🗑 <i>Заявку видалено.</i>",
                chat_id=chat_id,
                message_id=message_id,
            )
        except TelegramAPIError:
            logger.exception("Не вдалося прибрати повідомлення %s", message_id)


class NullPublisher:
    """Використовується, коли бот вимкнено (RUN_BOT=false), — API має
    працювати без піднятого бота."""

    async def publish(self, application: Application) -> tuple[int, int] | None:
        return None

    async def retract(
        self, chat_id: int, message_id: int, *, note: str | None = None
    ) -> None:
        return None

    async def send(self, chat_id: int, text: str) -> int | None:
        return None
