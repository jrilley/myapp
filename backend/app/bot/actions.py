"""Дії та списки, які викликаються з кількох місць.

Тримаємо їх окремо з двох причин: /delete і кнопка «🗑» мають виконувати
однакову перевірку прав, а всі списки — однаково гортатись, тож пагінація
живе в одному місці, а не копіюється по хендлерах.
"""

from html import escape

from aiogram.types import InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app import repository
from app.bot.access import Access
from app.bot.formatting import format_admin_application, format_own_application
from app.bot.keyboards import (
    COMPANY_CARD_PREFIX,
    COMPANY_VEHICLES_PREFIX,
    MENU_BACK,
    PAGE_APPLICATIONS,
    PAGE_EMPLOYEES,
    PAGE_REFERENCE,
    VEHICLE_TITLES,
    applications_keyboard,
    back_to_menu_keyboard,
    companies_list_keyboard,
    employees_keyboard,
    positions_keyboard,
    vehicle_list_keyboard,
)
from app.bot.publisher import Publisher
from app.models import ApplicationStatus

Rendered = tuple[str, InlineKeyboardMarkup]


async def delete_application(
    session: AsyncSession,
    publisher: Publisher,
    access: Access,
    *,
    application_id: int,
) -> tuple[bool, str]:
    """Повертає (чи вдалося, текст відповіді користувачу)."""
    application = await repository.get_application(session, application_id)
    if application is None:
        return False, f"Заявку #{application_id} не знайдено."

    # Адмін може видалити будь-яку заявку, звичайний користувач — лише власну.
    is_owner = application.telegram_user_id == access.telegram_user_id
    if not (is_owner or access.is_admin):
        return False, "Ви можете видаляти лише власні заявки."

    chat_id = application.group_chat_id
    message_id = application.group_message_id

    await repository.soft_delete_application(session, application)

    if chat_id is not None and message_id is not None:
        # Best-effort: збій прибирання в групі не має скасовувати видалення в БД.
        await publisher.retract(chat_id, message_id)

    return True, f"🗑 Заявку #{application_id} видалено."


def _range_note(offset: int, shown: int, total: int) -> str:
    if total <= shown and offset == 0:
        return f"{total}"
    return f"{offset + 1}–{offset + shown} з {total}"


async def render_own_applications(
    session: AsyncSession, telegram_user_id: int, *, offset: int = 0
) -> Rendered:
    applications, total = await repository.list_user_applications(
        session, telegram_user_id, limit=PAGE_APPLICATIONS, offset=offset
    )
    if not applications:
        return "У вас поки немає заявок.", back_to_menu_keyboard()

    header = f"<b>Ваші заявки</b> — {_range_note(offset, len(applications), total)}"
    body = "\n\n".join(format_own_application(a) for a in applications)
    return f"{header}\n\n{body}", applications_keyboard(
        applications, kind="my", offset=offset, total=total
    )


async def render_all_applications(
    session: AsyncSession, *, offset: int = 0
) -> Rendered:
    """Адмінський список: заявки всіх користувачів, найновіші зверху."""
    applications, total = await repository.list_applications(
        session, limit=PAGE_APPLICATIONS, offset=offset
    )
    if not applications:
        return "Заявок поки немає.", back_to_menu_keyboard()

    header = f"<b>Усі заявки</b> — {_range_note(offset, len(applications), total)}"
    body = "\n\n".join(format_admin_application(a) for a in applications)
    return f"{header}\n\n{body}", applications_keyboard(
        applications, kind="all", offset=offset, total=total
    )


def company_back(company_id: int, *, is_main_admin: bool) -> str:
    """Куди веде «Назад» зі списків усередині компанії.

    Головний адмін прийшов через картку компанії, адміністратор компанії —
    прямо з меню, і картки компанії в нього немає.
    """
    return f"{COMPANY_CARD_PREFIX}:{company_id}" if is_main_admin else MENU_BACK


async def render_company_employees(
    session: AsyncSession,
    company_id: int,
    *,
    offset: int = 0,
    is_main_admin: bool = False,
) -> Rendered:
    employees, total = await repository.list_company_employees(
        session, company_id, limit=PAGE_EMPLOYEES, offset=offset
    )
    back = company_back(company_id, is_main_admin=is_main_admin)
    if not employees:
        return (
            "У цій компанії ще немає зареєстрованих працівників.",
            employees_keyboard([], company_id=company_id, back=back),
        )

    header = f"<b>Працівники</b> — {_range_note(offset, len(employees), total)}"
    return f"{header}\nОберіть, щоб переглянути:", employees_keyboard(
        employees, company_id=company_id, offset=offset, total=total, back=back
    )


async def render_company_vehicles(
    session: AsyncSession,
    kind: str,
    company_id: int,
    *,
    offset: int = 0,
    is_main_admin: bool = False,
) -> Rendered | None:
    """None — якщо тип транспорту невідомий."""
    if repository.vehicle_model(kind) is None:
        return None

    vehicles, total = await repository.list_company_vehicles(
        session, kind, company_id, limit=PAGE_REFERENCE, offset=offset
    )
    back = f"{COMPANY_VEHICLES_PREFIX}:{company_id}"
    title = VEHICLE_TITLES[kind]
    if not vehicles:
        return (
            f"{title}: у цій компанії ще немає жодного запису.",
            vehicle_list_keyboard(
                [], kind, company_id, offset=0, total=0, back=back
            ),
        )

    header = f"<b>{title}</b> — {_range_note(offset, len(vehicles), total)}"
    return header, vehicle_list_keyboard(
        vehicles, kind, company_id, offset=offset, total=total, back=back
    )


async def render_positions(session: AsyncSession, *, offset: int = 0) -> Rendered:
    positions, total = await repository.page_positions(
        session, limit=PAGE_REFERENCE, offset=offset
    )
    if not positions:
        return "Довідник посад порожній.", positions_keyboard()

    header = f"<b>Посади</b> — {_range_note(offset, len(positions), total)}"
    body = "\n".join(f"#{p.id} — {escape(p.position)}" for p in positions)
    return f"{header}\n\n{body}", positions_keyboard(offset=offset, total=total)


async def render_companies(session: AsyncSession, *, offset: int = 0) -> Rendered:
    companies, total = await repository.page_companies(
        session, limit=PAGE_REFERENCE, offset=offset
    )
    if not companies:
        return (
            "Компаній ще немає. Без них ніхто не зможе зареєструватись.",
            companies_list_keyboard([]),
        )

    header = f"<b>Компанії</b> — {_range_note(offset, len(companies), total)}"
    return f"{header}\nОберіть компанію:", companies_list_keyboard(
        companies, offset=offset, total=total
    )


async def render_stats(session: AsyncSession) -> Rendered:
    """Адмінська статистика по статусах."""
    counts = await repository.count_by_status(session)
    live = counts[ApplicationStatus.published] + counts[ApplicationStatus.pending]

    lines = [
        "<b>Статистика</b>",
        "",
        f"Активних: <b>{live}</b>",
        f"  опубліковано: {counts[ApplicationStatus.published]}",
        f"  очікують модерації: {counts[ApplicationStatus.pending]}",
        "",
        f"Видалених: {counts[ApplicationStatus.deleted]}",
        f"Відхилених: {counts[ApplicationStatus.rejected]}",
        "",
        f"Усього рядків у базі: {sum(counts.values())}",
    ]
    return "\n".join(lines), back_to_menu_keyboard()
