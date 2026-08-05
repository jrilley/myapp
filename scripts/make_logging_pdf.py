"""Генерує docs/logging-plan.pdf — план журналу подій.

Запуск (з кореня репозиторію):
    backend/.venv/Scripts/python.exe scripts/make_logging_pdf.py    # Windows
    backend/.venv/bin/python scripts/make_logging_pdf.py            # Unix

Це ПЛАН, а не опис наявного коду: журналу подій у проєкті ще немає. Тому
файл, на відміну від schema.pdf, не звіряється з моделями — його джерело
тут, у цьому скрипті. Коли журнал з'явиться, таблицю варто буде описати
в app/models.py і перенести аркуш 2 у schema.pdf.
"""

from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen import canvas as pdfcanvas

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _sheet import (  # noqa: E402
    AMBER,
    AMBER_SOFT,
    INK,
    LINE,
    LINE_SOFT,
    PANEL,
    PANEL_ALT,
    RUST,
    SLATE,
    TEAL,
    Sheet,
    register_fonts,
)

# --------------------------------------------------------------------------
# Зміст плану
# --------------------------------------------------------------------------
# Без емодзі: в Arial цих гліфів немає, у PDF вони виходять порожніми
# квадратами.

PIPELINE = [
    ("telegram", "Апдейт", "Натискання кнопки, команда або текст у анкеті.",
     "human"),
    ("middleware 1", "DbSessionMiddleware", "Відкриває сесію БД на цей апдейт.",
     None),
    ("middleware 2", "AccessMiddleware", "Рахує роль і компанію з employees.",
     None),
    ("middleware 3", "EventLogMiddleware", "Пише подію. Одна точка на всі дії.",
     "core"),
    ("aiogram", "Хендлер", "Робить те, що просили. Про журнал не знає.", None),
    ("telegram", "Відповідь", "Тривалість і результат вертаються в подію.",
     None),
]

SEES_ITSELF = [
    ("хто", "tg_id, employee_id, company_id — з Access, який уже порахований"),
    ("що", "команда, callback_data або факт текстового вводу"),
    ("де", "FSM-стан на момент події: TripForm.ttn, TripEdit.value"),
    ("коли", "мітка часу, ISO-8601 UTC"),
    ("скільки", "тривалість хендлера, мілісекунди"),
    ("чим скінчилось", "ok або клас винятку"),
    ("чи не двічі", "update_id: Telegram повторює доставку при збої мережі"),
]

EXPLICIT = [
    ("denied", "Відмова через права. Хендлер відповідає штатно, збоку це не\n"
               "видно — тому пишемо самі."),
    ("invalid", "Ввід не пройшов перевірку: поле й причина. Значення — ні."),
    ("flow", "Віхи анкети: form_started, form_submitted, form_abandoned."),
    ("dead_end", "Вихід у меню одразу після відкриття екрана."),
]

NEVER = (
    "Ніколи не пишемо ЗНАЧЕННЯ, які ввела людина: текст повідомлення, ПІБ, "
    "номери телефонів, номер ТТН, держномери. Пишемо ім'я поля й результат "
    "перевірки — цього досить, щоб побачити, де люди спотикаються, і це не "
    "перетворює журнал на другу копію персональних даних. payload — білий "
    "список ключів (trip_id, company_id, field, reason), а не «все, що є»."
)

STAGES = [
    ("01", "Таблиця й middleware", "плюс вимикач у .env"),
    ("02", "Явні події", "denied, invalid, flow"),
    ("03", "Екран «Активність»", "головному адміну, у боті"),
    ("04", "Ретенція й агрегати", "сирі події живуть обмежено"),
]

EVENT_COLUMNS = [
    ("id", "INTEGER", "PK"),
    ("ts", "TEXT NOT NULL", ""),
    ("update_id", "INTEGER", "UQ"),
    ("tg_id", "BIGINT", ""),
    ("employee_id", "INTEGER", "FK"),
    ("company_id", "INTEGER", "FK"),
    ("kind", "TEXT NOT NULL", ""),
    ("name", "TEXT NOT NULL", ""),
    ("state", "TEXT", ""),
    ("payload", "TEXT", ""),
    ("duration_ms", "INTEGER", ""),
    ("ok", "INTEGER NOT NULL", ""),
    ("error", "TEXT", ""),
]

KINDS = [
    ("command", "/start, /help, /cancel"),
    ("callback", "натискання інлайн-кнопки"),
    ("message", "текстовий ввід у стані анкети"),
    ("denied", "відмовлено через права"),
    ("invalid", "ввід не пройшов перевірку"),
    ("flow", "віха анкети: почав, надіслав, кинув"),
    ("error", "виняток у хендлері"),
]

QUESTIONS = [
    ("Воронка рейсу",
     "скільки почали анкету, дійшли до кроку N, підтвердили"),
    ("Де кидають",
     "останній стан перед мовчанням понад 15 хвилин"),
    ("Які поля дратують",
     "kind=invalid, згруповано за полем — топ за тиждень"),
    ("Куди тиснуться без прав",
     "kind=denied: або модель прав крива, або кнопка веде не туди"),
    ("Глухі кути",
     "екрани, з яких одразу виходять у меню"),
    ("Повільні місця",
     "p95 duration_ms за name"),
    ("Хто користується",
     "активні люди за тиждень, у розрізі компаній"),
]

