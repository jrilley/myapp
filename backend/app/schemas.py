from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import ApplicationStatus


class ApplicationPublic(BaseModel):
    """Схема для публічного сайту.

    `contact` віддається публічно — це свідоме рішення замовника: заявка без
    способу зв'язатися з автором на сайті марна. Бот попереджає користувача
    про це на кроці анкети й перед підтвердженням (див. bot/handlers/form.py),
    щоб контакт залишався усвідомлено.

    Внутрішні поля (`telegram_user_id`, `group_*`, `deleted_at`) сюди НЕ
    входять: вони не потрібні сайту й дають зайву інформацію про механіку
    публікації. Вони лишаються в ApplicationAdmin.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    contact: str
    category: str
    description: str
    status: ApplicationStatus
    created_at: datetime


class ApplicationAdmin(ApplicationPublic):
    """Повна схема — лише для запитів з валідним X-Admin-Token."""

    telegram_user_id: int
    telegram_username: str | None
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
