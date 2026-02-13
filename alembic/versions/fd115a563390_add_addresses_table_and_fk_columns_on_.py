"""add addresses table and FK columns on geocoder_cache and voters

Revision ID: fd115a563390
Revises: 012
Create Date: 2026-02-13 17:59:57.656574
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fd115a563390'
down_revision: Union[str, None] = '012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create addresses table
    op.create_table('addresses',
        sa.Column('normalized_address', sa.Text(), nullable=False),
        sa.Column('street_number', sa.String(length=20), nullable=True),
        sa.Column('pre_direction', sa.String(length=10), nullable=True),
        sa.Column('street_name', sa.String(length=100), nullable=True),
        sa.Column('street_type', sa.String(length=20), nullable=True),
        sa.Column('post_direction', sa.String(length=10), nullable=True),
        sa.Column('apt_unit', sa.String(length=20), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=True),
        sa.Column('state', sa.String(length=2), nullable=True),
        sa.Column('zipcode', sa.String(length=10), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('normalized_address', name='uq_address_normalized'),
    )
    op.create_index('ix_addresses_city_state', 'addresses', ['city', 'state'], unique=False)
    op.create_index('ix_addresses_normalized_prefix', 'addresses', ['normalized_address'], unique=False, postgresql_ops={'normalized_address': 'text_pattern_ops'})
    op.create_index('ix_addresses_zipcode', 'addresses', ['zipcode'], unique=False)

    # Add address_id FK to geocoder_cache
    op.add_column('geocoder_cache', sa.Column('address_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_geocoder_cache_address_id'), 'geocoder_cache', ['address_id'], unique=False)
    op.create_foreign_key('fk_geocoder_cache_address_id', 'geocoder_cache', 'addresses', ['address_id'], ['id'])

    # Add residence_address_id FK to voters
    op.add_column('voters', sa.Column('residence_address_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_voters_residence_address_id'), 'voters', ['residence_address_id'], unique=False)
    op.create_foreign_key('fk_voters_residence_address_id', 'voters', 'addresses', ['residence_address_id'], ['id'])


def downgrade() -> None:
    # Drop voters FK and column
    op.drop_constraint('fk_voters_residence_address_id', 'voters', type_='foreignkey')
    op.drop_index(op.f('ix_voters_residence_address_id'), table_name='voters')
    op.drop_column('voters', 'residence_address_id')

    # Drop geocoder_cache FK and column
    op.drop_constraint('fk_geocoder_cache_address_id', 'geocoder_cache', type_='foreignkey')
    op.drop_index(op.f('ix_geocoder_cache_address_id'), table_name='geocoder_cache')
    op.drop_column('geocoder_cache', 'address_id')

    # Drop addresses table and indexes
    op.drop_index('ix_addresses_zipcode', table_name='addresses')
    op.drop_index('ix_addresses_normalized_prefix', table_name='addresses', postgresql_ops={'normalized_address': 'text_pattern_ops'})
    op.drop_index('ix_addresses_city_state', table_name='addresses')
    op.drop_table('addresses')
