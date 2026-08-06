"""Хто цей користувач і що йому дозволено.

Права визначає матриця роль × розділ × CRED у таблиці `role_permissions`.
Один запит на апдейт (AccessMiddleware), далі хендлери питають `access.can(...)`
і не знають ні про назви ролей, ні про SQL.

ADMIN_TELEGRAM_IDS лишається **аварійним входом**: без нього виникає замкнене
коло — поки немає жодного співробітника, немає й адміна, а отже нікому завести
компанію, без якої неможливо зареєструватись.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app import repository
from app.config import Settings

# Назви ролей і розділів оголошені в моделях: на них спираються і сіди
# міграцій, і репозиторій, а імпорт звідти в бік бота був би зворотним.
from app.models import (  # noqa: F401  — реекспорт, на нього спираються хендлери
    CATEGORIES,
    CATEGORY_COMPANY,
    CATEGORY_EMPLOYEES,
    CATEGORY_TITLES,
    CATEGORY_TRIPS,
    CATEGORY_VEHICLES,
    ROLE_COMPANY_ADMIN,
    ROLE_DISPATCHER,
    ROLE_DRIVER,
    ROLE_LOGIST,
    ROLE_MAIN_ADMIN,
    ROLE_MANAGER,
    ROLE_OPERATOR,
    SCOPE_ALL,
    SCOPE_COMPANY,
    SCOPE_OWN,
    Employee,
)

CREATE, READ, EDIT, DELETE = "C", "R", "E", "D"

ADMIN_ONLY = "Дія доступна лише адміністраторам."
MAIN_ADMIN_ONLY = "Дія доступна лише головному адміністратору."
DENIED = "Недостатньо прав для цієї дії."


@dataclass(frozen=True)
class Permission:
    """Права ролі в одному розділі."""

    create: bool = False
    read: bool = False
    edit: bool = False
    delete: bool = False
    scope: str = SCOPE_COMPANY
    #: None — усі поля розділу; інакше лише перелічені.
    fields: frozenset[str] | None = None

    def allows(self, right: str) -> bool:
        return {
            CREATE: self.create,
            READ: self.read,
            EDIT: self.edit,
            DELETE: self.delete,
        }.get(right, False)


#: Головний адміністратор і аварійний вхід. Окремим об'єктом, а не рядками в
#: таблиці, щоб зняти доступ у власника не могла ні міграція, ні описка.
FULL = Permission(
    create=True, read=True, edit=True, delete=True, scope=SCOPE_ALL, fields=None
)
NOTHING = Permission()


def _parse(row) -> Permission:
    raw = (row.fields or "").strip()
    return Permission(
        create=bool(row.can_create),
        read=bool(row.can_read),
        edit=bool(row.can_edit),
        delete=bool(row.can_delete),
        scope=row.scope,
        fields=frozenset(f.strip() for f in raw.split(",") if f.strip()) or None,
    )


@dataclass(frozen=True)
class Access:
    telegram_user_id: int
    employee: Employee | None
    #: True, якщо доступ отриманий через ADMIN_TELEGRAM_IDS, а не через роль.
    bootstrap_admin: bool = False
    #: розділ → права. Порожньо для незареєстрованих.
    permissions: dict[str, Permission] = None  # type: ignore[assignment]

    @property
    def is_registered(self) -> bool:
        return self.employee is not None

    @property
    def role_name(self) -> str | None:
        return self.employee.role.role if self.employee is not None else None

    @property
    def is_main_admin(self) -> bool:
        """Єдина роль, яку ще визначаємо за назвою: вона дає все й скрізь,
        і саме тому не має залежати від рядка в таблиці прав."""
        return self.bootstrap_admin or self.role_name == ROLE_MAIN_ADMIN

    @property
    def fullname(self) -> str | None:
        return self.employee.fullname if self.employee is not None else None

    def permission(self, category: str) -> Permission:
        if self.is_main_admin:
            return FULL
        if not self.permissions:
            return NOTHING
        return self.permissions.get(category, NOTHING)

    def can(self, category: str, right: str = READ) -> bool:
        return self.permission(category).allows(right)

    def scope(self, category: str) -> str:
        return self.permission(category).scope

    def may_edit_field(self, category: str, field: str) -> bool:
        """Чи можна редагувати конкретне поле розділу.

        Оператор має E на рейсах, але лише на масах; диспетчер — лише на
        статусі. Тому саме право E ще не означає, що можна чіпати все.
        """
        permission = self.permission(category)
        if not permission.edit:
            return False
        return permission.fields is None or field in permission.fields

    def editable_fields(self, category: str) -> frozenset[str] | None:
        return self.permission(category).fields


def resolve_company_id(access: Access, requested) -> int | None:
    """Яку компанію цьому користувачу дозволено дивитись.

    Хто має scope=all — будь-яку, вказану в запиті. Решта — **лише свою**,
    незалежно від того, що прийшло в callback_data: інакше достатньо було б
    підмінити id, щоб побачити чужих працівників.
    """
    if access.scope(CATEGORY_COMPANY) == SCOPE_ALL or access.is_main_admin:
        try:
            return int(requested)
        except (TypeError, ValueError):
            return None
    return access.employee.company_id if access.employee else None


async def resolve_access(
    session: AsyncSession, settings: Settings, telegram_user_id: int
) -> Access:
    employee = await repository.get_employee_by_tg_id(session, telegram_user_id)
    permissions: dict[str, Permission] = {}
    if employee is not None:
        permissions = {
            row.category: _parse(row)
            for row in await repository.list_role_permissions(session, employee.role_id)
        }
    return Access(
        telegram_user_id=telegram_user_id,
        employee=employee,
        bootstrap_admin=settings.is_admin(telegram_user_id),
        permissions=permissions,
    )


__all__ = [
    "ADMIN_ONLY",
    "CATEGORIES",
    "CATEGORY_COMPANY",
    "CATEGORY_EMPLOYEES",
    "CATEGORY_TITLES",
    "CATEGORY_TRIPS",
    "CATEGORY_VEHICLES",
    "CREATE",
    "DELETE",
    "DENIED",
    "EDIT",
    "MAIN_ADMIN_ONLY",
    "READ",
    "ROLE_COMPANY_ADMIN",
    "ROLE_DISPATCHER",
    "ROLE_DRIVER",
    "ROLE_LOGIST",
    "ROLE_MAIN_ADMIN",
    "ROLE_MANAGER",
    "ROLE_OPERATOR",
    "SCOPE_ALL",
    "SCOPE_COMPANY",
    "SCOPE_OWN",
    "Access",
    "Permission",
    "resolve_access",
    "resolve_company_id",
]
