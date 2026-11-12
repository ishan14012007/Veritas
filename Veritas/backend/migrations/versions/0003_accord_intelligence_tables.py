"""accord conversation intelligence tables

Revision ID: 0003_accord_intelligence_tables
Revises: 0002_accord_conversation_tables
Create Date: 2026-11-06 17:50:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from app.core.models.base import GUID

# revision identifiers, used by Alembic.
revision: str = '0003_accord_intelligence_tables'
down_revision: Union[str, None] = '0002_accord_conversation_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    schema = "accord" if is_postgres else None
    core_schema = "core" if is_postgres else None
    json_type = postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON()

    if is_postgres:
        op.execute("CREATE SCHEMA IF NOT EXISTS accord;")

    # 1. accord.conversation_analyses
    op.create_table(
        'conversation_analyses',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('conversation_id', GUID(), nullable=False),
        sa.Column('created_by_user_id', GUID(), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='QUEUED', nullable=False),
        sa.Column('ai_model', sa.String(length=64), nullable=False),
        sa.Column('overall_summary', sa.Text(), nullable=True),
        sa.Column('raw_ai_response', json_type, nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('token_count', sa.Integer(), nullable=True),
        sa.Column('execution_duration_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            [f'{schema}.conversations.id' if schema else 'conversations.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['created_by_user_id'],
            [f'{core_schema}.users.id' if core_schema else 'users.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        schema=schema,
    )
    op.create_index('ix_conv_analyses_conversation_id', 'conversation_analyses', ['conversation_id'], unique=False, schema=schema)
    op.create_index('ix_conv_analyses_created_by', 'conversation_analyses', ['created_by_user_id'], unique=False, schema=schema)

    # 2. accord.agreements
    op.create_table(
        'agreements',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('conversation_id', GUID(), nullable=False),
        sa.Column('analysis_id', GUID(), nullable=True),
        sa.Column('owner_id', GUID(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='DRAFT', nullable=False),
        sa.Column('total_value', sa.Numeric(precision=14, scale=4), server_default='0.0000', nullable=False),
        sa.Column('currency', sa.String(length=3), server_default='USD', nullable=False),
        sa.Column('terms', json_type, nullable=False),
        sa.Column('is_confirmed', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('confirmed_by_id', GUID(), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('rejection_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            [f'{schema}.conversations.id' if schema else 'conversations.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['analysis_id'],
            [f'{schema}.conversation_analyses.id' if schema else 'conversation_analyses.id'],
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['owner_id'],
            [f'{core_schema}.users.id' if core_schema else 'users.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['confirmed_by_id'],
            [f'{core_schema}.users.id' if core_schema else 'users.id'],
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
        schema=schema,
    )
    op.create_index('ix_agreements_conversation_id', 'agreements', ['conversation_id'], unique=False, schema=schema)
    op.create_index('ix_agreements_owner_id', 'agreements', ['owner_id'], unique=False, schema=schema)

    # 3. accord.agreement_participants
    op.create_table(
        'agreement_participants',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('agreement_id', GUID(), nullable=False),
        sa.Column('participant_id', GUID(), nullable=True),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('stated_role', sa.String(length=50), server_default='PARTICIPANT', nullable=False),
        sa.Column('is_confirmed', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['agreement_id'],
            [f'{schema}.agreements.id' if schema else 'agreements.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['participant_id'],
            [f'{schema}.participants.id' if schema else 'participants.id'],
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
        schema=schema,
    )
    op.create_index('ix_agr_participants_agreement_id', 'agreement_participants', ['agreement_id'], unique=False, schema=schema)

    # 4. accord.agreement_history
    op.create_table(
        'agreement_history',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('agreement_id', GUID(), nullable=False),
        sa.Column('user_id', GUID(), nullable=False),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('changes', json_type, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['agreement_id'],
            [f'{schema}.agreements.id' if schema else 'agreements.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'],
            [f'{core_schema}.users.id' if core_schema else 'users.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        schema=schema,
    )
    op.create_index('ix_agr_history_agreement_id', 'agreement_history', ['agreement_id'], unique=False, schema=schema)

    # 5. accord.financial_facts
    op.create_table(
        'financial_facts',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('analysis_id', GUID(), nullable=False),
        sa.Column('conversation_id', GUID(), nullable=False),
        sa.Column('agreement_id', GUID(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('currency', sa.String(length=3), server_default='USD', nullable=False),
        sa.Column('classification', sa.String(length=32), nullable=False),
        sa.Column('payer_name', sa.String(length=150), nullable=True),
        sa.Column('recipient_name', sa.String(length=150), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('evidence_quote', sa.Text(), nullable=False),
        sa.Column('message_indices', json_type, nullable=False),
        sa.Column('confidence', sa.Float(), server_default='1.0', nullable=False),
        sa.Column('is_explicit', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['analysis_id'],
            [f'{schema}.conversation_analyses.id' if schema else 'conversation_analyses.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            [f'{schema}.conversations.id' if schema else 'conversations.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['agreement_id'],
            [f'{schema}.agreements.id' if schema else 'agreements.id'],
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
        schema=schema,
    )
    op.create_index('ix_financial_facts_analysis_id', 'financial_facts', ['analysis_id'], unique=False, schema=schema)
    op.create_index('ix_financial_facts_conversation_id', 'financial_facts', ['conversation_id'], unique=False, schema=schema)

    # 6. accord.obligations
    op.create_table(
        'obligations',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('agreement_id', GUID(), nullable=False),
        sa.Column('analysis_id', GUID(), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('debtor_name', sa.String(length=150), nullable=True),
        sa.Column('creditor_name', sa.String(length=150), nullable=True),
        sa.Column('amount', sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column('currency', sa.String(length=3), server_default='USD', nullable=False),
        sa.Column('due_date_raw', sa.String(length=100), nullable=True),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=32), server_default='PENDING', nullable=False),
        sa.Column('is_freelance_milestone', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('deliverable', sa.Text(), nullable=True),
        sa.Column('condition', sa.Text(), nullable=True),
        sa.Column('evidence_quote', sa.Text(), nullable=False),
        sa.Column('message_indices', json_type, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['agreement_id'],
            [f'{schema}.agreements.id' if schema else 'agreements.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['analysis_id'],
            [f'{schema}.conversation_analyses.id' if schema else 'conversation_analyses.id'],
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
        schema=schema,
    )
    op.create_index('ix_obligations_agreement_id', 'obligations', ['agreement_id'], unique=False, schema=schema)

    # 7. accord.expense_splits
    op.create_table(
        'expense_splits',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('agreement_id', GUID(), nullable=False),
        sa.Column('analysis_id', GUID(), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('total_amount', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('currency', sa.String(length=3), server_default='USD', nullable=False),
        sa.Column('split_method', sa.String(length=20), server_default='EQUAL', nullable=False),
        sa.Column('proposer_name', sa.String(length=150), nullable=True),
        sa.Column('status', sa.String(length=20), server_default='PROPOSED', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['agreement_id'],
            [f'{schema}.agreements.id' if schema else 'agreements.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['analysis_id'],
            [f'{schema}.conversation_analyses.id' if schema else 'conversation_analyses.id'],
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
        schema=schema,
    )
    op.create_index('ix_expense_splits_agreement_id', 'expense_splits', ['agreement_id'], unique=False, schema=schema)

    # 8. accord.split_shares
    op.create_table(
        'split_shares',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('expense_split_id', GUID(), nullable=False),
        sa.Column('participant_name', sa.String(length=150), nullable=False),
        sa.Column('share_value', sa.Numeric(precision=10, scale=4), server_default='1.0000', nullable=False),
        sa.Column('computed_amount', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('paid_amount', sa.Numeric(precision=14, scale=4), server_default='0.0000', nullable=False),
        sa.Column('net_balance', sa.Numeric(precision=14, scale=4), server_default='0.0000', nullable=False),
        sa.Column('status', sa.String(length=20), server_default='UNPAID', nullable=False),
        sa.Column('payment_id', GUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['expense_split_id'],
            [f'{schema}.expense_splits.id' if schema else 'expense_splits.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        schema=schema,
    )
    op.create_index('ix_split_shares_expense_split_id', 'split_shares', ['expense_split_id'], unique=False, schema=schema)

    # 9. accord.ambiguities
    op.create_table(
        'ambiguities',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('analysis_id', GUID(), nullable=False),
        sa.Column('conversation_id', GUID(), nullable=False),
        sa.Column('agreement_id', GUID(), nullable=True),
        sa.Column('ambiguity_type', sa.String(length=64), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('severity', sa.String(length=20), server_default='MEDIUM', nullable=False),
        sa.Column('clarification_question', sa.Text(), nullable=False),
        sa.Column('suggested_options', json_type, nullable=False),
        sa.Column('related_participants', json_type, nullable=False),
        sa.Column('evidence_quote', sa.Text(), nullable=False),
        sa.Column('message_indices', json_type, nullable=False),
        sa.Column('status', sa.String(length=20), server_default='UNRESOLVED', nullable=False),
        sa.Column('resolution_text', sa.Text(), nullable=True),
        sa.Column('resolved_by_user_id', GUID(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['analysis_id'],
            [f'{schema}.conversation_analyses.id' if schema else 'conversation_analyses.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            [f'{schema}.conversations.id' if schema else 'conversations.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['agreement_id'],
            [f'{schema}.agreements.id' if schema else 'agreements.id'],
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['resolved_by_user_id'],
            [f'{core_schema}.users.id' if core_schema else 'users.id'],
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
        schema=schema,
    )
    op.create_index('ix_ambiguities_analysis_id', 'ambiguities', ['analysis_id'], unique=False, schema=schema)
    op.create_index('ix_ambiguities_conversation_id', 'ambiguities', ['conversation_id'], unique=False, schema=schema)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    schema = "accord" if is_postgres else None

    op.drop_table('ambiguities', schema=schema)
    op.drop_table('split_shares', schema=schema)
    op.drop_table('expense_splits', schema=schema)
    op.drop_table('obligations', schema=schema)
    op.drop_table('financial_facts', schema=schema)
    op.drop_table('agreement_history', schema=schema)
    op.drop_table('agreement_participants', schema=schema)
    op.drop_table('agreements', schema=schema)
    op.drop_table('conversation_analyses', schema=schema)
