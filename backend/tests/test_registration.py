"""Тести реєстрації співробітника та заведення компаній.

Тестова БД створюється через Base.metadata.create_all, а не міграціями,
тому довідники тут заповнюються фікстурою — у бойовій це робить
міграція 7d1b946ca46b.
"""

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app import repository
from app.bot.access import ROLE_MAIN_ADMIN, ROLE_USER
from app.bot.handlers.registration import (
    company_address,
    company_name,
    company_tax_id,
    on_companies,
    on_company_add,
    on_register,
    step_company,
    step_confirm,
    step_fullname,
    step_phone,
    step_position,
)
from app.bot.keyboards import FORM_CANCEL, REG_COMPANY_PREFIX, REG_POSITION_PREFIX
from app.bot.states import CompanyForm, Registration
from app.models import Company, Position, Role
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


@pytest.fixture
def state() -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=STRANGER_ID)
    )


@pytest.fixture
async def reference_data(session):
    """Довідники, без яких реєстрація неможлива."""
    company = Company(name="ТОВ Ромашка", tax_id="12345678", address="Київ")
    position = Position(id=1, position="Інше")
    session.add_all(
        [
            company,
            position,
            Role(id=1, role=ROLE_MAIN_ADMIN),
            Role(id=3, role=ROLE_USER),
        ]
    )
    await session.commit()
    return company, position


async def _walk_through(state, session, company, position):
    await step_fullname(FakeMessage("Олена Ковальчук"), state)
    await step_phone(FakeMessage("+380671112233"), state, session)
    await step_company(
        FakeCallback(f"{REG_COMPANY_PREFIX}:{company.id}"), state, session
    )
    await step_position(
        FakeCallback(f"{REG_POSITION_PREFIX}:{position.id}"), state, session
    )


# ---------------------------------------------------------------------------
# Реєстрація
# ---------------------------------------------------------------------------


async def test_registration_creates_an_employee(
    session, state, access_guest, reference_data
):
    company, position = reference_data
    await on_register(FakeCallback("reg:start"), state, session, access_guest)
    await _walk_through(state, session, company, position)

    callback = FakeCallback("reg:confirm", user=FakeUser(STRANGER_ID))
    await step_confirm(callback, state, session, access_guest)

    employee = await repository.get_employee_by_tg_id(session, STRANGER_ID)
    assert employee is not None
    assert employee.fullname == "Олена Ковальчук"
    assert employee.phone_number == "+380671112233"
    assert employee.company_id == company.id
    assert employee.position_id == position.id
    # Новий співробітник завжди отримує базову роль.
    assert employee.role.role == ROLE_USER
    assert await state.get_state() is None


async def test_menu_after_registration_is_the_user_menu(
    session, state, access_guest, reference_data
):
    company, position = reference_data
    await on_register(FakeCallback("reg:start"), state, session, access_guest)
    await _walk_through(state, session, company, position)

    callback = FakeCallback("reg:confirm", user=FakeUser(STRANGER_ID))
    await step_confirm(callback, state, session, access_guest)

    # Access у хендлері застарів, тому меню має будуватись на свіжому —
    # інакше щойно зареєстрований знову побачив би кнопку «Зареєструватися».
    assert "Зареєструватися" not in str(callback.message.markups[-1])


async def test_registration_is_refused_without_companies(session, state, access_guest):
    """Компаній немає — доводити людину до порожнього списку не варто."""
    callback = FakeCallback("reg:start")

    await on_register(callback, state, session, access_guest)

    assert await state.get_state() is None
    assert "немає жодної компанії" in callback.message.answers[0]


async def test_already_registered_user_is_told_so(
    session, state, access, reference_data
):
    callback = FakeCallback("reg:start")

    await on_register(callback, state, session, access)

    assert await state.get_state() is None
    assert "вже зареєстровані" in callback.message.answers[0]


