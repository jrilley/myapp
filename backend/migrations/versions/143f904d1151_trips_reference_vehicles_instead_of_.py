"""trips reference vehicles instead of copying them

Revision ID: 143f904d1151
Revises: ca25af309fa0
Create Date: 2026-08-07 18:05:44.902118

У рейсі лежало п'ять текстових колонок про транспорт (`truck`,
`truck_license_plate`, `trailer`, `trailer_type`, `trailer_license_plate`) і
три про менеджера (`logist_*`) — усі поруч із посиланнями, які кажуть те саме.
Дві правди про один рядок розходяться при першій же правці, тож лишається одна:
зв'язок.

`truck_id` і `trailer_id` стають обов'язковими, а чужа машина більше не
«текст у рейсі» — вона теж заводиться в довідник, із порожнім власником.

`vehicles` отримує `deleted_at`: на машину тепер посилаються рейси, і стерти
рядок означало б лишити перевезення без транспорту.

Наявні рейси переносяться без втрат: із їхнього тексту створюються види, марки
й самі машини, а вже потім проставляються посилання. Машина з порожнім
власником — це рівно те, чим вона й була: чужа, вписана руками.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '143f904d1151'
down_revision: Union[str, None] = 'ca25af309fa0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TRACTOR = "Тягач"
#: Для рядків, у яких вид причепа не заповнений.
UNKNOWN_TRAILER = "Причіп"
#: Для рядків, у яких немає навіть марки або номера. Дані все одно зіпсовані —
#: але рейс має лишитись прив'язаним до чогось, а не впасти на NOT NULL.
UNKNOWN = "—"


def _lookup(conn, table: str) -> dict:
    return {
        name: row_id
        for row_id, name in conn.execute(sa.text(f"SELECT id, name FROM {table}"))
    }


def _ensure(conn, table: str, cache: dict, name: str, **extra) -> int:
    """id рядка довідника: наявного або щойно створеного."""
    if name in cache:
        return cache[name]
    columns = ", ".join(["name", *extra])
    values = ", ".join([":name", *(f":{k}" for k in extra)])
    conn.execute(
        sa.text(f"INSERT INTO {table} ({columns}) VALUES ({values})"),
        {"name": name, **extra},
    )
    cache[name] = conn.execute(
        sa.text(f"SELECT id FROM {table} WHERE name = :name"), {"name": name}
    ).scalar_one()
    return cache[name]


def upgrade() -> None:
    conn = op.get_bind()

    with op.batch_alter_table("vehicles", schema=None) as batch_op:
        batch_op.add_column(sa.Column("deleted_at", sa.Text(), nullable=True))

    types = _lookup(conn, "vehicle_type")
    marks = _lookup(conn, "vehicle_mark")
    # Номер — це і є ідентичність машини, тож за ним і шукаємо наявну.
    plates = {
        plate: row_id
        for row_id, plate in conn.execute(
            sa.text("SELECT id, license_plate FROM vehicles")
        )
    }

    rows = conn.execute(
        sa.text(
            "SELECT id, truck, truck_license_plate, trailer, trailer_type,"
            " trailer_license_plate FROM trips ORDER BY id"
        )
    ).fetchall()

    for trip_id, truck, truck_plate, trailer, trailer_type, trailer_plate in rows:
        links = {}
        for column, make_model, plate, type_name in (
            ("truck_id", truck, truck_plate, TRACTOR),
            ("trailer_id", trailer, trailer_plate, trailer_type or UNKNOWN_TRAILER),
        ):
            plate = (plate or "").strip() or f"{UNKNOWN}{trip_id}{column}"
            if plate not in plates:
                type_id = _ensure(
                    conn, "vehicle_type", types, type_name.strip() or UNKNOWN_TRAILER,
                    is_tractor=int(type_name == TRACTOR),
                )
                mark_id = _ensure(
                    conn, "vehicle_mark", marks, (make_model or "").strip() or UNKNOWN
                )
                conn.execute(
                    sa.text(
                        "INSERT INTO vehicles (type_id, mark_id, license_plate,"
                        " owner_company_id) VALUES (:t, :m, :p, NULL)"
                    ),
                    {"t": type_id, "m": mark_id, "p": plate},
                )
                plates[plate] = conn.execute(
                    sa.text("SELECT id FROM vehicles WHERE license_plate = :p"),
                    {"p": plate},
                ).scalar_one()
            links[column] = plates[plate]

        conn.execute(
            sa.text(
                "UPDATE trips SET truck_id = :truck, trailer_id = :trailer"
                " WHERE id = :id"
            ),
            {"truck": links["truck_id"], "trailer": links["trailer_id"], "id": trip_id},
        )

    with op.batch_alter_table("trips", schema=None) as batch_op:
        batch_op.alter_column("truck_id", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("trailer_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("truck")
        batch_op.drop_column("truck_license_plate")
        batch_op.drop_column("trailer")
        batch_op.drop_column("trailer_type")
        batch_op.drop_column("trailer_license_plate")
        batch_op.drop_column("logist_fullname")
        batch_op.drop_column("logist_phone_number")
        batch_op.drop_column("logist_tg")


def downgrade() -> None:
    conn = op.get_bind()

    with op.batch_alter_table("trips", schema=None) as batch_op:
        for name in (
            "truck", "truck_license_plate", "trailer", "trailer_type",
            "trailer_license_plate", "logist_fullname", "logist_phone_number",
        ):
            batch_op.add_column(sa.Column(name, sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("logist_tg", sa.BigInteger(), nullable=True))

    # Копії відновлюємо з довідників і з employees — рівно звідти, звідки
    # вони туди й потрапили.
    conn.execute(
        sa.text(
            "UPDATE trips SET"
            " truck = (SELECT m.name FROM vehicles v JOIN vehicle_mark m"
            "   ON m.id = v.mark_id WHERE v.id = trips.truck_id),"
            " truck_license_plate = (SELECT v.license_plate FROM vehicles v"
            "   WHERE v.id = trips.truck_id),"
            " trailer = (SELECT m.name FROM vehicles v JOIN vehicle_mark m"
            "   ON m.id = v.mark_id WHERE v.id = trips.trailer_id),"
            " trailer_type = (SELECT t.name FROM vehicles v JOIN vehicle_type t"
            "   ON t.id = v.type_id WHERE v.id = trips.trailer_id),"
            " trailer_license_plate = (SELECT v.license_plate FROM vehicles v"
            "   WHERE v.id = trips.trailer_id),"
            " logist_fullname = (SELECT e.fullname FROM employees e"
            "   WHERE e.id = trips.created_by),"
            " logist_phone_number = (SELECT e.phone_number FROM employees e"
            "   WHERE e.id = trips.created_by),"
            " logist_tg = (SELECT e.tg_id FROM employees e"
            "   WHERE e.id = trips.created_by)"
        )
    )

    with op.batch_alter_table("trips", schema=None) as batch_op:
        for name in (
            "truck", "truck_license_plate", "trailer", "trailer_type",
            "trailer_license_plate", "logist_fullname", "logist_phone_number",
        ):
            batch_op.alter_column(name, existing_type=sa.Text(), nullable=False)
        batch_op.alter_column(
            "logist_tg", existing_type=sa.BigInteger(), nullable=False
        )
        batch_op.alter_column("truck_id", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("trailer_id", existing_type=sa.Integer(), nullable=True)

    with op.batch_alter_table("vehicles", schema=None) as batch_op:
        batch_op.drop_column("deleted_at")
