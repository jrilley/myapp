from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import repository
from app.api.deps import get_publisher, require_admin_token
from app.bot.publisher import Publisher
from app.db import get_db
from app.models import ApplicationStatus
from app.schemas import ApplicationListAdmin, ApplicationListPublic, ApplicationPublic

router = APIRouter(prefix="/api", tags=["applications"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/applications", response_model=ApplicationListPublic)
async def list_applications(
    status_filter: ApplicationStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> ApplicationListPublic:
    items, total = await repository.list_applications(
        session, status=status_filter, limit=limit, offset=offset
    )
    return ApplicationListPublic(
        items=[ApplicationPublic.model_validate(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/applications/{application_id}", response_model=ApplicationPublic)
async def get_application(
    application_id: int, session: AsyncSession = Depends(get_db)
) -> ApplicationPublic:
    application = await repository.get_application(session, application_id)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Не знайдено")
    return ApplicationPublic.model_validate(application)


@router.get(
    "/admin/applications",
    response_model=ApplicationListAdmin,
    dependencies=[Depends(require_admin_token)],
)
async def list_applications_admin(
    status_filter: ApplicationStatus | None = Query(default=None, alias="status"),
    include_deleted: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> ApplicationListAdmin:
    items, total = await repository.list_applications(
        session,
        status=status_filter,
        limit=limit,
        offset=offset,
        include_deleted=include_deleted,
    )
    return ApplicationListAdmin(
        items=[i for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete(
    "/applications/{application_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin_token)],
)
async def delete_application(
    application_id: int,
    session: AsyncSession = Depends(get_db),
    publisher: Publisher = Depends(get_publisher),
) -> Response:
    application = await repository.get_application(session, application_id)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Не знайдено")

    chat_id = application.group_chat_id
    message_id = application.group_message_id

    await repository.soft_delete_application(session, application)

    if chat_id is not None and message_id is not None:
        # Best-effort: збій у Telegram не має скасовувати видалення в БД.
        await publisher.retract(chat_id, message_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
