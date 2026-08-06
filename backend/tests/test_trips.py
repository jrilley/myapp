"""Тести рейсів.

Головне тут — дві речі. Перша: замовник і логіст беруться з того, хто
заповнює форму, а не з того, що прийшло в callback_data. Друга: межа
видимості — головний адмін бачить усі рейси, адміністратор компанії — рейси
своєї компанії, звичайний користувач — лише власні.
"""

from datetime import datetime
from types import SimpleNamespace

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app import repository
from app.bot.access import (
    ROLE_COMPANY_ADMIN,
    ROLE_DRIVER,
    ROLE_LOGIST,
    ROLE_MAIN_ADMIN,
    ROLE_OPERATOR,
    Access,
)
from app.bot.actions import render_trips
from app.bot.handlers.common import on_page
from app.bot.access import DENIED as NO_RIGHTS
from app.bot.handlers.trips import (
    DENIED,
    edit_driver_manual,
    edit_driver_name,
    edit_driver_phone,
    edit_choice,
    edit_datetime_button,
    edit_driver_pick,
    edit_status,
    on_calendar_nav,
    on_form_back,
    on_redo,
    on_redo_step,
    on_new_trip,
    on_trip_card,
    on_trip_delete,
    on_trip_edit,
    on_trip_field,
    edit_exporter,
    edit_value,
    step_arrival_date,
    step_client_manual,
    step_client_name,
    step_client_pick,
    step_confirm,
    step_driver_manual,
    step_driver_name,
    step_driver_phone,
    step_driver_pick,
    step_exporter,
    step_grain,
    step_grain_pick,
    step_trailer,
    step_trailer_plate,
    step_trailer_type,
    step_trailer_type_pick,
    step_truck,
    step_truck_plate,
    step_ttn,
)
from app.bot.keyboards import (
    MENU_TRIP_NEW,
    PAGE_PREFIX,
    PAGE_TRIPS,
    TRIP_CAL_PREFIX,
    TRIP_CHOICE_PREFIX,
    TRIP_CLEAR,
    TRIP_CLIENT_MANUAL,
    TRIP_CLIENT_PREFIX,
    TRIP_CONFIRM,
    TRIP_DATE_PREFIX,
    TRIP_DELETE_PREFIX,
    TRIP_DRIVER_MANUAL,
    TRIP_DRIVER_PREFIX,
    TRIP_EDIT_PREFIX,
    TRIP_EXPORTER_PREFIX,
    TRIP_FIELD_PREFIX,
    TRIP_BACK,
    TRIP_NOW,
    TRIP_REDO,
    TRIP_REDO_PREFIX,
    TRIP_SHOW_PREFIX,
    TRIP_STATUS_PREFIX,
)
from app.bot.states import TripEdit, TripForm
from app.models import TRIP_STATUS_NEW, TRIP_STATUSES, Company, Position, Role
from tests.conftest import (
    ADMIN_ID,
    OWNER_ID,
    STRANGER_ID,
    FakeCallback,
    FakeMessage,
    FakeUser,
    callback_data,
    permissions_for,
)

CHIEF_ID = 4004
DRIVER_ID = 5005
OUR_CHAT_ID = -1001111111111


@pytest.fixture
def state() -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=OWNER_ID)
    )


@pytest.fixture
async def world(session):
    """Дві компанії й чотири співробітники з різними ролями."""
    ours = Company(
        name="Alebor IT", tax_id="000000", address="VST",
        company_chat_id=OUR_CHAT_ID,
    )
    theirs = Company(name="ТОВ Чужа", tax_id="99999999", address="Львів")
    session.add_all(
        [
            ours, theirs,
            Role(id=1, role=ROLE_MAIN_ADMIN),
            Role(id=2, role=ROLE_COMPANY_ADMIN),
            Role(id=3, role=ROLE_DRIVER),
            Role(id=4, role=ROLE_LOGIST),
            Role(id=5, role=ROLE_OPERATOR),
            Position(id=1, position="Диспетчер"),
            Position(id=2, position="Логіст"),
        ]
    )
    await session.commit()

    async def employee(tg_id, company, name, phone, position_id, role_id):
        return await repository.create_employee(
            session, tg_id=tg_id, company_id=company.id, fullname=name,
            phone_number=phone, position_id=position_id, role_id=role_id,
        )

    return SimpleNamespace(
        ours=ours,
        theirs=theirs,
        logist=await employee(OWNER_ID, ours, "Марія Логіст", "+380501112233", 2, 4),
        boss=await employee(ADMIN_ID, ours, "Олег Логіст", "+380502223344", 2, 2),
        chief=await employee(CHIEF_ID, ours, "Головний Адмін", "+380509998877", 2, 1),
        driver=await employee(DRIVER_ID, ours, "Петро Водій", "+380507778899", 1, 3),
        outsider=await employee(
            STRANGER_ID, theirs, "Чужий Диспетчер", "+380503334455", 1, 3
        ),
    )


async def access_for(session, tg_id: int) -> Access:
    """Access із реального рядка employees — потрібні справжні id.

    Права беремо з тієї самої матриці, що йде в базу: інакше тести
    перевіряли б вигаданий набір.
    """
    employee = await repository.get_employee_by_tg_id(session, tg_id)
    return Access(
        telegram_user_id=tg_id,
        employee=employee,
        permissions=permissions_for(employee.role.role),
    )


@pytest.fixture
async def logist(session, world) -> Access:
    return await access_for(session, OWNER_ID)


@pytest.fixture
async def boss(session, world) -> Access:
    return await access_for(session, ADMIN_ID)


@pytest.fixture
async def chief(session, world) -> Access:
    return await access_for(session, CHIEF_ID)


@pytest.fixture
async def outsider(session, world) -> Access:
    return await access_for(session, STRANGER_ID)


async def make_trip(session, creator, exporter, **overrides):
    payload = {
        "ttn_num": "ТТН-1",
        "arrival_date": "2026-08-10",
        "owner_company_id": creator.company_id,
        "client_company_id": exporter.id,
        "client_company_name": exporter.name,
        "exporter_company_id": exporter.id,
        "created_by": creator.id,
        "logist_fullname": creator.fullname,
        "logist_phone_number": creator.phone_number,
        "logist_tg": creator.tg_id,
        "truck": "Volvo FH",
        "truck_license_plate": "AA1111AA",
        "trailer": "Schmitz SKO",
        "trailer_type": "зерновоз",
        "trailer_license_plate": "CC3333CC",
        "grain_type": "Пшениця",
        "driver_fullname": "Іван Водій",
        "driver_phone_number": "+380504445566",
    }
    payload.update(overrides)
    return await repository.create_trip(session, **payload)


async def fill_form_until_driver(state, session, access, exporter_id, *, grain="Пшениця"):
    """Анкета до кроку вибору водія. `grain=None` зупиняє перед культурою —
    щоб тест сам подав повідомлення й побачив список водіїв."""
    await on_new_trip(FakeCallback(MENU_TRIP_NEW, user=FakeUser(OWNER_ID)), state, access)
    await step_ttn(FakeMessage("ТТН-000123"), state, session)
    await step_arrival_date(FakeCallback(f"{TRIP_DATE_PREFIX}:2026-08-10"), state, session)
    await step_client_pick(
        FakeCallback(f"{TRIP_CLIENT_PREFIX}:{exporter_id}"), state, session
    )
    await step_exporter(
        FakeCallback(f"{TRIP_EXPORTER_PREFIX}:{exporter_id}"), state, session
    )
    await step_truck(FakeMessage("Volvo FH16"), state, session)
    await step_truck_plate(FakeMessage("aa1111aa"), state, session)
    await step_trailer(FakeMessage("Schmitz SKO24"), state, session)
    await step_trailer_type(FakeMessage("зерновоз"), state, session)
    await step_trailer_plate(FakeMessage("cc3333cc"), state, session)
    if grain is not None:
        await step_grain(FakeMessage(grain), state, session)


