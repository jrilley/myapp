"""Довідник транспорту: тягачі й причепи в одній таблиці.

Доступно адміністраторам. Різниця між ролями лише в тому, звідки береться
компанія: головний обирає її зі списку, адміністратору компанії вона
береться з його власного запису в employees — інакше він міг би завести
машину чужій компанії.

«Тягач чи причіп» окремим питанням не стоїть: це видно з виду транспорту,
а вид потрібен і сам по собі — при виборі причепа в рейсі він підставляється
замість того, щоб набирати «зерновоз» удесяте.
"""

from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app import repository
from app.bot.access import (
    CATEGORY_VEHICLES,
    CREATE,
    DELETE,
    DENIED,
    EDIT,
    READ,
    Access,
    resolve_company_id,
)
from app.bot.guards import deny
from app.bot.actions import render_company_vehicles
from app.bot.constants import (
    MAX_LICENSE_PLATE,
    MAX_VEHICLE_MAKE_MODEL,
    MIN_LICENSE_PLATE,
)
from app.bot.handlers.common import menu_for
from app.bot.keyboards import (
    COMPANY_CARD_PREFIX,
    COMPANY_VEHICLES_PREFIX,
    MENU_BACK,
    MENU_MY_VEHICLES,
    MENU_VEHICLE_ADD,
    VEHICLE_CARD_PREFIX,
    VEHICLE_COMPANY_PREFIX,
    VEHICLE_MARK_ADD,
    VEHICLE_MARK_PREFIX,
    VEHICLE_CONFIRM,
    VEHICLE_DELETE_CONFIRM,
    VEHICLE_DELETE_PREFIX,
    VEHICLE_EDIT_PREFIX,
    VEHICLE_LIST_PREFIX,
    cancel_keyboard,
    vehicle_card_keyboard,
    vehicle_company_keyboard,
    vehicle_confirm_keyboard,
    vehicle_delete_confirm_keyboard,
    vehicle_kind_keyboard,
    vehicle_mark_keyboard,
    vehicle_type_keyboard,
)
from app.bot.states import VehicleEdit, VehicleForm
from app.models import Vehicle

router = Router(name="vehicles")


def _ref_id(callback_data: str | None) -> int | None:
    """Останній сегмент callback_data як id довідника, або None."""
    raw = (callback_data or "").rsplit(":", 1)[-1]
    return int(raw) if raw.isdigit() else None


def _kind_of(vehicle: Vehicle) -> str:
    """До якої половини списку належить машина — щоб знати, куди повертати."""
    return "truck" if vehicle.is_tractor else "trailer"


