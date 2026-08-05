"""Тести FSM-анкети.

Хендлери викликаються напряму з фейковими Message/CallbackQuery і реальним
FSMContext на MemoryStorage — жодних мережевих викликів до Telegram.
"""

import pytest
from aiogram.filters import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app import repository
from app.bot.constants import CATEGORIES
from app.bot.handlers.admin import cmd_delete
from app.bot.handlers.common import cmd_cancel, cmd_my
from app.bot.handlers.form import (
    cmd_new,
    step_category,
    step_confirm,
    step_contact,
    step_description,
    step_full_name,
    step_reject,
)
from app.bot.states import ApplicationForm
from tests.conftest import (
    make_access,
    ADMIN_ID,
    OWNER_ID,
    STRANGER_ID,
    FakeCallback,
    FakeMessage,
    FakeUser,
)


@pytest.fixture(autouse=True)
def _applications_on(applications_enabled):
    """Цей файл увесь про стару анкету заявок — вона вимкнена
    прапорцем, але код живий і має лишатись перевіреним."""


@pytest.fixture
def state() -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=OWNER_ID)
    )


async def _fill_until_confirm(state: FSMContext, access) -> None:
    await cmd_new(FakeMessage(), state, access)
    await step_full_name(FakeMessage("Іван Петренко"), state)
    await step_contact(FakeMessage("+380000000000"), state)
    await step_category(FakeCallback("cat:0"), state)
    await step_description(FakeMessage("Достатньо довгий опис заявки"), state)


async def test_form_advances_through_all_steps(state, access):
    await _fill_until_confirm(state, access)

    assert await state.get_state() == ApplicationForm.confirm
    data = await state.get_data()
    assert data["full_name"] == "Іван Петренко"
    assert data["category"] == CATEGORIES[0]


async def test_confirm_saves_application_and_publishes(state, session, publisher, access):
    await _fill_until_confirm(state, access)
    callback = FakeCallback("confirm:yes")

    await step_confirm(callback, state, session, publisher)

    items, total = await repository.list_applications(session)
    assert total == 1
    application = items[0]
    assert application.telegram_user_id == OWNER_ID
    assert application.telegram_username == "tester"
    assert publisher.published == [application.id]
    # message_id збережено, інакше потім не прибрати запис із групи.
    assert application.group_message_id == publisher.message_id
    assert await state.get_state() is None


async def test_short_name_keeps_state_and_data(state, access):
    await cmd_new(FakeMessage(), state, access)
    message = FakeMessage("І")

    await step_full_name(message, state)

    assert await state.get_state() == ApplicationForm.full_name
    assert "full_name" not in await state.get_data()
    assert "від 2 до" in message.answers[0]


async def test_short_description_keeps_state(state, access):
    await cmd_new(FakeMessage(), state, access)
    await step_full_name(FakeMessage("Іван Петренко"), state)
    await step_contact(FakeMessage("+380000000000"), state)
    await step_category(FakeCallback("cat:1"), state)

    message = FakeMessage("коротко")
    await step_description(message, state)

    assert await state.get_state() == ApplicationForm.description
    assert "Опис має бути" in message.answers[0]


async def test_unknown_category_does_not_advance(state, access):
    await cmd_new(FakeMessage(), state, access)
    await step_full_name(FakeMessage("Іван Петренко"), state)
    await step_contact(FakeMessage("+380000000000"), state)

    callback = FakeCallback("cat:999")
    await step_category(callback, state)

    assert await state.get_state() == ApplicationForm.category
    assert callback.answered == ["Невідома категорія"]


async def test_cancel_clears_state(state, access):
    await cmd_new(FakeMessage(), state, access)
    await step_full_name(FakeMessage("Іван Петренко"), state)

    await cmd_cancel(FakeMessage(), state, access)

    assert await state.get_state() is None


async def test_reject_on_confirm_saves_nothing(state, session, access):
    await _fill_until_confirm(state, access)

    await step_reject(FakeCallback("confirm:no"), state, access)

    _, total = await repository.list_applications(session)
    assert total == 0
    assert await state.get_state() is None


async def test_my_lists_only_own_applications(session, access):
    await repository.create_application(
        session,
        telegram_user_id=OWNER_ID,
        telegram_username="tester",
        full_name="Власна заявка",
        contact="c",
        category=CATEGORIES[0],
        description="опис власної заявки",
    )
    await repository.create_application(
        session,
        telegram_user_id=STRANGER_ID,
        telegram_username="other",
        full_name="Чужа заявка",
        contact="c",
        category=CATEGORIES[0],
        description="опис чужої заявки",
    )

    message = FakeMessage(user=FakeUser(OWNER_ID))
    await cmd_my(message, session, access)

    assert "Власна заявка" not in message.answers[0]  # у списку лише категорія+опис
    assert "опис власної заявки" in message.answers[0]
    assert "опис чужої заявки" not in message.answers[0]


async def _seed_owned(session, publisher):
    application = await repository.create_application(
        session,
        telegram_user_id=OWNER_ID,
        telegram_username="tester",
        full_name="Іван",
        contact="c",
        category=CATEGORIES[0],
        description="опис заявки для видалення",
    )
    await repository.set_group_message(
        session, application, chat_id=publisher.chat_id, message_id=publisher.message_id
    )
    return application


async def test_owner_can_delete_own_application(session, publisher, access):
    application = await _seed_owned(session, publisher)
    message = FakeMessage(user=FakeUser(OWNER_ID))

    await cmd_delete(
        message,
        CommandObject(prefix="/", command="delete", args=str(application.id)),
        session,
        publisher,
        access,
    )

    _, total = await repository.list_applications(session)
    assert total == 0
    assert publisher.retracted == [(publisher.chat_id, publisher.message_id)]


async def test_stranger_cannot_delete_someone_elses_application(session, publisher):
    application = await _seed_owned(session, publisher)
    stranger = make_access(STRANGER_ID)
    message = FakeMessage(user=FakeUser(STRANGER_ID))

    await cmd_delete(
        message,
        CommandObject(prefix="/", command="delete", args=str(application.id)),
        session,
        publisher,
        stranger,
    )

    _, total = await repository.list_applications(session)
    assert total == 1
    assert "лише власні" in message.answers[0]
    assert publisher.retracted == []


async def test_admin_can_delete_any_application(session, publisher, access_admin):
    application = await _seed_owned(session, publisher)
    message = FakeMessage(user=FakeUser(ADMIN_ID))

    await cmd_delete(
        message,
        CommandObject(prefix="/", command="delete", args=str(application.id)),
        session,
        publisher,
        access_admin,
    )

    _, total = await repository.list_applications(session)
    assert total == 0


async def test_delete_requires_numeric_id(session, publisher, access_admin):
    message = FakeMessage(user=FakeUser(ADMIN_ID))

    await cmd_delete(
        message,
        CommandObject(prefix="/", command="delete", args="abc"),
        session,
        publisher,
        access_admin,
    )

    assert "Використання" in message.answers[0]
