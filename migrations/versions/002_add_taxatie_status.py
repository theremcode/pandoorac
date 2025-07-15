"""add taxatie status system

Revision ID: 002
Revises: 001
Create Date: 2024-12-19 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None

def upgrade():
    # Add status column to taxatie table
    op.add_column('taxatie', sa.Column('status', sa.String(length=20), nullable=False, server_default='concept'))
    
    # Add missing columns to taxatie table (if they don't exist)
    op.add_column('taxatie', sa.Column('taxateur', sa.String(length=100), nullable=True))
    op.add_column('taxatie', sa.Column('opmerkingen', sa.Text(), nullable=True))
    
    # Create taxatie_status_history table
    op.create_table('taxatie_status_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('taxatie_id', sa.Integer(), nullable=False),
        sa.Column('old_status', sa.String(length=20), nullable=False),
        sa.Column('new_status', sa.String(length=20), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['taxatie_id'], ['taxatie.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

def downgrade():
    # Drop taxatie_status_history table
    op.drop_table('taxatie_status_history')
    
    # Remove columns from taxatie table
    op.drop_column('taxatie', 'opmerkingen')
    op.drop_column('taxatie', 'taxateur')
    op.drop_column('taxatie', 'status') 