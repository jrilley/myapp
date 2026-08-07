import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    company_chat_id: Mapped[int | None] = mapped_column(
        BigInteger,
        doc=(
            "Робочий чат компанії в Telegram, куди бот дублює створені рейси. "
            "Порожній — чат ще не заведено, рейси нікуди не дублюються. "
            "BigInteger: id груп від'ємні й не вміщуються в int32."
        ),
    )

    employees: Mapped[list["Employee"]] = relationship(back_populates="company")
    vehicles: Mapped[list["Vehicle"]] = relationship(back_populates="owner_company")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Company id={self.id} name={self.name!r}>"


#: Назви ролей. Живуть тут, а не в шарі бота, бо на них спираються і
#: міграції-сіди, і репозиторій, і перевірки прав.
ROLE_MAIN_ADMIN = "Головний адміністратор"
ROLE_COMPANY_ADMIN = "Адміністратор компанії"
ROLE_MANAGER = "Менеджер"
ROLE_LOGIST = "Логіст"
ROLE_OPERATOR = "Оператор"
ROLE_DISPATCHER = "Диспетчер"
ROLE_DRIVER = "Водій"

#: Розділи, на які видаються права.
CATEGORY_COMPANY = "company"
CATEGORY_EMPLOYEES = "employees"
CATEGORY_VEHICLES = "vehicles"
CATEGORY_TRIPS = "trips"

CATEGORIES = (
    CATEGORY_COMPANY,
    CATEGORY_EMPLOYEES,
    CATEGORY_VEHICLES,
    CATEGORY_TRIPS,
)

CATEGORY_TITLES = {
    CATEGORY_COMPANY: "Компанія",
    CATEGORY_EMPLOYEES: "Працівники",
    CATEGORY_VEHICLES: "Транспорт",
    CATEGORY_TRIPS: "Рейси",
}

#: Наскільки широко діє право в межах розділу.
SCOPE_OWN = "own"
SCOPE_COMPANY = "company"
SCOPE_ALL = "all"

#: Що отримує кожен, хто щойно зареєструвався. Посада й роль однойменні, але
#: це різні речі: посада каже, ким людина працює, роль — що їй дозволено.
#: Обидві змінює головний адміністратор у картці співробітника.
DEFAULT_POSITION = "Водій"
DEFAULT_ROLE = ROLE_DRIVER


class Position(Base):
    """Довідник посад."""

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    position: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, doc="Назва посади, унікальна."
    )

    employees: Mapped[list["Employee"]] = relationship(back_populates="position")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Position id={self.id} position={self.position!r}>"


class Role(Base):
    """Довідник ролей доступу.

    Роль не пов'язана з посадою: її призначає головний адміністратор вручну.
    Так підвищення прав лишається свідомою дією людини, а не наслідком
    того, що комусь поміняли підпис у довіднику.
    """

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, doc="Назва ролі, унікальна."
    )

    employees: Mapped[list["Employee"]] = relationship(back_populates="role")
    permissions: Mapped[list["RolePermission"]] = relationship(back_populates="role")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Role id={self.id} role={self.role!r}>"


