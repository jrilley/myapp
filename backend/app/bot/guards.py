"""Перевірки прав на вході в хендлер.

Окремий модуль, бо `access` навмисно не знає про aiogram: там чиста логіка
прав, тут — те, як про відмову дізнається користувач.

Приховати кнопку — не захист: callback_data можна переслати або підробити,
тому кожен обмежений хендлер починається з виклику звідси.
"""

from aiogram.types import CallbackQuery

from app.bot.access import DENIED, MAIN_ADMIN_ONLY, READ, Access


async def deny(
    callback: CallbackQuery, access: Access, category: str, right: str = READ
) -> bool:
    """True, якщо права немає — відмова вже надіслана, хендлер має вийти."""
    if access.can(category, right):
        return False
    await callback.answer(DENIED, show_alert=True)
    return True


async def deny_main_admin(callback: CallbackQuery, access: Access) -> bool:
    """Для того, що не належить жодній компанії: довідники ролей і посад,
    список усіх компаній."""
    if access.is_main_admin:
        return False
    await callback.answer(MAIN_ADMIN_ONLY, show_alert=True)
    return True
