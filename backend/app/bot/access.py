"""Хто цей користувач і що йому дозволено.

Права визначає роль у таблиці employees, а не список у .env.
ADMIN_TELEGRAM_IDS лишається **аварійним входом**: без нього виникає замкнене
коло — поки немає жодного співробітника, немає й адміна, а отже нікому завести
компанію, без якої неможливо зареєструватись.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app import repository
from app.config import Settings

# Назви ролей оголошені в моделях: на них спираються і сіди міграцій, і
# репозиторій, а імпорт звідти в бік бота був би зворотним.
from app.models import (  # noqa: F401  — реекспорт, на нього спираються хендлери
    ROLE_COMPANY_ADMIN,
    ROLE_MAIN_ADMIN,
    ROLE_USER,
    Employee,
)

ADMIN_ROLES = frozenset({ROLE_MAIN_ADMIN, ROLE_COMPANY_ADMIN})

__all__ = [
    "ADMIN_ONLY",
    "ADMIN_ROLES",
    "MAIN_ADMIN_ONLY",
    "ROLE_COMPANY_ADMIN",
    "ROLE_MAIN_ADMIN",
    "ROLE_USER",
    "Access",
    "resolve_access",
    "resolve_company_id",
]


@dataclass(frozen=True)
class Access:
    telegram_user_id: int
    employee: Employee | None
    #: True, якщо доступ отриманий через ADMIN_TELEGRAM_IDS, а не через роль.
    bootstrap_admin: bool = False

    @property
    def is_registered(self) -> bool:
        return self.employee is not None

    @property
    def role_name(self) -> str | None:
        return self.employee.role.role if self.employee is not None else None

    @property
    def is_admin(self) -> bool:
        return self.bootstrap_admin or self.role_name in ADMIN_ROLES

    @property
    def is_main_admin(self) -> bool:
        """Тільки головний адміністратор заводить компанії."""
        return self.bootstrap_admin or self.role_name == ROLE_MAIN_ADMIN

    @property
    def fullname(self) -> str | None:
        return self.employee.fullname if self.employee is not None else None


ADMIN_ONLY = "Дія доступна лише адміністраторам."
MAIN_ADMIN_ONLY = "Дія доступна лише головному адміністратору."


def resolve_company_id(access: Access, requested) -> int | None:
    """Яку компанію цьому користувачу дозволено дивитись.

    Головний адмін — будь-яку, вказану в запиті. Адміністратор компанії —
    **лише свою**, незалежно від того, що прийшло в callback_data: інакше
    достатньо було б підмінити id, щоб побачити чужих працівників.
    """
    if not access.is_admin:
        return None
    if access.is_main_admin:
        try:
            return int(requested)
        except (TypeError, ValueError):
            return None
    return access.employee.company_id if access.employee else None


async def resolve_access(
    session: AsyncSession, settings: Settings, telegram_user_id: int
) -> Access:
    employee = await repository.get_employee_by_tg_id(session, telegram_user_id)
    return Access(
        telegram_user_id=telegram_user_id,
        employee=employee,
        bootstrap_admin=settings.is_admin(telegram_user_id),
    )
