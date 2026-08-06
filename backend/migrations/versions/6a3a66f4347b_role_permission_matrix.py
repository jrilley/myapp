"""role permission matrix

Revision ID: 6a3a66f4347b
Revises: 52b42532acfc
Create Date: 2026-08-06 12:03:31.975746

Права перестають бути перевіркою назви ролі в коді й стають матрицею
роль × розділ × CRED.

Ролей стає сім: додаються Менеджер, Логіст, Оператор, Диспетчер. Роль
«Користувач» більше не видається — усіх, хто на ній, переводимо на «Водій»
(рівний за правами набір, який ця людина фактично й мала).

Значення записані літералами, а не імпортовані з app.*: міграція фіксує стан
на момент її створення, і подальше перейменування константи в коді не має
змінювати те, що вона робить.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '6a3a66f4347b'
down_revision: Union[str, None] = '52b42532acfc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MAIN_ADMIN = "Головний адміністратор"
COMPANY_ADMIN = "Адміністратор компанії"
MANAGER = "Менеджер"
LOGIST = "Логіст"
OPERATOR = "Оператор"
DISPATCHER = "Диспетчер"
DRIVER = "Водій"
USER = "Користувач"

NEW_ROLES = [MANAGER, LOGIST, OPERATOR, DISPATCHER]

#: роль → розділ → (C, R, E, D, scope, поля для E)
MATRIX: dict[str, dict[str, tuple]] = {
    MAIN_ADMIN: {
        "company": (1, 1, 1, 1, "all", None),
        "employees": (1, 1, 1, 1, "all", None),
        "vehicles": (1, 1, 1, 1, "all", None),
        "trips": (1, 1, 1, 1, "all", None),
    },
    COMPANY_ADMIN: {
        "company": (0, 1, 1, 0, "company", None),
        "employees": (0, 1, 1, 0, "company", None),
        "vehicles": (1, 1, 1, 1, "company", None),
        "trips": (1, 1, 1, 1, "company", None),
    },
    MANAGER: {
        "company": (0, 1, 0, 0, "company", None),
        "employees": (0, 1, 0, 0, "company", None),
        "trips": (1, 1, 1, 1, "company", None),
    },
    LOGIST: {
        "company": (0, 1, 0, 0, "company", None),
        "employees": (0, 1, 0, 0, "company", None),
        "vehicles": (1, 1, 1, 0, "company", None),
        "trips": (1, 1, 1, 1, "company", None),
    },
    # Оператор на вагах: у рейсі йому належать лише маси.
    OPERATOR: {
        "company": (0, 1, 0, 0, "company", None),
        "trips": (0, 1, 1, 0, "company", "bmass,tmass,nmass"),
    },
    # Диспетчер веде рейс по стадіях — і більше нічого не міняє.
    DISPATCHER: {
        "company": (0, 1, 0, 0, "company", None),
        "trips": (0, 1, 1, 0, "company", "status"),
    },
    DRIVER: {
        "trips": (0, 1, 0, 0, "own", None),
    },
}

roles = sa.table("roles", sa.column("id", sa.Integer), sa.column("role", sa.Text))
employees = sa.table(
    "employees", sa.column("id", sa.Integer), sa.column("role_id", sa.Integer)
)
permissions = sa.table(
    "role_permissions",
    sa.column("id", sa.Integer),
    sa.column("role_id", sa.Integer),
    sa.column("category", sa.Text),
    sa.column("can_create", sa.Boolean),
    sa.column("can_read", sa.Boolean),
    sa.column("can_edit", sa.Boolean),
    sa.column("can_delete", sa.Boolean),
    sa.column("scope", sa.Text),
    sa.column("fields", sa.Text),
)


def _role_ids(conn) -> dict[str, int]:
    return {row.role: row.id for row in conn.execute(sa.select(roles.c.id, roles.c.role))}


def upgrade() -> None:
    conn = op.get_bind()

    op.create_table(
        "role_permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("can_create", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("can_read", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("can_edit", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("can_delete", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("scope", sa.Text(), server_default="company", nullable=False),
        sa.Column("fields", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "role_id", "category", name="uq_role_permissions_role_category"
        ),
    )

    existing = _role_ids(conn)
    missing = [name for name in NEW_ROLES if name not in existing]
    if missing:
        op.bulk_insert(roles, [{"role": name} for name in missing])

    ids = _role_ids(conn)
    rows = []
    for role_name, categories in MATRIX.items():
        role_id = ids.get(role_name)
        if role_id is None:
            raise RuntimeError(f"У довіднику roles немає «{role_name}»")
        for category, (c, r, e, d, scope, fields) in categories.items():
            rows.append(
                {
                    "role_id": role_id,
                    "category": category,
                    "can_create": bool(c),
                    "can_read": bool(r),
                    "can_edit": bool(e),
                    "can_delete": bool(d),
                    "scope": scope,
                    "fields": fields,
                }
            )
    op.bulk_insert(permissions, rows)

    # «Користувач» більше не видається. Прав вона не давала, тож переводимо
    # на «Водій» — рівний набір, який ці люди фактично й мали. Саму роль
    # лишаємо в довіднику: видалення розірвало б історію, а користі нуль.
    user_role, driver_role = ids.get(USER), ids.get(DRIVER)
    if user_role is not None and driver_role is not None:
        conn.execute(
            employees.update()
            .where(employees.c.role_id == user_role)
            .values(role_id=driver_role)
        )


def downgrade() -> None:
    # Ролі співробітників назад не розкручуємо: хто був «Користувачем» до
    # міграції, ніде не записано, а вгадувати гірше, ніж не чіпати.
    op.drop_table("role_permissions")
