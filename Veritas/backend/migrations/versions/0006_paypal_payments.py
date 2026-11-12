"""accord paypal payment integration and settlement

Revision ID: 0006_paypal_payments
Revises: 0005_participant_binding
Create Date: 2026-11-06 20:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from app.core.models.base import GUID

# revision identifiers, used by Alembic.
revision: str = '0006_paypal_payments'
down_revision: Union[str, None] = '0005_participant_binding'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    schema = "accord" if is_postgres else None
    core_schema = "core" if is_postgres else None
    json_type = JSON().with_variant(JSONB(), "postgresql") if is_postgres else sa.JSON()

    # 1. Create accord.payment_requests table
    op.create_table(
        'payment_requests',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('agreement_id', GUID(), nullable=False),
        sa.Column('agreement_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('obligation_id', GUID(), nullable=False),
        sa.Column('debtor_participant_id', GUID(), nullable=True),
        sa.Column('creditor_participant_id', GUID(), nullable=True),
        sa.Column('debtor_name', sa.String(length=150), nullable=False),
        sa.Column('creditor_name', sa.String(length=150), nullable=False),
        sa.Column('receiver_merchant_account', sa.String(length=255), nullable=False),
        sa.Column('amount', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='DRAFT'),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('paypal_order_id', sa.String(length=128), nullable=True),
        sa.Column('created_by_user_id', GUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['agreement_id'],
            [f'{schema}.agreements.id' if schema else 'agreements.id'],
            name='fk_payment_req_agreement_id',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['obligation_id'],
            [f'{schema}.obligations.id' if schema else 'obligations.id'],
            name='fk_payment_req_obligation_id',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['debtor_participant_id'],
            [f'{schema}.agreement_participants.id' if schema else 'agreement_participants.id'],
            name='fk_payment_req_debtor_part_id',
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['creditor_participant_id'],
            [f'{schema}.agreement_participants.id' if schema else 'agreement_participants.id'],
            name='fk_payment_req_creditor_part_id',
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['created_by_user_id'],
            [f'{core_schema}.users.id' if core_schema else 'users.id'],
            name='fk_payment_req_created_by_user_id',
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
        schema=schema,
    )
    op.create_index(
        'ix_accord_pay_req_agreement_id',
        'payment_requests',
        ['agreement_id'],
        unique=False,
        schema=schema,
    )
    op.create_index(
        'ix_accord_pay_req_obligation_id',
        'payment_requests',
        ['obligation_id'],
        unique=False,
        schema=schema,
    )
    op.create_index(
        'ix_accord_pay_req_status',
        'payment_requests',
        ['status'],
        unique=False,
        schema=schema,
    )
    op.create_index(
        'ix_accord_pay_req_paypal_order_id',
        'payment_requests',
        ['paypal_order_id'],
        unique=False,
        schema=schema,
    )

    # 2. Create accord.paypal_orders table
    op.create_table(
        'paypal_orders',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('payment_request_id', GUID(), nullable=False),
        sa.Column('paypal_order_id', sa.String(length=128), nullable=False),
        sa.Column('amount', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='CREATED'),
        sa.Column('approval_url', sa.String(length=512), nullable=True),
        sa.Column('custom_id', sa.String(length=128), nullable=True),
        sa.Column('reference_id', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['payment_request_id'],
            [f'{schema}.payment_requests.id' if schema else 'payment_requests.id'],
            name='fk_paypal_orders_req_id',
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        schema=schema,
    )
    op.create_index(
        'ix_accord_paypal_orders_paypal_id',
        'paypal_orders',
        ['paypal_order_id'],
        unique=True,
        schema=schema,
    )
    op.create_index(
        'ix_accord_paypal_orders_req_id',
        'paypal_orders',
        ['payment_request_id'],
        unique=False,
        schema=schema,
    )

    # 3. Create accord.payment_captures table
    op.create_table(
        'payment_captures',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('payment_request_id', GUID(), nullable=False),
        sa.Column('paypal_order_id', sa.String(length=128), nullable=False),
        sa.Column('paypal_capture_id', sa.String(length=128), nullable=False),
        sa.Column('amount', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='COMPLETED'),
        sa.Column('paypal_fee', sa.Numeric(precision=14, scale=4), nullable=True, server_default='0.0000'),
        sa.Column('net_amount', sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['payment_request_id'],
            [f'{schema}.payment_requests.id' if schema else 'payment_requests.id'],
            name='fk_payment_captures_req_id',
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        schema=schema,
    )
    op.create_index(
        'ix_accord_pay_captures_capture_id',
        'payment_captures',
        ['paypal_capture_id'],
        unique=True,
        schema=schema,
    )
    op.create_index(
        'ix_accord_pay_captures_req_id',
        'payment_captures',
        ['payment_request_id'],
        unique=False,
        schema=schema,
    )
    op.create_index(
        'ix_accord_pay_captures_order_id',
        'payment_captures',
        ['paypal_order_id'],
        unique=False,
        schema=schema,
    )

    # 4. Create accord.payment_webhook_events table
    op.create_table(
        'payment_webhook_events',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('paypal_event_id', sa.String(length=128), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.String(length=64), nullable=True),
        sa.Column('resource_id', sa.String(length=128), nullable=True),
        sa.Column('verification_status', sa.String(length=32), nullable=False, server_default='VERIFIED'),
        sa.Column('processing_status', sa.String(length=32), nullable=False, server_default='PENDING'),
        sa.Column('payload', json_type, nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        schema=schema,
    )
    op.create_index(
        'ix_accord_pay_webhooks_event_id',
        'payment_webhook_events',
        ['paypal_event_id'],
        unique=True,
        schema=schema,
    )
    op.create_index(
        'ix_accord_pay_webhooks_event_type',
        'payment_webhook_events',
        ['event_type'],
        unique=False,
        schema=schema,
    )
    op.create_index(
        'ix_accord_pay_webhooks_proc_status',
        'payment_webhook_events',
        ['processing_status'],
        unique=False,
        schema=schema,
    )

    # 5. Create accord.payment_history table
    op.create_table(
        'payment_history',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('payment_request_id', GUID(), nullable=False),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('from_status', sa.String(length=32), nullable=True),
        sa.Column('to_status', sa.String(length=32), nullable=False),
        sa.Column('performed_by_user_id', GUID(), nullable=True),
        sa.Column('details', json_type, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['payment_request_id'],
            [f'{schema}.payment_requests.id' if schema else 'payment_requests.id'],
            name='fk_payment_hist_req_id',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['performed_by_user_id'],
            [f'{core_schema}.users.id' if core_schema else 'users.id'],
            name='fk_payment_hist_user_id',
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
        schema=schema,
    )
    op.create_index(
        'ix_accord_pay_hist_req_id',
        'payment_history',
        ['payment_request_id'],
        unique=False,
        schema=schema,
    )

    # 6. Create accord.payment_refunds table
    op.create_table(
        'payment_refunds',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('payment_capture_id', GUID(), nullable=False),
        sa.Column('payment_request_id', GUID(), nullable=False),
        sa.Column('paypal_refund_id', sa.String(length=128), nullable=False),
        sa.Column('amount', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='COMPLETED'),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('refunded_by_user_id', GUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['payment_capture_id'],
            [f'{schema}.payment_captures.id' if schema else 'payment_captures.id'],
            name='fk_payment_refunds_capture_id',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['payment_request_id'],
            [f'{schema}.payment_requests.id' if schema else 'payment_requests.id'],
            name='fk_payment_refunds_req_id',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['refunded_by_user_id'],
            [f'{core_schema}.users.id' if core_schema else 'users.id'],
            name='fk_payment_refunds_user_id',
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
        schema=schema,
    )
    op.create_index(
        'ix_accord_pay_refunds_refund_id',
        'payment_refunds',
        ['paypal_refund_id'],
        unique=True,
        schema=schema,
    )
    op.create_index(
        'ix_accord_pay_refunds_req_id',
        'payment_refunds',
        ['payment_request_id'],
        unique=False,
        schema=schema,
    )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    schema = "accord" if is_postgres else None

    # Drop in reverse order
    op.drop_index('ix_accord_pay_refunds_req_id', table_name='payment_refunds', schema=schema)
    op.drop_index('ix_accord_pay_refunds_refund_id', table_name='payment_refunds', schema=schema)
    op.drop_table('payment_refunds', schema=schema)

    op.drop_index('ix_accord_pay_hist_req_id', table_name='payment_history', schema=schema)
    op.drop_table('payment_history', schema=schema)

    op.drop_index('ix_accord_pay_webhooks_proc_status', table_name='payment_webhook_events', schema=schema)
    op.drop_index('ix_accord_pay_webhooks_event_type', table_name='payment_webhook_events', schema=schema)
    op.drop_index('ix_accord_pay_webhooks_event_id', table_name='payment_webhook_events', schema=schema)
    op.drop_table('payment_webhook_events', schema=schema)

    op.drop_index('ix_accord_pay_captures_order_id', table_name='payment_captures', schema=schema)
    op.drop_index('ix_accord_pay_captures_req_id', table_name='payment_captures', schema=schema)
    op.drop_index('ix_accord_pay_captures_capture_id', table_name='payment_captures', schema=schema)
    op.drop_table('payment_captures', schema=schema)

    op.drop_index('ix_accord_paypal_orders_req_id', table_name='paypal_orders', schema=schema)
    op.drop_index('ix_accord_paypal_orders_paypal_id', table_name='paypal_orders', schema=schema)
    op.drop_table('paypal_orders', schema=schema)

    op.drop_index('ix_accord_pay_req_paypal_order_id', table_name='payment_requests', schema=schema)
    op.drop_index('ix_accord_pay_req_status', table_name='payment_requests', schema=schema)
    op.drop_index('ix_accord_pay_req_obligation_id', table_name='payment_requests', schema=schema)
    op.drop_index('ix_accord_pay_req_agreement_id', table_name='payment_requests', schema=schema)
    op.drop_table('payment_requests', schema=schema)

