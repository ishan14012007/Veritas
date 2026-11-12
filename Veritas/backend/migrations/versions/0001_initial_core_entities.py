"""initial core entities

Revision ID: 0001_initial_core_entities
Revises: 
Create Date: 2026-11-06 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from app.core.models.base import GUID

# revision identifiers, used by Alembic.
revision: str = '0001_initial_core_entities'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    schema = "core" if is_postgres else None

    if is_postgres:
        op.execute("CREATE SCHEMA IF NOT EXISTS core;")
        op.execute("CREATE SCHEMA IF NOT EXISTS accord;")
        op.execute("CREATE SCHEMA IF NOT EXISTS argus;")

    # 1. core.users
    op.create_table(
        'users',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('phone_number', sa.String(length=32), nullable=True),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=150), nullable=False),
        sa.Column('role', sa.String(length=32), server_default='USER', nullable=False),
        sa.Column('whatsapp_opt_in', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('whatsapp_opt_in_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('is_verified', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        schema=schema,
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True, schema=schema)
    op.create_index('ix_users_phone_number', 'users', ['phone_number'], unique=True, schema=schema)

    # 2. core.organizations
    op.create_table(
        'organizations',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('owner_id', GUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['owner_id'],
            [f'{schema}.users.id' if schema else 'users.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        schema=schema,
    )
    op.create_index('ix_organizations_slug', 'organizations', ['slug'], unique=True, schema=schema)

    # 3. core.organization_members
    op.create_table(
        'organization_members',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('organization_id', GUID(), nullable=False),
        sa.Column('user_id', GUID(), nullable=False),
        sa.Column('role', sa.String(length=32), server_default='MEMBER', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['organization_id'],
            [f'{schema}.organizations.id' if schema else 'organizations.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'],
            [f'{schema}.users.id' if schema else 'users.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'user_id', name='uq_org_member'),
        schema=schema,
    )

    # 4. core.audit_logs
    op.create_table(
        'audit_logs',
        sa.Column('id', GUID(), nullable=False),
        sa.Column('user_id', GUID(), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.String(length=50), nullable=False),
        sa.Column('resource_id', sa.String(length=64), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('changes', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['user_id'],
            [f'{schema}.users.id' if schema else 'users.id'],
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
        schema=schema,
    )
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'], unique=False, schema=schema)
    op.create_index('ix_audit_logs_created_at', 'audit_logs', ['created_at'], unique=False, schema=schema)
    op.create_index('ix_audit_logs_user_id', 'audit_logs', ['user_id'], unique=False, schema=schema)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"
    schema = "core" if is_postgres else None

    op.drop_table('audit_logs', schema=schema)
    op.drop_table('organization_members', schema=schema)
    op.drop_table('organizations', schema=schema)
    op.drop_table('users', schema=schema)