async def fill_form(state, session, access, **overrides):
    """Проходить анкету до підтвердження включно й повертає callback підтвердження."""
    steps = {
        "ttn": "ТТН-000123",
        "truck": "Volvo FH16",
        "truck_plate": "aa1111aa",
        "trailer": "Schmitz SKO24",
        "trailer_type": "зерновоз",
        "trailer_plate": "cc3333cc",
        "grain": "Пшениця 2 клас",
        "driver": "Іван Іванович Іваненко",
        "driver_phone": "+380504445566",
    }
    steps.update(overrides)
    exporter_id = overrides.get("exporter_id")

    await on_new_trip(FakeCallback(MENU_TRIP_NEW, user=FakeUser(OWNER_ID)), state, access)
    await step_ttn(FakeMessage(steps["ttn"]), state, session)
    await step_arrival_date(
        FakeCallback(f"{TRIP_DATE_PREFIX}:2026-08-10"), state, session
    )
    client_id = overrides.get("client_id", exporter_id)
    await step_client_pick(
        FakeCallback(f"{TRIP_CLIENT_PREFIX}:{client_id}"), state, session
    )
    await step_exporter(
        FakeCallback(f"{TRIP_EXPORTER_PREFIX}:{exporter_id}"), state, session
    )
    await step_truck(FakeMessage(steps["truck"]), state, session)
    await step_truck_plate(FakeMessage(steps["truck_plate"]), state, session)
    await step_trailer(FakeMessage(steps["trailer"]), state, session)
    await step_trailer_type(FakeMessage(steps["trailer_type"]), state, session)
    await step_trailer_plate(FakeMessage(steps["trailer_plate"]), state, session)
    await step_grain(FakeMessage(steps["grain"]), state, session)

    driver_id = overrides.get("driver_id")
    if driver_id is None:
        await step_driver_manual(FakeCallback(TRIP_DRIVER_MANUAL), state, session)
        await step_driver_name(FakeMessage(steps["driver"]), state, session)
        await step_driver_phone(FakeMessage(steps["driver_phone"]), state, session)
    else:
        await step_driver_pick(
            FakeCallback(f"{TRIP_DRIVER_PREFIX}:{driver_id}"), state, session
        )
    return FakeCallback(TRIP_CONFIRM, user=FakeUser(OWNER_ID))


# ---------------------------------------------------------------------------
# Створення
# ---------------------------------------------------------------------------


async def test_form_creates_a_trip_with_every_field(
    session, state, world, logist, publisher
):
    callback = await fill_form(state, session, logist, exporter_id=world.theirs.id)

    await step_confirm(callback, state, session, publisher, logist)

    trips, total = await repository.list_trips(session)
    assert total == 1
    trip = trips[0]
    assert trip.ttn_num == "ТТН-000123"
    assert trip.arrival_date == "2026-08-10"
    assert trip.truck == "Volvo FH16"
    assert trip.trailer_type == "зерновоз"
    assert trip.grain_type == "Пшениця 2 клас"
    assert trip.driver_fullname == "Іван Іванович Іваненко"
    # Номери зводяться до верхнього регістру, щоб не було двох написань.
    assert trip.truck_license_plate == "AA1111AA"
    assert trip.trailer_license_plate == "CC3333CC"
    assert await state.get_state() is None


async def test_owner_and_manager_come_from_the_creator(
    session, state, world, logist, publisher
):
    """Ці поля не питаються — підставити чужу компанію нічим."""
    callback = await fill_form(state, session, logist, exporter_id=world.theirs.id)

    await step_confirm(callback, state, session, publisher, logist)

    trips, _ = await repository.list_trips(session)
    trip = trips[0]
    # Власник — компанія творця; замовник — той, кого обрали.
    assert trip.owner_company_id == world.ours.id
    assert trip.client_company_id == world.theirs.id
    assert trip.exporter_company_id == world.theirs.id
    assert trip.created_by == world.logist.id
    assert trip.logist_fullname == "Марія Логіст"
    assert trip.logist_phone_number == "+380501112233"
    assert trip.logist_tg == OWNER_ID


async def test_new_trip_starts_empty_and_unaudited(
    session, state, world, logist, publisher
):
    callback = await fill_form(state, session, logist, exporter_id=world.ours.id)

    await step_confirm(callback, state, session, publisher, logist)

    trips, _ = await repository.list_trips(session)
    trip = trips[0]
    assert trip.status == TRIP_STATUS_NEW
    assert (trip.b_mass, trip.t_mass, trip.n_mass) == (0, 0, 0)
    assert trip.datetime_entry is None and trip.datetime_departure is None
    assert trip.edited_by is None and trip.updated_at is None
    assert trip.deleted_by is None and trip.deleted_at is None
    # created_at проставляє репозиторій — його неможливо забути.
    assert datetime.fromisoformat(trip.created_at).tzinfo is not None


async def test_unregistered_cannot_start_a_trip(state, access_guest):
    callback = FakeCallback(MENU_TRIP_NEW, user=FakeUser(STRANGER_ID))

    await on_new_trip(callback, state, access_guest)

    assert await state.get_state() is None
    assert callback.answered == [NO_RIGHTS]


async def test_driver_cannot_start_a_trip(session, state, world):
    """У водія на рейсах лише R: створення — не його справа."""
    driver_access = await access_for(session, DRIVER_ID)
    callback = FakeCallback(MENU_TRIP_NEW, user=FakeUser(DRIVER_ID))

    await on_new_trip(callback, state, driver_access)

    assert await state.get_state() is None
    assert callback.answered == [NO_RIGHTS]


async def test_bootstrap_admin_cannot_start_a_trip(state):
    """Вхід через ADMIN_TELEGRAM_IDS дає права, але не рядок у employees —
    а без нього нема ні компанії-замовника, ні логіста."""
    access = Access(telegram_user_id=9999, employee=None, bootstrap_admin=True)
    callback = FakeCallback(MENU_TRIP_NEW, user=FakeUser(9999))

    await on_new_trip(callback, state, access)

    assert await state.get_state() is None
    assert "співробітник" in callback.message.answers[0]


def test_callback_prefixes_do_not_shadow_each_other():
    """Усі префікси рейсу починаються з «trip:». Якби один був початком
    іншого, aiogram віддав би callback першому ж хендлеру зі startswith —
    і, наприклад, картка потрапила б у календар."""
    prefixes = [
        f"{p}:"
        for p in (
            TRIP_CAL_PREFIX, TRIP_DATE_PREFIX, TRIP_EXPORTER_PREFIX,
            TRIP_SHOW_PREFIX, TRIP_EDIT_PREFIX, TRIP_FIELD_PREFIX,
            TRIP_DELETE_PREFIX,
        )
    ]
    assert len(set(prefixes)) == len(prefixes)
    for one in prefixes:
        assert not any(one != other and one.startswith(other) for other in prefixes)
    # TRIP_CONFIRM звіряється точним порівнянням, але й він не має ловитись
    # жодним із startswith-хендлерів.
    assert not any(TRIP_CONFIRM.startswith(prefix) for prefix in prefixes)


