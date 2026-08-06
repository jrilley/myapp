import calendar
from collections.abc import Sequence

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Модуль, а не значення: SHOW_APPLICATIONS читається під час виклику, тож
# прапорець можна перемкнути в рантаймі — і тести на заявки лишаються
# робочими, поки код заявок живий.
from app.bot import constants
from app.bot.constants import CATEGORIES
from app.models import Application

CATEGORY_PREFIX = "cat"
CONFIRM_YES = "confirm:yes"
CONFIRM_NO = "confirm:no"

MENU_NEW = "menu:new"
MENU_MY = "menu:my"
MENU_HELP = "menu:help"
MENU_BACK = "menu:back"
MENU_ALL = "menu:all"
MENU_STATS = "menu:stats"
MENU_COMPANIES = "menu:companies"
MENU_EMPLOYEES = "menu:employees"
MENU_POSITIONS = "menu:positions"

EMP_VIEW_PREFIX = "emp"
EMP_EDIT_PREFIX = "empedit"
EMP_SET_PREFIX = "empset"
POSITION_ADD = "position:add"
POSITION_CARD_PREFIX = "position:card"

MENU_VEHICLE_ADD = "menu:vehicle"
#: Для адміністратора компанії — власна компанія мається на увазі.
MENU_MY_VEHICLES = "menu:myveh"
MENU_MY_EMPLOYEES = "menu:myemp"

MENU_TRIP_NEW = "menu:tripnew"
MENU_TRIPS = "menu:trips"

# Префікси рейсу. Усі починаються з «trip:», тому кожен розбір спирається на
# двокрапку в кінці — «trip:cal:» і «trip:card» інакше перетнулися б.
TRIP_CAL_PREFIX = "trip:cal"
TRIP_DATE_PREFIX = "trip:date"
TRIP_EXPORTER_PREFIX = "trip:exp"
TRIP_CONFIRM = "trip:confirm"
TRIP_SHOW_PREFIX = "trip:show"
TRIP_EDIT_PREFIX = "trip:edit"
TRIP_FIELD_PREFIX = "trip:field"
TRIP_DELETE_PREFIX = "trip:drop"
#: Вибір водія: trip:drv:<id співробітника> або trip:drv:manual.
TRIP_DRIVER_PREFIX = "trip:drv"
TRIP_DRIVER_MANUAL = "trip:drv:manual"

COMPANY_CARD_PREFIX = "comp"
COMPANY_EDIT_PREFIX = "compedit"
COMPANY_CHAT_SKIP = "company:chatskip"
COMPANY_VEHICLES_PREFIX = "compveh"
COMPANY_EMPLOYEES_PREFIX = "compemp"
VEHICLE_LIST_PREFIX = "vlist"
VEHICLE_CARD_PREFIX = "vcard"
VEHICLE_EDIT_PREFIX = "vedit"
VEHICLE_TYPE_PREFIX = "veh:type"
VEHICLE_COMPANY_PREFIX = "veh:company"
VEHICLE_CONFIRM = "veh:confirm"

#: Тип транспорту → підпис. Ключі збігаються з repository.VEHICLE_MODELS.
VEHICLE_TITLES = {"truck": "Тягач", "trailer": "Причіп"}


