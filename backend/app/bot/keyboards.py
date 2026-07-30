from collections.abc import Sequence

from aiogram.types import InlineKeyboardMarkup
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

FORM_CANCEL = "form:cancel"
DELETE_PREFIX = "del"


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Головне меню. Команди лишаються робочими, але вводити їх не потрібно."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Нова заявка", callback_data=MENU_NEW)
    builder.button(text="📋 Мої заявки", callback_data=MENU_MY)
    builder.button(text="ℹ️ Довідка", callback_data=MENU_HELP)
    builder.adjust(1)
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


def own_applications_keyboard(
    applications: Sequence[Application],
) -> InlineKeyboardMarkup:
    """Кнопка видалення на кожну заявку — замість того, щоб набирати
    /delete з номером вручну."""
    builder = InlineKeyboardBuilder()
    for application in applications:
        builder.button(
            text=f"🗑 #{application.id} · {application.category}",
            callback_data=f"{DELETE_PREFIX}:{application.id}",
        )
    builder.button(text="⬅️ Меню", callback_data=MENU_BACK)
    builder.adjust(1)
    return builder.as_markup()


def back_to_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Меню", callback_data=MENU_BACK)
    return builder.as_markup()