async def test_trailer_plate_must_differ_from_the_truck(session, state, world, logist):
    await on_new_trip(FakeCallback(MENU_TRIP_NEW, user=FakeUser(OWNER_ID)), state, logist)
    await step_ttn(FakeMessage("ТТН-2"), state, session)
    await step_arrival_date(FakeCallback(f"{TRIP_DATE_PREFIX}:2026-08-10"), state, session)
    await step_client_pick(
        FakeCallback(f"{TRIP_CLIENT_PREFIX}:{world.theirs.id}"), state, session
    )
    await step_exporter(
        FakeCallback(f"{TRIP_EXPORTER_PREFIX}:{world.theirs.id}"), state, session
    )
    await step_truck(FakeMessage("Volvo"), state, session)
    await step_truck_plate(FakeMessage("AA1111AA"), state, session)
    await step_trailer(FakeMessage("Schmitz"), state, session)
    await step_trailer_type(FakeMessage("зерновоз"), state, session)

    message = FakeMessage("aa1111aa")  # той самий номер, іншим регістром
    await step_trailer_plate(message, state, session)

    assert await state.get_state() == TripForm.trailer_plate
    assert "не можуть збігатися" in message.answers[0]


async def test_unknown_date_is_rejected(session, state, world, logist):
    await on_new_trip(FakeCallback(MENU_TRIP_NEW, user=FakeUser(OWNER_ID)), state, logist)
    await step_ttn(FakeMessage("ТТН-3"), state, session)
    callback = FakeCallback(f"{TRIP_DATE_PREFIX}:2026-02-31")

    await step_arrival_date(callback, state, session)

    assert callback.answered == ["Невідома дата"]
    assert await state.get_state() == TripForm.arrival_date


# ---------------------------------------------------------------------------
# Водій і розсилка
# ---------------------------------------------------------------------------


async def test_driver_is_picked_from_the_company(
    session, state, world, logist, publisher
):
    """Вибір зі списку дає зв'язок, а ПІБ і телефон копіюються в рейс:
    він документ і має лишитись читабельним, якщо людина піде з компанії."""
    callback = await fill_form(
        state, session, logist,
        exporter_id=world.theirs.id, driver_id=world.driver.id,
    )

    await step_confirm(callback, state, session, publisher, logist)

    trips, _ = await repository.list_trips(session)
    trip = trips[0]
    assert trip.driver_id == world.driver.id
    assert trip.driver_fullname == "Петро Водій"
    assert trip.driver_phone_number == "+380507778899"


async def test_manual_driver_leaves_no_link(session, state, world, logist, publisher):
    """Сторонній перевізник у employees не значиться — FK лишається порожнім."""
    callback = await fill_form(state, session, logist, exporter_id=world.theirs.id)

    await step_confirm(callback, state, session, publisher, logist)

    trips, _ = await repository.list_trips(session)
    assert trips[0].driver_id is None
    assert trips[0].driver_fullname == "Іван Іванович Іваненко"


async def test_driver_from_another_company_is_refused(session, state, world, logist):
    """Кнопки чужого співробітника немає, але callback_data можна підробити."""
    await fill_form_until_driver(state, session, logist, world.theirs.id)
    callback = FakeCallback(f"{TRIP_DRIVER_PREFIX}:{world.outsider.id}")

    await step_driver_pick(callback, state, session)

    assert callback.answered == ["Невідомий співробітник"]
    assert await state.get_state() == TripForm.driver


async def test_driver_list_offers_the_company_and_manual_entry(
    session, state, world, logist
):
    """У списку — свої співробітники, крім самого логіста; поруч завжди
    ручний ввід, бо рейс може виконувати найманий перевізник."""
    await fill_form_until_driver(state, session, logist, world.theirs.id, grain=None)
    message = FakeMessage("Пшениця")
    await step_grain(message, state, session)

    labels = [b.text for row in message.markups[-1].inline_keyboard for b in row]
    data = callback_data(message.markups[-1])
    assert "Диспетчер, Петро Водій" in labels
    assert TRIP_DRIVER_MANUAL in data
    # Себе логіст у списку не бачить, чужу компанію — теж.
    assert not any("Марія Логіст" in label for label in labels)
    assert not any("Чужий" in label for label in labels)


async def test_driver_is_notified_and_chat_gets_a_copy(
    session, state, world, logist, publisher
):
    callback = await fill_form(
        state, session, logist,
        exporter_id=world.theirs.id, driver_id=world.driver.id,
    )

    await step_confirm(callback, state, session, publisher, logist)

    targets = [chat_id for chat_id, _ in publisher.sent]
    assert DRIVER_ID in targets
    assert OUR_CHAT_ID in targets
    driver_text = next(text for chat, text in publisher.sent if chat == DRIVER_ID)
    assert "Вам призначено рейс" in driver_text
    # message_id збережено — без нього рейс не прибрати з чату при видаленні.
    trips, _ = await repository.list_trips(session)
    assert trips[0].chat_id == OUR_CHAT_ID
    assert trips[0].chat_message_id == publisher.message_id


async def test_confirmation_survives_a_fresh_session(
    session_factory, session, state, world, logist, publisher
):
    """Хендлер працює на сесії, відкритій під цей апдейт, — а не на тій, у
    якій щойно створили довідники. Різниця не косметична: у «своїй» сесії
    компанії лежать в identity map, і ліниве завантаження мовчки бере їх
    звідти, ховаючи те, що зв'язки вже не завантажені.
    """
    callback = await fill_form(
        state, session, logist,
        exporter_id=world.theirs.id, driver_id=world.driver.id,
    )

    async with session_factory() as fresh:
        await step_confirm(callback, state, fresh, publisher, logist)

    # Картка рейсу дійшла до логіста цілою, з обома компаніями.
    assert "ТОВ Чужа" in callback.message.answers[0]


async def test_unreachable_driver_does_not_lose_the_trip(
    session, state, world, logist, publisher
):
    """Telegram не дасть писати тому, хто не запускав бота. Рейс уже в базі —
    але логіст має дізнатись, що водій його не отримав."""
    publisher.unreachable.add(DRIVER_ID)
    callback = await fill_form(
        state, session, logist,
        exporter_id=world.theirs.id, driver_id=world.driver.id,
    )

    await step_confirm(callback, state, session, publisher, logist)

    _, total = await repository.list_trips(session)
    assert total == 1
    assert "не вдалося написати" in callback.message.answers[0]


async def test_supergroup_migration_updates_the_company(
    session, state, world, logist, publisher
):
    """Група стала супергрупою — старий id мертвий назавжди. Запам'ятовуємо
    новий одразу, інакше кожен наступний рейс упирався б у той самий глухий кут.
    """
    new_chat = -1004380122313
    publisher.migrated[OUR_CHAT_ID] = new_chat
    callback = await fill_form(state, session, logist, exporter_id=world.theirs.id)

    await step_confirm(callback, state, session, publisher, logist)

    trips, _ = await repository.list_trips(session)
    assert trips[0].chat_id == new_chat
    company = await repository.get_company(session, world.ours.id)
    assert company.company_chat_id == new_chat
    assert "id чату змінено" in callback.message.answers[0]


async def test_missing_working_chat_is_reported(
    session, state, world, logist, publisher
):
    await repository.update_company(session, world.ours, company_chat_id=None)
    callback = await fill_form(state, session, logist, exporter_id=world.theirs.id)

    await step_confirm(callback, state, session, publisher, logist)

    _, total = await repository.list_trips(session)
    assert total == 1
    assert publisher.sent == []
    assert "Робочий чат компанії не вказано" in callback.message.answers[0]


async def test_driver_sees_the_trip_assigned_to_them(session, world, logist, publisher):
    driver_access = await access_for(session, DRIVER_ID)
    await make_trip(
        session, world.logist, world.theirs, ttn_num="МІЙ-РЕЙС",
        driver_id=world.driver.id,
    )
    await make_trip(session, world.logist, world.theirs, ttn_num="ЧУЖИЙ-РЕЙС")

    text, _ = await render_trips(session, driver_access)

    assert "МІЙ-РЕЙС" in text
    assert "ЧУЖИЙ-РЕЙС" not in text


