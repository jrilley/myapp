from html import escape

from app.models import Application


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


def format_own_application(application: Application) -> str:
    return (
        f"#{application.id} — {escape(application.category)}\n"
        f"{escape(application.description[:120])}"
        f"{'…' if len(application.description) > 120 else ''}"
    )
