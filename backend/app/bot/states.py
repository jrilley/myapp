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
    """Додавання посади в довідник."""

    name = State()


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
