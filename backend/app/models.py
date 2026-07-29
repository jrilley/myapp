import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ApplicationStatus(str, enum.Enum):
    """Модерації зараз немає — заявка одразу `published`.

    Решта значень закладені наперед, щоб увімкнути модерацію
    без міграції схеми: достатньо змінити значення за замовчуванням.
    """

    pending = "pending"
    published = "published"
    rejected = "rejected"
    deleted = "deleted"


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # BigInteger обов'язково: Telegram user id не вміщується в int32.
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64))

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, native_enum=False, length=16),
        nullable=False,
        default=ApplicationStatus.published,
        index=True,
    )

    # Зберігаємо координати опублікованого повідомлення, щоб потім
    # прибрати його з групи разом із видаленням заявки.
    group_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    group_message_id: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    # Soft delete: заявки — це персональні дані й історія звернень,
    # безповоротне стирання однією командою в чаті надто легко зробити помилково.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_applications_visible", "deleted_at", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Application id={self.id} status={self.status} category={self.category!r}>"