READING = [
    ("у боті", "«Активність» головному адміну: 7 днів, топ дій, відмови, "
               "незавершені анкети"),
    ("через API", "GET /api/admin/events за X-Admin-Token — той самий секрет, "
                  "що й для заявок"),
    ("руками", "SQL по events: сесія рахується запитом, а не зберігається "
               "колонкою"),
]


# --------------------------------------------------------------------------
# Аркуш 1 — звідки беруться події
# --------------------------------------------------------------------------
def page_pipeline(s: Sheet) -> None:
    s.background()
    M = 40

    s.eyebrow(M, 46, "myapp · план", color=TEAL)
    s.text(M, 76, "Журнал подій", font="Sans-Bold", size=25, color=INK)
    s.wrap(M, 96, 760,
           "Мета — бачити, куди люди тиснуть, де спотикаються і що в них не "
           "виходить. Ключове рішення: події пише middleware, а не хендлери. "
           "Через нього проходить кожен апдейт, тож логування неможливо забути "
           "при додаванні нового екрана — рівно так само, як edited_by "
           "проставляє репозиторій, а не той, хто пише редактор.",
           size=8.6, leading=11.5)
    s.text(s.W - M, 76, "аркуш 1 / 2", font="Mono", size=8, color=SLATE,
           align="right")

    ty = s.section(M, 150, s.W - 2 * M, "тракт одного апдейта")
    node_w = (s.W - 2 * M - 5 * 14) / 6
    for i, (kind, title, detail, accent) in enumerate(PIPELINE):
        x = M + i * (node_w + 14)
        s.node(x, ty, node_w, 96, kind, title, detail, accent=accent)
        if i:
            s.arrow(x - 13, ty + 48, x - 1, ty + 48)

    note_ty = ty + 112
    s.box(M, note_ty, s.W - 2 * M, 44, fill=AMBER_SOFT, stroke=AMBER_SOFT)
    s.line(M, note_ty, M, note_ty + 44, color=AMBER, width=2.5)
    s.wrap(M + 12, note_ty + 18, s.W - 2 * M - 24,
           "Запис події не має права зламати дію. Помилка журналу гаситься й "
           "іде в лог процесу, а не до користувача, і коміт події окремий від "
           "коміту дії — інакше збій запису статистики відкотив би створений "
           "рейс.",
           size=8, leading=10.5, color=AMBER)

    col_w = (s.W - 2 * M - 40) / 2
    right_x = M + col_w + 40

    ty2 = s.section(M, 400, col_w, "що middleware бачить сам")
    for i, (label, what) in enumerate(SEES_ITSELF):
        row = ty2 + 12 + i * 17
        s.text(M, row, label, font="Sans-Bold", size=8, color=INK)
        s.text(M + 96, row, what, font="Mono", size=7, color=SLATE)

    ty3 = s.section(right_x, 400, col_w, "що доводиться писати явно")
    row = ty3 + 6
    for name, detail in EXPLICIT:
        s.box(right_x, row, col_w, 30, fill=PANEL, stroke=LINE)
        s.line(right_x, row, right_x, row + 30, color=RUST, width=2.5)
        s.text(right_x + 10, row + 13, name, font="Mono-Bold", size=8,
               color=RUST)
        s.wrap(right_x + 78, row + 12, col_w - 88, detail.replace("\n", " "),
               size=7.2, leading=8.8)
        row += 36

    amber_ty = 588
    s.box(M, amber_ty, s.W - 2 * M, 52, fill=AMBER_SOFT, stroke=AMBER_SOFT)
    s.line(M, amber_ty, M, amber_ty + 52, color=AMBER, width=2.5)
    s.eyebrow(M + 12, amber_ty + 16, "чого не пишемо ніколи", color=AMBER)
    s.wrap(M + 12, amber_ty + 30, s.W - 2 * M - 24, NEVER,
           size=8, leading=10.5, color=AMBER)

    ty4 = s.section(M, 668, s.W - 2 * M, "порядок робіт")
    chip_w = (s.W - 2 * M - 3 * 12) / 4
    for i, (num, title, detail) in enumerate(STAGES):
        x = M + i * (chip_w + 12)
        s.box(x, ty4, chip_w, 44, fill=PANEL, stroke=LINE)
        s.line(x, ty4, x, ty4 + 44, color=TEAL, width=2.5)
        s.text(x + 10, ty4 + 18, num, font="Mono-Bold", size=9.5, color=TEAL)
        s.text(x + 32, ty4 + 18, title, font="Sans-Bold", size=8.5, color=INK)
        s.text(x + 32, ty4 + 33, detail, font="Mono", size=7, color=SLATE)

    s.line(M, s.H - 34, s.W - M, s.H - 34, color=LINE, width=0.6)
    s.text(M, s.H - 22,
           "Вимикач EVENT_LOG_ENABLED у .env: журнал має вимикатись без "
           "викочування нової версії.",
           font="Mono", size=7, color=SLATE)


