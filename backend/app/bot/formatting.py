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
