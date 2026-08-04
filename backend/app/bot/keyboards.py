from collections.abc import Sequence

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

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

MENU_VEHICLE_ADD = "menu:vehicle"
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
REG_POSITION_PREFIX = "reg:position"
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

    builder.button(text="📝 Нова заявка", callback_data=MENU_NEW)
    builder.button(text="📋 Мої заявки", callback_data=MENU_MY)
    if is_admin:
        builder.button(text="🗂 Усі заявки", callback_data=MENU_ALL)
        builder.button(text="📊 Статистика", callback_data=MENU_STATS)
        builder.button(text="🚛 Додати автомобіль", callback_data=MENU_VEHICLE_ADD)
    if is_main_admin:
        builder.button(text="👥 Користувачі", callback_data=MENU_EMPLOYEES)
        builder.button(text="💼 Посади", callback_data=MENU_POSITIONS)
        builder.button(text="🏢 Компанії", callback_data=MENU_COMPANIES)
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
    employees, *, offset: int = 0, total: int | None = None
) -> InlineKeyboardMarkup:
    """Список співробітників: кожен — кнопка, що відкриває картку."""
    builder = InlineKeyboardBuilder()
    for employee in employees:
        builder.button(
            text=f"{employee.fullname} · {employee.role.role}",
            callback_data=f"{EMP_VIEW_PREFIX}:{employee.id}",
        )
    builder.adjust(1)
    if total is not None:
        _add_pagination(
            builder, "emp", offset=offset, limit=PAGE_EMPLOYEES, total=total
        )
    builder.row(InlineKeyboardButton(text="⬅️ Меню", callback_data=MENU_BACK))
    return builder.as_markup()


def employee_card_keyboard(employee_id: int) -> InlineKeyboardMarkup:
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
    builder.button(text="⬅️ До списку", callback_data=MENU_EMPLOYEES)
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


def positions_keyboard(
    *, offset: int = 0, total: int | None = None
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Додати посаду", callback_data=POSITION_ADD)
    builder.adjust(1)
    if total is not None:
        _add_pagination(
            builder, "pos", offset=offset, limit=PAGE_REFERENCE, total=total
        )
    builder.row(InlineKeyboardButton(text="⬅️ Меню", callback_data=MENU_BACK))
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
