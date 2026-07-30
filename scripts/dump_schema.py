"""Генерує docs/schema.json — повну структуру БД.

Запуск (з кореня репозиторію):
    backend/.venv/Scripts/python.exe scripts/dump_schema.py     # Windows
    backend/.venv/bin/python scripts/dump_schema.py             # Unix

Дані беруться з SQLAlchemy-метаданих (app/models.py), а не пишуться руками,
тож файл не може розійтися з кодом. Описи полів — із `doc=` у моделі.

Скрипт додатково звіряє результат із реальним файлом БД, якщо той існує,
і попереджає про розбіжність (наприклад, коли забули накотити міграцію).
Сам JSON при цьому лишається похідним лише від моделей — щоб не залежав
від того, на чиїй машині його згенеровано.
"""

from __future__ import annotations

import enum
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import Table  # noqa: E402
from sqlalchemy.dialects import postgresql, sqlite as sqlite_dialect  # noqa: E402
from sqlalchemy.schema import Column  # noqa: E402

import app.models  # noqa: E402,F401  — реєструє таблиці в Base.metadata
from app.db import Base  # noqa: E402
from app.models import ApplicationStatus  # noqa: E402
from app.schemas import ApplicationAdmin, ApplicationPublic  # noqa: E402

DIALECTS = {
    "sqlite": sqlite_dialect.dialect(),
    "postgresql": postgresql.dialect(),
}


def _render_types(column: Column) -> dict[str, str]:
    """Як тип виглядає в DDL різних СУБД — знадобиться при переїзді на Postgres."""
    rendered = {"generic": str(column.type)}
    for name, dialect in DIALECTS.items():
        try:
            rendered[name] = column.type.compile(dialect=dialect)
        except Exception:  # pragma: no cover - екзотичні типи
            rendered[name] = None
    return rendered


def _python_type(column: Column) -> str | None:
    try:
        return column.type.python_type.__name__
    except (NotImplementedError, AttributeError):
        return None


def _default(column: Column) -> Any:
    if column.default is None:
        return None
    arg = getattr(column.default, "arg", None)
    if isinstance(arg, enum.Enum):
        return arg.value
    if callable(arg):
        return "<callable>"
    return arg


def _server_default(column: Column) -> str | None:
    if column.server_default is None:
        return None
    return str(getattr(column.server_default, "arg", column.server_default))


def _on_update(column: Column) -> str | None:
    if column.onupdate is None:
        return None
    return str(getattr(column.onupdate, "arg", column.onupdate))


def _table_descriptions() -> dict[str, str]:
    """Опис таблиці беремо з докстрінга ORM-класу."""
    descriptions = {}
    for mapper in Base.registry.mappers:
        doc = (mapper.class_.__doc__ or "").strip()
        if doc and mapper.local_table is not None:
            descriptions[mapper.local_table.name] = doc.split("\n\n")[0].strip()
    return descriptions


def _column_dict(column: Column) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": column.name,
        "type": _render_types(column),
        "python_type": _python_type(column),
        "nullable": column.nullable,
        "primary_key": column.primary_key,
        "autoincrement": bool(column.primary_key and column.autoincrement),
        "default": _default(column),
        "server_default": _server_default(column),
        "on_update": _on_update(column),
        "description": column.doc,
    }
    enums = getattr(column.type, "enums", None)
    if enums:
        data["enum_values"] = list(enums)
    return data


def _indexes(table: Table) -> list[dict[str, Any]]:
    return sorted(
        (
            {
                "name": index.name,
                "columns": [c.name for c in index.columns],
                "unique": bool(index.unique),
            }
            for index in table.indexes
        ),
        key=lambda i: i["name"] or "",
    )


def _api_exposure() -> dict[str, list[str]]:
    """Витягуємо з самих Pydantic-схем, а не дублюємо списком —
    інакше документація розійдеться з тим, що реально віддає API."""
    public = list(ApplicationPublic.model_fields)
    admin_only = [f for f in ApplicationAdmin.model_fields if f not in set(public)]
    return {"public": public, "admin_only": admin_only}


