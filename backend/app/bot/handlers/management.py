"""Керування співробітниками та довідником посад.

Доступно лише головному адміністратору. Кожен хендлер перевіряє право
самостійно: приховати кнопку недостатньо, callback_data можна переслати.
"""

from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app import repository
from app.bot.access import ADMIN_ONLY, Access, resolve_company_id
from app.bot.actions import render_company_employees, render_positions
from app.bot.constants import (
    MAX_ADDRESS,
    MAX_COMPANY_NAME,
    MAX_FULLNAME,
    MAX_PHONE,
    MAX_POSITION,
    MAX_TAX_ID,
    MIN_PHONE,
    parse_chat_id,
)
from app.bot.keyboards import (
    COMPANY_CARD_PREFIX,
    COMPANY_EDIT_PREFIX,
    COMPANY_EMPLOYEES_PREFIX,
    EMP_EDIT_PREFIX,
    EMP_SET_PREFIX,
    EMP_VIEW_PREFIX,
    MENU_MY_EMPLOYEES,
    MENU_POSITIONS,
    POSITION_ADD,
    POSITION_CARD_PREFIX,
    POSITION_NEW_ACCESS_PREFIX,
    POSITION_SET_ACCESS_PREFIX,
    cancel_keyboard,
    company_card_keyboard,
    employee_card_keyboard,
    employee_choice_keyboard,
    position_access_keyboard,
    position_card_keyboard,
)
from app.bot.states import CompanyEdit, EmployeeEdit, PositionForm
from app.models import Employee

router = Router(name="management")

DENIED = "Дія доступна лише головному адміністратору."

# Поле картки → (назва в БД, підпис, як дістати варіанти)
CHOICE_FIELDS = {
    "company": ("company_id", "компанію"),
    "position": ("position_id", "посаду"),
    "role": ("role_id", "роль"),
}


#: Поля, які змінює лише головний адмін.
#:
#: Роль і посада — за рішенням замовника: керівні посади й будь-яке
#: підвищення прав роздає він сам. Компанія — щоб адміністратор компанії не
#: міг перекинути працівника до чужої.
#:
#: Адміністратору компанії лишаються ПІБ і телефони своїх людей.
MAIN_ADMIN_FIELDS = frozenset({"role", "company", "position"})


async def _deny(callback: CallbackQuery, access: Access) -> bool:
    """Лише головний адмін — для довідників і картки компанії."""
    if access.is_main_admin:
        return False
    await callback.answer(DENIED, show_alert=True)
    return True


async def _employee_or_denied(
    callback: CallbackQuery, session: AsyncSession, access: Access, employee_id: int
) -> Employee | None:
    """Співробітник, якого цьому адміну дозволено чіпати.

    Головний — будь-якого; адміністратор компанії — лише зі своєї компанії,
    навіть якщо дістане чужий id.
    """
    if not access.is_admin:
        await callback.answer(ADMIN_ONLY, show_alert=True)
        return None

    employee = await repository.get_employee(session, employee_id)
    if employee is None:
        await callback.answer("Співробітника не знайдено", show_alert=True)
        return None

    if not access.is_main_admin and employee.company_id != resolve_company_id(
        access, None
    ):
        await callback.answer(ADMIN_ONLY, show_alert=True)
        return None
    return employee


def _card(employee: Employee) -> str:
    extra = employee.phone_number2
    return (
        f"<b>{escape(employee.fullname)}</b>\n\n"
        f"<b>Телефон:</b> {escape(employee.phone_number)}\n"
        + (f"<b>Додатковий:</b> {escape(extra)}\n" if extra else "")
        + f"<b>Компанія:</b> {escape(employee.company.name)}\n"
        f"<b>Посада:</b> {escape(employee.position.position)}\n"
        f"<b>Роль:</b> {escape(employee.role.role)}\n"
        f"<b>Telegram id:</b> <code>{employee.tg_id}</code>"
    )


async def _show_card(
    message, session: AsyncSession, employee_id: int, *, access: Access
) -> None:
    employee = await repository.get_employee(session, employee_id)
    if employee is None:
        await message.answer("Співробітника не знайдено.")
        return
    back = (
        f"{COMPANY_EMPLOYEES_PREFIX}:{employee.company_id}"
        if access.is_main_admin
        else MENU_MY_EMPLOYEES
    )
    await message.answer(
        _card(employee), reply_markup=employee_card_keyboard(employee.id, back)
    )


