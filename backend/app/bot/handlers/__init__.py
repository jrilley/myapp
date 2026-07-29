from aiogram import Router

from app.bot.handlers import admin, common, form


def build_router() -> Router:
    """Порядок важливий: common перехоплює /start та /cancel у будь-якому
    стані, тому має бути підключений раніше за стан-залежні хендлери форми."""
    router = Router(name="root")
    router.include_router(common.router)
    router.include_router(admin.router)
    router.include_router(form.router)
    return router


__all__ = ["build_router"]
