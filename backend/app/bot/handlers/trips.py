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
from aiogram.filters import StateFilter
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
    MAX_COMPANY_NAME,
    MAX_LICENSE_PLATE,
    MAX_PHONE,
    MAX_TRIP_MASS,
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
    TRIP_BACK,
    TRIP_CAL_PREFIX,
    TRIP_CHOICE_PREFIX,
    TRIP_CHOICES,
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
    TRIP_NOW,
    TRIP_REDO,
    TRIP_REDO_PREFIX,
    TRIP_SHOW_PREFIX,
    TRIP_STATUS_PREFIX,
    TRIP_MARK_NEW,
    TRIP_MARK_PREFIX,
    TRIP_TTYPE_PREFIX,
    TRIP_VEHICLE_MANUAL,
    TRIP_VEHICLE_PREFIX,
    after_trip_keyboard,
    calendar_keyboard,
    cancel_keyboard,
    trip_card_keyboard,
    trip_choice_keyboard,
    trip_client_keyboard,
    trip_confirm_keyboard,
    trip_datetime_keyboard,
    trip_drivers_keyboard,
    trip_exporter_keyboard,
    trip_fields_keyboard,
    trip_mark_keyboard,
    trip_redo_keyboard,
    trip_status_keyboard,
    trip_step_keyboard,
    trip_vehicle_keyboard,
    trip_vehicle_type_keyboard,
)
from app.bot.publisher import Publisher
from app.bot.states import TripEdit, TripForm
from app.models import TRIP_STATUSES, Trip, Vehicle

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
    # Тягач і причіп — вибір із довідника. Окремого поля під номер немає й
    # бути не може: номер належить машині, а не рейсу.
    "truck": ("truck_id", "Тягач", "vehicle"),
    "trailer": ("trailer_id", "Причіп", "vehicle"),
    "grain": ("grain_type", "Культура", "text"),
    # Водій — не підпис, а призначення: разом із ПІБ і телефоном міняється
    # driver_id, інакше рейс лишився б за попередньою людиною.
    "driver": ("driver_id", "Водій", "driver"),
    "dphone": ("driver_phone_number", "Телефон водія", "phone"),
    "entry": ("datetime_entry", "Заїзд", "datetime"),
    "departure": ("datetime_departure", "Виїзд", "datetime"),
    "bmass": ("b_mass", "Брутто", "mass"),
    "tmass": ("t_mass", "Тара", "mass"),
    # «Нетто» тут немає навмисно: воно рахується з брутто й тари. Окреме поле
    # дозволяло б зберегти брутто 20000, тару 25000 і нетто 3 — три числа,
    # які не складаються в жодну вагу.
    "status": ("status", "Статус", "status"),
}

PROMPTS = {
    "ttn": "Новий номер ТТН:",
    "text": "Нове значення:",
    "plate": "Новий державний номер:",
    "phone": "Новий номер телефону:",
    "datetime": "Кнопкою нижче або текстом у форматі «РРРР-ММ-ДД ГГ:ХХ»:",
    "mass": "Маса в кілограмах, ціле число:",
}

#: Зміни, про які водій має дізнатись. Перелік вузький навмисно: сповіщати про
#: кожну правку маси — це не інформування, а спам, після якого перестають
#: читати й важливе.
NOTIFY_DRIVER_FIELDS = frozenset({"date", "status", "driver"})


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
            and employee.company_id == trip.owner_company_id
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


def _leaving_driver(trip: Trip, new_driver_id: int | None) -> int | None:
    """Telegram id водія, з якого рейс знімають, або None, якщо він той самий.

    Читається до збереження: після нього в рейсі стоїть уже новий водій, і
    сказати старому, що рейс не за ним, буде нікому.
    """
    if trip.driver is None or trip.driver_id == new_driver_id:
        return None
    return trip.driver.tg_id


def _actor_id(access: Access) -> int | None:
    """id співробітника для колонок аудиту. None — аварійний вхід
    через ADMIN_TELEGRAM_IDS, за яким рядка в employees немає."""
    return access.employee.id if access.employee is not None else None


def _choice(callback_data: str | None, kind: str) -> str | None:
    """«trip:pick:<вид>:<номер>» → значення з переліку, або None."""
    parts = (callback_data or "").split(":")
    if len(parts) != 4 or parts[2] != kind or not parts[3].isdigit():
        return None
    options = TRIP_CHOICES.get(kind, ())
    index = int(parts[3])
    return options[index] if index < len(options) else None


async def _trailer_type_name(
    callback: CallbackQuery, session: AsyncSession
) -> str | None:
    """Назва виду причепа з callback_data. У ній id рядка довідника, а не
    номер у списку: довідник поповнюють люди, і позиція в ньому не стала.

    У рейс іде саме назва, а не посилання: рейс — документ, і він має
    лишитись читабельним, якщо вид потім перейменують."""
    type_id = (callback.data or "").rsplit(":", 1)[-1]
    vehicle_type = (
        await repository.get_vehicle_type(session, int(type_id))
        if type_id.isdigit()
        else None
    )
    if vehicle_type is None:
        await callback.answer("Невідомий вид", show_alert=True)
        return None
    return vehicle_type.name


def _masses(trip: Trip, column: str, value: int) -> tuple[dict, str | None]:
    """Значення для збереження — брутто, тара й порахуване з них нетто.

    Нетто ніхто не вводить: воно похідне, і поки його зберігали окремо, ніщо
    не заважало трьом числам не складатись. Порівнюємо лише коли задані
    обидва: до зважування тара може стояти без брутто.
    """
    gross = value if column == "b_mass" else trip.b_mass
    tare = value if column == "t_mass" else trip.t_mass
    if gross and tare and tare > gross:
        return {}, "Тара більша за брутто — перевірте, будь ласка, числа."
    return {column: value, "n_mass": max(gross - tare, 0)}, None


