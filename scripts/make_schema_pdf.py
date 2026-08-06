"""Генерує docs/schema.pdf — векторну схему проєкту.

Запуск (з кореня репозиторію):
    backend/.venv/Scripts/python.exe scripts/make_schema_pdf.py     # Windows
    backend/.venv/bin/python scripts/make_schema_pdf.py             # Unix

Потрібен reportlab: pip install -r scripts/requirements-docs.txt

Схема будується з коду (app/models.py, app/bot/*), тож після зміни моделі
або кроків анкети достатньо перегенерувати файл, а не перемальовувати вручну.
"""

from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas as pdfcanvas

# Палітра, шрифти й клас Sheet спільні з scripts/make_logging_pdf.py —
# інакше дві схеми з часом розійшлися б у вигляді.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _sheet import (  # noqa: E402
    AMBER,
    HexColor,
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
# Дані схеми — тримаємо поруч зі структурою файлу, щоб оновлювати в одному місці
# --------------------------------------------------------------------------
# Без емодзі: в Arial цих гліфів немає, у PDF вони виходять порожніми
# квадратами. У самому боті кнопки, звісно, з піктограмами.
MENU_BUTTONS = [
    ("«Зареєструватися»", "гості", "Анкета реєстрації: рядок у employees."),
    ("«Новий рейс»", "зареєстровані", "Рейс за ТТН, десять кроків — аркуш 4."),
    ("«Рейси»", "зареєстровані", "Обсяг — за роллю; матриця на аркуші 4."),
    ("«Нова заявка»", "зареєстровані", "Починає анкету з першого кроку."),
    ("«Мої заявки»", "зареєстровані", "Свої заявки, до 10, з кнопкою видалення."),
    ("«Усі заявки»", "адміни", "Останні 10 заявок усіх користувачів, з автором."),
    ("«Статистика»", "адміни", "Кількість заявок за статусами."),
    ("«Додати автомобіль»", "адміни", "Тягач або причіп; компанія — за роллю."),
    ("«Транспорт»", "адмін компанії", "Транспорт своєї компанії: список і картка."),
    ("«Працівники»", "адмін компанії", "Працівники своєї компанії."),
    ("«Посади»", "головний адмін", "Довідник посад і додавання нових."),
    ("«Компанії»", "головний адмін", "Компанії, а через них транспорт і працівники."),
    ("«Скасувати»", "усі", "Під кожним кроком анкети — вихід в одне натискання."),
    ("«Видалити #N»", "автор або адмін", "Видаляє заявку і перемальовує список."),
]

COMMANDS = [
    ("/start", "Меню"),
    ("/new", "Нова заявка"),
    ("/my", "Мої заявки"),
    ("/cancel", "Перервати"),
    ("/help", "Довідка"),
    ("/delete <id>", "Видалити заявку"),
]

STEPS = [
    ("full_name", "Як вас звати? (ПІБ)", "текст · 2–200 символів", None),
    ("contact", "Контакт для зв'язку", "текст · 3–200 символів",
     "бот попереджає: контакт буде публічним"),
    ("category", "Оберіть категорію", "лише кнопки · 5 значень", None),
    ("description", "Опишіть суть заявки", "текст · 10–1000 символів", None),
    ("confirm", "Перевірка + «Надіслати» / «Скасувати»", "останній момент передумати",
     "ще раз про публічність контакту"),
]

CATEGORIES = ["Технічна підтримка", "Співпраця", "Скарга", "Пропозиція", "Інше"]

PIPELINE = [
    ("1", "Зчитати анкету, очистити FSM-стан"),
    ("2", "INSERT applications, status = published"),
    ("3", "Надіслати повідомлення в групу"),
    ("4", "UPDATE: group_chat_id, group_message_id"),
    ("5", "Відповісти «Заявку #N прийнято»"),
]

# поле, тип SQLAlchemy, тип SQLite, null, індекс, публічне, призначення
FIELDS = [
    ("id", "Integer", "INTEGER", False, "PK", True,
     "Номер заявки. Його людина бачить у «#N» і передає в /delete."),
    ("telegram_user_id", "BigInteger", "BIGINT", False, "так", False,
     "Автор. Саме Big: Telegram-id не вміщується в int32."),
    ("telegram_username", "String(64)", "VARCHAR(64)", True, "—", False,
     "@username, якщо є — у Telegram він не обов'язковий."),
    ("full_name", "String(200)", "VARCHAR(200)", False, "—", True,
     "Крок 1 анкети."),
    ("contact", "String(200)", "VARCHAR(200)", False, "—", True,
     "Крок 2. Публічний за рішенням замовника."),
    ("category", "String(64)", "VARCHAR(64)", False, "так", True,
     "Крок 3. Індекс — під фільтрацію."),
    ("description", "Text", "TEXT", False, "—", True,
     "Крок 4. Довжину обмежує бот, не схема."),
    ("status", "Enum(4)", "VARCHAR(16)", False, "так", True,
     "За замовчуванням published."),
    ("group_chat_id", "BigInteger", "BIGINT", True, "—", False,
     "Куди опубліковано. Порожнє, якщо публікація не вдалась."),
    ("group_message_id", "Integer", "INTEGER", True, "—", False,
     "Без нього не прибрати повідомлення з групи."),
    ("created_at", "DateTime(tz)", "DATETIME", False, "—", True,
     "Проставляє БД. За ним сортується список."),
    ("updated_at", "DateTime(tz)", "DATETIME", False, "—", False,
     "Оновлюється автоматично при зміні рядка."),
    ("deleted_at", "DateTime(tz)", "DATETIME", True, "так", False,
     "Мітка м'якого видалення. NULL = заявка жива."),
]

