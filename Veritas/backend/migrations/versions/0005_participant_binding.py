"""accord participant secure identity binding and invitations

Revision ID: 0005_participant_binding
Revises: 0004_participant_consensus
Create Date: 2026-11-06 19:42:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from app.core.models.base import GUID

# revision identifiers, used by Alembic.
revision: str = '0005_participant_binding'
down_revision: Union[str, None] = '0004_participant_consensus'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    schema = "accord" if is_postgres else None
    core_schema = "core" if is_postgres else None

    # 1. Add bound_at and bound_method to accord.agreement_participants
    op.add_column(
        'agreement_participants',
        sa.Column('bound_at', sa.DateTime(timezone=True), nullable=True),
        schema=schema,
    )
    op.add_column(
        'agreement_participants',
        sa.Column('bound_method', sa.String(length=32), nullable=True),
        schema=schema,
    )

    # 2. Create accord.participant_invitations table
    op.create_table(
        'participant_invitations',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('agreement_participant_id', GUID(), nullable=False),
        sa.Column('agreement_id', GUID(), nullable=False),
        sa.Column('created_by_user_id', GUID(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_claimed', sa.Boolean(), server_default='false' if is_postgres else '0', nullable=False),
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('claimed_by_user_id', GUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['agreement_participant_id'],
            [f'{schema}.agreement_participants.id' if schema else 'agreement_participants.id'],
            name='fk_part_inv_agreement_participant_id',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['agreement_id'],
            [f'{schema}.agreements.id' if schema else 'agreements.id'],
            name='fk_part_inv_agreement_id',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['created_by_user_id'],
            [f'{core_schema}.users.id' if core_schema else 'users.id'],
            name='fk_part_inv_created_by_user_id',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['claimed_by_user_id'],
            [f'{core_schema}.users.id' if core_schema else 'users.id'],
            name='fk_part_inv_claimed_by_user_id',
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
        schema=schema,
    )

    op.create_index(
        'ix_accord_part_inv_token_hash',
        'participant_invitations',
        ['token_hash'],
        unique=True,
        schema=schema,
    )
    op.create_index(
        'ix_accord_part_inv_part_id',
        'participant_invitations',
        ['agreement_participant_id'],
        unique=False,
        schema=schema,
    )
    op.create_index(
        'ix_accord_part_inv_agr_id',
        'participant_invitations',
        ['agreement_id'],
        unique=False,
        schema=schema,
    )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    schema = "accord" if is_postgres else None

    op.drop_index('ix_accord_part_inv_agr_id', table_name='participant_invitations', schema=schema)
    op.drop_index('ix_accord_part_inv_part_id', table_name='participant_invitations', schema=schema)
    op.drop_index('ix_accord_part_inv_token_hash', table_name='participant_invitations', schema=schema)
    op.drop_table('participant_invitations', schema=schema)

    op.drop_column('agreement_participants', 'bound_method', schema=schema)
    op.drop_column('agreement_participants', 'bound_at', schema=schema)

