from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.actions import delete_application
from app.bot.keyboards import main_menu_keyboard
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
    """Текстовий шлях видалення. Кнопка «🗑» у /my робить те саме через
    ту саму функцію — права перевіряються в одному місці."""
    if message.from_user is None:
        return

    keyboard = main_menu_keyboard(is_admin=settings.is_admin(message.from_user.id))

    if not command.args or not command.args.strip().isdigit():
        await message.answer(
            "Використання: /delete &lt;id&gt;\n"
            "Простіше — кнопка «🗑» у списку заявок.",
            reply_markup=keyboard,
        )
        return

    _, response = await delete_application(
        session, publisher, settings,
        application_id=int(command.args.strip()),
        actor_id=message.from_user.id,
    )
    await message.answer(response, reply_markup=keyboard)
