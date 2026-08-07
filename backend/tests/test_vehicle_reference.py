"""Тести довідників транспорту.

Вид і марка більше не поля машини, а окремі таблиці. Головне тут — хто їх
поповнює: види додає лише головний адміністратор, марку — той, хто заводить
машину, бо інакше він упирався б у список і чекав.
"""

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app import repository
from app.bot.access import MAIN_ADMIN_ONLY, ROLE_LOGIST
from app.bot.handlers.management import (
    on_vehicle_type_add,
    on_vehicle_type_card,
    on_vehicle_types,
    vehicle_type_flag,
    vehicle_type_name,
)
from app.bot.handlers.vehicles import step_mark_add, step_mark_name, step_mark_pick
from app.bot.keyboards import (
    MENU_VEHICLE_TYPES,
    VEHICLE_MARK_ADD,
    VEHICLE_MARK_PREFIX,
    VTYPE_ADD,
    VTYPE_CARD_PREFIX,
    VTYPE_FLAG_PREFIX,
)
from app.bot.states import VehicleForm, VehicleTypeForm
from app.models import Company, Vehicle
from tests.conftest import (
    ADMIN_ID,
    OWNER_ID,
    FakeCallback,
    FakeMessage,
    FakeUser,
    callback_data,
    make_access,
    seed_vehicle_mark,
    seed_vehicle_types,
)


@pytest.fixture
def state() -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=ADMIN_ID)
    )


# ---------------------------------------------------------------------------
# Види — тільки головний адміністратор
# ---------------------------------------------------------------------------


async def test_a_new_type_needs_the_tractor_answer(session, state, access_admin):
    """Назва не каже, тягач це чи причіп, — а від відповіді залежить, у якій
    половині списку машина опиниться."""
    await on_vehicle_type_add(FakeCallback(VTYPE_ADD), state, access_admin)
    await vehicle_type_name(FakeMessage("Сідловий тягач"), state, session)

    assert await state.get_state() == VehicleTypeForm.is_tractor
    # Доки не відповіли — у довіднику нічого немає.
    assert await repository.get_vehicle_type_by_name(session, "Сідловий тягач") is None

    await vehicle_type_flag(
        FakeCallback(f"{VTYPE_FLAG_PREFIX}:1"), state, session, access_admin
    )

    created = await repository.get_vehicle_type_by_name(session, "Сідловий тягач")
    assert created.is_tractor
    assert await state.get_state() is None


async def test_a_new_trailer_type_is_not_a_tractor(session, state, access_admin):
    await on_vehicle_type_add(FakeCallback(VTYPE_ADD), state, access_admin)
    await vehicle_type_name(FakeMessage("Скотовоз"), state, session)
    await vehicle_type_flag(
        FakeCallback(f"{VTYPE_FLAG_PREFIX}:0"), state, session, access_admin
    )

    created = await repository.get_vehicle_type_by_name(session, "Скотовоз")
    assert not created.is_tractor


async def test_a_duplicate_type_is_refused(session, state, access_admin):
    await seed_vehicle_types(session)
    await on_vehicle_type_add(FakeCallback(VTYPE_ADD), state, access_admin)
    message = FakeMessage("Зерновоз")

    await vehicle_type_name(message, state, session)

    assert "уже є" in message.answers[0]
    assert await state.get_state() == VehicleTypeForm.name


async def test_only_the_main_admin_reaches_the_types(session, state):
    """Кнопки не видно, але callback_data можна переслати."""
    access = make_access(OWNER_ID, role=ROLE_LOGIST)
    callback = FakeCallback(MENU_VEHICLE_TYPES, user=FakeUser(OWNER_ID))

    await on_vehicle_types(callback, state, session, access)

    assert callback.answered == [MAIN_ADMIN_ONLY]


async def test_only_the_main_admin_adds_a_type(session, state):
    access = make_access(OWNER_ID, role=ROLE_LOGIST)
    callback = FakeCallback(VTYPE_ADD, user=FakeUser(OWNER_ID))

    await on_vehicle_type_add(callback, state, access)

    assert callback.answered == [MAIN_ADMIN_ONLY]
    assert await state.get_state() is None