STATUSES = [
    ("published", TEAL, "єдиний при створенні"),
    ("deleted", RUST, "після /delete"),
    ("pending", SLATE, "зарезервовано під модерацію"),
    ("rejected", SLATE, "зарезервовано під модерацію"),
]

# Синтетичний приклад — реальні заявки містять справжні контакти людей.
EXAMPLE_PUBLIC = [
    "GET /api/applications",
    "",
    "{",
    '  "id": 42,',
    '  "full_name": "Олена Ковальчук",',
    '  "contact": "olena@example.com",',
    '  "category": "Співпраця",',
    '  "description": "Пропонуємо...",',
    '  "status": "published",',
    '  "created_at": "2026-07-29T14:20:11"',
    "}",
]

EXAMPLE_ADMIN = [
    "GET /api/admin/applications",
    "X-Admin-Token: ...",
    "",
    "{  ...усі публічні поля, плюс:",
    '  "telegram_user_id": 1029384756,',
    '  "telegram_username": "olena",',
    '  "group_chat_id": -1001234567890,',
    '  "group_message_id": 118,',
    '  "updated_at": "2026-07-29T14:20:12",',
    '  "deleted_at": null',
    "}",
]


# --------------------------------------------------------------------------
# Сторінка 1 — маршрут заявки
# --------------------------------------------------------------------------
def page_route(s: Sheet) -> None:
    s.background()
    M = 40

    s.eyebrow(M, 46, "myapp · схема системи", color=TEAL)
    s.text(M, 76, "Маршрут заявки", font="Sans-Bold", size=25, color=INK)
    s.wrap(
        M, 96, 620,
        "Бот проводить людину через анкету з п'яти кроків, зберігає результат одним "
        "рядком у таблиці applications і розсилає його у два місця. База — єдине "
        "джерело правди: публікація в групу може не вдатись, і це не втратить заявку.",
        size=8.6, leading=11.5,
    )
    s.text(s.W - M, 76, "аркуш 1 / 5", font="Mono", size=8, color=SLATE, align="right")

    # ---- головний тракт ----
    top = 150
    s.node(M, top, 190, 92, "людина", "Користувач",
           "Приватний чат із ботом. Групу не чіпає.", accent="human")
    s.arrow(M + 190, top + 46, M + 245, top + 46)
    s.text(M + 217, top + 40, "/new", font="Mono", size=7, color=SLATE, align="center")

    s.node(285, top, 240, 92, "aiogram · FSM", "Анкета, 5 кроків",
           "Стан у пам'яті процесу. Невалідний ввід не скидає прогрес.")
    s.arrow(525, top + 46, 585, top + 46)
    s.text(555, top + 40, "надіслати", font="Mono", size=7, color=SLATE, align="center")

    s.node(590, top, 250, 92, "джерело правди", "INSERT у applications",
           "status = published, created_at = now()", accent="core")

    # ---- розгалуження ----
    s.elbow(840, top + 46, 905, top - 5)
    s.elbow(840, top + 46, 905, top + 100)

    s.node(910, top - 47, 240, 84, "вихід 1 · telegram", "Повідомлення в групу",
           "Категорія, ім'я, контакт, опис. Telegram повертає message_id.")
    s.node(910, top + 58, 240, 84, "вихід 2 · http", "REST API → сайт",
           "GET /api/applications → сторінка /applications.")

    # message_id повертається назад у БД — пунктиром, це зворотний зв'язок
    s.line(1030, top - 47, 1030, top - 60, color=SLATE, width=0.8, dash=[2, 2])
    s.line(1030, top - 60, 715, top - 60, color=SLATE, width=0.8, dash=[2, 2])
    s.arrow(715, top - 60, 715, top - 2, color=SLATE, width=0.8)
    s.text(872, top - 64, "message_id назад у рядок", font="Mono", size=7, color=SLATE,
           align="center")

    # ---- порядок операцій ----
    ty = s.section(M, 300, s.W - 2 * M, "порядок операцій після «надіслати»")
    chip_w = (s.W - 2 * M - 4 * 14) / 5
    for i, (num, label) in enumerate(PIPELINE):
        x = M + i * (chip_w + 14)
        accent = TEAL if num in ("2", "4") else LINE
        s.box(x, ty, chip_w, 46, fill=PANEL, stroke=accent,
              width=1.4 if accent is TEAL else 0.8)
        s.text(x + 10, ty + 19, num, font="Mono-Bold", size=11, color=TEAL)
        s.wrap(x + 28, ty + 17, chip_w - 38, label, size=7.6, leading=9.6, color=INK)
        if i < 4:
            s.arrow(x + chip_w, ty + 23, x + chip_w + 13, ty + 23, width=1, head=4)

    s.box(M, ty + 58, s.W - 2 * M, 30, fill=AMBER_SOFT, stroke=AMBER_SOFT)
    s.line(M, ty + 58, M, ty + 88, color=AMBER, width=2.5)
    s.wrap(M + 12, ty + 76, s.W - 2 * M - 24,
           "Порядок має значення: спершу база, потім Telegram. Якби публікація йшла "
           "першою, кожен збій мережі втрачав би заявку. Зараз збій лишає "
           "group_message_id порожнім, а заявка збережена.",
           size=8, leading=10.5, color=AMBER)

    # ---- нижні панелі ----
    # Жовтий блок вище закінчується на ~418 — панелі мають починатись під ним.
    panel_top = 420
    left_w, right_w = 520, 590

    ty2 = s.section(M, panel_top, left_w, "керування: inline-кнопки")
    s.text(M, ty2 + 8, "Кнопка", font="Mono-Bold", size=7, color=SLATE)
    s.text(M + 138, ty2 + 8, "Хто", font="Mono-Bold", size=7, color=SLATE)
    s.text(M + 242, ty2 + 8, "Дія", font="Mono-Bold", size=7, color=SLATE)
    row = ty2 + 14
    for button, who, what in MENU_BUTTONS:
        s.line(M, row, M + left_w, row, color=LINE_SOFT, width=0.6)
        s.text(M, row + 14, button, font="Sans-Bold", size=8, color=INK)
        s.text(M + 138, row + 14, who, font="Sans", size=7.6, color=SLATE)
        leading = 8.6
        end = s.wrap(M + 242, row + 12, left_w - 242, what, size=7.2, leading=leading,
                     color=INK)
        # wrap повертає ty ПІСЛЯ останнього рядка, тобто вже з одним leading.
        # Віднімаємо його, інакше однорядковий опис дає крок 22.6 замість 18,
        # і на чотирнадцяти кнопках таблиця виїжджає на футер.
        row = max(row + 18, end - leading + 6)
    s.line(M, row, M + left_w, row, color=LINE_SOFT, width=0.6)

    s.wrap(M, row + 16, left_w,
           "Склад меню визначає роль у employees. Приховування кнопки не є "
           "захистом — callback_data можна підробити, тому права перевіряються "
           "при кожному виклику. Команди теж лишаються робочими:",
           size=7.8, leading=10)
    # Лише самі команди: що вони роблять, видно з таблиці вище, а два рядки
    # чипів не вміщуються над футером.
    cx, cy = M, row + 42
    for cmd, _label in COMMANDS:
        w = pdfmetrics.stringWidth(cmd, "Mono", 7) + 14
        if cx + w > M + left_w:
            cx, cy = M, cy + 20
        s.box(cx, cy, w, 15, fill=PANEL_ALT, stroke=LINE_SOFT)
        s.text(cx + 7, cy + 11, cmd, font="Mono", size=7, color=SLATE)
        cx += w + 6

    x_right = M + left_w + 40
    ty3 = s.section(x_right, panel_top, right_w, "анкета: 5 станів fsm")
    row = ty3
    for i, (state, ask, rule, warn) in enumerate(STEPS, start=1):
        h = 56 if warn else 44
        s.box(x_right, row, right_w, h, fill=PANEL, stroke=LINE)
        s.line(x_right, row, x_right, row + h, color=TEAL, width=2.5)
        s.text(x_right + 12, row + 17, f"0{i}", font="Mono-Bold", size=10, color=TEAL)
        s.text(x_right + 36, row + 17, state, font="Mono", size=8, color=SLATE)
        s.text(x_right + 140, row + 17, ask, font="Sans-Bold", size=9, color=INK)
        s.text(x_right + 36, row + 33, rule, font="Mono", size=7.5, color=SLATE)
        if warn:
            s.box(x_right + 36, row + 38, 250, 13, fill=AMBER_SOFT, stroke=AMBER_SOFT)
            s.text(x_right + 42, row + 47, warn, font="Mono", size=7, color=AMBER)
        row += h + 7

    s.text(x_right, row + 12, "Категорії (лише з кнопок):", font="Sans-Bold", size=8,
           color=INK)
    cx = x_right + 138
    for cat in CATEGORIES:
        w = pdfmetrics.stringWidth(cat, "Mono", 7.5) + 14
        s.box(cx, row + 2, w, 15, fill=PANEL_ALT, stroke=LINE_SOFT)
        s.text(cx + 7, row + 12, cat, font="Mono", size=7.5, color=SLATE)
        cx += w + 6

    s.line(M, s.H - 34, s.W - M, s.H - 34, color=LINE, width=0.6)
    s.text(M, s.H - 22, "Схему згенеровано з коду: app/models.py, app/bot/, app/schemas.py",
           font="Mono", size=7, color=SLATE)


