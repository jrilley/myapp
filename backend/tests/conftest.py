import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_publisher
from app.bot.access import ROLE_MAIN_ADMIN, ROLE_USER, Access
from app.config import Settings, get_settings
from app.db import Base, create_engine, get_db
from app.main import create_app
from app.models import Application, Employee, Role

TEST_ADMIN_TOKEN = "test-admin-token"

OWNER_ID = 1001
ADMIN_ID = 777
STRANGER_ID = 2002


class FakeUser:
    def __init__(self, user_id: int = OWNER_ID, username: str | None = "tester"):
        self.id = user_id
        self.username = username


class FakeMessage:
    """Мінімальний двійник aiogram.types.Message — рівно ті методи,
    які викликають хендлери."""

    def __init__(self, text: str | None = None, user: FakeUser | None = None):
        self.text = text
        self.from_user = user or FakeUser()
        self.answers: list[str] = []
        self.edits: list[str] = []
        self.markups: list[object] = []

    async def answer(self, text: str, reply_markup=None, **_kwargs) -> "FakeMessage":
        self.answers.append(text)
        self.markups.append(reply_markup)
        return self

    async def edit_text(self, text: str, reply_markup=None, **_kwargs) -> "FakeMessage":
        self.edits.append(text)
        self.markups.append(reply_markup)
        return self


class FakeCallback:
    def __init__(self, data: str, user: FakeUser | None = None):
        self.data = data
        self.from_user = user or FakeUser()
        self.message = FakeMessage(user=user)
        self.answered: list[str | None] = []

    async def answer(self, text: str | None = None, **_kwargs) -> None:
        self.answered.append(text)


def make_access(
    user_id: int = OWNER_ID,
    *,
    role: str = ROLE_USER,
    registered: bool = True,
    bootstrap_admin: bool = False,
) -> Access:
    """Access без походу в БД: він читає лише employee.role.role і fullname,
    тож транзієнтних об'єктів достатньо."""
    employee = None
    if registered:
        employee = Employee(
            tg_id=user_id,
            fullname="Тестовий Співробітник",
            phone_number="+380000000000",
            company_id=1,
            position_id=1,
            role_id=1,
        )
        employee.role = Role(id=1, role=role)
    return Access(
        telegram_user_id=user_id,
        employee=employee,
        bootstrap_admin=bootstrap_admin,
    )


@pytest.fixture
def access() -> Access:
    """Звичайний зареєстрований користувач."""
    return make_access(OWNER_ID)


@pytest.fixture
def access_admin() -> Access:
    return make_access(ADMIN_ID, role=ROLE_MAIN_ADMIN)


@pytest.fixture
def access_guest() -> Access:
    """Незареєстрований — йому доступна лише реєстрація."""
    return make_access(STRANGER_ID, registered=False)


def callback_data(markup) -> list[str]:
    """Плоский список callback_data з inline-клавіатури."""
    if markup is None:
        return []
    return [b.callback_data for row in markup.inline_keyboard for b in row]


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
    # Через app.db.create_engine, а не напряму, — щоб застосувались ті самі
    # PRAGMA, що й у бойовій БД (зокрема foreign_keys=ON).
    engine = create_engine(
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
