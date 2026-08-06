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
from app.models import DEFAULT_POSITION, ROLE_DRIVER
from app.bot.handlers.registration import (
    company_address,
    company_chat,
    company_chat_skip,
    company_name,
    company_tax_id,
    on_companies,
    on_company_add,
    on_register,
    step_company,
    step_confirm,
    step_fullname,
    step_phone,
    step_phone2,
    step_phone2_no,
    step_phone2_yes,
    step_phone_shared,
)
from app.bot.keyboards import (
    CANCEL_TEXT,
    COMPANY_CHAT_SKIP,
    FORM_CANCEL,
    REG_COMPANY_PREFIX,
    REG_PHONE2_NO,
    REG_PHONE2_YES,
)
from app.bot.states import CompanyForm, Registration
from app.models import Company, Position, Role
from tests.conftest import (
    ADMIN_ID,
    OWNER_ID,
    STRANGER_ID,
    FakeCallback,
    FakeContact,
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
    position = Position(id=1, position="Водій")
    session.add_all(
        [
            company,
            position,
            Role(id=1, role=ROLE_MAIN_ADMIN),
            Role(id=3, role=ROLE_USER),
            Role(id=4, role=ROLE_DRIVER),
        ]
    )
    await session.commit()
    return company, position


async def _walk_through(state, session, company, position=None, *, second_phone=None):
    await step_fullname(FakeMessage("Олена Ковальчук"), state)
    await step_phone(FakeMessage("+380671112233"), state)
    if second_phone is None:
        await step_phone2_no(FakeCallback(REG_PHONE2_NO), state, session)
    else:
        await step_phone2_yes(FakeCallback(REG_PHONE2_YES), state)
        await step_phone2(FakeMessage(second_phone), state, session)
    # Останній крок анкети — компанія; у його повідомленні лежить зведення.
    callback = FakeCallback(f"{REG_COMPANY_PREFIX}:{company.id}")
    await step_company(callback, state, session)
    return callback


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
    assert employee.position.position == DEFAULT_POSITION
    # Роль при реєстрації завжди «Водій»: підвищує її головний адміністратор.
    assert employee.role.role == ROLE_DRIVER
    assert await state.get_state() is None


async def test_registration_does_not_ask_for_a_position(
    session, state, access_guest, reference_data
):
    """Посада в усіх однакова, тож кроку немає — але людина має бачити,
    ким її запишуть, ще до підтвердження."""
    company, _ = reference_data
    await on_register(FakeCallback("reg:start"), state, session, access_guest)

    callback = await _walk_through(state, session, company)

    assert await state.get_state() == Registration.confirm
    assert f"<b>Посада:</b> {DEFAULT_POSITION}" in callback.message.answers[0]


async def test_registration_without_the_driver_role_is_refused(
    session, state, access_guest, reference_data
):
    """Роль «Водій» — обов'язковий довідниковий рядок. Якщо його немає,
    краще сказати про це, ніж падати помилкою зовнішнього ключа."""
    company, _ = reference_data
    role = await repository.get_role_by_name(session, ROLE_DRIVER)
    await session.delete(role)
    await session.commit()

    await on_register(FakeCallback("reg:start"), state, session, access_guest)
    await _walk_through(state, session, company)
    callback = FakeCallback("reg:confirm", user=FakeUser(STRANGER_ID))
    await step_confirm(callback, state, session, access_guest)

    assert await repository.count_employees(session) == 0
    assert ROLE_DRIVER in callback.message.answers[0]


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
    await state.set_state(Registration.phone2_ask)
    callback = FakeCallback(REG_PHONE2_NO)

    await step_phone2_no(callback, state, session)

    assert callback_data(callback.message.markups[0])[-1] == FORM_CANCEL


# ---------------------------------------------------------------------------
# Номер телефону
# ---------------------------------------------------------------------------


async def test_shared_contact_is_accepted(session, state, reference_data):
    """Основний шлях: користувач тисне «Поділитися номером»."""
    await state.set_state(Registration.phone)
    message = FakeMessage(
        contact=FakeContact("+380671112233", user_id=STRANGER_ID),
        user=FakeUser(STRANGER_ID),
    )

    await step_phone_shared(message, state)

    assert (await state.get_data())["phone_number"] == "+380671112233"
    assert await state.get_state() == Registration.phone2_ask


async def test_someone_elses_contact_is_refused(session, state, reference_data):
    """Telegram дозволяє надіслати чужий контакт зі списку — це не наш номер."""
    await state.set_state(Registration.phone)
    message = FakeMessage(
        contact=FakeContact("+380990000000", user_id=999999),
        user=FakeUser(STRANGER_ID),
    )

    await step_phone_shared(message, state)

    assert "phone_number" not in await state.get_data()
    assert await state.get_state() == Registration.phone
    assert "іншої людини" in message.answers[0]


async def test_phone_can_still_be_typed(session, state, reference_data):
    await state.set_state(Registration.phone)

    await step_phone(FakeMessage("+380671112233"), state)

    assert (await state.get_data())["phone_number"] == "+380671112233"
    assert await state.get_state() == Registration.phone2_ask


async def test_reply_cancel_button_stops_registration(session, state, reference_data):
    """Reply-клавіатура не має callback_data, тому скасування — за текстом."""
    await state.set_state(Registration.phone)
    message = FakeMessage(CANCEL_TEXT)

    await step_phone(message, state)

    assert await state.get_state() is None
    assert "скасовано" in message.answers[0]


async def test_second_phone_is_stored(session, state, access_guest, reference_data):
    company, position = reference_data
    await on_register(FakeCallback("reg:start"), state, session, access_guest)
    await _walk_through(
        state, session, company, position, second_phone="+380509998877"
    )
    await step_confirm(
        FakeCallback("reg:confirm", user=FakeUser(STRANGER_ID)),
        state, session, access_guest,
    )

    employee = await repository.get_employee_by_tg_id(session, STRANGER_ID)
    assert employee.phone_number == "+380671112233"
    assert employee.phone_number2 == "+380509998877"


async def test_second_phone_is_optional(session, state, access_guest, reference_data):
    company, position = reference_data
    await on_register(FakeCallback("reg:start"), state, session, access_guest)
    await _walk_through(state, session, company, position)
    await step_confirm(
        FakeCallback("reg:confirm", user=FakeUser(STRANGER_ID)),
        state, session, access_guest,
    )

    employee = await repository.get_employee_by_tg_id(session, STRANGER_ID)
    assert employee.phone_number2 is None


async def test_short_second_phone_keeps_state(session, state, reference_data):
    await state.set_state(Registration.phone2)
    message = FakeMessage("12")

    await step_phone2(message, state, session)

    assert await state.get_state() == Registration.phone2
    assert "Номер має бути" in message.answers[0]


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


async def _new_company(session, state, access_admin, *, chat: str | None = None):
    await on_company_add(
        FakeCallback("company:add", user=FakeUser(ADMIN_ID)), state, access_admin
    )
    await company_name(FakeMessage("ТОВ Нова"), state)
    await company_tax_id(FakeMessage("87654321"), state, session)
    await company_address(FakeMessage("Львів, вул. Січових Стрільців, 5"), state)

    if chat is None:
        callback = FakeCallback(COMPANY_CHAT_SKIP, user=FakeUser(ADMIN_ID))
        await company_chat_skip(callback, state, session, access_admin)
        return callback.message
    message = FakeMessage(chat)
    await company_chat(message, state, session, access_admin)
    return message


async def test_main_admin_creates_a_company(session, state, access_admin):
    message = await _new_company(session, state, access_admin, chat="-1001234567890")

    companies = await repository.list_companies(session)
    assert [c.name for c in companies] == ["ТОВ Нова"]
    assert companies[0].tax_id == "87654321"
    assert companies[0].company_chat_id == -1001234567890
    assert await state.get_state() is None
    assert "додано" in message.answers[-1]


async def test_working_chat_can_be_skipped(session, state, access_admin):
    """Чат могли ще не створити — це не має блокувати заведення компанії."""
    message = await _new_company(session, state, access_admin)

    companies = await repository.list_companies(session)
    assert companies[0].company_chat_id is None
    assert "не вказано" in message.answers[-1]


async def test_garbage_chat_id_keeps_the_step(session, state, access_admin):
    await on_company_add(
        FakeCallback("company:add", user=FakeUser(ADMIN_ID)), state, access_admin
    )
    await company_name(FakeMessage("ТОВ Нова"), state)
    await company_tax_id(FakeMessage("87654321"), state, session)
    await company_address(FakeMessage("Львів, вул. Січових Стрільців, 5"), state)

    message = FakeMessage("моя група")
    await company_chat(message, state, session, access_admin)

    assert await state.get_state() == CompanyForm.chat
    assert "Не схоже на id чату" in message.answers[0]
    assert await repository.list_companies(session) == []


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
