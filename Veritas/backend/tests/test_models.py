import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.models.user import User
from app.core.models.organization import Organization, OrganizationMember
from app.core.models.audit import AuditLog
from app.core.security import hash_password


@pytest.mark.asyncio
async def test_models_lifecycle(test_db_session: AsyncSession):
    """Test creation, relationships, and querying of core database entities."""
    # 1. Create User
    user = User(
        email="org.owner@example.com",
        password_hash=hash_password("OwnerPassword123!"),
        full_name="Organization Owner",
        role="MERCHANT_ADMIN",
    )
    test_db_session.add(user)
    await test_db_session.commit()
    await test_db_session.refresh(user)

    assert isinstance(user.id, uuid.UUID)
    assert user.created_at is not None

    # 2. Create Organization owned by User
    org = Organization(
        name="Apex Enterprises",
        slug="apex-enterprises",
        owner_id=user.id,
    )
    test_db_session.add(org)
    await test_db_session.commit()
    await test_db_session.refresh(org)

    assert org.slug == "apex-enterprises"
    assert org.owner_id == user.id

    # 3. Create Member association
    member = OrganizationMember(
        organization_id=org.id,
        user_id=user.id,
        role="OWNER",
    )
    test_db_session.add(member)
    await test_db_session.commit()

    # Query organization with members
    query = select(OrganizationMember).where(OrganizationMember.organization_id == org.id)
    res = await test_db_session.execute(query)
    memberships = res.scalars().all()
    assert len(memberships) == 1
    assert memberships[0].role == "OWNER"

    # 4. Create Audit Log
    audit_entry = AuditLog(
        user_id=user.id,
        action="USER_LOGIN",
        resource_type="user",
        resource_id=str(user.id),
        ip_address="127.0.0.1",
        changes={"status": "success"},
    )
    test_db_session.add(audit_entry)
    await test_db_session.commit()
    await test_db_session.refresh(audit_entry)

    assert audit_entry.action == "USER_LOGIN"
    assert audit_entry.changes["status"] == "success"

