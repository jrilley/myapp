"""Тести inline-меню.

Мета меню — щоб користувач не набирав команд: усе, що він робить,
має бути досяжним натисканням кнопки.
"""

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app import repository
from app.bot.constants import CATEGORIES
from app.bot.handlers.common import cmd_start, on_back, on_delete, on_help, on_my
from app.bot.handlers.form import on_cancel, on_menu_new, step_contact, step_full_name
from app.bot.keyboards import (
    DELETE_PREFIX,
    FORM_CANCEL,
    MENU_BACK,
    MENU_HELP,
    MENU_MY,
    MENU_NEW,
)
from app.bot.states import ApplicationForm
from tests.conftest import (
    OWNER_ID,
    STRANGER_ID,
    FakeCallback,
    FakeMessage,
    FakeUser,
    callback_data,
)


@pytest.fixture
def state() -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=OWNER_ID)
    )


async def _make(session, **overrides):
    payload = {
        "telegram_user_id": OWNER_ID,
        "telegram_username": "tester",
        "full_name": "Іван Петренко",
        "contact": "+380000000000",
        "category": CATEGORIES[0],
        "description": "Опис заявки для тесту",
    }
    payload.update(overrides)
    return await repository.create_application(session, **payload)


async def test_start_shows_menu_instead_of_bare_text(state):
    message = FakeMessage()

    await cmd_start(message, state)

    assert callback_data(message.markups[0]) == [MENU_NEW, MENU_MY, MENU_HELP]


async def test_menu_button_starts_the_form(state):
    callback = FakeCallback(MENU_NEW)

    await on_menu_new(callback, state)

    assert await state.get_state() == ApplicationForm.full_name
    # Під першим питанням має бути вихід, щоб не довелось друкувати /cancel.
    assert callback_data(callback.message.markups[0]) == [FORM_CANCEL]


async def test_cancel_button_works_from_any_step(state):
    await on_menu_new(FakeCallback(MENU_NEW), state)
    await step_full_name(FakeMessage("Іван Петренко"), state)
    assert await state.get_state() == ApplicationForm.contact

    callback = FakeCallback(FORM_CANCEL)
    await on_cancel(callback, state)

    assert await state.get_state() is None
    assert callback_data(callback.message.markups[0]) == [MENU_NEW, MENU_MY, MENU_HELP]


async def test_category_step_offers_cancel_alongside_categories(state):
    await on_menu_new(FakeCallback(MENU_NEW), state)
    await step_full_name(FakeMessage("Іван Петренко"), state)
    message = FakeMessage("+380000000000")

    await step_contact(message, state)

    data = callback_data(message.markups[0])
    assert len(data) == len(CATEGORIES) + 1
    assert data[-1] == FORM_CANCEL


async def test_my_lists_applications_with_a_delete_button_each(session):
    first = await _make(session, description="перша заявка користувача")
    second = await _make(session, description="друга заявка користувача")
    callback = FakeCallback(MENU_MY)
    state = FSMContext(
        storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=OWNER_ID)
    )

    await on_my(callback, state, session)

    data = callback_data(callback.message.markups[0])
    assert f"{DELETE_PREFIX}:{first.id}" in data
    assert f"{DELETE_PREFIX}:{second.id}" in data
    assert data[-1] == MENU_BACK


async def test_empty_list_still_offers_a_way_back(session, state):
    callback = FakeCallback(MENU_MY)

    await on_my(callback, state, session)

    assert "немає заявок" in callback.message.answers[0]
    assert callback_data(callback.message.markups[0]) == [MENU_BACK]


async def test_delete_button_removes_and_refreshes_the_list(
    session, publisher, settings
):
    application = await _make(session)
    await repository.set_group_message(
        session, application, chat_id=publisher.chat_id, message_id=publisher.message_id
    )
    callback = FakeCallback(f"{DELETE_PREFIX}:{application.id}")

    await on_delete(callback, session, publisher, settings)

    _, total = await repository.list_applications(session)
    assert total == 0
    assert publisher.retracted == [(publisher.chat_id, publisher.message_id)]
    # Список перемальовано на місці, а не надіслано новим повідомленням.
    assert callback.message.edits
    assert "немає заявок" in callback.message.edits[0]


async def test_delete_button_respects_ownership(session, publisher, settings):
    application = await _make(session)
    callback = FakeCallback(
        f"{DELETE_PREFIX}:{application.id}", user=FakeUser(STRANGER_ID)
    )

    await on_delete(callback, session, publisher, settings)

    _, total = await repository.list_applications(session)
    assert total == 1
    assert "лише власні" in callback.answered[0]
    assert not callback.message.edits


async def test_delete_button_with_broken_payload_does_not_crash(
    session, publisher, settings
):
    callback = FakeCallback(f"{DELETE_PREFIX}:abc")

    await on_delete(callback, session, publisher, settings)

    assert callback.answered == ["Невідома заявка"]


async def test_help_and_back_return_the_menu(state):
    help_callback = FakeCallback(MENU_HELP)
    await on_help(help_callback)

    back_callback = FakeCallback(MENU_BACK)
    await on_back(back_callback, state)

    for callback in (help_callback, back_callback):
        assert callback_data(callback.message.markups[0]) == [
            MENU_NEW, MENU_MY, MENU_HELP
        ]
