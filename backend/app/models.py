import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from app.db import Base


class ApplicationStatus(str, enum.Enum):
    """Модерації зараз немає — заявка одразу `published`.

    Решта значень закладені наперед, щоб увімкнути модерацію
    без міграції схеми: достатньо змінити значення за замовчуванням.
    """

    pending = "pending"
    published = "published"
    rejected = "rejected"
    deleted = "deleted"


class Application(Base):
    """Заявка, надіслана через Telegram-бота.

    Описи полів живуть у `doc=` і звідти потрапляють у docs/schema.json
    (scripts/dump_schema.py). `doc` — метадані рівня Python: у DDL вони не
    йдуть, тож на міграції не впливають.
    """

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        doc="Номер заявки. Його бачить користувач у «#N» і передає в /delete.",
    )

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        doc="Автор заявки. BigInteger обов'язково: Telegram id не вміщується в int32.",
    )
    telegram_username: Mapped[str | None] = mapped_column(
        String(64),
        doc="@username автора, якщо він є — у Telegram він не обов'язковий.",
    )

    full_name: Mapped[str] = mapped_column(
        String(200), nullable=False, doc="Крок 1 анкети: ПІБ."
    )
    contact: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="Крок 2 анкети. Публічний за рішенням замовника — бот попереджає.",
    )
    category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        doc="Крок 3 анкети, значення з фіксованого списку app/bot/constants.py.",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Крок 4 анкети. Text, а не String: довжину обмежує бот, не схема.",
    )

    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, native_enum=False, length=16),
        nullable=False,
        default=ApplicationStatus.published,
        index=True,
        doc="Модерації немає, тому при створенні завжди published.",
    )

    group_chat_id: Mapped[int | None] = mapped_column(
        BigInteger,
        doc="Куди опубліковано. Порожнє, якщо публікація не вдалася.",
    )
    group_message_id: Mapped[int | None] = mapped_column(
        Integer,
        doc="Без нього неможливо прибрати повідомлення з групи при видаленні.",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        doc="Проставляє БД. За ним сортується список на сайті.",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        doc="Оновлюється автоматично при кожній зміні рядка.",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        doc=(
            "Мітка м'якого видалення; NULL = заявка жива. Рядок не стирається: "
            "заявки — персональні дані й історія звернень."
        ),
    )

    __table_args__ = (
        # Під основний запит сайту: живі заявки, новіші вгорі.
        Index("ix_applications_visible", "deleted_at", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Application id={self.id} status={self.status} category={self.category!r}>"


# ---------------------------------------------------------------------------
# Компанії, довідники та співробітники
# ---------------------------------------------------------------------------


class Company(Base):
    """Компанія, до якої належать співробітники."""

    __tablename__ = "company"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, doc="Назва компанії.")
    tax_id: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, doc="Податковий номер, унікальний."
    )
    address: Mapped[str] = mapped_column(Text, nullable=False, doc="Адреса компанії.")

    employees: Mapped[list["Employee"]] = relationship(back_populates="company")
    trucks: Mapped[list["Truck"]] = relationship(back_populates="company")
    trailers: Mapped[list["Trailer"]] = relationship(back_populates="company")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Company id={self.id} name={self.name!r}>"


#: Назви ролей. Живуть тут, а не в шарі бота, бо на них спираються і
#: міграції-сіди, і репозиторій, і перевірки прав.
ROLE_MAIN_ADMIN = "Головний адміністратор"
ROLE_COMPANY_ADMIN = "Адміністратор компанії"
ROLE_USER = "Користувач"

#: Посади, які дають адміністрування компанії. Список потрібен лише для сіду
#: нових БД: після нього зв'язок «посада → роль» живе в positions.role_id,
#: і головний адмін міняє його кнопкою, а не правкою коду.
ADMIN_POSITIONS = ("Директор", "Менеджер", "Логіст")

#: Посада-заглушка: ставиться, коли справжня невідома. Прав не дає.
FALLBACK_POSITION = "Інше"


class Position(Base):
    """Довідник посад. Посада визначає роль доступу."""

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    position: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, doc="Назва посади, унікальна."
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id"),
        nullable=False,
        doc=(
            "Роль доступу, яку дає ця посада. Саме звідси береться "
            "employees.role_id при реєстрації та при зміні посади."
        ),
    )

    role: Mapped["Role"] = relationship(back_populates="positions")
    employees: Mapped[list["Employee"]] = relationship(back_populates="position")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Position id={self.id} position={self.position!r}>"


