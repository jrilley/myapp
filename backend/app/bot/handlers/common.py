from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.actions import (
    delete_application,
    render_all_applications,
    render_own_applications,
    render_stats,
)
from app.bot.keyboards import (
    DELETE_PREFIX,
    MENU_ALL,
    MENU_BACK,
    MENU_HELP,
    MENU_MY,
    MENU_STATS,
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

ADMIN_HELP = (
    "\n\nВи адміністратор: у меню доступні «Усі заявки» та «Статистика», "
    "і ви можете видаляти чужі заявки."
)


def _menu_for(user_id: int, settings: Settings):
    return main_menu_keyboard(is_admin=settings.is_admin(user_id))


async def _reject_non_admin(callback: CallbackQuery, settings: Settings) -> bool:
    """Кнопку видно лише адмінам, але це не захист: callback_data можна
    переслати або підробити. Тому право перевіряємо на кожному виклику."""
    if settings.is_admin(callback.from_user.id):
        return False
    await callback.answer("Дія доступна лише адміністраторам.", show_alert=True)
    return True


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, settings: Settings) -> None:
    # /start скидає незавершену анкету, щоб людина не залишалась
    # у «підвислому» стані з попередньої спроби.
    await state.clear()
    if message.from_user is None:
        return
    await message.answer(GREETING, reply_markup=_menu_for(message.from_user.id, settings))


@router.message(Command("help"))
async def cmd_help(message: Message, settings: Settings) -> None:
    if message.from_user is None:
        return
    is_admin = settings.is_admin(message.from_user.id)
    text = HELP_TEXT + (ADMIN_HELP if is_admin else "")
    await message.answer(text, reply_markup=main_menu_keyboard(is_admin=is_admin))


@router.callback_query(F.data == MENU_HELP)
async def on_help(callback: CallbackQuery, settings: Settings) -> None:
    await callback.answer()
    is_admin = settings.is_admin(callback.from_user.id)
    text = HELP_TEXT + (ADMIN_HELP if is_admin else "")
    if callback.message is not None:
        await callback.message.answer(
            text, reply_markup=main_menu_keyboard(is_admin=is_admin)
        )


@router.callback_query(F.data == MENU_BACK)
async def on_back(
    callback: CallbackQuery, state: FSMContext, settings: Settings
) -> None:
    await state.clear()
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            GREETING, reply_markup=_menu_for(callback.from_user.id, settings)
        )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, settings: Settings) -> None:
    if message.from_user is None:
        return
    keyboard = _menu_for(message.from_user.id, settings)
    if await state.get_state() is None:
        await message.answer("Немає чого скасовувати.", reply_markup=keyboard)
        return
    await state.clear()
    await message.answer("Заповнення скасовано.", reply_markup=keyboard)


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


@router.callback_query(F.data == MENU_ALL)
async def on_all(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if await _reject_non_admin(callback, settings):
        return
    await state.clear()
    await callback.answer()
    text, keyboard = await render_all_applications(session)
    if callback.message is not None:
        await callback.message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == MENU_STATS)
async def on_stats(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    if await _reject_non_admin(callback, settings):
        return
    await state.clear()
    await callback.answer()
    text, keyboard = await render_stats(session)
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
    # Адміну показуємо загальний список, решті — свій.
    if ok and callback.message is not None:
        if settings.is_admin(callback.from_user.id):
            text, keyboard = await render_all_applications(session)
        else:
            text, keyboard = await render_own_applications(session, callback.from_user.id)
        await callback.message.edit_text(text, reply_markup=keyboard)
