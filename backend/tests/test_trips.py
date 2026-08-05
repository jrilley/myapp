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
    ROLE_MAIN_ADMIN,
    ROLE_USER,
    Access,
)
from app.bot.actions import render_trips
from app.bot.handlers.common import on_page
from app.bot.handlers.trips import (
    DENIED,
    on_calendar_nav,
    on_new_trip,
    on_trip_card,
    on_trip_delete,
    on_trip_field,
    edit_exporter,
    edit_value,
    step_arrival_date,
    step_confirm,
    step_driver_manual,
    step_driver_name,
    step_driver_phone,
    step_driver_pick,
    step_exporter,
    step_grain,
    step_trailer,
    step_trailer_plate,
    step_trailer_type,
    step_truck,
    step_truck_plate,
    step_ttn,
)
from app.bot.keyboards import (
    MENU_TRIP_NEW,
    PAGE_PREFIX,
    PAGE_TRIPS,
    TRIP_CAL_PREFIX,
    TRIP_CONFIRM,
    TRIP_DATE_PREFIX,
    TRIP_DELETE_PREFIX,
    TRIP_DRIVER_MANUAL,
    TRIP_DRIVER_PREFIX,
    TRIP_EDIT_PREFIX,
    TRIP_EXPORTER_PREFIX,
    TRIP_FIELD_PREFIX,
    TRIP_SHOW_PREFIX,
)
from app.bot.states import TripEdit, TripForm
from app.models import TRIP_STATUS_NEW, Company, Position, Role
from tests.conftest import (
    ADMIN_ID,
    OWNER_ID,
    STRANGER_ID,
    FakeCallback,
    FakeMessage,
    FakeUser,
    callback_data,
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
            Role(id=3, role=ROLE_USER),
            # Посада дає роль: диспетчер — звичайний користувач, логіст —
            # адміністратор компанії.
            Position(id=1, position="Диспетчер", self_service=True),
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
        logist=await employee(OWNER_ID, ours, "Марія Диспетчер", "+380501112233", 1, 3),
        boss=await employee(ADMIN_ID, ours, "Олег Логіст", "+380502223344", 2, 2),
        # Головного адміністратора не дає жодна посада — його призначають вручну.
        chief=await employee(CHIEF_ID, ours, "Головний Адмін", "+380509998877", 2, 1),
        driver=await employee(DRIVER_ID, ours, "Петро Водій", "+380507778899", 1, 3),
        outsider=await employee(
            STRANGER_ID, theirs, "Чужий Диспетчер", "+380503334455", 1, 3
        ),
    )


async def access_for(session, tg_id: int) -> Access:
    """Access із реального рядка employees — потрібні справжні id."""
    employee = await repository.get_employee_by_tg_id(session, tg_id)
    return Access(telegram_user_id=tg_id, employee=employee)


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
        "client_company_id": creator.company_id,
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
    await step_ttn(FakeMessage("ТТН-000123"), state)
    await step_arrival_date(FakeCallback(f"{TRIP_DATE_PREFIX}:2026-08-10"), state, session)
    await step_exporter(
        FakeCallback(f"{TRIP_EXPORTER_PREFIX}:{exporter_id}"), state, session
    )
    await step_truck(FakeMessage("Volvo FH16"), state)
    await step_truck_plate(FakeMessage("aa1111aa"), state)
    await step_trailer(FakeMessage("Schmitz SKO24"), state)
    await step_trailer_type(FakeMessage("зерновоз"), state)
    await step_trailer_plate(FakeMessage("cc3333cc"), state)
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
    await step_ttn(FakeMessage(steps["ttn"]), state)
    await step_arrival_date(
        FakeCallback(f"{TRIP_DATE_PREFIX}:2026-08-10"), state, session
    )
    await step_exporter(
        FakeCallback(f"{TRIP_EXPORTER_PREFIX}:{exporter_id}"), state, session
    )
    await step_truck(FakeMessage(steps["truck"]), state)
    await step_truck_plate(FakeMessage(steps["truck_plate"]), state)
    await step_trailer(FakeMessage(steps["trailer"]), state)
    await step_trailer_type(FakeMessage(steps["trailer_type"]), state)
    await step_trailer_plate(FakeMessage(steps["trailer_plate"]), state)
    await step_grain(FakeMessage(steps["grain"]), state, session)

    driver_id = overrides.get("driver_id")
    if driver_id is None:
        await step_driver_manual(FakeCallback(TRIP_DRIVER_MANUAL), state)
        await step_driver_name(FakeMessage(steps["driver"]), state)
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


async def test_client_and_logist_come_from_the_creator(
    session, state, world, logist, publisher
):
    """Ці поля не питаються — підставити чужу компанію нічим."""
    callback = await fill_form(state, session, logist, exporter_id=world.theirs.id)

    await step_confirm(callback, state, session, publisher, logist)

    trips, _ = await repository.list_trips(session)
    trip = trips[0]
    assert trip.client_company_id == world.ours.id
    assert trip.exporter_company_id == world.theirs.id
    assert trip.created_by == world.logist.id
    assert trip.logist_fullname == "Марія Диспетчер"
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
    assert "співробітник" in callback.message.answers[0]


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
    await step_ttn(FakeMessage("ТТН-2"), state)
    await step_arrival_date(FakeCallback(f"{TRIP_DATE_PREFIX}:2026-08-10"), state, session)
    await step_exporter(
        FakeCallback(f"{TRIP_EXPORTER_PREFIX}:{world.theirs.id}"), state, session
    )
    await step_truck(FakeMessage("Volvo"), state)
    await step_truck_plate(FakeMessage("AA1111AA"), state)
    await step_trailer(FakeMessage("Schmitz"), state)
    await step_trailer_type(FakeMessage("зерновоз"), state)

    message = FakeMessage("aa1111aa")  # той самий номер, іншим регістром
    await step_trailer_plate(message, state)

    assert await state.get_state() == TripForm.trailer_plate
    assert "не можуть збігатися" in message.answers[0]


