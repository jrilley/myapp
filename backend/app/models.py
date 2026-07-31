import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    """Заявка, надіслана через Telegram-бота.

    Описи полів живуть у `doc=` і звідти потрапляють у docs/schema.json
    (scripts/dump_schema.py). `doc` — метадані рівня Python: у DDL вони не
    йдуть, тож на міграції не впливають.
    """

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        doc="Номер заявки. Його бачить користувач у «#N» і передає в /delete.",
    )

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True,
        doc="Автор заявки. BigInteger обов'язково: Telegram id не вміщується в int32.",
    )
    telegram_username: Mapped[str | None] = mapped_column(
        String(64),
        doc="@username автора, якщо він є — у Telegram він не обов'язковий.",
    )

    full_name: Mapped[str] = mapped_column(
        String(200), nullable=False, doc="Крок 1 анкети: ПІБ."
    )
    contact: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="Крок 2 анкети. Публічний за рішенням замовника — бот попереджає.",
    )
    category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        doc="Крок 3 анкети, значення з фіксованого списку app/bot/constants.py.",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Крок 4 анкети. Text, а не String: довжину обмежує бот, не схема.",
    )

    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus, native_enum=False, length=16),
        nullable=False,
        default=ApplicationStatus.published,
        index=True,
        doc="Модерації немає, тому при створенні завжди published.",
    )

    group_chat_id: Mapped[int | None] = mapped_column(
        BigInteger,
        doc="Куди опубліковано. Порожнє, якщо публікація не вдалася.",
    )
    group_message_id: Mapped[int | None] = mapped_column(
        Integer,
        doc="Без нього неможливо прибрати повідомлення з групи при видаленні.",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        doc="Проставляє БД. За ним сортується список на сайті.",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        doc="Оновлюється автоматично при кожній зміні рядка.",
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        doc=(
            "Мітка м'якого видалення; NULL = заявка жива. Рядок не стирається: "
            "заявки — персональні дані й історія звернень."
        ),
    )

    __table_args__ = (
        # Під основний запит сайту: живі заявки, новіші вгорі.
        Index("ix_applications_visible", "deleted_at", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Application id={self.id} status={self.status} category={self.category!r}>"


# ---------------------------------------------------------------------------
# Компанії, довідники та співробітники
# ---------------------------------------------------------------------------


class Company(Base):
    """Компанія, до якої належать співробітники."""

    __tablename__ = "company"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, doc="Назва компанії.")
    tax_id: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, doc="Податковий номер, унікальний."
    )
    address: Mapped[str] = mapped_column(Text, nullable=False, doc="Адреса компанії.")

    employees: Mapped[list["Employee"]] = relationship(back_populates="company")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Company id={self.id} name={self.name!r}>"


class Position(Base):
    """Довідник посад."""

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    position: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, doc="Назва посади, унікальна."
    )

    employees: Mapped[list["Employee"]] = relationship(back_populates="position")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Position id={self.id} position={self.position!r}>"


class Role(Base):
    """Довідник ролей доступу."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, doc="Назва ролі, унікальна."
    )

    employees: Mapped[list["Employee"]] = relationship(back_populates="role")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Role id={self.id} role={self.role!r}>"


class Employee(Base):
    """Співробітник компанії, ідентифікований за Telegram-акаунтом."""

    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # BigInteger, а не INTEGER зі схеми: у SQLite INTEGER і так 64-бітний, але
    # в PostgreSQL він 32-бітний, і Telegram-id туди не влізе. Та сама причина,
    # що й для applications.telegram_user_id.
    tg_id: Mapped[int] = mapped_column(
        BigInteger, nullable=False, unique=True, doc="Telegram user id, унікальний."
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("company.id"), nullable=False, doc="Компанія співробітника."
    )
    fullname: Mapped[str] = mapped_column(Text, nullable=False, doc="ПІБ співробітника.")
    phone_number: Mapped[str] = mapped_column(
        Text, nullable=False, doc="Номер телефону."
    )
    position_id: Mapped[int] = mapped_column(
        ForeignKey("positions.id"), nullable=False, doc="Посада з довідника positions."
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id"), nullable=False, doc="Роль доступу з довідника roles."
    )

    company: Mapped["Company"] = relationship(back_populates="employees")
    position: Mapped["Position"] = relationship(back_populates="employees")
    role: Mapped["Role"] = relationship(back_populates="employees")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Employee id={self.id} tg_id={self.tg_id} fullname={self.fullname!r}>"
