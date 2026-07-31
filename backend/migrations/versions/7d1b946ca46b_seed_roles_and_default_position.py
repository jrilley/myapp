"""seed roles and default position

Revision ID: 7d1b946ca46b
Revises: 6a0399695822
Create Date: 2026-07-31 08:50:02.333249

Довідникові рядки, без яких employees неможливо заповнити: role_id і
position_id — NOT NULL із зовнішнім ключем.

Значення записані літералами, а не імпортовані з app.*: міграція фіксує стан
на момент її створення, і подальше перейменування константи в коді не має
змінювати те, що вона робить.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7d1b946ca46b'
down_revision: Union[str, None] = '6a0399695822'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLES = ["Головний адміністратор", "Адміністратор компанії", "Користувач"]
POSITIONS = ["Інше"]

roles_table = sa.table("roles", sa.column("id", sa.Integer), sa.column("role", sa.Text))
positions_table = sa.table(
    "positions", sa.column("id", sa.Integer), sa.column("position", sa.Text)
)


def upgrade() -> None:
    # id задаємо явно, щоб на них можна було посилатись передбачувано
    # (наприклад, «Користувач» = 3 як роль за замовчуванням при реєстрації).
    op.bulk_insert(
        roles_table,
        [{"id": index, "role": name} for index, name in enumerate(ROLES, start=1)],
    )
    op.bulk_insert(
        positions_table,
        [
            {"id": index, "position": name}
            for index, name in enumerate(POSITIONS, start=1)
        ],
    )


def downgrade() -> None:
    op.execute(roles_table.delete().where(roles_table.c.role.in_(ROLES)))
    op.execute(
        positions_table.delete().where(positions_table.c.position.in_(POSITIONS))
    )