# --------------------------------------------------------------------------
# Сторінка 2 — заявка в базі даних
# --------------------------------------------------------------------------
def page_schema(s: Sheet) -> None:
    s.background()
    M = 40

    s.eyebrow(M, 46, "myapp · схема системи", color=TEAL)
    s.text(M, 76, "Заявка в базі даних", font="Sans-Bold", size=25, color=INK)
    s.wrap(M, 96, 620,
           "Центральна таблиця — applications, 13 колонок. Стовпець «сайт» "
           "показує, чи потрапляє поле у публічну відповідь API; решта доступна "
           "лише за адмін-токеном X-Admin-Token. Решта таблиць — на аркуші 3.",
           size=8.6, leading=11.5)
    s.text(s.W - M, 76, "аркуш 2 / 5", font="Mono", size=8, color=SLATE, align="right")

    # ---- таблиця-сутність ----
    tx, tw = M, 700
    ty = s.section(tx, 150, tw, "таблиця applications")

    header_h = 22
    s.box(tx, ty, tw, header_h, fill=TEAL, stroke=TEAL)
    cols = [(10, "поле"), (168, "sqlalchemy"), (268, "sqlite"),
            (368, "null"), (410, "індекс"), (462, "сайт"), (505, "призначення")]
    for dx, label in cols:
        s.text(tx + dx, ty + 15, label.upper(), font="Mono-Bold", size=6.8,
               color=HexColor("#FFFFFF"))

    row = ty + header_h
    row_h = 27
    for i, (name, satype, sqlite, nullable, index, public, note) in enumerate(FIELDS):
        if i % 2 == 0:
            s.box(tx, row, tw, row_h, fill=PANEL, stroke=PANEL, radius=0)
        else:
            s.box(tx, row, tw, row_h, fill=PANEL_ALT, stroke=PANEL_ALT, radius=0)

        s.text(tx + 10, row + 17, name, font="Mono-Bold", size=8, color=INK)
        s.text(tx + 168, row + 17, satype, font="Mono", size=7.5, color=TEAL)
        s.text(tx + 268, row + 17, sqlite, font="Mono", size=7.5, color=SLATE)
        # Не використовуємо "✓": цього гліфа немає в Consolas, і клітинка
        # виходила порожньою. Слова читаються однозначно й у будь-якому шрифті.
        s.text(tx + 374, row + 17, "так" if nullable else "—", font="Mono", size=7.5,
               color=SLATE if nullable else LINE)
        s.text(tx + 424, row + 17, index, font="Mono", size=7.5,
               color=RUST if index == "PK" else (TEAL if index == "так" else LINE))
        s.text(tx + 470, row + 17, "●" if public else "○", font="Mono", size=8.5,
               color=TEAL if public else SLATE)
        s.wrap(tx + 505, row + 16, tw - 515, note, size=7.4, leading=9, color=SLATE)
        row += row_h

    s.box(tx, ty, tw, row - ty, fill=None, stroke=LINE, width=1)
    s.line(tx, row, tx + tw, row, color=LINE, width=1)

    s.wrap(tx, row + 18, tw,
           "Складений індекс ix_applications_visible (deleted_at, created_at) — під "
           "основний запит сайту: живі заявки, новіші вгорі.",
           size=8, leading=10.5)

    # ---- той самий запис у двох відповідях API ----
    ey = s.section(tx, row + 46, tw, "той самий запис у двох відповідях api")
    panel_w = (tw - 20) / 2
    for i, (lines, accent, title) in enumerate([
        (EXAMPLE_PUBLIC, TEAL, "публічно — бачить сайт"),
        (EXAMPLE_ADMIN, RUST, "лише за адмін-токеном"),
    ]):
        px = tx + i * (panel_w + 20)
        ph = 20 + len(lines) * 11 + 12
        s.box(px, ey, panel_w, ph, fill=PANEL, stroke=LINE)
        s.line(px, ey, px + panel_w, ey, color=accent, width=2.5)
        s.eyebrow(px + 10, ey + 16, title, color=accent)
        for j, ln in enumerate(lines):
            s.text(px + 10, ey + 31 + j * 11, ln, font="Mono", size=7,
                   color=SLATE if ln.startswith(("GET", "X-Admin")) else INK)

    # ---- права колонка ----
    rx, rw = M + tw + 40, s.W - (M + tw + 40) - M

    ry = s.section(rx, 150, rw, "легенда")
    for dot, color, label in [("●", TEAL, "потрапляє у публічну відповідь API"),
                              ("○", SLATE, "лише за X-Admin-Token")]:
        s.text(rx + 4, ry + 10, dot, font="Mono", size=9, color=color)
        s.text(rx + 22, ry + 10, label, font="Sans", size=8, color=SLATE)
        ry += 17

    ry = s.section(rx, ry + 18, rw, "значення status")
    for name, color, note in STATUSES:
        s.box(rx, ry, rw, 26, fill=PANEL, stroke=LINE)
        s.c.setFillColor(color)
        s.c.circle(rx + 14, s.H - ry - 13, 4, stroke=0, fill=1)
        s.text(rx + 26, ry + 12, name, font="Mono-Bold", size=8.5, color=INK)
        s.text(rx + 26, ry + 21, note, font="Sans", size=7, color=SLATE)
        ry += 31

    ry = s.section(rx, ry + 18, rw, "видалення")
    for title, body in [
        ("М'яке, не фізичне",
         "Проставляються deleted_at і status = deleted. Рядок лишається: заявки — "
         "персональні дані й історія звернень, стерти їх однією командою в чаті "
         "надто легко помилково."),
        ("Прибирання з групи — по можливості",
         "Спершу deleteMessage. Telegram дозволяє боту видаляти повідомлення лише "
         "близько 48 годин, далі текст замінюється на «Заявку видалено». Збій у "
         "Telegram не скасовує видалення в базі."),
    ]:
        s.text(rx, ry + 10, title, font="Sans-Bold", size=8.5, color=INK)
        ry = s.wrap(rx, ry + 24, rw, body, size=7.6, leading=9.8) + 10

    s.box(rx, ry + 6, rw, 46, fill=AMBER_SOFT, stroke=AMBER_SOFT)
    s.line(rx, ry + 6, rx, ry + 52, color=AMBER, width=2.5)
    s.wrap(rx + 12, ry + 22, rw - 24,
           "Модерації немає — заявка публікується одразу. Але pending і rejected вже "
           "є в схемі й API, тож увімкнути її можна без міграції.",
           size=7.6, leading=9.8, color=AMBER)

    s.line(M, s.H - 34, s.W - M, s.H - 34, color=LINE, width=0.6)
    s.text(M, s.H - 22,
           "Робочий і тестовий інстанси мають цю саму схему, але різні файли БД: "
           "applications.db та applications.test.db",
           font="Mono", size=7, color=SLATE)


