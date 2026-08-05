"""positions grant roles

Revision ID: f159d6c59519
Revises: e551df298167
Create Date: 2026-08-05 14:17:33.816933

Посада перестає бути просто підписом: вона визначає роль доступу.

Колонка додається nullable, заповнюється, і лише тоді стає NOT NULL —
у наявних рядках значення взятись нізвідки, а NOT NULL без DEFAULT до
непорожньої таблиці не додати.

Значення записані літералами, а не імпортовані з app.*: міграція фіксує стан
на момент її створення, і подальше перейменування константи в коді не має
змінювати те, що вона робить.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f159d6c59519'
down_revision: Union[str, None] = 'e551df298167'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLE_MAIN_ADMIN = "Головний адміністратор"
ROLE_COMPANY_ADMIN = "Адміністратор компанії"
ROLE_USER = "Користувач"

#: Посади, які дають адміністрування компанії.
ADMIN_POSITIONS = ["Директор", "Менеджер", "Логіст"]

roles = sa.table("roles", sa.column("id", sa.Integer), sa.column("role", sa.Text))
positions = sa.table(
    "positions",
    sa.column("id", sa.Integer),
    sa.column("position", sa.Text),
    sa.column("role_id", sa.Integer),
)
employees = sa.table(
    "employees",
    sa.column("id", sa.Integer),
    sa.column("position_id", sa.Integer),
    sa.column("role_id", sa.Integer),
)


def _role_id(conn, name: str):
    return conn.scalar(sa.select(roles.c.id).where(roles.c.role == name))


def upgrade() -> None:
    conn = op.get_bind()

    with op.batch_alter_table("positions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("role_id", sa.Integer(), nullable=True))

    admin_role = _role_id(conn, ROLE_COMPANY_ADMIN)
    user_role = _role_id(conn, ROLE_USER)
    if admin_role is None or user_role is None:
        raise RuntimeError(
            "У довіднику roles немає базових ролей — спершу накотіть 7d1b946ca46b"
        )

    # Адмінські посади можуть бути ще не заведені: сід свіжої БД створює лише
    # «Інше». Додаємо ті, яких бракує, наявні не чіпаємо.
    existing = set(conn.scalars(sa.select(positions.c.position)))
    missing = [name for name in ADMIN_POSITIONS if name not in existing]
    if missing:
        op.bulk_insert(
            positions,
            [{"position": name, "role_id": admin_role} for name in missing],
        )

    conn.execute(
        positions.update()
        .where(positions.c.position.in_(ADMIN_POSITIONS))
        .values(role_id=admin_role)
    )
    # Решта — звичайні користувачі. «Інше» теж: це заглушка, прав вона не дає.
    conn.execute(
        positions.update().where(positions.c.role_id.is_(None)).values(role_id=user_role)
    )

    with op.batch_alter_table("positions", schema=None) as batch_op:
        batch_op.alter_column("role_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            "fk_positions_role_id_roles", "roles", ["role_id"], ["id"]
        )

    # Приводимо наявних співробітників до нового правила. Головних
    # адміністраторів не чіпаємо: цю роль дає не посада, а людина, і жодна
    # посада її не видає — інакше міграція зняла б доступ з власника системи.
    main_admin = _role_id(conn, ROLE_MAIN_ADMIN)
    sync = employees.update().values(
        role_id=sa.select(positions.c.role_id)
        .where(positions.c.id == employees.c.position_id)
        .scalar_subquery()
    )
    if main_admin is not None:
        sync = sync.where(employees.c.role_id != main_admin)
    conn.execute(sync)


def downgrade() -> None:
    # Ролі співробітників назад не розкручуємо: інформації, хто яку роль мав
    # до міграції, ніде не лишилось, а вгадувати її гірше, ніж не чіпати.
    with op.batch_alter_table("positions", schema=None) as batch_op:
        batch_op.drop_constraint("fk_positions_role_id_roles", type_="foreignkey")
        batch_op.drop_column("role_id")
