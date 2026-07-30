from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.actions import delete_application, render_own_applications
from app.bot.keyboards import (
    DELETE_PREFIX,
    MENU_BACK,
    MENU_HELP,
    MENU_MY,
    main_menu_keyboard,
)
from app.bot.publisher import Publisher
from app.config import Settings

router = Router(name="common")

GREETING = "Вітаю! Я приймаю заявки. Оберіть дію:"

HELP_TEXT = (
    "Я приймаю заявки.\n\n"
    "Користуйтесь кнопками нижче — вводити команди не потрібно.\n\n"
    "Якщо зручніше текстом, працюють і команди:\n"
    "/new — нова заявка\n"
    "/my — мої заявки\n"
    "/cancel — перервати заповнення\n"
    "/help — ця довідка"
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    # /start скидає незавершену анкету, щоб людина не залишалась
    # у «підвислому» стані з попередньої спроби.
    await state.clear()
    await message.answer(GREETING, reply_markup=main_menu_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=main_menu_keyboard())


@router.callback_query(F.data == MENU_HELP)
async def on_help(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(HELP_TEXT, reply_markup=main_menu_keyboard())


@router.callback_query(F.data == MENU_BACK)
async def on_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(GREETING, reply_markup=main_menu_keyboard())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer("Немає чого скасовувати.", reply_markup=main_menu_keyboard())
        return
    await state.clear()
    await message.answer("Заповнення скасовано.", reply_markup=main_menu_keyboard())


@router.message(Command("my"))
async def cmd_my(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return
    text, keyboard = await render_own_applications(session, message.from_user.id)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == MENU_MY)
async def on_my(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    await callback.answer()
    text, keyboard = await render_own_applications(session, callback.from_user.id)
    if callback.message is not None:
        await callback.message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith(f"{DELETE_PREFIX}:"))
async def on_delete(
    callback: CallbackQuery,
    session: AsyncSession,
    publisher: Publisher,
    settings: Settings,
) -> None:
    raw_id = (callback.data or "").split(":", 1)[1]
    if not raw_id.isdigit():
        await callback.answer("Невідома заявка", show_alert=True)
        return

    ok, response = await delete_application(
        session, publisher, settings,
        application_id=int(raw_id), actor_id=callback.from_user.id,
    )
    await callback.answer(response, show_alert=not ok)

    # Перемальовуємо список на місці, щоб видалений запис одразу зник.
    if ok and callback.message is not None:
        text, keyboard = await render_own_applications(session, callback.from_user.id)
        await callback.message.edit_text(text, reply_markup=keyboard)
