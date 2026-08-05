"""Тести адаптера до Telegram.

Мережі тут немає: підставляємо об'єкт із одним методом send_message і
перевіряємо, як публікатор поводиться з помилками, які Telegram присилає
насправді.
"""

import pytest
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramMigrateToChat,
)

from app.bot.publisher import TelegramPublisher

OLD_CHAT = -5162228105
NEW_CHAT = -1004380122313


class FakeMethod:
    """Мінімум, який читають конструктори винятків aiogram."""

    def __init__(self, chat_id: int) -> None:
        self.chat_id = chat_id


class FakeSentMessage:
    def __init__(self, message_id: int) -> None:
        self.message_id = message_id


class FakeBot:
    """Кидає задані винятки за викликами по черзі, решту — надсилає."""

    def __init__(self, *, errors: dict[int, Exception] | None = None) -> None:
        self.errors = errors or {}
        self.calls: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> FakeSentMessage:
        self.calls.append((chat_id, text))
        error = self.errors.pop(chat_id, None)
        if error is not None:
            raise error
        return FakeSentMessage(555)


def _migrated() -> TelegramMigrateToChat:
    return TelegramMigrateToChat(
        method=FakeMethod(OLD_CHAT),
        message="Bad Request: group chat was upgraded to a supergroup chat",
        migrate_to_chat_id=NEW_CHAT,
    )


async def test_send_returns_the_chat_it_actually_used():
    bot = FakeBot()
    publisher = TelegramPublisher(bot, None)

    sent = await publisher.send(OLD_CHAT, "текст")

    assert sent == (555, OLD_CHAT)


async def test_migration_is_retried_against_the_new_chat():
    """Звичайна група стає супергрупою — Telegram міняє їй id і каже, який.
    Старий мертвий назавжди, тож повторюємо туди, куди сказали."""
    bot = FakeBot(errors={OLD_CHAT: _migrated()})
    publisher = TelegramPublisher(bot, None)

    sent = await publisher.send(OLD_CHAT, "текст")

    assert sent == (555, NEW_CHAT)
    assert [chat for chat, _ in bot.calls] == [OLD_CHAT, NEW_CHAT]


async def test_migration_is_caught_before_the_generic_error():
    """TelegramMigrateToChat — підклас TelegramAPIError, тож порядок гілок
    у send має значення: інакше міграцію проковтне загальний except."""
    assert issubclass(TelegramMigrateToChat, Exception)
    bot = FakeBot(errors={OLD_CHAT: _migrated()})

    sent = await TelegramPublisher(bot, None).send(OLD_CHAT, "текст")

    assert sent is not None


async def test_second_failure_after_migration_gives_up():
    """Без рекурсії: двічі поспіль чат мігрувати не може, а цикл — може."""
    bot = FakeBot(
        errors={
            OLD_CHAT: _migrated(),
            NEW_CHAT: TelegramBadRequest(
                method=FakeMethod(NEW_CHAT), message="chat not found"
            ),
        }
    )

    sent = await TelegramPublisher(bot, None).send(OLD_CHAT, "текст")

    assert sent is None
    assert len(bot.calls) == 2


@pytest.mark.parametrize(
    "error",
    [
        TelegramForbiddenError(method=FakeMethod(OLD_CHAT), message="bot was blocked"),
        TelegramBadRequest(method=FakeMethod(OLD_CHAT), message="chat not found"),
    ],
)
async def test_delivery_failure_is_swallowed(error):
    """Рейс уже в базі — збій розсилки не має долітати винятком до хендлера."""
    bot = FakeBot(errors={OLD_CHAT: error})

    assert await TelegramPublisher(bot, None).send(OLD_CHAT, "текст") is None
