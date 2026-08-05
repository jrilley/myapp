from aiogram.fsm.state import State, StatesGroup


class ApplicationForm(StatesGroup):
    """Покрокова анкета. При невалідному вводі лишаємось у поточному стані,
    щоб уже введені відповіді не губились."""

    full_name = State()
    contact = State()
    category = State()
    description = State()
    confirm = State()


class Registration(StatesGroup):
    """Реєстрація нового співробітника — рядок у employees."""

    fullname = State()
    phone = State()
    phone2_ask = State()
    phone2 = State()
    company = State()
    position = State()
    confirm = State()


class CompanyForm(StatesGroup):
    """Заведення компанії. Доступна лише головному адміністратору:
    без жодної компанії зареєструватись неможливо."""

    name = State()
    tax_id = State()
    address = State()


class EmployeeEdit(StatesGroup):
    """Редагування текстових полів співробітника. Поля-довідники (компанія,
    посада, роль) міняються кнопкою й стану не потребують."""

    fullname = State()
    phone = State()
    phone2 = State()


class PositionForm(StatesGroup):
    """Додавання посади в довідник.

    Роль питаємо одразу: посада без ролі не має сенсу — саме вона визначає,
    які права отримає той, кого на цю посаду призначать.
    """

    name = State()
    role = State()


class VehicleForm(StatesGroup):
    """Додавання тягача або причепа.

    Крок `company` проходить лише головний адміністратор — адміністратору
    компанії company_id береться з його власного запису в employees.
    """

    kind = State()
    company = State()
    brand = State()
    model = State()
    license_plate = State()
    confirm = State()


class VehicleEdit(StatesGroup):
    """Редагування наявного транспорту з його картки."""

    brand = State()
    model = State()
    license_plate = State()


class TripForm(StatesGroup):
    """Створення рейсу.

    Компанія-замовник і дані логіста не мають власних кроків: вони
    підтягуються з employees того, хто заповнює форму.
    """

    ttn = State()
    arrival_date = State()
    exporter = State()
    truck = State()
    truck_plate = State()
    trailer = State()
    trailer_type = State()
    trailer_plate = State()
    grain = State()
    driver = State()
    driver_phone = State()
    confirm = State()


class TripEdit(StatesGroup):
    """Редагування рейсу з картки.

    Стан один на всі текстові поля: що саме редагуємо — лежить у даних FSM,
    інакше знадобився б окремий стан і окремий хендлер на кожне з півтора
    десятка полів.
    """

    value = State()
    #: Дата й компанія-експортер обираються кнопками, тому мають свої стани:
    #: за станом визначається, який саме крок чекає на натискання.
    arrival_date = State()
    exporter = State()