async def test_driver_may_look_but_not_edit(session, state, world):
    """Рейс водієві видали — це завдання, а не його документ."""
    driver_access = await access_for(session, DRIVER_ID)
    trip = await make_trip(
        session, world.logist, world.theirs, driver_id=world.driver.id
    )

    card = FakeCallback(f"{TRIP_SHOW_PREFIX}:{trip.id}", user=FakeUser(DRIVER_ID))
    await on_trip_card(card, state, session, driver_access)
    assert card.message.answers
    # Кнопок редагування водієві не показуємо…
    assert f"{TRIP_EDIT_PREFIX}:{trip.id}" not in callback_data(card.message.markups[0])

    # …і підроблений callback_data теж не проходить.
    edit = FakeCallback(f"{TRIP_FIELD_PREFIX}:grain:{trip.id}", user=FakeUser(DRIVER_ID))
    await on_trip_field(edit, state, session, driver_access)
    assert edit.answered == [DENIED]


async def test_delete_clears_the_chat_and_tells_the_driver(
    session_factory, session, world, logist, publisher
):
    trip = await make_trip(
        session, world.logist, world.theirs, driver_id=world.driver.id
    )
    await repository.set_trip_chat_message(
        session, trip, chat_id=OUR_CHAT_ID, message_id=777
    )
    callback = FakeCallback(f"{TRIP_DELETE_PREFIX}:{trip.id}", user=FakeUser(OWNER_ID))

    # Сесія під апдейт — окрема, як у бойовому боті.
    async with session_factory() as fresh:
        await on_trip_delete(callback, fresh, publisher, logist)

    assert publisher.retracted == [(OUR_CHAT_ID, 777)]
    assert any(chat == DRIVER_ID and "скасовано" in text for chat, text in publisher.sent)
    assert await repository.get_trip(session, trip.id) is None


# ---------------------------------------------------------------------------
# Календар
# ---------------------------------------------------------------------------


async def test_calendar_navigation_rolls_over_the_year(state):
    callback = FakeCallback(f"{TRIP_CAL_PREFIX}:2026:12")
    await on_calendar_nav(callback, state)

    # Кнопка «›» грудня має вести в січень наступного року.
    data = callback_data(callback.message.markups[0])
    assert f"{TRIP_CAL_PREFIX}:2027:1" in data


async def test_calendar_days_carry_a_full_date(state):
    callback = FakeCallback(f"{TRIP_CAL_PREFIX}:2026:8")
    await on_calendar_nav(callback, state)

    data = callback_data(callback.message.markups[0])
    assert f"{TRIP_DATE_PREFIX}:2026-08-01" in data
    assert f"{TRIP_DATE_PREFIX}:2026-08-31" in data
    assert f"{TRIP_DATE_PREFIX}:2026-08-32" not in data


async def test_calendar_rejects_a_forged_month(state):
    callback = FakeCallback(f"{TRIP_CAL_PREFIX}:2026:13")

    await on_calendar_nav(callback, state)

    assert callback.answered == ["Дата поза межами"]


# ---------------------------------------------------------------------------
# Межа видимості
# ---------------------------------------------------------------------------


@pytest.fixture
async def trips(session, world):
    """Три рейси: два в нашій компанії (від різних людей) і один у чужій."""
    return SimpleNamespace(
        mine=await make_trip(session, world.logist, world.theirs, ttn_num="МІЙ"),
        colleague=await make_trip(session, world.boss, world.theirs, ttn_num="КОЛЕГИ"),
        foreign=await make_trip(session, world.outsider, world.ours, ttn_num="ЧУЖИЙ"),
    )


async def test_driver_sees_only_own_trips(session, world, trips):
    """У водія обсяг own: рейси, які він створив або в яких він водій."""
    driver_access = await access_for(session, DRIVER_ID)

    text, _ = await render_trips(session, driver_access)

    assert "МІЙ" not in text
    assert "КОЛЕГИ" not in text
    assert "ЧУЖИЙ" not in text


async def test_logist_sees_the_whole_company(session, logist, trips):
    """У логіста обсяг company — і чужа компанія в нього не потрапляє."""
    text, _ = await render_trips(session, logist)

    assert "МІЙ" in text and "КОЛЕГИ" in text
    assert "ЧУЖИЙ" not in text


async def test_company_admin_sees_the_whole_company(session, boss, trips):
    text, _ = await render_trips(session, boss)

    assert "МІЙ" in text and "КОЛЕГИ" in text
    assert "ЧУЖИЙ" not in text


async def test_main_admin_sees_everything(session, chief, trips):
    text, _ = await render_trips(session, chief)

    assert "МІЙ" in text and "КОЛЕГИ" in text and "ЧУЖИЙ" in text


async def test_foreign_trip_cannot_be_opened_by_id(session, state, logist, trips):
    """Кнопки чужого рейсу немає, але callback_data можна підробити."""
    callback = FakeCallback(
        f"{TRIP_SHOW_PREFIX}:{trips.foreign.id}", user=FakeUser(OWNER_ID)
    )

    await on_trip_card(callback, state, session, logist)

    assert callback.answered == [DENIED]
    assert not callback.message.answers


async def test_colleague_trip_is_out_of_reach_for_a_driver(
    session, state, world, boss, trips
):
    """Обсяг company відкриває рейс колеги, обсяг own — ні."""
    driver_access = await access_for(session, DRIVER_ID)
    for access, expected in ((driver_access, [DENIED]), (boss, [None])):
        callback = FakeCallback(f"{TRIP_SHOW_PREFIX}:{trips.colleague.id}")
        await on_trip_card(callback, state, session, access)
        assert callback.answered == expected


async def test_card_shows_when_the_trip_was_created(session, state, chief, trips):
    """updated_at і deleted_at при створенні порожні, тож без created_at
    з картки неможливо сказати, коли рейс з'явився."""
    callback = FakeCallback(f"{TRIP_SHOW_PREFIX}:{trips.mine.id}", user=FakeUser(CHIEF_ID))

    await on_trip_card(callback, state, session, chief)

    assert f"Створено: {trips.mine.created_at}" in callback.message.answers[0]


async def test_card_shows_both_companies(session, state, chief, trips):
    callback = FakeCallback(f"{TRIP_SHOW_PREFIX}:{trips.mine.id}", user=FakeUser(CHIEF_ID))

    await on_trip_card(callback, state, session, chief)

    text = callback.message.answers[0]
    assert "ТОВ Чужа" in text
    assert "Марія Логіст" in text


# ---------------------------------------------------------------------------
# Редагування
# ---------------------------------------------------------------------------


async def _start_edit(session, state, access, trip_id: int, field: str):
    callback = FakeCallback(f"{TRIP_FIELD_PREFIX}:{field}:{trip_id}")
    await on_trip_field(callback, state, session, access)
    return callback


async def test_editing_records_who_and_when(session, state, boss, trips, publisher):
    await _start_edit(session, state, boss, trips.mine.id, "grain")

    await edit_value(FakeMessage("Кукурудза"), state, session, boss, publisher)

    trip = await repository.get_trip(session, trips.mine.id)
    assert trip.grain_type == "Кукурудза"
    assert trip.edited_by == (await repository.get_employee_by_tg_id(session, ADMIN_ID)).id
    assert trip.updated_at is not None
    assert await state.get_state() is None


