"""Тести таблиць company / positions / roles / employees.

Головне тут — що зовнішні ключі справді діють. У SQLite їх перевірка
за замовчуванням ВИМКНЕНА, і без `PRAGMA foreign_keys=ON` посилання на
неіснуючий рядок пройшло б мовчки.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from tests.conftest import seed_vehicle_mark, seed_vehicle_types
from app.models import (
    Company,
    Employee,
    Position,
    Role,
    Vehicle,
    VehicleMark,
    VehicleType,
)


@pytest.fixture
async def refs(session):
    """Довідники видів і марок — усе, на що тепер посилається машина."""
    types = await seed_vehicle_types(session)
    marks = {
        name: await seed_vehicle_mark(session, name)
        for name in ("Volvo FH", "Schmitz SKO", "Renault Magnum")
    }
    return types, marks


async def _fixtures(session):
    company = Company(name="ТОВ Ромашка", tax_id="12345678", address="Київ, вул. Хрещатик, 1")
    position = Position(position="Менеджер")
    role = Role(role="admin")
    session.add_all([company, position, role])
    await session.commit()
    return company, position, role


async def _employee(session, company, position, role, **overrides):
    payload = {
        "tg_id": 1029384756,
        "company_id": company.id,
        "fullname": "Іван Петренко",
        "phone_number": "+380671112233",
        "position_id": position.id,
        "role_id": role.id,
    }
    payload.update(overrides)
    employee = Employee(**payload)
    session.add(employee)
    await session.commit()
    return employee


async def test_employee_is_created_with_all_links(session):
    company, position, role = await _fixtures(session)

    employee = await _employee(session, company, position, role)

    assert employee.id is not None
    assert employee.company_id == company.id
    assert employee.position_id == position.id
    assert employee.role_id == role.id


async def test_relationships_resolve_to_the_linked_rows(session):
    company, position, role = await _fixtures(session)
    await _employee(session, company, position, role)

    stmt = select(Employee).options(
        selectinload(Employee.company),
        selectinload(Employee.position),
        selectinload(Employee.role),
    )
    employee = await session.scalar(stmt)

    assert employee.company.name == "ТОВ Ромашка"
    assert employee.position.position == "Менеджер"
    assert employee.role.role == "admin"


async def test_company_backref_lists_its_employees(session):
    company, position, role = await _fixtures(session)
    await _employee(session, company, position, role)
    await _employee(session, company, position, role, tg_id=555000111, fullname="Олена К.")

    loaded = await session.scalar(
        select(Company).options(selectinload(Company.employees))
    )

    assert {e.fullname for e in loaded.employees} == {"Іван Петренко", "Олена К."}


@pytest.mark.parametrize("field", ["company_id", "position_id", "role_id"])
async def test_foreign_keys_are_enforced(session, field):
    """Без PRAGMA foreign_keys=ON цей запис пройшов би — SQLite мовчки
    прийняв би посилання на неіснуючий рядок."""
    company, position, role = await _fixtures(session)

    with pytest.raises(IntegrityError):
        await _employee(session, company, position, role, **{field: 9999})


async def test_tg_id_is_unique(session):
    company, position, role = await _fixtures(session)
    await _employee(session, company, position, role, tg_id=42)

    with pytest.raises(IntegrityError):
        await _employee(session, company, position, role, tg_id=42, fullname="Інший")


async def test_company_tax_id_is_unique(session):
    session.add(Company(name="Перша", tax_id="1111", address="Львів"))
    await session.commit()

    session.add(Company(name="Друга", tax_id="1111", address="Одеса"))
    with pytest.raises(IntegrityError):
        await session.commit()


@pytest.mark.parametrize(
    ("model", "field", "value"),
    [(Position, "position", "Бухгалтер"), (Role, "role", "manager")],
)
async def test_reference_names_are_unique(session, model, field, value):
    session.add(model(**{field: value}))
    await session.commit()

    session.add(model(**{field: value}))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_position_is_just_a_name(session):
    """Посада нічого не вирішує: прав вона не дає, роль призначається окремо.
    Тому для створення досить назви."""
    position = Position(position="Вагар")
    session.add(position)
    await session.commit()

    assert position.id is not None


async def test_vehicle_belongs_to_a_company(session, refs):
    company, _, _ = await _fixtures(session)
    types, marks = refs

    vehicle = Vehicle(
        type_id=types["Тягач"].id, mark_id=marks["Renault Magnum"].id,
        license_plate="AA1234BB", owner_company_id=company.id,
    )
    session.add(vehicle)
    await session.commit()

    loaded = await session.scalar(
        select(Vehicle).options(selectinload(Vehicle.owner_company))
    )
    assert loaded.owner_company.name == "ТОВ Ромашка"


async def test_vehicle_reads_type_and_mark_from_the_references(session, refs):
    """Вид і марка більше не колонки машини — вона їх лише читає."""
    types, marks = refs
    vehicle = Vehicle(
        type_id=types["Зерновоз"].id, mark_id=marks["Renault Magnum"].id,
        license_plate="AA0000AA",
    )
    session.add(vehicle)
    await session.commit()

    loaded = await session.scalar(
        select(Vehicle).options(
            selectinload(Vehicle.type), selectinload(Vehicle.mark)
        )
    )
    assert loaded.type_name == "Зерновоз"
    assert loaded.make_model == "Renault Magnum"
    assert not loaded.is_tractor


async def test_vehicle_company_is_optional(session, refs):
    """Власника могли не вказати — техніка від цього не перестає існувати."""
    types, marks = refs
    vehicle = Vehicle(
        type_id=types["Тягач"].id,
        mark_id=marks["Renault Magnum"].id,
        license_plate="BC5678CD",
    )
    session.add(vehicle)
    await session.commit()

    assert vehicle.id is not None
    assert vehicle.owner_company_id is None


async def test_vehicle_company_must_exist(session, refs):
    types, marks = refs
    vehicle = Vehicle(
        type_id=types["Тягач"].id, mark_id=marks["Renault Magnum"].id,
        license_plate="CD9012DE", owner_company_id=9999,
    )
    session.add(vehicle)

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_vehicle_type_must_exist(session, refs):
    """Вид тепер зв'язок, а не рядок: неіснуючий id має відхилятись."""
    _, marks = refs
    session.add(
        Vehicle(type_id=9999, mark_id=marks["Renault Magnum"].id, license_plate="EF1111EF")
    )

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_license_plate_is_unique(session, refs):
    """Номер унікальний на весь довідник, а не в межах виду: інакше тягач і
    причіп могли б мати один номер — а це та сама машина двічі."""
    types, marks = refs
    session.add(
        Vehicle(type_id=types["Тягач"].id, mark_id=marks["Volvo FH"].id,
                license_plate="AA1111AA")
    )
    await session.commit()

    session.add(
        Vehicle(type_id=types["Зерновоз"].id, mark_id=marks["Volvo FH"].id,
                license_plate="AA1111AA")
    )
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_reference_names_are_unique_too(session, refs):
    """Довідник, у якому «Volvo FH» лежить двічі, не довідник."""
    session.add(VehicleMark(name="Volvo FH"))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_a_tractor_is_a_flag_not_a_name(session, refs):
    """«Тягач чи причіп» — прапорець у довіднику. Порівняння назви зламалось
    би на «Сідловому тягачі» або на перейменованому рядку."""
    types, marks = refs
    saddle = VehicleType(name="Сідловий тягач", is_tractor=True)
    session.add(saddle)
    await session.commit()

    vehicle = Vehicle(
        type_id=saddle.id, mark_id=marks["Volvo FH"].id, license_plate="GG2222GG"
    )
    session.add(vehicle)
    await session.commit()

    loaded = await session.scalar(
        select(Vehicle)
        .where(Vehicle.license_plate == "GG2222GG")
        .options(selectinload(Vehicle.type))
    )
    assert loaded.is_tractor


