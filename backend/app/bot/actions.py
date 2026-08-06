"""Дії та списки, які викликаються з кількох місць.

Тримаємо їх окремо з двох причин: /delete і кнопка «🗑» мають виконувати
однакову перевірку прав, а всі списки — однаково гортатись, тож пагінація
живе в одному місці, а не копіюється по хендлерах.
"""

from html import escape

from aiogram.types import InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app import repository
from app.bot.access import (
    CATEGORY_TITLES,
    CATEGORY_TRIPS,
    ROLE_MAIN_ADMIN,
    SCOPE_ALL,
    SCOPE_COMPANY,
    SCOPE_OWN,
    Access,
)
from app.bot.formatting import (
    format_admin_application,
    format_own_application,
    format_trip_row,
)
from app.bot.keyboards import (
    COMPANY_CARD_PREFIX,
    COMPANY_VEHICLES_PREFIX,
    MENU_BACK,
    PAGE_APPLICATIONS,
    PAGE_EMPLOYEES,
    PAGE_REFERENCE,
    PAGE_TRIPS,
    VEHICLE_TITLES,
    applications_keyboard,
    back_to_menu_keyboard,
    companies_list_keyboard,
    employees_keyboard,
    positions_keyboard,
    trips_keyboard,
    vehicle_list_keyboard,
)
from app.bot.publisher import Publisher
from app.models import ApplicationStatus

Rendered = tuple[str, InlineKeyboardMarkup]

#: Як підписати обсяг права в переліку ролей.
SCOPE_NOTES = {
    SCOPE_ALL: " (усі компанії)",
    SCOPE_COMPANY: " (своя компанія)",
    SCOPE_OWN: " (лише свої)",
}


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

    # Головний адмін може видалити будь-яку заявку, решта — лише власну.
    is_owner = application.telegram_user_id == access.telegram_user_id
    if not (is_owner or access.is_main_admin):
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
    return (
        # Посада каже, ким людина працює; що їй дозволено — окреме питання,
        # і відповідає на нього роль. Зв'язок між ними прибрано навмисно:
        # підвищення прав має лишатись свідомою дією, а не наслідком того,
        # що комусь поміняли підпис у довіднику.
        f"{header}\nПосада — це підпис, а не права: їх дає роль. "
        f"Оберіть, щоб змінити:",
        positions_keyboard(positions, offset=offset, total=total),
    )


async def render_roles(session: AsyncSession) -> Rendered:
    """Матриця прав як вона є в базі — щоб її можна було перевірити, не
    відкриваючи міграцію."""
    roles = await repository.list_roles(session)
    lines = ["<b>Ролі й права</b>", ""]
    for role in roles:
        permissions = await repository.list_role_permissions(session, role.id)
        lines.append(f"<b>{escape(role.role)}</b>")
        if role.role == ROLE_MAIN_ADMIN:
            lines.append("  усе, в усіх компаніях")
        elif not permissions:
            lines.append("  без доступу")
        else:
            for row in sorted(permissions, key=lambda r: r.category):
                rights = "".join(
                    letter
                    for letter, on in (
                        ("C", row.can_create),
                        ("R", row.can_read),
                        ("E", row.can_edit),
                        ("D", row.can_delete),
                    )
                    if on
                )
                title = CATEGORY_TITLES.get(row.category, row.category)
                note = SCOPE_NOTES.get(row.scope, "")
                fields = f" · лише {escape(row.fields)}" if row.fields else ""
                lines.append(f"  {title}: {rights}{note}{fields}")
        lines.append("")
    lines.append("<i>Права змінюються міграцією, не з бота.</i>")
    return "\n".join(lines), back_to_menu_keyboard()


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


NOT_REGISTERED = "Спершу зареєструйтесь — рейс веде співробітник компанії."


async def render_trips(
    session: AsyncSession, access: Access, *, offset: int = 0
) -> Rendered:
    """Список рейсів у межах, доступних викликачу.

    Обсяг видимого визначає роль, а не callback_data: головний адмін бачить
    усі рейси, адміністратор компанії — рейси своєї компанії, решта — власні.
    Фільтр обчислюється тут, бо `repository.list_trips` трактує None як
    «без обмеження» — передати туди невизначений id означало б показати все.
    """
    scope = access.scope(CATEGORY_TRIPS)
    if access.is_main_admin or scope == SCOPE_ALL:
        trips, total = await repository.list_trips(
            session, limit=PAGE_TRIPS, offset=offset
        )
        title = "Усі рейси"
    elif access.employee is None:
        return NOT_REGISTERED, back_to_menu_keyboard()
    elif scope == SCOPE_COMPANY:
        if access.employee.company_id is None:
            return "Не вдалося визначити вашу компанію.", back_to_menu_keyboard()
        trips, total = await repository.list_trips(
            session,
            company_id=access.employee.company_id,
            limit=PAGE_TRIPS,
            offset=offset,
        )
        title = "Рейси компанії"
    else:
        if access.employee.id is None:
            return NOT_REGISTERED, back_to_menu_keyboard()
        # Свої — це і створені, і ті, де людина водій: рейс їй видали, і
        # побачити його вона має так само, як той, що завела сама.
        trips, total = await repository.list_trips(
            session, participant_id=access.employee.id, limit=PAGE_TRIPS, offset=offset
        )
        title = "Мої рейси"

    if not trips:
        return "Рейсів поки немає.", trips_keyboard([])

    header = f"<b>{title}</b> — {_range_note(offset, len(trips), total)}"
    body = "\n\n".join(format_trip_row(trip) for trip in trips)
    return f"{header}\n\n{body}", trips_keyboard(trips, offset=offset, total=total)


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