async def test_the_list_marks_tractors(session, state, access_admin):
    await seed_vehicle_types(session)
    callback = FakeCallback(MENU_VEHICLE_TYPES, user=FakeUser(ADMIN_ID))

    await on_vehicle_types(callback, state, session, access_admin)

    labels = [
        b.text
        for row in callback.message.markups[-1].inline_keyboard
        for b in row
    ]
    assert "🚛 Тягач" in labels
    assert "🚚 Зерновоз" in labels


async def test_the_card_counts_vehicles_of_that_type(session, state, access_admin):
    types = await seed_vehicle_types(session)
    mark = await seed_vehicle_mark(session, "Volvo FH")
    company = Company(name="Alebor IT", tax_id="000000", address="VST")
    session.add(company)
    await session.commit()
    session.add(
        Vehicle(
            type_id=types["Тягач"].id, mark_id=mark.id,
            license_plate="AA1111AA", owner_company_id=company.id,
        )
    )
    await session.commit()

    callback = FakeCallback(
        f"{VTYPE_CARD_PREFIX}:{types['Тягач'].id}", user=FakeUser(ADMIN_ID)
    )
    await on_vehicle_type_card(callback, state, session, access_admin)

    text = callback.message.answers[0]
    assert "Тягач" in text
    assert "Машин цього виду: 1" in text


# ---------------------------------------------------------------------------
# Марки — поповнює той, хто заводить машину
# ---------------------------------------------------------------------------


async def test_a_new_mark_lands_in_the_reference(session, state):
    """Довідник росте сам: інакше логіст із новою машиною чекав би на адміна."""
    await state.set_state(VehicleForm.mark_name)

    await step_mark_name(FakeMessage("Renault Magnum"), state, session)

    created = await repository.get_vehicle_mark_by_name(session, "Renault Magnum")
    assert created is not None
    assert (await state.get_data())["mark_id"] == created.id
    assert await state.get_state() == VehicleForm.license_plate


async def test_an_existing_mark_is_reused_not_duplicated(session, state):
    """Двічі введена та сама назва — один рядок: довідник, у якому «Volvo FH»
    лежить двічі, не довідник."""
    first = await seed_vehicle_mark(session, "Volvo FH")
    await state.set_state(VehicleForm.mark_name)

    await step_mark_name(FakeMessage("Volvo FH"), state, session)

    assert (await state.get_data())["mark_id"] == first.id
    marks = await repository.list_vehicle_marks(session)
    assert [m.name for m in marks] == ["Volvo FH"]


async def test_the_mark_list_offers_adding_a_new_one(session, state):
    await seed_vehicle_mark(session, "Volvo FH")
    await state.set_state(VehicleForm.mark)
    callback = FakeCallback(VEHICLE_MARK_ADD)

    await step_mark_add(callback, state)

    assert await state.get_state() == VehicleForm.mark_name


async def test_picking_a_mark_skips_typing(session, state):
    mark = await seed_vehicle_mark(session, "Schmitz SKO24")
    await state.set_state(VehicleForm.mark)

    await step_mark_pick(
        FakeCallback(f"{VEHICLE_MARK_PREFIX}:{mark.id}"), state, session
    )

    assert (await state.get_data())["mark_id"] == mark.id
    assert await state.get_state() == VehicleForm.license_plate


async def test_an_unknown_mark_is_refused(session, state):
    await state.set_state(VehicleForm.mark)
    callback = FakeCallback(f"{VEHICLE_MARK_PREFIX}:9999")

    await step_mark_pick(callback, state, session)

    assert callback.answered == ["Невідома марка"]
    assert "mark_id" not in await state.get_data()


async def test_the_trip_form_lists_trailer_kinds_from_the_reference(session):
    """Види причепів у рейсі — з того самого довідника, без тягачів."""
    await seed_vehicle_types(session)

    trailers = await repository.list_vehicle_types(session, tractors=False)

    names = [t.name for t in trailers]
    assert "Зерновоз" in names
    assert "Тягач" not in names


async def test_the_pick_keyboard_carries_reference_ids(session, state, access_admin):
    """У callback_data їде id рядка, а не номер у списку: довідник
    поповнюють люди, і позиція в ньому не є чимось сталим."""
    types = await seed_vehicle_types(session)
    callback = FakeCallback(MENU_VEHICLE_TYPES, user=FakeUser(ADMIN_ID))

    await on_vehicle_types(callback, state, session, access_admin)

    data = callback_data(callback.message.markups[-1])
    assert f"{VTYPE_CARD_PREFIX}:{types['Тягач'].id}" in data