def _alembic_head() -> str | None:
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        config = Config(str(BACKEND / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND / "migrations"))
        heads = ScriptDirectory.from_config(config).get_heads()
        return heads[0] if len(heads) == 1 else ",".join(heads)
    except Exception as exc:  # pragma: no cover
        print(f"  ! не вдалося прочитати ревізію Alembic: {exc}")
        return None


def _check_live_database(tables: dict[str, Any]) -> None:
    """Порівнюємо з реальним файлом БД, якщо він є. У JSON не потрапляє."""
    db_file = BACKEND / "applications.db"
    if not db_file.exists():
        print("  · applications.db не знайдено — звірку пропущено")
        return

    conn = sqlite3.connect(db_file)
    try:
        for name, table in tables.items():
            rows = conn.execute(f"PRAGMA table_info({name})").fetchall()
            if not rows:
                print(f"  ! у БД немає таблиці {name} — потрібна міграція")
                continue
            live = {r[1] for r in rows}
            declared = {c["name"] for c in table["columns"]}
            if live != declared:
                missing = declared - live
                extra = live - declared
                print(f"  ! {name}: розбіжність із БД. Немає: {missing}; зайві: {extra}")
            else:
                print(f"  · {name}: збігається з applications.db ({len(live)} колонок)")
    finally:
        conn.close()


def build() -> dict[str, Any]:
    descriptions = _table_descriptions()
    tables: dict[str, Any] = {}
    for table in Base.metadata.sorted_tables:
        tables[table.name] = {
            "description": descriptions.get(table.name),
            "primary_key": list(table.primary_key.columns.keys()),
            "columns": [_column_dict(c) for c in table.columns],
            "indexes": _indexes(table),
        }

    return {
        "$comment": (
            "Згенеровано scripts/dump_schema.py з app/models.py. "
            "Не редагуйте вручну — змініть модель і перегенеруйте."
        ),
        "source": "backend/app/models.py",
        "alembic_head": _alembic_head(),
        "default_database_url": "sqlite+aiosqlite:///./applications.db",
        "enums": {
            "ApplicationStatus": {
                "values": [s.value for s in ApplicationStatus],
                "default": ApplicationStatus.published.value,
                "description": (
                    "Модерації немає — при створенні завжди published. "
                    "pending і rejected закладені наперед, щоб увімкнути "
                    "модерацію без міграції."
                ),
            }
        },
        "tables": tables,
        "managed_by_alembic": {
            "$comment": (
                "Крім таблиць вище, у файлі БД є службова таблиця Alembic. "
                "Вона не описана в моделях і не належить застосунку."
            ),
            "alembic_version": {
                "columns": ["version_num VARCHAR(32) NOT NULL PRIMARY KEY"],
                "purpose": "Зберігає номер накоченої ревізії міграцій.",
            },
        },
        "api_exposure": {
            "$comment": (
                "Які колонки віддає REST API. Виведено з app/schemas.py."
            ),
            "applications": _api_exposure(),
        },
    }


def main() -> None:
    schema = build()
    rendered = json.dumps(schema, ensure_ascii=False, indent=2) + "\n"
    out = Path(__file__).resolve().parent.parent / "docs" / "schema.json"

    # --check нічого не пише: лише каже, чи файл відстав від моделі.
    # Придатне для CI та для перевірки перед комітом.
    if "--check" in sys.argv:
        if not out.exists():
            sys.exit(f"НЕМАЄ {out} — запустіть скрипт без --check")
        if out.read_text(encoding="utf-8") != rendered:
            sys.exit(
                f"{out} відстав від app/models.py.\n"
                "Перегенеруйте: python scripts/dump_schema.py"
            )
        print(f"OK: {out} відповідає моделі")
        return

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(rendered, encoding="utf-8")

    columns = sum(len(t["columns"]) for t in schema["tables"].values())
    print(f"OK: {out}")
    print(f"  таблиць: {len(schema['tables'])}, колонок: {columns}")
    _check_live_database(schema["tables"])


if __name__ == "__main__":
    main()