ORG_TABLES = {
    "company": [
        ("id", "INTEGER", "PK"),
        ("name", "TEXT NOT NULL", ""),
        ("tax_id", "TEXT NOT NULL", "UQ"),
        ("address", "TEXT NOT NULL", ""),
        ("company_chat_id", "BIGINT", ""),
    ],
    "positions": [
        ("id", "INTEGER", "PK"),
        ("position", "TEXT NOT NULL", "UQ"),
    ],
    "roles": [
        ("id", "INTEGER", "PK"),
        ("role", "TEXT NOT NULL", "UQ"),
    ],
    "role_permissions": [
        ("id", "INTEGER", "PK"),
        ("role_id", "INTEGER NOT NULL", "FK"),
        ("category", "TEXT NOT NULL", "UQ"),
        ("can_create", "BOOLEAN NOT NULL", ""),
        ("can_read", "BOOLEAN NOT NULL", ""),
        ("can_edit", "BOOLEAN NOT NULL", ""),
        ("can_delete", "BOOLEAN NOT NULL", ""),
        ("scope", "TEXT NOT NULL", ""),
        ("fields", "TEXT", ""),
    ],
    "employees": [
        ("id", "INTEGER", "PK"),
        ("tg_id", "BIGINT NOT NULL", "UQ"),
        ("company_id", "INTEGER NOT NULL", "FK"),
        ("fullname", "TEXT NOT NULL", ""),
        ("phone_number", "TEXT NOT NULL", ""),
        ("phone_number2", "TEXT", ""),
        ("position_id", "INTEGER NOT NULL", "FK"),
        ("role_id", "INTEGER NOT NULL", "FK"),
    ],
}


