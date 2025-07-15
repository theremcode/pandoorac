"""initial schema

Revision ID: 001
Revises: None
Create Date: 2024-12-19 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create user table
    op.create_table('user',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=80), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=True),
        sa.Column('full_name', sa.String(length=120), nullable=True),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('registration_status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username')
    )
    
    # Create dossier table
    op.create_table('dossier',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('naam', sa.String(length=100), nullable=False),
        sa.Column('adres', sa.String(length=200), nullable=False),
        sa.Column('postcode', sa.String(length=10), nullable=False),
        sa.Column('plaats', sa.String(length=100), nullable=False),
        sa.Column('bouwjaar', sa.String(length=10), nullable=True),
        sa.Column('oppervlakte', sa.String(length=20), nullable=True),
        sa.Column('inhoud', sa.String(length=20), nullable=True),
        sa.Column('hoogte', sa.String(length=20), nullable=True),
        sa.Column('aantal_bouwlagen', sa.String(length=10), nullable=True),
        sa.Column('gebruiksdoel', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create taxatie table
    op.create_table('taxatie',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('datum', sa.Date(), nullable=False),
        sa.Column('taxateur', sa.String(length=100), nullable=False),
        sa.Column('waarde', sa.Float(), nullable=False),
        sa.Column('opmerkingen', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('hoogte_meters', sa.Float(), nullable=True),
        sa.Column('prijs_per_m2', sa.Float(), nullable=True),
        sa.Column('prijs_per_m3', sa.Float(), nullable=True),
        sa.Column('berekening_methode', sa.String(length=20), nullable=True),
        sa.Column('dossier_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['dossier_id'], ['dossier.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create document table
    op.create_table('document',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('file_type', sa.String(length=50), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(), nullable=False),
        sa.Column('dossier_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['dossier_id'], ['dossier.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create photo table
    op.create_table('photo',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(), nullable=False),
        sa.Column('taxatie_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['taxatie_id'], ['taxatie.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create user_log table
    op.create_table('user_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create setting table
    op.create_table('setting',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key')
    )


def downgrade():
    op.drop_table('setting')
    op.drop_table('user_log')
    op.drop_table('photo')
    op.drop_table('document')
    op.drop_table('taxatie')
    op.drop_table('dossier')
    op.drop_table('user') 