import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import get_settings
from app.db import Base, create_engine

# Імпорт моделей обов'язковий: без нього Base.metadata порожня
# і autogenerate вирішить, що треба видалити всі таблиці.
import app.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    return get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite не вміє більшість ALTER — batch-режим перебудовує таблицю.
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()

    if connection.dialect.name == "sqlite":
        # Ключі під час міграцій вимкнені (див. _disable_foreign_keys), тож
        # звіряємо цілісність самі. Краще впасти тут, ніж лишити в базі
        # посилання в нікуди. Транзакція вище вже закрита — це чисте читання.
        broken = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        if broken:
            raise RuntimeError(
                "Міграція лишила посилання в нікуди "
                f"(таблиця, rowid, ціль, номер ключа): {broken}"
            )


def _disable_foreign_keys(engine: AsyncEngine) -> None:
    """Вимикає перевірку зовнішніх ключів на час міграцій.

    Batch-режим перебудовує таблицю через CREATE tmp → DROP стара → RENAME,
    а DROP батьківської таблиці з увімкненими ключами SQLite не пропускає —
    навіть якщо після перейменування все знову цілісне.

    Ставимо саме на «connect», а не окремим запитом: PRAGMA не діє всередині
    транзакції, а будь-який exec_driver_sql на з'єднанні SQLAlchemy її
    відкриває — і тоді коміт міграції дістається зовнішній транзакції, якої
    ніхто не комітить, тож зміни мовчки відкочуються при закритті.

    Обробник вішається після того, який ставить app.db, і перекриває його:
    події SQLAlchemy виконуються в порядку реєстрації.
    """

    @event.listens_for(engine.sync_engine, "connect")
    def _off(dbapi_connection, _connection_record):  # pragma: no cover
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.close()


async def run_migrations_online() -> None:
    engine: AsyncEngine = create_engine(_database_url())
    if engine.dialect.name == "sqlite":
        _disable_foreign_keys(engine)
    async with engine.connect() as connection:
        await connection.run_sync(_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
