"""Allow future plain-product order item snapshots without a variant name.

Revision ID: c5b21d4e8f32
Revises: b4a10f3c7a21
"""

from alembic import op
import sqlalchemy as sa

revision = "c5b21d4e8f32"
down_revision = "b4a10f3c7a21"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("order_items") as batch:
        batch.alter_column("variant_name_snapshot", existing_type=sa.String(120), nullable=True)


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT 1 FROM order_items WHERE variant_name_snapshot IS NULL LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade while plain-product order snapshots exist")
    with op.batch_alter_table("order_items") as batch:
        batch.alter_column("variant_name_snapshot", existing_type=sa.String(120), nullable=False)
