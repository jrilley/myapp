"""Тести гортання списків.

Один хендлер обслуговує всі списки, тому перевіряємо і правильність
сторінок, і те, що права перевіряються для кожного виду окремо —
offset і вид списку приходять із callback_data, яку можна підмінити.
"""

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app import repository
from app.bot.access import ROLE_MAIN_ADMIN, ROLE_USER
from app.bot.handlers.common import on_my, on_noop, on_page
from app.bot.keyboards import (
    MENU_BACK,
    NOOP,
    PAGE_APPLICATIONS,
    PAGE_PREFIX,
    PAGE_REFERENCE,
)
from app.models import Company, Position, Role
from tests.conftest import (
    ADMIN_ID,
    OWNER_ID,
    FakeCallback,
    FakeUser,
    callback_data,
    make_access,
)


@pytest.fixture
def state() -> FSMContext:
    return FSMContext(
        storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=OWNER_ID)
    )


async def _applications(session, count: int, *, owner: int = OWNER_ID):
    for index in range(count):
        await repository.create_application(
            session,
            telegram_user_id=owner,
            telegram_username="tester",
            full_name="Іван Петренко",
            contact="+380000000000",
            category="Інше",
            description=f"заявка номер {index:02d}",
        )


def _nav(markup) -> list[str]:
    """Кнопки навігації — усе, крім кнопок самих елементів і «Меню»."""
    return [
        data
        for data in callback_data(markup)
        if data == NOOP or data.startswith(f"{PAGE_PREFIX}:")
    ]


# ---------------------------------------------------------------------------
# Наявність і склад навігації
# ---------------------------------------------------------------------------


async def test_short_list_has_no_pagination(session, state, access):
    await _applications(session, PAGE_APPLICATIONS)
    callback = FakeCallback("menu:my")

    await on_my(callback, state, session, access)

    assert _nav(callback.message.markups[0]) == []


async def test_first_page_offers_only_forward(session, state, access):
    await _applications(session, PAGE_APPLICATIONS + 1)
    callback = FakeCallback("menu:my")

    await on_my(callback, state, session, access)

    assert _nav(callback.message.markups[0]) == [
        NOOP, f"{PAGE_PREFIX}:my:{PAGE_APPLICATIONS}"
    ]


async def test_last_page_offers_only_back(session, session_factory, access):
    await _applications(session, PAGE_APPLICATIONS + 1)
    callback = FakeCallback(f"{PAGE_PREFIX}:my:{PAGE_APPLICATIONS}")

    await on_page(callback, session, access)

    assert _nav(callback.message.markups[0]) == [f"{PAGE_PREFIX}:my:0", NOOP]


async def test_middle_page_offers_both_directions(session, access):
    await _applications(session, PAGE_APPLICATIONS * 3)
    callback = FakeCallback(f"{PAGE_PREFIX}:my:{PAGE_APPLICATIONS}")

    await on_page(callback, session, access)

    assert _nav(callback.message.markups[0]) == [
        f"{PAGE_PREFIX}:my:0", NOOP, f"{PAGE_PREFIX}:my:{PAGE_APPLICATIONS * 2}"
    ]


async def test_menu_button_stays_last(session, access):
    await _applications(session, PAGE_APPLICATIONS + 1)
    callback = FakeCallback(f"{PAGE_PREFIX}:my:0")

    await on_page(callback, session, access)

    assert callback_data(callback.message.markups[0])[-1] == MENU_BACK


# ---------------------------------------------------------------------------
# Вміст сторінок
# ---------------------------------------------------------------------------


async def test_pages_do_not_overlap(session, access):
    await _applications(session, PAGE_APPLICATIONS * 2)

    first = FakeCallback(f"{PAGE_PREFIX}:my:0")
    await on_page(first, session, access)
    second = FakeCallback(f"{PAGE_PREFIX}:my:{PAGE_APPLICATIONS}")
    await on_page(second, session, access)

    page_one = first.message.edits[0]
    page_two = second.message.edits[0]
    # Найновіші зверху: на першій сторінці — останні створені.
    assert "заявка номер 09" in page_one
    assert "заявка номер 09" not in page_two
    assert "заявка номер 00" in page_two


