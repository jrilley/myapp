"""Тести матриці прав.

Матриця живе у двох місцях: `app/permissions.py` (звідки її читають тести й
код) і міграція 6a3a66f4347b (звідки вона потрапляє в базу). Копії в
міграціях — норма, вони фіксують стан на момент створення. Ненормально —
коли копії розходяться мовчки, тож перший тест звіряє їх.
"""

import importlib.util
from pathlib import Path

import pytest

from app.bot.access import (
    CATEGORY_COMPANY,
    CATEGORY_EMPLOYEES,
    CATEGORY_TRIPS,
    CATEGORY_VEHICLES,
    CREATE,
    DELETE,
    EDIT,
    READ,
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
)
from app.permissions import DEFAULT_MATRIX
from tests.conftest import make_access

MIGRATION = (
    Path(__file__).resolve().parent.parent
    / "migrations"
    / "versions"
    / "6a3a66f4347b_role_permission_matrix.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("_perm_migration", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_code_and_migration_agree():
    """Розійдуться — і в базі буде одна матриця, а в тестах інша."""
    assert _load_migration().MATRIX == DEFAULT_MATRIX


# ---------------------------------------------------------------------------
# Хто що може
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "category", "right", "expected"),
    [
        # Адміністратор компанії: компанія й люди — читання й правка;
        # транспорт і рейси — повністю.
        (ROLE_COMPANY_ADMIN, CATEGORY_COMPANY, EDIT, True),
        (ROLE_COMPANY_ADMIN, CATEGORY_COMPANY, CREATE, False),
        (ROLE_COMPANY_ADMIN, CATEGORY_EMPLOYEES, EDIT, True),
        (ROLE_COMPANY_ADMIN, CATEGORY_VEHICLES, DELETE, True),
        (ROLE_COMPANY_ADMIN, CATEGORY_TRIPS, DELETE, True),
        # Менеджер веде рейси, але транспорту не бачить.
        (ROLE_MANAGER, CATEGORY_TRIPS, CREATE, True),
        (ROLE_MANAGER, CATEGORY_VEHICLES, READ, False),
        (ROLE_MANAGER, CATEGORY_EMPLOYEES, EDIT, False),
        # Логіст — єдиний, крім адміна компанії, хто заводить машини,
        # але видаляти їх не може.
        (ROLE_LOGIST, CATEGORY_VEHICLES, CREATE, True),
        (ROLE_LOGIST, CATEGORY_VEHICLES, DELETE, False),
        # Оператор і диспетчер правлять рейси, але не створюють і не видаляють.
        (ROLE_OPERATOR, CATEGORY_TRIPS, EDIT, True),
        (ROLE_OPERATOR, CATEGORY_TRIPS, CREATE, False),
        (ROLE_OPERATOR, CATEGORY_TRIPS, DELETE, False),
        (ROLE_DISPATCHER, CATEGORY_TRIPS, EDIT, True),
        (ROLE_DISPATCHER, CATEGORY_EMPLOYEES, READ, False),
        # Водій лише читає рейси.
        (ROLE_DRIVER, CATEGORY_TRIPS, READ, True),
        (ROLE_DRIVER, CATEGORY_TRIPS, EDIT, False),
        (ROLE_DRIVER, CATEGORY_COMPANY, READ, False),
    ],
)
def test_matrix(role, category, right, expected):
    assert make_access(role=role).can(category, right) is expected


def test_main_admin_can_everything():
    """Головний адмін не залежить від рядків у таблиці: його права —
    окремий об'єкт, щоб їх не могла зняти ні міграція, ні описка."""
    access = make_access(role=ROLE_MAIN_ADMIN)
    for category in (
        CATEGORY_COMPANY,
        CATEGORY_EMPLOYEES,
        CATEGORY_VEHICLES,
        CATEGORY_TRIPS,
    ):
        for right in (CREATE, READ, EDIT, DELETE):
            assert access.can(category, right)


def test_bootstrap_admin_has_full_rights_without_a_row():
    """Аварійний вхід: рядка в employees ще немає, а компанію хтось має
    завести — інакше зареєструватись неможливо нікому."""
    access = make_access(registered=False, bootstrap_admin=True)

    assert access.can(CATEGORY_COMPANY, CREATE)
    assert access.is_main_admin


def test_unknown_role_gets_nothing():
    """Роль без рядків у матриці не отримує нічого — не «усе»."""
    access = make_access(role="Вигадана роль")

    assert not access.can(CATEGORY_TRIPS, READ)
    assert not access.can(CATEGORY_COMPANY, READ)


# ---------------------------------------------------------------------------
# Обсяг
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (ROLE_MAIN_ADMIN, SCOPE_ALL),
        (ROLE_COMPANY_ADMIN, SCOPE_COMPANY),
        (ROLE_LOGIST, SCOPE_COMPANY),
        (ROLE_DRIVER, SCOPE_OWN),
    ],
)
def test_trip_scope(role, expected):
    assert make_access(role=role).scope(CATEGORY_TRIPS) == expected


# ---------------------------------------------------------------------------
# Права на рівні поля
# ---------------------------------------------------------------------------


def test_operator_edits_only_masses():
    """У оператора є E на рейсах — але лише на масах. Право саме по собі
    ще не означає, що можна чіпати все."""
    access = make_access(role=ROLE_OPERATOR)

    assert access.may_edit_field(CATEGORY_TRIPS, "bmass")
    assert access.may_edit_field(CATEGORY_TRIPS, "nmass")
    assert not access.may_edit_field(CATEGORY_TRIPS, "status")
    assert not access.may_edit_field(CATEGORY_TRIPS, "ttn")


def test_dispatcher_edits_only_status():
    access = make_access(role=ROLE_DISPATCHER)

    assert access.may_edit_field(CATEGORY_TRIPS, "status")
    assert not access.may_edit_field(CATEGORY_TRIPS, "bmass")


def test_unrestricted_role_edits_every_field():
    access = make_access(role=ROLE_LOGIST)

    assert access.editable_fields(CATEGORY_TRIPS) is None
    assert access.may_edit_field(CATEGORY_TRIPS, "ttn")


def test_no_edit_right_means_no_field():
    """Водій не редагує нічого, тож жодне поле йому не належить."""
    access = make_access(role=ROLE_DRIVER)

    assert not access.may_edit_field(CATEGORY_TRIPS, "status")