@router.callback_query(F.data == MENU_VEHICLE_ADD)
async def on_add_vehicle(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    if await deny(callback, access, CATEGORY_VEHICLES, CREATE):
        return
    await state.clear()
    await state.set_state(VehicleForm.type)
    await callback.answer()
    if callback.message is None:
        return

    types = await repository.list_vehicle_types(session)
    if not types:
        await state.clear()
        await callback.message.answer(
            "Довідник видів транспорту порожній. Зверніться до головного "
            "адміністратора.",
            reply_markup=menu_for(access),
        )
        return
    await callback.message.answer(
        "Який транспорт додаємо?", reply_markup=vehicle_type_keyboard(types)
    )


@router.callback_query(VehicleForm.type, F.data.startswith("veh:type:"))
async def step_type(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    if await deny(callback, access, CATEGORY_VEHICLES, CREATE):
        return
    type_id = _ref_id(callback.data)
    vehicle_type = (
        await repository.get_vehicle_type(session, type_id)
        if type_id is not None
        else None
    )
    if vehicle_type is None:
        await callback.answer("Невідомий вид", show_alert=True)
        return

    await state.update_data(type_id=vehicle_type.id)
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

    await state.update_data(owner_company_id=company_id)
    await _ask_mark(callback.message, state, session)


async def _ask_mark(message: Message, state: FSMContext, session: AsyncSession) -> None:
    await state.set_state(VehicleForm.mark)
    marks = await repository.list_vehicle_marks(session)
    await message.answer(
        "Марка й модель:" if marks else "Довідник марок порожній — додайте першу.",
        reply_markup=vehicle_mark_keyboard(marks),
    )


async def _ask_plate(message: Message, state: FSMContext) -> None:
    await state.set_state(VehicleForm.license_plate)
    await message.answer("Державний номер:", reply_markup=cancel_keyboard())


@router.callback_query(VehicleForm.mark, F.data == VEHICLE_MARK_ADD)
async def step_mark_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(VehicleForm.mark_name)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Марка й модель (наприклад «Volvo FH16»):",
            reply_markup=cancel_keyboard(),
        )


@router.callback_query(VehicleForm.mark, F.data.startswith(f"{VEHICLE_MARK_PREFIX}:"))
async def step_mark_pick(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    mark_id = _ref_id(callback.data)
    mark = (
        await repository.get_vehicle_mark(session, mark_id)
        if mark_id is not None
        else None
    )
    if mark is None:
        await callback.answer("Невідома марка", show_alert=True)
        return
    await state.update_data(mark_id=mark.id)
    await callback.answer()
    if callback.message is not None:
        await _ask_plate(callback.message, state)


@router.message(VehicleForm.mark_name, F.text)
async def step_mark_name(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    """Нова марка потрапляє в довідник одразу: інакше той, хто заводить
    машину, упирався б у список і чекав на адміністратора."""
    value = (message.text or "").strip()
    if not 1 <= len(value) <= MAX_VEHICLE_MAKE_MODEL:
        await message.answer(
            f"Марка й модель — від 1 до {MAX_VEHICLE_MAKE_MODEL} символів.",
            reply_markup=cancel_keyboard(),
        )
        return

    # Назва унікальна, тож наявну беремо як є, а не падаємо помилкою БД.
    mark = await repository.get_vehicle_mark_by_name(session, value)
    if mark is None:
        mark = await repository.create_vehicle_mark(session, name=value)
    await state.update_data(mark_id=mark.id)
    await _ask_plate(message, state)


@router.callback_query(
    VehicleForm.company, F.data.startswith(f"{VEHICLE_COMPANY_PREFIX}:")
)
async def step_company(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    if await deny(callback, access, CATEGORY_VEHICLES, CREATE):
        return
    raw_id = (callback.data or "").rsplit(":", 1)[-1]
    company = (
        await repository.get_company(session, int(raw_id)) if raw_id.isdigit() else None
    )
    if company is None:
        await callback.answer("Невідома компанія", show_alert=True)
        return

    await state.update_data(owner_company_id=company.id, company_name=company.name)
    await callback.answer()
    if callback.message is not None:
        await _ask_mark(callback.message, state, session)


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

    # Номер унікальний — ловимо тут, а не помилкою БД після підтвердження.
    if await repository.get_vehicle_by_plate(session, value):
        await message.answer(
            "Транспорт із таким номером уже є. Введіть інший.",
            reply_markup=cancel_keyboard(),
        )
        return

    await state.update_data(license_plate=value)
    await state.set_state(VehicleForm.confirm)

    data = await state.get_data()
    company = await repository.get_company(session, data["owner_company_id"])
    company_name = company.name if company else "—"
    # Назви беремо з довідників, а не з даних форми: у стані лежать самі id.
    # Дублювати туди ще й назви означало б тримати дві правди про один рядок —
    # і падати на екрані підтвердження, якщо стан лишився від старої версії.
    vehicle_type = await repository.get_vehicle_type(session, data["type_id"])
    mark = await repository.get_vehicle_mark(session, data["mark_id"])
    await message.answer(
        "<b>Перевірте дані:</b>\n\n"
        f"<b>Вид:</b> {escape(vehicle_type.name if vehicle_type else '—')}\n"
        f"<b>Марка й модель:</b> {escape(mark.name if mark else '—')}\n"
        f"<b>Номер:</b> {escape(value)}\n"
        f"<b>Власник:</b> {escape(company_name)}",
        reply_markup=vehicle_confirm_keyboard(),
    )


@router.callback_query(VehicleForm.confirm, F.data == VEHICLE_CONFIRM)
async def step_confirm(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    if await deny(callback, access, CATEGORY_VEHICLES, CREATE):
        return
    data = await state.get_data()
    await state.clear()
    await callback.answer()
    if callback.message is None:
        return

    # Номер могли зайняти, поки анкета була відкрита.
    if await repository.get_vehicle_by_plate(session, data["license_plate"]):
        await callback.message.answer(
            f"Транспорт із номером {escape(data['license_plate'])} уже є. "
            "Спробуйте додати ще раз з іншим номером.",
            reply_markup=menu_for(access),
        )
        return

    vehicle = await repository.create_vehicle(
        session,
        type_id=data["type_id"],
        mark_id=data["mark_id"],
        license_plate=data["license_plate"],
        owner_company_id=data["owner_company_id"],
    )
    await callback.message.answer(
        f"✅ {escape(vehicle.type_name)} {escape(vehicle.make_model)} "
        f"({escape(vehicle.license_plate)}) додано під #{vehicle.id}.",
        reply_markup=menu_for(access),
    )


# ---------------------------------------------------------------------------
# Перегляд і редагування
# ---------------------------------------------------------------------------


def _card(vehicle: Vehicle) -> str:
    company = vehicle.owner_company.name if vehicle.owner_company else "—"
    return (
        f"<b>{escape(vehicle.type_name)}</b>\n\n"
        f"<b>Марка й модель:</b> {escape(vehicle.make_model)}\n"
        f"<b>Номер:</b> {escape(vehicle.license_plate)}\n"
        f"<b>Власник:</b> {escape(company)}"
    )


async def _show_card(
    message: Message, session: AsyncSession, vehicle_id: int, access: Access
) -> None:
    vehicle = await repository.get_vehicle(session, vehicle_id)
    if vehicle is None:
        await message.answer("Транспорт не знайдено.")
        return
    back = (
        f"{VEHICLE_LIST_PREFIX}:{_kind_of(vehicle)}:{vehicle.owner_company_id}:0"
    )
    await message.answer(
        _card(vehicle), reply_markup=vehicle_card_keyboard(vehicle.id, back, access)
    )


@router.callback_query(F.data.startswith(f"{COMPANY_VEHICLES_PREFIX}:"))
async def on_company_vehicles(
    callback: CallbackQuery, state: FSMContext, access: Access
) -> None:
    """Вибір тягачі/причепи для конкретної компанії."""
    if await deny(callback, access, CATEGORY_VEHICLES):
        return
    company_id = resolve_company_id(access, (callback.data or "").split(":", 1)[1])
    if company_id is None:
        await callback.answer(DENIED, show_alert=True)
        return
    await state.clear()
    await callback.answer()
    if callback.message is not None:
        back = (
            f"{COMPANY_CARD_PREFIX}:{company_id}" if access.is_main_admin else MENU_BACK
        )
        await callback.message.answer(
            "Що показати?",
            reply_markup=vehicle_kind_keyboard(company_id, back=back),
        )


@router.callback_query(F.data == MENU_MY_VEHICLES)
async def on_my_vehicles(
    callback: CallbackQuery, state: FSMContext, access: Access
) -> None:
    """Транспорт власної компанії — без кроку вибору компанії."""
    if await deny(callback, access, CATEGORY_VEHICLES):
        return
    company_id = resolve_company_id(access, None)
    if company_id is None:
        await callback.answer(DENIED, show_alert=True)
        return
    await state.clear()
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Що показати?",
            reply_markup=vehicle_kind_keyboard(company_id, back=MENU_BACK),
        )


@router.callback_query(F.data.startswith(f"{VEHICLE_LIST_PREFIX}:"))
async def on_vehicle_list(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 4 or not parts[3].isdigit():
        await callback.answer("Невідомий список", show_alert=True)
        return
    _, kind, raw_company, raw_offset = parts

    if await deny(callback, access, CATEGORY_VEHICLES):
        return
    company_id = resolve_company_id(access, raw_company)
    if company_id is None:
        await callback.answer(DENIED, show_alert=True)
        return

    rendered = await render_company_vehicles(
        session, kind, company_id, offset=int(raw_offset),
        is_main_admin=access.is_main_admin,
    )
    if rendered is None:
        await callback.answer("Невідомий тип", show_alert=True)
        return

    await state.clear()
    await callback.answer()
    if callback.message is not None:
        text, keyboard = rendered
        await callback.message.answer(text, reply_markup=keyboard)


async def _vehicle_or_denied(
    callback: CallbackQuery,
    session: AsyncSession,
    access: Access,
    vehicle_id: int,
    right: str = READ,
) -> Vehicle | None:
    if await deny(callback, access, CATEGORY_VEHICLES, right):
        return None
    vehicle = await repository.get_vehicle(session, vehicle_id)
    if vehicle is None:
        await callback.answer("Транспорт не знайдено", show_alert=True)
        return None
    # Чужу машину не відкрити навіть за прямим id.
    if not access.is_main_admin and vehicle.owner_company_id != resolve_company_id(
        access, None
    ):
        await callback.answer(DENIED, show_alert=True)
        return None
    return vehicle


def _one_id(callback_data: str | None) -> int | None:
    """«<префікс>:<id>» → id, або None."""
    parts = (callback_data or "").split(":")
    if len(parts) != 2 or not parts[1].isdigit():
        return None
    return int(parts[1])


@router.callback_query(F.data.startswith(f"{VEHICLE_CARD_PREFIX}:"))
async def on_vehicle_card(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    vehicle_id = _one_id(callback.data)
    if vehicle_id is None:
        await callback.answer("Невідомий транспорт", show_alert=True)
        return

    vehicle = await _vehicle_or_denied(callback, session, access, vehicle_id)
    if vehicle is None:
        return

    await state.clear()
    await callback.answer()
    if callback.message is not None:
        await _show_card(callback.message, session, vehicle.id, access)


@router.callback_query(F.data.startswith(f"{VEHICLE_EDIT_PREFIX}:"))
async def on_vehicle_edit(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    parts = (callback.data or "").split(":")
    if len(parts) != 3 or not parts[2].isdigit():
        await callback.answer("Невідоме поле", show_alert=True)
        return
    _, field, raw_id = parts

    if field not in ("type", "makemodel", "plate"):
        await callback.answer("Невідоме поле", show_alert=True)
        return

    vehicle = await _vehicle_or_denied(callback, session, access, int(raw_id), EDIT)
    if vehicle is None:
        return

    await state.update_data(vehicle_id=vehicle.id)
    await callback.answer()
    if callback.message is None:
        return

    if field == "type":
        await state.set_state(VehicleEdit.type)
        await callback.message.answer(
            "Новий вид:",
            reply_markup=vehicle_type_keyboard(
                await repository.list_vehicle_types(session)
            ),
        )
        return
    if field == "makemodel":
        await _ask_mark(callback.message, state, session)
        await state.set_state(VehicleEdit.mark)
        return

    await state.set_state(VehicleEdit.license_plate)
    await callback.message.answer(
        "Новий державний номер:", reply_markup=cancel_keyboard()
    )


@router.callback_query(VehicleEdit.type, F.data.startswith("veh:type:"))
async def edit_type(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    type_id = _ref_id(callback.data)
    vehicle_type = (
        await repository.get_vehicle_type(session, type_id)
        if type_id is not None
        else None
    )
    if vehicle_type is None:
        await callback.answer("Невідомий вид", show_alert=True)
        return
    await callback.answer()
    if callback.message is not None:
        await _apply_edit(
            callback.message, state, session, access, type_id=vehicle_type.id
        )


@router.callback_query(VehicleEdit.mark, F.data == VEHICLE_MARK_ADD)
async def edit_mark_add(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(VehicleEdit.mark_name)
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Марка й модель:", reply_markup=cancel_keyboard()
        )


@router.callback_query(VehicleEdit.mark, F.data.startswith(f"{VEHICLE_MARK_PREFIX}:"))
async def edit_mark_pick(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    mark_id = _ref_id(callback.data)
    mark = (
        await repository.get_vehicle_mark(session, mark_id)
        if mark_id is not None
        else None
    )
    if mark is None:
        await callback.answer("Невідома марка", show_alert=True)
        return
    await callback.answer()
    if callback.message is not None:
        await _apply_edit(callback.message, state, session, access, mark_id=mark.id)


@router.message(VehicleEdit.mark_name, F.text)
async def edit_mark_name(
    message: Message, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    value = (message.text or "").strip()
    if not 1 <= len(value) <= MAX_VEHICLE_MAKE_MODEL:
        await message.answer(
            f"Марка й модель — від 1 до {MAX_VEHICLE_MAKE_MODEL} символів.",
            reply_markup=cancel_keyboard(),
        )
        return
    mark = await repository.get_vehicle_mark_by_name(session, value)
    if mark is None:
        mark = await repository.create_vehicle_mark(session, name=value)
    await _apply_edit(message, state, session, access, mark_id=mark.id)


@router.message(VehicleEdit.license_plate, F.text)
async def edit_plate(
    message: Message, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    value = (message.text or "").strip().upper()
    if not MIN_LICENSE_PLATE <= len(value) <= MAX_LICENSE_PLATE:
        await message.answer(
            f"Номер має бути від {MIN_LICENSE_PLATE} до {MAX_LICENSE_PLATE} символів.",
            reply_markup=cancel_keyboard(),
        )
        return

    data = await state.get_data()
    existing = await repository.get_vehicle_by_plate(session, value)
    if existing is not None and existing.id != data.get("vehicle_id"):
        await message.answer(
            "Транспорт із таким номером уже є. Введіть інший.",
            reply_markup=cancel_keyboard(),
        )
        return
    await _apply_edit(message, state, session, access, license_plate=value)


async def _apply_edit(
    message: Message, state: FSMContext, session: AsyncSession, access: Access, **fields
) -> None:
    data = await state.get_data()
    await state.clear()
    if not access.can(CATEGORY_VEHICLES, EDIT):
        await message.answer(DENIED)
        return
    vehicle = await repository.get_vehicle(session, data.get("vehicle_id", 0))
    if vehicle is None:
        await message.answer("Транспорт не знайдено.")
        return
    await repository.update_vehicle(session, vehicle, **fields)
    await _show_card(message, session, vehicle.id, access)


@router.callback_query(F.data.startswith(f"{VEHICLE_DELETE_PREFIX}:"))
async def on_vehicle_delete(
    callback: CallbackQuery, session: AsyncSession, access: Access
) -> None:
    """Питаємо підтвердження: машина зникне зі списків і з вибору в рейсі.

    Сам рядок лишається — на нього посилаються перевезення, і стерти його
    означало б лишити рейс без транспорту.
    """
    vehicle_id = _one_id(callback.data)
    if vehicle_id is None:
        await callback.answer("Невідомий транспорт", show_alert=True)
        return

    vehicle = await _vehicle_or_denied(callback, session, access, vehicle_id, DELETE)
    if vehicle is None:
        return

    await callback.answer()
    if callback.message is None:
        return

    # Скільки перевезень на неї посилаються — щоб рішення ухвалювалось із
    # відкритими очима: рядок лишиться, але зі списків машина зникне.
    used = await repository.count_vehicle_trips(session, vehicle.id)
    note = (
        f"\n\nМашина є в {used} рейс(ах) — вони її й далі показуватимуть."
        if used
        else ""
    )
    await callback.message.answer(
        f"Видалити {escape(vehicle.type_name.lower())} "
        f"{escape(vehicle.make_model)} {escape(vehicle.license_plate)}?{note}",
        reply_markup=vehicle_delete_confirm_keyboard(
            vehicle.id, f"{VEHICLE_CARD_PREFIX}:{vehicle.id}"
        ),
    )


@router.callback_query(F.data.startswith(f"{VEHICLE_DELETE_CONFIRM}:"))
async def on_vehicle_delete_confirm(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, access: Access
) -> None:
    vehicle_id = _one_id(callback.data)
    if vehicle_id is None:
        await callback.answer("Невідомий транспорт", show_alert=True)
        return

    vehicle = await _vehicle_or_denied(callback, session, access, vehicle_id, DELETE)
    if vehicle is None:
        return

    company_id = vehicle.owner_company_id
    kind = _kind_of(vehicle)
    label = f"{vehicle.make_model} {vehicle.license_plate}"

    await repository.delete_vehicle(session, vehicle)
    await callback.answer(f"🗑 {label} видалено")

    await state.clear()
    if callback.message is not None:
        rendered = await render_company_vehicles(
            session, kind, company_id, is_main_admin=access.is_main_admin
        )
        if rendered is not None:
            text, keyboard = rendered
            await callback.message.answer(text, reply_markup=keyboard)


@router.message(VehicleForm.mark_name)
@router.message(VehicleForm.license_plate)
@router.message(VehicleEdit.mark_name)
@router.message(VehicleEdit.license_plate)
async def non_text(message: Message) -> None:
    await message.answer(
        "Надішліть, будь ласка, текст.", reply_markup=cancel_keyboard()
    )
