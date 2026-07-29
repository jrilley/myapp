from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app import repository
from app.bot.publisher import Publisher
from app.config import Settings

router = Router(name="admin")


@router.message(Command("delete"))
async def cmd_delete(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    publisher: Publisher,
    settings: Settings,
) -> None:
    if message.from_user is None:
        return

    if not command.args or not command.args.strip().isdigit():
        await message.answer("Використання: /delete &lt;id&gt;")
        return

    application_id = int(command.args.strip())
    application = await repository.get_application(session, application_id)
    if application is None:
        await message.answer(f"Заявку #{application_id} не знайдено.")
        return

    # Адмін може видалити будь-яку заявку, звичайний користувач — лише власну.
    is_owner = application.telegram_user_id == message.from_user.id
    if not (is_owner or settings.is_admin(message.from_user.id)):
        await message.answer("Ви можете видаляти лише власні заявки.")
        return

    await repository.soft_delete_application(session, application)

    if application.group_chat_id is not None and application.group_message_id is not None:
        # Best-effort: збій прибирання в групі не має скасовувати видалення в БД.
        await publisher.retract(
            application.group_chat_id, application.group_message_id
        )

    await message.answer(f"🗑 Заявку #{application_id} видалено.")
