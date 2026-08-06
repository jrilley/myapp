"""operator stops editing net mass

Revision ID: 54ed2bf7c71c
Revises: 5a8e1ff2ef40
Create Date: 2026-08-06 16:02:11.417203

Нетто більше не вводять: воно рахується з брутто й тари. Поки його зберігали
окремим полем, ніщо не заважало трьом числам не складатись — брутто 20000,
тара 25000, нетто 3.

Поле зникло з меню редагування, тож право оператора на нього стало посиланням
у нікуди. Прибираємо і його: право, яке нічому не відповідає, згодом читають
як дозвіл і повертають кнопку.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '54ed2bf7c71c'
down_revision: Union[str, None] = '5a8e1ff2ef40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Що ця міграція міняє в матриці прав: роль → розділ → нове значення `fields`.
#: Читається тестом, який звіряє суму міграцій із app/permissions.py.
CHANGES = {
    "Оператор": {"trips": "bmass,tmass"},
}

BEFORE = "bmass,tmass,nmass"

role_permissions = sa.table(
    "role_permissions",
    sa.column("role_id", sa.Integer),
    sa.column("category", sa.Text),
    sa.column("fields", sa.Text),
)
roles = sa.table("roles", sa.column("id", sa.Integer), sa.column("role", sa.Text))


def _set_fields(value: str) -> None:
    conn = op.get_bind()
    for role_name, categories in CHANGES.items():
        role_id = sa.select(roles.c.id).where(roles.c.role == role_name).scalar_subquery()
        for category in categories:
            conn.execute(
                role_permissions.update()
                .where(role_permissions.c.role_id == role_id)
                .where(role_permissions.c.category == category)
                .values(fields=value)
            )


def upgrade() -> None:
    _set_fields(CHANGES["Оператор"]["trips"])


def downgrade() -> None:
    _set_fields(BEFORE)
