"""Спільні примітиви малювання для PDF-схем проєкту.

Тут живуть палітра, шрифти й клас Sheet — усе, що ділять між собою
scripts/make_schema_pdf.py і scripts/make_logging_pdf.py. Винесено, щоб
дві схеми не розійшлись у вигляді: одна зміна кольору або відступу має
відбиватись в обох.
"""

from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib.colors import HexColor
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
        if ty1 == ty2:  # горизонтальна, у будь-який бік
            back = head if x2 >= x1 else -head
            p.moveTo(x2, self.H - ty2)
            p.lineTo(x2 - back, self.H - ty2 + head * 0.55)
            p.lineTo(x2 - back, self.H - ty2 - head * 0.55)
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

    def entity(self, x, ty, w, title, rows, *, accent=TEAL):
        """Таблиця у вигляді ER-сутності: шапка + рядки «колонка · тип · ознака».
        Повертає ty нижнього краю та словник {колонка: ty її рядка} — за ним
        малюються стрілки зв'язків."""
        header_h, row_h = 20, 21
        height = header_h + row_h * len(rows)

        self.box(x, ty, w, height, fill=PANEL, stroke=accent, width=1.4)
        self.box(x, ty, w, header_h, fill=accent, stroke=accent)
        self.text(x + 9, ty + 14, title, font="Mono-Bold", size=8.5,
                  color=HexColor("#FFFFFF"))

        anchors = {}
        cursor = ty + header_h
        for name, coltype, flag in rows:
            anchors[name] = cursor + row_h / 2
            self.text(x + 9, cursor + 14, name, font="Mono-Bold", size=7.5, color=INK)
            self.text(x + 140, cursor + 14, coltype, font="Mono", size=7, color=SLATE)
            if flag:
                color = RUST if flag == "PK" else (TEAL if flag == "FK" else AMBER)
                self.text(x + w - 9, cursor + 14, flag, font="Mono-Bold", size=6.8,
                          color=color, align="right")
            cursor += row_h
            if cursor < ty + height:
                self.line(x, cursor, x + w, cursor, color=LINE_SOFT, width=0.5)

        return ty + height, anchors

    def section(self, x, ty, w, label):
        self.line(x, ty, x + w, ty, color=INK, width=1.4)
        self.eyebrow(x, ty + 15, label, color=INK)
        return ty + 30