class RolePermission(Base):
    """Що роль може робити в одному розділі.

    Матриця живе в базі, а не в коді: ролей сім, розділів чотири, і тримати
    це розсипаним по перевірках у хендлерах означало б шукати правду в
    двадцяти місцях. Редагувати її з бота не можна — лише міграцією: право
    змінювати права це те, з чого починаються тихі підвищення.
    """

    __tablename__ = "role_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id"), nullable=False, doc="Роль із довідника roles."
    )
    category: Mapped[str] = mapped_column(
        Text, nullable=False, doc="Розділ: company, employees, vehicles, trips."
    )

    can_create: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0", doc="C — створення."
    )
    can_read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0", doc="R — перегляд."
    )
    can_edit: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0", doc="E — редагування."
    )
    can_delete: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0", doc="D — видалення."
    )

    scope: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=SCOPE_COMPANY,
        server_default=SCOPE_COMPANY,
        doc=(
            "Наскільки широко діє право: own — лише свої записи, company — "
            "у межах своєї компанії, all — без обмежень."
        ),
    )
    fields: Mapped[str | None] = mapped_column(
        Text,
        doc=(
            "Обмеження E на перелік полів, через кому. Порожнє — усі поля "
            "розділу. Так оператор редагує лише маси, а диспетчер — лише статус."
        ),
    )

    role: Mapped["Role"] = relationship(back_populates="permissions")

    __table_args__ = (
        UniqueConstraint("role_id", "category", name="uq_role_permissions_role_category"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RolePermission role_id={self.role_id} category={self.category!r}>"


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
        ForeignKey("positions.id"),
        nullable=False,
        doc="Посада з довідника positions. При реєстрації завжди «Водій».",
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id"),
        nullable=False,
        doc=(
            "Роль доступу. При реєстрації завжди «Водій»; підвищує її "
            "головний адміністратор вручну. З посадою не пов'язана."
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


#: Види транспорту, якими засівається довідник `vehicle_type`. Це стартовий
#: набір, а не перелік дозволеного: далі види живуть у базі, і поповнює їх
#: головний адміністратор.
VEHICLE_TRACTOR = "Тягач"
VEHICLE_TYPE_SEED = (
    VEHICLE_TRACTOR,
    "Зерновоз",
    "Самоскид",
    "Тент",
    "Цистерна",
    "Контейнеровоз",
    #: Для причепа, вид якого невідомий або не має значення.
    "Причіп",
)


class VehicleType(Base):
    """Вид транспорту: «Тягач», «Зерновоз», «Самоскид».

    Довідник, а не перелік у коді: додати вид має бути дією адміністратора,
    а не релізом.
    """

    __tablename__ = "vehicle_type"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, doc="Назва виду, унікальна."
    )
    is_tractor: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
        doc=(
            "Чи це тягач. Окрема колонка, а не порівняння назви з «Тягач»: "
            "довідник поповнюють люди, і «Сідловий тягач» або перейменований "
            "рядок мовчки зламали б поділ списку на тягачі й причепи."
        ),
    )

    vehicles: Mapped[list["Vehicle"]] = relationship(back_populates="type")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<VehicleType id={self.id} name={self.name!r}>"


class VehicleMark(Base):
    """Марка й модель одним рядком: «Volvo FH16», «Schmitz SKO24».

    Окремою таблицею, щоб та сама модель не вводилась щоразу заново — і не
    розходилась написанням, як це вже траплялось із культурами.
    """

    __tablename__ = "vehicle_mark"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, doc="Марка й модель, як їх називають."
    )

    vehicles: Mapped[list["Vehicle"]] = relationship(back_populates="mark")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<VehicleMark id={self.id} name={self.name!r}>"


class Vehicle(Base):
    """Транспортний засіб: вид і марка з довідників плюс те, що належить
    саме цій машині, — номер і власник."""

    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type_id: Mapped[int] = mapped_column(
        ForeignKey("vehicle_type.id"),
        nullable=False,
        index=True,
        doc="Вид із довідника vehicle_type.",
    )
    mark_id: Mapped[int] = mapped_column(
        ForeignKey("vehicle_mark.id"),
        nullable=False,
        index=True,
        doc="Марка й модель із довідника vehicle_mark.",
    )
    license_plate: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, doc="Державний номер, унікальний."
    )
    owner_company_id: Mapped[int | None] = mapped_column(
        ForeignKey("company.id"),
        index=True,
        doc=(
            "Компанія-власник. За нею працює обсяг доступу: у списку транспорту "
            "видно машини своєї компанії. Nullable — власника могли не вказати."
        ),
    )

    type: Mapped["VehicleType"] = relationship(back_populates="vehicles")
    mark: Mapped["VehicleMark"] = relationship(back_populates="vehicles")
    owner_company: Mapped["Company | None"] = relationship(back_populates="vehicles")

    __table_args__ = (
        # Ім'я задаємо явно: безіменне обмеження неможливо зняти в downgrade,
        # а в SQLite будь-яка зміна обмежень — це перебудова таблиці.
        UniqueConstraint("license_plate", name="uq_vehicles_license_plate"),
    )

    # Вид і марку читаємо властивостями: так решта коду не знає, що вони
    # приїхали з інших таблиць, і не розсипається на .type.name по всіх
    # клавіатурах і картках.
    @property
    def type_name(self) -> str:
        return self.type.name

    @property
    def make_model(self) -> str:
        return self.mark.name

    @property
    def is_tractor(self) -> bool:
        return self.type.is_tractor

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Vehicle id={self.id} plate={self.license_plate!r}>"