@pytest.mark.parametrize("missing", ["type_id", "mark_id", "license_plate"])
async def test_vehicle_required_fields(session, refs, missing):
    types, marks = refs
    values = {
        "type_id": types["Тягач"].id,
        "mark_id": marks["Volvo FH"].id,
        "license_plate": "DE3456EF",
    }
    values.pop(missing)
    session.add(Vehicle(**values))

    with pytest.raises(IntegrityError):
        await session.commit()


async def test_a_company_owns_its_vehicles(session, refs):
    """Одна таблиця на тягачі й причепи, один зв'язок від компанії."""
    company, _, _ = await _fixtures(session)
    types, marks = refs
    session.add(Vehicle(type_id=types["Тягач"].id, mark_id=marks["Volvo FH"].id,
                        license_plate="AA0001AA", owner_company_id=company.id))
    session.add(Vehicle(type_id=types["Зерновоз"].id, mark_id=marks["Schmitz SKO"].id,
                        license_plate="AA0002AA", owner_company_id=company.id))
    await session.commit()

    loaded = await session.scalar(
        select(Company).options(selectinload(Company.vehicles))
    )
    assert sorted(v.license_plate for v in loaded.vehicles) == [
        "AA0001AA", "AA0002AA"
    ]


async def test_tg_id_survives_a_real_telegram_id(session):
    """Telegram-id не вміщується в int32 — тому в моделі BigInteger,
    хоча у вихідному DDL стояв INTEGER."""
    company, position, role = await _fixtures(session)
    huge = 8_000_000_000  # більше за 2^31-1

    employee = await _employee(session, company, position, role, tg_id=huge)

    stored = await session.scalar(select(Employee.tg_id).where(Employee.id == employee.id))
    assert stored == huge
