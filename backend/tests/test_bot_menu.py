"""Тести inline-меню та прав доступу.

Мета меню — щоб користувач не набирав команд: усе, що він робить,
має бути досяжним натисканням кнопки. Склад меню залежить від ролі
в employees, і кожен обмежений хендлер перевіряє право самостійно.
"""

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app import repository
from app.bot.constants import CATEGORIES
from app.bot.handlers.common import (
    cmd_start,
    on_all,
    on_back,
    on_delete,
    on_help,
    on_my,
    on_stats,
)
from app.bot.handlers.form import on_cancel, on_menu_new, step_contact, step_full_name
from app.bot.keyboards import (
    DELETE_PREFIX,
    FORM_CANCEL,
    MENU_ALL,
    MENU_BACK,
    MENU_COMPANIES,
    MENU_EMPLOYEES,
    MENU_HELP,
    MENU_MY,
    MENU_NEW,
    MENU_POSITIONS,
    MENU_STATS,
    MENU_VEHICLE_ADD,
    REG_START,
)
from app.bot.states import ApplicationForm
from tests.conftest import (
    ADMIN_ID,
    OWNER_ID,
    STRANGER_ID,
    FakeCallback,
    FakeMessage,
    FakeUser,
    callback_data,
    make_access,
)

USER_MENU = [MENU_NEW, MENU_MY, MENU_HELP]
ADMIN_MENU = [
    MENU_NEW, MENU_MY, MENU_ALL, MENU_STATS, MENU_VEHICLE_ADD,
    MENU_EMPLOYEES, MENU_POSITIONS, MENU_COMPANIES, MENU_HELP,
]
#: Адміністратор компанії: без керування довідниками, але з транспортом.
COMPANY_ADMIN_MENU = [
    MENU_NEW, MENU_MY, MENU_ALL, MENU_STATS, MENU_VEHICLE_ADD, MENU_HELP,
]
GUEST_MENU = [REG_START, MENU_HELP]


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


# ---------------------------------------------------------------------------
# Склад меню
# ---------------------------------------------------------------------------


async def test_start_shows_menu_instead_of_bare_text(state, access):
    message = FakeMessage()

    await cmd_start(message, state, access)

    assert callback_data(message.markups[0]) == USER_MENU


async def test_menu_depends_on_who_opened_it(state, access, access_admin, access_guest):
    plain, admin, guest = FakeMessage(), FakeMessage(), FakeMessage()

    await cmd_start(plain, state, access)
    await cmd_start(admin, state, access_admin)
    await cmd_start(guest, state, access_guest)

    assert callback_data(plain.markups[0]) == USER_MENU
    assert callback_data(admin.markups[0]) == ADMIN_MENU
    # Незареєстрованому нема чого пропонувати, крім реєстрації.
    assert callback_data(guest.markups[0]) == GUEST_MENU


# ---------------------------------------------------------------------------
# Анкета заявки
# ---------------------------------------------------------------------------


async def test_menu_button_starts_the_form(state, access):
    callback = FakeCallback(MENU_NEW)

    await on_menu_new(callback, state, access)

    assert await state.get_state() == ApplicationForm.full_name
    # Під першим питанням має бути вихід, щоб не довелось друкувати /cancel.
    assert callback_data(callback.message.markups[0]) == [FORM_CANCEL]


async def test_unregistered_cannot_start_the_form(state, access_guest):
    """Кнопки «Нова заявка» гостю не видно, але callback_data можна
    переслати — тому перевірка має бути в хендлері."""
    callback = FakeCallback(MENU_NEW, user=FakeUser(STRANGER_ID))

    await on_menu_new(callback, state, access_guest)

    assert await state.get_state() is None
    assert "реєстрац" in callback.message.answers[0].lower()
    assert callback_data(callback.message.markups[0]) == [REG_START]


async def test_cancel_button_works_from_any_step(state, access):
    await on_menu_new(FakeCallback(MENU_NEW), state, access)
    await step_full_name(FakeMessage("Іван Петренко"), state)
    assert await state.get_state() == ApplicationForm.contact

    callback = FakeCallback(FORM_CANCEL)
    await on_cancel(callback, state, access)

    assert await state.get_state() is None
    assert callback_data(callback.message.markups[0]) == USER_MENU


async def test_category_step_offers_cancel_alongside_categories(state, access):
    await on_menu_new(FakeCallback(MENU_NEW), state, access)
    await step_full_name(FakeMessage("Іван Петренко"), state)
    message = FakeMessage("+380000000000")

    await step_contact(message, state)

    data = callback_data(message.markups[0])
    assert len(data) == len(CATEGORIES) + 1
    assert data[-1] == FORM_CANCEL


# ---------------------------------------------------------------------------
# Списки заявок і видалення
# ---------------------------------------------------------------------------


