from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import ApplicationStatus


class ApplicationPublic(BaseModel):
    """Схема для публічного сайту.

    Свідомо БЕЗ `contact` і `telegram_user_id`: анкета містить особистий
    контакт людини, і віддавати його у відкритий API означало б віддати
    телефони в пошукові індекси. Повні дані — лише через /api/admin/*.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    category: str
    description: str
    status: ApplicationStatus
    created_at: datetime


class ApplicationAdmin(ApplicationPublic):
    """Повна схема — лише для запитів з валідним X-Admin-Token."""

    telegram_user_id: int
    telegram_username: str | None
    contact: str
    group_chat_id: int | None
    group_message_id: int | None
    updated_at: datetime
    deleted_at: datetime | None


class _PageMeta(BaseModel):
    total: int
    limit: int
    offset: int


class ApplicationListPublic(_PageMeta):
    items: list[ApplicationPublic]


class ApplicationListAdmin(_PageMeta):
    # Окремий тип, а не Union: pydantic звів би список адмінських записів
    # до публічної схеми й мовчки обрізав поля.
    items: list[ApplicationAdmin]
