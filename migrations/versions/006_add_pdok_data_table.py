"""Add PDOK data table

Revision ID: 006
Revises: 005
Create Date: 2024-01-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade():
    # Create PDOKData table
    op.create_table('pdok_data',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bag_id', sa.String(length=50), nullable=True),
        sa.Column('search_successful', sa.Boolean(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=True),
        sa.Column('bouwjaar', sa.String(length=10), nullable=True),
        sa.Column('oppervlakte', sa.String(length=20), nullable=True),
        sa.Column('aantal_bouwlagen', sa.String(length=10), nullable=True),
        sa.Column('hoogste_bouwlaag', sa.String(length=10), nullable=True),
        sa.Column('laagste_bouwlaag', sa.String(length=10), nullable=True),
        sa.Column('gebruiksdoel', sa.String(length=200), nullable=True),
        sa.Column('aantal_kamers', sa.String(length=10), nullable=True),
        sa.Column('verdieping_toegang', sa.String(length=10), nullable=True),
        sa.Column('toegang', sa.String(length=100), nullable=True),
        sa.Column('reden_afvoer', sa.String(length=100), nullable=True),
        sa.Column('reden_opvoer', sa.String(length=100), nullable=True),
        sa.Column('bouwperiode', sa.String(length=50), nullable=True),
        sa.Column('constructie_type', sa.String(length=100), nullable=True),
        sa.Column('fundering_type', sa.String(length=100), nullable=True),
        sa.Column('dak_type', sa.String(length=100), nullable=True),
        sa.Column('externe_materialen', sa.String(length=200), nullable=True),
        sa.Column('interne_materialen', sa.String(length=200), nullable=True),
        sa.Column('energielabel', sa.String(length=10), nullable=True),
        sa.Column('energie_einddatum', sa.Date(), nullable=True),
        sa.Column('energie_registratiedatum', sa.Date(), nullable=True),
        sa.Column('energie_score', sa.Integer(), nullable=True),
        sa.Column('monument_status', sa.String(length=100), nullable=True),
        sa.Column('beschermd_stadsgezicht', sa.String(length=100), nullable=True),
        sa.Column('herstructurering', sa.String(length=100), nullable=True),
        sa.Column('planologische_status', sa.String(length=100), nullable=True),
        sa.Column('buurtnaam', sa.String(length=200), nullable=True),
        sa.Column('wijknaam', sa.String(length=200), nullable=True),
        sa.Column('gemeentenaam', sa.String(length=200), nullable=True),
        sa.Column('inwoners', sa.Integer(), nullable=True),
        sa.Column('huishoudens', sa.Integer(), nullable=True),
        sa.Column('gemiddelde_inkomen', sa.Float(), nullable=True),
        sa.Column('werkloosheid_percentage', sa.Float(), nullable=True),
        sa.Column('recente_verkopen', sa.Text(), nullable=True),
        sa.Column('gemiddelde_prijs_m2', sa.Float(), nullable=True),
        sa.Column('prijsontwikkeling', sa.Text(), nullable=True),
        sa.Column('dagen_op_markt', sa.Integer(), nullable=True),
        sa.Column('huurprijzen', sa.Text(), nullable=True),
        sa.Column('ov_afstand', sa.Float(), nullable=True),
        sa.Column('snelweg_afstand', sa.Float(), nullable=True),
        sa.Column('parkeergelegenheid', sa.String(length=100), nullable=True),
        sa.Column('fietsinfrastructuur', sa.String(length=100), nullable=True),
        sa.Column('geluidzone', sa.String(length=100), nullable=True),
        sa.Column('luchtkwaliteit', sa.String(length=100), nullable=True),
        sa.Column('overstromingsrisico', sa.String(length=100), nullable=True),
        sa.Column('zonnepotentieel', sa.String(length=100), nullable=True),
        sa.Column('groen_percentage', sa.Float(), nullable=True),
        sa.Column('has_basic_info', sa.Boolean(), nullable=True),
        sa.Column('has_building_details', sa.Boolean(), nullable=True),
        sa.Column('has_construction_info', sa.Boolean(), nullable=True),
        sa.Column('has_energy_data', sa.Boolean(), nullable=True),
        sa.Column('has_neighborhood_data', sa.Boolean(), nullable=True),
        sa.Column('has_market_data', sa.Boolean(), nullable=True),
        sa.Column('property_type_category', sa.String(length=50), nullable=True),
        sa.Column('taxatie_relevance_score', sa.Integer(), nullable=True),
        sa.Column('last_updated', sa.DateTime(), nullable=False),
        sa.Column('api_response_data', sa.Text(), nullable=True),
        sa.Column('dossier_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['dossier_id'], ['dossier.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    # Drop PDOKData table
    op.drop_table('pdok_data') 