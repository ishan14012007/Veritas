"""accord participant consensus and agreement versioning

Revision ID: 0004_accord_participant_consensus
Revises: 0003_accord_intelligence_tables
Create Date: 2026-11-06 19:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from app.core.models.base import GUID

# revision identifiers, used by Alembic.
revision: str = '0004_participant_consensus'
down_revision: Union[str, None] = '0003_accord_intelligence_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    schema = "accord" if is_postgres else None
    core_schema = "core" if is_postgres else None
    json_type = postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON()

    # 1. Add version and submitted_for_review_at to agreements
    op.add_column(
        'agreements',
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        schema=schema,
    )
    op.add_column(
        'agreements',
        sa.Column('submitted_for_review_at', sa.DateTime(timezone=True), nullable=True),
        schema=schema,
    )

    # 2. Add individual consent fields to agreement_participants
    op.add_column(
        'agreement_participants',
        sa.Column('user_id', GUID(), nullable=True),
        schema=schema,
    )
    op.add_column(
        'agreement_participants',
        sa.Column('consent_status', sa.String(length=32), server_default='PENDING', nullable=False),
        schema=schema,
    )
    op.add_column(
        'agreement_participants',
        sa.Column('responded_version', sa.Integer(), nullable=True),
        schema=schema,
    )
    op.add_column(
        'agreement_participants',
        sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
        schema=schema,
    )
    op.add_column(
        'agreement_participants',
        sa.Column('comment', sa.Text(), nullable=True),
        schema=schema,
    )

    if is_postgres:
        op.create_foreign_key(
            'fk_agr_part_user_id',
            'agreement_participants',
            'users',
            ['user_id'],
            ['id'],
            source_schema=schema,
            referent_schema=core_schema,
            ondelete='SET NULL',
        )
        op.create_index(
            'ix_agr_participants_user_id',
            'agreement_participants',
            ['user_id'],
            unique=False,
            schema=schema,
        )

    # 3. Create accord.agreement_versions
    op.create_table(
        'agreement_versions',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('agreement_id', GUID(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('terms', json_type, nullable=False),
        sa.Column('total_value', sa.Numeric(precision=14, scale=4), server_default='0.0000', nullable=False),
        sa.Column('currency', sa.String(length=3), server_default='USD', nullable=False),
        sa.Column('created_by_user_id', GUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['agreement_id'],
            [f'{schema}.agreements.id' if schema else 'agreements.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['created_by_user_id'],
            [f'{core_schema}.users.id' if core_schema else 'users.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('agreement_id', 'version', name='uq_accord_agreement_version'),
        schema=schema,
    )
    op.create_index('ix_agr_versions_agreement_id', 'agreement_versions', ['agreement_id'], unique=False, schema=schema)

    # 4. Create accord.agreement_participant_responses
    op.create_table(
        'agreement_participant_responses',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('agreement_id', GUID(), nullable=False),
        sa.Column('agreement_participant_id', GUID(), nullable=False),
        sa.Column('participant_id', GUID(), nullable=True),
        sa.Column('user_id', GUID(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('response', sa.String(length=32), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['agreement_id'],
            [f'{schema}.agreements.id' if schema else 'agreements.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['agreement_participant_id'],
            [f'{schema}.agreement_participants.id' if schema else 'agreement_participants.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['participant_id'],
            [f'{schema}.participants.id' if schema else 'participants.id'],
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'],
            [f'{core_schema}.users.id' if core_schema else 'users.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('agreement_participant_id', 'version', name='uq_participant_response_version'),
        schema=schema,
    )
    op.create_index('ix_agr_part_responses_agr_id', 'agreement_participant_responses', ['agreement_id'], unique=False, schema=schema)
    op.create_index('ix_agr_part_responses_part_id', 'agreement_participant_responses', ['agreement_participant_id'], unique=False, schema=schema)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    schema = "accord" if is_postgres else None

    op.drop_table('agreement_participant_responses', schema=schema)
    op.drop_table('agreement_versions', schema=schema)

    op.drop_column('agreement_participants', 'comment', schema=schema)
    op.drop_column('agreement_participants', 'responded_at', schema=schema)
    op.drop_column('agreement_participants', 'responded_version', schema=schema)
    op.drop_column('agreement_participants', 'consent_status', schema=schema)
    op.drop_column('agreement_participants', 'user_id', schema=schema)

    op.drop_column('agreements', 'submitted_for_review_at', schema=schema)
    op.drop_column('agreements', 'version', schema=schema)
