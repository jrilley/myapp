"""register as driver, drop position self service

Revision ID: 52b42532acfc
Revises: 176ec7989d3e
Create Date: 2026-08-06 08:55:42.822140

Реєстрація більше не питає посаду: кожен новий співробітник отримує посаду
«Водій» і роль «Водій». Обидві змінює головний адміністратор у картці.

Роль «Водій» додається в довідник. Прав вона не дає жодних, як і
«Користувач»: адміністратором робить лише перевірка за назвою в
app/bot/access.py.

Разом із цим зникає positions.self_service. Ознака мала рівно одного
споживача — список посад при реєстрації, — а списку більше немає. Лишити
колонку означало б лишити в боті перемикач «Дозволити при реєстрації», який
нічого не робить: мовчазна кнопка гірша за відсутню.

Наявних співробітників не чіпаємо: їхні посади й ролі — це діючий стан.

Значення записані літералами, а не імпортовані з app.*: міграція фіксує стан
на момент її створення.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '52b42532acfc'
down_revision: Union[str, None] = '176ec7989d3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLE_DRIVER = "Водій"
DEFAULT_POSITION = "Водій"
#: Були відкриті для самостійного вибору — знадобиться лише для відкату.
SELF_SERVICE_POSITIONS = ["Водій", "Диспетчер", "Оператор", "Менеджер", "Логіст"]

roles = sa.table("roles", sa.column("id", sa.Integer), sa.column("role", sa.Text))
positions = sa.table(
    "positions",
    sa.column("id", sa.Integer),
    sa.column("position", sa.Text),
    sa.column("self_service", sa.Boolean),
)


def upgrade() -> None:
    conn = op.get_bind()

    if conn.scalar(sa.select(roles.c.id).where(roles.c.role == ROLE_DRIVER)) is None:
        op.bulk_insert(roles, [{"role": ROLE_DRIVER}])

    # Посада за замовчуванням має існувати, інакше реєстрація впертиметься
    # в порожнечу на останньому кроці.
    if (
        conn.scalar(
            sa.select(positions.c.id).where(positions.c.position == DEFAULT_POSITION)
        )
        is None
    ):
        op.bulk_insert(positions, [{"position": DEFAULT_POSITION}])

    with op.batch_alter_table("positions", schema=None) as batch_op:
        batch_op.drop_column("self_service")


def downgrade() -> None:
    with op.batch_alter_table("positions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("self_service", sa.Boolean(), nullable=False, server_default="0")
        )

    op.get_bind().execute(
        positions.update()
        .where(positions.c.position.in_(SELF_SERVICE_POSITIONS))
        .values(self_service=True)
    )
    # Роль «Водій» лишаємо: на неї вже можуть посилатись employees.role_id,
    # і видалення розірвало б зовнішній ключ.
