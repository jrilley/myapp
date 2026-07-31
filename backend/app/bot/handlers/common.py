from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.access import Access
from app.bot.actions import (
    delete_application,
    render_all_applications,
    render_companies,
    render_employees,
    render_own_applications,
    render_positions,
    render_stats,
)
from app.bot.keyboards import (
    DELETE_PREFIX,
    MENU_ALL,
    MENU_BACK,
    MENU_HELP,
    MENU_MY,
    MENU_STATS,
    NOOP,
    PAGE_PREFIX,
    main_menu_keyboard,
)
from app.bot.publisher import Publisher

router = Router(name="common")

GREETING_REGISTERED = "Вітаю! Я приймаю заявки. Оберіть дію:"
GREETING_GUEST = (
    "Вітаю! Щоб подавати заявки, спершу зареєструйтесь — "
    "це займе хвилину."
)

HELP_GUEST = (
    "Я приймаю заявки від зареєстрованих співробітників.\n\n"
    "Натисніть «Зареєструватися»: знадобляться ПІБ, телефон, "
    "компанія та посада."
)

HELP_REGISTERED = (
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


def menu_for(access: Access):
    return main_menu_keyboard(
        is_registered=access.is_registered,
        is_admin=access.is_admin,
        is_main_admin=access.is_main_admin,
    )


def _help_text(access: Access) -> str:
    if not access.is_registered:
        return HELP_GUEST
    return HELP_REGISTERED + (ADMIN_HELP if access.is_admin else "")


async def _reject_non_admin(callback: CallbackQuery, access: Access) -> bool:
    """Кнопку видно лише адмінам, але це не захист: callback_data можна
    переслати або підробити. Тому право перевіряємо на кожному виклику."""
    if access.is_admin:
        return False
    await callback.answer("Дія доступна лише адміністраторам.", show_alert=True)
    return True


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, access: Access) -> None:
    # /start скидає незавершену анкету, щоб людина не залишалась
    # у «підвислому» стані з попередньої спроби.
    await state.clear()
    greeting = GREETING_REGISTERED if access.is_registered else GREETING_GUEST
    await message.answer(greeting, reply_markup=menu_for(access))


@router.message(Command("help"))
async def cmd_help(message: Message, access: Access) -> None:
    await message.answer(_help_text(access), reply_markup=menu_for(access))


@router.callback_query(F.data == MENU_HELP)
async def on_help(callback: CallbackQuery, access: Access) -> None:
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            _help_text(access), reply_markup=menu_for(access)
        )


@router.callback_query(F.data == MENU_BACK)
async def on_back(callback: CallbackQuery, state: FSMContext, access: Access) -> None:
    await state.clear()
    await callback.answer()
    greeting = GREETING_REGISTERED if access.is_registered else GREETING_GUEST
    if callback.message is not None:
        await callback.message.answer(greeting, reply_markup=menu_for(access))


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext, access: Access) -> None:
    keyboard = menu_for(access)
    if await state.get_state() is None:
        await message.answer("Немає чого скасовувати.", reply_markup=keyboard)
        return
    await state.clear()
    await message.answer("Заповнення скасовано.", reply_markup=keyboard)


@router.message(Command("my"))
async def cmd_my(message: Message, session: AsyncSession, access: Access) -> None:
    if not access.is_registered:
        await message.answer(_help_text(access), reply_markup=menu_for(access))
        return
    text, keyboard = await render_own_applications(session, access.telegram_user_id)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == MENU_MY)
async def on_my(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    await state.clear()
    await callback.answer()
    if callback.message is None:
        return
    if not access.is_registered:
        await callback.message.answer(_help_text(access), reply_markup=menu_for(access))
        return
    text, keyboard = await render_own_applications(session, access.telegram_user_id)
    await callback.message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == MENU_ALL)
async def on_all(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    if await _reject_non_admin(callback, access):
        return
    await state.clear()
    await callback.answer()
    text, keyboard = await render_all_applications(session)
    if callback.message is not None:
        await callback.message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == MENU_STATS)
async def on_stats(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    if await _reject_non_admin(callback, access):
        return
    await state.clear()
    await callback.answer()
    text, keyboard = await render_stats(session)
    if callback.message is not None:
        await callback.message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == NOOP)
async def on_noop(callback: CallbackQuery) -> None:
    """Лічильник «2 / 5» — не кнопка, але Telegram чекає відповіді."""
    await callback.answer()


@router.callback_query(F.data.startswith(f"{PAGE_PREFIX}:"))
async def on_page(
    callback: CallbackQuery, session: AsyncSession, access: Access
) -> None:
    """Гортання будь-якого списку. Права перевіряються тут заново:
    offset у callback_data можна підмінити, а сам вид списку — підставити."""
    parts = (callback.data or "").split(":")
    if len(parts) != 3 or not parts[2].isdigit():
        await callback.answer("Не вдалося погортати", show_alert=True)
        return
    _, kind, raw_offset = parts
    offset = int(raw_offset)

    if kind == "my":
        if not access.is_registered:
            await callback.answer("Спершу зареєструйтесь.", show_alert=True)
            return
        rendered = await render_own_applications(
            session, access.telegram_user_id, offset=offset
        )
    elif kind == "all":
        if await _reject_non_admin(callback, access):
            return
        rendered = await render_all_applications(session, offset=offset)
    elif kind in ("emp", "pos", "comp"):
        if not access.is_main_admin:
            await callback.answer(
                "Дія доступна лише головному адміністратору.", show_alert=True
            )
            return
        if kind == "emp":
            rendered = await render_employees(session, offset=offset)
        elif kind == "pos":
            rendered = await render_positions(session, offset=offset)
        else:
            rendered = await render_companies(session, offset=offset)
    else:
        await callback.answer("Невідомий список", show_alert=True)
        return

    await callback.answer()
    text, keyboard = rendered
    if callback.message is not None:
        # Гортаємо на місці, а не засипаємо чат новими повідомленнями.
        await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith(f"{DELETE_PREFIX}:"))
async def on_delete(
    callback: CallbackQuery,
    session: AsyncSession,
    publisher: Publisher,
    access: Access,
) -> None:
    raw_id = (callback.data or "").split(":", 1)[1]
    if not raw_id.isdigit():
        await callback.answer("Невідома заявка", show_alert=True)
        return

    ok, response = await delete_application(
        session, publisher, access, application_id=int(raw_id)
    )
    await callback.answer(response, show_alert=not ok)

    # Перемальовуємо список на місці, щоб видалений запис одразу зник.
    # Адміну показуємо загальний список, решті — свій.
    if ok and callback.message is not None:
        if access.is_admin:
            text, keyboard = await render_all_applications(session)
        else:
            text, keyboard = await render_own_applications(
                session, access.telegram_user_id
            )
        await callback.message.edit_text(text, reply_markup=keyboard)
