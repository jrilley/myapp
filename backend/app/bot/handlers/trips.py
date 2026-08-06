"""Рейси: створення, перегляд, редагування, видалення.

Рейс заводить логіст — будь-який зареєстрований співробітник. Компанія-замовник
і контакти логіста не питаються: вони беруться з його запису в employees, тож
підставити чужу компанію неможливо навіть підміною callback_data.

Хто що бачить і чіпає, вирішує матриця прав: право (CRED) плюс його обсяг
(усі рейси / рейси компанії / власні). Обидві половини перевіряє `_may`, і
викликається вона в кожному хендлері: сховати кнопку — не захист.

Права бувають і на рівні поля: оператор має E на рейсах, але лише на масах,
диспетчер — лише на статусі. Це перевіряє `access.may_edit_field`.
"""

from datetime import date, datetime
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app import repository
from app.bot.access import (
    CATEGORY_TRIPS,
    CREATE,
    DELETE,
    EDIT,
    READ,
    SCOPE_ALL,
    SCOPE_COMPANY,
    Access,
)
from app.bot.actions import render_trips
from app.bot.guards import deny
from app.bot.constants import (
    DATE_FORMAT,
    DATETIME_FORMAT,
    MAX_LICENSE_PLATE,
    MAX_PHONE,
    MAX_TRIP_MASS,
    MAX_TRIP_STATUS,
    MAX_TRIP_TEXT,
    MAX_TTN,
    MIN_LICENSE_PLATE,
    MIN_PHONE,
)
from app.bot.formatting import company_label, format_trip, format_trip_summary
from app.bot.handlers.common import menu_for
from app.bot.keyboards import (
    MENU_TRIP_NEW,
    MENU_TRIPS,
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
    after_trip_keyboard,
    calendar_keyboard,
    cancel_keyboard,
    trip_card_keyboard,
    trip_confirm_keyboard,
    trip_drivers_keyboard,
    trip_exporter_keyboard,
    trip_fields_keyboard,
)
from app.bot.publisher import Publisher
from app.bot.states import TripEdit, TripForm
from app.models import Trip

router = Router(name="trips")

DENIED = "Цей рейс вам недоступний."
NEEDS_EMPLOYEE = (
    "Створити рейс може лише зареєстрований співробітник: у рейсі "
    "вказується ваша компанія та ваші контакти як логіста."
)
NO_COMPANIES = "Немає жодної компанії, тож нема кого вказати експортером."

#: Межі навігації календарем. Не обмеження на дату як таку, а захист від
#: підробленого callback_data з роком на п'ять знаків.
MIN_YEAR, MAX_YEAR = 2000, 2100

#: ключ у callback → (колонка в БД, підпис кнопки, тип редактора)
TRIP_FIELDS: dict[str, tuple[str, str, str]] = {
    "ttn": ("ttn_num", "Номер ТТН", "ttn"),
    "date": ("arrival_date", "Дата прибуття", "date"),
    "exp": ("exporter_company_id", "Експортер", "company"),
    "truck": ("truck", "Тягач", "text"),
    "tplate": ("truck_license_plate", "Номер тягача", "plate"),
    "trailer": ("trailer", "Причіп", "text"),
    "ttype": ("trailer_type", "Тип причепа", "text"),
    "rplate": ("trailer_license_plate", "Номер причепа", "plate"),
    "grain": ("grain_type", "Культура", "text"),
    "driver": ("driver_fullname", "ПІБ водія", "text"),
    "dphone": ("driver_phone_number", "Телефон водія", "phone"),
    "entry": ("datetime_entry", "Заїзд", "datetime"),
    "departure": ("datetime_departure", "Виїзд", "datetime"),
    "bmass": ("b_mass", "Брутто", "mass"),
    "tmass": ("t_mass", "Тара", "mass"),
    "nmass": ("n_mass", "Нетто", "mass"),
    "status": ("status", "Статус", "status"),
}

