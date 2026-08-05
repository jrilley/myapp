"""Реєстрація співробітника та заведення компаній.

Реєстрація обов'язкова: без рядка в employees заявку подати не можна.
Роль не питається й не задається за замовчуванням — її дає обрана посада
(`positions.role_id`).
"""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession

from app import repository
from app.bot.access import Access
from app.bot.actions import render_companies
from app.bot.constants import (
    MAX_ADDRESS,
    MAX_COMPANY_NAME,
    MAX_FULLNAME,
    MAX_PHONE,
    MAX_TAX_ID,
    MIN_PHONE,
)
from app.bot.keyboards import (
    CANCEL_TEXT,
    COMPANY_ADD,
    MENU_COMPANIES,
    REG_COMPANY_PREFIX,
    REG_CONFIRM,
    REG_PHONE2_NO,
    REG_PHONE2_YES,
    REG_POSITION_PREFIX,
    REG_START,
    cancel_keyboard,
    choices_keyboard,
    main_menu_keyboard,
    phone2_keyboard,
    registration_confirm_keyboard,
    share_phone_keyboard,
)
from app.bot.states import CompanyForm, Registration

router = Router(name="registration")


def _menu(access: Access):
    return main_menu_keyboard(
        is_registered=access.is_registered,
        is_admin=access.is_admin,
        is_main_admin=access.is_main_admin,
    )


# ---------------------------------------------------------------------------
# Реєстрація
# ---------------------------------------------------------------------------


@router.callback_query(F.data == REG_START)
async def on_register(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    access: Access,
) -> None:
    await callback.answer()
    if callback.message is None:
        return

    if access.is_registered:
        await callback.message.answer(
            "Ви вже зареєстровані.", reply_markup=_menu(access)
        )
        return

    # Без жодної компанії реєстрація не має чим завершитись — краще сказати
    # це одразу, ніж провести людину через анкету й впертись у порожній список.
    if not await repository.list_companies(session):
        await callback.message.answer(
            "Реєстрація поки неможлива: у системі ще немає жодної компанії.\n"
            "Зверніться до головного адміністратора.",
            reply_markup=_menu(access),
        )
        return

    await state.clear()
    await state.set_state(Registration.fullname)
    await callback.message.answer(
        "Реєстрація. Як вас звати? (ПІБ)", reply_markup=cancel_keyboard()
    )


