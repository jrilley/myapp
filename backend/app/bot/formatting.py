from html import escape

from app.models import Application, Trip


def format_for_group(application: Application) -> str:
    """Повідомлення для групи. Контакт тут є — так само, як і в публічному
    API та на сайті (див. schemas.ApplicationPublic)."""
    return (
        f"🆕 <b>Заявка #{application.id}</b>\n\n"
        f"<b>Категорія:</b> {escape(application.category)}\n"
        f"<b>Ім'я:</b> {escape(application.full_name)}\n"
        f"<b>Контакт:</b> {escape(application.contact)}\n\n"
        f"{escape(application.description)}"
    )


def format_summary(data: dict) -> str:
    """Підсумок анкети перед підтвердженням."""
    return (
        "<b>Перевірте заявку:</b>\n\n"
        f"<b>Категорія:</b> {escape(str(data.get('category', '')))}\n"
        f"<b>Ім'я:</b> {escape(str(data.get('full_name', '')))}\n"
        f"<b>Контакт:</b> {escape(str(data.get('contact', '')))}\n\n"
        f"{escape(str(data.get('description', '')))}"
    )


def _shorten(text: str, limit: int = 120) -> str:
    return escape(text[:limit]) + ("…" if len(text) > limit else "")


def format_own_application(application: Application) -> str:
    return f"#{application.id} — {escape(application.category)}\n{_shorten(application.description)}"


def format_admin_application(application: Application) -> str:
    """Для адмінського списку. На відміну від «моїх заявок», показує автора —
    у своєму списку він завжди той самий, а тут різні."""
    author = (
        f"@{escape(application.telegram_username)}"
        if application.telegram_username
        else f"id{application.telegram_user_id}"
    )
    return (
        f"#{application.id} — {escape(application.category)} · {author}\n"
        f"<b>{escape(application.full_name)}</b> · {escape(application.contact)}\n"
        f"{_shorten(application.description, 90)}"
    )


# ---------------------------------------------------------------------------
# Рейси
# ---------------------------------------------------------------------------


def company_label(company) -> str:
    """«Назва ІПН» — той самий вигляд, що й на кнопці вибору компанії."""
    if company is None:
        return "—"
    return f"{company.name} {company.tax_id}"


def _trip_body(
    *,
    ttn_num: str,
    arrival_date: str,
    client: str,
    exporter: str,
    logist_fullname: str,
    logist_phone_number: str,
    truck: str,
    truck_license_plate: str,
    trailer: str,
    trailer_type: str,
    trailer_license_plate: str,
    grain_type: str,
    driver_fullname: str,
    driver_phone_number: str,
) -> str:
    """Тіло рейсу — спільне для підсумку перед створенням і для картки.

    Одне джерело тексту навмисно: інакше людина підтверджувала б один набір
    полів, а в картці бачила інший.
    """
    return (
        f"<b>ТТН:</b> {escape(ttn_num)}\n"
        f"<b>Дата прибуття:</b> {escape(arrival_date)}\n\n"
        f"<b>Замовник:</b> {escape(client)}\n"
        f"<b>Експортер:</b> {escape(exporter)}\n"
        f"<b>Логіст:</b> {escape(logist_fullname)}, {escape(logist_phone_number)}\n\n"
        f"<b>Тягач:</b> {escape(truck)} · {escape(truck_license_plate)}\n"
        f"<b>Причіп:</b> {escape(trailer)} ({escape(trailer_type)}) · "
        f"{escape(trailer_license_plate)}\n"
        f"<b>Культура:</b> {escape(grain_type)}\n"
        f"<b>Водій:</b> {escape(driver_fullname)}, {escape(driver_phone_number)}"
    )


def format_trip_summary(data: dict, *, client: str, exporter: str) -> str:
    """Підсумок перед створенням. Показуємо рівно ті поля, які заповнює
    людина, плюс підставлені замовника й логіста — решта колонок при
    створенні порожні."""
    return "<b>Перевірте рейс:</b>\n\n" + _trip_body(
        client=client,
        exporter=exporter,
        **{
            name: data[name]
            for name in (
                "ttn_num", "arrival_date", "logist_fullname", "logist_phone_number",
                "truck", "truck_license_plate", "trailer", "trailer_type",
                "trailer_license_plate", "grain_type", "driver_fullname",
                "driver_phone_number",
            )
        },
    )


def format_trip(trip: Trip) -> str:
    """Картка рейсу. Поля, які заповнюють уже після створення (час на
    території, маси, слід редагування), показуються лише коли в них щось є."""
    text = f"🚛 <b>Рейс #{trip.id}</b> · {escape(trip.status)}\n\n" + _trip_body(
        ttn_num=trip.ttn_num,
        arrival_date=trip.arrival_date,
        client=company_label(trip.client_company),
        exporter=company_label(trip.exporter_company),
        logist_fullname=trip.logist_fullname,
        logist_phone_number=trip.logist_phone_number,
        truck=trip.truck,
        truck_license_plate=trip.truck_license_plate,
        trailer=trip.trailer,
        trailer_type=trip.trailer_type,
        trailer_license_plate=trip.trailer_license_plate,
        grain_type=trip.grain_type,
        driver_fullname=trip.driver_fullname,
        driver_phone_number=trip.driver_phone_number,
    )

    extras = []
    if trip.datetime_entry:
        extras.append(f"<b>Заїзд:</b> {escape(trip.datetime_entry)}")
    if trip.datetime_departure:
        extras.append(f"<b>Виїзд:</b> {escape(trip.datetime_departure)}")
    if trip.b_mass or trip.t_mass or trip.n_mass:
        extras.append(
            f"<b>Маса, кг:</b> брутто {trip.b_mass} · тара {trip.t_mass} · "
            f"нетто {trip.n_mass}"
        )
    if trip.updated_at:
        extras.append(f"<i>Змінено: {escape(trip.updated_at)}</i>")
    if extras:
        text += "\n\n" + "\n".join(extras)
    return text


def format_trip_row(trip: Trip) -> str:
    """Рядок списку: стільки, щоб упізнати рейс, не відкриваючи картку."""
    return (
        f"#{trip.id} · ТТН {escape(trip.ttn_num)} · {escape(trip.arrival_date)}\n"
        f"{escape(trip.truck_license_plate)} / {escape(trip.trailer_license_plate)} · "
        f"{escape(trip.grain_type)} · {escape(trip.status)}"
    )
