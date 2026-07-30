"""Дії, які викликаються і командою, і кнопкою.

Тримаємо їх окремо, щоб /delete і кнопка «🗑» не розʼїхались у правах
доступу: логіка перевірки одна на обидва шляхи.
"""

from aiogram.types import InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app import repository
from app.bot.formatting import format_own_application
from app.bot.keyboards import back_to_menu_keyboard, own_applications_keyboard
from app.bot.publisher import Publisher
from app.config import Settings


async def delete_application(
    session: AsyncSession,
    publisher: Publisher,
    settings: Settings,
    *,
    application_id: int,
    actor_id: int,
) -> tuple[bool, str]:
    """Повертає (чи вдалося, текст відповіді користувачу)."""
    application = await repository.get_application(session, application_id)
    if application is None:
        return False, f"Заявку #{application_id} не знайдено."

    # Адмін може видалити будь-яку заявку, звичайний користувач — лише власну.
    is_owner = application.telegram_user_id == actor_id
    if not (is_owner or settings.is_admin(actor_id)):
        return False, "Ви можете видаляти лише власні заявки."

    chat_id = application.group_chat_id
    message_id = application.group_message_id

    await repository.soft_delete_application(session, application)

    if chat_id is not None and message_id is not None:
        # Best-effort: збій прибирання в групі не має скасовувати видалення в БД.
        await publisher.retract(chat_id, message_id)

    return True, f"🗑 Заявку #{application_id} видалено."


async def render_own_applications(
    session: AsyncSession, telegram_user_id: int
) -> tuple[str, InlineKeyboardMarkup]:
    """Текст списку заявок користувача разом із клавіатурою під нього."""
    applications = await repository.list_user_applications(session, telegram_user_id)
    if not applications:
        return "У вас поки немає заявок.", back_to_menu_keyboard()

    body = "\n\n".join(format_own_application(a) for a in applications)
    return f"<b>Ваші заявки:</b>\n\n{body}", own_applications_keyboard(applications)
