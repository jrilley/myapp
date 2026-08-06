"""Тести керування співробітниками та довідником посад.

Обидві гілки доступні лише головному адміністратору, і кожен хендлер
перевіряє це сам — приховати кнопку недостатньо.
"""

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app import repository
from app.bot.access import (
    DENIED as NO_RIGHTS,
    ROLE_COMPANY_ADMIN,
    MAIN_ADMIN_ONLY,
    ROLE_DRIVER,
    ROLE_MAIN_ADMIN,
    ROLE_MANAGER,
    Access,
)
from app.bot.handlers.management import (
    edit_fullname,
    edit_phone,
    edit_phone2,
    on_employee_card,
    on_employee_edit,
    on_employee_set,
    on_company_edit,
    on_company_employees,
    on_my_company,
    on_position_add,
    on_roles,
    on_positions,
    edit_company_value,
    position_name,
)
from app.bot.keyboards import (
    EMP_EDIT_PREFIX,
    EMP_SET_PREFIX,
    EMP_VIEW_PREFIX,
    COMPANY_EDIT_PREFIX,
    COMPANY_EMPLOYEES_PREFIX,
    MENU_MY_COMPANY,
    MENU_POSITIONS,
    MENU_ROLES,
    POSITION_ADD,
    POSITION_CARD_PREFIX,
)
from app.bot.states import CompanyEdit, EmployeeEdit, PositionForm
from app.models import Company, Employee, Position, Role
from tests.conftest import (
    ADMIN_ID,
    OWNER_ID,
    FakeCallback,
    FakeMessage,
    FakeUser,
    callback_data,
    make_access,
    permissions_for,
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
    position = Position(id=1, position="Водій")
    session.add_all(
        [
            company,
            position,
            Role(id=1, role=ROLE_MAIN_ADMIN),
            Role(id=2, role=ROLE_COMPANY_ADMIN),
            Role(id=3, role=ROLE_DRIVER),
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


async def test_positions_are_main_admin_only(session, state, access):
    """Довідник посад — глобальний, тож лише головний адміністратор."""
    callback = FakeCallback(MENU_POSITIONS, user=FakeUser(OWNER_ID))

    await on_positions(callback, state, session, access)

    assert callback.answered == [DENIED]
    assert not callback.message.answers


async def test_ordinary_user_cannot_list_employees(session, state, access, employee):
    callback = FakeCallback(f"{COMPANY_EMPLOYEES_PREFIX}:1", user=FakeUser(OWNER_ID))

    await on_company_employees(callback, state, session, access)

    assert callback.answered == [NO_RIGHTS]
    assert not callback.message.answers


async def test_ordinary_user_cannot_open_an_employee_card(
    session, state, access, employee
):
    callback = FakeCallback(f"{EMP_VIEW_PREFIX}:{employee.id}", user=FakeUser(OWNER_ID))

    await on_employee_card(callback, state, session, access)

    assert callback.answered == [NO_RIGHTS]


# ---------------------------------------------------------------------------
# Список і картка
# ---------------------------------------------------------------------------


async def test_list_shows_every_employee_as_a_button(
    session, state, access_admin, org, employee
):
    company, _ = org
    callback = FakeCallback(
        f"{COMPANY_EMPLOYEES_PREFIX}:{company.id}", user=FakeUser(ADMIN_ID)
    )

    await on_company_employees(callback, state, session, access_admin)

    data = callback_data(callback.message.markups[0])
    assert f"{EMP_VIEW_PREFIX}:{employee.id}" in data


async def test_empty_list_is_reported(session, state, access_admin, org):
    company, _ = org
    callback = FakeCallback(
        f"{COMPANY_EMPLOYEES_PREFIX}:{company.id}", user=FakeUser(ADMIN_ID)
    )

    await on_company_employees(callback, state, session, access_admin)

    assert "ще немає" in callback.message.answers[0]


async def test_card_shows_all_fields(session, state, access_admin, employee):
    callback = FakeCallback(f"{EMP_VIEW_PREFIX}:{employee.id}", user=FakeUser(ADMIN_ID))

    await on_employee_card(callback, state, session, access_admin)

    text = callback.message.answers[0]
    assert "Олена Ковальчук" in text
    assert "+380671112233" in text
    assert "ТОВ Ромашка" in text
    assert "Водій" in text
    assert ROLE_DRIVER in text
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

    await edit_fullname(
        FakeMessage("Олена Петрівна Ковальчук"), state, session, access_admin
    )

    updated = await repository.get_employee(session, employee.id)
    assert updated.fullname == "Олена Петрівна Ковальчук"
    assert await state.get_state() is None


async def test_short_fullname_keeps_state(session, state, access_admin, employee):
    await state.set_state(EmployeeEdit.fullname)
    await state.update_data(employee_id=employee.id)
    message = FakeMessage("О")

    await edit_fullname(message, state, session, access_admin)

    assert await state.get_state() == EmployeeEdit.fullname
    assert "від 2 до" in message.answers[0]


async def test_card_shows_second_phone_only_when_present(
    session, state, access_admin, employee
):
    first = FakeCallback(f"{EMP_VIEW_PREFIX}:{employee.id}", user=FakeUser(ADMIN_ID))
    await on_employee_card(first, state, session, access_admin)
    assert "Додатковий" not in first.message.answers[0]

    await repository.update_employee(session, employee, phone_number2="+380509998877")
    second = FakeCallback(f"{EMP_VIEW_PREFIX}:{employee.id}", user=FakeUser(ADMIN_ID))
    await on_employee_card(second, state, session, access_admin)

    assert "+380509998877" in second.message.answers[0]


async def test_editing_second_phone_updates_the_row(
    session, state, access_admin, employee
):
    await state.set_state(EmployeeEdit.phone2)
    await state.update_data(employee_id=employee.id)

    await edit_phone2(FakeMessage("+380509998877"), state, session, access_admin)

    updated = await repository.get_employee(session, employee.id)
    assert updated.phone_number2 == "+380509998877"


async def test_second_phone_can_be_cleared(session, state, access_admin, employee):
    """Поле необов'язкове, тож має бути спосіб його прибрати."""
    await repository.update_employee(session, employee, phone_number2="+380509998877")
    await state.set_state(EmployeeEdit.phone2)
    await state.update_data(employee_id=employee.id)

    await edit_phone2(FakeMessage("-"), state, session, access_admin)

    updated = await repository.get_employee(session, employee.id)
    assert updated.phone_number2 is None


async def test_editing_phone_updates_the_row(session, state, access_admin, employee):
    await state.set_state(EmployeeEdit.phone)
    await state.update_data(employee_id=employee.id)

    await edit_phone(FakeMessage("+380509998877"), state, session, access_admin)

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


# ---------------------------------------------------------------------------
# Посада й роль розведені
# ---------------------------------------------------------------------------


async def test_position_change_leaves_the_role_alone(
    session, access_admin, employee
):
    """Посада каже, ким людина працює; роль — що їй дозволено. Одне не має
    тихо міняти інше: підвищення прав роздає головний адміністратор."""
    director = await repository.create_position(session, name="Директор")
    callback = FakeCallback(
        f"{EMP_SET_PREFIX}:position:{employee.id}:{director.id}",
        user=FakeUser(ADMIN_ID),
    )

    await on_employee_set(callback, session, access_admin)

    updated = await repository.get_employee(session, employee.id)
    assert updated.position.position == "Директор"
    assert updated.role.role == ROLE_DRIVER


@pytest.mark.parametrize("field", ["position", "role", "company"])
async def test_company_admin_cannot_change_position_or_role(
    session, state, org, employee, field
):
    """Адміністратору компанії лишаються ПІБ і телефони. Посади й ролі —
    за рішенням замовника — роздає лише головний адміністратор."""
    company, _ = org
    boss = Employee(
        tg_id=ADMIN_ID, company_id=company.id, fullname="Адмін Компанії",
        phone_number="+380000000000", position_id=1, role_id=2,
    )
    boss.role = Role(id=2, role=ROLE_COMPANY_ADMIN)
    access = Access(
        telegram_user_id=ADMIN_ID,
        employee=boss,
        permissions=permissions_for(ROLE_COMPANY_ADMIN),
    )

    callback = FakeCallback(
        f"{EMP_EDIT_PREFIX}:{field}:{employee.id}", user=FakeUser(ADMIN_ID)
    )
    await on_employee_edit(callback, state, session, access)

    assert callback.answered == [DENIED]
    assert await state.get_state() is None


async def test_positions_are_listed_as_buttons(session, state, access_admin, org):
    callback = FakeCallback(MENU_POSITIONS, user=FakeUser(ADMIN_ID))

    await on_positions(callback, state, session, access_admin)

    labels = [
        b.text for row in callback.message.markups[0].inline_keyboard for b in row
    ]
    data = callback_data(callback.message.markups[0])
    assert "Водій" in labels
    assert POSITION_ADD in data
    assert any(d.startswith(f"{POSITION_CARD_PREFIX}:") for d in data)


async def test_adding_a_position_takes_one_step(session, state, access_admin, org):
    """Посада — це просто назва: прав вона не дає, тож питати більше нічого."""
    await on_position_add(
        FakeCallback(POSITION_ADD, user=FakeUser(ADMIN_ID)), state, access_admin
    )
    assert await state.get_state() == PositionForm.name

    message = FakeMessage("Вагар")
    await position_name(message, state, session)

    created = await repository.get_position_by_name(session, "Вагар")
    assert created is not None
    assert await state.get_state() is None
    assert "додано" in message.answers[0]


async def test_duplicate_position_is_refused(session, state, access_admin, org):
    await state.set_state(PositionForm.name)
    message = FakeMessage("Водій")  # уже є в довіднику

    await position_name(message, state, session)

    assert await state.get_state() == PositionForm.name
    assert "вже є" in message.answers[0]
    assert len(await repository.list_positions(session)) == 1


async def test_only_main_admin_adds_a_position(state, access):
    callback = FakeCallback(POSITION_ADD, user=FakeUser(OWNER_ID))

    await on_position_add(callback, state, access)

    assert await state.get_state() is None
    assert callback.answered == [DENIED]


# ---------------------------------------------------------------------------
# Картка компанії
# ---------------------------------------------------------------------------


async def test_editing_the_working_chat_redraws_the_card(
    session, state, access_admin, org
):
    """Цей шлях не був покритий — і саме на ньому впав TypeError після того,
    як картка компанії почала залежати від прав."""
    company, _ = org
    callback = FakeCallback(
        f"{COMPANY_EDIT_PREFIX}:chat:{company.id}", user=FakeUser(ADMIN_ID)
    )
    await on_company_edit(callback, state, session, access_admin)
    assert await state.get_state() == CompanyEdit.value

    message = FakeMessage("-1001234567890")
    await edit_company_value(message, state, session, access_admin)

    refreshed = await repository.get_company(session, company.id)
    assert refreshed.company_chat_id == -1001234567890
    assert "-1001234567890" in message.answers[-1]
    assert await state.get_state() is None


async def test_working_chat_can_be_cleared(session, state, access_admin, org):
    company, _ = org
    await repository.update_company(session, company, company_chat_id=-100500)
    await state.set_state(CompanyEdit.value)
    await state.update_data(company_id=company.id, field="chat")

    await edit_company_value(FakeMessage("-"), state, session, access_admin)

    refreshed = await repository.get_company(session, company.id)
    assert refreshed.company_chat_id is None


async def test_garbage_chat_id_keeps_the_editor_open(
    session, state, access_admin, org
):
    company, _ = org
    await state.set_state(CompanyEdit.value)
    await state.update_data(company_id=company.id, field="chat")
    message = FakeMessage("моя група")

    await edit_company_value(message, state, session, access_admin)

    assert await state.get_state() == CompanyEdit.value
    assert "Не схоже на id чату" in message.answers[0]


async def test_taken_tax_id_is_refused(session, state, access_admin, org):
    """Код унікальний; власний номер компанії конфліктом не рахуємо."""
    company, _ = org
    other = await repository.create_company(
        session, name="ТОВ Друга", tax_id="99999999", address="Львів"
    )
    await state.set_state(CompanyEdit.value)
    await state.update_data(company_id=company.id, field="tax")

    message = FakeMessage(other.tax_id)
    await edit_company_value(message, state, session, access_admin)
    assert "уже є" in message.answers[0]

    await edit_company_value(FakeMessage("55555555"), state, session, access_admin)
    refreshed = await repository.get_company(session, company.id)
    assert refreshed.tax_id == "55555555"


async def test_my_company_opens_your_own(session, state, org, employee):
    """Кнопка «Моя компанія» — без кроку вибору й без чужих компаній."""
    company, _ = org
    access = make_access(
        OWNER_ID, role=ROLE_COMPANY_ADMIN, company_id=company.id
    )
    callback = FakeCallback(MENU_MY_COMPANY, user=FakeUser(OWNER_ID))

    await on_my_company(callback, state, session, access)

    assert "ТОВ Ромашка" in callback.message.answers[0]


async def test_manager_sees_the_company_without_edit_buttons(
    session, state, org, employee
):
    """У менеджера на компанію лише R: кнопок, які все одно відмовлять,
    показувати не треба."""
    company, _ = org
    access = make_access(OWNER_ID, role=ROLE_MANAGER, company_id=company.id)
    callback = FakeCallback(MENU_MY_COMPANY, user=FakeUser(OWNER_ID))

    await on_my_company(callback, state, session, access)

    data = callback_data(callback.message.markups[0])
    assert not any(d.startswith(COMPANY_EDIT_PREFIX) for d in data)


async def test_manager_cannot_edit_the_company_even_by_id(
    session, state, org, employee
):
    company, _ = org
    access = make_access(OWNER_ID, role=ROLE_MANAGER, company_id=company.id)
    callback = FakeCallback(
        f"{COMPANY_EDIT_PREFIX}:name:{company.id}", user=FakeUser(OWNER_ID)
    )

    await on_company_edit(callback, state, session, access)

    assert callback.answered == [NO_RIGHTS]
    assert await state.get_state() is None


async def test_roles_screen_lists_the_matrix(session, state, access_admin, org):
    callback = FakeCallback(MENU_ROLES, user=FakeUser(ADMIN_ID))

    await on_roles(callback, state, session, access_admin)

    text = callback.message.answers[0]
    assert ROLE_MAIN_ADMIN in text
    assert "усе, в усіх компаніях" in text


async def test_roles_screen_is_main_admin_only(session, state, org, employee):
    access = make_access(OWNER_ID, role=ROLE_COMPANY_ADMIN)
    callback = FakeCallback(MENU_ROLES, user=FakeUser(OWNER_ID))

    await on_roles(callback, state, session, access)

    assert callback.answered == [MAIN_ADMIN_ONLY]
