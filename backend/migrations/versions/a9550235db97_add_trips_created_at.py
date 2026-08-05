"""add trips created_at

Revision ID: a9550235db97
Revises: f159d6c59519
Create Date: 2026-08-05 14:41:50.029941

Коли рейс створено, з таблиці досі не читалось: updated_at і deleted_at при
створенні порожні.

Колонка додається nullable, заповнюється, і лише тоді стає NOT NULL —
NOT NULL без DEFAULT до непорожньої таблиці не додати. Для рейсів, які вже
є, точної дати не існує: беремо updated_at, якщо він є (рейс точно існував
не пізніше правки), інакше — час самої міграції як верхню межу.
"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a9550235db97'
down_revision: Union[str, None] = 'f159d6c59519'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

trips = sa.table(
    "trips",
    sa.column("created_at", sa.Text),
    sa.column("updated_at", sa.Text),
)


def upgrade() -> None:
    with op.batch_alter_table("trips", schema=None) as batch_op:
        batch_op.add_column(sa.Column("created_at", sa.Text(), nullable=True))

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    op.get_bind().execute(
        trips.update().values(created_at=sa.func.coalesce(trips.c.updated_at, now))
    )

    with op.batch_alter_table("trips", schema=None) as batch_op:
        batch_op.alter_column("created_at", existing_type=sa.Text(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("trips", schema=None) as batch_op:
        batch_op.drop_column("created_at")
