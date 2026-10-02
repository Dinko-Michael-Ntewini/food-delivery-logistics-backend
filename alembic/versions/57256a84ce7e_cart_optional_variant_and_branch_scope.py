"""cart_optional_variant_and_branch_scope

Revision ID: 57256a84ce7e
Revises: e8e1cb5f1505
Create Date: 2026-10-02 00:47:43.339180
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



revision: str = '57256a84ce7e'
down_revision: Union[str, Sequence[str], None] = 'e8e1cb5f1505'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cart_items', sa.Column('product_id', sa.Uuid(), nullable=True))
    op.execute(sa.text(
        'UPDATE cart_items SET product_id = '
        '(SELECT product_id FROM product_variants WHERE product_variants.id = cart_items.product_variant_id)'
    ))
    with op.batch_alter_table('cart_items') as batch_op:
        batch_op.alter_column('product_id', existing_type=sa.Uuid(), nullable=False)
        batch_op.alter_column('product_variant_id', existing_type=sa.Uuid(), nullable=True)
        batch_op.drop_constraint(op.f('uq_cart_items_cart_id'), type_='unique')
        batch_op.create_foreign_key(op.f('fk_cart_items_product_id_products'), 'products', ['product_id'], ['id'], ondelete='RESTRICT')
    op.create_index('uq_cart_item_plain_product', 'cart_items', ['cart_id', 'product_id'], unique=True, sqlite_where=sa.text('product_variant_id IS NULL'), postgresql_where=sa.text('product_variant_id IS NULL'))
    op.create_index('uq_cart_item_variant', 'cart_items', ['cart_id', 'product_variant_id'], unique=True, sqlite_where=sa.text('product_variant_id IS NOT NULL'), postgresql_where=sa.text('product_variant_id IS NOT NULL'))
    with op.batch_alter_table('carts') as batch_op:
        batch_op.alter_column('branch_id', existing_type=sa.Uuid(), nullable=True)


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(sa.text('SELECT 1 FROM carts WHERE branch_id IS NULL LIMIT 1')).first():
        raise RuntimeError('Cannot downgrade while unscoped carts exist')
    if connection.execute(sa.text('SELECT 1 FROM cart_items WHERE product_variant_id IS NULL LIMIT 1')).first():
        raise RuntimeError('Cannot downgrade while variant-free cart items exist')
    with op.batch_alter_table('carts') as batch_op:
        batch_op.alter_column('branch_id', existing_type=sa.Uuid(), nullable=False)
    op.drop_index('uq_cart_item_variant', table_name='cart_items', sqlite_where=sa.text('product_variant_id IS NOT NULL'), postgresql_where=sa.text('product_variant_id IS NOT NULL'))
    op.drop_index('uq_cart_item_plain_product', table_name='cart_items', sqlite_where=sa.text('product_variant_id IS NULL'), postgresql_where=sa.text('product_variant_id IS NULL'))
    with op.batch_alter_table('cart_items') as batch_op:
        batch_op.drop_constraint(op.f('fk_cart_items_product_id_products'), type_='foreignkey')
        batch_op.create_unique_constraint(op.f('uq_cart_items_cart_id'), ['cart_id', 'product_variant_id', 'notes'])
        batch_op.alter_column('product_variant_id', existing_type=sa.Uuid(), nullable=False)
        batch_op.drop_column('product_id')
