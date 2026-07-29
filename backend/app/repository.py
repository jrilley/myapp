"""Єдиний шар доступу до БД — використовується і ботом, і API.

Навмисно без сирого SQL і без SQLite-специфіки, щоб перехід на PostgreSQL
зводився до зміни DATABASE_URL.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Application, ApplicationStatus


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