class Role(Base):
    """Довідник ролей доступу."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, doc="Назва ролі, унікальна."
    )

    employees: Mapped[list["Employee"]] = relationship(back_populates="role")
    positions: Mapped[list["Position"]] = relationship(back_populates="role")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Role id={self.id} role={self.role!r}>"


class Employee(Base):
    """Співробітник компанії, ідентифікований за Telegram-акаунтом."""

    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # BigInteger, а не INTEGER зі схеми: у SQLite INTEGER і так 64-бітний, але
    # в PostgreSQL він 32-бітний, і Telegram-id туди не влізе. Та сама причина,
    # що й для applications.telegram_user_id.
    tg_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, unique=True, doc="Telegram user id, унікальний."
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("company.id"), nullable=False, doc="Компанія співробітника."
    )
    fullname: Mapped[str] = mapped_column(Text, nullable=False, doc="ПІБ співробітника.")
    phone_number: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Основний номер. Зазвичай отриманий кнопкою «Поділитися номером».",
    )
    phone_number2: Mapped[str | None] = mapped_column(
        Text,
        doc="Додатковий номер, якщо користувач його вказав. Необов'язковий.",
    )
    position_id: Mapped[int] = mapped_column(
        ForeignKey("positions.id"), nullable=False, doc="Посада з довідника positions."
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id"),
        nullable=False,
        doc=(
            "Діюча роль доступу. Проставляється з positions.role_id при "
            "реєстрації та при зміні посади; головний адмін може перевизначити "
            "вручну — саме так видається «Головний адміністратор», якого не дає "
            "жодна посада."
        ),
    )

    company: Mapped["Company"] = relationship(back_populates="employees")
    position: Mapped["Position"] = relationship(back_populates="employees")
    role: Mapped["Role"] = relationship(back_populates="employees")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Employee id={self.id} tg_id={self.tg_id} fullname={self.fullname!r}>"


# ---------------------------------------------------------------------------
# Транспорт
# ---------------------------------------------------------------------------


class VehicleMixin:
    """Спільні колонки truck і trailer.

    Таблиці однакові за структурою, тож тримаємо її в одному місці —
    інакше при наступній зміні одна з них відстане від іншої.
    """

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand: Mapped[str] = mapped_column(Text, nullable=False, doc="Марка.")
    model: Mapped[str] = mapped_column(Text, nullable=False, doc="Модель.")
    license_plate: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Державний номер, унікальний у межах своєї таблиці.",
    )

    @declared_attr
    def __table_args__(cls) -> tuple:
        # Ім'я задаємо явно: безіменне обмеження неможливо зняти в downgrade,
        # а в SQLite будь-яка зміна обмежень — це перебудова таблиці.
        return (
            UniqueConstraint(
                "license_plate", name=f"uq_{cls.__tablename__}_license_plate"
            ),
        )

    @declared_attr
    def company_id(cls) -> Mapped[int | None]:
        # declared_attr обов'язковий: ForeignKey не можна ділити між класами,
        # для кожної таблиці потрібен свій екземпляр.
        return mapped_column(
            ForeignKey("company.id"),
            doc="Компанія-власник. Nullable — так задано у вихідній схемі.",
        )


class Truck(VehicleMixin, Base):
    """Тягач."""

    __tablename__ = "truck"

    company: Mapped["Company | None"] = relationship(back_populates="trucks")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Truck id={self.id} plate={self.license_plate!r}>"


class Trailer(VehicleMixin, Base):
    """Причіп."""

    __tablename__ = "trailer"

    company: Mapped["Company | None"] = relationship(back_populates="trailers")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Trailer id={self.id} plate={self.license_plate!r}>"


# ---------------------------------------------------------------------------
# Рейси
# ---------------------------------------------------------------------------

#: Статус новоствореного рейсу. Колонка текстова, а не Enum, навмисно:
#: додати статус має бути зміною константи, а не міграцією схеми.
TRIP_STATUS_NEW = "Створено"


class Trip(Base):
    """Рейс — заявка на перевезення за однією ТТН.

    Дані логіста продубльовані копією (`logist_fullname`, `logist_phone_number`,
    `logist_tg`), хоча поруч є FK `created_by`. Це навмисно: рейс — документ, і
    він має лишитись читабельним, якщо співробітник змінить прізвище чи піде з
    компанії. FK відповідає на «хто це зараз», копія — на «хто це був тоді».

    Дати й час зберігаються текстом, як у вихідній схемі. Формати фіксовані,
    щоб сортування рядком збігалося з хронологією:
      arrival_date                — «РРРР-ММ-ДД»
      datetime_entry/_departure   — «РРРР-ММ-ДД ГГ:ХХ», місцевий час
      updated_at/deleted_at       — ISO-8601 UTC, проставляє репозиторій
    """

    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    ttn_num: Mapped[str] = mapped_column(
        Text, nullable=False, index=True, doc="Номер ТТН. Вводить логіст."
    )
    arrival_date: Mapped[str] = mapped_column(
        Text, nullable=False, doc="Дата прибуття автомобіля, «РРРР-ММ-ДД». Обирається в календарі."
    )

    # У вихідній схемі ці два поля TEXT, але в них лежить company.id. Тримаємо
    # їх INTEGER із справжнім FK: інакше зв'язок неможливо ні перевірити, ні
    # зджойнити, а назва компанії дублювалась би в кожному рейсі.
    client_company_id: Mapped[int] = mapped_column(
        ForeignKey("company.id"),
        nullable=False,
        doc="Компанія-замовник. Береться з компанії того, хто створює рейс.",
    )
    exporter_company_id: Mapped[int] = mapped_column(
        ForeignKey("company.id"),
        nullable=False,
        doc="Компанія-експортер. Обирається зі списку компаній.",
    )

    created_by: Mapped[int] = mapped_column(
        ForeignKey("employees.id"),
        nullable=False,
        doc="Хто створив рейс. У самій заявці не показується.",
    )
    logist_fullname: Mapped[str] = mapped_column(
        Text, nullable=False, doc="ПІБ логіста на момент створення (копія employees.fullname)."
    )
    logist_phone_number: Mapped[str] = mapped_column(
        Text, nullable=False, doc="Телефон логіста на момент створення (копія employees.phone_number)."
    )
    logist_tg: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        doc="Telegram id логіста (копія employees.tg_id) — щоб із заявки можна було написати.",
    )

    truck: Mapped[str] = mapped_column(Text, nullable=False, doc="Тягач: марка й модель, вводить логіст.")
    truck_license_plate: Mapped[str] = mapped_column(
        Text, nullable=False, doc="Державний номер тягача."
    )
    trailer: Mapped[str] = mapped_column(Text, nullable=False, doc="Причіп: марка й модель, вводить логіст.")
    trailer_type: Mapped[str] = mapped_column(Text, nullable=False, doc="Тип причепа (зерновоз, самоскид тощо).")
    trailer_license_plate: Mapped[str] = mapped_column(
        Text, nullable=False, doc="Державний номер причепа. Не може збігатися з номером тягача."
    )

    grain_type: Mapped[str] = mapped_column(Text, nullable=False, doc="Культура, яку везуть.")
    driver_fullname: Mapped[str] = mapped_column(Text, nullable=False, doc="ПІБ водія.")
    driver_phone_number: Mapped[str] = mapped_column(Text, nullable=False, doc="Телефон водія.")

    datetime_entry: Mapped[str | None] = mapped_column(
        Text, doc="Час заїзду на територію, «РРРР-ММ-ДД ГГ:ХХ». При створенні порожній."
    )
    datetime_departure: Mapped[str | None] = mapped_column(
        Text, doc="Час виїзду, «РРРР-ММ-ДД ГГ:ХХ». При створенні порожній."
    )

    # server_default, а не лише default: у вихідній схемі стоїть DEFAULT 0,
    # і вставка в обхід ORM (міграція, ручний SQL) має поводитись так само.
    b_mass: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", doc="Брутто, кг. При створенні 0."
    )
    t_mass: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", doc="Тара, кг. При створенні 0."
    )
    n_mass: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0", doc="Нетто, кг. При створенні 0."
    )

    # У вихідній схемі edited_by був NOT NULL, але той самий опис каже, що при
    # створенні поле порожнє — виконати обидві вимоги неможливо. Лишаємо
    # nullable: NULL тут означає «рейс ще ніхто не редагував».
    edited_by: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), doc="Хто востаннє редагував. NULL — рейс не редагували."
    )
    updated_at: Mapped[str | None] = mapped_column(
        Text, doc="Коли востаннє редагували, ISO-8601 UTC. NULL — не редагували."
    )
    deleted_by: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"), doc="Хто видалив рейс."
    )
    deleted_at: Mapped[str | None] = mapped_column(
        Text,
        doc=(
            "Мітка м'якого видалення, ISO-8601 UTC; NULL = рейс живий. "
            "Рядок не стирається: це історія перевезень."
        ),
    )

    status: Mapped[str] = mapped_column(
        Text, nullable=False, default=TRIP_STATUS_NEW, doc="Статус рейсу."
    )

    # foreign_keys обов'язковий: на company і на employees звідси веде
    # більш ніж один FK, і SQLAlchemy сама не вгадає, який із них чий.
    client_company: Mapped["Company"] = relationship(foreign_keys=[client_company_id])
    exporter_company: Mapped["Company"] = relationship(foreign_keys=[exporter_company_id])
    creator: Mapped["Employee"] = relationship(foreign_keys=[created_by])

    __table_args__ = (
        # Під основний запит списку: живі рейси, найближчі за датою прибуття.
        Index("ix_trips_visible", "deleted_at", "arrival_date"),
        Index("ix_trips_client", "client_company_id", "deleted_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Trip id={self.id} ttn={self.ttn_num!r} date={self.arrival_date}>"
