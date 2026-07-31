from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.access import Access
from app.bot.actions import delete_application
from app.bot.handlers.common import menu_for
from app.bot.publisher import Publisher

router = Router(name="admin")


@router.message(Command("delete"))
async def cmd_delete(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    publisher: Publisher,
    access: Access,
) -> None:
    """Текстовий шлях видалення. Кнопка «🗑» у списку робить те саме через
    ту саму функцію — права перевіряються в одному місці."""
    keyboard = menu_for(access)

    if not command.args or not command.args.strip().isdigit():
        await message.answer(
            "Використання: /delete &lt;id&gt;\n"
            "Простіше — кнопка «🗑» у списку заявок.",
            reply_markup=keyboard,
        )
        return

    _, response = await delete_application(
        session, publisher, access, application_id=int(command.args.strip())
    )
    await message.answer(response, reply_markup=keyboard)
