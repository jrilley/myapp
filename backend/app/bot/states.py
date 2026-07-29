from aiogram.fsm.state import State, StatesGroup


class ApplicationForm(StatesGroup):
    """Покрокова анкета. При невалідному вводі лишаємось у поточному стані,
    щоб уже введені відповіді не губились."""

    full_name = State()
    contact = State()
    category = State()
    description = State()
    confirm = State()