def vehicle_type_keyboard() -> InlineKeyboardMarkup:
    """Кнопка в меню одна, а таблиці дві — тип питаємо першим кроком."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🚛 Тягач", callback_data=f"{VEHICLE_TYPE_PREFIX}:truck")
    builder.button(text="🚚 Причіп", callback_data=f"{VEHICLE_TYPE_PREFIX}:trailer")
    builder.button(text="✖️ Скасувати", callback_data=FORM_CANCEL)
    builder.adjust(2, 1)
    return builder.as_markup()


def vehicle_company_keyboard(companies) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for company in companies:
        builder.button(
            text=f"{company.name} - {company.tax_id}",
            callback_data=f"{VEHICLE_COMPANY_PREFIX}:{company.id}",
        )
    builder.button(text="✖️ Скасувати", callback_data=FORM_CANCEL)
    builder.adjust(1)
    return builder.as_markup()


def vehicle_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Зберегти", callback_data=VEHICLE_CONFIRM)
    builder.button(text="✖️ Скасувати", callback_data=FORM_CANCEL)
    builder.adjust(2)
    return builder.as_markup()


PAGE_PREFIX = "page"
#: Натискання на «2 / 5» нічого не робить, але Telegram чекає відповіді,
#: інакше на кнопці лишається годинник.
NOOP = "noop"

# Розміри сторінок різні: заявки багатослівні, довідники — ні.
PAGE_APPLICATIONS = 5
PAGE_EMPLOYEES = 8
PAGE_REFERENCE = 10
PAGE_TRIPS = 6


def _add_pagination(
    builder: InlineKeyboardBuilder, kind: str, *, offset: int, limit: int, total: int
) -> None:
    """Додає рядок «‹ Назад · 2/5 · Далі ›», якщо сторінка не одна."""
    if total <= limit:
        return

    pages = (total + limit - 1) // limit
    current = offset // limit + 1

    row: list[InlineKeyboardButton] = []
    if offset > 0:
        row.append(
            InlineKeyboardButton(
                text="‹ Назад",
                callback_data=f"{PAGE_PREFIX}:{kind}:{max(0, offset - limit)}",
            )
        )
    row.append(InlineKeyboardButton(text=f"{current} / {pages}", callback_data=NOOP))
    if offset + limit < total:
        row.append(
            InlineKeyboardButton(
                text="Далі ›",
                callback_data=f"{PAGE_PREFIX}:{kind}:{offset + limit}",
            )
        )
    builder.row(*row)

FORM_CANCEL = "form:cancel"
DELETE_PREFIX = "del"

REG_START = "reg:start"
REG_COMPANY_PREFIX = "reg:company"
REG_CONFIRM = "reg:confirm"
REG_PHONE2_YES = "reg:phone2:yes"
REG_PHONE2_NO = "reg:phone2:no"

#: Текст reply-кнопки скасування. Reply-клавіатура не має callback_data,
#: тому розпізнаємо її за текстом.
CANCEL_TEXT = "✖️ Скасувати"


def share_phone_keyboard() -> ReplyKeyboardMarkup:
    """Reply-клавіатура: інакше Telegram не віддасть номер.

    request_contact працює лише в приватному чаті й повертає номер САМОГО
    користувача. Поруч — скасування, бо інлайн-кнопку до цього повідомлення
    прикріпити не можна: розмітка або inline, або reply.
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Поділитися номером", request_contact=True)],
            [KeyboardButton(text=CANCEL_TEXT)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="або введіть номер вручну",
    )


def phone2_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Так, додати", callback_data=REG_PHONE2_YES)
    builder.button(text="Ні, продовжити", callback_data=REG_PHONE2_NO)
    builder.adjust(1)
    return builder.as_markup()

COMPANY_ADD = "company:add"


def main_menu_keyboard(
    *, is_registered: bool = False, is_admin: bool = False, is_main_admin: bool = False
) -> InlineKeyboardMarkup:
    """Меню під конкретного користувача.

    Незареєстрованому доступна лише реєстрація — заявки без неї не подати.
    Приховування кнопки не є захистом: callback_data можна переслати або
    підробити, тому кожен обмежений хендлер перевіряє права самостійно.
    """
    builder = InlineKeyboardBuilder()

    if not is_registered:
        builder.button(text="🔑 Зареєструватися", callback_data=REG_START)
        builder.button(text="ℹ️ Довідка", callback_data=MENU_HELP)
        builder.adjust(1)
        return builder.as_markup()

    builder.button(text="🚛 Новий рейс", callback_data=MENU_TRIP_NEW)
    builder.button(text="🧾 Рейси", callback_data=MENU_TRIPS)
    if constants.SHOW_APPLICATIONS:
        builder.button(text="📝 Нова заявка", callback_data=MENU_NEW)
        builder.button(text="📋 Мої заявки", callback_data=MENU_MY)
    if is_admin:
        if constants.SHOW_APPLICATIONS:
            builder.button(text="🗂 Усі заявки", callback_data=MENU_ALL)
            builder.button(text="📊 Статистика", callback_data=MENU_STATS)
        builder.button(text="🚛 Додати автомобіль", callback_data=MENU_VEHICLE_ADD)
    if is_admin and not is_main_admin:
        # Адміністратор компанії бачить лише свою компанію, тож заходить
        # у транспорт і працівників напряму, без кроку вибору компанії.
        builder.button(text="🚚 Транспорт", callback_data=MENU_MY_VEHICLES)
        builder.button(text="👥 Працівники", callback_data=MENU_MY_EMPLOYEES)
    if is_main_admin:
        # Головний адмін заходить до транспорту й працівників через компанію.
        builder.button(text="🏢 Компанії", callback_data=MENU_COMPANIES)
        builder.button(text="💼 Посади", callback_data=MENU_POSITIONS)
    builder.button(text="ℹ️ Довідка", callback_data=MENU_HELP)
    builder.adjust(1)
    return builder.as_markup()