# ---------------------------------------------------------------------------
# Користувачі
# ---------------------------------------------------------------------------


@router.callback_query(F.data.startswith(f"{COMPANY_CARD_PREFIX}:"))
async def on_company_card(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    """Картка компанії — вхід у її транспорт і працівників."""
    if await _deny(callback, access):
        return
    raw_id = (callback.data or "").split(":", 1)[1]
    if not raw_id.isdigit():
        await callback.answer("Невідома компанія", show_alert=True)
        return

    company = await repository.get_company(session, int(raw_id))
    if company is None:
        await callback.answer("Компанію не знайдено", show_alert=True)
        return

    await state.clear()
    await callback.answer()
    if callback.message is not None:
        await _show_company(callback.message, company)


def _company_card(company) -> str:
    chat = (
        f"<code>{company.company_chat_id}</code>"
        if company.company_chat_id is not None
        else "не вказано — рейси нікуди не дублюються"
    )
    return (
        f"<b>{escape(company.name)}</b>\n\n"
        f"<b>Податковий номер:</b> {escape(company.tax_id)}\n"
        f"<b>Адреса:</b> {escape(company.address)}\n"
        f"<b>Робочий чат:</b> {chat}"
    )


async def _show_company(message, company) -> None:
    await message.answer(
        _company_card(company), reply_markup=company_card_keyboard(company.id)
    )


#: поле в callback → (колонка, підпис, запит)
COMPANY_FIELDS = {
    "name": ("name", "Назва", "Нова назва компанії:"),
    "tax": ("tax_id", "Податковий номер", "Новий податковий номер:"),
    "address": ("address", "Адреса", "Нова адреса:"),
    "chat": (
        "company_chat_id",
        "Робочий чат",
        "Id робочого чату (наприклад <code>-1001234567890</code>). "
        "Надішліть «-», щоб прибрати:",
    ),
}


@router.callback_query(F.data.startswith(f"{COMPANY_EDIT_PREFIX}:"))
async def on_company_edit(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    if await _deny(callback, access):
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 3 or parts[1] not in COMPANY_FIELDS or not parts[2].isdigit():
        await callback.answer("Невідоме поле", show_alert=True)
        return

    company = await repository.get_company(session, int(parts[2]))
    if company is None:
        await callback.answer("Компанію не знайдено", show_alert=True)
        return

    _, _, prompt = COMPANY_FIELDS[parts[1]]
    await state.clear()
    await state.update_data(company_id=company.id, field=parts[1])
    await state.set_state(CompanyEdit.value)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(prompt, reply_markup=cancel_keyboard())


@router.message(CompanyEdit.value, F.text)
async def edit_company_value(
    message: Message, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    if not access.is_main_admin:
        await state.clear()
        await message.answer(DENIED)
        return

    data = await state.get_data()
    field = COMPANY_FIELDS.get(data.get("field", ""))
    company = await repository.get_company(session, data.get("company_id", 0))
    if field is None or company is None:
        await state.clear()
        await message.answer("Компанію не знайдено.")
        return

    column, _, _ = field
    value, error = await _company_value(session, data["field"], message.text or "", company)
    if error:
        await message.answer(error, reply_markup=cancel_keyboard())
        return

    await state.clear()
    company = await repository.update_company(session, company, **{column: value})
    await _show_company(message, company)


async def _company_value(session: AsyncSession, field: str, raw: str, company):
    """(значення, помилка) — рівно одне з двох None. Значення може бути None:
    робочий чат прибирається символом «-»."""
    value = raw.strip()
    if field == "name":
        if not 2 <= len(value) <= MAX_COMPANY_NAME:
            return None, f"Назва має бути від 2 до {MAX_COMPANY_NAME} символів."
        return value, None
    if field == "address":
        if not 4 <= len(value) <= MAX_ADDRESS:
            return None, f"Адреса має бути від 4 до {MAX_ADDRESS} символів."
        return value, None
    if field == "tax":
        if not 4 <= len(value) <= MAX_TAX_ID:
            return None, f"Номер має бути від 4 до {MAX_TAX_ID} символів."
        # tax_id унікальний; власний номер конфліктом не рахуємо.
        existing = await repository.get_company_by_tax_id(session, value)
        if existing is not None and existing.id != company.id:
            return None, "Компанія з таким номером уже є. Введіть інший."
        return value, None
    if field == "chat":
        if value == "-":
            return None, None
        chat_id = parse_chat_id(value)
        if chat_id is None:
            return None, (
                "Не схоже на id чату. Очікую ціле число, зазвичай від'ємне — "
                "наприклад -1001234567890."
            )
        return chat_id, None
    return None, "Невідоме поле."


@router.message(CompanyEdit.value)
async def company_non_text(message: Message) -> None:
    await message.answer(
        "Надішліть, будь ласка, текст.", reply_markup=cancel_keyboard()
    )


@router.callback_query(F.data.startswith(f"{COMPANY_EMPLOYEES_PREFIX}:"))
async def on_company_employees(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    company_id = resolve_company_id(access, (callback.data or "").split(":", 1)[1])
    if company_id is None:
        await callback.answer(ADMIN_ONLY, show_alert=True)
        return
    await state.clear()
    await callback.answer()
    if callback.message is not None:
        text, keyboard = await render_company_employees(
            session, company_id, is_main_admin=access.is_main_admin
        )
        await callback.message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == MENU_MY_EMPLOYEES)
async def on_my_employees(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    """Для адміністратора компанії — працівники його власної компанії."""
    company_id = resolve_company_id(access, None)
    if company_id is None:
        await callback.answer(ADMIN_ONLY, show_alert=True)
        return
    await state.clear()
    await callback.answer()
    if callback.message is not None:
        text, keyboard = await render_company_employees(
            session, company_id, is_main_admin=access.is_main_admin
        )
        await callback.message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith(f"{EMP_VIEW_PREFIX}:"))
async def on_employee_card(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    raw_id = (callback.data or "").split(":", 1)[1]
    if not raw_id.isdigit():
        await callback.answer("Невідомий співробітник", show_alert=True)
        return

    employee = await _employee_or_denied(callback, session, access, int(raw_id))
    if employee is None:
        return

    await state.clear()
    await callback.answer()
    if callback.message is not None:
        await _show_card(callback.message, session, employee.id, access=access)


@router.callback_query(F.data.startswith(f"{EMP_EDIT_PREFIX}:"))
async def on_employee_edit(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 3 or not parts[2].isdigit():
        await callback.answer("Невідоме поле", show_alert=True)
        return
    _, field, raw_id = parts
    employee_id = int(raw_id)

    if field in MAIN_ADMIN_FIELDS and not access.is_main_admin:
        await callback.answer(DENIED, show_alert=True)
        return

    employee = await _employee_or_denied(callback, session, access, employee_id)
    if employee is None:
        return

    await callback.answer()
    if callback.message is None:
        return

    text_fields = {
        "name": (EmployeeEdit.fullname, "Новий ПІБ:"),
        "phone": (EmployeeEdit.phone, "Новий номер телефону:"),
        "phone2": (
            EmployeeEdit.phone2,
            "Новий додатковий номер (надішліть «-», щоб прибрати):",
        ),
    }
    if field in text_fields:
        next_state, prompt = text_fields[field]
        await state.set_state(next_state)
        await state.update_data(employee_id=employee_id)
        await callback.message.answer(prompt, reply_markup=cancel_keyboard())
        return

    if field == "company":
        items = [(c.id, c.name) for c in await repository.list_companies(session)]
    elif field == "position":
        items = [(p.id, p.position) for p in await repository.list_positions(session)]
    elif field == "role":
        # Заборона на власну роль: інакше головний адмін одним натисканням
        # знімає з себе доступ і повернути його вже нічим.
        if employee.tg_id == access.telegram_user_id:
            await callback.message.answer(
                "Не можна змінити власну роль — так можна втратити доступ.",
                reply_markup=employee_card_keyboard(
                    employee_id, f"{COMPANY_EMPLOYEES_PREFIX}:{employee.company_id}"
                ),
            )
            return
        items = [(r.id, r.role) for r in await repository.list_roles(session)]
    else:
        await callback.message.answer("Невідоме поле.")
        return

    _, label = CHOICE_FIELDS[field]
    await callback.message.answer(
        f"Оберіть {label}:",
        reply_markup=employee_choice_keyboard(field, employee_id, items),
    )


@router.callback_query(F.data.startswith(f"{EMP_SET_PREFIX}:"))
async def on_employee_set(
    callback: CallbackQuery, session: AsyncSession, access: Access
) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 4 or not parts[2].isdigit() or not parts[3].isdigit():
        await callback.answer("Невідоме значення", show_alert=True)
        return
    _, field, raw_employee, raw_value = parts

    if field not in CHOICE_FIELDS:
        await callback.answer("Невідоме поле", show_alert=True)
        return

    if field in MAIN_ADMIN_FIELDS and not access.is_main_admin:
        await callback.answer(DENIED, show_alert=True)
        return

    employee = await _employee_or_denied(
        callback, session, access, int(raw_employee)
    )
    if employee is None:
        return

    if field == "role" and employee.tg_id == access.telegram_user_id:
        await callback.answer(
            "Не можна змінити власну роль.", show_alert=True
        )
        return

    column, _ = CHOICE_FIELDS[field]
    # Посада й роль ставляться незалежно: посада каже, ким людина працює,
    # роль — що їй дозволено, і одне не має тихо міняти інше.
    await repository.update_employee(session, employee, **{column: int(raw_value)})
    await callback.answer("Збережено")
    if callback.message is not None:
        await _show_card(callback.message, session, employee.id, access=access)


@router.message(EmployeeEdit.fullname, F.text)
async def edit_fullname(
    message: Message, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    value = (message.text or "").strip()
    if not 2 <= len(value) <= MAX_FULLNAME:
        await message.answer(
            f"ПІБ має бути від 2 до {MAX_FULLNAME} символів.",
            reply_markup=cancel_keyboard(),
        )
        return
    data = await state.get_data()
    await state.clear()

    employee = await repository.get_employee(session, data["employee_id"])
    if employee is None:
        await message.answer("Співробітника не знайдено.")
        return
    await repository.update_employee(session, employee, fullname=value)
    await _show_card(message, session, employee.id, access=access)


@router.message(EmployeeEdit.phone, F.text)
async def edit_phone(
    message: Message, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    value = (message.text or "").strip()
    if not MIN_PHONE <= len(value) <= MAX_PHONE:
        await message.answer(
            f"Номер має бути від {MIN_PHONE} до {MAX_PHONE} символів.",
            reply_markup=cancel_keyboard(),
        )
        return
    data = await state.get_data()
    await state.clear()

    employee = await repository.get_employee(session, data["employee_id"])
    if employee is None:
        await message.answer("Співробітника не знайдено.")
        return
    await repository.update_employee(session, employee, phone_number=value)
    await _show_card(message, session, employee.id, access=access)


@router.message(EmployeeEdit.phone2, F.text)
async def edit_phone2(
    message: Message, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    value = (message.text or "").strip()
    # Додатковий номер необов'язковий, тому потрібен спосіб його прибрати.
    cleared = value == "-"
    if not cleared and not MIN_PHONE <= len(value) <= MAX_PHONE:
        await message.answer(
            f"Номер має бути від {MIN_PHONE} до {MAX_PHONE} символів "
            "або «-», щоб прибрати.",
            reply_markup=cancel_keyboard(),
        )
        return
    data = await state.get_data()
    await state.clear()

    employee = await repository.get_employee(session, data["employee_id"])
    if employee is None:
        await message.answer("Співробітника не знайдено.")
        return
    await repository.update_employee(
        session, employee, phone_number2=None if cleared else value
    )
    await _show_card(message, session, employee.id, access=access)


# ---------------------------------------------------------------------------
# Посади
# ---------------------------------------------------------------------------


@router.callback_query(F.data == MENU_POSITIONS)
async def on_positions(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    if await _deny(callback, access):
        return
    await state.clear()
    await callback.answer()
    if callback.message is None:
        return

    text, keyboard = await render_positions(session)
    await callback.message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == POSITION_ADD)
async def on_position_add(
    callback: CallbackQuery, state: FSMContext, access: Access
) -> None:
    if await _deny(callback, access):
        return
    await state.clear()
    await state.set_state(PositionForm.name)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer("Назва посади:", reply_markup=cancel_keyboard())


@router.message(PositionForm.name, F.text)
async def position_name(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    value = (message.text or "").strip()
    if not 2 <= len(value) <= MAX_POSITION:
        await message.answer(
            f"Назва має бути від 2 до {MAX_POSITION} символів.",
            reply_markup=cancel_keyboard(),
        )
        return
    # position унікальний — ловимо тут, а не помилкою БД.
    if await repository.get_position_by_name(session, value):
        await message.answer(
            "Така посада вже є. Введіть іншу назву.", reply_markup=cancel_keyboard()
        )
        return

    await state.update_data(position_name=value)
    await state.set_state(PositionForm.self_service)
    await message.answer(
        f"Посада «{escape(value)}».\nЧи може людина обрати її сама при реєстрації?",
        reply_markup=position_access_keyboard(
            POSITION_NEW_ACCESS_PREFIX, back=MENU_POSITIONS
        ),
    )


@router.callback_query(
    PositionForm.self_service, F.data.startswith(f"{POSITION_NEW_ACCESS_PREFIX}:")
)
async def position_self_service(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    if await _deny(callback, access):
        return
    self_service = (callback.data or "").rsplit(":", 1)[-1] == "1"

    data = await state.get_data()
    await state.clear()
    await callback.answer()
    if callback.message is None:
        return

    # Назву могли зайняти, поки анкета була відкрита.
    if await repository.get_position_by_name(session, data["position_name"]):
        text, keyboard = await render_positions(session)
        await callback.message.answer(
            f"Посада «{escape(data['position_name'])}» уже є.\n\n{text}",
            reply_markup=keyboard,
        )
        return

    position = await repository.create_position(
        session, name=data["position_name"], self_service=self_service
    )
    text, keyboard = await render_positions(session)
    await callback.message.answer(
        f"✅ Посаду «{escape(position.position)}» додано — "
        f"{_access_note(position)}.\n\n{text}",
        reply_markup=keyboard,
    )


def _access_note(position) -> str:
    return (
        "її можна обрати при реєстрації"
        if position.self_service
        else "її призначає лише адміністратор"
    )


@router.callback_query(F.data.startswith(f"{POSITION_CARD_PREFIX}:"))
async def on_position_card(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    if await _deny(callback, access):
        return
    raw_id = (callback.data or "").rsplit(":", 1)[-1]
    position = (
        await repository.get_position(session, int(raw_id)) if raw_id.isdigit() else None
    )
    if position is None:
        await callback.answer("Посаду не знайдено", show_alert=True)
        return

    await state.clear()
    await callback.answer()
    if callback.message is not None:
        employees = await repository.count_position_employees(session, position.id)
        await callback.message.answer(
            f"<b>{escape(position.position)}</b>\n\n"
            f"<b>Доступ:</b> {_access_note(position)}\n"
            f"<b>Співробітників на посаді:</b> {employees}\n\n"
            "<i>Роль доступу від посади не залежить — її призначає головний "
            "адміністратор у картці співробітника.</i>",
            reply_markup=position_card_keyboard(position.id, position.self_service),
        )


@router.callback_query(F.data.startswith(f"{POSITION_SET_ACCESS_PREFIX}:"))
async def on_position_set_access(
    callback: CallbackQuery, session: AsyncSession, access: Access
) -> None:
    if await _deny(callback, access):
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 4 or not parts[2].isdigit():
        await callback.answer("Невідома посада", show_alert=True)
        return

    position = await repository.get_position(session, int(parts[2]))
    if position is None:
        await callback.answer("Посаду не знайдено", show_alert=True)
        return

    position = await repository.set_position_self_service(
        session, position, parts[3] == "1"
    )
    await callback.answer("Збережено")
    if callback.message is not None:
        text, keyboard = await render_positions(session)
        await callback.message.answer(
            f"✅ Посада «{escape(position.position)}» — {_access_note(position)}."
            f"\n\n{text}",
            reply_markup=keyboard,
        )


@router.message(EmployeeEdit.fullname)
@router.message(EmployeeEdit.phone)
@router.message(EmployeeEdit.phone2)
@router.message(PositionForm.name)
async def non_text(message: Message) -> None:
    await message.answer(
        "Надішліть, будь ласка, текст.", reply_markup=cancel_keyboard()
    )
