"""positions self service, company chat, trip driver

Revision ID: 79f175b784a2
Revises: a9550235db97
Create Date: 2026-08-05 19:46:41.793384

Три зміни, які роблять одну справу — розводять «ким людина працює» і «що їй
дозволено»:

1. positions.role_id зникає. Роль більше не випливає з посади: її призначає
   головний адміністратор вручну. Замість неї — positions.self_service:
   чи може людина обрати цю посаду сама при реєстрації.
2. company.company_chat_id — робочий чат компанії, куди бот дублює рейси.
3. trips.driver_id — водій зі складу компанії, а також chat_id і
   chat_message_id: куди рейс продубльовано.

Ролі наявних співробітників НЕ чіпаємо. Вони вже проставлені попередньою
міграцією і є діючими правами: перерахувати їх нема з чого, а скинути всіх
у «Користувач» означало б зняти доступ з тих, хто його має.

Значення записані літералами, а не імпортовані з app.*: міграція фіксує стан
на момент її створення.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '79f175b784a2'
down_revision: Union[str, None] = 'a9550235db97'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Посади, які людина обирає сама при реєстрації. Решта — через адміністратора.
SELF_SERVICE_POSITIONS = ["Водій", "Диспетчер", "Оператор"]
#: Потрібні лише для відкату — щоб відновити рівно те, що було до міграції.
ADMIN_POSITIONS = ["Директор", "Менеджер", "Логіст"]

ROLE_COMPANY_ADMIN = "Адміністратор компанії"
ROLE_USER = "Користувач"

positions = sa.table(
    "positions",
    sa.column("id", sa.Integer),
    sa.column("position", sa.Text),
    sa.column("role_id", sa.Integer),
    sa.column("self_service", sa.Boolean),
)
roles = sa.table("roles", sa.column("id", sa.Integer), sa.column("role", sa.Text))


def upgrade() -> None:
    conn = op.get_bind()

    with op.batch_alter_table("positions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "self_service",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            )
        )

    conn.execute(
        positions.update()
        .where(positions.c.position.in_(SELF_SERVICE_POSITIONS))
        .values(self_service=True)
    )

    # Посади, яких у свіжій БД ще немає: сід створює лише «Інше».
    existing = set(conn.scalars(sa.select(positions.c.position)))
    missing = [p for p in SELF_SERVICE_POSITIONS if p not in existing]
    if missing:
        op.bulk_insert(
            positions,
            [{"position": name, "self_service": True} for name in missing],
        )

    with op.batch_alter_table("positions", schema=None) as batch_op:
        batch_op.drop_constraint("fk_positions_role_id_roles", type_="foreignkey")
        batch_op.drop_column("role_id")

    with op.batch_alter_table("company", schema=None) as batch_op:
        batch_op.add_column(sa.Column("company_chat_id", sa.BigInteger(), nullable=True))

    with op.batch_alter_table("trips", schema=None) as batch_op:
        batch_op.add_column(sa.Column("driver_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("chat_id", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("chat_message_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_trips_driver_id_employees", "employees", ["driver_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("trips", schema=None) as batch_op:
        batch_op.drop_constraint("fk_trips_driver_id_employees", type_="foreignkey")
        batch_op.drop_column("chat_message_id")
        batch_op.drop_column("chat_id")
        batch_op.drop_column("driver_id")

    with op.batch_alter_table("company", schema=None) as batch_op:
        batch_op.drop_column("company_chat_id")

    conn = op.get_bind()
    with op.batch_alter_table("positions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("role_id", sa.Integer(), nullable=True))

    # Відновлюємо зв'язок так само, як ставила його попередня міграція: за
    # іменами трьох керівних посад. Не «все, що не self_service»: під це
    # правило потрапили б «Інше» та «Бухгалтер», і відкат роздав би їм
    # адміністратора компанії — відкат не має підвищувати прав.
    user_role = conn.scalar(sa.select(roles.c.id).where(roles.c.role == ROLE_USER))
    admin_role = conn.scalar(
        sa.select(roles.c.id).where(roles.c.role == ROLE_COMPANY_ADMIN)
    )
    conn.execute(positions.update().values(role_id=user_role))
    conn.execute(
        positions.update()
        .where(positions.c.position.in_(ADMIN_POSITIONS))
        .values(role_id=admin_role)
    )

    with op.batch_alter_table("positions", schema=None) as batch_op:
        batch_op.alter_column("role_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            "fk_positions_role_id_roles", "roles", ["role_id"], ["id"]
        )
        batch_op.drop_column("self_service")
