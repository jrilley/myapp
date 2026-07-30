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

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas

# --------------------------------------------------------------------------
# Палітра: прохолодний нейтральний із зеленувато-синім ухилом.
# teal = система/бекенд, rust = людина/вхідний бік, amber = застереження.
# --------------------------------------------------------------------------
PAPER = HexColor("#F5F7F7")
PANEL = HexColor("#FFFFFF")
PANEL_ALT = HexColor("#EDF1F1")
INK = HexColor("#0E171A")
SLATE = HexColor("#54646A")
LINE = HexColor("#D3DCDD")
LINE_SOFT = HexColor("#E4EAEA")
TEAL = HexColor("#0E6E6B")
TEAL_SOFT = HexColor("#E2EFEE")
RUST = HexColor("#B0512A")
RUST_SOFT = HexColor("#F7E9E1")
AMBER = HexColor("#7E5B00")
AMBER_SOFT = HexColor("#F7EFD9")

RADIUS = 3

# --------------------------------------------------------------------------
# Шрифти. Потрібна кирилиця, тому вбудовані Type1 (Helvetica) не годяться.
# --------------------------------------------------------------------------
FONT_CANDIDATES = {
    "Sans": [
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ],
    "Sans-Bold": [
        r"C:\Windows\Fonts\arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ],
    "Mono": [
        r"C:\Windows\Fonts\consola.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
    ],
    "Mono-Bold": [
        r"C:\Windows\Fonts\consolab.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/System/Library/Fonts/Menlo.ttc",
    ],
}


def register_fonts() -> None:
    for name, candidates in FONT_CANDIDATES.items():
        for path in candidates:
            if Path(path).exists():
                pdfmetrics.registerFont(TTFont(name, path))
                break
        else:
            sys.exit(
                f"Не знайдено шрифт для '{name}'. Перевірені шляхи:\n  "
                + "\n  ".join(candidates)
            )


# --------------------------------------------------------------------------
# Полотно з координатами зверху вниз — так layout рахувати простіше.
# --------------------------------------------------------------------------
class Sheet:
    def __init__(self, c: pdfcanvas.Canvas, width: float, height: float) -> None:
        self.c = c
        self.W = width
        self.H = height

    # -- примітиви ---------------------------------------------------------
    def background(self) -> None:
        self.c.setFillColor(PAPER)
        self.c.rect(0, 0, self.W, self.H, stroke=0, fill=1)

    def box(self, x, ty, w, h, *, fill=PANEL, stroke=LINE, width=0.8, radius=RADIUS):
        """fill=None — лише рамка, без заливки (щоб не затирати вміст під нею)."""
        if fill is not None:
            self.c.setFillColor(fill)
        self.c.setStrokeColor(stroke)
        self.c.setLineWidth(width)
        self.c.roundRect(
            x, self.H - ty - h, w, h, radius,
            stroke=1, fill=0 if fill is None else 1,
        )

    def line(self, x1, ty1, x2, ty2, *, color=LINE, width=0.8, dash=None):
        self.c.setStrokeColor(color)
        self.c.setLineWidth(width)
        self.c.setDash(dash or [])
        self.c.line(x1, self.H - ty1, x2, self.H - ty2)
        self.c.setDash([])

    def text(self, x, ty, s, *, font="Sans", size=9, color=INK, align="left"):
        self.c.setFillColor(color)
        self.c.setFont(font, size)
        y = self.H - ty
        if align == "center":
            self.c.drawCentredString(x, y, s)
        elif align == "right":
            self.c.drawRightString(x, y, s)
        else:
            self.c.drawString(x, y, s)

    def wrap(self, x, ty, w, s, *, font="Sans", size=8, color=SLATE, leading=10.5):
        """Проста переносна розкладка. Повертає ty після останнього рядка."""
        self.c.setFillColor(color)
        self.c.setFont(font, size)
        words = s.split()
        line, cursor = "", ty
        for word in words:
            probe = f"{line} {word}".strip()
            if pdfmetrics.stringWidth(probe, font, size) <= w:
                line = probe
                continue
            self.c.drawString(x, self.H - cursor, line)
            cursor += leading
            line = word
        if line:
            self.c.drawString(x, self.H - cursor, line)
            cursor += leading
        return cursor

    def arrow(self, x1, ty1, x2, ty2, *, color=TEAL, width=1.4, head=6):
        self.line(x1, ty1, x2, ty2, color=color, width=width)
        self.c.setFillColor(color)
        p = self.c.beginPath()
        if ty1 == ty2:  # горизонтальна
            p.moveTo(x2, self.H - ty2)
            p.lineTo(x2 - head, self.H - ty2 + head * 0.55)
            p.lineTo(x2 - head, self.H - ty2 - head * 0.55)
        else:  # вертикальна
            direction = 1 if ty2 > ty1 else -1
            p.moveTo(x2, self.H - ty2)
            p.lineTo(x2 - head * 0.55, self.H - ty2 + head * direction)
            p.lineTo(x2 + head * 0.55, self.H - ty2 + head * direction)
        p.close()
        self.c.drawPath(p, stroke=0, fill=1)

    def elbow(self, x1, ty1, x2, ty2, *, color=TEAL, width=1.4):
        """Г-подібний з'єднувач: горизонтально, потім вертикально, потім стрілка."""
        mid = x1 + (x2 - x1) * 0.45
        self.line(x1, ty1, mid, ty1, color=color, width=width)
        self.line(mid, ty1, mid, ty2, color=color, width=width)
        self.arrow(mid, ty2, x2, ty2, color=color, width=width)

    # -- складені елементи -------------------------------------------------
    def eyebrow(self, x, ty, s, *, color=TEAL):
        self.c.setFillColor(color)
        self.c.setFont("Mono-Bold", 7)
        self.c.drawString(x, self.H - ty, " ".join(s.upper()))

    def node(self, x, ty, w, h, kind, title, detail, *, accent=None):
        fill, stroke, lw = PANEL, LINE, 0.8
        kind_color = SLATE
        if accent == "human":
            fill, stroke, kind_color = RUST_SOFT, RUST, RUST
        elif accent == "core":
            fill, stroke, kind_color, lw = TEAL_SOFT, TEAL, TEAL, 1.8
        self.box(x, ty, w, h, fill=fill, stroke=stroke, width=lw)
        self.eyebrow(x + 11, ty + 16, kind, color=kind_color)
        self.text(x + 11, ty + 33, title, font="Sans-Bold", size=10.5, color=INK)
        if detail:
            self.wrap(x + 11, ty + 47, w - 22, detail, size=7.6, leading=9.8)

    def section(self, x, ty, w, label):
        self.line(x, ty, x + w, ty, color=INK, width=1.4)
        self.eyebrow(x, ty + 15, label, color=INK)
        return ty + 30


# --------------------------------------------------------------------------
# Дані схеми — тримаємо поруч зі структурою файлу, щоб оновлювати в одному місці
# --------------------------------------------------------------------------
# Без емодзі: в Arial цих гліфів немає, у PDF вони виходять порожніми
# квадратами. У самому боті кнопки, звісно, з піктограмами.
MENU_BUTTONS = [
    ("«Нова заявка»", "усі", "Починає анкету з першого кроку."),
    ("«Мої заявки»", "усі", "Свої заявки, до 10, у кожної кнопка видалення."),
    ("«Довідка»", "усі", "Довідка й повернення в меню."),
    ("«Скасувати»", "усі", "Під кожним кроком анкети — вихід в одне натискання."),
    ("«Видалити #N»", "автор або адмін", "Видаляє заявку і перемальовує список на місці."),
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
    s.text(s.W - M, 76, "аркуш 1 / 2", font="Mono", size=8, color=SLATE, align="right")

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
    panel_top = 440
    left_w, right_w = 520, 590

    ty2 = s.section(M, panel_top, left_w, "керування: inline-кнопки")
    s.text(M, ty2 + 8, "Кнопка", font="Mono-Bold", size=7, color=SLATE)
    s.text(M + 138, ty2 + 8, "Хто", font="Mono-Bold", size=7, color=SLATE)
    s.text(M + 242, ty2 + 8, "Дія", font="Mono-Bold", size=7, color=SLATE)
    row = ty2 + 14
    for button, who, what in MENU_BUTTONS:
        s.line(M, row, M + left_w, row, color=LINE_SOFT, width=0.6)
        s.text(M, row + 15, button, font="Sans-Bold", size=8.5, color=INK)
        s.text(M + 138, row + 15, who, font="Sans", size=8, color=SLATE)
        end = s.wrap(M + 242, row + 15, left_w - 242, what, size=8, leading=10, color=INK)
        row = max(row + 26, end + 5)
    s.line(M, row, M + left_w, row, color=LINE_SOFT, width=0.6)

    s.wrap(M, row + 18, left_w,
           "Команди лишаються робочими й показані в меню команд клієнта Telegram, "
           "але вводити їх не потрібно — весь шлях проходиться натисканнями:",
           size=8, leading=10.5)
    cx, cy = M, row + 46
    for cmd, label in COMMANDS:
        w = pdfmetrics.stringWidth(f"{cmd} — {label}", "Mono", 7) + 14
        if cx + w > M + left_w:
            cx, cy = M, cy + 20
        s.box(cx, cy, w, 15, fill=PANEL_ALT, stroke=LINE_SOFT)
        s.text(cx + 7, cy + 11, f"{cmd} — {label}", font="Mono", size=7, color=SLATE)
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
           "Одна таблиця applications, 13 колонок. Стовпець «сайт» показує, чи "
           "потрапляє поле у публічну відповідь API — решта доступна лише за "
           "адмін-токеном X-Admin-Token.",
           size=8.6, leading=11.5)
    s.text(s.W - M, 76, "аркуш 2 / 2", font="Mono", size=8, color=SLATE, align="right")

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


def main() -> None:
    register_fonts()

    out = Path(__file__).resolve().parent.parent / "docs" / "schema.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)

    width, height = landscape(A3)
    c = pdfcanvas.Canvas(str(out), pagesize=(width, height))
    c.setTitle("myapp — схема системи")
    c.setAuthor("myapp")
    c.setSubject("Бот, маршрут заявки та структура таблиці applications")

    sheet = Sheet(c, width, height)
    page_route(sheet)
    c.showPage()
    page_schema(sheet)
    c.showPage()
    c.save()

    print(f"OK: {out}  ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
