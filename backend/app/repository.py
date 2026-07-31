"""Єдиний шар доступу до БД — використовується і ботом, і API.

Навмисно без сирого SQL і без SQLite-специфіки, щоб перехід на PostgreSQL
зводився до зміни DATABASE_URL.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Application,
    ApplicationStatus,
    Company,
    Employee,
    Position,
    Role,
)


async def create_application(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    telegram_username: str | None,
    full_name: str,
    contact: str,
    category: str,
    description: str,
    status: ApplicationStatus = ApplicationStatus.published,
) -> Application:
    application = Application(
        telegram_user_id=telegram_user_id,
        telegram_username=telegram_username,
        full_name=full_name,
        contact=contact,
        category=category,
        description=description,
        status=status,
    )
    session.add(application)
    await session.commit()
    await session.refresh(application)
    return application


async def get_application(
    session: AsyncSession, application_id: int, *, include_deleted: bool = False
) -> Application | None:
    stmt = select(Application).where(Application.id == application_id)
    if not include_deleted:
        stmt = stmt.where(Application.deleted_at.is_(None))
    return await session.scalar(stmt)


async def list_applications(
    session: AsyncSession,
    *,
    status: ApplicationStatus | None = None,
    limit: int = 20,
    offset: int = 0,
    include_deleted: bool = False,
) -> tuple[list[Application], int]:
    """Повертає (сторінку записів, загальну кількість під ті самі фільтри)."""
    filters = []
    if not include_deleted:
        filters.append(Application.deleted_at.is_(None))
    if status is not None:
        filters.append(Application.status == status)

    total = await session.scalar(
        select(func.count()).select_from(Application).where(*filters)
    )

    stmt = (
        select(Application)
        .where(*filters)
        .order_by(Application.created_at.desc(), Application.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list(await session.scalars(stmt))
    return items, int(total or 0)


async def list_user_applications(
    session: AsyncSession, telegram_user_id: int, *, limit: int = 10
) -> list[Application]:
    stmt = (
        select(Application)
        .where(
            Application.telegram_user_id == telegram_user_id,
            Application.deleted_at.is_(None),
        )
        .order_by(Application.created_at.desc(), Application.id.desc())
        .limit(limit)
    )
    return list(await session.scalars(stmt))


async def count_by_status(session: AsyncSession) -> dict[ApplicationStatus, int]:
    """Скільки заявок у кожному статусі, включно з видаленими."""
    stmt = select(Application.status, func.count()).group_by(Application.status)
    rows = await session.execute(stmt)
    counts = {status: 0 for status in ApplicationStatus}
    for status, total in rows:
        counts[status] = int(total)
    return counts


async def set_group_message(
    session: AsyncSession, application: Application, *, chat_id: int, message_id: int
) -> Application:
    application.group_chat_id = chat_id
    application.group_message_id = message_id
    await session.commit()
    await session.refresh(application)
    return application


async def soft_delete_application(
    session: AsyncSession, application: Application
) -> Application:
    application.deleted_at = datetime.now(timezone.utc)
    application.status = ApplicationStatus.deleted
    await session.commit()
    await session.refresh(application)
    return application


# ---------------------------------------------------------------------------
# Співробітники, компанії та довідники
# ---------------------------------------------------------------------------


async def get_employee_by_tg_id(
    session: AsyncSession, telegram_user_id: int
) -> Employee | None:
    """Роль і компанію тягнемо одразу: в async-сесії ліниве завантаження
    кидає MissingGreenlet, а викликачам майже завжди потрібна роль."""
    stmt = (
        select(Employee)
        .where(Employee.tg_id == telegram_user_id)
        .options(
            selectinload(Employee.role),
            selectinload(Employee.company),
            selectinload(Employee.position),
        )
    )
    return await session.scalar(stmt)


async def create_employee(
    session: AsyncSession,
    *,
    tg_id: int,
    company_id: int,
    fullname: str,
    phone_number: str,
    position_id: int,
    role_id: int,
) -> Employee:
    employee = Employee(
        tg_id=tg_id,
        company_id=company_id,
        fullname=fullname,
        phone_number=phone_number,
        position_id=position_id,
        role_id=role_id,
    )
    session.add(employee)
    await session.commit()
    await session.refresh(employee)
    return employee


async def count_employees(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(Employee)) or 0)


async def list_companies(session: AsyncSession) -> list[Company]:
    return list(await session.scalars(select(Company).order_by(Company.name)))


async def get_company(session: AsyncSession, company_id: int) -> Company | None:
    return await session.get(Company, company_id)


async def get_company_by_tax_id(session: AsyncSession, tax_id: str) -> Company | None:
    return await session.scalar(select(Company).where(Company.tax_id == tax_id))


async def create_company(
    session: AsyncSession, *, name: str, tax_id: str, address: str
) -> Company:
    company = Company(name=name, tax_id=tax_id, address=address)
    session.add(company)
    await session.commit()
    await session.refresh(company)
    return company


async def list_positions(session: AsyncSession) -> list[Position]:
    return list(await session.scalars(select(Position).order_by(Position.id)))


async def get_role_by_name(session: AsyncSession, name: str) -> Role | None:
    return await session.scalar(select(Role).where(Role.role == name))
