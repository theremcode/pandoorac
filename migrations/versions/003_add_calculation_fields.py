"""add calculation fields to taxatie

Revision ID: 003
Revises: 002
Create Date: 2024-12-19 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None

def upgrade():
    # Add calculation fields to taxatie table
    op.add_column('taxatie', sa.Column('hoogte_meters', sa.Float(), nullable=True))
    op.add_column('taxatie', sa.Column('prijs_per_m2', sa.Float(), nullable=True))
    op.add_column('taxatie', sa.Column('prijs_per_m3', sa.Float(), nullable=True))
    op.add_column('taxatie', sa.Column('berekening_methode', sa.String(length=20), nullable=True))

def downgrade():
    # Remove calculation fields from taxatie table
    op.drop_column('taxatie', 'berekening_methode')
    op.drop_column('taxatie', 'prijs_per_m3')
    op.drop_column('taxatie', 'prijs_per_m2')
    op.drop_column('taxatie', 'hoogte_meters') 