async def test_editing_a_plate_rejects_the_other_one(
    session, state, logist, trips, publisher
):
    await _start_edit(session, state, logist, trips.mine.id, "rplate")
    message = FakeMessage("AA1111AA")  # номер тягача цього ж рейсу

    await edit_value(message, state, session, logist, publisher)

    assert "не можуть збігатися" in message.answers[0]
    assert await state.get_state() == TripEdit.value


async def test_mass_takes_only_whole_numbers(session, state, logist, trips, publisher):
    await _start_edit(session, state, logist, trips.mine.id, "bmass")

    bad = FakeMessage("28,5 тонни")
    await edit_value(bad, state, session, logist, publisher)
    assert "Ціле число" in bad.answers[0]

    await edit_value(FakeMessage("28500"), state, session, logist, publisher)
    trip = await repository.get_trip(session, trips.mine.id)
    assert trip.b_mass == 28500


async def test_entry_time_is_validated_and_can_be_cleared(
    session, state, logist, trips, publisher
):
    await _start_edit(session, state, logist, trips.mine.id, "entry")
    bad = FakeMessage("10.08.2026 07:30")
    await edit_value(bad, state, session, logist, publisher)
    assert "РРРР-ММ-ДД" in bad.answers[0]

    await edit_value(FakeMessage("2026-08-10 07:30"), state, session, logist, publisher)
    trip = await repository.get_trip(session, trips.mine.id)
    assert trip.datetime_entry == "2026-08-10 07:30"

    await _start_edit(session, state, logist, trips.mine.id, "entry")
    await edit_value(FakeMessage("-"), state, session, logist, publisher)
    trip = await repository.get_trip(session, trips.mine.id)
    assert trip.datetime_entry is None


async def test_changing_exporter_refreshes_the_card(
    session, state, world, logist, trips, publisher
):
    await _start_edit(session, state, logist, trips.mine.id, "exp")
    assert await state.get_state() == TripEdit.exporter

    callback = FakeCallback(f"{TRIP_EXPORTER_PREFIX}:{world.ours.id}")
    await edit_exporter(callback, state, session, logist, publisher)

    trip = await repository.get_trip(session, trips.mine.id)
    assert trip.exporter_company_id == world.ours.id
    # Картку перемальовано з новою компанією, а не зі старою з identity map.
    assert "Експортер:</b> Alebor IT 000000" in callback.message.answers[-1]


async def test_editing_a_foreign_trip_is_refused(session, state, logist, trips):
    callback = await _start_edit(session, state, logist, trips.foreign.id, "grain")

    assert callback.answered == [DENIED]
    assert await state.get_state() is None


# ---------------------------------------------------------------------------
# Видалення
# ---------------------------------------------------------------------------


async def test_delete_marks_the_row_instead_of_erasing_it(
    session, logist, trips, publisher
):
    callback = FakeCallback(
        f"{TRIP_DELETE_PREFIX}:{trips.mine.id}", user=FakeUser(OWNER_ID)
    )

    await on_trip_delete(callback, session, publisher, logist)

    assert await repository.get_trip(session, trips.mine.id) is None
    kept = await repository.get_trip(session, trips.mine.id, include_deleted=True)
    assert kept.deleted_at is not None
    assert kept.deleted_by == (await repository.get_employee_by_tg_id(session, OWNER_ID)).id
    # Список перемальовано на місці, і видаленого рейсу в ньому вже немає.
    assert "МІЙ" not in callback.message.edits[0]


async def test_trips_scroll_in_place(session, chief, world):
    """Гортання йде через спільний on_page: вид «trips», зсув останнім."""
    for i in range(PAGE_TRIPS + 2):
        await make_trip(
            session, world.logist, world.theirs,
            ttn_num=f"Т{i:02d}", arrival_date=f"2026-08-{i + 1:02d}",
        )
    callback = FakeCallback(f"{PAGE_PREFIX}:trips:{PAGE_TRIPS}")

    await on_page(callback, session, chief)

    # Сортування — за датою прибуття вниз, тож на другій сторінці найстаріші.
    assert "Т00" in callback.message.edits[0]
    assert "Т07" not in callback.message.edits[0]
    assert not callback.message.answers  # редагуємо, а не шлемо нове


async def test_foreign_trip_cannot_be_deleted(session, logist, trips, publisher):
    callback = FakeCallback(
        f"{TRIP_DELETE_PREFIX}:{trips.foreign.id}", user=FakeUser(OWNER_ID)
    )

    await on_trip_delete(callback, session, publisher, logist)

    assert callback.answered == [DENIED]
    assert await repository.get_trip(session, trips.foreign.id) is not None


# ---------------------------------------------------------------------------
# Права на рівні поля
# ---------------------------------------------------------------------------


@pytest.fixture
async def operator(session, world) -> Access:
    await repository.create_employee(
        session, tg_id=6006, company_id=world.ours.id, fullname="Ольга Ваги",
        phone_number="+380506660000", position_id=1, role_id=5,
    )
    return Access(
        telegram_user_id=6006,
        employee=await repository.get_employee_by_tg_id(session, 6006),
        permissions=permissions_for(ROLE_OPERATOR),
    )


async def test_operator_menu_offers_only_masses(session, state, operator, trips):
    """У меню редагування — лише те, що ця роль справді може змінити."""
    callback = FakeCallback(f"{TRIP_EDIT_PREFIX}:{trips.mine.id}", user=FakeUser(6006))

    await on_trip_edit(callback, state, session, operator)

    data = callback_data(callback.message.markups[0])
    assert f"{TRIP_FIELD_PREFIX}:bmass:{trips.mine.id}" in data
    assert f"{TRIP_FIELD_PREFIX}:status:{trips.mine.id}" not in data
    assert f"{TRIP_FIELD_PREFIX}:ttn:{trips.mine.id}" not in data


async def test_operator_cannot_open_a_field_outside_their_right(
    session, state, operator, trips
):
    """Кнопки немає, але callback_data можна підробити."""
    callback = FakeCallback(
        f"{TRIP_FIELD_PREFIX}:ttn:{trips.mine.id}", user=FakeUser(6006)
    )

    await on_trip_field(callback, state, session, operator)

    assert callback.answered == [DENIED]
    assert await state.get_state() is None


async def test_operator_saves_a_mass(session, state, operator, trips, publisher):
    callback = FakeCallback(
        f"{TRIP_FIELD_PREFIX}:bmass:{trips.mine.id}", user=FakeUser(6006)
    )
    await on_trip_field(callback, state, session, operator)

    await edit_value(FakeMessage("28500"), state, session, operator, publisher)

    trip = await repository.get_trip(session, trips.mine.id)
    assert trip.b_mass == 28500


async def test_operator_cannot_save_a_forbidden_field_by_state(
    session, state, operator, trips, publisher
):
    """Стан можна лишити з попереднього кроку — право перевіряється і тут."""
    await state.set_state(TripEdit.value)
    await state.update_data(trip_id=trips.mine.id, field="ttn")
    message = FakeMessage("ПІДРОБКА")

    await edit_value(message, state, session, operator, publisher)

    trip = await repository.get_trip(session, trips.mine.id)
    assert trip.ttn_num != "ПІДРОБКА"
    assert message.answers[0] == DENIED


async def test_operator_cannot_delete_a_trip(session, operator, trips, publisher):
    callback = FakeCallback(
        f"{TRIP_DELETE_PREFIX}:{trips.mine.id}", user=FakeUser(6006)
    )

    await on_trip_delete(callback, session, publisher, operator)

    assert callback.answered == [DENIED]
    assert await repository.get_trip(session, trips.mine.id) is not None


# ---------------------------------------------------------------------------
# Замовник
# ---------------------------------------------------------------------------


