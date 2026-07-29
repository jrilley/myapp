from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.constants import CATEGORIES

CATEGORY_PREFIX = "cat"
CONFIRM_YES = "confirm:yes"
CONFIRM_NO = "confirm:no"


def categories_keyboard() -> InlineKeyboardMarkup:
    """Категорія обирається з фіксованого списку, а не вільним текстом —
    інакше поле стає непридатним для фільтрації на сайті."""
    builder = InlineKeyboardBuilder()
    for index, title in enumerate(CATEGORIES):
        builder.button(text=title, callback_data=f"{CATEGORY_PREFIX}:{index}")
    builder.adjust(1)
    return builder.as_markup()


def confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Надіслати", callback_data=CONFIRM_YES)
    builder.button(text="✖️ Скасувати", callback_data=CONFIRM_NO)
    builder.adjust(2)
    return builder.as_markup()
