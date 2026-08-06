"""Що робити, коли хендлер упав.

Досі не робилось нічого. Для людини це виглядало як мовчання: кнопка
натиснута, відповіді немає, зрозуміти чому — неможливо. А до розробника
помилка доходила лише тому, що хтось помітив traceback у консолі й переслав
його вручну.

Тому дві речі. Користувачу — коротка чесна відповідь, щоб він не чекав
даремно. Головному адміністратору — сам traceback і те, на чому саме впало:
хто натиснув, що натиснув, у якому чаті.
"""

import logging
import traceback

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ErrorEvent
from aiogram.types.update import UpdateTypeLookupError
from html import escape

from app.config import Settings

logger = logging.getLogger(__name__)

router = Router(name="errors")

APOLOGY = "Щось пішло не так. Спробуйте ще раз або натисніть /start."

#: Скільки символів traceback лишаємо. Telegram обмежує повідомлення 4096
#: символами, а корисне майже завжди в кінці — там, де воно й упало.
TRACE_TAIL = 2500


def _origin(event: ErrorEvent) -> tuple[int | None, str, int | None]:
    """(куди відповісти, що людина зробила, хто вона).

    Апдейти бувають різні, а до збою призводять два: натиснута кнопка й
    надісланий текст. Решту описуємо типом — цього досить, щоб зрозуміти,
    звідки прийшло. Розбираємо руками, а не через Update.event: той кидає
    виняток на нерозпізнаному типі, а падати в обробнику падінь нікуди.
    """
    update = event.update
    callback = update.callback_query
    if callback is not None:
        message = callback.message
        return (
            message.chat.id if message is not None else None,
            f"кнопка {callback.data!r}",
            callback.from_user.id if callback.from_user is not None else None,
        )
    if update.message is not None:
        user = update.message.from_user
        return (
            update.message.chat.id,
            f"повідомлення {update.message.text!r}",
            user.id if user is not None else None,
        )
    # event_type кидає UpdateTypeLookupError, якщо тип апдейту незнайомий —
    # а це рівно та ситуація, у якій ми сюди й потрапили.
    try:
        what = str(update.event_type)
    except UpdateTypeLookupError:
        what = "невідомий тип апдейту"
    return None, what, None


def _report(event: ErrorEvent) -> str:
    chat_id, what, user_id = _origin(event)
    who = str(user_id) if user_id is not None else "невідомо"
    trace = "".join(
        traceback.format_exception(
            type(event.exception), event.exception, event.exception.__traceback__
        )
    )
    return (
        f"💥 <b>Помилка в боті</b>\n"
        f"Користувач: <code>{who}</code>\n"
        f"Чат: <code>{chat_id}</code>\n"
        f"Дія: {escape(what)}\n\n"
        f"<pre>{escape(trace[-TRACE_TAIL:])}</pre>"
    )


@router.errors()
async def on_error(event: ErrorEvent, bot: Bot, settings: Settings) -> None:
    """Ковтає будь-який збій хендлера: повернути помилку в aiogram означало б
    лише повторити її в логах."""
    logger.exception("Необроблена помилка", exc_info=event.exception)

    chat_id, _, _ = _origin(event)
    if chat_id is not None:
        # Кожен наступний виклик тут може впасти так само, і другий збій уже
        # нікому доповідати — тож обидва загорнуті.
        try:
            await bot.send_message(chat_id, APOLOGY)
        except TelegramAPIError:
            logger.warning("Не вдалося вибачитись у чаті %s", chat_id)

    report = _report(event)
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, report)
        except TelegramAPIError:
            logger.warning("Не вдалося доповісти адміну %s", admin_id)
