"""open menedzher and logist for self registration

Revision ID: 176ec7989d3e
Revises: 79f175b784a2
Create Date: 2026-08-06 02:40:03.339827

«Менеджер» і «Логіст» стають доступними при самостійній реєстрації.
«Директор» лишається за адміністратором.

Це зміна даних, і головний адмін може зробити її кнопкою (💼 Посади →
посада → «Дозволити при реєстрації»). Міграція потрібна, щоб свіжа БД
піднімалась із тим самим набором, що й робоча: інакше сід і реальність
розійшлися б, а документація описувала б неіснуючий стан.

Роль ця зміна не чіпає: при реєстрації вона завжди «Користувач», і
підвищує її головний адміністратор вручну.

Значення записані літералами, а не імпортовані з app.*: міграція фіксує стан
на момент її створення.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '176ec7989d3e'
down_revision: Union[str, None] = '79f175b784a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OPENED = ["Менеджер", "Логіст"]

positions = sa.table(
    "positions",
    sa.column("id", sa.Integer),
    sa.column("position", sa.Text),
    sa.column("self_service", sa.Boolean),
)


def upgrade() -> None:
    conn = op.get_bind()

    # У свіжій БД цих посад ще немає: сід створює лише «Інше».
    existing = set(conn.scalars(sa.select(positions.c.position)))
    missing = [name for name in OPENED if name not in existing]
    if missing:
        op.bulk_insert(
            positions, [{"position": name, "self_service": True} for name in missing]
        )

    conn.execute(
        positions.update()
        .where(positions.c.position.in_(OPENED))
        .values(self_service=True)
    )


def downgrade() -> None:
    op.get_bind().execute(
        positions.update()
        .where(positions.c.position.in_(OPENED))
        .values(self_service=False)
    )