def registration_prompt_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔑 Зареєструватися", callback_data=REG_START)
    return builder.as_markup()


def choices_keyboard(prefix: str, items) -> InlineKeyboardMarkup:
    """Кнопки «id → назва» для довідників (компанії, посади) + скасування."""
    builder = InlineKeyboardBuilder()
    for item_id, title in items:
        builder.button(text=title, callback_data=f"{prefix}:{item_id}")
    builder.button(text="✖️ Скасувати", callback_data=FORM_CANCEL)
    builder.adjust(1)
    return builder.as_markup()


def registration_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Підтвердити", callback_data=REG_CONFIRM)
    builder.button(text="✖️ Скасувати", callback_data=FORM_CANCEL)
    builder.adjust(2)
    return builder.as_markup()


def companies_keyboard(
    *, offset: int = 0, total: int | None = None
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Додати компанію", callback_data=COMPANY_ADD)
    builder.adjust(1)
    if total is not None:
        _add_pagination(
            builder, "comp", offset=offset, limit=PAGE_REFERENCE, total=total
        )
    builder.row(InlineKeyboardButton(text="⬅️ Меню", callback_data=MENU_BACK))
    return builder.as_markup()


def employees_keyboard(
    employees,
    *,
    company_id: int,
    offset: int = 0,
    total: int | None = None,
    back: str = MENU_BACK,
) -> InlineKeyboardMarkup:
    """Список співробітників компанії: кожен — кнопка, що відкриває картку.

    Підпис — посада й ПІБ, як просив замовник.
    """
    builder = InlineKeyboardBuilder()
    for employee in employees:
        builder.button(
            text=f"{employee.position.position}, {employee.fullname}",
            callback_data=f"{EMP_VIEW_PREFIX}:{employee.id}",
        )
    builder.adjust(1)
    if total is not None:
        _add_pagination(
            builder, f"cemp:{company_id}", offset=offset, limit=PAGE_EMPLOYEES,
            total=total,
        )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=back))
    return builder.as_markup()


def employee_card_keyboard(
    employee_id: int, back: str = MENU_BACK
) -> InlineKeyboardMarkup:
    """Що саме редагуємо — вирішує кнопка; редактор один на поле."""
    builder = InlineKeyboardBuilder()
    for field, title in (
        ("name", "✏️ ПІБ"),
        ("phone", "✏️ Телефон"),
        ("phone2", "✏️ Дод. номер"),
        ("company", "🏢 Компанія"),
        ("position", "💼 Посада"),
        ("role", "🔑 Роль"),
    ):
        builder.button(
            text=title, callback_data=f"{EMP_EDIT_PREFIX}:{field}:{employee_id}"
        )
    builder.button(text="⬅️ До списку", callback_data=back)
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def employee_choice_keyboard(field: str, employee_id: int, items) -> InlineKeyboardMarkup:
    """Варіанти для поля-довідника; вибір застосовується одразу."""
    builder = InlineKeyboardBuilder()
    for item_id, title in items:
        builder.button(
            text=title,
            callback_data=f"{EMP_SET_PREFIX}:{field}:{employee_id}:{item_id}",
        )
    builder.button(
        text="⬅️ Назад", callback_data=f"{EMP_VIEW_PREFIX}:{employee_id}"
    )
    builder.adjust(1)
    return builder.as_markup()


