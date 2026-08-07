"""vehicle type and mark become reference tables

Revision ID: ca25af309fa0
Revises: 8ab5b0392923
Create Date: 2026-08-07 14:38:02.115447

Вид і марка були текстом у самій машині. Вид — із переліку в коді, тож додати
новий означало реліз; марка — вільним рядком, тож «Volvo FH16», «volvo fh16» і
«Volvo FH-16» ставали трьома різними моделями. Обидва переїжджають у довідники,
а `vehicles` посилається на них.

У `vehicle_type` з'являється `is_tractor` — прапорець замість порівняння назви
з «Тягач». Довідник тепер поповнюють люди, і «Сідловий тягач» або просто
перейменований рядок мовчки зламали б поділ списку на тягачі й причепи.

Наявні машини переносяться: види беруться зі стартового набору плюс усе, що
вже стоїть у рядках, марки — з унікальних значень make_model.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'ca25af309fa0'
down_revision: Union[str, None] = '8ab5b0392923'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TRACTOR = "Тягач"
#: Стартовий набір видів. Далі довідник живе своїм життям.
TYPE_SEED = (
    TRACTOR,
    "Зерновоз",
    "Самоскид",
    "Тент",
    "Цистерна",
    "Контейнеровоз",
    "Причіп",
)

vehicle_type = sa.table(
    "vehicle_type",
    sa.column("id", sa.Integer),
    sa.column("name", sa.Text),
    sa.column("is_tractor", sa.Boolean),
)
vehicle_mark = sa.table(
    "vehicle_mark", sa.column("id", sa.Integer), sa.column("name", sa.Text)
)


def upgrade() -> None:
    conn = op.get_bind()

    op.create_table(
        "vehicle_type",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "is_tractor", sa.Boolean(), nullable=False, server_default="0"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_vehicle_type_name"),
    )
    op.create_table(
        "vehicle_mark",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_vehicle_mark_name"),
    )

    # Стартовий набір плюс усе, що встигло опинитись у машинах: інакше рядок
    # із видом поза набором лишився б без пари й впав на NOT NULL.
    existing = [
        row[0]
        for row in conn.execute(
            sa.text("SELECT DISTINCT type FROM vehicles WHERE type IS NOT NULL")
        )
    ]
    names = list(TYPE_SEED) + [n for n in existing if n not in TYPE_SEED]
    conn.execute(
        vehicle_type.insert(),
        [{"name": name, "is_tractor": name == TRACTOR} for name in names],
    )

    marks = [
        row[0]
        for row in conn.execute(
            sa.text(
                "SELECT DISTINCT make_model FROM vehicles"
                " WHERE make_model IS NOT NULL ORDER BY make_model"
            )
        )
    ]
    if marks:
        conn.execute(vehicle_mark.insert(), [{"name": name} for name in marks])

    # Спершу nullable: значення проставляємо наступним кроком.
    with op.batch_alter_table("vehicles", schema=None) as batch_op:
        batch_op.add_column(sa.Column("type_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("mark_id", sa.Integer(), nullable=True))

    conn.execute(
        sa.text(
            "UPDATE vehicles SET"
            " type_id = (SELECT t.id FROM vehicle_type t WHERE t.name = vehicles.type),"
            " mark_id = (SELECT m.id FROM vehicle_mark m WHERE m.name = vehicles.make_model)"
        )
    )

    with op.batch_alter_table("vehicles", schema=None) as batch_op:
        batch_op.alter_column("type_id", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("mark_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            "fk_vehicles_type_id_vehicle_type", "vehicle_type", ["type_id"], ["id"]
        )
        batch_op.create_foreign_key(
            "fk_vehicles_mark_id_vehicle_mark", "vehicle_mark", ["mark_id"], ["id"]
        )
        batch_op.drop_index("ix_vehicles_type")
        batch_op.create_index("ix_vehicles_type_id", ["type_id"])
        batch_op.create_index("ix_vehicles_mark_id", ["mark_id"])
        batch_op.drop_column("type")
        batch_op.drop_column("make_model")


def downgrade() -> None:
    conn = op.get_bind()

    with op.batch_alter_table("vehicles", schema=None) as batch_op:
        batch_op.add_column(sa.Column("type", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("make_model", sa.Text(), nullable=True))

    conn.execute(
        sa.text(
            "UPDATE vehicles SET"
            " type = (SELECT t.name FROM vehicle_type t WHERE t.id = vehicles.type_id),"
            " make_model = (SELECT m.name FROM vehicle_mark m WHERE m.id = vehicles.mark_id)"
        )
    )

    with op.batch_alter_table("vehicles", schema=None) as batch_op:
        batch_op.alter_column("type", existing_type=sa.Text(), nullable=False)
        batch_op.alter_column("make_model", existing_type=sa.Text(), nullable=False)
        batch_op.drop_constraint(
            "fk_vehicles_mark_id_vehicle_mark", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_vehicles_type_id_vehicle_type", type_="foreignkey"
        )
        batch_op.drop_index("ix_vehicles_mark_id")
        batch_op.drop_index("ix_vehicles_type_id")
        batch_op.create_index("ix_vehicles_type", ["type"])
        batch_op.drop_column("mark_id")
        batch_op.drop_column("type_id")

    op.drop_table("vehicle_mark")
    op.drop_table("vehicle_type")