async def test_client_is_asked_not_taken_from_the_creator(
    session, state, world, logist, publisher
):
    """Рейс возять для чужої компанії — компанія того, хто заповнює, тут
    ні до чого."""
    callback = await fill_form(
        state, session, logist,
        exporter_id=world.ours.id, client_id=world.theirs.id,
    )

    await step_confirm(callback, state, session, publisher, logist)

    trips, _ = await repository.list_trips(session)
    trip = trips[0]
    assert trip.client_company_id == world.theirs.id
    assert trip.client_company_name == "ТОВ Чужа 99999999"
    # А власник — усе одно компанія творця.
    assert trip.owner_company_id == world.ours.id


async def test_client_can_be_typed_by_hand(
    session, state, world, logist, publisher
):
    """Замовника може не бути в системі — тоді лишається сама назва."""
    await on_new_trip(FakeCallback(MENU_TRIP_NEW, user=FakeUser(OWNER_ID)), state, logist)
    await step_ttn(FakeMessage("ТТН-777"), state, session)
    await step_arrival_date(FakeCallback(f"{TRIP_DATE_PREFIX}:2026-08-10"), state, session)

    await step_client_manual(FakeCallback(TRIP_CLIENT_MANUAL), state, session)
    assert await state.get_state() == TripForm.client_name
    await step_client_name(FakeMessage("ФГ Стороннє"), state, session)

    await step_exporter(
        FakeCallback(f"{TRIP_EXPORTER_PREFIX}:{world.theirs.id}"), state, session
    )
    await step_truck(FakeMessage("Volvo"), state, session)
    await step_truck_plate(FakeMessage("AA9999AA"), state, session)
    await step_trailer(FakeMessage("Schmitz"), state, session)
    await step_trailer_type(FakeMessage("зерновоз"), state, session)
    await step_trailer_plate(FakeMessage("CC9999CC"), state, session)
    await step_grain(FakeMessage("Ріпак"), state, session)
    await step_driver_manual(FakeCallback(TRIP_DRIVER_MANUAL), state, session)
    await step_driver_name(FakeMessage("Іван Водій"), state, session)
    await step_driver_phone(FakeMessage("+380500000000"), state, session)

    confirm = FakeCallback(TRIP_CONFIRM, user=FakeUser(OWNER_ID))
    await step_confirm(confirm, state, session, publisher, logist)

    trips, _ = await repository.list_trips(session)
    trip = next(t for t in trips if t.ttn_num == "ТТН-777")
    assert trip.client_company_id is None
    assert trip.client_company_name == "ФГ Стороннє"
    assert trip.owner_company_id == world.ours.id


async def test_short_client_name_keeps_the_step(session, state, world, logist):
    await on_new_trip(FakeCallback(MENU_TRIP_NEW, user=FakeUser(OWNER_ID)), state, logist)
    await step_ttn(FakeMessage("ТТН-778"), state, session)
    await step_arrival_date(FakeCallback(f"{TRIP_DATE_PREFIX}:2026-08-10"), state, session)
    await step_client_manual(FakeCallback(TRIP_CLIENT_MANUAL), state, session)

    message = FakeMessage("Ф")
    await step_client_name(message, state, session)

    assert await state.get_state() == TripForm.client_name
    assert "від 2 до" in message.answers[0]


async def test_scope_follows_the_owner_not_the_client(session, world, boss):
    """Головне в цій зміні: доступ рахується за компанією-власником.

    Рейс із замовником «ТОВ Чужа» лишається видимим для своєї компанії, а
    чужий рейс із замовником «Alebor IT» — ні. На client_company_id обсяг
    тримати вже не можна.
    """
    await make_trip(session, world.logist, world.theirs, ttn_num="НАШ-ДЛЯ-ЧУЖИХ")
    await make_trip(session, world.outsider, world.ours, ttn_num="ЧУЖИЙ-ДЛЯ-НАС")

    text, _ = await render_trips(session, boss)

    assert "НАШ-ДЛЯ-ЧУЖИХ" in text
    assert "ЧУЖИЙ-ДЛЯ-НАС" not in text


async def test_working_chat_is_the_owners_not_the_clients(
    session, state, world, logist, publisher
):
    """Дублювання в чат теж іде за власником: чат замовника — чужий."""
    await repository.update_company(session, world.theirs, company_chat_id=-100999)
    callback = await fill_form(
        state, session, logist,
        exporter_id=world.ours.id, client_id=world.theirs.id,
    )

    await step_confirm(callback, state, session, publisher, logist)

    targets = [chat for chat, _ in publisher.sent]
    assert OUR_CHAT_ID in targets
    assert -100999 not in targets


async def test_card_says_manager_not_logist(session, state, chief, trips):
    """Підпис у документі — «Менеджер», хоч колонки досі logist_*."""
    callback = FakeCallback(f"{TRIP_SHOW_PREFIX}:{trips.mine.id}", user=FakeUser(CHIEF_ID))

    await on_trip_card(callback, state, session, chief)

    text = callback.message.answers[0]
    assert "<b>Менеджер:</b>" in text
    assert "Логіст:" not in text


# ---------------------------------------------------------------------------
# Статус, робочий чат і зміна водія
# ---------------------------------------------------------------------------


async def test_status_is_picked_from_the_list(session, state, logist, trips, publisher):
    """Статус більше не набирається текстом: у callback_data йде номер."""
    await _start_edit(session, state, logist, trips.mine.id, "status")
    assert await state.get_state() == TripEdit.status

    index = TRIP_STATUSES.index("В дорозі")
    await edit_status(
        FakeCallback(f"{TRIP_STATUS_PREFIX}:{index}"), state, session, logist, publisher
    )

    trip = await repository.get_trip(session, trips.mine.id)
    assert trip.status == "В дорозі"


async def test_status_outside_the_list_is_refused(
    session, state, logist, trips, publisher
):
    """Номер за межами переліку — саме те, що приходить із підробленої
    callback_data. Раніше на цьому місці зберігався б довільний рядок."""
    await _start_edit(session, state, logist, trips.mine.id, "status")
    callback = FakeCallback(f"{TRIP_STATUS_PREFIX}:{len(TRIP_STATUSES)}")

    await edit_status(callback, state, session, logist, publisher)

    assert callback.answered == ["Невідомий статус"]
    trip = await repository.get_trip(session, trips.mine.id)
    assert trip.status == TRIP_STATUS_NEW


async def test_status_typed_as_text_no_longer_saves(
    session, state, logist, trips, publisher
):
    """Стан міг лишитись від старої версії бота — текст у нього не пройде."""
    await state.set_state(TripEdit.value)
    await state.update_data(trip_id=trips.mine.id, field="status")
    message = FakeMessage("готово")

    await edit_value(message, state, session, logist, publisher)

    trip = await repository.get_trip(session, trips.mine.id)
    assert trip.status == TRIP_STATUS_NEW


async def test_editing_refreshes_the_working_chat(
    session, state, logist, world, publisher
):
    """Головне: у чаті має висіти теперішній рейс, а не його перша версія."""
    trip = await make_trip(
        session, world.logist, world.ours,
        chat_id=OUR_CHAT_ID, chat_message_id=777,
    )
    await _start_edit(session, state, logist, trip.id, "grain")

    await edit_value(FakeMessage("Кукурудза"), state, session, logist, publisher)

    assert len(publisher.edited) == 1
    chat_id, message_id, text = publisher.edited[0]
    assert (chat_id, message_id) == (OUR_CHAT_ID, 777)
    assert "Кукурудза" in text


async def test_trip_outside_a_chat_is_not_refreshed(
    session, state, logist, trips, publisher
):
    """Рейс могли створити до появи робочого чату — редагувати його можна."""
    await _start_edit(session, state, logist, trips.mine.id, "grain")

    await edit_value(FakeMessage("Ріпак"), state, session, logist, publisher)

    assert publisher.edited == []


