"""accord conversation tables

Revision ID: 0002_accord_conversation_tables
Revises: 0001_initial_core_entities
Create Date: 2026-11-06 13:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from app.core.models.base import GUID

# revision identifiers, used by Alembic.
revision: str = '0002_accord_conversation_tables'
down_revision: Union[str, None] = '0001_initial_core_entities'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    schema = "accord" if is_postgres else None
    core_schema = "core" if is_postgres else None

    if is_postgres:
        op.execute("CREATE SCHEMA IF NOT EXISTS accord;")

    # 1. accord.conversations
    op.create_table(
        'conversations',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('owner_id', GUID(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('source_type', sa.String(length=32), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=True),
        sa.Column('raw_transcript', sa.Text(), nullable=False),
        sa.Column('processing_status', sa.String(length=20), server_default='COMPLETED', nullable=False),
        sa.Column('retention_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['owner_id'],
            [f'{core_schema}.users.id' if core_schema else 'users.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        schema=schema,
    )
    op.create_index('ix_conversations_owner_id', 'conversations', ['owner_id'], unique=False, schema=schema)

    # 2. accord.participants
    op.create_table(
        'participants',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('conversation_id', GUID(), nullable=False),
        sa.Column('display_name', sa.String(length=150), nullable=False),
        sa.Column('sender_identifier', sa.String(length=150), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            [f'{schema}.conversations.id' if schema else 'conversations.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('conversation_id', 'sender_identifier', name='uq_accord_conversation_participant'),
        schema=schema,
    )
    op.create_index('ix_participants_conversation_id', 'participants', ['conversation_id'], unique=False, schema=schema)

    # 3. accord.messages
    op.create_table(
        'messages',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('conversation_id', GUID(), nullable=False),
        sa.Column('participant_id', GUID(), nullable=True),
        sa.Column('sender_name', sa.String(length=150), nullable=True),
        sa.Column('message_body', sa.Text(), nullable=False),
        sa.Column('original_timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.Column('order_index', sa.Integer(), nullable=False),
        sa.Column('is_system_message', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            [f'{schema}.conversations.id' if schema else 'conversations.id'],
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
    op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'], unique=False, schema=schema)
    op.create_index('ix_messages_participant_id', 'messages', ['participant_id'], unique=False, schema=schema)
    op.create_index('ix_messages_order_index', 'messages', ['order_index'], unique=False, schema=schema)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    schema = "accord" if is_postgres else None

    op.drop_table('messages', schema=schema)
    op.drop_table('participants', schema=schema)
    op.drop_table('conversations', schema=schema)