async def test_double_submit_does_not_create_a_second_row(
    session, state, access_guest, reference_data
):
    """tg_id унікальний: друга вставка впала б помилкою БД."""
    company, position = reference_data
    await on_register(FakeCallback("reg:start"), state, session, access_guest)
    await _walk_through(state, session, company, position)
    await step_confirm(
        FakeCallback("reg:confirm", user=FakeUser(STRANGER_ID)),
        state, session, access_guest,
    )

    # Друга анкета тим самим користувачем
    await state.set_state(Registration.confirm)
    await state.update_data(
        fullname="Ще Раз", phone_number="+380000000000",
        company_id=company.id, position_id=position.id,
    )
    second = FakeCallback("reg:confirm", user=FakeUser(STRANGER_ID))
    await step_confirm(second, state, session, access_guest)

    assert await repository.count_employees(session) == 1
    assert "вже зареєстровані" in second.message.answers[0]


async def test_unknown_company_does_not_advance(session, state, reference_data):
    await state.set_state(Registration.company)
    callback = FakeCallback(f"{REG_COMPANY_PREFIX}:9999")

    await step_company(callback, state, session)

    assert await state.get_state() == Registration.company
    assert callback.answered == ["Невідома компанія"]


async def test_short_fullname_keeps_state(state):
    await state.set_state(Registration.fullname)
    message = FakeMessage("О")

    await step_fullname(message, state)

    assert await state.get_state() == Registration.fullname
    assert "від 2 до" in message.answers[0]


async def test_company_step_offers_cancel(session, state, reference_data):
    await state.set_state(Registration.phone)
    message = FakeMessage("+380671112233")

    await step_phone(message, state, session)

    assert callback_data(message.markups[0])[-1] == FORM_CANCEL


# ---------------------------------------------------------------------------
# Компанії
# ---------------------------------------------------------------------------


async def test_only_main_admin_opens_companies(session, state, access):
    callback = FakeCallback("menu:companies", user=FakeUser(OWNER_ID))

    await on_companies(callback, state, session, access)

    assert callback.answered == ["Дія доступна лише головному адміністратору."]
    assert not callback.message.answers


async def test_only_main_admin_adds_a_company(state, access):
    callback = FakeCallback("company:add", user=FakeUser(OWNER_ID))

    await on_company_add(callback, state, access)

    assert await state.get_state() is None
    assert callback.answered == ["Дія доступна лише головному адміністратору."]


async def test_main_admin_creates_a_company(session, state, access_admin):
    await on_company_add(FakeCallback("company:add", user=FakeUser(ADMIN_ID)), state, access_admin)
    await company_name(FakeMessage("ТОВ Нова"), state)
    await company_tax_id(FakeMessage("87654321"), state, session)

    message = FakeMessage("Львів, вул. Січових Стрільців, 5")
    await company_address(message, state, session, access_admin)

    companies = await repository.list_companies(session)
    assert [c.name for c in companies] == ["ТОВ Нова"]
    assert companies[0].tax_id == "87654321"
    assert await state.get_state() is None
    assert "додано" in message.answers[0]


async def test_duplicate_tax_id_is_caught_before_asking_address(
    session, state, access_admin, reference_data
):
    """tax_id унікальний. Ловимо це на кроці вводу, а не помилкою БД
    після того, як людина введе ще й адресу."""
    await state.set_state(CompanyForm.tax_id)
    await state.update_data(name="ТОВ Дубль")
    message = FakeMessage("12345678")  # уже зайнятий у reference_data

    await company_tax_id(message, state, session)

    assert await state.get_state() == CompanyForm.tax_id
    assert "уже є" in message.answers[0]


async def test_bootstrap_admin_counts_as_main_admin(session, state):
    """Без аварійного входу нікому завести першу компанію: адміном робить
    роль у employees, а employees порожня, поки немає компаній."""
    bootstrap = make_access(ADMIN_ID, registered=False, bootstrap_admin=True)
    callback = FakeCallback("menu:companies", user=FakeUser(ADMIN_ID))

    await on_companies(callback, state, session, bootstrap)

    assert callback.answered == [None]
    assert "Компаній ще немає" in callback.message.answers[0]