PROMPTS = {
    "ttn": "Новий номер ТТН:",
    "text": "Нове значення:",
    "plate": "Новий державний номер:",
    "phone": "Новий номер телефону:",
    "datetime": "Формат «РРРР-ММ-ДД ГГ:ХХ». Надішліть «-», щоб очистити:",
    "mass": "Маса в кілограмах, ціле число:",
    "status": "Новий статус:",
}


# ---------------------------------------------------------------------------
# Права
# ---------------------------------------------------------------------------


def _in_reach(access: Access, trip: Trip) -> bool:
    """Чи дотягується цей рейс до людини за обсягом її права.

    scope=all — будь-який; scope=company — рейси своєї компанії; scope=own —
    лише ті, які людина створила або в яких вона водій.
    """
    if access.is_main_admin:
        return True
    employee = access.employee
    if employee is None:
        return False

    scope = access.scope(CATEGORY_TRIPS)
    if scope == SCOPE_ALL:
        return True
    if scope == SCOPE_COMPANY:
        return (
            employee.company_id is not None
            and employee.company_id == trip.client_company_id
        )
    return employee.id is not None and employee.id in (trip.created_by, trip.driver_id)


def _may(access: Access, trip: Trip, right: str) -> bool:
    """Право діє, тільки якщо рейс у межах обсягу цього права."""
    return access.can(CATEGORY_TRIPS, right) and _in_reach(access, trip)


async def _trip_or_denied(
    callback: CallbackQuery,
    session: AsyncSession,
    access: Access,
    trip_id: int,
    *,
    right: str = EDIT,
) -> Trip | None:
    trip = await repository.get_trip(session, trip_id)
    if trip is None:
        await callback.answer("Рейс не знайдено", show_alert=True)
        return None
    if not _may(access, trip, right):
        await callback.answer(DENIED, show_alert=True)
        return None
    return trip


def _actor_id(access: Access) -> int | None:
    """id співробітника для колонок аудиту. None — аварійний вхід
    через ADMIN_TELEGRAM_IDS, за яким рядка в employees немає."""
    return access.employee.id if access.employee is not None else None


# ---------------------------------------------------------------------------
# Створення
# ---------------------------------------------------------------------------


@router.callback_query(F.data == MENU_TRIP_NEW)
async def on_new_trip(
    callback: CallbackQuery, state: FSMContext, access: Access
) -> None:
    if await deny(callback, access, CATEGORY_TRIPS, CREATE):
        return
    employee = access.employee
    if employee is None or employee.id is None or employee.company_id is None:
        await callback.answer()
        if callback.message is not None:
            await callback.message.answer(NEEDS_EMPLOYEE, reply_markup=menu_for(access))
        return

    await state.clear()
    # Замовника й логіста фіксуємо одразу: вони не залежать від подальших
    # кроків, і так їх неможливо переписати нічим, що прийде від користувача.
    await state.update_data(
        client_company_id=employee.company_id,
        created_by=employee.id,
        logist_fullname=employee.fullname,
        logist_phone_number=employee.phone_number,
        logist_tg=employee.tg_id,
    )
    await state.set_state(TripForm.ttn)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer("Номер ТТН:", reply_markup=cancel_keyboard())


