import secrets

from fastapi import Depends, Header, HTTPException, Request, status

from app.bot.publisher import NullPublisher, Publisher
from app.config import Settings, get_settings


def get_publisher(request: Request) -> Publisher:
    """Publisher кладеться в app.state під час lifespan.
    Якщо бот вимкнено (RUN_BOT=false) — це NullPublisher."""
    return getattr(request.app.state, "publisher", None) or NullPublisher()


def require_admin_token(
    x_admin_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Простий спільний секрет.

    Свідомо мінімальний механізм: він захищає від стороннього видалення,
    але це НЕ повноцінна авторизація — немає ролей, ротації й аудиту.
    Коли з'являться справжні акаунти адміністраторів, це місце треба замінити.
    """
    expected = settings.admin_api_token
    if not expected:
        # Порожній секрет у конфізі не має означати «вхід усім».
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_API_TOKEN не налаштовано",
        )
    if not x_admin_token or not secrets.compare_digest(x_admin_token, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Невірний X-Admin-Token"
        )
