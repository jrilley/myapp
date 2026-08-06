"""Тести додавання тягачів і причепів.

Ключова відмінність між ролями — звідки береться компанія: головний адмін
обирає її зі списку, адміністратору компанії вона береться з його запису
в employees, і підмінити її він не може.
"""

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app import repository
from app.bot.access import (
    DENIED as NO_RIGHTS,
    ROLE_COMPANY_ADMIN,
    ROLE_LOGIST,
    ROLE_MANAGER,
    Access,
)
from app.bot.handlers.vehicles import (
    on_add_vehicle,
    on_vehicle_delete,
    on_vehicle_delete_confirm,
    step_brand,
    step_company,
    step_confirm,
    step_kind,
    step_license_plate,
    step_model,
)
from app.bot.keyboards import (
    MENU_VEHICLE_ADD,
    VEHICLE_DELETE_CONFIRM,
    VEHICLE_DELETE_PREFIX,
    VEHICLE_COMPANY_PREFIX,
    VEHICLE_CONFIRM,
    VEHICLE_TYPE_PREFIX,
)
from app.bot.states import VehicleForm
from app.models import Company, Employee, Role, Truck
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


@pytest.fixture
def state() -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=ADMIN_ID)
    )


@pytest.fixture
async def companies(session):
    first = Company(name="Alebor IT", tax_id="000000", address="VST")
    second = Company(name="ТОВ Ромашка", tax_id="12345678", address="Київ")
    session.add_all([first, second])
    await session.commit()
    return first, second


@pytest.fixture
async def company_admin(session, companies):
    """Адміністратор компанії, прив'язаний до другої компанії.

    Employee і Role навмисно транзієнтні, як у conftest.make_access: Access
    читає лише role.role і company_id. Якби Role була в сесії, autoflush
    спробував би записати й цього співробітника.
    """
    _, second = companies
    employee = Employee(
        tg_id=OWNER_ID,
        company_id=second.id,
        fullname="Адмін Компанії",
        phone_number="+380000000000",
        position_id=1,
        role_id=2,
    )
    employee.role = Role(id=2, role=ROLE_COMPANY_ADMIN)
    return Access(
        telegram_user_id=OWNER_ID,
        employee=employee,
        permissions=permissions_for(ROLE_COMPANY_ADMIN),
    ), second


async def _fill_fields(state, session, *, plate="AA1234BB"):
    await step_brand(FakeMessage("Volvo"), state)
    await step_model(FakeMessage("FH16"), state)
    await step_license_plate(FakeMessage(plate), state, session)


# ---------------------------------------------------------------------------
# Головний адміністратор
# ---------------------------------------------------------------------------


async def test_main_admin_picks_a_company(session, state, access_admin, companies):
    first, _ = companies
    await on_add_vehicle(FakeCallback(MENU_VEHICLE_ADD), state, access_admin)
    kind = FakeCallback(f"{VEHICLE_TYPE_PREFIX}:truck")

    await step_kind(kind, state, session, access_admin)

    assert await state.get_state() == VehicleForm.company
    data = callback_data(kind.message.markups[0])
    assert f"{VEHICLE_COMPANY_PREFIX}:{first.id}" in data


async def test_company_button_shows_name_and_tax_id(
    session, state, access_admin, companies
):
    await state.set_state(VehicleForm.kind)
    kind = FakeCallback(f"{VEHICLE_TYPE_PREFIX}:truck")

    await step_kind(kind, state, session, access_admin)

    labels = [b.text for row in kind.message.markups[0].inline_keyboard for b in row]
    assert "Alebor IT - 000000" in labels


async def test_main_admin_creates_a_truck(session, state, access_admin, companies):
    first, _ = companies
    await on_add_vehicle(FakeCallback(MENU_VEHICLE_ADD), state, access_admin)
    await step_kind(
        FakeCallback(f"{VEHICLE_TYPE_PREFIX}:truck"), state, session, access_admin
    )
    await step_company(
        FakeCallback(f"{VEHICLE_COMPANY_PREFIX}:{first.id}"), state, session, access_admin
    )
    await _fill_fields(state, session)

    await step_confirm(FakeCallback(VEHICLE_CONFIRM), state, session, access_admin)

    truck = await repository.get_vehicle_by_plate(session, "truck", "AA1234BB")
    assert truck is not None
    assert truck.brand == "Volvo"
    assert truck.model == "FH16"
    assert truck.company_id == first.id
    assert await state.get_state() is None