# --------------------------------------------------------------------------
# Аркуш 2 — таблиця й що вона відповідає
# --------------------------------------------------------------------------
def page_table(s: Sheet) -> None:
    s.background()
    M = 40

    s.eyebrow(M, 46, "myapp · план", color=TEAL)
    s.text(M, 76, "Таблиця events", font="Sans-Bold", size=25, color=INK)
    s.wrap(M, 96, 760,
           "Один рядок — одна дія однієї людини. Сесію не зберігаємо колонкою: "
           "«візит» — це події одного tg_id з проміжком менше 30 хвилин, і "
           "рахується вона запитом. Так поріг можна змінити заднім числом, не "
           "переписуючи вже накопичене.",
           size=8.6, leading=11.5)
    s.text(s.W - M, 76, "аркуш 2 / 2", font="Mono", size=8, color=SLATE,
           align="right")

    left_w = 380
    ty = s.section(M, 150, left_w, "структура")
    s.entity(M, ty, left_w, "events", EVENT_COLUMNS)

    mid_x = M + left_w + 34
    mid_w = 300
    ty2 = s.section(mid_x, 150, mid_w, "kind")
    for i, (name, detail) in enumerate(KINDS):
        row = ty2 + 12 + i * 18
        s.box(mid_x, row - 11, 74, 15, fill=PANEL_ALT, stroke=LINE_SOFT)
        s.text(mid_x + 7, row, name, font="Mono", size=7.2, color=SLATE)
        s.text(mid_x + 84, row, detail, font="Sans", size=7.6, color=INK)

    idx_ty = ty2 + 12 + len(KINDS) * 18 + 16
    s.eyebrow(mid_x, idx_ty, "індекси", color=INK)
    for i, line in enumerate((
        "(ts)                  вибірка за період",
        "(tg_id, ts)           шлях однієї людини",
        "(kind, name, ts)      топи й воронки",
    )):
        s.text(mid_x, idx_ty + 16 + i * 13, line, font="Mono", size=7,
               color=SLATE)

    right_x = mid_x + mid_w + 34
    right_w = s.W - M - right_x
    ty3 = s.section(right_x, 150, right_w, "на які питання відповідає")
    row = ty3
    for i, (title, how) in enumerate(QUESTIONS, start=1):
        s.box(right_x, row, right_w, 34, fill=PANEL, stroke=LINE)
        s.line(right_x, row, right_x, row + 34, color=TEAL, width=2.5)
        s.text(right_x + 10, row + 15, f"{i:02d}", font="Mono-Bold", size=9,
               color=TEAL)
        s.text(right_x + 32, row + 15, title, font="Sans-Bold", size=8.6,
               color=INK)
        s.text(right_x + 32, row + 27, how, font="Mono", size=7, color=SLATE)
        row += 40

    ty4 = s.section(M, 560, s.W - 2 * M, "де це читати")
    for i, (where, what) in enumerate(READING):
        r = ty4 + 12 + i * 16
        s.text(M, r, where, font="Sans-Bold", size=8, color=INK)
        s.text(M + 96, r, what, font="Mono", size=7.2, color=SLATE)

    amber_ty = 640
    s.box(M, amber_ty, s.W - 2 * M, 60, fill=AMBER_SOFT, stroke=AMBER_SOFT)
    s.line(M, amber_ty, M, amber_ty + 60, color=AMBER, width=2.5)
    s.eyebrow(M + 12, amber_ty + 16, "ретенція, обсяг і межі", color=AMBER)
    s.wrap(M + 12, amber_ty + 30, s.W - 2 * M - 24,
           "tg_id — персональні дані, тому сирі події не живуть вічно: "
           "пропозиція — 90 днів, далі лишаються добові агрегати без "
           "прив'язки до людини. Обсяг невеликий: приблизно 10-30 подій на "
           "рейс, тобто близько 1500 на день при 50 рейсах — SQLite тримає це "
           "спокійно. Але писати в неї буде і бот, і журнал, а writer у SQLite "
           "один: коли записи почнуть конкурувати, журнал переїжджає в окремий "
           "файл events.db, і лише потім — у Postgres.",
           size=8, leading=10.5, color=AMBER)

    s.line(M, s.H - 34, s.W - M, s.H - 34, color=LINE, width=0.6)
    s.text(M, s.H - 22,
           "Це план, а не наявний код: таблиці events у проєкті ще немає.",
           font="Mono", size=7, color=SLATE)


def main() -> None:
    register_fonts()

    out = Path(__file__).resolve().parent.parent / "docs" / "logging-plan.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)

    width, height = landscape(A3)
    c = pdfcanvas.Canvas(str(out), pagesize=(width, height))
    c.setTitle("myapp — журнал подій, план")
    c.setAuthor("myapp")
    c.setSubject("Що логувати, де і навіщо")

    sheet = Sheet(c, width, height)
    page_pipeline(sheet)
    c.showPage()
    page_table(sheet)
    c.showPage()
    c.save()

    print(f"OK: {out}  ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