@router.message(TripForm.ttn, F.text)
async def step_ttn(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not 1 <= len(value) <= MAX_TTN:
        await message.answer(
            f"Номер ТТН має бути від 1 до {MAX_TTN} символів.",
            reply_markup=cancel_keyboard(),
        )
        return
    await state.update_data(ttn_num=value)
    await state.set_state(TripForm.arrival_date)
    today = date.today()
    await message.answer(
        "Дата прибуття автомобіля:",
        reply_markup=calendar_keyboard(today.year, today.month),
    )


@router.callback_query(F.data.startswith(f"{TRIP_CAL_PREFIX}:"))
async def on_calendar_nav(callback: CallbackQuery) -> None:
    """Гортання місяців. Без фільтра стану: календар той самий і при
    створенні рейсу, і при зміні дати в готовому."""
    parts = (callback.data or "").split(":")
    if len(parts) != 4 or not parts[2].isdigit() or not parts[3].isdigit():
        await callback.answer("Не вдалося погортати", show_alert=True)
        return
    year, month = int(parts[2]), int(parts[3])
    if not (MIN_YEAR <= year <= MAX_YEAR and 1 <= month <= 12):
        await callback.answer("Дата поза межами", show_alert=True)
        return

    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_reply_markup(
            reply_markup=calendar_keyboard(year, month)
        )


def _parse_date(callback_data: str | None) -> str | None:
    """«trip:date:РРРР-ММ-ДД» → рядок дати або None, якщо це не дата."""
    raw = (callback_data or "").split(":", 2)
    if len(raw) != 3:
        return None
    try:
        return datetime.strptime(raw[2], DATE_FORMAT).strftime(DATE_FORMAT)
    except ValueError:
        return None


async def _ask_exporter(
    message: Message, state: FSMContext, session: AsyncSession, next_state
) -> bool:
    companies = await repository.list_companies(session)
    if not companies:
        await state.clear()
        await message.answer(NO_COMPANIES)
        return False
    await state.set_state(next_state)
    await message.answer(
        "Компанія-експортер:", reply_markup=trip_exporter_keyboard(companies)
    )
    return True


@router.callback_query(TripForm.arrival_date, F.data.startswith(f"{TRIP_DATE_PREFIX}:"))
async def step_arrival_date(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    value = _parse_date(callback.data)
    if value is None:
        await callback.answer("Невідома дата", show_alert=True)
        return
    await state.update_data(arrival_date=value)
    await callback.answer()
    if callback.message is not None:
        await _ask_exporter(callback.message, state, session, TripForm.exporter)


@router.callback_query(TripForm.exporter, F.data.startswith(f"{TRIP_EXPORTER_PREFIX}:"))
async def step_exporter(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    raw_id = (callback.data or "").rsplit(":", 1)[-1]
    company = (
        await repository.get_company(session, int(raw_id)) if raw_id.isdigit() else None
    )
    if company is None:
        await callback.answer("Невідома компанія", show_alert=True)
        return

    await state.update_data(exporter_company_id=company.id)
    await state.set_state(TripForm.truck)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Тягач — марка й модель:", reply_markup=cancel_keyboard()
        )


def _short_text(value: str) -> str | None:
    """Помилка або None. Спільна перевірка коротких текстових полів рейсу."""
    if not 1 <= len(value) <= MAX_TRIP_TEXT:
        return f"Значення має бути від 1 до {MAX_TRIP_TEXT} символів."
    return None


@router.message(TripForm.truck, F.text)
async def step_truck(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if error := _short_text(value):
        await message.answer(error, reply_markup=cancel_keyboard())
        return
    await state.update_data(truck=value)
    await state.set_state(TripForm.truck_plate)
    await message.answer("Державний номер тягача:", reply_markup=cancel_keyboard())


def _plate(value: str) -> tuple[str, str | None]:
    """(нормалізований номер, помилка). Номери зводимо до верхнього регістру,
    щоб «аа1111аа» і «AA1111AA» не рахувались різними."""
    normalized = value.strip().upper()
    if not MIN_LICENSE_PLATE <= len(normalized) <= MAX_LICENSE_PLATE:
        return normalized, (
            f"Номер має бути від {MIN_LICENSE_PLATE} до {MAX_LICENSE_PLATE} символів."
        )
    return normalized, None


@router.message(TripForm.truck_plate, F.text)
async def step_truck_plate(message: Message, state: FSMContext) -> None:
    value, error = _plate(message.text or "")
    if error:
        await message.answer(error, reply_markup=cancel_keyboard())
        return
    await state.update_data(truck_license_plate=value)
    await state.set_state(TripForm.trailer)
    await message.answer("Причіп — марка й модель:", reply_markup=cancel_keyboard())


@router.message(TripForm.trailer, F.text)
async def step_trailer(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if error := _short_text(value):
        await message.answer(error, reply_markup=cancel_keyboard())
        return
    await state.update_data(trailer=value)
    await state.set_state(TripForm.trailer_type)
    await message.answer(
        "Тип причепа (зерновоз, самоскид тощо):", reply_markup=cancel_keyboard()
    )


@router.message(TripForm.trailer_type, F.text)
async def step_trailer_type(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if error := _short_text(value):
        await message.answer(error, reply_markup=cancel_keyboard())
        return
    await state.update_data(trailer_type=value)
    await state.set_state(TripForm.trailer_plate)
    await message.answer("Державний номер причепа:", reply_markup=cancel_keyboard())


@router.message(TripForm.trailer_plate, F.text)
async def step_trailer_plate(message: Message, state: FSMContext) -> None:
    value, error = _plate(message.text or "")
    if error:
        await message.answer(error, reply_markup=cancel_keyboard())
        return

    data = await state.get_data()
    if value == data.get("truck_license_plate"):
        await message.answer(
            "Номери тягача й причепа не можуть збігатися. Введіть інший.",
            reply_markup=cancel_keyboard(),
        )
        return

    await state.update_data(trailer_license_plate=value)
    await state.set_state(TripForm.grain)
    await message.answer("Культура:", reply_markup=cancel_keyboard())


@router.message(TripForm.grain, F.text)
async def step_grain(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    value = (message.text or "").strip()
    if error := _short_text(value):
        await message.answer(error, reply_markup=cancel_keyboard())
        return
    await state.update_data(grain_type=value)
    await _ask_driver(message, state, session)


async def _ask_driver(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    """Список водіїв компанії. Порожній список не тупик: ручний ввід поруч."""
    data = await state.get_data()
    employees, _ = await repository.list_company_employees(
        session, data["client_company_id"], limit=50
    )
    # Себе зі списку прибираємо: логіст, який сам себе везе, — це або помилка,
    # або той рідкісний випадок, для якого лишається ручний ввід.
    candidates = [e for e in employees if e.id != data["created_by"]]

    await state.set_state(TripForm.driver)
    await message.answer(
        "Оберіть водія:" if candidates
        else "У компанії немає інших зареєстрованих співробітників.",
        reply_markup=trip_drivers_keyboard(candidates),
    )


@router.callback_query(TripForm.driver, F.data == TRIP_DRIVER_MANUAL)
async def step_driver_manual(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(driver_id=None)
    await state.set_state(TripForm.driver_name)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer("ПІБ водія:", reply_markup=cancel_keyboard())


@router.callback_query(TripForm.driver, F.data.startswith(f"{TRIP_DRIVER_PREFIX}:"))
async def step_driver_pick(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    raw_id = (callback.data or "").rsplit(":", 1)[-1]
    employee = (
        await repository.get_employee(session, int(raw_id)) if raw_id.isdigit() else None
    )
    data = await state.get_data()
    # Компанію звіряємо заново: id співробітника приходить у callback_data,
    # і без перевірки водієм можна було б призначити людину з чужої компанії.
    if employee is None or employee.company_id != data["client_company_id"]:
        await callback.answer("Невідомий співробітник", show_alert=True)
        return

    # ПІБ і телефон копіюємо в рейс: він документ і має лишитись читабельним,
    # навіть якщо людина потім змінить прізвище чи піде з компанії.
    await state.update_data(
        driver_id=employee.id,
        driver_fullname=employee.fullname,
        driver_phone_number=employee.phone_number,
    )
    await callback.answer()
    if callback.message is not None:
        await _show_summary(callback.message, state, session)


@router.message(TripForm.driver_name, F.text)
async def step_driver_name(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if error := _short_text(value):
        await message.answer(error, reply_markup=cancel_keyboard())
        return
    await state.update_data(driver_fullname=value)
    await state.set_state(TripForm.driver_phone)
    await message.answer("Телефон водія:", reply_markup=cancel_keyboard())


@router.message(TripForm.driver_phone, F.text)
async def step_driver_phone(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    value = (message.text or "").strip()
    if not MIN_PHONE <= len(value) <= MAX_PHONE:
        await message.answer(
            f"Номер має бути від {MIN_PHONE} до {MAX_PHONE} символів.",
            reply_markup=cancel_keyboard(),
        )
        return

    await state.update_data(driver_phone_number=value)
    await _show_summary(message, state, session)


async def _show_summary(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await state.set_state(TripForm.confirm)
    data = await state.get_data()

    client = await repository.get_company(session, data["client_company_id"])
    exporter = await repository.get_company(session, data["exporter_company_id"])
    await message.answer(
        format_trip_summary(
            data, client=company_label(client), exporter=company_label(exporter)
        ),
        reply_markup=trip_confirm_keyboard(),
    )


#: Колонки, які беруться з форми. Перелік явний, щоб службові ключі стану
#: (наприклад, назви компаній для підсумку) не потрапили в модель.
TRIP_COLUMNS = (
    "ttn_num", "arrival_date", "client_company_id", "exporter_company_id",
    "created_by", "logist_fullname", "logist_phone_number", "logist_tg",
    "truck", "truck_license_plate", "trailer", "trailer_type",
    "trailer_license_plate", "grain_type", "driver_id", "driver_fullname",
    "driver_phone_number",
)


async def _announce(session: AsyncSession, publisher: Publisher, trip: Trip) -> str:
    """Розсилає створений рейс і повертає рядок про те, що вийшло.

    Рейс уже в базі, тож жоден збій тут його не скасовує: Telegram буває
    недоступний, водій міг не запускати бота, бота могли прибрати з групи.
    Але мовчати про це не можна — логіст має знати, що водій не отримав
    рейсу, інакше він вважатиме, що все дійшло.
    """
    notes = []

    driver = trip.driver
    if driver is not None:
        sent = await publisher.send(
            driver.tg_id, f"🆕 <b>Вам призначено рейс</b>\n\n{format_trip(trip)}"
        )
        notes.append(
            "Водія сповіщено." if sent is not None
            else "⚠️ Водієві не вдалося написати — можливо, він ще не "
                 "запускав бота або заблокував його."
        )
    else:
        notes.append("Водій сторонній — сповіщення не надсилалось.")

    company = trip.client_company
    chat_id = company.company_chat_id if company else None
    if chat_id is None:
        notes.append("Робочий чат компанії не вказано — рейс нікуди не дубльовано.")
    else:
        sent = await publisher.send(
            chat_id, f"🆕 <b>Новий рейс</b>\n\n{format_trip(trip)}"
        )
        if sent is None:
            notes.append(
                "⚠️ У робочий чат не вдалося — перевірте, чи бот доданий у групу."
            )
        else:
            await repository.set_trip_chat_message(
                session, trip, chat_id=sent.chat_id, message_id=sent.message_id
            )
            notes.append("Продубльовано в робочий чат.")
            if sent.chat_id != chat_id:
                # Група стала супергрупою й змінила id. Старий мертвий, тож
                # запам'ятовуємо новий одразу — інакше кожен наступний рейс
                # так само впирався б у неіснуючий чат.
                await repository.update_company(
                    session, company, company_chat_id=sent.chat_id
                )
                notes.append(
                    f"Групу оновлено до супергрупи — id чату змінено на "
                    f"<code>{sent.chat_id}</code>."
                )

    return "\n".join(notes)


@router.callback_query(TripForm.confirm, F.data == TRIP_CONFIRM)
async def step_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    publisher: Publisher,
    access: Access,
) -> None:
    data = await state.get_data()
    await state.clear()
    await callback.answer()
    if callback.message is None:
        return

    # Компанію могли видалити, поки форма була відкрита; без перевірки це
    # впало б помилкою зовнішнього ключа вже після «Створити».
    if await repository.get_company(session, data["exporter_company_id"]) is None:
        await callback.message.answer(
            "Обрана компанія-експортер більше не існує. Створіть рейс заново.",
            reply_markup=menu_for(access),
        )
        return

    trip = await repository.create_trip(
        session, **{name: data.get(name) for name in TRIP_COLUMNS}
    )
    report = await _announce(session, publisher, trip)
    await callback.message.answer(
        f"✅ Рейс #{trip.id} створено.\n\n{format_trip(trip)}\n\n{report}",
        reply_markup=after_trip_keyboard(),
    )


# ---------------------------------------------------------------------------
# Перегляд
# ---------------------------------------------------------------------------


@router.callback_query(F.data == MENU_TRIPS)
async def on_trips(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    await state.clear()
    await callback.answer()
    if callback.message is not None:
        text, keyboard = await render_trips(session, access)
        await callback.message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith(f"{TRIP_SHOW_PREFIX}:"))
async def on_trip_card(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    raw_id = (callback.data or "").rsplit(":", 1)[-1]
    if not raw_id.isdigit():
        await callback.answer("Невідомий рейс", show_alert=True)
        return

    trip = await _trip_or_denied(callback, session, access, int(raw_id), right=READ)
    if trip is None:
        return

    await state.clear()
    await callback.answer()
    if callback.message is not None:
        # Кнопок, які все одно відмовлять, не показуємо: зайва кнопка
        # виглядає як помилка системи.
        await callback.message.answer(
            format_trip(trip),
            reply_markup=trip_card_keyboard(
                trip.id,
                editable=_may(access, trip, EDIT),
                deletable=_may(access, trip, DELETE),
            ),
        )


# ---------------------------------------------------------------------------
# Редагування
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith(f"{TRIP_EDIT_PREFIX}:"))
async def on_trip_edit(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    """Меню полів: редактор один, а що саме він змінює — вибирає кнопка."""
    raw_id = (callback.data or "").rsplit(":", 1)[-1]
    if not raw_id.isdigit():
        await callback.answer("Невідомий рейс", show_alert=True)
        return

    trip = await _trip_or_denied(callback, session, access, int(raw_id))
    if trip is None:
        return

    await state.clear()
    await callback.answer()
    if callback.message is not None:
        # Показуємо лише те, що ця роль справді може змінити: оператору —
        # маси, диспетчеру — статус.
        fields = [
            (key, title)
            for key, (_, title, _) in TRIP_FIELDS.items()
            if access.may_edit_field(CATEGORY_TRIPS, key)
        ]
        if not fields:
            await callback.message.answer(DENIED)
            return
        await callback.message.answer(
            f"Рейс #{trip.id}. Що змінюємо?",
            reply_markup=trip_fields_keyboard(trip.id, fields),
        )


@router.callback_query(F.data.startswith(f"{TRIP_FIELD_PREFIX}:"))
async def on_trip_field(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 4 or not parts[3].isdigit():
        await callback.answer("Невідоме поле", show_alert=True)
        return
    key = parts[2]
    if key not in TRIP_FIELDS:
        await callback.answer("Невідоме поле", show_alert=True)
        return
    # Право E ще не означає, що можна чіпати саме це поле.
    if not access.may_edit_field(CATEGORY_TRIPS, key):
        await callback.answer(DENIED, show_alert=True)
        return

    trip = await _trip_or_denied(callback, session, access, int(parts[3]))
    if trip is None:
        return

    _, title, kind = TRIP_FIELDS[key]
    await callback.answer()
    if callback.message is None:
        return

    # clear до update_data: інакше в стані лишились би ключі з попередньої
    # форми, і редактор працював би з чужими даними.
    await state.clear()
    await state.update_data(trip_id=trip.id, field=key)
    if kind == "date":
        await state.set_state(TripEdit.arrival_date)
        today = date.today()
        await callback.message.answer(
            "Нова дата прибуття:",
            reply_markup=calendar_keyboard(today.year, today.month),
        )
        return
    if kind == "company":
        await _ask_exporter(callback.message, state, session, TripEdit.exporter)
        return

    await state.set_state(TripEdit.value)
    await callback.message.answer(
        f"<b>{escape(title)}</b>\n{PROMPTS[kind]}", reply_markup=cancel_keyboard()
    )


def _validate(kind: str, column: str, raw: str, trip: Trip):
    """(значення, помилка) — рівно одне з двох є None.

    Значення теж може бути None (очищення часу), тому гілкуватись треба
    саме за помилкою, а не за істинністю значення.
    """
    value = raw.strip()
    if kind == "ttn":
        if not 1 <= len(value) <= MAX_TTN:
            return None, f"Номер ТТН має бути від 1 до {MAX_TTN} символів."
        return value, None
    if kind == "text":
        error = _short_text(value)
        return (None, error) if error else (value, None)
    if kind == "plate":
        normalized, error = _plate(value)
        if error:
            return None, error
        other = (
            trip.trailer_license_plate
            if column == "truck_license_plate"
            else trip.truck_license_plate
        )
        if normalized == other:
            return None, "Номери тягача й причепа не можуть збігатися."
        return normalized, None
    if kind == "phone":
        if not MIN_PHONE <= len(value) <= MAX_PHONE:
            return None, f"Номер має бути від {MIN_PHONE} до {MAX_PHONE} символів."
        return value, None
    if kind == "datetime":
        if value == "-":
            return None, None
        try:
            parsed = datetime.strptime(value, DATETIME_FORMAT)
        except ValueError:
            return None, "Очікую «РРРР-ММ-ДД ГГ:ХХ», наприклад 2026-08-10 07:30."
        return parsed.strftime(DATETIME_FORMAT), None
    if kind == "mass":
        if not value.isdigit() or int(value) > MAX_TRIP_MASS:
            return None, f"Ціле число від 0 до {MAX_TRIP_MASS}."
        return int(value), None
    if kind == "status":
        if not 2 <= len(value) <= MAX_TRIP_STATUS:
            return None, f"Статус має бути від 2 до {MAX_TRIP_STATUS} символів."
        return value, None
    return None, "Невідоме поле."


async def _apply(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    access: Access,
    trip: Trip,
    **fields,
) -> None:
    await state.clear()
    updated = await repository.update_trip(
        session, trip, editor_id=_actor_id(access), **fields
    )
    await message.answer(
        format_trip(updated),
        reply_markup=trip_card_keyboard(
            updated.id,
            editable=_may(access, updated, EDIT),
            deletable=_may(access, updated, DELETE),
        ),
    )


async def _editable_trip(
    message: Message, state: FSMContext, session: AsyncSession, access: Access
) -> Trip | None:
    """Рейс із поточного стану — з повторною перевіркою прав.

    Між натисканням кнопки й надсиланням значення минає час, тому право
    перевіряємо ще раз, а не покладаємось на те, що воно було при вході.
    """
    data = await state.get_data()
    trip = await repository.get_trip(session, data.get("trip_id", 0))
    if trip is None:
        await state.clear()
        await message.answer("Рейс не знайдено.")
        return None
    if not _may(access, trip, EDIT):
        await state.clear()
        await message.answer(DENIED)
        return None
    return trip


@router.message(TripEdit.value, F.text)
async def edit_value(
    message: Message, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    trip = await _editable_trip(message, state, session, access)
    if trip is None:
        return

    data = await state.get_data()
    key = data.get("field", "")
    if not access.may_edit_field(CATEGORY_TRIPS, key):
        await state.clear()
        await message.answer(DENIED)
        return
    field = TRIP_FIELDS.get(key)
    if field is None:
        # Стан розійшовся з даними — почати спочатку зрозуміліше, ніж
        # мовчки зберегти значення не в те поле.
        await state.clear()
        await message.answer("Не зрозуміло, що саме редагуємо. Відкрийте рейс заново.")
        return
    column, _, kind = field
    value, error = _validate(kind, column, message.text or "", trip)
    if error:
        await message.answer(error, reply_markup=cancel_keyboard())
        return
    await _apply(message, state, session, access, trip, **{column: value})


@router.callback_query(TripEdit.arrival_date, F.data.startswith(f"{TRIP_DATE_PREFIX}:"))
async def edit_arrival_date(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    value = _parse_date(callback.data)
    if value is None:
        await callback.answer("Невідома дата", show_alert=True)
        return
    if not access.may_edit_field(CATEGORY_TRIPS, "date"):
        await callback.answer(DENIED, show_alert=True)
        return
    await callback.answer()
    if callback.message is None:
        return
    trip = await _editable_trip(callback.message, state, session, access)
    if trip is None:
        return
    await _apply(
        callback.message, state, session, access, trip, arrival_date=value
    )


@router.callback_query(TripEdit.exporter, F.data.startswith(f"{TRIP_EXPORTER_PREFIX}:"))
async def edit_exporter(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    raw_id = (callback.data or "").rsplit(":", 1)[-1]
    company = (
        await repository.get_company(session, int(raw_id)) if raw_id.isdigit() else None
    )
    if company is None:
        await callback.answer("Невідома компанія", show_alert=True)
        return
    if not access.may_edit_field(CATEGORY_TRIPS, "exp"):
        await callback.answer(DENIED, show_alert=True)
        return
    await callback.answer()
    if callback.message is None:
        return
    trip = await _editable_trip(callback.message, state, session, access)
    if trip is None:
        return
    await _apply(
        callback.message, state, session, access, trip, exporter_company_id=company.id
    )


# ---------------------------------------------------------------------------
# Видалення
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith(f"{TRIP_DELETE_PREFIX}:"))
async def on_trip_delete(
    callback: CallbackQuery,
    session: AsyncSession,
    publisher: Publisher,
    access: Access,
) -> None:
    raw_id = (callback.data or "").rsplit(":", 1)[-1]
    if not raw_id.isdigit():
        await callback.answer("Невідомий рейс", show_alert=True)
        return

    trip = await _trip_or_denied(callback, session, access, int(raw_id), right=DELETE)
    if trip is None:
        return

    # Читаємо до видалення: soft_delete_trip робить refresh, після якого
    # звернення до зв'язків тягне ліниве завантаження.
    trip_id = trip.id
    chat_id, chat_message_id = trip.chat_id, trip.chat_message_id
    driver_tg = trip.driver.tg_id if trip.driver is not None else None

    await repository.soft_delete_trip(session, trip, deleted_by=_actor_id(access))

    if chat_id is not None and chat_message_id is not None:
        # Best-effort: збій у Telegram не має скасовувати видалення в базі.
        await publisher.retract(
            chat_id, chat_message_id, note=f"🗑 <i>Рейс #{trip_id} скасовано.</i>"
        )
    if driver_tg is not None:
        await publisher.send(driver_tg, f"🗑 Рейс #{trip_id} скасовано.")

    await callback.answer(f"🗑 Рейс #{trip_id} видалено")

    # Перемальовуємо список на місці, щоб видалений рейс одразу зник.
    if callback.message is not None:
        text, keyboard = await render_trips(session, access)
        await callback.message.edit_text(text, reply_markup=keyboard)


@router.message(TripForm.ttn)
@router.message(TripForm.truck)
@router.message(TripForm.truck_plate)
@router.message(TripForm.trailer)
@router.message(TripForm.trailer_type)
@router.message(TripForm.trailer_plate)
@router.message(TripForm.grain)
@router.message(TripForm.driver_name)
@router.message(TripForm.driver_phone)
@router.message(TripEdit.value)
async def non_text(message: Message) -> None:
    await message.answer(
        "Надішліть, будь ласка, текст.", reply_markup=cancel_keyboard()
    )


@router.message(TripForm.arrival_date)
@router.message(TripEdit.arrival_date)
async def expects_calendar(message: Message) -> None:
    today = date.today()
    await message.answer(
        "Оберіть дату в календарі нижче.",
        reply_markup=calendar_keyboard(today.year, today.month),
    )
