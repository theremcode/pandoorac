"""increase file_type size

Revision ID: 004
Revises: 003
Create Date: 2025-06-27 09:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    # Increase file_type field size from 50 to 100 characters in PostgreSQL
    op.alter_column('document', 'file_type',
                    existing_type=sa.String(length=50),
                    type_=sa.String(length=100),
                    existing_nullable=False)


def downgrade():
    # Revert file_type field size back to 50 characters
    op.alter_column('document', 'file_type',
                    existing_type=sa.String(length=100),
                    type_=sa.String(length=50),
                    existing_nullable=False) 