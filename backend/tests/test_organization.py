"""Тести таблиць company / positions / roles / employees.

Головне тут — що зовнішні ключі справді діють. У SQLite їх перевірка
за замовчуванням ВИМКНЕНА, і без `PRAGMA foreign_keys=ON` посилання на
неіснуючий рядок пройшло б мовчки.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.models import Company, Employee, Position, Role


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


async def test_tg_id_survives_a_real_telegram_id(session):
    """Telegram-id не вміщується в int32 — тому в моделі BigInteger,
    хоча у вихідному DDL стояв INTEGER."""
    company, position, role = await _fixtures(session)
    huge = 8_000_000_000  # більше за 2^31-1

    employee = await _employee(session, company, position, role, tg_id=huge)

    stored = await session.scalar(select(Employee.tg_id).where(Employee.id == employee.id))
    assert stored == huge
