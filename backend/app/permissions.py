"""Матриця прав за замовчуванням — роль × розділ × CRED.

Тут вона у вигляді, придатному для читання й для сіду тестової БД. У бойовій
базі права лежать у таблиці `role_permissions`, куди їх кладе міграція
6a3a66f4347b — і та тримає власну копію значень, як усі міграції-сіди.

Щоб копії не розійшлись, є тест, який звіряє цей словник із міграцією
(tests/test_permissions.py). Розійдуться — тест впаде.
"""

from app.models import (
    CATEGORY_COMPANY,
    CATEGORY_EMPLOYEES,
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
    RolePermission,
)

#: роль → розділ → (C, R, E, D, обсяг, поля для E)
DEFAULT_MATRIX: dict[str, dict[str, tuple]] = {
    ROLE_MAIN_ADMIN: {
        CATEGORY_COMPANY: (1, 1, 1, 1, SCOPE_ALL, None),
        CATEGORY_EMPLOYEES: (1, 1, 1, 1, SCOPE_ALL, None),
        CATEGORY_VEHICLES: (1, 1, 1, 1, SCOPE_ALL, None),
        CATEGORY_TRIPS: (1, 1, 1, 1, SCOPE_ALL, None),
    },
    ROLE_COMPANY_ADMIN: {
        CATEGORY_COMPANY: (0, 1, 1, 0, SCOPE_COMPANY, None),
        CATEGORY_EMPLOYEES: (0, 1, 1, 0, SCOPE_COMPANY, None),
        CATEGORY_VEHICLES: (1, 1, 1, 1, SCOPE_COMPANY, None),
        CATEGORY_TRIPS: (1, 1, 1, 1, SCOPE_COMPANY, None),
    },
    ROLE_MANAGER: {
        CATEGORY_COMPANY: (0, 1, 0, 0, SCOPE_COMPANY, None),
        CATEGORY_EMPLOYEES: (0, 1, 0, 0, SCOPE_COMPANY, None),
        CATEGORY_TRIPS: (1, 1, 1, 1, SCOPE_COMPANY, None),
    },
    ROLE_LOGIST: {
        CATEGORY_COMPANY: (0, 1, 0, 0, SCOPE_COMPANY, None),
        CATEGORY_EMPLOYEES: (0, 1, 0, 0, SCOPE_COMPANY, None),
        CATEGORY_VEHICLES: (1, 1, 1, 0, SCOPE_COMPANY, None),
        CATEGORY_TRIPS: (1, 1, 1, 1, SCOPE_COMPANY, None),
    },
    # Оператор на вагах: у рейсі йому належать лише маси.
    ROLE_OPERATOR: {
        CATEGORY_COMPANY: (0, 1, 0, 0, SCOPE_COMPANY, None),
        CATEGORY_TRIPS: (0, 1, 1, 0, SCOPE_COMPANY, "bmass,tmass,nmass"),
    },
    # Диспетчер веде рейс по стадіях — і більше нічого не міняє.
    ROLE_DISPATCHER: {
        CATEGORY_COMPANY: (0, 1, 0, 0, SCOPE_COMPANY, None),
        CATEGORY_TRIPS: (0, 1, 1, 0, SCOPE_COMPANY, "status"),
    },
    ROLE_DRIVER: {
        CATEGORY_TRIPS: (0, 1, 0, 0, SCOPE_OWN, None),
    },
}


def rows_for(role_id: int, role_name: str) -> list[RolePermission]:
    """Рядки `role_permissions` для однієї ролі."""
    return [
        RolePermission(
            role_id=role_id,
            category=category,
            can_create=bool(create),
            can_read=bool(read),
            can_edit=bool(edit),
            can_delete=bool(delete),
            scope=scope,
            fields=fields,
        )
        for category, (create, read, edit, delete, scope, fields) in DEFAULT_MATRIX.get(
            role_name, {}
        ).items()
    ]
