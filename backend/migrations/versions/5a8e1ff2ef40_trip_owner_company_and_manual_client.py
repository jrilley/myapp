"""trip owner company and manual client

Revision ID: 5a8e1ff2ef40
Revises: 6a3a66f4347b
Create Date: 2026-08-06 13:24:07.974767

Замовника більше не беремо з того, хто створює рейс: його обирають зі списку
або вводять руками. А отже client_company_id перестає означати «чия це
компанія» — і на ньому більше не можна тримати ні доступ, ні маршрутизацію
в робочий чат.

Тому з'являється owner_company_id: компанія, яка веде рейс. Вона й далі
береться з творця, і саме за нею працюють обсяг «рейси компанії» та
дублювання в чат.

Наявні рейси переносяться без втрат: у них client_company_id — це якраз
компанія творця, тож вона стає owner_company_id, а назва замовника
береться з тієї ж компанії.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '5a8e1ff2ef40'
down_revision: Union[str, None] = '6a3a66f4347b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

trips = sa.table(
    "trips",
    sa.column("id", sa.Integer),
    sa.column("owner_company_id", sa.Integer),
    sa.column("client_company_id", sa.Integer),
    sa.column("client_company_name", sa.Text),
)
company = sa.table(
    "company", sa.column("id", sa.Integer), sa.column("name", sa.Text)
)


def upgrade() -> None:
    conn = op.get_bind()

    # Спершу nullable: у наявних рядках значення взятись нізвідки.
    with op.batch_alter_table("trips", schema=None) as batch_op:
        batch_op.add_column(sa.Column("owner_company_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("client_company_name", sa.Text(), nullable=True))

    conn.execute(trips.update().values(owner_company_id=trips.c.client_company_id))
    conn.execute(
        trips.update().values(
            client_company_name=sa.select(company.c.name)
            .where(company.c.id == trips.c.client_company_id)
            .scalar_subquery()
        )
    )
    # Компанію могли видалити — рейс не має лишитись без назви замовника.
    conn.execute(
        trips.update()
        .where(trips.c.client_company_name.is_(None))
        .values(client_company_name="—")
    )

    with op.batch_alter_table("trips", schema=None) as batch_op:
        batch_op.alter_column(
            "owner_company_id", existing_type=sa.Integer(), nullable=False
        )
        batch_op.alter_column(
            "client_company_name", existing_type=sa.Text(), nullable=False
        )
        # Замовник тепер може бути поза системою — зв'язок необов'язковий.
        batch_op.alter_column(
            "client_company_id", existing_type=sa.Integer(), nullable=True
        )
        batch_op.create_foreign_key(
            "fk_trips_owner_company_id_company", "company", ["owner_company_id"], ["id"]
        )
        batch_op.drop_index("ix_trips_client")
        batch_op.create_index(
            "ix_trips_owner", ["owner_company_id", "deleted_at"], unique=False
        )


def downgrade() -> None:
    conn = op.get_bind()
    # Рейси з ручним замовником не мають чим заповнити обов'язковий FK —
    # повертаємо їм компанію-власника, це найближче до правди.
    conn.execute(
        trips.update()
        .where(trips.c.client_company_id.is_(None))
        .values(client_company_id=trips.c.owner_company_id)
    )

    with op.batch_alter_table("trips", schema=None) as batch_op:
        batch_op.drop_index("ix_trips_owner")
        batch_op.create_index(
            "ix_trips_client", ["client_company_id", "deleted_at"], unique=False
        )
        batch_op.drop_constraint(
            "fk_trips_owner_company_id_company", type_="foreignkey"
        )
        batch_op.alter_column(
            "client_company_id", existing_type=sa.Integer(), nullable=False
        )
        batch_op.drop_column("client_company_name")
        batch_op.drop_column("owner_company_id")
