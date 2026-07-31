from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _apply_sqlite_pragmas(engine: AsyncEngine) -> None:
    """WAL дозволяє читати під час запису — важливо, бо бот і API ділять файл."""

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_connection, _connection_record):  # pragma: no cover
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_engine(database_url: str, **kwargs) -> AsyncEngine:
    """**kwargs потрібні тестам (StaticPool, connect_args), і саме тому вони
    ходять сюди, а не створюють engine самі: інакше тестова БД лишалась би
    без PRAGMA foreign_keys і не перевіряла б зовнішні ключі взагалі."""
    engine = create_async_engine(database_url, future=True, **kwargs)
    if database_url.startswith("sqlite"):
        _apply_sqlite_pragmas(engine)
    return engine


engine = create_engine(get_settings().database_url)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """Залежність FastAPI. У тестах підмінюється через dependency_overrides."""
    async with SessionFactory() as session:
        yield session