async def test_my_lists_applications_with_a_delete_button_each(session, state, access):
    first = await _make(session, description="перша заявка користувача")
    second = await _make(session, description="друга заявка користувача")
    callback = FakeCallback(MENU_MY)

    await on_my(callback, state, session, access)

    data = callback_data(callback.message.markups[0])
    assert f"{DELETE_PREFIX}:{first.id}" in data
    assert f"{DELETE_PREFIX}:{second.id}" in data
    assert data[-1] == MENU_BACK


async def test_empty_list_still_offers_a_way_back(session, state, access):
    callback = FakeCallback(MENU_MY)

    await on_my(callback, state, session, access)

    assert "немає заявок" in callback.message.answers[0]
    assert callback_data(callback.message.markups[0]) == [MENU_BACK]


async def test_delete_button_removes_and_refreshes_the_list(session, publisher, access):
    application = await _make(session)
    await repository.set_group_message(
        session, application, chat_id=publisher.chat_id, message_id=publisher.message_id
    )
    callback = FakeCallback(f"{DELETE_PREFIX}:{application.id}")

    await on_delete(callback, session, publisher, access)

    _, total = await repository.list_applications(session)
    assert total == 0
    assert publisher.retracted == [(publisher.chat_id, publisher.message_id)]
    # Список перемальовано на місці, а не надіслано новим повідомленням.
    assert callback.message.edits
    assert "немає заявок" in callback.message.edits[0]


async def test_delete_button_respects_ownership(session, publisher):
    application = await _make(session)
    stranger = make_access(STRANGER_ID)
    callback = FakeCallback(
        f"{DELETE_PREFIX}:{application.id}", user=FakeUser(STRANGER_ID)
    )

    await on_delete(callback, session, publisher, stranger)

    _, total = await repository.list_applications(session)
    assert total == 1
    assert "лише власні" in callback.answered[0]
    assert not callback.message.edits


async def test_delete_button_with_broken_payload_does_not_crash(
    session, publisher, access
):
    callback = FakeCallback(f"{DELETE_PREFIX}:abc")

    await on_delete(callback, session, publisher, access)

    assert callback.answered == ["Невідома заявка"]


# ---------------------------------------------------------------------------
# Адмінські дії
# ---------------------------------------------------------------------------


async def test_admin_actions_reject_a_non_admin(session, state, access):
    """Кнопки не видно звичайному користувачу, але callback_data можна
    переслати або підробити — право має перевірятись на кожному виклику."""
    for handler, data in ((on_all, MENU_ALL), (on_stats, MENU_STATS)):
        callback = FakeCallback(data, user=FakeUser(OWNER_ID))

        await handler(callback, state, session, access)

        assert callback.answered == ["Дія доступна лише адміністраторам."]
        assert not callback.message.answers


async def test_admin_sees_applications_of_every_user(session, state, access_admin):
    await _make(session, telegram_user_id=OWNER_ID, description="заявка власника")
    await _make(
        session, telegram_user_id=STRANGER_ID, telegram_username=None,
        description="заявка іншого користувача",
    )
    callback = FakeCallback(MENU_ALL, user=FakeUser(ADMIN_ID))

    await on_all(callback, state, session, access_admin)

    text = callback.message.answers[0]
    assert "заявка власника" in text
    assert "заявка іншого користувача" in text
    # Автора видно: у спільному списку заявки різних людей.
    assert "@tester" in text
    assert f"id{STRANGER_ID}" in text


async def test_stats_counts_live_and_deleted(session, state, access_admin):
    await _make(session, description="ця заявка лишається")
    removed = await _make(session, description="цю заявку видалимо")
    await repository.soft_delete_application(session, removed)
    callback = FakeCallback(MENU_STATS, user=FakeUser(ADMIN_ID))

    await on_stats(callback, state, session, access_admin)

    text = callback.message.answers[0]
    assert "Активних: <b>1</b>" in text
    assert "Видалених: 1" in text
    assert "Усього рядків у базі: 2" in text


async def test_admin_delete_refreshes_the_full_list(session, publisher, access_admin):
    mine = await _make(session, telegram_user_id=ADMIN_ID, description="заявка адміна")
    someone = await _make(
        session, telegram_user_id=OWNER_ID, description="заявка іншої людини"
    )
    callback = FakeCallback(f"{DELETE_PREFIX}:{mine.id}", user=FakeUser(ADMIN_ID))

    await on_delete(callback, session, publisher, access_admin)

    # Адмін після видалення бачить загальний список, а не лише свій —
    # інакше чужа заявка зникла б з екрана разом зі своєю.
    assert "заявка іншої людини" in callback.message.edits[0]
    assert str(someone.id) in callback.message.edits[0]


async def test_help_and_back_return_the_menu(state, access):
    help_callback = FakeCallback(MENU_HELP)
    await on_help(help_callback, access)

    back_callback = FakeCallback(MENU_BACK)
    await on_back(back_callback, state, access)

    for callback in (help_callback, back_callback):
        assert callback_data(callback.message.markups[0]) == USER_MENU
