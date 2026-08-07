from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

# Модуль, а не значення: прапорець читається під час виклику, тож його
# можна перемкнути в рантаймі (див. app/bot/constants.py).
from app.bot import constants
from app.bot.access import (
    CATEGORY_EMPLOYEES,
    CATEGORY_TRIPS,
    CATEGORY_VEHICLES,
    DENIED,
    MAIN_ADMIN_ONLY,
    Access,
    resolve_company_id,
)
from app.bot.actions import (
    delete_application,
    render_all_applications,
    render_companies,
    render_company_employees,
    render_company_vehicles,
    render_own_applications,
    render_positions,
    render_stats,
    render_trips,
    render_vehicle_types,
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
    "Натисніть «Зареєструватися»: знадобляться ПІБ, телефон і компанія. "
    "Посаду та права призначає головний адміністратор."
)

HELP_REGISTERED = (
    "Я веду рейси.\n\n"
    "Користуйтесь кнопками нижче — вводити команди не потрібно.\n\n"
    "«Новий рейс» проведе по кроках: ТТН, дата прибуття, замовник, "
    "експортер, транспорт, культура й водій. Ваші контакти як менеджера "
    "я підставлю сам — питати їх не буду.\n\n"
    "На кожному кроці є «⬅️ Назад», а перед створенням — «✏️ Змінити»: "
    "виправити одне поле можна, не проходячи анкету заново.\n\n"
    "Якщо зручніше текстом, працюють і команди:\n"
    + ("/new — нова заявка\n/my — мої заявки\n" if constants.SHOW_APPLICATIONS else "")
    + "/cancel — перервати заповнення\n"
    "/help — ця довідка"
)

ADMIN_HELP = (
    "\n\nВи адміністратор: вам видно рейси всієї компанії, а головному "
    "адміністратору — усіх компаній."
)

#: Заявки вимкнені прапорцем, але callback_data можна переслати або підробити,
#: тому хендлери відмовляють самі, а не покладаються на приховану кнопку.
APPLICATIONS_OFF = "Заявки наразі вимкнені — користуйтесь рейсами."


def menu_for(access: Access):
    return main_menu_keyboard(access)


def _help_text(access: Access) -> str:
    if not access.is_registered:
        return HELP_GUEST
    return HELP_REGISTERED + (ADMIN_HELP if access.is_main_admin else "")


async def _reject_applications(callback: CallbackQuery) -> bool:
    if constants.SHOW_APPLICATIONS:
        return False
    await callback.answer(APPLICATIONS_OFF, show_alert=True)
    return True


async def _reject_non_admin(callback: CallbackQuery, access: Access) -> bool:
    """Спільні списки заявок — лише головному адміну. Заявки вимкнені
    прапорцем, тож ця гілка зараз недосяжна, але право перевіряється."""
    if access.is_main_admin:
        return False
    await callback.answer(MAIN_ADMIN_ONLY, show_alert=True)
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
    if not constants.SHOW_APPLICATIONS:
        await message.answer(APPLICATIONS_OFF, reply_markup=menu_for(access))
        return
    if not access.is_registered:
        await message.answer(_help_text(access), reply_markup=menu_for(access))
        return
    text, keyboard = await render_own_applications(session, access.telegram_user_id)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == MENU_MY)
async def on_my(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    if await _reject_applications(callback):
        return
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
    if await _reject_applications(callback) or await _reject_non_admin(callback, access):
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
    if await _reject_applications(callback) or await _reject_non_admin(callback, access):
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
    """Гортання будь-якого списку.

    Формат: page:<вид>[:<параметри>]:<зсув> — зсув завжди останній, тож
    списки з додатковими параметрами (компанія, тип транспорту) вкладаються
    в той самий розбір. Права перевіряються тут заново: і вид, і параметри
    приходять із callback_data, яку можна підмінити.
    """
    parts = (callback.data or "").split(":")
    if len(parts) < 3 or not parts[-1].isdigit():
        await callback.answer("Не вдалося погортати", show_alert=True)
        return
    kind, args, offset = parts[1], parts[2:-1], int(parts[-1])

    if kind == "my":
        if await _reject_applications(callback):
            return
        if not access.is_registered:
            await callback.answer("Спершу зареєструйтесь.", show_alert=True)
            return
        rendered = await render_own_applications(
            session, access.telegram_user_id, offset=offset
        )
    elif kind == "all":
        if await _reject_applications(callback) or await _reject_non_admin(
            callback, access
        ):
            return
        rendered = await render_all_applications(session, offset=offset)
    elif kind == "trips":
        if not access.can(CATEGORY_TRIPS):
            await callback.answer(DENIED, show_alert=True)
            return
        # Обсяг видимого визначає render_trips за правами — у callback_data
        # немає нічого, чим його можна було б розширити.
        rendered = await render_trips(session, access, offset=offset)
    elif kind in ("pos", "comp", "vtype"):
        if not access.is_main_admin:
            await callback.answer(MAIN_ADMIN_ONLY, show_alert=True)
            return
        renderers = {
            "pos": render_positions,
            "comp": render_companies,
            "vtype": render_vehicle_types,
        }
        rendered = await renderers[kind](session, offset=offset)
    elif kind == "cemp" and args:
        if not access.can(CATEGORY_EMPLOYEES):
            await callback.answer(DENIED, show_alert=True)
            return
        company_id = resolve_company_id(access, args[0])
        if company_id is None:
            await callback.answer(DENIED, show_alert=True)
            return
        rendered = await render_company_employees(
            session, company_id, offset=offset, is_main_admin=access.is_main_admin
        )
    elif kind == "veh" and len(args) == 2:
        if not access.can(CATEGORY_VEHICLES):
            await callback.answer(DENIED, show_alert=True)
            return
        company_id = resolve_company_id(access, args[1])
        if company_id is None:
            await callback.answer(DENIED, show_alert=True)
            return
        rendered = await render_company_vehicles(
            session, args[0], company_id, offset=offset,
            is_main_admin=access.is_main_admin,
        )
        if rendered is None:
            await callback.answer("Невідомий тип", show_alert=True)
            return
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
        if access.is_main_admin:
            text, keyboard = await render_all_applications(session)
        else:
            text, keyboard = await render_own_applications(
                session, access.telegram_user_id
            )
        await callback.message.edit_text(text, reply_markup=keyboard)
