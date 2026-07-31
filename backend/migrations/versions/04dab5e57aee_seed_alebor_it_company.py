"""seed Alebor IT company

Revision ID: 04dab5e57aee
Revises: 7d1b946ca46b
Create Date: 2026-07-31 09:18:27.477267

Перша компанія. Без жодного рядка в company реєстрація неможлива:
employees.company_id — NOT NULL із зовнішнім ключем, а бот пропонує
обрати компанію зі списку.

Вставка умовна: tax_id унікальний, і якщо компанію вже завели через бота,
міграція має пройти без помилки, а не впертись у конфлікт.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '04dab5e57aee'
down_revision: Union[str, None] = '7d1b946ca46b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NAME = "Alebor IT"
TAX_ID = "000000"
ADDRESS = "VST"

company_table = sa.table(
    "company",
    sa.column("id", sa.Integer),
    sa.column("name", sa.Text),
    sa.column("tax_id", sa.Text),
    sa.column("address", sa.Text),
)


def upgrade() -> None:
    connection = op.get_bind()
    existing = connection.execute(
        sa.select(company_table.c.id).where(company_table.c.tax_id == TAX_ID)
    ).first()
    if existing is not None:
        return

    # id не задаємо: на нього ніщо в коді не посилається, тож нехай
    # призначить БД — інакше ризикуємо конфліктом із доданими через бота.
    op.bulk_insert(
        company_table, [{"name": NAME, "tax_id": TAX_ID, "address": ADDRESS}]
    )


def downgrade() -> None:
    # Співробітники посилаються на компанію: якщо до неї вже привʼязані
    # люди, видалення впаде на зовнішньому ключі — і це правильно,
    # мовчки втратити звʼязок гірше.
    op.execute(company_table.delete().where(company_table.c.tax_id == TAX_ID))
