"""accord whatsapp business cloud api integration

Revision ID: 0007_whatsapp_integration
Revises: 0006_paypal_payments
Create Date: 2026-11-06 23:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from app.core.models.base import GUID

# revision identifiers, used by Alembic.
revision: str = '0007_whatsapp_integration'
down_revision: Union[str, None] = '0006_paypal_payments'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    schema = "accord" if is_postgres else None
    core_schema = "core" if is_postgres else None
    json_type = JSON().with_variant(JSONB(), "postgresql") if is_postgres else sa.JSON()

    # 1. Create accord.whatsapp_accounts table
    op.create_table(
        'whatsapp_accounts',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('user_id', GUID(), nullable=False),
        sa.Column('phone_number', sa.String(length=32), nullable=False),
        sa.Column('display_name', sa.String(length=150), nullable=True),
        sa.Column('provider', sa.String(length=32), nullable=False, server_default='mock'),
        sa.Column('phone_number_id', sa.String(length=64), nullable=True),
        sa.Column('business_account_id', sa.String(length=64), nullable=True),
        sa.Column('connection_status', sa.String(length=32), nullable=False, server_default='PENDING_VERIFICATION'),
        sa.Column('consent_status', sa.String(length=32), nullable=False, server_default='OPTED_OUT'),
        sa.Column('verification_token', sa.String(length=128), nullable=True),
        sa.Column('verification_token_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['user_id'],
            [f'{core_schema}.users.id' if core_schema else 'users.id'],
            name='fk_whatsapp_accounts_user_id',
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('phone_number', name='uq_whatsapp_accounts_phone_number'),
        schema=schema,
    )
    op.create_index(
        'ix_whatsapp_accounts_user_id',
        'whatsapp_accounts',
        ['user_id'],
        schema=schema,
    )
    op.create_index(
        'ix_whatsapp_accounts_phone_number',
        'whatsapp_accounts',
        ['phone_number'],
        schema=schema,
    )

    # 2. Create accord.whatsapp_messages table
    op.create_table(
        'whatsapp_messages',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('user_id', GUID(), nullable=True),
        sa.Column('account_id', GUID(), nullable=True),
        sa.Column('conversation_id', GUID(), nullable=True),
        sa.Column('accord_message_id', GUID(), nullable=True),
        sa.Column('provider_message_id', sa.String(length=128), nullable=False),
        sa.Column('sender_number', sa.String(length=32), nullable=False),
        sa.Column('recipient_number', sa.String(length=32), nullable=False),
        sa.Column('direction', sa.String(length=16), nullable=False),
        sa.Column('message_type', sa.String(length=32), nullable=False, server_default='TEXT'),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('raw_payload', json_type, nullable=True),
        sa.Column('provider', sa.String(length=32), nullable=False, server_default='mock'),
        sa.Column('delivery_status', sa.String(length=32), nullable=False, server_default='SENT'),
        sa.Column('error_code', sa.String(length=64), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('is_mock', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['user_id'],
            [f'{core_schema}.users.id' if core_schema else 'users.id'],
            name='fk_whatsapp_messages_user_id',
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['account_id'],
            [f'{schema}.whatsapp_accounts.id' if schema else 'whatsapp_accounts.id'],
            name='fk_whatsapp_messages_account_id',
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            [f'{schema}.conversations.id' if schema else 'conversations.id'],
            name='fk_whatsapp_messages_conversation_id',
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['accord_message_id'],
            [f'{schema}.messages.id' if schema else 'messages.id'],
            name='fk_whatsapp_messages_accord_message_id',
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider_message_id', name='uq_whatsapp_messages_provider_id'),
        schema=schema,
    )
    op.create_index('ix_whatsapp_messages_provider_id', 'whatsapp_messages', ['provider_message_id'], schema=schema)
    op.create_index('ix_whatsapp_messages_conversation_id', 'whatsapp_messages', ['conversation_id'], schema=schema)
    op.create_index('ix_whatsapp_messages_sender', 'whatsapp_messages', ['sender_number'], schema=schema)
    op.create_index('ix_whatsapp_messages_recipient', 'whatsapp_messages', ['recipient_number'], schema=schema)
    op.create_index('ix_whatsapp_messages_user_id', 'whatsapp_messages', ['user_id'], schema=schema)

    # 3. Create accord.whatsapp_webhook_events table
    op.create_table(
        'whatsapp_webhook_events',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('provider_event_id', sa.String(length=128), nullable=False),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('signature_verified', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('processing_status', sa.String(length=32), nullable=False, server_default='PENDING'),
        sa.Column('idempotency_key', sa.String(length=128), nullable=False),
        sa.Column('payload', json_type, nullable=False),
        sa.Column('error_detail', sa.Text(), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key', name='uq_whatsapp_webhook_idempotency_key'),
        schema=schema,
    )
    op.create_index('ix_whatsapp_webhook_events_idempotency_key', 'whatsapp_webhook_events', ['idempotency_key'], schema=schema)
    op.create_index('ix_whatsapp_webhook_events_provider_event_id', 'whatsapp_webhook_events', ['provider_event_id'], schema=schema)

    # 4. Create accord.whatsapp_message_templates table
    op.create_table(
        'whatsapp_message_templates',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('template_name', sa.String(length=128), nullable=False),
        sa.Column('language', sa.String(length=16), nullable=False, server_default='en_US'),
        sa.Column('category', sa.String(length=64), nullable=False, server_default='UTILITY'),
        sa.Column('approval_status', sa.String(length=32), nullable=False, server_default='APPROVED'),
        sa.Column('provider_template_id', sa.String(length=128), nullable=True),
        sa.Column('content_structure', json_type, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('template_name', name='uq_whatsapp_message_templates_name'),
        schema=schema,
    )
    op.create_index('ix_whatsapp_message_templates_name', 'whatsapp_message_templates', ['template_name'], schema=schema)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    schema = "accord" if is_postgres else None

    op.drop_table('whatsapp_message_templates', schema=schema)
    op.drop_table('whatsapp_webhook_events', schema=schema)
    op.drop_table('whatsapp_messages', schema=schema)
    op.drop_table('whatsapp_accounts', schema=schema)
