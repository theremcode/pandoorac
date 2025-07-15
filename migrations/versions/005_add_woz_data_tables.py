"""add woz data tables

Revision ID: 005
Revises: 004
Create Date: 2025-06-27 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    # Create woz_data table
    op.create_table('woz_data',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('wozobjectnummer', sa.String(length=50), nullable=False),
        sa.Column('woonplaatsnaam', sa.String(length=100), nullable=True),
        sa.Column('openbareruimtenaam', sa.String(length=200), nullable=True),
        sa.Column('straatnaam', sa.String(length=200), nullable=True),
        sa.Column('postcode', sa.String(length=10), nullable=True),
        sa.Column('huisnummer', sa.Integer(), nullable=True),
        sa.Column('huisletter', sa.String(length=10), nullable=True),
        sa.Column('huisnummertoevoeging', sa.String(length=10), nullable=True),
        sa.Column('gemeentecode', sa.String(length=10), nullable=True),
        sa.Column('grondoppervlakte', sa.Integer(), nullable=True),
        sa.Column('adresseerbaarobjectid', sa.String(length=50), nullable=True),
        sa.Column('nummeraanduidingid', sa.String(length=50), nullable=True),
        sa.Column('kadastrale_gemeente_code', sa.String(length=10), nullable=True),
        sa.Column('kadastrale_sectie', sa.String(length=10), nullable=True),
        sa.Column('kadastraal_perceel_nummer', sa.String(length=20), nullable=True),
        sa.Column('last_updated', sa.DateTime(), nullable=False),
        sa.Column('api_response_data', sa.Text(), nullable=True),
        sa.Column('dossier_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['dossier_id'], ['dossier.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create woz_value table
    op.create_table('woz_value',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('woz_data_id', sa.Integer(), nullable=False),
        sa.Column('peildatum', sa.Date(), nullable=False),
        sa.Column('vastgestelde_waarde', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['woz_data_id'], ['woz_data.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('woz_value')
    op.drop_table('woz_data') 