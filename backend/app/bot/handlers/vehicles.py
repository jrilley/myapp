"""Додавання тягачів і причепів.

Доступно адміністраторам. Різниця між ролями лише в тому, звідки береться
компанія: головний обирає її зі списку, адміністратору компанії вона
береться з його власного запису в employees — інакше він міг би завести
машину чужій компанії.
"""

from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app import repository
from app.bot.access import Access
from app.bot.constants import (
    MAX_LICENSE_PLATE,
    MAX_VEHICLE_BRAND,
    MAX_VEHICLE_MODEL,
    MIN_LICENSE_PLATE,
)
from app.bot.handlers.common import menu_for
from app.bot.keyboards import (
    MENU_VEHICLE_ADD,
    VEHICLE_COMPANY_PREFIX,
    VEHICLE_CONFIRM,
    VEHICLE_TITLES,
    VEHICLE_TYPE_PREFIX,
    cancel_keyboard,
    vehicle_company_keyboard,
    vehicle_confirm_keyboard,
    vehicle_type_keyboard,
)
from app.bot.states import VehicleForm

router = Router(name="vehicles")

DENIED = "Дія доступна лише адміністраторам."


async def _deny(callback: CallbackQuery, access: Access) -> bool:
    if access.is_admin:
        return False
    await callback.answer(DENIED, show_alert=True)
    return True


@router.callback_query(F.data == MENU_VEHICLE_ADD)
async def on_add_vehicle(
    callback: CallbackQuery, state: FSMContext, access: Access
) -> None:
    if await _deny(callback, access):
        return
    await state.clear()
    await state.set_state(VehicleForm.kind)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Що додаємо?", reply_markup=vehicle_type_keyboard()
        )


@router.callback_query(VehicleForm.kind, F.data.startswith(f"{VEHICLE_TYPE_PREFIX}:"))
async def step_kind(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    if await _deny(callback, access):
        return
    kind = (callback.data or "").rsplit(":", 1)[-1]
    if repository.vehicle_model(kind) is None:
        await callback.answer("Невідомий тип", show_alert=True)
        return

    await state.update_data(kind=kind)
    await callback.answer()
    if callback.message is None:
        return

    # Головний адмін обирає компанію; адміністратору компанії вона відома.
    if access.is_main_admin:
        companies = await repository.list_companies(session)
        if not companies:
            await state.clear()
            await callback.message.answer(
                "Спершу потрібно завести хоча б одну компанію.",
                reply_markup=menu_for(access),
            )
            return
        await state.set_state(VehicleForm.company)
        await callback.message.answer(
            "Оберіть компанію:", reply_markup=vehicle_company_keyboard(companies)
        )
        return

    company_id = access.employee.company_id if access.employee else None
    if company_id is None:
        await state.clear()
        await callback.message.answer(
            "Не вдалося визначити вашу компанію. Зверніться до головного "
            "адміністратора.",
            reply_markup=menu_for(access),
        )
        return

    await state.update_data(company_id=company_id)
    await _ask_brand(callback.message, state)


async def _ask_brand(message: Message, state: FSMContext) -> None:
    await state.set_state(VehicleForm.brand)
    await message.answer("Марка:", reply_markup=cancel_keyboard())


@router.callback_query(
    VehicleForm.company, F.data.startswith(f"{VEHICLE_COMPANY_PREFIX}:")
)
async def step_company(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    if await _deny(callback, access):
        return
    raw_id = (callback.data or "").rsplit(":", 1)[-1]
    company = (
        await repository.get_company(session, int(raw_id)) if raw_id.isdigit() else None
    )
    if company is None:
        await callback.answer("Невідома компанія", show_alert=True)
        return

    await state.update_data(company_id=company.id, company_name=company.name)
    await callback.answer()
    if callback.message is not None:
        await _ask_brand(callback.message, state)


@router.message(VehicleForm.brand, F.text)
async def step_brand(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not 1 <= len(value) <= MAX_VEHICLE_BRAND:
        await message.answer(
            f"Марка має бути від 1 до {MAX_VEHICLE_BRAND} символів.",
            reply_markup=cancel_keyboard(),
        )
        return
    await state.update_data(brand=value)
    await state.set_state(VehicleForm.model)
    await message.answer("Модель:", reply_markup=cancel_keyboard())


@router.message(VehicleForm.model, F.text)
async def step_model(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not 1 <= len(value) <= MAX_VEHICLE_MODEL:
        await message.answer(
            f"Модель має бути від 1 до {MAX_VEHICLE_MODEL} символів.",
            reply_markup=cancel_keyboard(),
        )
        return
    await state.update_data(model=value)
    await state.set_state(VehicleForm.license_plate)
    await message.answer("Державний номер:", reply_markup=cancel_keyboard())


@router.message(VehicleForm.license_plate, F.text)
async def step_license_plate(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    value = (message.text or "").strip().upper()
    if not MIN_LICENSE_PLATE <= len(value) <= MAX_LICENSE_PLATE:
        await message.answer(
            f"Номер має бути від {MIN_LICENSE_PLATE} до {MAX_LICENSE_PLATE} символів.",
            reply_markup=cancel_keyboard(),
        )
        return

    data = await state.get_data()
    # Номер унікальний — ловимо тут, а не помилкою БД після підтвердження.
    if await repository.get_vehicle_by_plate(session, data["kind"], value):
        await message.answer(
            "Транспорт із таким номером уже є. Введіть інший.",
            reply_markup=cancel_keyboard(),
        )
        return

    await state.update_data(license_plate=value)
    await state.set_state(VehicleForm.confirm)

    company = await repository.get_company(session, data["company_id"])
    company_name = company.name if company else "—"
    await message.answer(
        "<b>Перевірте дані:</b>\n\n"
        f"<b>Тип:</b> {VEHICLE_TITLES[data['kind']]}\n"
        f"<b>Марка:</b> {escape(data['brand'])}\n"
        f"<b>Модель:</b> {escape(data['model'])}\n"
        f"<b>Номер:</b> {escape(value)}\n"
        f"<b>Компанія:</b> {escape(company_name)}",
        reply_markup=vehicle_confirm_keyboard(),
    )


@router.callback_query(VehicleForm.confirm, F.data == VEHICLE_CONFIRM)
async def step_confirm(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    if await _deny(callback, access):
        return
    data = await state.get_data()
    await state.clear()
    await callback.answer()
    if callback.message is None:
        return

    # Номер могли зайняти, поки анкета була відкрита.
    if await repository.get_vehicle_by_plate(
        session, data["kind"], data["license_plate"]
    ):
        await callback.message.answer(
            f"Транспорт із номером {escape(data['license_plate'])} уже є. "
            "Спробуйте додати ще раз з іншим номером.",
            reply_markup=menu_for(access),
        )
        return

    vehicle = await repository.create_vehicle(
        session,
        data["kind"],
        brand=data["brand"],
        model=data["model"],
        license_plate=data["license_plate"],
        company_id=data["company_id"],
    )
    await callback.message.answer(
        f"✅ {VEHICLE_TITLES[data['kind']]} {escape(vehicle.brand)} "
        f"{escape(vehicle.model)} ({escape(vehicle.license_plate)}) "
        f"додано під #{vehicle.id}.",
        reply_markup=menu_for(access),
    )


@router.message(VehicleForm.brand)
@router.message(VehicleForm.model)
@router.message(VehicleForm.license_plate)
async def non_text(message: Message) -> None:
    await message.answer(
        "Надішліть, будь ласка, текст.", reply_markup=cancel_keyboard()
    )
