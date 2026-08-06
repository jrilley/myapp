"""one vehicles table, referenced by trips

Revision ID: 8ab5b0392923
Revises: 54ed2bf7c71c
Create Date: 2026-08-07 10:14:52.338091

`truck` і `trailer` були двома однаковими таблицями, які відрізнялись лише
назвою, — і жодного разу не використовувались при створенні рейсу: тягач,
причіп і обидва номери вводились текстом заново. Замість них одна `vehicles`
з колонкою `type`, а рейс на неї посилається.

`type` тримає не «тягач чи причіп», а вид: «Тягач», «Зерновоз», «Самоскид».
Тягач — рівно `type = 'Тягач'`, решта причепи. Завдяки цьому зникає окремий
крок анкети «тип причепа»: він був властивістю причепа, а набирався в
кожному рейсі заново.

Наявні рядки переносяться: brand і model склеюються в make_model, company_id
стає owner_company_id. Причепи отримують вид «Причіп» — у старій таблиці
його ніде було взяти.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '8ab5b0392923'
down_revision: Union[str, None] = '54ed2bf7c71c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TRACTOR = "Тягач"
#: Вид причепа зі старої таблиці невідомий — там не було такої колонки.
UNKNOWN_TRAILER = "Причіп"

vehicles = sa.table(
    "vehicles",
    sa.column("id", sa.Integer),
    sa.column("type", sa.Text),
    sa.column("make_model", sa.Text),
    sa.column("license_plate", sa.Text),
    sa.column("owner_company_id", sa.Integer),
)

VEHICLE_COLUMNS = (
    sa.Column("id", sa.Integer(), nullable=False),
    sa.Column("brand", sa.Text(), nullable=False),
    sa.Column("model", sa.Text(), nullable=False),
    sa.Column("license_plate", sa.Text(), nullable=False),
    sa.Column("company_id", sa.Integer(), nullable=True),
)


def upgrade() -> None:
    conn = op.get_bind()

    op.create_table(
        "vehicles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("make_model", sa.Text(), nullable=False),
        sa.Column("license_plate", sa.Text(), nullable=False),
        sa.Column("owner_company_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_company_id"], ["company.id"],
            name="fk_vehicles_owner_company_id_company",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("license_plate", name="uq_vehicles_license_plate"),
    )
    op.create_index("ix_vehicles_type", "vehicles", ["type"])
    op.create_index(
        "ix_vehicles_owner_company_id", "vehicles", ["owner_company_id"]
    )

    for table, kind in (("truck", TRACTOR), ("trailer", UNKNOWN_TRAILER)):
        rows = conn.execute(
            sa.text(
                f"SELECT brand, model, license_plate, company_id FROM {table}"
                " ORDER BY id"
            )
        ).fetchall()
        if not rows:
            continue
        conn.execute(
            vehicles.insert(),
            [
                {
                    "type": kind,
                    # Марка й модель окремими колонками нічого не давали:
                    # у боті вони завжди показувались поруч.
                    "make_model": f"{brand} {model}".strip(),
                    "license_plate": plate,
                    "owner_company_id": company_id,
                }
                for brand, model, plate, company_id in rows
            ],
        )

    op.drop_table("truck")
    op.drop_table("trailer")

    with op.batch_alter_table("trips", schema=None) as batch_op:
        batch_op.add_column(sa.Column("truck_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("trailer_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_trips_truck_id_vehicles", "vehicles", ["truck_id"], ["id"]
        )
        batch_op.create_foreign_key(
            "fk_trips_trailer_id_vehicles", "vehicles", ["trailer_id"], ["id"]
        )

    # Наявні рейси прив'язуємо до довідника за номером — єдине, що їх пов'язує.
    # Ті, що не збіглись, лишаються з порожнім FK: марка й номер у них свої,
    # і рейс від цього не постраждає.
    for column, kind in (("truck_id", "="), ("trailer_id", "!=")):
        conn.execute(
            sa.text(
                f"UPDATE trips SET {column} = (SELECT v.id FROM vehicles v"
                f" WHERE v.license_plate ="
                f" {'trips.truck_license_plate' if column == 'truck_id' else 'trips.trailer_license_plate'}"
                f" AND v.type {kind} :tractor)"
            ),
            {"tractor": TRACTOR},
        )


def downgrade() -> None:
    conn = op.get_bind()

    with op.batch_alter_table("trips", schema=None) as batch_op:
        batch_op.drop_constraint("fk_trips_trailer_id_vehicles", type_="foreignkey")
        batch_op.drop_constraint("fk_trips_truck_id_vehicles", type_="foreignkey")
        batch_op.drop_column("trailer_id")
        batch_op.drop_column("truck_id")

    for table in ("truck", "trailer"):
        op.create_table(
            table,
            *(c.copy() for c in VEHICLE_COLUMNS),
            sa.ForeignKeyConstraint(
                ["company_id"], ["company.id"],
                name=f"fk_{table}_company_id_company",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("license_plate", name=f"uq_{table}_license_plate"),
        )

    rows = conn.execute(
        sa.text(
            "SELECT type, make_model, license_plate, owner_company_id"
            " FROM vehicles ORDER BY id"
        )
    ).fetchall()
    for kind, make_model, plate, company_id in rows:
        # Марку від моделі відділяємо по першому пробілу — рівно так вони й
        # склеювались. Точно відновити неможливо: «Schmitz SKO 24» могло бути
        # і маркою з двох слів.
        brand, _, model = make_model.partition(" ")
        table = "truck" if kind == TRACTOR else "trailer"
        conn.execute(
            sa.text(
                f"INSERT INTO {table} (brand, model, license_plate, company_id)"
                " VALUES (:brand, :model, :plate, :company_id)"
            ),
            {
                "brand": brand,
                "model": model or brand,
                "plate": plate,
                "company_id": company_id,
            },
        )

    op.drop_index("ix_vehicles_owner_company_id", table_name="vehicles")
    op.drop_index("ix_vehicles_type", table_name="vehicles")
    op.drop_table("vehicles")