#: роль → (компанія, працівники, транспорт, рейси), обсяг
MATRIX_ROWS = [
    ("Головний адміністратор", ("CRED", "CRED", "CRED", "CRED"), "усі компанії"),
    ("Адміністратор компанії", ("RE", "RE", "CRED", "CRED"), "своя компанія"),
    ("Менеджер", ("R", "R", "—", "CRED"), "своя компанія"),
    ("Логіст", ("R", "R", "CRE", "CRED"), "своя компанія"),
    ("Оператор", ("R", "—", "—", "RE — лише маси"), "своя компанія"),
    ("Диспетчер", ("R", "—", "—", "RE — лише статус"), "своя компанія"),
    ("Водій", ("—", "—", "—", "R"), "лише свої рейси"),
]


VEHICLE_COLUMNS = [
    ("id", "INTEGER", "PK"),
    ("brand", "TEXT NOT NULL", ""),
    ("model", "TEXT NOT NULL", ""),
    ("license_plate", "TEXT NOT NULL", "UQ"),
    ("company_id", "INTEGER", "FK"),
]
ORG_TABLES["truck"] = VEHICLE_COLUMNS
ORG_TABLES["trailer"] = VEHICLE_COLUMNS


def page_organization(s: Sheet) -> None:
    s.background()
    M = 40

    s.eyebrow(M, 46, "myapp · схема системи", color=TEAL)
    s.text(M, 76, "Компанії та співробітники", font="Sans-Bold", size=25, color=INK)
    s.wrap(M, 96, 660,
           "Реєстрація в боті створює рядок у employees: ПІБ, номер телефону "
           "(кнопкою «Поділитися номером»), необов'язковий другий номер, "
           "і компанія зі списку. Посада й роль у всіх нових однакові — «Водій»; "
           "змінює їх головний адміністратор. Права дає не посада, а роль — через "
           "матрицю role_permissions унизу аркуша.",
           size=8.6, leading=11.5)
    s.text(s.W - M, 76, "аркуш 3 / 5", font="Mono", size=8, color=SLATE, align="right")

    left_x, left_w = M, 330
    right_x, right_w = 620, 380

    ty = s.section(left_x, 150, left_w, "довідники")
    bottoms = {}
    cursor = ty
    for name in ("company", "positions", "roles"):
        cursor, anchors = s.entity(left_x, cursor, left_w, name, ORG_TABLES[name])
        bottoms[name] = anchors
        cursor += 26

    s.section(right_x, 150, right_w, "співробітники")
    _, emp_anchors = s.entity(
        right_x, ty, right_w, "employees", ORG_TABLES["employees"], accent=RUST
    )

    # truck і trailer однакові за структурою (у коді — спільний міксин),
    # тому показуємо одним блоком, а не двома копіями тих самих рядків.
    vehicle_ty = 396
    s.entity(
        right_x, vehicle_ty, right_w, "truck   ·   trailer", VEHICLE_COLUMNS,
        accent=RUST,
    )
    s.text(right_x, vehicle_ty + 138,
           "дві окремі таблиці з ідентичною структурою; company_id → company.id",
           font="Sans", size=7.4, color=SLATE)

    # Стрілки від FK-колонок employees до відповідних таблиць.
    for column, target in (
        ("company_id", "company"),
        ("position_id", "positions"),
        ("role_id", "roles"),
    ):
        from_ty = emp_anchors[column]
        to_ty = bottoms[target]["id"]
        s.line(right_x, from_ty, right_x - 30, from_ty, color=TEAL, width=1.2)
        s.line(right_x - 30, from_ty, right_x - 30, to_ty, color=TEAL, width=1.2)
        s.arrow(right_x - 30, to_ty, left_x + left_w, to_ty, color=TEAL, width=1.2,
                head=5)

    note_ty = 556
    s.box(M, note_ty, s.W - 2 * M, 44, fill=AMBER_SOFT, stroke=AMBER_SOFT)
    s.line(M, note_ty, M, note_ty + 44, color=AMBER, width=2.5)
    s.wrap(M + 12, note_ty + 18, s.W - 2 * M - 24,
           "У SQLite перевірка зовнішніх ключів за замовчуванням ВИМКНЕНА: без "
           "PRAGMA foreign_keys=ON посилання на неіснуючий рядок пройшло б мовчки. "
           "Застосунок вмикає її на кожному підключенні (app/db.py), і тести це "
           "перевіряють — див. tests/test_organization.py.",
           size=8, leading=10.5, color=AMBER)

    ty2 = s.section(M, 624, s.W - 2 * M, "відхилення від вихідного ddl")
    s.wrap(M, ty2 + 10, s.W - 2 * M,
           "tg_id оголошено BIGINT, а не INTEGER. У SQLite різниці немає — там "
           "INTEGER і так 64-бітний. Але в PostgreSQL INTEGER 32-бітний, і "
           "Telegram-id у нього не вміщується; перехід на Postgres закладений у "
           "плани, тому тип узято з запасом. Та сама причина, що й для "
           "applications.telegram_user_id.",
           size=8, leading=10.5)

    ty3 = s.section(M, 700, s.W - 2 * M, "посада й роль розведені")
    for i, (left, right) in enumerate((
        ("новий співробітник", "посада «Водій» і роль «Водій» — анкета їх не питає"),
        ("будь-яка інша посада", "призначає головний адміністратор, з картки"),
        ("права", "дає роль, а не посада — матриця на аркуші 4"),
    )):
        row_ty = ty3 + 12 + i * 16
        s.text(M, row_ty, left, font="Sans-Bold", size=8, color=INK)
        s.text(M + 230, row_ty, "→", font="Sans", size=8, color=TEAL)
        s.text(M + 250, row_ty, right, font="Mono", size=7.5, color=SLATE)

    s.line(M, s.H - 34, s.W - M, s.H - 34, color=LINE, width=0.6)
    s.text(M, s.H - 22,
           "ADMIN_TELEGRAM_IDS лишається аварійним входом: без нього нікому "
           "завести першу компанію.",
           font="Mono", size=7, color=SLATE)


