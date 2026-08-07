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
    """Реєстрація нового співробітника — рядок у employees.

    Посаду не питаємо: новий співробітник завжди «Водій», і посаду з роллю
    змінює головний адміністратор у картці.
    """

    fullname = State()
    phone = State()
    phone2_ask = State()
    phone2 = State()
    company = State()
    confirm = State()


class CompanyForm(StatesGroup):
    """Заведення компанії. Доступна лише головному адміністратору:
    без жодної компанії зареєструватись неможливо."""

    name = State()
    tax_id = State()
    address = State()
    #: Робочий чат може бути ще не створений, тож крок пропускається кнопкою.
    chat = State()


class CompanyEdit(StatesGroup):
    """Редагування компанії з її картки. Стан один на всі текстові поля:
    що саме редагуємо — лежить у даних FSM."""

    value = State()


class EmployeeEdit(StatesGroup):
    """Редагування текстових полів співробітника. Поля-довідники (компанія,
    посада, роль) міняються кнопкою й стану не потребують."""

    fullname = State()
    phone = State()
    phone2 = State()


class PositionForm(StatesGroup):
    """Додавання посади в довідник."""

    name = State()


class VehicleTypeForm(StatesGroup):
    """Додавання виду транспорту. Доступно лише головному адміністратору."""

    name = State()
    #: Тягач чи причіп — питаємо явно: назва цього не каже, а від відповіді
    #: залежить, у якій половині списку машина опиниться.
    is_tractor = State()


class VehicleForm(StatesGroup):
    """Додавання транспорту в довідник.

    Крок `company` проходить лише головний адміністратор — адміністратору
    компанії company_id береться з його власного запису в employees.
    """

    #: Вид: «Тягач» або вид причепа. «Тягач чи причіп» окремо не питаємо —
    #: це з нього й випливає.
    type = State()
    company = State()
    #: Марку обирають із довідника…
    mark = State()
    #: …або вводять нову, і вона одразу туди потрапляє.
    mark_name = State()
    license_plate = State()
    confirm = State()


class VehicleEdit(StatesGroup):
    """Редагування наявного транспорту з його картки."""

    #: Вид і марка обираються кнопками, тому мають власні стани.
    type = State()
    mark = State()
    mark_name = State()
    license_plate = State()


class TripForm(StatesGroup):
    """Створення рейсу.

    Компанія-власник і дані менеджера власних кроків не мають: вони
    підтягуються з employees того, хто заповнює форму. Замовник — має:
    рейс возять для чужої компанії.
    """

    ttn = State()
    arrival_date = State()
    #: Замовника обирають зі списку компаній…
    client = State()
    #: …або вводять назву руками, якщо його в системі немає.
    client_name = State()
    exporter = State()
    #: Тягач і причіп обирають із довідника vehicles…
    truck = State()
    #: …або вводять руками, якщо машина чужа. Причіп у ручній гілці ще й
    #: питає вид — у довіднику він береться із самого запису.
    truck_manual = State()
    truck_plate = State()
    trailer = State()
    trailer_manual = State()
    trailer_type = State()
    trailer_plate = State()
    grain = State()
    #: Водія обирають зі складу компанії…
    driver = State()
    #: …або вводять руками, якщо це сторонній перевізник.
    driver_name = State()
    driver_phone = State()
    confirm = State()


class TripEdit(StatesGroup):
    """Редагування рейсу з картки.

    Стан один на всі текстові поля: що саме редагуємо — лежить у даних FSM,
    інакше знадобився б окремий стан і окремий хендлер на кожне з півтора
    десятка полів.
    """

    value = State()
    #: Дата, компанія-експортер і статус обираються кнопками, тому мають свої
    #: стани: за станом визначається, який саме крок чекає на натискання.
    arrival_date = State()
    exporter = State()
    status = State()
    #: Транспорт — вибір із довідника або ручний ввід, як і в анкеті.
    truck = State()
    trailer = State()
    vehicle_name = State()
    vehicle_type = State()
    vehicle_plate = State()
    #: Водій — теж кнопка, але з двома гілками: вибір зі складу компанії…
    driver = State()
    #: …або ручний ввід стороннього перевізника, і тоді потрібні два кроки.
    driver_name = State()
    driver_phone = State()