def companies_list_keyboard(
    companies, *, offset: int = 0, total: int | None = None
) -> InlineKeyboardMarkup:
    """Список компаній: кожна — вхід у її транспорт і працівників."""
    builder = InlineKeyboardBuilder()
    for company in companies:
        builder.button(
            text=f"{company.name} - {company.tax_id}",
            callback_data=f"{COMPANY_CARD_PREFIX}:{company.id}",
        )
    builder.adjust(1)
    if total is not None:
        _add_pagination(
            builder, "comp", offset=offset, limit=PAGE_REFERENCE, total=total
        )
    builder.row(
        InlineKeyboardButton(text="➕ Додати компанію", callback_data=COMPANY_ADD)
    )
    builder.row(InlineKeyboardButton(text="⬅️ Меню", callback_data=MENU_BACK))
    return builder.as_markup()


def company_card_keyboard(company_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🚚 Транспорт",
        callback_data=f"{COMPANY_VEHICLES_PREFIX}:{company_id}",
    )
    builder.button(
        text="👥 Працівники",
        callback_data=f"{COMPANY_EMPLOYEES_PREFIX}:{company_id}",
    )
    for field, title in (
        ("name", "✏️ Назва"),
        ("tax", "✏️ Код"),
        ("address", "✏️ Адреса"),
        ("chat", "💬 Робочий чат"),
    ):
        builder.button(
            text=title, callback_data=f"{COMPANY_EDIT_PREFIX}:{field}:{company_id}"
        )
    builder.button(text="⬅️ До компаній", callback_data=MENU_COMPANIES)
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def company_chat_keyboard() -> InlineKeyboardMarkup:
    """Крок робочого чату при заведенні компанії. Чат могли ще не створити,
    тож пропуск має бути кнопкою, а не здогадкою про порожній ввід."""
    builder = InlineKeyboardBuilder()
    builder.button(text="Пропустити", callback_data=COMPANY_CHAT_SKIP)
    builder.button(text="✖️ Скасувати", callback_data=FORM_CANCEL)
    builder.adjust(1)
    return builder.as_markup()


def vehicle_kind_keyboard(company_id: int, *, back: str) -> InlineKeyboardMarkup:
    """Вибір тягачі/причепи перед списком."""
    builder = InlineKeyboardBuilder()
    for kind, title in (("truck", "🚛 Тягачі"), ("trailer", "🚚 Причепи")):
        builder.button(
            text=title,
            callback_data=f"{VEHICLE_LIST_PREFIX}:{kind}:{company_id}:0",
        )
    builder.button(text="⬅️ Назад", callback_data=back)
    builder.adjust(2, 1)
    return builder.as_markup()


def vehicle_list_keyboard(
    vehicles, kind: str, company_id: int, *, offset: int, total: int, back: str
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for vehicle in vehicles:
        builder.button(
            text=f"{vehicle.brand} - {vehicle.license_plate}",
            callback_data=f"{VEHICLE_CARD_PREFIX}:{kind}:{vehicle.id}",
        )
    builder.adjust(1)
    # Формат має збігатися з розбором у on_page: page:veh:<тип>:<компанія>:<зсув>
    _add_pagination(
        builder, f"veh:{kind}:{company_id}", offset=offset, limit=PAGE_REFERENCE,
        total=total,
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=back))
    return builder.as_markup()