async def test_trailer_goes_to_its_own_table(session, state, access_admin, companies):
    first, _ = companies
    await state.set_state(VehicleForm.kind)
    await step_kind(
        FakeCallback(f"{VEHICLE_TYPE_PREFIX}:trailer"), state, session, access_admin
    )
    await step_company(
        FakeCallback(f"{VEHICLE_COMPANY_PREFIX}:{first.id}"), state, session, access_admin
    )
    await _fill_fields(state, session, plate="BB5678CC")
    await step_confirm(FakeCallback(VEHICLE_CONFIRM), state, session, access_admin)

    assert await repository.get_vehicle_by_plate(session, "trailer", "BB5678CC")
    assert await repository.get_vehicle_by_plate(session, "truck", "BB5678CC") is None


async def test_confirmation_shows_what_was_entered(
    session, state, access_admin, companies
):
    first, _ = companies
    await state.set_state(VehicleForm.kind)
    await step_kind(
        FakeCallback(f"{VEHICLE_TYPE_PREFIX}:truck"), state, session, access_admin
    )
    await step_company(
        FakeCallback(f"{VEHICLE_COMPANY_PREFIX}:{first.id}"), state, session, access_admin
    )
    await step_brand(FakeMessage("Scania"), state)
    await step_model(FakeMessage("R450"), state)
    message = FakeMessage("CC9012DD")

    await step_license_plate(message, state, session)

    summary = message.answers[0]
    for expected in ("Тягач", "Scania", "R450", "CC9012DD", "Alebor IT"):
        assert expected in summary


async def test_no_companies_stops_the_flow(session, state, access_admin):
    await state.set_state(VehicleForm.kind)
    kind = FakeCallback(f"{VEHICLE_TYPE_PREFIX}:truck")

    await step_kind(kind, state, session, access_admin)

    assert await state.get_state() is None
    assert "хоча б одну компанію" in kind.message.answers[0]


# ---------------------------------------------------------------------------
# Адміністратор компанії
# ---------------------------------------------------------------------------


async def test_company_admin_skips_the_company_step(session, state, company_admin):
    access, company = company_admin
    await on_add_vehicle(FakeCallback(MENU_VEHICLE_ADD), state, access)
    kind = FakeCallback(f"{VEHICLE_TYPE_PREFIX}:truck", user=FakeUser(OWNER_ID))

    await step_kind(kind, state, session, access)

    # Компанію не питаємо — одразу поля.
    assert await state.get_state() == VehicleForm.brand
    assert (await state.get_data())["company_id"] == company.id


async def test_company_admin_vehicle_is_bound_to_own_company(
    session, state, company_admin
):
    access, company = company_admin
    await state.set_state(VehicleForm.kind)
    await step_kind(
        FakeCallback(f"{VEHICLE_TYPE_PREFIX}:truck", user=FakeUser(OWNER_ID)),
        state, session, access,
    )
    await _fill_fields(state, session, plate="DD3456EE")

    await step_confirm(
        FakeCallback(VEHICLE_CONFIRM, user=FakeUser(OWNER_ID)), state, session, access
    )

    truck = await repository.get_vehicle_by_plate(session, "truck", "DD3456EE")
    assert truck.company_id == company.id


# ---------------------------------------------------------------------------
# Валідація та права
# ---------------------------------------------------------------------------


async def test_duplicate_plate_is_caught_before_confirmation(
    session, state, access_admin, companies
):
    """Номер унікальний. Ловимо на вводі, а не помилкою БД після підтвердження."""
    first, _ = companies
    session.add(Truck(brand="MAN", model="TGX", license_plate="EE7890FF"))
    await session.commit()

    await state.set_state(VehicleForm.license_plate)
    await state.update_data(kind="truck", company_id=first.id, brand="X", model="Y")
    message = FakeMessage("EE7890FF")

    await step_license_plate(message, state, session)

    assert await state.get_state() == VehicleForm.license_plate
    assert "уже є" in message.answers[0]


async def test_plate_taken_while_form_was_open(session, state, access_admin, companies):
    first, _ = companies
    await state.set_state(VehicleForm.confirm)
    await state.update_data(
        kind="truck", company_id=first.id, brand="DAF", model="XF",
        license_plate="FF1122GG",
    )
    session.add(Truck(brand="Інший", model="Інша", license_plate="FF1122GG"))
    await session.commit()

    callback = FakeCallback(VEHICLE_CONFIRM)
    await step_confirm(callback, state, session, access_admin)

    trucks = await repository.get_vehicle_by_plate(session, "truck", "FF1122GG")
    assert trucks.brand == "Інший"  # наш запис не перезаписав чужий
    assert "уже є" in callback.message.answers[0]