async def test_driver_learns_about_a_new_status(
    session, state, logist, world, publisher
):
    trip = await make_trip(session, world.logist, world.ours, driver_id=world.driver.id)
    await _start_edit(session, state, logist, trip.id, "status")

    index = TRIP_STATUSES.index("Завершено")
    await edit_status(
        FakeCallback(f"{TRIP_STATUS_PREFIX}:{index}"), state, session, logist, publisher
    )

    assert [chat for chat, _ in publisher.sent] == [DRIVER_ID]
    assert "Завершено" in publisher.sent[0][1]


async def test_driver_is_not_told_about_a_mass(
    session, state, logist, world, publisher
):
    """Сповіщати про кожну правку маси — спам, після якого перестають
    читати й важливе."""
    trip = await make_trip(session, world.logist, world.ours, driver_id=world.driver.id)
    await _start_edit(session, state, logist, trip.id, "bmass")

    await edit_value(FakeMessage("28500"), state, session, logist, publisher)

    assert publisher.sent == []


async def test_reassigning_a_driver_moves_the_trip(
    session, state, logist, world, publisher
):
    """Раніше мінявся лише підпис: driver_id лишався на попередній людині,
    вона й далі бачила рейс, а новий водій не дізнавався нічого."""
    trip = await make_trip(session, world.logist, world.ours, driver_id=world.driver.id)
    await _start_edit(session, state, logist, trip.id, "driver")
    assert await state.get_state() == TripEdit.driver

    await edit_driver_pick(
        FakeCallback(f"{TRIP_DRIVER_PREFIX}:{world.boss.id}"),
        state, session, logist, publisher,
    )

    updated = await repository.get_trip(session, trip.id)
    assert updated.driver_id == world.boss.id
    assert updated.driver_fullname == "Олег Логіст"
    assert updated.driver_phone_number == world.boss.phone_number

    told = {chat: text for chat, text in publisher.sent}
    assert "більше не за вами" in told[DRIVER_ID]
    assert f"Рейс #{trip.id}" in told[ADMIN_ID]


async def test_a_released_driver_loses_the_trip(session, state, logist, world, publisher):
    """Обсяг «власні» рахується за driver_id — після передачі рейс зникає
    зі списку колишнього водія."""
    trip = await make_trip(session, world.logist, world.ours, driver_id=world.driver.id)
    await _start_edit(session, state, logist, trip.id, "driver")
    await edit_driver_pick(
        FakeCallback(f"{TRIP_DRIVER_PREFIX}:{world.boss.id}"),
        state, session, logist, publisher,
    )

    driver_access = await access_for(session, DRIVER_ID)
    text, _ = await render_trips(session, driver_access)

    assert "Рейсів поки немає" in text


async def test_a_manual_driver_releases_the_employee(
    session, state, logist, world, publisher
):
    """Найманий перевізник: зв'язок знімається, ПІБ і телефон лишаються."""
    trip = await make_trip(session, world.logist, world.ours, driver_id=world.driver.id)
    await _start_edit(session, state, logist, trip.id, "driver")

    await edit_driver_manual(FakeCallback(TRIP_DRIVER_MANUAL), state)
    await edit_driver_name(FakeMessage("Сторонній Перевізник"), state, session, logist)
    await edit_driver_phone(
        FakeMessage("+380971112233"), state, session, logist, publisher
    )

    updated = await repository.get_trip(session, trip.id)
    assert updated.driver_id is None
    assert updated.driver_fullname == "Сторонній Перевізник"
    assert updated.driver_phone_number == "+380971112233"
    assert "більше не за вами" in dict(publisher.sent)[DRIVER_ID]


async def test_a_driver_from_another_company_is_refused(
    session, state, logist, world, publisher
):
    """id співробітника приходить у callback_data — компанію звіряємо заново."""
    trip = await make_trip(session, world.logist, world.ours, driver_id=world.driver.id)
    await _start_edit(session, state, logist, trip.id, "driver")

    callback = FakeCallback(f"{TRIP_DRIVER_PREFIX}:{world.outsider.id}")
    await edit_driver_pick(callback, state, session, logist, publisher)

    updated = await repository.get_trip(session, trip.id)
    assert updated.driver_id == world.driver.id
    assert "Невідомий співробітник" in callback.message.answers[-1]


# ---------------------------------------------------------------------------
# Маси, час і підказки
# ---------------------------------------------------------------------------


async def test_net_mass_is_computed(session, state, logist, trips, publisher):
    """Нетто ніхто не вводить: воно рахується з брутто й тари."""
    await _start_edit(session, state, logist, trips.mine.id, "bmass")
    await edit_value(FakeMessage("30000"), state, session, logist, publisher)
    await _start_edit(session, state, logist, trips.mine.id, "tmass")
    await edit_value(FakeMessage("12500"), state, session, logist, publisher)

    trip = await repository.get_trip(session, trips.mine.id)
    assert (trip.b_mass, trip.t_mass, trip.n_mass) == (30000, 12500, 17500)


async def test_tare_above_gross_is_refused(session, state, logist, trips, publisher):
    await _start_edit(session, state, logist, trips.mine.id, "bmass")
    await edit_value(FakeMessage("20000"), state, session, logist, publisher)

    await _start_edit(session, state, logist, trips.mine.id, "tmass")
    message = FakeMessage("25000")
    await edit_value(message, state, session, logist, publisher)

    assert "Тара більша за брутто" in message.answers[0]
    trip = await repository.get_trip(session, trips.mine.id)
    assert trip.t_mass == 0


async def test_net_mass_is_not_offered_for_editing(session, state, logist, trips):
    """Поля «Нетто» в меню немає — воно похідне."""
    callback = FakeCallback(f"{TRIP_EDIT_PREFIX}:{trips.mine.id}", user=FakeUser(OWNER_ID))

    await on_trip_edit(callback, state, session, logist)

    keys = callback_data(callback.message.markups[-1])
    assert any("bmass" in key for key in keys)
    assert not any("nmass" in key for key in keys)


async def test_entry_time_takes_one_tap(session, state, logist, trips, publisher):
    await _start_edit(session, state, logist, trips.mine.id, "entry")

    await edit_datetime_button(
        FakeCallback(TRIP_NOW), state, session, logist, publisher
    )

    trip = await repository.get_trip(session, trips.mine.id)
    assert trip.datetime_entry == datetime.now().strftime("%Y-%m-%d %H:%M")


async def test_entry_time_clears_by_button(session, state, logist, trips, publisher):
    await _start_edit(session, state, logist, trips.mine.id, "entry")
    await edit_value(FakeMessage("2026-08-10 07:30"), state, session, logist, publisher)

    await _start_edit(session, state, logist, trips.mine.id, "entry")
    await edit_datetime_button(
        FakeCallback(TRIP_CLEAR), state, session, logist, publisher
    )

    trip = await repository.get_trip(session, trips.mine.id)
    assert trip.datetime_entry is None


async def test_the_now_button_needs_a_time_field(
    session, state, logist, trips, publisher
):
    """Стан міг лишитись від іншого поля — кнопка не має писати «зараз»
    у номер ТТН."""
    await _start_edit(session, state, logist, trips.mine.id, "ttn")
    callback = FakeCallback(TRIP_NOW)

    await edit_datetime_button(callback, state, session, logist, publisher)

    assert callback.answered == ["Не зрозуміло, що саме редагуємо"]
    trip = await repository.get_trip(session, trips.mine.id)
    assert trip.ttn_num == "МІЙ"


