"""Тести обробника падінь.

Перевіряємо дві речі, яких раніше не було зовсім: людина отримує відповідь
замість мовчання, а адмін — traceback замість необхідності лізти в консоль.
"""

import pytest
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import ErrorEvent, Update

from app.bot.errors import APOLOGY, on_error
from tests.conftest import ADMIN_ID, OWNER_ID


class FakeBot:
    """Записує надіслане. `refuse` — чати, які «заблокували бота»."""

    def __init__(self, refuse: set[int] | None = None) -> None:
        self.sent: list[tuple[int, str]] = []
        self.refuse = refuse or set()

    async def send_message(self, chat_id: int, text: str, **_kwargs) -> None:
        if chat_id in self.refuse:
            raise TelegramForbiddenError(method=None, message="blocked")
        self.sent.append((chat_id, text))


def _callback_update(data: str = "menu:trips") -> Update:
    return Update.model_validate(
        {
            "update_id": 1,
            "callback_query": {
                "id": "1",
                "from": {"id": OWNER_ID, "is_bot": False, "first_name": "Тест"},
                "chat_instance": "1",
                "data": data,
                "message": {
                    "message_id": 10,
                    "date": 0,
                    "chat": {"id": OWNER_ID, "type": "private"},
                },
            },
        }
    )


def _message_update(text: str = "привіт") -> Update:
    return Update.model_validate(
        {
            "update_id": 2,
            "message": {
                "message_id": 11,
                "date": 0,
                "text": text,
                "chat": {"id": OWNER_ID, "type": "private"},
                "from": {"id": OWNER_ID, "is_bot": False, "first_name": "Тест"},
            },
        }
    )


def _event(update: Update, exception: Exception) -> ErrorEvent:
    return ErrorEvent(update=update, exception=exception)


async def test_user_gets_an_answer_instead_of_silence(settings):
    bot = FakeBot()

    await on_error(_event(_callback_update(), ValueError("бум")), bot, settings)

    assert (OWNER_ID, APOLOGY) in bot.sent


async def test_admin_gets_the_traceback(settings):
    """Раніше єдиним способом дізнатись про збій було побачити його в консолі."""
    bot = FakeBot()

    await on_error(_event(_callback_update("trip:show:7"), KeyError("driver")), bot, settings)

    report = dict(bot.sent)[ADMIN_ID]
    assert "KeyError" in report
    assert "trip:show:7" in report
    assert str(OWNER_ID) in report


async def test_a_text_message_is_reported_too(settings):
    bot = FakeBot()

    await on_error(_event(_message_update("28,5 тонни"), TypeError("ой")), bot, settings)

    report = dict(bot.sent)[ADMIN_ID]
    assert "28,5 тонни" in report
    assert "TypeError" in report


async def test_a_blocked_user_does_not_break_the_report(settings):
    """Збій вибачення не має з'їдати доповідь: саме тоді вона й потрібна."""
    bot = FakeBot(refuse={OWNER_ID})

    await on_error(_event(_callback_update(), ValueError("бум")), bot, settings)

    assert dict(bot.sent).keys() == {ADMIN_ID}


async def test_an_unreachable_admin_does_not_raise(settings):
    """Обробник падінь, який падає сам, лишає користувача без відповіді
    і не пише нікому."""
    bot = FakeBot(refuse={ADMIN_ID})

    await on_error(_event(_callback_update(), ValueError("бум")), bot, settings)

    assert bot.sent == [(OWNER_ID, APOLOGY)]


@pytest.mark.parametrize("update", [Update(update_id=3)])
async def test_an_update_without_a_chat_is_only_reported(update, settings):
    """Нікому відповідати — але доповісти все одно треба."""
    bot = FakeBot()

    await on_error(_event(update, RuntimeError("нізвідки")), bot, settings)

    assert dict(bot.sent).keys() == {ADMIN_ID}