async def test_plate_is_normalised_to_upper_case(
    session, state, access_admin, companies
):
    first, _ = companies
    await state.set_state(VehicleForm.license_plate)
    await state.update_data(kind="truck", company_id=first.id, brand="X", model="Y")

    await step_license_plate(FakeMessage("aa9999bb"), state, session)

    assert (await state.get_data())["license_plate"] == "AA9999BB"


@pytest.mark.parametrize("plate", ["AB", "A" * 20])
async def test_plate_length_is_checked(
    session, state, access_admin, companies, plate
):
    first, _ = companies
    await state.set_state(VehicleForm.license_plate)
    await state.update_data(kind="truck", company_id=first.id, brand="X", model="Y")
    message = FakeMessage(plate)

    await step_license_plate(message, state, session)

    assert await state.get_state() == VehicleForm.license_plate
    assert "Номер має бути" in message.answers[0]


async def test_unknown_vehicle_type_is_rejected(session, state, access_admin):
    await state.set_state(VehicleForm.kind)
    callback = FakeCallback(f"{VEHICLE_TYPE_PREFIX}:bicycle")

    await step_kind(callback, state, session, access_admin)

    assert callback.answered == ["Невідомий тип"]
    assert await state.get_state() == VehicleForm.kind


async def test_ordinary_user_cannot_add_a_vehicle(session, state, access):
    """Кнопки не видно, але callback_data можна переслати."""
    callback = FakeCallback(MENU_VEHICLE_ADD, user=FakeUser(OWNER_ID))

    await on_add_vehicle(callback, state, access)

    assert await state.get_state() is None
    assert callback.answered == [NO_RIGHTS]


# ---------------------------------------------------------------------------
# Видалення
# ---------------------------------------------------------------------------


async def test_delete_asks_before_erasing(session, state, access_admin, companies):
    """Рядок транспорту стирається назовсім, тож питаємо."""
    first, _ = companies
    truck = await repository.create_vehicle(
        session, "truck", brand="Volvo", model="FH",
        license_plate="AA1111AA", company_id=first.id,
    )
    callback = FakeCallback(
        f"{VEHICLE_DELETE_PREFIX}:truck:{truck.id}", user=FakeUser(ADMIN_ID)
    )

    await on_vehicle_delete(callback, session, access_admin)

    assert "Видалити" in callback.message.answers[0]
    # Поки не підтвердили — машина на місці.
    assert await repository.get_vehicle(session, "truck", truck.id) is not None


async def test_confirmed_delete_frees_the_plate(
    session, state, access_admin, companies
):
    """М'яке видалення тут нічого не дало б: номер лишався б зайнятим."""
    first, _ = companies
    truck = await repository.create_vehicle(
        session, "truck", brand="Volvo", model="FH",
        license_plate="AA1111AA", company_id=first.id,
    )
    callback = FakeCallback(
        f"{VEHICLE_DELETE_CONFIRM}:truck:{truck.id}", user=FakeUser(ADMIN_ID)
    )

    await on_vehicle_delete_confirm(callback, state, session, access_admin)

    assert await repository.get_vehicle(session, "truck", truck.id) is None
    assert await repository.get_vehicle_by_plate(session, "truck", "AA1111AA") is None


async def test_logist_may_add_but_not_delete(session, state, companies):
    """У логіста на транспорт C,R,E — і жодного D."""
    first, _ = companies
    truck = await repository.create_vehicle(
        session, "truck", brand="Volvo", model="FH",
        license_plate="AA1111AA", company_id=first.id,
    )
    access = make_access(OWNER_ID, role=ROLE_LOGIST, company_id=first.id)

    callback = FakeCallback(
        f"{VEHICLE_DELETE_PREFIX}:truck:{truck.id}", user=FakeUser(OWNER_ID)
    )
    await on_vehicle_delete(callback, session, access)

    assert callback.answered == [NO_RIGHTS]
    assert await repository.get_vehicle(session, "truck", truck.id) is not None


async def test_manager_cannot_reach_vehicles_at_all(session, state, companies):
    first, _ = companies
    access = make_access(OWNER_ID, role=ROLE_MANAGER, company_id=first.id)
    callback = FakeCallback(MENU_VEHICLE_ADD, user=FakeUser(OWNER_ID))

    await on_add_vehicle(callback, state, access)

    assert callback.answered == [NO_RIGHTS]
    assert await state.get_state() is None
