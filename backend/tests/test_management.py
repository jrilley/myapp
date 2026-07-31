"""Тести керування співробітниками та довідником посад.

Обидві гілки доступні лише головному адміністратору, і кожен хендлер
перевіряє це сам — приховати кнопку недостатньо.
"""

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app import repository
from app.bot.access import ROLE_COMPANY_ADMIN, ROLE_MAIN_ADMIN, ROLE_USER
from app.bot.handlers.management import (
    edit_fullname,
    edit_phone,
    on_employee_card,
    on_employee_edit,
    on_employee_set,
    on_employees,
    on_position_add,
    on_positions,
    position_name,
)
from app.bot.keyboards import (
    EMP_EDIT_PREFIX,
    EMP_SET_PREFIX,
    EMP_VIEW_PREFIX,
    MENU_EMPLOYEES,
    MENU_POSITIONS,
    POSITION_ADD,
)
from app.bot.states import EmployeeEdit, PositionForm
from app.models import Company, Position, Role
from tests.conftest import (
    ADMIN_ID,
    OWNER_ID,
    FakeCallback,
    FakeMessage,
    FakeUser,
    callback_data,
)

DENIED = "Дія доступна лише головному адміністратору."


@pytest.fixture
def state() -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=ADMIN_ID)
    )


@pytest.fixture
async def org(session):
    """Компанія, посада і три ролі — мінімум, щоб завести співробітника."""
    company = Company(name="ТОВ Ромашка", tax_id="12345678", address="Київ")
    position = Position(id=1, position="Інше")
    session.add_all(
        [
            company,
            position,
            Role(id=1, role=ROLE_MAIN_ADMIN),
            Role(id=2, role=ROLE_COMPANY_ADMIN),
            Role(id=3, role=ROLE_USER),
        ]
    )
    await session.commit()
    return company, position


@pytest.fixture
async def employee(session, org):
    company, position = org
    return await repository.create_employee(
        session,
        tg_id=OWNER_ID,
        company_id=company.id,
        fullname="Олена Ковальчук",
        phone_number="+380671112233",
        position_id=position.id,
        role_id=3,
    )


# ---------------------------------------------------------------------------
# Права
# ---------------------------------------------------------------------------


async def test_plain_admin_cannot_reach_management(session, state, access, employee):
    """access — звичайний користувач; але навіть «Адміністратор компанії»
    сюди не має доступу, тільки головний."""
    for handler, data in (
        (on_employees, MENU_EMPLOYEES),
        (on_positions, MENU_POSITIONS),
    ):
        callback = FakeCallback(data, user=FakeUser(OWNER_ID))
        await handler(callback, state, session, access)
        assert callback.answered == [DENIED]
        assert not callback.message.answers


async def test_employee_card_is_closed_to_non_main_admin(
    session, state, access, employee
):
    callback = FakeCallback(f"{EMP_VIEW_PREFIX}:{employee.id}", user=FakeUser(OWNER_ID))

    await on_employee_card(callback, state, session, access)

    assert callback.answered == [DENIED]


# ---------------------------------------------------------------------------
# Список і картка
# ---------------------------------------------------------------------------


async def test_list_shows_every_employee_as_a_button(
    session, state, access_admin, employee
):
    callback = FakeCallback(MENU_EMPLOYEES, user=FakeUser(ADMIN_ID))

    await on_employees(callback, state, session, access_admin)

    data = callback_data(callback.message.markups[0])
    assert f"{EMP_VIEW_PREFIX}:{employee.id}" in data


async def test_empty_list_is_reported(session, state, access_admin, org):
    callback = FakeCallback(MENU_EMPLOYEES, user=FakeUser(ADMIN_ID))

    await on_employees(callback, state, session, access_admin)

    assert "ще немає" in callback.message.answers[0]


async def test_card_shows_all_fields(session, state, access_admin, employee):
    callback = FakeCallback(f"{EMP_VIEW_PREFIX}:{employee.id}", user=FakeUser(ADMIN_ID))

    await on_employee_card(callback, state, session, access_admin)

    text = callback.message.answers[0]
    assert "Олена Ковальчук" in text
    assert "+380671112233" in text
    assert "ТОВ Ромашка" in text
    assert "Інше" in text
    assert ROLE_USER in text
    assert str(OWNER_ID) in text


async def test_unknown_employee_id_is_rejected(session, state, access_admin):
    callback = FakeCallback(f"{EMP_VIEW_PREFIX}:abc", user=FakeUser(ADMIN_ID))

    await on_employee_card(callback, state, session, access_admin)

    assert callback.answered == ["Невідомий співробітник"]


# ---------------------------------------------------------------------------
# Редагування
# ---------------------------------------------------------------------------


