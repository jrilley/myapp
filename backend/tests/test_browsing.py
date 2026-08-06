"""Тести перегляду й редагування транспорту та працівників.

Головне тут — межа компанії: адміністратор компанії має бачити лише свою,
навіть якщо підставить чужий id у callback_data.
"""

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app import repository
from app.bot.access import (
    DENIED as NO_RIGHTS,
    ROLE_COMPANY_ADMIN,
    ROLE_MAIN_ADMIN,
    ROLE_DRIVER,
    Access,
)
from app.bot.handlers.management import on_company_card, on_company_employees
from app.bot.handlers.vehicles import (
    edit_make_model,
    edit_plate,
    on_company_vehicles,
    on_my_vehicles,
    on_vehicle_card,
    on_vehicle_edit,
    on_vehicle_list,
)
from app.bot.keyboards import (
    COMPANY_CARD_PREFIX,
    COMPANY_EMPLOYEES_PREFIX,
    COMPANY_VEHICLES_PREFIX,
    MENU_MY_VEHICLES,
    VEHICLE_CARD_PREFIX,
    VEHICLE_EDIT_PREFIX,
    VEHICLE_LIST_PREFIX,
)
from app.bot.states import VehicleEdit
from app.models import Company, Employee, Position, Role, Vehicle
from tests.conftest import (
    ADMIN_ID,
    OWNER_ID,
    FakeCallback,
    FakeMessage,
    FakeUser,
    callback_data,
    permissions_for,
)


@pytest.fixture
def state() -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=ADMIN_ID)
    )


@pytest.fixture
async def two_companies(session):
    """Дві компанії з власним транспортом і працівниками."""
    ours = Company(name="Alebor IT", tax_id="000000", address="VST")
    theirs = Company(name="ТОВ Чужа", tax_id="99999999", address="Львів")
    position = Position(id=1, position="Водій")
    session.add_all(
        [
            ours, theirs, position,
            Role(id=1, role=ROLE_MAIN_ADMIN),
            Role(id=2, role=ROLE_COMPANY_ADMIN),
            Role(id=3, role=ROLE_DRIVER),
        ]
    )
    await session.commit()

    session.add_all([
        Vehicle(type="Тягач", make_model="Volvo FH",
                license_plate="AA1111AA", owner_company_id=ours.id),
        Vehicle(type="Тягач", make_model="Scania R450",
                license_plate="BB2222BB", owner_company_id=theirs.id),
        Vehicle(type="Зерновоз", make_model="Schmitz SKO",
                license_plate="CC3333CC", owner_company_id=ours.id),
    ])
    await repository.create_employee(
        session, tg_id=OWNER_ID, company_id=ours.id, fullname="Наш Працівник",
        phone_number="+380000000001", position_id=1, role_id=3,
    )
    await repository.create_employee(
        session, tg_id=555000, company_id=theirs.id, fullname="Чужий Працівник",
        phone_number="+380000000002", position_id=1, role_id=3,
    )
    await session.commit()
    return ours, theirs


@pytest.fixture
def company_admin(two_companies):
    """Адміністратор першої компанії."""
    ours, _ = two_companies
    employee = Employee(
        tg_id=OWNER_ID, company_id=ours.id, fullname="Адмін Компанії",
        phone_number="+380000000000", position_id=1, role_id=2,
    )
    employee.role = Role(id=2, role=ROLE_COMPANY_ADMIN)
    return Access(
        telegram_user_id=OWNER_ID,
        employee=employee,
        permissions=permissions_for(ROLE_COMPANY_ADMIN),
    )


# ---------------------------------------------------------------------------
# Навігація головного адміністратора
# ---------------------------------------------------------------------------