@router.message(Registration.fullname, F.text)
async def step_fullname(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not 2 <= len(value) <= MAX_FULLNAME:
        await message.answer(
            f"ПІБ має бути від 2 до {MAX_FULLNAME} символів. Спробуйте ще раз.",
            reply_markup=cancel_keyboard(),
        )
        return
    await state.update_data(fullname=value)
    await state.set_state(Registration.phone)
    await message.answer(
        "Поділіться номером телефону — натисніть кнопку нижче.\n"
        "Можна також ввести номер вручну.",
        reply_markup=share_phone_keyboard(),
    )


async def _ask_about_second_phone(message: Message, state: FSMContext) -> None:
    await state.set_state(Registration.phone2_ask)
    # Reply-клавіатуру треба прибрати явно, інакше кнопка «Поділитися
    # номером» лишиться висіти під полем вводу до кінця анкети.
    await message.answer("Номер збережено.", reply_markup=ReplyKeyboardRemove())
    await message.answer(
        "Чи є у вас додатковий номер?", reply_markup=phone2_keyboard()
    )


@router.message(Registration.phone, F.contact)
async def step_phone_shared(message: Message, state: FSMContext) -> None:
    """Номер, отриманий кнопкою. Telegram дозволяє надіслати й чужий контакт
    (вибравши його зі списку), тому звіряємо, що це справді власний."""
    contact = message.contact
    if contact.user_id != message.from_user.id:
        await message.answer(
            "Це контакт іншої людини. Поділіться, будь ласка, власним номером "
            "або введіть його вручну.",
            reply_markup=share_phone_keyboard(),
        )
        return

    await state.update_data(phone_number=contact.phone_number)
    await _ask_about_second_phone(message, state)


@router.message(Registration.phone, F.text)
async def step_phone(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if value == CANCEL_TEXT:
        await state.clear()
        await message.answer("Реєстрацію скасовано.", reply_markup=ReplyKeyboardRemove())
        return
    if not MIN_PHONE <= len(value) <= MAX_PHONE:
        await message.answer(
            f"Номер має бути від {MIN_PHONE} до {MAX_PHONE} символів. Спробуйте ще раз.",
            reply_markup=share_phone_keyboard(),
        )
        return
    await state.update_data(phone_number=value)
    await _ask_about_second_phone(message, state)


@router.callback_query(Registration.phone2_ask, F.data == REG_PHONE2_YES)
async def step_phone2_yes(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Registration.phone2)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Введіть додатковий номер:", reply_markup=cancel_keyboard()
        )


async def _ask_company(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.set_state(Registration.company)
    companies = await repository.list_companies(session)
    await message.answer(
        "Оберіть компанію:",
        reply_markup=choices_keyboard(
            REG_COMPANY_PREFIX, [(c.id, c.name) for c in companies]
        ),
    )


@router.callback_query(Registration.phone2_ask, F.data == REG_PHONE2_NO)
async def step_phone2_no(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    await callback.answer()
    if callback.message is not None:
        await _ask_company(callback.message, state, session)


@router.message(Registration.phone2, F.text)
async def step_phone2(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    value = (message.text or "").strip()
    if not MIN_PHONE <= len(value) <= MAX_PHONE:
        await message.answer(
            f"Номер має бути від {MIN_PHONE} до {MAX_PHONE} символів. Спробуйте ще раз.",
            reply_markup=cancel_keyboard(),
        )
        return
    await state.update_data(phone_number2=value)
    await _ask_company(message, state, session)


@router.callback_query(Registration.company, F.data.startswith(f"{REG_COMPANY_PREFIX}:"))
async def step_company(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    raw_id = (callback.data or "").rsplit(":", 1)[-1]
    company = (
        await repository.get_company(session, int(raw_id)) if raw_id.isdigit() else None
    )
    if company is None:
        await callback.answer("Невідома компанія", show_alert=True)
        return

    await state.update_data(company_id=company.id, company_name=company.name)
    await state.set_state(Registration.position)
    await callback.answer()

    positions = await repository.list_positions(session)
    if callback.message is not None:
        await callback.message.answer(
            "Оберіть посаду:",
            reply_markup=choices_keyboard(
                REG_POSITION_PREFIX, [(p.id, p.position) for p in positions]
            ),
        )


@router.callback_query(
    Registration.position, F.data.startswith(f"{REG_POSITION_PREFIX}:")
)
async def step_position(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    raw_id = (callback.data or "").rsplit(":", 1)[-1]
    position = (
        await repository.get_position(session, int(raw_id)) if raw_id.isdigit() else None
    )
    if position is None:
        await callback.answer("Невідома посада", show_alert=True)
        return

    await state.update_data(position_id=position.id, position_name=position.position)
    await state.set_state(Registration.confirm)
    await callback.answer()

    data = await state.get_data()
    extra = data.get("phone_number2")
    if callback.message is not None:
        await callback.message.answer(
            "<b>Перевірте дані:</b>\n\n"
            f"<b>ПІБ:</b> {data['fullname']}\n"
            f"<b>Телефон:</b> {data['phone_number']}\n"
            + (f"<b>Додатковий:</b> {extra}\n" if extra else "")
            + f"<b>Компанія:</b> {data['company_name']}\n"
            f"<b>Посада:</b> {data['position_name']}\n"
            f"<b>Роль доступу:</b> {position.role.role}",
            reply_markup=registration_confirm_keyboard(),
        )


@router.callback_query(Registration.confirm, F.data == REG_CONFIRM)
async def step_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    access: Access,
) -> None:
    data = await state.get_data()
    await state.clear()
    await callback.answer()
    if callback.message is None:
        return

    # Могли зареєструватись з іншого пристрою, поки анкета була відкрита:
    # tg_id унікальний, і вставка впала б помилкою БД.
    if await repository.get_employee_by_tg_id(session, callback.from_user.id):
        await callback.message.answer(
            "Ви вже зареєстровані.", reply_markup=_menu(access)
        )
        return

    # Роль дає посада. Перечитуємо посаду замість того, щоб брати роль зі
    # стану: поки анкета була відкрита, головний адмін міг змінити довідник.
    position = await repository.get_position(session, data["position_id"])
    if position is None:
        await callback.message.answer(
            "Обраної посади більше немає в довіднику. Почніть реєстрацію заново.",
            reply_markup=_menu(access),
        )
        return

    employee = await repository.create_employee(
        session,
        tg_id=callback.from_user.id,
        company_id=data["company_id"],
        fullname=data["fullname"],
        phone_number=data["phone_number"],
        phone_number2=data.get("phone_number2"),
        position_id=position.id,
        role_id=position.role_id,
    )

    # Access у data застарів — його порахували до створення рядка.
    fresh = Access(
        telegram_user_id=callback.from_user.id,
        employee=await repository.get_employee_by_tg_id(session, employee.tg_id),
        bootstrap_admin=access.bootstrap_admin,
    )
    await callback.message.answer(
        f"✅ Реєстрацію завершено. Вітаємо, {data['fullname']}!",
        reply_markup=_menu(fresh),
    )


# ---------------------------------------------------------------------------
# Компанії (лише головний адміністратор)
# ---------------------------------------------------------------------------


@router.callback_query(F.data == MENU_COMPANIES)
async def on_companies(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    if not access.is_main_admin:
        await callback.answer(
            "Дія доступна лише головному адміністратору.", show_alert=True
        )
        return
    await state.clear()
    await callback.answer()

    text, keyboard = await render_companies(session)
    if callback.message is not None:
        await callback.message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == COMPANY_ADD)
async def on_company_add(
    callback: CallbackQuery, state: FSMContext, access: Access
) -> None:
    if not access.is_main_admin:
        await callback.answer(
            "Дія доступна лише головному адміністратору.", show_alert=True
        )
        return
    await state.clear()
    await state.set_state(CompanyForm.name)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Назва компанії:", reply_markup=cancel_keyboard()
        )


@router.message(CompanyForm.name, F.text)
async def company_name(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not 2 <= len(value) <= MAX_COMPANY_NAME:
        await message.answer(
            f"Назва має бути від 2 до {MAX_COMPANY_NAME} символів.",
            reply_markup=cancel_keyboard(),
        )
        return
    await state.update_data(name=value)
    await state.set_state(CompanyForm.tax_id)
    await message.answer("Податковий номер (ЄДРПОУ/ІПН):", reply_markup=cancel_keyboard())


@router.message(CompanyForm.tax_id, F.text)
async def company_tax_id(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    value = (message.text or "").strip()
    if not 4 <= len(value) <= MAX_TAX_ID:
        await message.answer(
            f"Номер має бути від 4 до {MAX_TAX_ID} символів.",
            reply_markup=cancel_keyboard(),
        )
        return
    # tax_id унікальний — перевіряємо тут, щоб не впертись у помилку БД
    # після того, як людина введе ще й адресу.
    if await repository.get_company_by_tax_id(session, value):
        await message.answer(
            "Компанія з таким номером уже є. Введіть інший.",
            reply_markup=cancel_keyboard(),
        )
        return
    await state.update_data(tax_id=value)
    await state.set_state(CompanyForm.address)
    await message.answer("Адреса компанії:", reply_markup=cancel_keyboard())


@router.message(CompanyForm.address, F.text)
async def company_address(
    message: Message, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    value = (message.text or "").strip()
    if not 4 <= len(value) <= MAX_ADDRESS:
        await message.answer(
            f"Адреса має бути від 4 до {MAX_ADDRESS} символів.",
            reply_markup=cancel_keyboard(),
        )
        return

    data = await state.get_data()
    await state.clear()
    company = await repository.create_company(
        session, name=data["name"], tax_id=data["tax_id"], address=value
    )
    await message.answer(
        f"✅ Компанію «{company.name}» додано (#{company.id}).",
        reply_markup=_menu(access),
    )


@router.message(Registration.fullname)
@router.message(Registration.phone)
@router.message(CompanyForm.name)
@router.message(CompanyForm.tax_id)
@router.message(CompanyForm.address)
async def non_text(message: Message) -> None:
    await message.answer(
        "Надішліть, будь ласка, текст.", reply_markup=cancel_keyboard()
    )
