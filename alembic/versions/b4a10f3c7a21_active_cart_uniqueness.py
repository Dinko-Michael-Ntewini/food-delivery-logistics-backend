"""Enforce one active cart per customer.

Revision ID: b4a10f3c7a21
Revises: 57256a84ce7e
"""

from alembic import op
import sqlalchemy as sa

revision = "b4a10f3c7a21"
down_revision = "57256a84ce7e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    duplicates = connection.execute(sa.text(
        "SELECT customer_id FROM carts WHERE status = 'ACTIVE' "
        "GROUP BY customer_id HAVING COUNT(*) > 1 LIMIT 1"
    )).first()
    if duplicates:
        raise RuntimeError("Resolve duplicate active carts before applying this migration")
    op.create_index("uq_carts_one_active_per_customer", "carts", ["customer_id"],
                    unique=True, sqlite_where=sa.text("status = 'ACTIVE'"),
                    postgresql_where=sa.text("status = 'ACTIVE'"))


def downgrade() -> None:
    op.drop_index("uq_carts_one_active_per_customer", table_name="carts")