async def test_company_card_offers_vehicles_and_employees(
    session, state, access_admin, two_companies
):
    ours, _ = two_companies
    callback = FakeCallback(f"{COMPANY_CARD_PREFIX}:{ours.id}")

    await on_company_card(callback, state, session, access_admin)

    data = callback_data(callback.message.markups[0])
    assert f"{COMPANY_VEHICLES_PREFIX}:{ours.id}" in data
    assert f"{COMPANY_EMPLOYEES_PREFIX}:{ours.id}" in data
    assert "Alebor IT" in callback.message.answers[0]


async def test_vehicle_list_is_scoped_to_the_company(
    session, state, access_admin, two_companies
):
    ours, _ = two_companies
    callback = FakeCallback(f"{VEHICLE_LIST_PREFIX}:truck:{ours.id}:0")

    await on_vehicle_list(callback, state, session, access_admin)

    labels = [
        b.text for row in callback.message.markups[0].inline_keyboard for b in row
    ]
    assert "Тягач · Volvo FH - AA1111AA" in labels
    assert "Тягач · Scania R450 - BB2222BB" not in labels  # чужа машина


async def test_employee_button_shows_position_and_name(
    session, state, access_admin, two_companies
):
    ours, _ = two_companies
    callback = FakeCallback(f"{COMPANY_EMPLOYEES_PREFIX}:{ours.id}")

    await on_company_employees(callback, state, session, access_admin)

    labels = [
        b.text for row in callback.message.markups[0].inline_keyboard for b in row
    ]
    assert "Водій, Наш Працівник" in labels
    assert "Водій, Чужий Працівник" not in labels


async def test_trailers_are_listed_separately(
    session, state, access_admin, two_companies
):
    ours, _ = two_companies
    callback = FakeCallback(f"{VEHICLE_LIST_PREFIX}:trailer:{ours.id}:0")

    await on_vehicle_list(callback, state, session, access_admin)

    labels = [
        b.text for row in callback.message.markups[0].inline_keyboard for b in row
    ]
    assert "Зерновоз · Schmitz SKO - CC3333CC" in labels
    assert "Тягач · Volvo FH - AA1111AA" not in labels


# ---------------------------------------------------------------------------
# Межа компанії
# ---------------------------------------------------------------------------


async def test_company_admin_sees_only_own_vehicles(
    session, state, company_admin, two_companies
):
    """Підставляємо id чужої компанії — має показати свою."""
    _, theirs = two_companies
    callback = FakeCallback(
        f"{VEHICLE_LIST_PREFIX}:truck:{theirs.id}:0", user=FakeUser(OWNER_ID)
    )

    await on_vehicle_list(callback, state, session, company_admin)

    labels = [
        b.text for row in callback.message.markups[0].inline_keyboard for b in row
    ]
    assert "Тягач · Volvo FH - AA1111AA" in labels
    assert "Тягач · Scania R450 - BB2222BB" not in labels


async def test_company_admin_sees_only_own_employees(
    session, state, company_admin, two_companies
):
    _, theirs = two_companies
    callback = FakeCallback(
        f"{COMPANY_EMPLOYEES_PREFIX}:{theirs.id}", user=FakeUser(OWNER_ID)
    )

    await on_company_employees(callback, state, session, company_admin)

    labels = [
        b.text for row in callback.message.markups[0].inline_keyboard for b in row
    ]
    assert "Водій, Наш Працівник" in labels
    assert "Водій, Чужий Працівник" not in labels


async def test_company_admin_cannot_open_a_foreign_vehicle(
    session, state, company_admin, two_companies
):
    foreign = await repository.get_vehicle_by_plate(session, "BB2222BB")
    callback = FakeCallback(
        f"{VEHICLE_CARD_PREFIX}:{foreign.id}", user=FakeUser(OWNER_ID)
    )

    await on_vehicle_card(callback, state, session, company_admin)

    assert callback.answered == [NO_RIGHTS]
    assert not callback.message.answers


