"""add search indexes

Revision ID: 7e4ba82a7d6a
Revises: a0191c4b1f5c
Create Date: 2025-06-29 16:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7e4ba82a7d6a'
down_revision = 'a0191c4b1f5c'
branch_labels = None
depends_on = None


def upgrade():
    # Add indexes for search functionality (SQLite compatible)
    op.create_index('ix_dossier_user_id', 'dossier', ['user_id'])
    op.create_index('ix_dossier_postcode', 'dossier', ['postcode'])
    op.create_index('ix_dossier_plaats', 'dossier', ['plaats'])
    op.create_index('ix_dossier_created_at', 'dossier', ['created_at'])
    
    # Add composite index for duplicate detection
    op.create_index('ix_dossier_postcode_user', 'dossier', ['postcode', 'user_id'])
    
    # Add basic search indexes for naam and adres
    op.create_index('ix_dossier_naam', 'dossier', ['naam'])
    op.create_index('ix_dossier_adres', 'dossier', ['adres'])


def downgrade():
    # Remove indexes
    op.drop_index('ix_dossier_user_id', table_name='dossier')
    op.drop_index('ix_dossier_postcode', table_name='dossier')
    op.drop_index('ix_dossier_plaats', table_name='dossier')
    op.drop_index('ix_dossier_created_at', table_name='dossier')
    op.drop_index('ix_dossier_postcode_user', table_name='dossier')
    op.drop_index('ix_dossier_naam', table_name='dossier')
    op.drop_index('ix_dossier_adres', table_name='dossier')