# --------------------------------------------------------------------------
# Сторінка 4 — рейс
# --------------------------------------------------------------------------
# Колонки trips згруповані не за порядком у DDL, а за тим, звідки береться
# значення: так видно, що логіст вводить руками, а що підставляється саме.
TRIP_ENTERED = [
    ("ttn_num", "TEXT NOT NULL", ""),
    ("arrival_date", "TEXT NOT NULL", ""),
    ("exporter_company_id", "INTEGER NOT NULL", "FK"),
    ("truck", "TEXT NOT NULL", ""),
    ("truck_license_plate", "TEXT NOT NULL", ""),
    ("trailer", "TEXT NOT NULL", ""),
    ("trailer_type", "TEXT NOT NULL", ""),
    ("trailer_license_plate", "TEXT NOT NULL", ""),
    ("grain_type", "TEXT NOT NULL", ""),
    ("driver_id", "INTEGER", "FK"),
    ("driver_fullname", "TEXT NOT NULL", ""),
    ("driver_phone_number", "TEXT NOT NULL", ""),
]

TRIP_DERIVED = [
    ("id", "INTEGER", "PK"),
    ("client_company_id", "INTEGER NOT NULL", "FK"),
    ("created_by", "INTEGER NOT NULL", "FK"),
    ("logist_fullname", "TEXT NOT NULL", ""),
    ("logist_phone_number", "TEXT NOT NULL", ""),
    ("logist_tg", "BIGINT NOT NULL", ""),
    ("created_at", "TEXT NOT NULL", ""),
    ("status", "TEXT NOT NULL", ""),
]

TRIP_LATER = [
    ("datetime_entry", "TEXT", ""),
    ("datetime_departure", "TEXT", ""),
    ("b_mass", "INTEGER DEFAULT 0", ""),
    ("t_mass", "INTEGER DEFAULT 0", ""),
    ("n_mass", "INTEGER DEFAULT 0", ""),
    ("edited_by", "INTEGER", "FK"),
    ("updated_at", "TEXT", ""),
    ("deleted_by", "INTEGER", "FK"),
    ("deleted_at", "TEXT", ""),
    ("chat_id", "BIGINT", ""),
    ("chat_message_id", "INTEGER", ""),
]

TRIP_STEPS = [
    ("01", "Номер ТТН", "текст"),
    ("02", "Дата прибуття", "календар, не текст"),
    ("03", "Експортер", "кнопки: назва + ІПН"),
    ("04", "Тягач", "марка й модель"),
    ("05", "Номер тягача", "верхній регістр"),
    ("06", "Причіп", "марка й модель"),
    ("07", "Тип причепа", "зерновоз, самоскид"),
    ("08", "Номер причепа", "не такий, як у тягача"),
    ("09", "Культура", "текст"),
    ("10", "Водій", "зі складу компанії"),
    ("11", "або вручну", "ПІБ і телефон"),
    ("12", "Перевірка", "«Створити рейс»"),
]