async def test_page_is_edited_not_resent(session, access):
    await _applications(session, PAGE_APPLICATIONS + 1)
    callback = FakeCallback(f"{PAGE_PREFIX}:my:{PAGE_APPLICATIONS}")

    await on_page(callback, session, access)

    # Гортання має міняти те саме повідомлення, а не слати нове.
    assert callback.message.edits
    assert not callback.message.answers


async def test_header_reports_the_visible_range(session, access):
    await _applications(session, PAGE_APPLICATIONS * 2)
    callback = FakeCallback(f"{PAGE_PREFIX}:my:{PAGE_APPLICATIONS}")

    await on_page(callback, session, access)

    assert f"{PAGE_APPLICATIONS + 1}–{PAGE_APPLICATIONS * 2} з {PAGE_APPLICATIONS * 2}" \
        in callback.message.edits[0]


# ---------------------------------------------------------------------------
# Права та стійкість до підробки
# ---------------------------------------------------------------------------


async def test_all_applications_page_rejects_non_admin(session, access):
    await _applications(session, PAGE_APPLICATIONS + 1)
    callback = FakeCallback(f"{PAGE_PREFIX}:all:0", user=FakeUser(OWNER_ID))

    await on_page(callback, session, access)

    assert callback.answered == ["Дія доступна лише адміністраторам."]
    assert not callback.message.edits


@pytest.mark.parametrize("kind", ["emp", "pos", "comp"])
async def test_management_pages_reject_non_main_admin(session, access, kind):
    callback = FakeCallback(f"{PAGE_PREFIX}:{kind}:0", user=FakeUser(OWNER_ID))

    await on_page(callback, session, access)

    assert callback.answered == ["Дія доступна лише головному адміністратору."]
    assert not callback.message.edits


async def test_unregistered_cannot_page_own_applications(session, access_guest):
    callback = FakeCallback(f"{PAGE_PREFIX}:my:0")

    await on_page(callback, session, access_guest)

    assert callback.answered == ["Спершу зареєструйтесь."]


@pytest.mark.parametrize("payload", ["page:my:abc", "page:my", "page:unknown:0"])
async def test_malformed_page_payload_does_not_crash(session, access, payload):
    callback = FakeCallback(payload)

    await on_page(callback, session, access)

    assert callback.answered  # відповіли помилкою, а не впали
    assert not callback.message.edits


async def test_page_counter_is_answered(session):
    """Інакше на кнопці «2 / 5» лишається годинник."""
    callback = FakeCallback(NOOP)

    await on_noop(callback)

    assert callback.answered == [None]


# ---------------------------------------------------------------------------
# Довідники
# ---------------------------------------------------------------------------


async def test_reference_lists_paginate(session):
    admin = make_access(ADMIN_ID, role=ROLE_MAIN_ADMIN)
    session.add(Role(id=1, role=ROLE_MAIN_ADMIN))
    session.add(Role(id=3, role=ROLE_USER))
    for index in range(PAGE_REFERENCE + 2):
        session.add(Position(position=f"Посада {index:02d}"))
        session.add(
            Company(name=f"Компанія {index:02d}", tax_id=f"{index:08d}", address="Київ")
        )
    await session.commit()

    for kind in ("pos", "comp"):
        callback = FakeCallback(f"{PAGE_PREFIX}:{kind}:0", user=FakeUser(ADMIN_ID))

        await on_page(callback, session, admin)

        assert callback.message.edits
        assert _nav(callback.message.markups[0]) == [
            NOOP, f"{PAGE_PREFIX}:{kind}:{PAGE_REFERENCE}"
        ]
