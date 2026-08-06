import logging
from typing import NamedTuple, Protocol

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramMigrateToChat,
)

from app.bot.formatting import format_for_group
from app.models import Application

logger = logging.getLogger(__name__)


class Sent(NamedTuple):
    """Результат надсилання.

    `chat_id` повертаємо разом із message_id, бо він може відрізнятись від
    того, що просили: коли звичайна група стає супергрупою, Telegram міняє їй
    id. Хто зберігає посилання на чат, має дізнатись про це — інакше кожне
    наступне надсилання йтиме на мертвий id.
    """

    message_id: int
    chat_id: int


class Publisher(Protocol):
    """Абстракція над відправкою в Telegram — щоб тести не ходили в мережу."""

    async def publish(self, application: Application) -> tuple[int, int] | None:
        """Повертає (chat_id, message_id) або None, якщо публікація не вдалась."""

    async def retract(
        self, chat_id: int, message_id: int, *, note: str | None = None
    ) -> None:
        """Прибрати опубліковане повідомлення (best-effort)."""

    async def send(self, chat_id: int, text: str) -> Sent | None:
        """Надіслати текст у довільний чат: робочий чат компанії або приватний
        чат водія. None — якщо не дійшло."""

    async def edit(self, chat_id: int, message_id: int, text: str) -> bool:
        """Перемалювати вже надіслане повідомлення. False — не вдалося."""


class TelegramPublisher:
    def __init__(self, bot: Bot, chat_id: int | None) -> None:
        self._bot = bot
        self._chat_id = chat_id

    async def send(self, chat_id: int, text: str) -> Sent | None:
        try:
            message = await self._bot.send_message(chat_id, text)
        except TelegramMigrateToChat as exc:
            # Звичайна група стала супергрупою — Telegram видав їй новий id і
            # каже, який саме. Старий мертвий назавжди, тож повторюємо один
            # раз і віддаємо новий id викликачу, щоб той його зберіг.
            #
            # Гілка має бути ПЕРЕД TelegramAPIError: це його підклас.
            logger.warning("Чат %s мігрував у %s", chat_id, exc.migrate_to_chat_id)
            return await self._send_once(exc.migrate_to_chat_id, text)
        except TelegramForbiddenError:
            # Найчастіший випадок, і не помилка як така: людина не натискала
            # /start або заблокувала бота, або бота прибрали з чату. Telegram
            # не дозволяє писати першим — тут нічого не зробиш кодом.
            logger.warning("Немає доступу до чату %s — повідомлення не надіслано", chat_id)
            return None
        except TelegramAPIError:
            logger.exception("Не вдалося надіслати повідомлення в чат %s", chat_id)
            return None
        return Sent(message.message_id, chat_id)

    async def _send_once(self, chat_id: int, text: str) -> Sent | None:
        """Повторна спроба після міграції. Без рекурсії: двічі поспіль
        мігрувати чат не може, а нескінченний цикл — може."""
        try:
            message = await self._bot.send_message(chat_id, text)
        except TelegramAPIError:
            logger.exception("Не вдалося надіслати повідомлення в чат %s", chat_id)
            return None
        return Sent(message.message_id, chat_id)

    async def edit(self, chat_id: int, message_id: int, text: str) -> bool:
        """Перемалювати повідомлення на місці — так рейс у робочому чаті
        показує себе теперішнього, а не свою першу версію.

        «message is not modified» помилкою не рахуємо: текст просто не
        змінився, і для викликача це той самий успіх. Гілка має бути ПЕРЕД
        TelegramAPIError: TelegramBadRequest — його підклас.
        """
        try:
            await self._bot.edit_message_text(
                text, chat_id=chat_id, message_id=message_id
            )
        except TelegramBadRequest as exc:
            if "not modified" in str(exc):
                return True
            logger.warning("Не вдалося оновити повідомлення %s: %s", message_id, exc)
            return False
        except TelegramAPIError:
            logger.exception("Не вдалося оновити повідомлення %s", message_id)
            return False
        return True

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

    async def send(self, chat_id: int, text: str) -> Sent | None:
        return None

    async def edit(self, chat_id: int, message_id: int, text: str) -> bool:
        return False