async def test_grain_is_picked_from_the_hints(session, state, world, logist):
    """Підказка — це кнопка, а не довідник: у колонці лишається текст."""
    await fill_form_until_driver(state, session, logist, world.ours.id, grain=None)
    await step_trailer_plate(FakeMessage("cc3333cc"), state, session)

    await step_grain_pick(
        FakeCallback(f"{TRIP_CHOICE_PREFIX}:grain:0"), state, session
    )

    assert (await state.get_data())["grain_type"] == "Пшениця"
    assert await state.get_state() == TripForm.driver


async def test_typed_grain_still_works(session, state, world, logist):
    """Культур більше, ніж шість, і клас усе одно дописують руками."""
    await fill_form_until_driver(
        state, session, logist, world.ours.id, grain="Пшениця 2 клас"
    )

    assert (await state.get_data())["grain_type"] == "Пшениця 2 клас"


async def test_trailer_type_is_picked_from_the_hints(session, state, world, logist):
    await on_new_trip(FakeCallback(MENU_TRIP_NEW, user=FakeUser(OWNER_ID)), state, logist)
    await step_ttn(FakeMessage("ТТН-999"), state, session)
    await step_arrival_date(FakeCallback(f"{TRIP_DATE_PREFIX}:2026-08-10"), state, session)
    await step_client_pick(
        FakeCallback(f"{TRIP_CLIENT_PREFIX}:{world.ours.id}"), state, session
    )
    await step_exporter(
        FakeCallback(f"{TRIP_EXPORTER_PREFIX}:{world.ours.id}"), state, session
    )
    await step_truck(FakeMessage("Volvo"), state, session)
    await step_truck_plate(FakeMessage("aa1111aa"), state, session)
    await step_trailer(FakeMessage("Schmitz"), state, session)

    await step_trailer_type_pick(
        FakeCallback(f"{TRIP_CHOICE_PREFIX}:ttype:0"), state, session
    )

    assert (await state.get_data())["trailer_type"] == "Зерновоз"
    assert await state.get_state() == TripForm.trailer_plate


async def test_editing_grain_by_button(session, state, logist, trips, publisher):
    await _start_edit(session, state, logist, trips.mine.id, "grain")

    await edit_choice(
        FakeCallback(f"{TRIP_CHOICE_PREFIX}:grain:1"), state, session, logist, publisher
    )

    trip = await repository.get_trip(session, trips.mine.id)
    assert trip.grain_type == "Кукурудза"


# ---------------------------------------------------------------------------
# Навігація анкетою
# ---------------------------------------------------------------------------


async def test_back_returns_to_the_previous_step(session, state, world, logist):
    """Описка на третьому кроці з чотирнадцяти більше не означає почати
    анкету спочатку."""
    await on_new_trip(FakeCallback(MENU_TRIP_NEW, user=FakeUser(OWNER_ID)), state, logist)
    await step_ttn(FakeMessage("ТТН-000123"), state, session)
    await step_arrival_date(FakeCallback(f"{TRIP_DATE_PREFIX}:2026-08-10"), state, session)
    assert await state.get_state() == TripForm.client

    await on_form_back(FakeCallback(TRIP_BACK), state, session)

    assert await state.get_state() == TripForm.arrival_date
    # Уже введене лишається: рух назад нічого не стирає.
    assert (await state.get_data())["ttn_num"] == "ТТН-000123"


async def test_back_from_a_branch_returns_to_its_fork(session, state, world, logist):
    """Ручний ввід замовника — гілка, а не наступний крок: назад із неї має
    вести на вибір замовника, а не на дату."""
    await on_new_trip(FakeCallback(MENU_TRIP_NEW, user=FakeUser(OWNER_ID)), state, logist)
    await step_ttn(FakeMessage("ТТН-000123"), state, session)
    await step_arrival_date(FakeCallback(f"{TRIP_DATE_PREFIX}:2026-08-10"), state, session)
    await step_client_manual(FakeCallback(TRIP_CLIENT_MANUAL), state, session)
    assert await state.get_state() == TripForm.client_name

    await on_form_back(FakeCallback(TRIP_BACK), state, session)

    assert await state.get_state() == TripForm.client


async def test_back_from_the_first_step_says_so(session, state, world, logist):
    await on_new_trip(FakeCallback(MENU_TRIP_NEW, user=FakeUser(OWNER_ID)), state, logist)
    callback = FakeCallback(TRIP_BACK)

    await on_form_back(callback, state, session)

    assert callback.answered == ["Повертатись нікуди"]


async def test_the_first_step_has_no_back_button(session, state, world, logist):
    """Кнопка, яка веде в нікуди, читається як поламана система."""
    callback = FakeCallback(MENU_TRIP_NEW, user=FakeUser(OWNER_ID))

    await on_new_trip(callback, state, logist)

    assert TRIP_BACK not in callback_data(callback.message.markups[-1])


async def test_editing_from_the_summary_returns_to_the_summary(
    session, state, world, logist
):
    """Головне в цьому кроці: правка одного поля не веде рештою анкети."""
    await fill_form(state, session, logist, exporter_id=world.ours.id)
    assert await state.get_state() == TripForm.confirm

    await on_redo(FakeCallback(TRIP_REDO), state)
    await on_redo_step(FakeCallback(f"{TRIP_REDO_PREFIX}:ttn"), state, session)
    assert await state.get_state() == TripForm.ttn

    message = FakeMessage("ТТН-ВИПРАВЛЕНА")
    await step_ttn(message, state, session)

    assert await state.get_state() == TripForm.confirm
    assert "ТТН-ВИПРАВЛЕНА" in message.answers[-1]


async def test_the_corrected_value_reaches_the_trip(
    session, state, world, logist, publisher
):
    await fill_form(state, session, logist, exporter_id=world.ours.id)
    await on_redo(FakeCallback(TRIP_REDO), state)
    await on_redo_step(FakeCallback(f"{TRIP_REDO_PREFIX}:grain"), state, session)
    await step_grain(FakeMessage("Ріпак"), state, session)

    callback = FakeCallback(TRIP_CONFIRM, user=FakeUser(OWNER_ID))
    await step_confirm(callback, state, session, publisher, logist)

    trips, _ = await repository.list_trips(session)
    assert trips[0].grain_type == "Ріпак"


async def test_the_flag_does_not_outlive_one_correction(
    session, state, world, logist
):
    """Прапорець згорає на підсумку: наступний крок, відкритий уже не з
    підсумку, має вести анкетою далі, а не стрибати назад."""
    await fill_form(state, session, logist, exporter_id=world.ours.id)
    await on_redo(FakeCallback(TRIP_REDO), state)
    await on_redo_step(FakeCallback(f"{TRIP_REDO_PREFIX}:truck"), state, session)
    await step_truck(FakeMessage("Scania R500"), state, session)
    assert await state.get_state() == TripForm.confirm

    # Тепер звичайний прохід: після тягача має йти його номер, а не підсумок.
    await on_redo(FakeCallback(TRIP_REDO), state)
    await on_redo_step(FakeCallback(f"{TRIP_REDO_PREFIX}:date"), state, session)
    await state.update_data(return_to_summary=False)
    await step_arrival_date(FakeCallback(f"{TRIP_DATE_PREFIX}:2026-09-01"), state, session)

    assert await state.get_state() == TripForm.client


async def test_an_unknown_redo_key_is_refused(session, state, world, logist):
    await fill_form(state, session, logist, exporter_id=world.ours.id)
    callback = FakeCallback(f"{TRIP_REDO_PREFIX}:вигадане")

    await on_redo_step(callback, state, session)

    assert callback.answered == ["Невідоме поле"]
    assert await state.get_state() == TripForm.confirm