VISIBILITY = [
    ("Користувач", "власні рейси — created_by або driver_id це він"),
    ("Водій рейсу", "бачить, але не редагує: рейс йому видали"),
    ("Адміністратор компанії", "рейси своєї компанії: client_company_id = його company_id"),
    ("Головний адміністратор", "усі рейси"),
]


def page_trip(s: Sheet) -> None:
    s.background()
    M = 40

    s.eyebrow(M, 46, "myapp · схема системи", color=TEAL)
    s.text(M, 76, "Рейс", font="Sans-Bold", size=25, color=INK)
    s.wrap(M, 96, 700,
           "Рейс заводить логіст: десять кроків і підтвердження. Компанію-замовника "
           "та контакти логіста бот не питає — вони беруться з рядка employees "
           "того, хто заповнює форму, тож підставити чужу компанію нічим. Водія "
           "обирають зі складу компанії; для стороннього перевізника лишається "
           "ручний ввід, і тоді кроків одинадцять. Решта колонок заповнюється "
           "вже після створення.",
           size=8.6, leading=11.5)
    s.text(s.W - M, 76, "аркуш 5 / 5", font="Mono", size=8, color=SLATE, align="right")

    col_w, gap = 350, 30
    xs = [M + i * (col_w + gap) for i in range(3)]

    ty = s.section(xs[0], 150, col_w, "вводить логіст")
    s.section(xs[1], 150, col_w, "підставляється")
    s.section(xs[2], 150, col_w, "заповнюється пізніше")

    s.entity(xs[0], ty, col_w, "trips  ·  кроки анкети", TRIP_ENTERED)
    s.entity(xs[1], ty, col_w, "trips  ·  з employees", TRIP_DERIVED, accent=RUST)
    s.entity(xs[2], ty, col_w, "trips  ·  службові", TRIP_LATER, accent=RUST)

    ty2 = s.section(M, 466, s.W - 2 * M, "порядок кроків")
    chip_w = (s.W - 2 * M - 5 * 10) / 6
    for i, (num, title, rule) in enumerate(TRIP_STEPS):
        cx = M + (i % 6) * (chip_w + 10)
        cy = ty2 + (i // 6) * 52
        s.box(cx, cy, chip_w, 44, fill=PANEL, stroke=LINE)
        s.line(cx, cy, cx, cy + 44, color=TEAL, width=2.5)
        s.text(cx + 10, cy + 18, num, font="Mono-Bold", size=9.5, color=TEAL)
        s.text(cx + 32, cy + 18, title, font="Sans-Bold", size=8.5, color=INK)
        s.text(cx + 32, cy + 33, rule, font="Mono", size=7, color=SLATE)

    note_ty = 604
    s.box(M, note_ty, s.W - 2 * M, 48, fill=AMBER_SOFT, stroke=AMBER_SOFT)
    s.line(M, note_ty, M, note_ty + 48, color=AMBER, width=2.5)
    s.wrap(M + 12, note_ty + 18, s.W - 2 * M - 24,
           "Відхилення від вихідного опису. client_company та exporter_company "
           "оголошені INTEGER із зовнішнім ключем, а не TEXT: у полі лежить "
           "company.id, і зв'язок має бути справжнім. edited_by лишили nullable — "
           "NOT NULL суперечив би вимозі «при створенні порожнє». Додано "
           "logist_tg, щоб із рейсу можна було написати логісту, і driver_id — "
           "щоб було кого сповістити.",
           size=8, leading=10.5, color=AMBER)

    ty3 = s.section(M, 668, s.W - 2 * M, "хто які рейси бачить")
    for i, (who, what) in enumerate(VISIBILITY):
        s.text(M, ty3 + 12 + i * 16, who, font="Sans-Bold", size=8, color=INK)
        s.text(M + 170, ty3 + 12 + i * 16, what, font="Mono", size=7.5, color=SLATE)

    s.line(M, s.H - 34, s.W - M, s.H - 34, color=LINE, width=0.6)
    s.text(M, s.H - 22,
           "Створений рейс іде водієві в приват і в робочий чат компанії "
           "(company.company_chat_id). Збій розсилки рейсу не скасовує — "
           "логісту про це повідомляється.",
           font="Mono", size=7, color=SLATE)


# --------------------------------------------------------------------------
# Сторінка 4 — ролі й права
# --------------------------------------------------------------------------
PERMISSION_COLUMNS = [
    ("id", "INTEGER", "PK"),
    ("role_id", "INTEGER NOT NULL", "FK"),
    ("category", "TEXT NOT NULL", "UQ"),
    ("can_create", "BOOLEAN NOT NULL", ""),
    ("can_read", "BOOLEAN NOT NULL", ""),
    ("can_edit", "BOOLEAN NOT NULL", ""),
    ("can_delete", "BOOLEAN NOT NULL", ""),
    ("scope", "TEXT NOT NULL", ""),
    ("fields", "TEXT", ""),
]

SCOPES = [
    ("all", "усі компанії — лише головний адміністратор"),
    ("company", "у межах своєї компанії"),
    ("own", "лише свої записи: створені або де людина водій"),
]

MENU_BY_ROLE = [
    ("Головний адміністратор", "Новий рейс · Рейси · Додати автомобіль · Компанії · Посади · Ролі"),
    ("Адміністратор компанії", "Новий рейс · Рейси · Додати автомобіль · Транспорт · Працівники · Моя компанія"),
    ("Менеджер", "Новий рейс · Рейси · Працівники · Моя компанія"),
    ("Логіст", "Новий рейс · Рейси · Додати автомобіль · Транспорт · Працівники · Моя компанія"),
    ("Оператор", "Рейси · Моя компанія"),
    ("Диспетчер", "Рейси · Моя компанія"),
    ("Водій", "Рейси"),
]


def page_roles(s: Sheet) -> None:
    s.background()
    M = 40

    s.eyebrow(M, 46, "myapp · схема системи", color=TEAL)
    s.text(M, 76, "Ролі й права", font="Sans-Bold", size=25, color=INK)
    s.wrap(M, 96, 760,
           "Права — це матриця роль × розділ × CRED плюс обсяг: усі компанії, "
           "своя компанія або лише свої записи. Вона лежить у таблиці, а не "
           "розсипана перевірками по хендлерах, тож правду про доступ можна "
           "прочитати в одному місці. Змінюється міграцією, не з бота: право "
           "змінювати права — це те, з чого починаються тихі підвищення.",
           size=8.6, leading=11.5)
    s.text(s.W - M, 76, "аркуш 4 / 5", font="Mono", size=8, color=SLATE,
           align="right")

    left_w = 330
    ty = s.section(M, 170, left_w, "структура")
    bottom, _ = s.entity(M, ty, left_w, "role_permissions", PERMISSION_COLUMNS)

    ty_scope = s.section(M, bottom + 30, left_w, "обсяг")
    for i, (name, note) in enumerate(SCOPES):
        row = ty_scope + 12 + i * 26
        s.box(M, row - 11, 74, 15, fill=PANEL_ALT, stroke=LINE_SOFT)
        s.text(M + 8, row, name, font="Mono", size=7.2, color=SLATE)
        s.wrap(M + 84, row, left_w - 84, note, size=7.4, leading=9)

    right_x = M + left_w + 40
    right_w = s.W - M - right_x
    ty2 = s.section(right_x, 170,
                    right_w,
                    "c створення · r перегляд · e редагування · d видалення")

    col = [right_x, right_x + 190, right_x + 300, right_x + 410, right_x + 520]
    s.text(col[0], ty2 + 10, "Роль", font="Mono-Bold", size=7, color=SLATE)
    for i, title in enumerate(("Компанія", "Працівники", "Транспорт", "Рейси"),
                              start=1):
        s.text(col[i], ty2 + 10, title, font="Mono-Bold", size=7, color=SLATE)

    for i, (role, cells, scope) in enumerate(MATRIX_ROWS):
        row = ty2 + 32 + i * 25
        s.line(right_x, row - 16, s.W - M, row - 16, color=LINE_SOFT, width=0.5)
        s.text(col[0], row, role, font="Sans-Bold", size=8, color=INK)
        s.text(col[0], row + 10, scope, font="Mono", size=6.8, color=SLATE)
        for j, cell in enumerate(cells, start=1):
            s.text(col[j], row, cell, font="Mono", size=7.5,
                   color=INK if cell != "—" else LINE)

    note_ty = ty2 + 32 + len(MATRIX_ROWS) * 25 + 8
    s.box(right_x, note_ty, right_w, 62, fill=AMBER_SOFT, stroke=AMBER_SOFT)
    s.line(right_x, note_ty, right_x, note_ty + 62, color=AMBER, width=2.5)
    s.wrap(right_x + 12, note_ty + 18, right_w - 24,
           "Головного адміністратора в таблиці немає взагалі: його доступ — "
           "окремий об'єкт у коді, щоб зняти його не могла ні міграція, ні "
           "описка в рядку. Право E буває звужене до переліку полів: оператор "
           "має E на рейсах, але лише на масах, диспетчер — лише на статусі.",
           size=8, leading=10.5, color=AMBER)

    ty3 = s.section(M, 620, s.W - 2 * M, "меню будується з тієї самої матриці")
    for i, (role, buttons) in enumerate(MENU_BY_ROLE):
        row = ty3 + 12 + i * 15
        s.text(M, row, role, font="Sans-Bold", size=8, color=INK)
        s.text(M + 200, row, buttons, font="Mono", size=7.2, color=SLATE)

    s.line(M, s.H - 34, s.W - M, s.H - 34, color=LINE, width=0.6)
    s.text(M, s.H - 22,
           "Кнопки й перевірки в хендлерах питають той самий access.can, тож "
           "розійтись не можуть. Приховати кнопку при цьому не є захистом — "
           "callback_data можна підробити, і право перевіряється ще раз.",
           font="Mono", size=7, color=SLATE)


def main() -> None:
    register_fonts()

    out = Path(__file__).resolve().parent.parent / "docs" / "schema.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)

    width, height = landscape(A3)
    c = pdfcanvas.Canvas(str(out), pagesize=(width, height))
    c.setTitle("myapp — схема системи")
    c.setAuthor("myapp")
    c.setSubject("Бот, маршрут заявки, компанії та структура рейсу")

    sheet = Sheet(c, width, height)
    page_route(sheet)
    c.showPage()
    page_schema(sheet)
    c.showPage()
    page_organization(sheet)
    c.showPage()
    page_roles(sheet)
    c.showPage()
    page_trip(sheet)
    c.showPage()
    c.save()

    print(f"OK: {out}  ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