def vehicle_card_keyboard(kind: str, vehicle_id: int, back: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for field, title in (
        ("brand", "✏️ Марка"),
        ("model", "✏️ Модель"),
        ("plate", "✏️ Номер"),
    ):
        builder.button(
            text=title,
            callback_data=f"{VEHICLE_EDIT_PREFIX}:{field}:{kind}:{vehicle_id}",
        )
    builder.button(text="⬅️ До списку", callback_data=back)
    builder.adjust(2, 1, 1)
    return builder.as_markup()


def positions_keyboard(
    positions=(), *, offset: int = 0, total: int | None = None
) -> InlineKeyboardMarkup:
    """Довідник посад: кожна — кнопка, що відкриває картку."""
    builder = InlineKeyboardBuilder()
    for position in positions:
        builder.button(
            text=position.position,
            callback_data=f"{POSITION_CARD_PREFIX}:{position.id}",
        )
    builder.adjust(1)
    if total is not None:
        _add_pagination(
            builder, "pos", offset=offset, limit=PAGE_REFERENCE, total=total
        )
    builder.row(
        InlineKeyboardButton(text="➕ Додати посаду", callback_data=POSITION_ADD)
    )
    builder.row(InlineKeyboardButton(text="⬅️ Меню", callback_data=MENU_BACK))
    return builder.as_markup()


def position_card_keyboard(position_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ До посад", callback_data=MENU_POSITIONS)
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    """Висить під кожним кроком анкети, щоб вихід був у одне натискання."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✖️ Скасувати", callback_data=FORM_CANCEL)
    return builder.as_markup()


def categories_keyboard() -> InlineKeyboardMarkup:
    """Категорія обирається з фіксованого списку, а не вільним текстом —
    інакше поле стає непридатним для фільтрації на сайті."""
    builder = InlineKeyboardBuilder()
    for index, title in enumerate(CATEGORIES):
        builder.button(text=title, callback_data=f"{CATEGORY_PREFIX}:{index}")
    builder.button(text="✖️ Скасувати", callback_data=FORM_CANCEL)
    builder.adjust(1)
    return builder.as_markup()


def confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Надіслати", callback_data=CONFIRM_YES)
    builder.button(text="✖️ Скасувати", callback_data=CONFIRM_NO)
    builder.adjust(2)
    return builder.as_markup()


def after_submit_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Мої заявки", callback_data=MENU_MY)
    builder.button(text="📝 Ще одна заявка", callback_data=MENU_NEW)
    builder.adjust(1)
    return builder.as_markup()


def applications_keyboard(
    applications: Sequence[Application],
    *,
    kind: str = "my",
    offset: int = 0,
    total: int | None = None,
) -> InlineKeyboardMarkup:
    """Кнопка видалення на кожну заявку — замість того, щоб набирати
    /delete з номером вручну. Використовується і для своїх заявок,
    і для адмінського списку всіх."""
    builder = InlineKeyboardBuilder()
    for application in applications:
        builder.button(
            text=f"🗑 #{application.id} · {application.category}",
            callback_data=f"{DELETE_PREFIX}:{application.id}",
        )
    builder.adjust(1)
    if total is not None:
        _add_pagination(
            builder, kind, offset=offset, limit=PAGE_APPLICATIONS, total=total
        )
    builder.row(InlineKeyboardButton(text="⬅️ Меню", callback_data=MENU_BACK))
    return builder.as_markup()


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Меню", callback_data=MENU_BACK)
    return builder.as_markup()


# ---------------------------------------------------------------------------
# Рейси
# ---------------------------------------------------------------------------

MONTHS = (
    "Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
    "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень",
)
WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд")


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """Сусідній місяць. Рахуємо в «місяцях від нуля», щоб грудень→січень
    переносив рік сам, без окремої гілки."""
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def calendar_keyboard(year: int, month: int) -> InlineKeyboardMarkup:
    """Календар на місяць: дату обирають натисканням, а не набирають.

    Порожні клітинки — теж кнопки: Telegram не дозволяє пропуски в рядку,
    тому вони NOOP із крапкою замість числа.
    """
    builder = InlineKeyboardBuilder()

    prev_year, prev_month = shift_month(year, month, -1)
    next_year, next_month = shift_month(year, month, 1)
    builder.row(
        InlineKeyboardButton(
            text="‹", callback_data=f"{TRIP_CAL_PREFIX}:{prev_year}:{prev_month}"
        ),
        InlineKeyboardButton(text=f"{MONTHS[month - 1]} {year}", callback_data=NOOP),
        InlineKeyboardButton(
            text="›", callback_data=f"{TRIP_CAL_PREFIX}:{next_year}:{next_month}"
        ),
    )
    builder.row(*(InlineKeyboardButton(text=d, callback_data=NOOP) for d in WEEKDAYS))

    # monthdayscalendar тижнями по 7, нулі — дні сусідніх місяців.
    for week in calendar.Calendar().monthdayscalendar(year, month):
        builder.row(
            *(
                InlineKeyboardButton(text="·", callback_data=NOOP)
                if day == 0
                else InlineKeyboardButton(
                    text=str(day),
                    callback_data=f"{TRIP_DATE_PREFIX}:{year:04d}-{month:02d}-{day:02d}",
                )
                for day in week
            )
        )

    builder.row(
        InlineKeyboardButton(text="✖️ Скасувати", callback_data=FORM_CANCEL)
    )
    return builder.as_markup()


def trip_exporter_keyboard(companies) -> InlineKeyboardMarkup:
    """Компанія-експортер: підпис — «назва - код», як і при виборі компанії
    для транспорту."""
    builder = InlineKeyboardBuilder()
    for company in companies:
        builder.button(
            text=f"{company.name} - {company.tax_id}",
            callback_data=f"{TRIP_EXPORTER_PREFIX}:{company.id}",
        )
    builder.button(text="✖️ Скасувати", callback_data=FORM_CANCEL)
    builder.adjust(1)
    return builder.as_markup()


def trip_drivers_keyboard(employees) -> InlineKeyboardMarkup:
    """Водії — зі складу компанії. Ручний ввід лишається окремою кнопкою:
    рейс може виконувати найманий перевізник, якого в employees немає."""
    builder = InlineKeyboardBuilder()
    for employee in employees:
        builder.button(
            text=f"{employee.position.position}, {employee.fullname}",
            callback_data=f"{TRIP_DRIVER_PREFIX}:{employee.id}",
        )
    builder.button(text="✍️ Ввести вручну", callback_data=TRIP_DRIVER_MANUAL)
    builder.button(text="✖️ Скасувати", callback_data=FORM_CANCEL)
    builder.adjust(1)
    return builder.as_markup()


def trip_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Створити рейс", callback_data=TRIP_CONFIRM)
    builder.button(text="✖️ Скасувати", callback_data=FORM_CANCEL)
    builder.adjust(1)
    return builder.as_markup()


def trips_keyboard(trips, *, offset: int = 0, total: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for trip in trips:
        builder.button(
            text=f"ТТН {trip.ttn_num} · {trip.arrival_date}",
            callback_data=f"{TRIP_SHOW_PREFIX}:{trip.id}",
        )
    builder.adjust(1)
    if total is not None:
        _add_pagination(builder, "trips", offset=offset, limit=PAGE_TRIPS, total=total)
    builder.row(
        InlineKeyboardButton(text="🚛 Новий рейс", callback_data=MENU_TRIP_NEW)
    )
    builder.row(InlineKeyboardButton(text="⬅️ Меню", callback_data=MENU_BACK))
    return builder.as_markup()


def trip_card_keyboard(trip_id: int, *, editable: bool = True) -> InlineKeyboardMarkup:
    """`editable=False` — для водія: рейс йому видали, а не він його веде."""
    builder = InlineKeyboardBuilder()
    if editable:
        builder.button(
            text="✏️ Редагувати", callback_data=f"{TRIP_EDIT_PREFIX}:{trip_id}"
        )
        builder.button(
            text="🗑 Видалити", callback_data=f"{TRIP_DELETE_PREFIX}:{trip_id}"
        )
    builder.button(text="⬅️ До рейсів", callback_data=MENU_TRIPS)
    builder.adjust(2, 1) if editable else builder.adjust(1)
    return builder.as_markup()


def trip_fields_keyboard(trip_id: int, fields) -> InlineKeyboardMarkup:
    """Меню полів рейсу. Список приходить ззовні: які поля існують і як
    називаються, знає хендлер, який їх і зберігає."""
    builder = InlineKeyboardBuilder()
    for key, title in fields:
        builder.button(text=title, callback_data=f"{TRIP_FIELD_PREFIX}:{key}:{trip_id}")
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(
            text="⬅️ До рейсу", callback_data=f"{TRIP_SHOW_PREFIX}:{trip_id}"
        )
    )
    return builder.as_markup()


def after_trip_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🧾 Рейси", callback_data=MENU_TRIPS)
    builder.button(text="🚛 Ще один рейс", callback_data=MENU_TRIP_NEW)
    builder.button(text="⬅️ Меню", callback_data=MENU_BACK)
    builder.adjust(1)
    return builder.as_markup()