async def test_company_admin_skips_company_selection(
    session, state, company_admin, two_companies
):
    ours, _ = two_companies
    callback = FakeCallback(MENU_MY_VEHICLES, user=FakeUser(OWNER_ID))

    await on_my_vehicles(callback, state, company_admin)

    data = callback_data(callback.message.markups[0])
    assert f"{VEHICLE_LIST_PREFIX}:truck:{ours.id}:0" in data


async def test_company_card_shows_only_your_own(
    session, state, company_admin, two_companies
):
    """Адміністратор компанії має R на компанію — але лише на свою.
    Підставлений id чужої має привести його до власної картки."""
    _, theirs = two_companies
    callback = FakeCallback(f"{COMPANY_CARD_PREFIX}:{theirs.id}", user=FakeUser(OWNER_ID))

    await on_company_card(callback, state, session, company_admin)

    assert "Alebor IT" in callback.message.answers[0]
    assert "ТОВ Чужа" not in callback.message.answers[0]


# ---------------------------------------------------------------------------
# Редагування транспорту
# ---------------------------------------------------------------------------


async def test_vehicle_card_shows_details(session, state, access_admin, two_companies):
    truck = await repository.get_vehicle_by_plate(session, "AA1111AA")
    callback = FakeCallback(f"{VEHICLE_CARD_PREFIX}:{truck.id}")

    await on_vehicle_card(callback, state, session, access_admin)

    text = callback.message.answers[0]
    assert "Volvo" in text and "FH" in text and "AA1111AA" in text
    assert "Alebor IT" in text


async def test_editing_make_model_updates_the_row(
    session, state, access_admin, two_companies
):
    truck = await repository.get_vehicle_by_plate(session, "AA1111AA")
    callback = FakeCallback(f"{VEHICLE_EDIT_PREFIX}:makemodel:{truck.id}")
    await on_vehicle_edit(callback, state, session, access_admin)
    assert await state.get_state() == VehicleEdit.make_model

    await edit_make_model(FakeMessage("Renault Magnum"), state, session, access_admin)

    updated = await repository.get_vehicle(session, truck.id)
    assert updated.make_model == "Renault Magnum"
    assert await state.get_state() is None


async def test_editing_plate_rejects_a_taken_number(
    session, state, access_admin, two_companies
):
    truck = await repository.get_vehicle_by_plate(session, "AA1111AA")
    await state.set_state(VehicleEdit.license_plate)
    await state.update_data(kind="truck", vehicle_id=truck.id)
    message = FakeMessage("BB2222BB")  # номер іншого тягача

    await edit_plate(message, state, session, access_admin)

    assert await state.get_state() == VehicleEdit.license_plate
    assert "уже є" in message.answers[0]


async def test_keeping_own_plate_is_not_a_conflict(
    session, state, access_admin, two_companies
):
    """Збереження власного номера без змін не має вважатись дублікатом."""
    truck = await repository.get_vehicle_by_plate(session, "AA1111AA")
    await state.set_state(VehicleEdit.license_plate)
    await state.update_data(kind="truck", vehicle_id=truck.id)

    await edit_plate(FakeMessage("aa1111aa"), state, session, access_admin)

    updated = await repository.get_vehicle(session, truck.id)
    assert updated.license_plate == "AA1111AA"
    assert await state.get_state() is None


async def test_company_admin_can_edit_own_vehicle(
    session, state, company_admin, two_companies
):
    truck = await repository.get_vehicle_by_plate(session, "AA1111AA")
    callback = FakeCallback(
        f"{VEHICLE_EDIT_PREFIX}:makemodel:{truck.id}", user=FakeUser(OWNER_ID)
    )

    await on_vehicle_edit(callback, state, session, company_admin)

    assert await state.get_state() == VehicleEdit.make_model


async def test_ordinary_user_cannot_browse_vehicles(session, state, access):
    callback = FakeCallback(f"{COMPANY_VEHICLES_PREFIX}:1", user=FakeUser(OWNER_ID))

    await on_company_vehicles(callback, state, access)

    assert callback.answered == [NO_RIGHTS]
