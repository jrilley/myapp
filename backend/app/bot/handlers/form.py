from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app import repository
from app.bot.constants import (
    CATEGORIES,
    MAX_CONTACT,
    MAX_DESCRIPTION,
    MAX_FULL_NAME,
    MIN_DESCRIPTION,
)
from app.bot.formatting import format_summary
from app.bot.keyboards import (
    CATEGORY_PREFIX,
    CONFIRM_NO,
    CONFIRM_YES,
    categories_keyboard,
    confirm_keyboard,
)
from app.bot.publisher import Publisher
from app.bot.states import ApplicationForm

router = Router(name="form")


@router.message(Command("new"))
async def cmd_new(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(ApplicationForm.full_name)
    await message.answer("Як вас звати? (ПІБ)")


@router.message(ApplicationForm.full_name, F.text)
async def step_full_name(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not 2 <= len(value) <= MAX_FULL_NAME:
        # Лишаємось у тому самому стані — попередні відповіді не втрачаються.
        await message.answer(
            f"Ім'я має бути від 2 до {MAX_FULL_NAME} символів. Спробуйте ще раз."
        )
        return
    await state.update_data(full_name=value)
    await state.set_state(ApplicationForm.contact)
    await message.answer("Залиште контакт для зв'язку (телефон, email або @username).")


@router.message(ApplicationForm.contact, F.text)
async def step_contact(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not 3 <= len(value) <= MAX_CONTACT:
        await message.answer(
            f"Контакт має бути від 3 до {MAX_CONTACT} символів. Спробуйте ще раз."
        )
        return
    await state.update_data(contact=value)
    await state.set_state(ApplicationForm.category)
    await message.answer("Оберіть категорію:", reply_markup=categories_keyboard())


@router.callback_query(ApplicationForm.category, F.data.startswith(f"{CATEGORY_PREFIX}:"))
async def step_category(callback: CallbackQuery, state: FSMContext) -> None:
    raw_index = (callback.data or "").split(":", 1)[1]
    try:
        category = CATEGORIES[int(raw_index)]
    except (ValueError, IndexError):
        await callback.answer("Невідома категорія", show_alert=True)
        return

    await state.update_data(category=category)
    await state.set_state(ApplicationForm.description)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            f"Категорія: {category}.\nТепер опишіть суть заявки "
            f"({MIN_DESCRIPTION}–{MAX_DESCRIPTION} символів)."
        )


@router.message(ApplicationForm.category)
async def step_category_wrong_input(message: Message) -> None:
    await message.answer(
        "Оберіть категорію кнопкою нижче.", reply_markup=categories_keyboard()
    )


@router.message(ApplicationForm.description, F.text)
async def step_description(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not MIN_DESCRIPTION <= len(value) <= MAX_DESCRIPTION:
        await message.answer(
            f"Опис має бути від {MIN_DESCRIPTION} до {MAX_DESCRIPTION} символів. "
            "Спробуйте ще раз."
        )
        return
    await state.update_data(description=value)
    await state.set_state(ApplicationForm.confirm)
    data = await state.get_data()
    await message.answer(
        f"{format_summary(data)}\n\n"
        "<i>Заявку буде опубліковано. Контакт бачать лише адміністратори.</i>",
        reply_markup=confirm_keyboard(),
    )


@router.callback_query(ApplicationForm.confirm, F.data == CONFIRM_YES)
async def step_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    publisher: Publisher,
) -> None:
    data = await state.get_data()
    await state.clear()
    await callback.answer()

    user = callback.from_user
    application = await repository.create_application(
        session,
        telegram_user_id=user.id,
        telegram_username=user.username,
        full_name=data["full_name"],
        contact=data["contact"],
        category=data["category"],
        description=data["description"],
    )

    published = await publisher.publish(application)
    if published is not None:
        chat_id, message_id = published
        await repository.set_group_message(
            session, application, chat_id=chat_id, message_id=message_id
        )

    if callback.message is not None:
        await callback.message.answer(
            f"✅ Заявку #{application.id} прийнято. /my — переглянути свої заявки."
        )


@router.callback_query(ApplicationForm.confirm, F.data == CONFIRM_NO)
async def step_reject(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer("Заявку не надіслано. /new — почати спочатку.")


@router.message(ApplicationForm.full_name)
@router.message(ApplicationForm.contact)
@router.message(ApplicationForm.description)
async def step_non_text(message: Message) -> None:
    await message.answer("Надішліть, будь ласка, текст.")
