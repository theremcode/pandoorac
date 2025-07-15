"""add_geodata_fields_to_bag_data

Revision ID: e5dc4e179728
Revises: 78d8458a8f37
Create Date: 2025-06-29 19:06:23.968520

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5dc4e179728'
down_revision: Union[str, Sequence[str], None] = '78d8458a8f37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add geodata fields to bag_data table
    op.add_column('bag_data', sa.Column('centroide_ll', sa.String(length=100), nullable=True))
    op.add_column('bag_data', sa.Column('centroide_rd', sa.String(length=100), nullable=True))
    op.add_column('bag_data', sa.Column('geometrie', sa.Text(), nullable=True))
    op.add_column('bag_data', sa.Column('latitude', sa.Float(), nullable=True))
    op.add_column('bag_data', sa.Column('longitude', sa.Float(), nullable=True))
    op.add_column('bag_data', sa.Column('x_coord', sa.Float(), nullable=True))
    op.add_column('bag_data', sa.Column('y_coord', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove geodata fields from bag_data table
    op.drop_column('bag_data', 'y_coord')
    op.drop_column('bag_data', 'x_coord')
    op.drop_column('bag_data', 'longitude')
    op.drop_column('bag_data', 'latitude')
    op.drop_column('bag_data', 'geometrie')
    op.drop_column('bag_data', 'centroide_rd')
    op.drop_column('bag_data', 'centroide_ll')
