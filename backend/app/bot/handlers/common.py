from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app import repository
from app.bot.formatting import format_own_application

router = Router(name="common")

HELP_TEXT = (
    "Я приймаю заявки.\n\n"
    "/new — заповнити нову заявку\n"
    "/my — мої заявки\n"
    "/cancel — перервати заповнення\n"
    "/help — ця довідка"
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    # /start скидає незавершену анкету, щоб користувач не залишався
    # у «підвислому» стані з попередньої спроби.
    await state.clear()
    await message.answer(f"Вітаю! {HELP_TEXT}")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer("Немає чого скасовувати. /new — почати заявку.")
        return
    await state.clear()
    await message.answer("Заповнення скасовано. /new — почати спочатку.")


@router.message(Command("my"))
async def cmd_my(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    applications = await repository.list_user_applications(
        session, message.from_user.id
    )
    if not applications:
        await message.answer("У вас поки немає заявок. /new — створити.")
        return
    body = "\n\n".join(format_own_application(a) for a in applications)
    await message.answer(f"<b>Ваші заявки:</b>\n\n{body}")