# ---------------------------------------------------------------------------
# Створення
# ---------------------------------------------------------------------------
#
# Кожен крок анкети розділений надвоє: `_ask_*` питає, `step_*` зберігає.
# Розділення потрібне не заради симетрії: маючи «запитати» окремою функцією,
# той самий крок можна відкрити повторно — кнопкою «⬅️ Назад» або з екрана
# підтвердження, — не переписуючи ні текст питання, ні клавіатуру.
#
# Усі `_ask_*` мають однакову сигнатуру, навіть коли сесія комусь не потрібна:
# інакше таблиця переходів розпалась би на окремі гілки за кількістю аргументів.


async def _ask_ttn(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.set_state(TripForm.ttn)
    # Перший крок — повертатись нікуди, тож і кнопки «Назад» тут немає.
    await message.answer("Номер ТТН:", reply_markup=cancel_keyboard())


async def _ask_arrival_date(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await state.set_state(TripForm.arrival_date)
    today = date.today()
    await message.answer(
        "Дата прибуття автомобіля:",
        reply_markup=calendar_keyboard(today.year, today.month, back=True),
    )


async def _ask_client(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    """Замовника не беремо з того, хто заповнює: рейс возять для чужої
    компанії, і його власна компанія тут ні до чого."""
    await state.set_state(TripForm.client)
    companies = await repository.list_companies(session)
    await message.answer(
        "Компанія-замовник:", reply_markup=trip_client_keyboard(companies, back=True)
    )


async def _ask_client_name(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await state.set_state(TripForm.client_name)
    await message.answer(
        "Назва компанії-замовника:", reply_markup=trip_step_keyboard()
    )


async def _ask_exporter(
    message: Message, state: FSMContext, session: AsyncSession, next_state
) -> bool:
    """False — коли компаній немає взагалі й крок нема чим заповнити."""
    companies = await repository.list_companies(session)
    if not companies:
        await state.clear()
        await message.answer(NO_COMPANIES)
        return False
    await state.set_state(next_state)
    await message.answer(
        "Компанія-експортер:",
        reply_markup=trip_exporter_keyboard(
            companies, back=next_state == TripForm.exporter
        ),
    )
    return True


async def _ask_trip_exporter(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await _ask_exporter(message, state, session, TripForm.exporter)


async def _ask_vehicle(
    message: Message, state: FSMContext, session: AsyncSession, kind: str
) -> None:
    """Транспорт із довідника компанії. Порожній список не тупик: ручний
    ввід поруч — рейс може виконувати й чужа машина."""
    data = await state.get_data()
    vehicles = await repository.list_vehicles_for_pick(
        session, kind, data["owner_company_id"]
    )
    await state.set_state(
        TripForm.truck if kind == "truck" else TripForm.trailer
    )
    what = "тягач" if kind == "truck" else "причіп"
    await message.answer(
        f"Оберіть {what}:" if vehicles
        else f"У довіднику компанії немає жодного: {what} доведеться ввести вручну.",
        reply_markup=trip_vehicle_keyboard(kind, vehicles),
    )


async def _ask_truck(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await _ask_vehicle(message, state, session, "truck")


# Заведення машини прямо з анкети. Чужа машина теж має бути в довіднику:
# рейс на неї посилається, і класти марку з номером у сам рейс означало б
# знову тримати дві правди про один транспорт.


async def _ask_vehicle_type(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    """Вид нової машини. Тягач у довіднику зазвичай один — тоді не питаємо."""
    data = await state.get_data()
    kind = data.get("vehicle_kind", "truck")
    types = await repository.list_vehicle_types(session, tractors=kind == "truck")
    if len(types) == 1:
        await state.update_data(v_type_id=types[0].id)
        await _ask_vehicle_mark(message, state, session)
        return
    await state.set_state(TripForm.v_type)
    await message.answer(
        "Вид:", reply_markup=trip_vehicle_type_keyboard(types)
    )


async def _ask_vehicle_mark(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await state.set_state(TripForm.v_mark)
    marks = await repository.list_vehicle_marks(session)
    await message.answer(
        "Марка й модель:" if marks else "Довідник марок порожній — додайте першу.",
        reply_markup=trip_mark_keyboard(marks),
    )


async def _ask_vehicle_plate(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await state.set_state(TripForm.v_plate)
    await message.answer("Державний номер:", reply_markup=trip_step_keyboard())


async def _ask_trailer(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await _ask_vehicle(message, state, session, "trailer")


async def _back_to_vehicle(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    """Назад із заведення машини — на той вибір, з якого в нього зайшли."""
    data = await state.get_data()
    await _ask_vehicle(message, state, session, data.get("vehicle_kind", "truck"))


async def _ask_grain(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await state.set_state(TripForm.grain)
    await message.answer(
        "Культура — оберіть або введіть свою:",
        reply_markup=trip_choice_keyboard("grain", back=True),
    )


async def _driver_candidates(
    session: AsyncSession, company_id: int, *, exclude_id: int | None
) -> list:
    """Склад компанії без того, хто веде рейс.

    Себе зі списку прибираємо: логіст, який сам себе везе, — це або помилка,
    або той рідкісний випадок, для якого лишається ручний ввід.
    """
    employees, _ = await repository.list_company_employees(
        session, company_id, limit=50
    )
    return [e for e in employees if e.id != exclude_id]


async def _ask_driver(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    """Список водіїв компанії. Порожній список не тупик: ручний ввід поруч."""
    data = await state.get_data()
    candidates = await _driver_candidates(
        session, data["owner_company_id"], exclude_id=data["created_by"]
    )

    await state.set_state(TripForm.driver)
    await message.answer(
        "Оберіть водія:" if candidates
        else "У компанії немає інших зареєстрованих співробітників.",
        reply_markup=trip_drivers_keyboard(candidates, back=True),
    )


async def _ask_driver_name(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await state.set_state(TripForm.driver_name)
    await message.answer("ПІБ водія:", reply_markup=trip_step_keyboard())


async def _ask_driver_phone(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await state.set_state(TripForm.driver_phone)
    await message.answer("Телефон водія:", reply_markup=trip_step_keyboard())


#: Стан → крок, на який веде «⬅️ Назад». Таблиця явна, а не арифметика по
#: індексу: анкета розгалужується (замовник зі списку чи руками, водій зі
#: складу чи сторонній), і «попередній» там не означає «на одиницю менший».
BACK_TO = {
    TripForm.arrival_date.state: _ask_ttn,
    TripForm.client.state: _ask_arrival_date,
    TripForm.client_name.state: _ask_client,
    TripForm.exporter.state: _ask_client,
    TripForm.truck.state: _ask_trip_exporter,
    TripForm.trailer.state: _ask_truck,
    # Заведення машини — гілка всередині свого кроку, тож «Назад» із неї веде
    # на той самий вибір, з якого в неї зайшли.
    TripForm.v_type.state: _back_to_vehicle,
    TripForm.v_mark.state: _back_to_vehicle,
    TripForm.v_mark_name.state: _ask_vehicle_mark,
    TripForm.v_plate.state: _ask_vehicle_mark,
    TripForm.grain.state: _ask_trailer,
    TripForm.driver.state: _ask_grain,
    TripForm.driver_name.state: _ask_driver,
    TripForm.driver_phone.state: _ask_driver_name,
}

#: Що можна переробити з екрана підтвердження: ключ → (підпис, крок).
#: Ключі ті самі, що й у TRIP_FIELDS, — щоб одне поле не звалось у двох
#: місцях по-різному.
REDO_STEPS = {
    "ttn": ("Номер ТТН", _ask_ttn),
    "date": ("Дата прибуття", _ask_arrival_date),
    "client": ("Замовник", _ask_client),
    "exp": ("Експортер", _ask_trip_exporter),
    # Тягач і причіп ведуть на свій крок цілком: обрати машину з довідника —
    # це і марка, і номер, і вид причепа разом, а правити їх поодинці означало
    # б розсинхронити їх із самим записом.
    "truck": ("Тягач", _ask_truck),
    "trailer": ("Причіп", _ask_trailer),
    "grain": ("Культура", _ask_grain),
    "driver": ("Водій", _ask_driver),
}


async def _advance(
    message: Message, state: FSMContext, session: AsyncSession, next_step
) -> None:
    """Куди йти після збереженого кроку.

    Зазвичай — далі анкетою. Але якщо крок відкрили з екрана підтвердження,
    вести людину рештою кроків заново означало б покарати її за одну описку.
    """
    data = await state.get_data()
    if data.get("return_to_summary"):
        await _show_summary(message, state, session)
        return
    await next_step(message, state, session)


@router.callback_query(F.data == TRIP_BACK)
async def on_form_back(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """Один крок назад. Уже введене лишається в стані, тож повернення вперед
    нічого не втрачає."""
    step = BACK_TO.get(await state.get_state() or "")
    if step is None:
        await callback.answer("Повертатись нікуди", show_alert=True)
        return
    await callback.answer()
    if callback.message is not None:
        await step(callback.message, state, session)


@router.callback_query(TripForm.confirm, F.data == TRIP_REDO)
async def on_redo(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Що змінюємо?",
            reply_markup=trip_redo_keyboard(
                [(key, title) for key, (title, _) in REDO_STEPS.items()]
            ),
        )


@router.callback_query(TripForm.confirm, F.data.startswith(f"{TRIP_REDO_PREFIX}:"))
async def on_redo_step(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    key = (callback.data or "").rsplit(":", 1)[-1]
    step = REDO_STEPS.get(key)
    if step is None:
        await callback.answer("Невідоме поле", show_alert=True)
        return
    # Прапорець живе до наступного збереженого кроку: саме він поверне
    # людину на підсумок замість решти анкети.
    await state.update_data(return_to_summary=True)
    await callback.answer()
    if callback.message is not None:
        await step[1](callback.message, state, session)


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
    # Компанію-власника й логіста фіксуємо одразу: вони не залежать від
    # подальших кроків, і так їх неможливо переписати нічим, що прийде
    # від користувача.
    # Менеджер у рейсі — це created_by. Дублювати сюди його ПІБ і телефон
    # означало б знову тримати дві правди про одну людину.
    await state.update_data(
        owner_company_id=employee.company_id,
        created_by=employee.id,
    )
    await state.set_state(TripForm.ttn)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer("Номер ТТН:", reply_markup=cancel_keyboard())


@router.message(TripForm.ttn, F.text)
async def step_ttn(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    value = (message.text or "").strip()
    if not 1 <= len(value) <= MAX_TTN:
        await message.answer(
            f"Номер ТТН має бути від 1 до {MAX_TTN} символів.",
            reply_markup=cancel_keyboard(),
        )
        return
    await state.update_data(ttn_num=value)
    await _advance(message, state, session, _ask_arrival_date)


@router.callback_query(F.data.startswith(f"{TRIP_CAL_PREFIX}:"))
async def on_calendar_nav(callback: CallbackQuery, state: FSMContext) -> None:
    """Гортання місяців. Без фільтра стану: календар той самий і при
    створенні рейсу, і при зміні дати в готовому. Кнопку «Назад» лишаємо
    тільки в анкеті — у картці повертатись нікуди."""
    parts = (callback.data or "").split(":")
    if len(parts) != 4 or not parts[2].isdigit() or not parts[3].isdigit():
        await callback.answer("Не вдалося погортати", show_alert=True)
        return
    year, month = int(parts[2]), int(parts[3])
    if not (MIN_YEAR <= year <= MAX_YEAR and 1 <= month <= 12):
        await callback.answer("Дата поза межами", show_alert=True)
        return

    in_form = await state.get_state() == TripForm.arrival_date.state
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_reply_markup(
            reply_markup=calendar_keyboard(year, month, back=in_form)
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
        await _advance(callback.message, state, session, _ask_client)


@router.callback_query(TripForm.client, F.data == TRIP_CLIENT_MANUAL)
async def step_client_manual(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """Ручний ввід — не наступний крок, а друга половина цього: підсумок
    чекає на назву, а не на порожнє поле."""
    await state.update_data(client_company_id=None)
    await callback.answer()
    if callback.message is not None:
        await _ask_client_name(callback.message, state, session)


@router.callback_query(TripForm.client, F.data.startswith(f"{TRIP_CLIENT_PREFIX}:"))
async def step_client_pick(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    raw_id = (callback.data or "").rsplit(":", 1)[-1]
    company = (
        await repository.get_company(session, int(raw_id)) if raw_id.isdigit() else None
    )
    if company is None:
        await callback.answer("Невідома компанія", show_alert=True)
        return

    # Назву копіюємо в рейс і при виборі зі списку: рейс — документ, і він
    # має лишитись читабельним, якщо компанію потім перейменують.
    await state.update_data(
        client_company_id=company.id,
        client_company_name=company_label(company),
    )
    await callback.answer()
    if callback.message is not None:
        await _advance(callback.message, state, session, _ask_trip_exporter)


@router.message(TripForm.client_name, F.text)
async def step_client_name(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    value = (message.text or "").strip()
    if not 2 <= len(value) <= MAX_COMPANY_NAME:
        await message.answer(
            f"Назва має бути від 2 до {MAX_COMPANY_NAME} символів.",
            reply_markup=trip_step_keyboard(),
        )
        return
    await state.update_data(client_company_name=value)
    await _advance(message, state, session, _ask_trip_exporter)


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
    await callback.answer()
    if callback.message is not None:
        await _advance(callback.message, state, session, _ask_truck)


def _short_text(value: str) -> str | None:
    """Помилка або None. Спільна перевірка коротких текстових полів рейсу."""
    if not 1 <= len(value) <= MAX_TRIP_TEXT:
        return f"Значення має бути від 1 до {MAX_TRIP_TEXT} символів."
    return None


async def _picked_vehicle(
    callback: CallbackQuery, session: AsyncSession, company_id: int, kind: str
) -> Vehicle | None:
    """Машина з callback_data — з перевіркою, що вона тієї компанії й того
    виду. Id приходить ззовні, тож і те, і те звіряємо заново."""
    parts = (callback.data or "").split(":")
    if len(parts) != 4 or not parts[3].isdigit():
        await callback.answer("Невідомий транспорт", show_alert=True)
        return None
    vehicle = await repository.get_vehicle(session, int(parts[3]))
    if (
        vehicle is None
        or vehicle.deleted_at is not None
        or vehicle.owner_company_id != company_id
        or vehicle.is_tractor != (kind == "truck")
    ):
        await callback.answer("Невідомий транспорт", show_alert=True)
        return None
    return vehicle


async def _use_vehicle(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    vehicle: Vehicle,
) -> None:
    """Записати машину в рейс і піти далі: після тягача — причіп, після
    причепа — культура."""
    kind = (await state.get_data()).get("vehicle_kind", "truck")
    if kind == "truck":
        await state.update_data(truck_id=vehicle.id)
        await _advance(message, state, session, _ask_trailer)
        return
    await state.update_data(trailer_id=vehicle.id)
    await _advance(message, state, session, _ask_grain)


@router.callback_query(
    StateFilter(TripForm.truck, TripForm.trailer),
    F.data.startswith(f"{TRIP_VEHICLE_PREFIX}:"),
)
async def step_vehicle_pick(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """Машина з довідника. Марка, номер і вид причепа приходять разом із нею —
    у рейсі лишається саме посилання."""
    data = await state.get_data()
    kind = "truck" if await state.get_state() == TripForm.truck.state else "trailer"
    vehicle = await _picked_vehicle(
        callback, session, data["owner_company_id"], kind
    )
    if vehicle is None:
        return
    if kind == "trailer" and vehicle.id == data.get("truck_id"):
        await callback.answer("Це вже тягач цього рейсу.", show_alert=True)
        return

    await state.update_data(vehicle_kind=kind)
    await callback.answer()
    if callback.message is not None:
        await _use_vehicle(callback.message, state, session, vehicle)


@router.callback_query(
    StateFilter(TripForm.truck, TripForm.trailer),
    F.data.startswith(f"{TRIP_VEHICLE_MANUAL}:"),
)
async def step_vehicle_new(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """Чужа машина заводиться в довідник — з порожнім власником. Інакше рейсу
    просто нема на що посилатись."""
    kind = "truck" if await state.get_state() == TripForm.truck.state else "trailer"
    await state.update_data(vehicle_kind=kind, v_type_id=None)
    await callback.answer()
    if callback.message is not None:
        await _ask_vehicle_type(callback.message, state, session)


@router.callback_query(TripForm.v_type, F.data.startswith(f"{TRIP_TTYPE_PREFIX}:"))
async def step_vehicle_type(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    raw = (callback.data or "").rsplit(":", 1)[-1]
    vehicle_type = (
        await repository.get_vehicle_type(session, int(raw)) if raw.isdigit() else None
    )
    if vehicle_type is None:
        await callback.answer("Невідомий вид", show_alert=True)
        return
    await state.update_data(v_type_id=vehicle_type.id)
    await callback.answer()
    if callback.message is not None:
        await _ask_vehicle_mark(callback.message, state, session)


@router.callback_query(TripForm.v_mark, F.data == TRIP_MARK_NEW)
async def step_vehicle_mark_new(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TripForm.v_mark_name)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Марка й модель (наприклад «Volvo FH16»):",
            reply_markup=trip_step_keyboard(),
        )


@router.callback_query(TripForm.v_mark, F.data.startswith(f"{TRIP_MARK_PREFIX}:"))
async def step_vehicle_mark(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    raw = (callback.data or "").rsplit(":", 1)[-1]
    mark = (
        await repository.get_vehicle_mark(session, int(raw)) if raw.isdigit() else None
    )
    if mark is None:
        await callback.answer("Невідома марка", show_alert=True)
        return
    await state.update_data(v_mark_id=mark.id)
    await callback.answer()
    if callback.message is not None:
        await _ask_vehicle_plate(callback.message, state, session)


@router.message(TripForm.v_mark_name, F.text)
async def step_vehicle_mark_name(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    value = (message.text or "").strip()
    if error := _short_text(value):
        await message.answer(error, reply_markup=trip_step_keyboard())
        return
    # Назва унікальна, тож наявну беремо як є, а не падаємо помилкою БД.
    mark = await repository.get_vehicle_mark_by_name(session, value)
    if mark is None:
        mark = await repository.create_vehicle_mark(session, name=value)
    await state.update_data(v_mark_id=mark.id)
    await _ask_vehicle_plate(message, state, session)


def _plate(value: str) -> tuple[str, str | None]:
    """(нормалізований номер, помилка). Номери зводимо до верхнього регістру,
    щоб «аа1111аа» і «AA1111AA» не рахувались різними."""
    normalized = value.strip().upper()
    if not MIN_LICENSE_PLATE <= len(normalized) <= MAX_LICENSE_PLATE:
        return normalized, (
            f"Номер має бути від {MIN_LICENSE_PLATE} до {MAX_LICENSE_PLATE} символів."
        )
    return normalized, None


async def _vehicle_by_plate_or_new(
    session: AsyncSession, state: FSMContext, plate: str
) -> tuple[Vehicle | None, str | None]:
    """(машина, помилка). Номер — це і є ідентичність машини, тож наявну за
    ним знаходимо, а не заводимо другу з тим самим номером."""
    data = await state.get_data()
    kind = data.get("vehicle_kind", "truck")

    existing = await repository.get_vehicle_by_plate(session, plate)
    if existing is not None:
        if existing.is_tractor != (kind == "truck"):
            return None, (
                f"Машина з номером {plate} уже є в довіднику, і це "
                f"{'причіп' if kind == 'truck' else 'тягач'}."
            )
        return existing, None

    if data.get("v_type_id") is None or data.get("v_mark_id") is None:
        # Стан міг лишитись від попереднього кроку — краще сказати про це,
        # ніж упасти на NOT NULL уже в базі.
        return None, "Не зрозуміло, яку машину заводимо. Почніть крок заново."

    return (
        await repository.create_vehicle(
            session,
            type_id=data["v_type_id"],
            mark_id=data["v_mark_id"],
            license_plate=plate,
            # Порожній власник — це рівно те, чим машина і є: чужа.
            owner_company_id=None,
        ),
        None,
    )


@router.message(TripForm.v_plate, F.text)
async def step_vehicle_plate(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    plate, error = _plate(message.text or "")
    if error:
        await message.answer(error, reply_markup=trip_step_keyboard())
        return

    data = await state.get_data()
    if data.get("vehicle_kind") == "trailer":
        truck = await repository.get_vehicle(session, data.get("truck_id", 0))
        if truck is not None and truck.license_plate == plate:
            await message.answer(
                "Номери тягача й причепа не можуть збігатися. Введіть інший.",
                reply_markup=trip_step_keyboard(),
            )
            return

    vehicle, error = await _vehicle_by_plate_or_new(session, state, plate)
    if error:
        await message.answer(error, reply_markup=trip_step_keyboard())
        return
    await _use_vehicle(message, state, session, vehicle)


@router.callback_query(TripForm.grain, F.data.startswith(f"{TRIP_CHOICE_PREFIX}:"))
async def step_grain_pick(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    value = _choice(callback.data, "grain")
    if value is None:
        await callback.answer("Невідоме значення", show_alert=True)
        return
    await state.update_data(grain_type=value)
    await callback.answer()
    if callback.message is not None:
        await _advance(callback.message, state, session, _ask_driver)


@router.message(TripForm.grain, F.text)
async def step_grain(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    """Кнопки — підказка, а не обмеження: культур більше, ніж шість, і сорт
    або клас усе одно дописують руками."""
    value = (message.text or "").strip()
    if error := _short_text(value):
        await message.answer(
            error, reply_markup=trip_choice_keyboard("grain", back=True)
        )
        return
    await state.update_data(grain_type=value)
    await _advance(message, state, session, _ask_driver)


@router.callback_query(TripForm.driver, F.data == TRIP_DRIVER_MANUAL)
async def step_driver_manual(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    await state.update_data(driver_id=None)
    await callback.answer()
    if callback.message is not None:
        await _ask_driver_name(callback.message, state, session)


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
    if employee is None or employee.company_id != data["owner_company_id"]:
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
async def step_driver_name(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    value = (message.text or "").strip()
    if error := _short_text(value):
        await message.answer(error, reply_markup=trip_step_keyboard())
        return
    await state.update_data(driver_fullname=value)
    await _ask_driver_phone(message, state, session)


@router.message(TripForm.driver_phone, F.text)
async def step_driver_phone(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    value = (message.text or "").strip()
    if not MIN_PHONE <= len(value) <= MAX_PHONE:
        await message.answer(
            f"Номер має бути від {MIN_PHONE} до {MAX_PHONE} символів.",
            reply_markup=trip_step_keyboard(),
        )
        return

    await state.update_data(driver_phone_number=value)
    await _show_summary(message, state, session)


async def _show_summary(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await state.set_state(TripForm.confirm)
    # Прапорець спрацював і згорів: наступний крок, відкритий уже не з
    # підсумку, має вести анкетою далі.
    await state.update_data(return_to_summary=False)
    data = await state.get_data()

    exporter = await repository.get_company(session, data["exporter_company_id"])
    # Менеджер і машини — з бази, а не з даних форми: у стані лежать самі id,
    # і саме вони підуть у рейс.
    manager = await repository.get_employee(session, data["created_by"])
    truck = await repository.get_vehicle(session, data["truck_id"])
    trailer = await repository.get_vehicle(session, data["trailer_id"])
    await message.answer(
        format_trip_summary(
            data,
            client=data["client_company_name"],
            exporter=company_label(exporter),
            manager=manager,
            truck=truck,
            trailer=trailer,
        ),
        reply_markup=trip_confirm_keyboard(),
    )


#: Колонки, які беруться з форми. Перелік явний, щоб службові ключі стану
#: (наприклад, назви компаній для підсумку) не потрапили в модель.
TRIP_COLUMNS = (
    "ttn_num", "arrival_date", "owner_company_id", "client_company_id",
    "client_company_name", "exporter_company_id", "created_by",
    "truck_id", "trailer_id",
    "grain_type", "driver_id", "driver_fullname", "driver_phone_number",
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

    company = trip.owner_company
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
    if kind == "status":
        await state.set_state(TripEdit.status)
        await callback.message.answer(
            "Новий статус:", reply_markup=trip_status_keyboard(trip.status)
        )
        return
    if kind == "vehicle":
        await state.set_state(
            TripEdit.truck if key == "truck" else TripEdit.trailer
        )
        vehicles = await repository.list_vehicles_for_pick(
            session, key, trip.owner_company_id
        )
        await callback.message.answer(
            f"Новий {'тягач' if key == 'truck' else 'причіп'}:",
            reply_markup=trip_vehicle_keyboard(key, vehicles),
        )
        return
    if kind == "driver":
        await state.set_state(TripEdit.driver)
        candidates = await _driver_candidates(
            session, trip.owner_company_id, exclude_id=trip.created_by
        )
        await callback.message.answer(
            "Кому передаємо рейс?" if candidates
            else "У компанії немає інших зареєстрованих співробітників.",
            reply_markup=trip_drivers_keyboard(candidates),
        )
        return

    await state.set_state(TripEdit.value)
    # Клавіатура за полем: час відмічають «зараз», культуру й тип причепа
    # частіше обирають, ніж набирають. Ручний ввід лишається в усіх трьох.
    if kind == "datetime":
        keyboard = trip_datetime_keyboard()
    elif key in TRIP_CHOICES:
        keyboard = trip_choice_keyboard(key)
    else:
        keyboard = cancel_keyboard()
    await callback.message.answer(
        f"<b>{escape(title)}</b>\n{PROMPTS[kind]}", reply_markup=keyboard
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
    return None, "Невідоме поле."


async def _refresh_chat(publisher: Publisher, trip: Trip) -> None:
    """Перемалювати рейс у робочому чаті.

    Без цього в чаті назавжди висить перша версія: оператор вносить маси,
    диспетчер рухає статус, а компанія бачить рейс таким, яким він був у
    момент створення. Best-effort — збій у Telegram не скасовує правку.
    """
    if trip.chat_id is None or trip.chat_message_id is None:
        return
    await publisher.edit(trip.chat_id, trip.chat_message_id, format_trip(trip))


async def _notify_driver(publisher: Publisher, trip: Trip, field: str) -> None:
    """Сказати водію, що в його рейсі змінилось."""
    if trip.driver is None:
        return
    title = TRIP_FIELDS[field][1]
    await publisher.send(
        trip.driver.tg_id,
        f"✏️ <b>Рейс #{trip.id}</b> — змінено «{escape(title)}»\n\n{format_trip(trip)}",
    )


async def _apply(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    access: Access,
    publisher: Publisher,
    trip: Trip,
    *,
    field: str,
    unassigned_tg: int | None = None,
    **fields,
) -> None:
    """Зберегти правку й розповісти про неї тим, кого вона стосується.

    `unassigned_tg` — Telegram id водія, з якого рейс щойно зняли: сказати
    йому має саме той, хто знає, що водій змінився, бо після оновлення в
    рейсі його вже немає.
    """
    await state.clear()
    updated = await repository.update_trip(
        session, trip, editor_id=_actor_id(access), **fields
    )

    await _refresh_chat(publisher, updated)
    if unassigned_tg is not None:
        await publisher.send(
            unassigned_tg, f"🚫 Рейс #{updated.id} більше не за вами."
        )
    if field in NOTIFY_DRIVER_FIELDS:
        await _notify_driver(publisher, updated, field)

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
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    access: Access,
    publisher: Publisher,
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

    values = {column: value}
    if kind == "mass":
        values, error = _masses(trip, column, value)
        if error:
            await message.answer(error, reply_markup=cancel_keyboard())
            return

    await _apply(
        message, state, session, access, publisher, trip, field=key, **values
    )


@router.callback_query(TripEdit.value, F.data.startswith(f"{TRIP_CHOICE_PREFIX}:"))
async def edit_choice(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    access: Access,
    publisher: Publisher,
) -> None:
    """Культура або тип причепа, обрані кнопкою. Ключ підказки збігається з
    ключем поля, тож окремої відповідності тримати не треба."""
    data = await state.get_data()
    key = data.get("field", "")
    value = _choice(callback.data, key)
    if value is None:
        await callback.answer("Невідоме значення", show_alert=True)
        return
    if not access.may_edit_field(CATEGORY_TRIPS, key):
        await callback.answer(DENIED, show_alert=True)
        return

    await callback.answer()
    if callback.message is None:
        return
    trip = await _editable_trip(callback.message, state, session, access)
    if trip is None:
        return
    column = TRIP_FIELDS[key][0]
    await _apply(
        callback.message, state, session, access, publisher, trip,
        field=key, **{column: value},
    )


@router.callback_query(TripEdit.value, F.data.in_({TRIP_NOW, TRIP_CLEAR}))
async def edit_datetime_button(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    access: Access,
    publisher: Publisher,
) -> None:
    """Заїзд і виїзд однією кнопкою.

    Місцевий час, а не UTC: так задано в моделі для цих двох колонок — їх
    читає людина на вагах, і зсув зробив би час незрозумілим.
    """
    data = await state.get_data()
    key = data.get("field", "")
    field = TRIP_FIELDS.get(key)
    if field is None or field[2] != "datetime":
        await callback.answer("Не зрозуміло, що саме редагуємо", show_alert=True)
        return
    if not access.may_edit_field(CATEGORY_TRIPS, key):
        await callback.answer(DENIED, show_alert=True)
        return

    await callback.answer()
    if callback.message is None:
        return
    trip = await _editable_trip(callback.message, state, session, access)
    if trip is None:
        return

    value = None if callback.data == TRIP_CLEAR else datetime.now().strftime(
        DATETIME_FORMAT
    )
    await _apply(
        callback.message, state, session, access, publisher, trip,
        field=key, **{field[0]: value},
    )


@router.callback_query(TripEdit.arrival_date, F.data.startswith(f"{TRIP_DATE_PREFIX}:"))
async def edit_arrival_date(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    access: Access,
    publisher: Publisher,
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
        callback.message, state, session, access, publisher, trip,
        field="date", arrival_date=value,
    )


@router.callback_query(TripEdit.exporter, F.data.startswith(f"{TRIP_EXPORTER_PREFIX}:"))
async def edit_exporter(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    access: Access,
    publisher: Publisher,
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
        callback.message, state, session, access, publisher, trip,
        field="exp", exporter_company_id=company.id,
    )


@router.callback_query(TripEdit.status, F.data.startswith(f"{TRIP_STATUS_PREFIX}:"))
async def edit_status(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    access: Access,
    publisher: Publisher,
) -> None:
    """Статус — лише з переліку. У callback_data номер, тож підмінити його на
    довільний рядок неможливо: те, чого немає в TRIP_STATUSES, не збережеться."""
    raw = (callback.data or "").rsplit(":", 1)[-1]
    if not raw.isdigit() or int(raw) >= len(TRIP_STATUSES):
        await callback.answer("Невідомий статус", show_alert=True)
        return
    if not access.may_edit_field(CATEGORY_TRIPS, "status"):
        await callback.answer(DENIED, show_alert=True)
        return
    await callback.answer()
    if callback.message is None:
        return
    trip = await _editable_trip(callback.message, state, session, access)
    if trip is None:
        return
    await _apply(
        callback.message, state, session, access, publisher, trip,
        field="status", status=TRIP_STATUSES[int(raw)],
    )


# ---------------------------------------------------------------------------
# Зміна транспорту
# ---------------------------------------------------------------------------
#
# Дзеркало кроків анкети. Машину міняємо цілком: у рейсі лежить саме
# посилання, тож «поміняти лише номер» тут просто немає що означати —
# номер належить машині, а не рейсу.


def _edit_kind(state_name: str | None) -> str:
    """Що саме редагуємо — тягач чи причіп."""
    return "truck" if state_name == TripEdit.truck.state else "trailer"


async def _replace_vehicle(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    access: Access,
    publisher: Publisher,
    trip: Trip,
    kind: str,
    vehicle: Vehicle,
) -> None:
    column = "truck_id" if kind == "truck" else "trailer_id"
    await _apply(
        message, state, session, access, publisher, trip,
        field=kind, **{column: vehicle.id},
    )


def _clashes(kind: str, trip: Trip, vehicle: Vehicle) -> bool:
    """Тягач і причіп не можуть бути однією машиною."""
    other = trip.trailer_id if kind == "truck" else trip.truck_id
    return vehicle.id == other


@router.callback_query(
    StateFilter(TripEdit.truck, TripEdit.trailer),
    F.data.startswith(f"{TRIP_VEHICLE_PREFIX}:"),
)
async def edit_vehicle_pick(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    access: Access,
    publisher: Publisher,
) -> None:
    kind = _edit_kind(await state.get_state())
    await callback.answer()
    if callback.message is None:
        return
    trip = await _editable_trip(callback.message, state, session, access)
    if trip is None:
        return

    vehicle = await _picked_vehicle(
        callback, session, trip.owner_company_id, kind
    )
    if vehicle is None:
        await state.clear()
        await callback.message.answer("Невідомий транспорт.")
        return
    if _clashes(kind, trip, vehicle):
        await state.clear()
        await callback.message.answer(
            "Тягач і причіп не можуть бути однією машиною."
        )
        return

    await _replace_vehicle(
        callback.message, state, session, access, publisher, trip, kind, vehicle
    )


@router.callback_query(
    StateFilter(TripEdit.truck, TripEdit.trailer),
    F.data.startswith(f"{TRIP_VEHICLE_MANUAL}:"),
)
async def edit_vehicle_new(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    kind = _edit_kind(await state.get_state())
    await state.update_data(vehicle_kind=kind, v_type_id=None)
    await callback.answer()
    if callback.message is None:
        return

    types = await repository.list_vehicle_types(session, tractors=kind == "truck")
    if len(types) == 1:
        await state.update_data(v_type_id=types[0].id)
        await _edit_ask_mark(callback.message, state, session)
        return
    await state.set_state(TripEdit.v_type)
    await callback.message.answer(
        "Вид:", reply_markup=trip_vehicle_type_keyboard(types)
    )


async def _edit_ask_mark(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    await state.set_state(TripEdit.v_mark)
    marks = await repository.list_vehicle_marks(session)
    await message.answer(
        "Марка й модель:" if marks else "Довідник марок порожній — додайте першу.",
        reply_markup=trip_mark_keyboard(marks),
    )


@router.callback_query(TripEdit.v_type, F.data.startswith(f"{TRIP_TTYPE_PREFIX}:"))
async def edit_vehicle_type(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    raw = (callback.data or "").rsplit(":", 1)[-1]
    vehicle_type = (
        await repository.get_vehicle_type(session, int(raw)) if raw.isdigit() else None
    )
    if vehicle_type is None:
        await callback.answer("Невідомий вид", show_alert=True)
        return
    await state.update_data(v_type_id=vehicle_type.id)
    await callback.answer()
    if callback.message is not None:
        await _edit_ask_mark(callback.message, state, session)


@router.callback_query(TripEdit.v_mark, F.data == TRIP_MARK_NEW)
async def edit_vehicle_mark_new(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TripEdit.v_mark_name)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Марка й модель:", reply_markup=cancel_keyboard()
        )


async def _edit_ask_plate(message: Message, state: FSMContext) -> None:
    await state.set_state(TripEdit.v_plate)
    await message.answer("Державний номер:", reply_markup=cancel_keyboard())


@router.callback_query(TripEdit.v_mark, F.data.startswith(f"{TRIP_MARK_PREFIX}:"))
async def edit_vehicle_mark(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    raw = (callback.data or "").rsplit(":", 1)[-1]
    mark = (
        await repository.get_vehicle_mark(session, int(raw)) if raw.isdigit() else None
    )
    if mark is None:
        await callback.answer("Невідома марка", show_alert=True)
        return
    await state.update_data(v_mark_id=mark.id)
    await callback.answer()
    if callback.message is not None:
        await _edit_ask_plate(callback.message, state)


@router.message(TripEdit.v_mark_name, F.text)
async def edit_vehicle_mark_name(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    value = (message.text or "").strip()
    if error := _short_text(value):
        await message.answer(error, reply_markup=cancel_keyboard())
        return
    mark = await repository.get_vehicle_mark_by_name(session, value)
    if mark is None:
        mark = await repository.create_vehicle_mark(session, name=value)
    await state.update_data(v_mark_id=mark.id)
    await _edit_ask_plate(message, state)


@router.message(TripEdit.v_plate, F.text)
async def edit_vehicle_plate(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    access: Access,
    publisher: Publisher,
) -> None:
    plate, error = _plate(message.text or "")
    if error:
        await message.answer(error, reply_markup=cancel_keyboard())
        return
    trip = await _editable_trip(message, state, session, access)
    if trip is None:
        return

    kind = (await state.get_data()).get("vehicle_kind", "truck")
    vehicle, error = await _vehicle_by_plate_or_new(session, state, plate)
    if error:
        await message.answer(error, reply_markup=cancel_keyboard())
        return
    if _clashes(kind, trip, vehicle):
        await message.answer(
            "Тягач і причіп не можуть бути однією машиною.",
            reply_markup=cancel_keyboard(),
        )
        return

    await _replace_vehicle(
        message, state, session, access, publisher, trip, kind, vehicle
    )


# ---------------------------------------------------------------------------
# Зміна водія
# ---------------------------------------------------------------------------


@router.callback_query(TripEdit.driver, F.data.startswith(f"{TRIP_DRIVER_PREFIX}:"))
async def edit_driver_pick(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    access: Access,
    publisher: Publisher,
) -> None:
    """Призначити рейс іншому співробітнику.

    Разом із ПІБ і телефоном міняється driver_id — інакше рейс лишався б за
    попередньою людиною: вона й далі бачила б його в «своїх» і отримувала
    сповіщення, а новий водій не дізнався б нічого.
    """
    raw_id = (callback.data or "").rsplit(":", 1)[-1]
    employee = (
        await repository.get_employee(session, int(raw_id)) if raw_id.isdigit() else None
    )
    await callback.answer()
    if callback.message is None:
        return
    trip = await _editable_trip(callback.message, state, session, access)
    if trip is None:
        return
    # Компанію звіряємо заново: id приходить у callback_data, і без перевірки
    # водієм можна було б призначити людину з чужої компанії.
    if employee is None or employee.company_id != trip.owner_company_id:
        await state.clear()
        await callback.message.answer("Невідомий співробітник.")
        return

    await _apply(
        callback.message, state, session, access, publisher, trip,
        field="driver",
        unassigned_tg=_leaving_driver(trip, employee.id),
        driver_id=employee.id,
        driver_fullname=employee.fullname,
        driver_phone_number=employee.phone_number,
    )


@router.callback_query(TripEdit.driver, F.data == TRIP_DRIVER_MANUAL)
async def edit_driver_manual(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(TripEdit.driver_name)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer("ПІБ водія:", reply_markup=cancel_keyboard())


@router.message(TripEdit.driver_name, F.text)
async def edit_driver_name(
    message: Message, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    value = (message.text or "").strip()
    if error := _short_text(value):
        await message.answer(error, reply_markup=cancel_keyboard())
        return
    if await _editable_trip(message, state, session, access) is None:
        return
    await state.update_data(driver_fullname=value)
    await state.set_state(TripEdit.driver_phone)
    await message.answer("Телефон водія:", reply_markup=cancel_keyboard())


@router.message(TripEdit.driver_phone, F.text)
async def edit_driver_phone(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    access: Access,
    publisher: Publisher,
) -> None:
    value = (message.text or "").strip()
    if not MIN_PHONE <= len(value) <= MAX_PHONE:
        await message.answer(
            f"Номер має бути від {MIN_PHONE} до {MAX_PHONE} символів.",
            reply_markup=cancel_keyboard(),
        )
        return
    trip = await _editable_trip(message, state, session, access)
    if trip is None:
        return

    data = await state.get_data()
    # Сторонній перевізник: driver_id порожній, а ПІБ із телефоном лишаються —
    # рейс документ, і водій у ньому має бути названий.
    await _apply(
        message, state, session, access, publisher, trip,
        field="driver",
        unassigned_tg=_leaving_driver(trip, None),
        driver_id=None,
        driver_fullname=data.get("driver_fullname", ""),
        driver_phone_number=value,
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
@router.message(TripForm.client_name)
@router.message(TripForm.v_mark_name)
@router.message(TripForm.v_plate)
@router.message(TripForm.grain)
@router.message(TripForm.driver_name)
@router.message(TripForm.driver_phone)
@router.message(TripEdit.value)
@router.message(TripEdit.driver_name)
@router.message(TripEdit.driver_phone)
@router.message(TripEdit.v_mark_name)
@router.message(TripEdit.v_plate)
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
