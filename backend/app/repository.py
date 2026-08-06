"""Єдиний шар доступу до БД — використовується і ботом, і API.

Навмисно без сирого SQL і без SQLite-специфіки, щоб перехід на PostgreSQL
зводився до зміни DATABASE_URL.
"""

from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Application,
    ApplicationStatus,
    Company,
    Employee,
    Position,
    Role,
    RolePermission,
    Trailer,
    Trip,
    Truck,
)


def _utc_now() -> str:
    """Мітка часу для аудиту рейсів: ISO-8601 UTC, посекундно.

    UTC, а не місцевий час: рядки в updated_at/deleted_at порівнюються між
    собою, і зсув через перехід на літній час зробив би це порівняння хибним.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def create_application(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    telegram_username: str | None,
    full_name: str,
    contact: str,
    category: str,
    description: str,
    status: ApplicationStatus = ApplicationStatus.published,
) -> Application:
    application = Application(
        telegram_user_id=telegram_user_id,
        telegram_username=telegram_username,
        full_name=full_name,
        contact=contact,
        category=category,
        description=description,
        status=status,
    )
    session.add(application)
    await session.commit()
    await session.refresh(application)
    return application


async def get_application(
    session: AsyncSession, application_id: int, *, include_deleted: bool = False
) -> Application | None:
    stmt = select(Application).where(Application.id == application_id)
    if not include_deleted:
        stmt = stmt.where(Application.deleted_at.is_(None))
    return await session.scalar(stmt)


async def list_applications(
    session: AsyncSession,
    *,
    status: ApplicationStatus | None = None,
    limit: int = 20,
    offset: int = 0,
    include_deleted: bool = False,
) -> tuple[list[Application], int]:
    """Повертає (сторінку записів, загальну кількість під ті самі фільтри)."""
    filters = []
    if not include_deleted:
        filters.append(Application.deleted_at.is_(None))
    if status is not None:
        filters.append(Application.status == status)

    total = await session.scalar(
        select(func.count()).select_from(Application).where(*filters)
    )

    stmt = (
        select(Application)
        .where(*filters)
        .order_by(Application.created_at.desc(), Application.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list(await session.scalars(stmt))
    return items, int(total or 0)


async def list_user_applications(
    session: AsyncSession, telegram_user_id: int, *, limit: int = 10, offset: int = 0
) -> tuple[list[Application], int]:
    """Повертає (сторінку, загальну кількість) — total потрібен пагінації,
    щоб знати, чи є наступна сторінка."""
    filters = (
        Application.telegram_user_id == telegram_user_id,
        Application.deleted_at.is_(None),
    )
    total = await session.scalar(
        select(func.count()).select_from(Application).where(*filters)
    )
    stmt = (
        select(Application)
        .where(*filters)
        .order_by(Application.created_at.desc(), Application.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(await session.scalars(stmt)), int(total or 0)


async def count_by_status(session: AsyncSession) -> dict[ApplicationStatus, int]:
    """Скільки заявок у кожному статусі, включно з видаленими."""
    stmt = select(Application.status, func.count()).group_by(Application.status)
    rows = await session.execute(stmt)
    counts = {status: 0 for status in ApplicationStatus}
    for status, total in rows:
        counts[status] = int(total)
    return counts


async def set_group_message(
    session: AsyncSession, application: Application, *, chat_id: int, message_id: int
) -> Application:
    application.group_chat_id = chat_id
    application.group_message_id = message_id
    await session.commit()
    await session.refresh(application)
    return application


async def soft_delete_application(
    session: AsyncSession, application: Application
) -> Application:
    application.deleted_at = datetime.now(timezone.utc)
    application.status = ApplicationStatus.deleted
    await session.commit()
    await session.refresh(application)
    return application


# ---------------------------------------------------------------------------
# Співробітники, компанії та довідники
# ---------------------------------------------------------------------------


async def get_employee_by_tg_id(
    session: AsyncSession, telegram_user_id: int
) -> Employee | None:
    """Роль і компанію тягнемо одразу: в async-сесії ліниве завантаження
    кидає MissingGreenlet, а викликачам майже завжди потрібна роль."""
    stmt = (
        select(Employee)
        .where(Employee.tg_id == telegram_user_id)
        .options(
            selectinload(Employee.role),
            selectinload(Employee.company),
            selectinload(Employee.position),
        )
    )
    return await session.scalar(stmt)


async def create_employee(
    session: AsyncSession,
    *,
    tg_id: int,
    company_id: int,
    fullname: str,
    phone_number: str,
    position_id: int,
    role_id: int,
    phone_number2: str | None = None,
) -> Employee:
    employee = Employee(
        tg_id=tg_id,
        company_id=company_id,
        fullname=fullname,
        phone_number=phone_number,
        phone_number2=phone_number2,
        position_id=position_id,
        role_id=role_id,
    )
    session.add(employee)
    await session.commit()
    await session.refresh(employee)
    return employee


async def count_employees(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count()).select_from(Employee)) or 0)


def _employee_with_links():
    return (
        selectinload(Employee.role),
        selectinload(Employee.company),
        selectinload(Employee.position),
    )


async def list_employees(
    session: AsyncSession, *, limit: int = 8, offset: int = 0
) -> tuple[list[Employee], int]:
    total = await session.scalar(select(func.count()).select_from(Employee))
    stmt = (
        select(Employee)
        .options(*_employee_with_links())
        .order_by(Employee.fullname)
        .limit(limit)
        .offset(offset)
    )
    return list(await session.scalars(stmt)), int(total or 0)


async def get_employee(session: AsyncSession, employee_id: int) -> Employee | None:
    stmt = (
        select(Employee)
        .where(Employee.id == employee_id)
        .options(*_employee_with_links())
    )
    return await session.scalar(stmt)


async def update_employee(
    session: AsyncSession, employee: Employee, **fields
) -> Employee:
    """Оновлює лише передані поля. Значення не валідуються тут —
    це робить хендлер, який знає контекст вводу."""
    for name, value in fields.items():
        setattr(employee, name, value)
    await session.commit()

    # id читаємо ДО expire: після нього будь-яке звернення до атрибута
    # тягне синхронне довантаження, а в async-сесії це MissingGreenlet.
    employee_id = employee.id

    # Сесія створена з expire_on_commit=False, тому після коміту об'єкт
    # лишається в identity map зі старими зв'язками: зміна role_id сама
    # по собі не перечитує employee.role. Без expire повернувся б
    # оновлений FK, але стара роль.
    session.expire(employee)
    return await get_employee(session, employee_id)


async def list_companies(session: AsyncSession) -> list[Company]:
    """Повний список — для клавіатури вибору при реєстрації."""
    return list(await session.scalars(select(Company).order_by(Company.name)))


async def page_companies(
    session: AsyncSession, *, limit: int = 10, offset: int = 0
) -> tuple[list[Company], int]:
    total = await session.scalar(select(func.count()).select_from(Company))
    stmt = select(Company).order_by(Company.name).limit(limit).offset(offset)
    return list(await session.scalars(stmt)), int(total or 0)


async def get_company(session: AsyncSession, company_id: int) -> Company | None:
    return await session.get(Company, company_id)


async def get_company_by_tax_id(session: AsyncSession, tax_id: str) -> Company | None:
    return await session.scalar(select(Company).where(Company.tax_id == tax_id))


async def create_company(
    session: AsyncSession,
    *,
    name: str,
    tax_id: str,
    address: str,
    company_chat_id: int | None = None,
) -> Company:
    company = Company(
        name=name, tax_id=tax_id, address=address, company_chat_id=company_chat_id
    )
    session.add(company)
    await session.commit()
    await session.refresh(company)
    return company


async def update_company(session: AsyncSession, company: Company, **fields) -> Company:
    # Без refresh: нові значення вже в об'єкті, а перечитування погасило б
    # завантажені зв'язки. Refresh доречний після INSERT — там він приносить
    # id і серверні значення за замовчуванням, — але не після UPDATE, у якому
    # ми самі проставили все, що змінилось.
    for name, value in fields.items():
        setattr(company, name, value)
    await session.commit()
    return company


async def list_positions(session: AsyncSession) -> list[Position]:
    """Повний список — для клавіатури вибору посади в картці співробітника."""
    return list(await session.scalars(select(Position).order_by(Position.id)))


async def page_positions(
    session: AsyncSession, *, limit: int = 10, offset: int = 0
) -> tuple[list[Position], int]:
    total = await session.scalar(select(func.count()).select_from(Position))
    stmt = select(Position).order_by(Position.id).limit(limit).offset(offset)
    return list(await session.scalars(stmt)), int(total or 0)


async def get_position(session: AsyncSession, position_id: int) -> Position | None:
    return await session.get(Position, position_id)


async def get_position_by_name(session: AsyncSession, name: str) -> Position | None:
    return await session.scalar(select(Position).where(Position.position == name))


async def create_position(session: AsyncSession, *, name: str) -> Position:
    position = Position(position=name)
    session.add(position)
    await session.commit()
    await session.refresh(position)
    return position


async def count_position_employees(session: AsyncSession, position_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(Employee)
            .where(Employee.position_id == position_id)
        )
        or 0
    )


# ---------------------------------------------------------------------------
# Транспорт
# ---------------------------------------------------------------------------

#: Тип транспорту → модель. Ключі збігаються з callback_data кнопок вибору.
VEHICLE_MODELS: dict[str, type[Truck] | type[Trailer]] = {
    "truck": Truck,
    "trailer": Trailer,
}


def vehicle_model(kind: str) -> type[Truck] | type[Trailer] | None:
    return VEHICLE_MODELS.get(kind)


async def get_vehicle_by_plate(
    session: AsyncSession, kind: str, license_plate: str
) -> Truck | Trailer | None:
    """Номер унікальний у межах своєї таблиці, тому шукаємо саме в ній."""
    model = vehicle_model(kind)
    if model is None:
        return None
    return await session.scalar(
        select(model).where(model.license_plate == license_plate)
    )


async def create_vehicle(
    session: AsyncSession,
    kind: str,
    *,
    brand: str,
    model: str,
    license_plate: str,
    company_id: int | None,
) -> Truck | Trailer:
    vehicle_cls = vehicle_model(kind)
    if vehicle_cls is None:
        raise ValueError(f"Невідомий тип транспорту: {kind!r}")
    vehicle = vehicle_cls(
        brand=brand,
        model=model,
        license_plate=license_plate,
        company_id=company_id,
    )
    session.add(vehicle)
    await session.commit()
    await session.refresh(vehicle)
    return vehicle


async def get_vehicle(
    session: AsyncSession, kind: str, vehicle_id: int
) -> Truck | Trailer | None:
    model = vehicle_model(kind)
    if model is None:
        return None
    return await session.scalar(
        select(model).where(model.id == vehicle_id).options(selectinload(model.company))
    )


async def list_company_vehicles(
    session: AsyncSession,
    kind: str,
    company_id: int,
    *,
    limit: int = 10,
    offset: int = 0,
) -> tuple[list[Truck | Trailer], int]:
    model = vehicle_model(kind)
    if model is None:
        return [], 0
    total = await session.scalar(
        select(func.count()).select_from(model).where(model.company_id == company_id)
    )
    stmt = (
        select(model)
        .where(model.company_id == company_id)
        .order_by(model.brand, model.license_plate)
        .limit(limit)
        .offset(offset)
    )
    return list(await session.scalars(stmt)), int(total or 0)


async def delete_vehicle(session: AsyncSession, vehicle: Truck | Trailer) -> None:
    """Транспорт стирається назовсім, на відміну від рейсу.

    М'яке видалення тут нічого не дало б: історія перевезень зберігає марку
    й номер копією в самому рейсі, тож на неї це не впливає. А ось унікальний
    держномер лишався б зайнятим назавжди.
    """
    await session.delete(vehicle)
    await session.commit()


async def update_vehicle(
    session: AsyncSession, vehicle: Truck | Trailer, **fields
) -> Truck | Trailer:
    for name, value in fields.items():
        setattr(vehicle, name, value)
    await session.commit()
    vehicle_id = vehicle.id
    kind = "truck" if isinstance(vehicle, Truck) else "trailer"
    session.expire(vehicle)
    return await get_vehicle(session, kind, vehicle_id)


async def list_company_employees(
    session: AsyncSession, company_id: int, *, limit: int = 8, offset: int = 0
) -> tuple[list[Employee], int]:
    total = await session.scalar(
        select(func.count()).select_from(Employee).where(
            Employee.company_id == company_id
        )
    )
    stmt = (
        select(Employee)
        .where(Employee.company_id == company_id)
        .options(*_employee_with_links())
        .order_by(Employee.fullname)
        .limit(limit)
        .offset(offset)
    )
    return list(await session.scalars(stmt)), int(total or 0)


# ---------------------------------------------------------------------------
# Рейси
# ---------------------------------------------------------------------------


def _trip_with_links():
    return (
        selectinload(Trip.owner_company),
        selectinload(Trip.client_company),
        selectinload(Trip.exporter_company),
        selectinload(Trip.creator),
        selectinload(Trip.driver),
    )


async def create_trip(session: AsyncSession, **fields) -> Trip:
    """Створює рейс. Поля перевіряє хендлер — тут лише запис.

    created_at проставляється тут, а не хендлером: так само, як edited_by в
    update_trip. Мітку часу неможливо забути, і формат у всіх рейсів один.
    """
    fields.setdefault("created_at", _utc_now())
    trip = Trip(**fields)
    session.add(trip)
    await session.commit()
    return await get_trip(session, trip.id)


async def get_trip(
    session: AsyncSession, trip_id: int, *, include_deleted: bool = False
) -> Trip | None:
    stmt = select(Trip).where(Trip.id == trip_id).options(*_trip_with_links())
    if not include_deleted:
        stmt = stmt.where(Trip.deleted_at.is_(None))
    return await session.scalar(stmt)


async def list_trips(
    session: AsyncSession,
    *,
    company_id: int | None = None,
    participant_id: int | None = None,
    limit: int = 5,
    offset: int = 0,
) -> tuple[list[Trip], int]:
    """Сторінка рейсів і загальна кількість під ті самі фільтри.

    `participant_id` — рейси, до яких людина причетна: створила або їде як
    водій. Саме «або»: водій свій рейс не створював, але бачити його має.

    Фільтри звужують видимість, тож ніколи не приходять із callback_data
    напряму — їх обчислює `actions.render_trips` за роллю викликача.
    """
    filters = [Trip.deleted_at.is_(None)]
    if company_id is not None:
        filters.append(Trip.owner_company_id == company_id)
    if participant_id is not None:
        filters.append(
            or_(Trip.created_by == participant_id, Trip.driver_id == participant_id)
        )

    total = await session.scalar(select(func.count()).select_from(Trip).where(*filters))
    stmt = (
        select(Trip)
        .where(*filters)
        .options(*_trip_with_links())
        .order_by(Trip.arrival_date.desc(), Trip.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(await session.scalars(stmt)), int(total or 0)


async def update_trip(
    session: AsyncSession, trip: Trip, *, editor_id: int, **fields
) -> Trip:
    """Оновлює поля рейсу й одразу проставляє, хто і коли це зробив.

    Аудит пишеться тут, а не в хендлерах: інакше достатньо було б додати
    один новий редактор і забути про edited_by, а слід уже не відновити.
    """
    for name, value in fields.items():
        setattr(trip, name, value)
    trip.edited_by = editor_id
    trip.updated_at = _utc_now()
    await session.commit()

    # id читаємо ДО expire: після нього звернення до атрибута тягне синхронне
    # довантаження, а в async-сесії це MissingGreenlet.
    trip_id = trip.id
    # expire_on_commit=False лишає в identity map старі зв'язки, тож зміна
    # exporter_company_id сама по собі не перечитала б exporter_company.
    session.expire(trip)
    return await get_trip(session, trip_id)


async def set_trip_chat_message(
    session: AsyncSession, trip: Trip, *, chat_id: int, message_id: int
) -> Trip:
    """Куди продубльовано рейс. Без цього його не прибрати з чату потім.

    Без refresh навмисно. Нові значення вже проставлені в Python, а перечитати
    рядок означало б погасити завантажені зв'язки: refresh скидає ВСІ
    атрибути, але перезавантажує лише колонки. Наступне звернення до
    trip.exporter_company пішло б у БД лінивим завантаженням — а в async-сесії
    це MissingGreenlet, і рейс, уже створений, обривався б помилкою на
    відповіді користувачу.
    """
    trip.chat_id = chat_id
    trip.chat_message_id = message_id
    await session.commit()
    return trip


async def soft_delete_trip(session: AsyncSession, trip: Trip, *, deleted_by: int) -> Trip:
    # Так само без refresh — див. set_trip_chat_message.
    trip.deleted_by = deleted_by
    trip.deleted_at = _utc_now()
    await session.commit()
    return trip


async def list_role_permissions(
    session: AsyncSession, role_id: int
) -> list[RolePermission]:
    """Права ролі по розділах. Один запит на апдейт — його робить
    AccessMiddleware, хендлери працюють уже з готовим Access."""
    return list(
        await session.scalars(
            select(RolePermission).where(RolePermission.role_id == role_id)
        )
    )


async def list_roles(session: AsyncSession) -> list[Role]:
    return list(await session.scalars(select(Role).order_by(Role.id)))


async def get_role_by_name(session: AsyncSession, name: str) -> Role | None:
    return await session.scalar(select(Role).where(Role.role == name))