async def test_editing_fullname_updates_the_row(
    session, state, access_admin, employee
):
    callback = FakeCallback(
        f"{EMP_EDIT_PREFIX}:name:{employee.id}", user=FakeUser(ADMIN_ID)
    )
    await on_employee_edit(callback, state, session, access_admin)
    assert await state.get_state() == EmployeeEdit.fullname

    await edit_fullname(FakeMessage("Олена Петрівна Ковальчук"), state, session)

    updated = await repository.get_employee(session, employee.id)
    assert updated.fullname == "Олена Петрівна Ковальчук"
    assert await state.get_state() is None


async def test_short_fullname_keeps_state(session, state, access_admin, employee):
    await state.set_state(EmployeeEdit.fullname)
    await state.update_data(employee_id=employee.id)
    message = FakeMessage("О")

    await edit_fullname(message, state, session)

    assert await state.get_state() == EmployeeEdit.fullname
    assert "від 2 до" in message.answers[0]


async def test_editing_phone_updates_the_row(session, state, access_admin, employee):
    await state.set_state(EmployeeEdit.phone)
    await state.update_data(employee_id=employee.id)

    await edit_phone(FakeMessage("+380509998877"), state, session)

    updated = await repository.get_employee(session, employee.id)
    assert updated.phone_number == "+380509998877"


async def test_choosing_a_position_applies_immediately(
    session, state, access_admin, employee
):
    new_position = await repository.create_position(session, name="Бухгалтер")
    callback = FakeCallback(
        f"{EMP_SET_PREFIX}:position:{employee.id}:{new_position.id}",
        user=FakeUser(ADMIN_ID),
    )

    await on_employee_set(callback, session, access_admin)

    updated = await repository.get_employee(session, employee.id)
    assert updated.position.position == "Бухгалтер"
    assert callback.answered == ["Збережено"]


async def test_role_can_be_raised(session, state, access_admin, employee):
    callback = FakeCallback(
        f"{EMP_SET_PREFIX}:role:{employee.id}:2", user=FakeUser(ADMIN_ID)
    )

    await on_employee_set(callback, session, access_admin)

    updated = await repository.get_employee(session, employee.id)
    assert updated.role.role == ROLE_COMPANY_ADMIN


async def test_admin_cannot_change_their_own_role(session, state, access_admin, org):
    """Інакше головний адмін одним натисканням знімає з себе доступ,
    і повернути його вже нічим."""
    company, position = org
    me = await repository.create_employee(
        session,
        tg_id=ADMIN_ID,
        company_id=company.id,
        fullname="Головний Адмін",
        phone_number="+380000000000",
        position_id=position.id,
        role_id=1,
    )
    callback = FakeCallback(
        f"{EMP_SET_PREFIX}:role:{me.id}:3", user=FakeUser(ADMIN_ID)
    )

    await on_employee_set(callback, session, access_admin)

    unchanged = await repository.get_employee(session, me.id)
    assert unchanged.role.role == ROLE_MAIN_ADMIN
    assert callback.answered == ["Не можна змінити власну роль."]


async def test_malformed_set_payload_does_not_crash(session, access_admin):
    callback = FakeCallback(f"{EMP_SET_PREFIX}:role:abc", user=FakeUser(ADMIN_ID))

    await on_employee_set(callback, session, access_admin)

    assert callback.answered == ["Невідоме значення"]


# ---------------------------------------------------------------------------
# Посади
# ---------------------------------------------------------------------------


async def test_positions_are_listed(session, state, access_admin, org):
    callback = FakeCallback(MENU_POSITIONS, user=FakeUser(ADMIN_ID))

    await on_positions(callback, state, session, access_admin)

    assert "Інше" in callback.message.answers[0]
    assert callback_data(callback.message.markups[0])[0] == POSITION_ADD


async def test_adding_a_position(session, state, access_admin, org):
    await on_position_add(
        FakeCallback(POSITION_ADD, user=FakeUser(ADMIN_ID)), state, access_admin
    )
    assert await state.get_state() == PositionForm.name

    message = FakeMessage("Менеджер з продажу")
    await position_name(message, state, session)

    positions = [p.position for p in await repository.list_positions(session)]
    assert "Менеджер з продажу" in positions
    assert await state.get_state() is None
    assert "додано" in message.answers[0]


async def test_duplicate_position_is_refused(session, state, access_admin, org):
    await state.set_state(PositionForm.name)
    message = FakeMessage("Інше")  # уже є в довіднику

    await position_name(message, state, session)

    assert await state.get_state() == PositionForm.name
    assert "вже є" in message.answers[0]
    assert len(await repository.list_positions(session)) == 1


async def test_only_main_admin_adds_a_position(state, access):
    callback = FakeCallback(POSITION_ADD, user=FakeUser(OWNER_ID))

    await on_position_add(callback, state, access)

    assert await state.get_state() is None
    assert callback.answered == [DENIED]