# ---------------------------------------------------------------------------
# Рейси
# ---------------------------------------------------------------------------

#: Статус новоствореного рейсу. Колонка текстова, а не Enum, навмисно:
#: додати статус має бути зміною константи, а не міграцією схеми.
TRIP_STATUS_NEW = "Створено"

#: Дозволені статуси, у порядку руху рейсу. Перелік потрібен, бо статус —
#: єдине, що змінює диспетчер, і доти, доки його вводили текстом, у колонці
#: могли опинитись «ок», «готово» й «111»: ні відфільтрувати, ні порахувати.
#:
#: Картка показує й статус поза переліком — рядок, збережений до цієї зміни,
#: лишається читабельним. Заборона діє лише на нові значення.
TRIP_STATUSES = (
    TRIP_STATUS_NEW,
    "В дорозі",
    "На території",
    "Зважено",
    "Виїхав",
    "Завершено",
    "Скасовано",
)


class Trip(Base):
    """Рейс — заявка на перевезення за однією ТТН.

    Дані логіста продубльовані копією (`logist_fullname`, `logist_phone_number`,
    `logist_tg`), хоча поруч є FK `created_by`. Це навмисно: рейс — документ, і
    він має лишитись читабельним, якщо співробітник змінить прізвище чи піде з
    компанії. FK відповідає на «хто це зараз», копія — на «хто це був тоді».

    Дати й час зберігаються текстом, як у вихідній схемі. Формати фіксовані,
    щоб сортування рядком збігалося з хронологією:
      arrival_date                        — «РРРР-ММ-ДД»
      datetime_entry/_departure           — «РРРР-ММ-ДД ГГ:ХХ», місцевий час
      created_at/updated_at/deleted_at    — ISO-8601 UTC, проставляє репозиторій
    """

    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    ttn_num: Mapped[str] = mapped_column(
        Text, nullable=False, index=True, doc="Номер ТТН. Вводить логіст."
    )
    arrival_date: Mapped[str] = mapped_column(
        Text, nullable=False, doc="Дата прибуття автомобіля, «РРРР-ММ-ДД». Обирається в календарі."
    )

    # Компанія, яка веде рейс. Не питається: береться з того, хто створює.
    # Саме за нею працює обсяг доступу «рейси компанії» й дублювання в робочий
    # чат — замовник для цього не годиться, він тепер чужа компанія.
    owner_company_id: Mapped[int] = mapped_column(
        ForeignKey("company.id"),
        nullable=False,
        doc=(
            "Компанія, яка веде рейс: компанія того, хто його створив. "
            "За нею визначається, хто рейс бачить і в який чат він іде."
        ),
    )

    # Замовник може не бути в системі взагалі, тож FK необов'язковий, а назва
    # обов'язкова: та сама пара «зв'язок + копія», що й у водія з менеджером.
    client_company_id: Mapped[int | None] = mapped_column(
        ForeignKey("company.id"),
        doc="Компанія-замовник, якщо її обрали зі списку. Порожньо — введена вручну.",
    )
    client_company_name: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Назва замовника, як вона потрапила в документ.",
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

    # Транспорт обирають із довідника `vehicles`, але не завжди: рейс може
    # виконувати чужа машина, якої там немає. Тому FK необов'язкові, а марка
    # з номером — обов'язкові: вони і є документом. Та сама пара
    # «зв'язок + копія», що й у водія з менеджером.
    truck_id: Mapped[int | None] = mapped_column(
        ForeignKey("vehicles.id"),
        doc="Тягач із довідника, якщо його обрали зі списку. Порожній — введений вручну.",
    )
    truck: Mapped[str] = mapped_column(Text, nullable=False, doc="Тягач: марка й модель.")
    truck_license_plate: Mapped[str] = mapped_column(
        Text, nullable=False, doc="Державний номер тягача."
    )
    trailer_id: Mapped[int | None] = mapped_column(
        ForeignKey("vehicles.id"),
        doc="Причіп із довідника, якщо його обрали зі списку.",
    )
    trailer: Mapped[str] = mapped_column(Text, nullable=False, doc="Причіп: марка й модель.")
    trailer_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc=(
            "Вид причепа (зерновоз, самоскид тощо). При виборі з довідника "
            "береться з vehicles.type — це властивість причепа, не рейсу."
        ),
    )
    trailer_license_plate: Mapped[str] = mapped_column(
        Text, nullable=False, doc="Державний номер причепа. Не може збігатися з номером тягача."
    )

    grain_type: Mapped[str] = mapped_column(Text, nullable=False, doc="Культура, яку везуть.")

    # Водія обирають зі співробітників компанії, але не завжди: рейс може
    # виконувати найманий перевізник, якого в employees немає. Тому FK
    # необов'язковий, а ПІБ і телефон лишаються обов'язковими — вони і є
    # документом. Та сама пара «зв'язок + копія», що й у логіста.
    driver_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id"),
        doc=(
            "Водій-співробітник, якщо його обрали зі списку. Порожній для "
            "стороннього водія. Саме за цим полем водій бачить свій рейс і "
            "отримує сповіщення."
        ),
    )
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

    created_at: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc=(
            "Коли рейс створено, ISO-8601 UTC. Не сортувальне поле — списки "
            "йдуть за датою прибуття, — але без нього неможливо сказати, коли "
            "рейс з'явився: updated_at і deleted_at при створенні порожні."
        ),
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

    # Куди продубльовано рейс. Chat id зберігаємо разом із message_id, а не
    # беремо з company: робочий чат компанії могли змінити, і тоді правка
    # пішла б у новий чат, а повідомлення висить у старому.
    chat_id: Mapped[int | None] = mapped_column(
        BigInteger, doc="Робочий чат, у який продубльовано рейс."
    )
    chat_message_id: Mapped[int | None] = mapped_column(
        Integer,
        doc="Без нього неможливо прибрати повідомлення з чату при видаленні рейсу.",
    )

    # foreign_keys обов'язковий: на company і на employees звідси веде
    # більш ніж один FK, і SQLAlchemy сама не вгадає, який із них чий.
    owner_company: Mapped["Company"] = relationship(foreign_keys=[owner_company_id])
    client_company: Mapped["Company | None"] = relationship(
        foreign_keys=[client_company_id]
    )
    exporter_company: Mapped["Company"] = relationship(foreign_keys=[exporter_company_id])
    creator: Mapped["Employee"] = relationship(foreign_keys=[created_by])
    driver: Mapped["Employee | None"] = relationship(foreign_keys=[driver_id])
    truck_vehicle: Mapped["Vehicle | None"] = relationship(foreign_keys=[truck_id])
    trailer_vehicle: Mapped["Vehicle | None"] = relationship(foreign_keys=[trailer_id])

    __table_args__ = (
        # Під основний запит списку: живі рейси, найближчі за датою прибуття.
        Index("ix_trips_visible", "deleted_at", "arrival_date"),
        Index("ix_trips_owner", "owner_company_id", "deleted_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Trip id={self.id} ttn={self.ttn_num!r} date={self.arrival_date}>"
