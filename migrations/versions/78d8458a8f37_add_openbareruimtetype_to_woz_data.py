"""add openbareruimtetype to woz data

Revision ID: 78d8458a8f37
Revises: 7e4ba82a7d6a
Create Date: 2025-06-29 16:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '78d8458a8f37'
down_revision: Union[str, Sequence[str], None] = '7e4ba82a7d6a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add openbareruimtetype field to woz_data table
    op.add_column('woz_data', sa.Column('openbareruimtetype', sa.String(50), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove openbareruimtetype field from woz_data table
    op.drop_column('woz_data', 'openbareruimtetype')
