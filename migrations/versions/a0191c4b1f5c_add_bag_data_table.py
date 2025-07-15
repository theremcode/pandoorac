"""add_bag_data_table

Revision ID: a0191c4b1f5c
Revises: 005
Create Date: 2025-06-27 16:13:47.907291

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a0191c4b1f5c'
down_revision: Union[str, Sequence[str], None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('bag_data',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('adresseerbaarobjectid', sa.String(length=50), nullable=True),
        sa.Column('nummeraanduidingid', sa.String(length=50), nullable=True),
        sa.Column('pand_id', sa.String(length=50), nullable=True),
        sa.Column('straatnaam', sa.String(length=200), nullable=True),
        sa.Column('huisnummer', sa.String(length=20), nullable=True),
        sa.Column('huisletter', sa.String(length=10), nullable=True),
        sa.Column('postcode', sa.String(length=10), nullable=True),
        sa.Column('woonplaats', sa.String(length=100), nullable=True),
        sa.Column('bouwjaar', sa.String(length=10), nullable=True),
        sa.Column('oppervlakte', sa.String(length=20), nullable=True),
        sa.Column('inhoud', sa.String(length=20), nullable=True),
        sa.Column('hoogte', sa.String(length=20), nullable=True),
        sa.Column('aantal_bouwlagen', sa.String(length=10), nullable=True),
        sa.Column('gebruiksdoel', sa.String(length=200), nullable=True),
        sa.Column('last_updated', sa.DateTime(), nullable=False),
        sa.Column('api_response_data', sa.Text(), nullable=True),
        sa.Column('dossier_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['dossier_id'], ['dossier.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('bag_data')
