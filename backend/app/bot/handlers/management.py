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
from app.bot.access import Access
from app.bot.actions import render_employees, render_positions
from app.bot.constants import MAX_FULLNAME, MAX_PHONE, MAX_POSITION, MIN_PHONE
from app.bot.keyboards import (
    EMP_EDIT_PREFIX,
    EMP_SET_PREFIX,
    EMP_VIEW_PREFIX,
    MENU_EMPLOYEES,
    MENU_POSITIONS,
    POSITION_ADD,
    cancel_keyboard,
    employee_card_keyboard,
    employee_choice_keyboard,
)
from app.bot.states import EmployeeEdit, PositionForm
from app.models import Employee

router = Router(name="management")

DENIED = "Дія доступна лише головному адміністратору."

# Поле картки → (назва в БД, підпис, як дістати варіанти)
CHOICE_FIELDS = {
    "company": ("company_id", "компанію"),
    "position": ("position_id", "посаду"),
    "role": ("role_id", "роль"),
}


async def _deny(callback: CallbackQuery, access: Access) -> bool:
    if access.is_main_admin:
        return False
    await callback.answer(DENIED, show_alert=True)
    return True


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


async def _show_card(message, session: AsyncSession, employee_id: int) -> None:
    employee = await repository.get_employee(session, employee_id)
    if employee is None:
        await message.answer("Співробітника не знайдено.")
        return
    await message.answer(_card(employee), reply_markup=employee_card_keyboard(employee.id))


# ---------------------------------------------------------------------------
# Користувачі
# ---------------------------------------------------------------------------


@router.callback_query(F.data == MENU_EMPLOYEES)
async def on_employees(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    if await _deny(callback, access):
        return
    await state.clear()
    await callback.answer()
    if callback.message is None:
        return

    text, keyboard = await render_employees(session)
    await callback.message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith(f"{EMP_VIEW_PREFIX}:"))
async def on_employee_card(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    if await _deny(callback, access):
        return
    raw_id = (callback.data or "").split(":", 1)[1]
    if not raw_id.isdigit():
        await callback.answer("Невідомий співробітник", show_alert=True)
        return
    await state.clear()
    await callback.answer()
    if callback.message is not None:
        await _show_card(callback.message, session, int(raw_id))


@router.callback_query(F.data.startswith(f"{EMP_EDIT_PREFIX}:"))
async def on_employee_edit(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    if await _deny(callback, access):
        return

    parts = (callback.data or "").split(":")
    if len(parts) != 3 or not parts[2].isdigit():
        await callback.answer("Невідоме поле", show_alert=True)
        return
    _, field, raw_id = parts
    employee_id = int(raw_id)

    employee = await repository.get_employee(session, employee_id)
    if employee is None:
        await callback.answer("Співробітника не знайдено", show_alert=True)
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
                reply_markup=employee_card_keyboard(employee_id),
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
    if await _deny(callback, access):
        return

    parts = (callback.data or "").split(":")
    if len(parts) != 4 or not parts[2].isdigit() or not parts[3].isdigit():
        await callback.answer("Невідоме значення", show_alert=True)
        return
    _, field, raw_employee, raw_value = parts

    if field not in CHOICE_FIELDS:
        await callback.answer("Невідоме поле", show_alert=True)
        return

    employee = await repository.get_employee(session, int(raw_employee))
    if employee is None:
        await callback.answer("Співробітника не знайдено", show_alert=True)
        return

    if field == "role" and employee.tg_id == access.telegram_user_id:
        await callback.answer(
            "Не можна змінити власну роль.", show_alert=True
        )
        return

    column, _ = CHOICE_FIELDS[field]
    await repository.update_employee(session, employee, **{column: int(raw_value)})
    await callback.answer("Збережено")
    if callback.message is not None:
        await _show_card(callback.message, session, employee.id)


@router.message(EmployeeEdit.fullname, F.text)
async def edit_fullname(
    message: Message, state: FSMContext, session: AsyncSession
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
    await _show_card(message, session, employee.id)


@router.message(EmployeeEdit.phone, F.text)
async def edit_phone(
    message: Message, state: FSMContext, session: AsyncSession
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
    await _show_card(message, session, employee.id)


@router.message(EmployeeEdit.phone2, F.text)
async def edit_phone2(
    message: Message, state: FSMContext, session: AsyncSession
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
    await _show_card(message, session, employee.id)


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

    await state.clear()
    position = await repository.create_position(session, name=value)
    text, keyboard = await render_positions(session)
    await message.answer(
        f"✅ Посаду «{escape(position.position)}» додано.\n\n{text}",
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
