import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.deps import get_publisher
from app.config import Settings, get_settings
from app.db import Base, get_db
from app.main import create_app
from app.models import Application

TEST_ADMIN_TOKEN = "test-admin-token"


class FakePublisher:
    """Підміна TelegramPublisher — тести не мають ходити в мережу."""

    def __init__(self) -> None:
        self.published: list[int] = []
        self.retracted: list[tuple[int, int]] = []
        self.chat_id = -1001234567890
        self.message_id = 555

    async def publish(self, application: Application) -> tuple[int, int] | None:
        self.published.append(application.id)
        return self.chat_id, self.message_id

    async def retract(self, chat_id: int, message_id: int) -> None:
        self.retracted.append((chat_id, message_id))


@pytest.fixture
async def engine():
    # StaticPool + in-memory: усі підключення бачать ту саму БД.
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def session(session_factory):
    async with session_factory() as s:
        yield s


@pytest.fixture
def publisher() -> FakePublisher:
    return FakePublisher()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        admin_api_token=TEST_ADMIN_TOKEN,
        run_bot=False,
        admin_telegram_ids="777",
        telegram_bot_token="",
    )


@pytest.fixture
async def client(session_factory, publisher, settings):
    app = create_app()

    async def _get_db():
        async with session_factory() as s:
            yield s

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_publisher] = lambda: publisher

    # ASGITransport не запускає lifespan — бот у тестах не піднімається,
    # що нам і потрібно.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