async def test_unknown_date_is_rejected(session, state, world, logist):
    await on_new_trip(FakeCallback(MENU_TRIP_NEW, user=FakeUser(OWNER_ID)), state, logist)
    await step_ttn(FakeMessage("ТТН-3"), state)
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
    assert not any("Марія Диспетчер" in label for label in labels)
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
    session, world, logist, publisher
):
    trip = await make_trip(
        session, world.logist, world.theirs, driver_id=world.driver.id
    )
    await repository.set_trip_chat_message(
        session, trip, chat_id=OUR_CHAT_ID, message_id=777
    )
    callback = FakeCallback(f"{TRIP_DELETE_PREFIX}:{trip.id}", user=FakeUser(OWNER_ID))

    await on_trip_delete(callback, session, publisher, logist)

    assert publisher.retracted == [(OUR_CHAT_ID, 777)]
    assert any(chat == DRIVER_ID and "скасовано" in text for chat, text in publisher.sent)


# ---------------------------------------------------------------------------
# Календар
# ---------------------------------------------------------------------------


async def test_calendar_navigation_rolls_over_the_year():
    callback = FakeCallback(f"{TRIP_CAL_PREFIX}:2026:12")
    await on_calendar_nav(callback)

    # Кнопка «›» грудня має вести в січень наступного року.
    data = callback_data(callback.message.markups[0])
    assert f"{TRIP_CAL_PREFIX}:2027:1" in data


async def test_calendar_days_carry_a_full_date():
    callback = FakeCallback(f"{TRIP_CAL_PREFIX}:2026:8")
    await on_calendar_nav(callback)

    data = callback_data(callback.message.markups[0])
    assert f"{TRIP_DATE_PREFIX}:2026-08-01" in data
    assert f"{TRIP_DATE_PREFIX}:2026-08-31" in data
    assert f"{TRIP_DATE_PREFIX}:2026-08-32" not in data


async def test_calendar_rejects_a_forged_month():
    callback = FakeCallback(f"{TRIP_CAL_PREFIX}:2026:13")

    await on_calendar_nav(callback)

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


async def test_ordinary_user_sees_only_own_trips(session, logist, trips):
    text, _ = await render_trips(session, logist)

    assert "МІЙ" in text
    assert "КОЛЕГИ" not in text
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


async def test_colleague_trip_is_readable_only_by_the_admin(
    session, state, logist, boss, trips
):
    for access, expected in ((logist, [DENIED]), (boss, [None])):
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
    assert "Alebor IT 000000" in text
    assert "ТОВ Чужа 99999999" in text
    assert "Марія Диспетчер" in text


# ---------------------------------------------------------------------------
# Редагування
# ---------------------------------------------------------------------------


async def _start_edit(session, state, access, trip_id: int, field: str):
    callback = FakeCallback(f"{TRIP_FIELD_PREFIX}:{field}:{trip_id}")
    await on_trip_field(callback, state, session, access)
    return callback


async def test_editing_records_who_and_when(session, state, boss, trips):
    await _start_edit(session, state, boss, trips.mine.id, "grain")

    await edit_value(FakeMessage("Кукурудза"), state, session, boss)

    trip = await repository.get_trip(session, trips.mine.id)
    assert trip.grain_type == "Кукурудза"
    assert trip.edited_by == (await repository.get_employee_by_tg_id(session, ADMIN_ID)).id
    assert trip.updated_at is not None
    assert await state.get_state() is None


async def test_editing_a_plate_rejects_the_other_one(session, state, logist, trips):
    await _start_edit(session, state, logist, trips.mine.id, "rplate")
    message = FakeMessage("AA1111AA")  # номер тягача цього ж рейсу

    await edit_value(message, state, session, logist)

    assert "не можуть збігатися" in message.answers[0]
    assert await state.get_state() == TripEdit.value


async def test_mass_takes_only_whole_numbers(session, state, logist, trips):
    await _start_edit(session, state, logist, trips.mine.id, "bmass")

    bad = FakeMessage("28,5 тонни")
    await edit_value(bad, state, session, logist)
    assert "Ціле число" in bad.answers[0]

    await edit_value(FakeMessage("28500"), state, session, logist)
    trip = await repository.get_trip(session, trips.mine.id)
    assert trip.b_mass == 28500


async def test_entry_time_is_validated_and_can_be_cleared(
    session, state, logist, trips
):
    await _start_edit(session, state, logist, trips.mine.id, "entry")
    bad = FakeMessage("10.08.2026 07:30")
    await edit_value(bad, state, session, logist)
    assert "РРРР-ММ-ДД" in bad.answers[0]

    await edit_value(FakeMessage("2026-08-10 07:30"), state, session, logist)
    trip = await repository.get_trip(session, trips.mine.id)
    assert trip.datetime_entry == "2026-08-10 07:30"

    await _start_edit(session, state, logist, trips.mine.id, "entry")
    await edit_value(FakeMessage("-"), state, session, logist)
    trip = await repository.get_trip(session, trips.mine.id)
    assert trip.datetime_entry is None


async def test_changing_exporter_refreshes_the_card(session, state, world, logist, trips):
    await _start_edit(session, state, logist, trips.mine.id, "exp")
    assert await state.get_state() == TripEdit.exporter

    callback = FakeCallback(f"{TRIP_EXPORTER_PREFIX}:{world.ours.id}")
    await edit_exporter(callback, state, session, logist)

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
