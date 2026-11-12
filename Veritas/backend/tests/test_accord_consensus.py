import uuid
from datetime import datetime, timezone, timedelta
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.accord.models.agreement import ParticipantInvitation
from app.ai.adapter import MockAIServiceAdapter, set_ai_adapter


@pytest.fixture(autouse=True)
def setup_mock_ai():
    """Ensure predictable MockAIServiceAdapter is active."""
    adapter = MockAIServiceAdapter()
    set_ai_adapter(adapter)
    yield
    set_ai_adapter(None)


async def register_user(client: AsyncClient, email: str, full_name: str) -> str:
    """Helper to register user with full name and return access token."""
    res = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!", "full_name": full_name},
    )
    if res.status_code == 201:
        return res.json()["tokens"]["access_token"]
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    return login_res.json()["tokens"]["access_token"]


async def bind_participant(
    client: AsyncClient,
    agreement_id: str,
    participant_id: str,
    email: str,
    owner_token: str,
) -> dict:
    """Helper for agreement owner to explicitly bind a user account to a participant."""
    res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{participant_id}/bind",
        json={"email": email},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert res.status_code == 200, res.text
    return res.json()


async def setup_test_agreement(client: AsyncClient, owner_token: str):
    """Helper to ingest a 3-person conversation and generate draft agreement."""
    chat = """[12/03/24, 14:32:00] Alice Smith: Let's settle cabin expenses.
[12/03/24, 14:33:10] Bob Miller: I paid $450 directly to the host for 3 nights.
[12/03/24, 14:34:25] Alice Smith: I bought groceries totaling $180 at Safeway.
[12/03/24, 14:35:40] Charlie Davis: I will cover my fair share split 3 ways!
[12/03/24, 14:37:00] Bob Miller: Total is $630 split 3 ways, so $210 each."""

    ingest_res = await client.post(
        "/api/v1/accord/conversations/text",
        json={"title": "Cabin Trip Consensus Test", "content": chat},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert ingest_res.status_code == 201
    conv_id = ingest_res.json()["id"]

    analyze_res = await client.post(
        f"/api/v1/accord/conversations/{conv_id}/analyze?sync=true",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert analyze_res.status_code == 200
    analysis = analyze_res.json()
    agreement = analysis["agreements"][0]
    return conv_id, agreement


@pytest.mark.asyncio
async def test_participant_consensus_progression(client: AsyncClient):
    """Verify Scenarios 1, 2, 3:
    - Initial state: DRAFT, 0/3 accepted.
    - Owner binds Alice, Bob, and Charlie to their respective accounts.
    - Alice accepts: PARTIALLY_ACCEPTED (1/3).
    - Bob accepts: PARTIALLY_ACCEPTED (2/3).
    - Charlie accepts: CONFIRMED (3/3).
    """
    owner_token = await register_user(client, "owner@veritas.local", "Owner User")
    alice_token = await register_user(client, "alice@veritas.local", "Alice Smith")
    bob_token = await register_user(client, "bob@veritas.local", "Bob Miller")
    charlie_token = await register_user(client, "charlie@veritas.local", "Charlie Davis")

    conv_id, agreement = await setup_test_agreement(client, owner_token)
    agreement_id = agreement["id"]
    assert agreement["version"] == 1
    assert agreement["status"] == "DRAFT"
    assert agreement["is_confirmed"] is False

    # 1. Check initial consensus
    consensus_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/consensus",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert consensus_res.status_code == 200
    c_data = consensus_res.json()
    assert c_data["version"] == 1
    assert c_data["status"] == "DRAFT"
    assert c_data["is_confirmed"] is False
    assert c_data["total_participants"] == 3
    assert c_data["accepted_count"] == 0
    assert c_data["pending_count"] == 3
    assert c_data["consensus_achieved"] is False
    assert "awaiting" in c_data["status_message"].lower() or "0 of 3" in c_data["status_message"].lower()

    # Find participant IDs by name
    parts = {p["name"].lower(): p["id"] for p in c_data["participants"]}
    alice_part_id = next(pid for name, pid in parts.items() if "alice" in name)
    bob_part_id = next(pid for name, pid in parts.items() if "bob" in name)
    charlie_part_id = next(pid for name, pid in parts.items() if "charlie" in name)

    # Explicitly bind participants to verified user accounts
    await bind_participant(client, agreement_id, alice_part_id, "alice@veritas.local", owner_token)
    await bind_participant(client, agreement_id, bob_part_id, "bob@veritas.local", owner_token)
    await bind_participant(client, agreement_id, charlie_part_id, "charlie@veritas.local", owner_token)

    # 2. Alice accepts -> PARTIALLY_ACCEPTED (1/3)
    alice_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{alice_part_id}/respond",
        json={"response": "ACCEPTED", "comment": "Alice agrees."},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert alice_res.status_code == 200
    a_data = alice_res.json()
    assert a_data["status"] == "PARTIALLY_ACCEPTED"
    assert a_data["accepted_count"] == 1
    assert a_data["pending_count"] == 2
    assert a_data["is_confirmed"] is False
    assert "1 of 3 participants accepted" in a_data["status_message"]

    # 3. Bob accepts -> PARTIALLY_ACCEPTED (2/3)
    bob_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{bob_part_id}/respond",
        json={"response": "ACCEPTED", "comment": "Bob confirms."},
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert bob_res.status_code == 200
    b_data = bob_res.json()
    assert b_data["status"] == "PARTIALLY_ACCEPTED"
    assert b_data["accepted_count"] == 2
    assert b_data["pending_count"] == 1
    assert b_data["is_confirmed"] is False
    assert "2 of 3 participants accepted — awaiting Charlie" in b_data["status_message"]

    # 4. Charlie accepts -> CONFIRMED (3/3)
    charlie_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{charlie_part_id}/respond",
        json={"response": "ACCEPTED", "comment": "Charlie signs off."},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert charlie_res.status_code == 200
    c_final = charlie_res.json()
    assert c_final["status"] == "CONFIRMED"
    assert c_final["accepted_count"] == 3
    assert c_final["pending_count"] == 0
    assert c_final["is_confirmed"] is True
    assert c_final["consensus_achieved"] is True
    assert "All 3 required participants accepted Version 1" in c_final["status_message"]


@pytest.mark.asyncio
async def test_rejection_prevents_confirmation(client: AsyncClient):
    """Verify Scenario 4: If any participant rejects, status becomes REJECTED and confirmation is prevented."""
    owner_token = await register_user(client, "owner_rej@veritas.local", "Owner Rej")
    alice_token = await register_user(client, "alice_rej@veritas.local", "Alice Smith")
    bob_token = await register_user(client, "bob_rej@veritas.local", "Bob Miller")

    conv_id, agreement = await setup_test_agreement(client, owner_token)
    agreement_id = agreement["id"]

    consensus_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/consensus",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    parts = {p["name"].lower(): p["id"] for p in consensus_res.json()["participants"]}
    alice_part_id = next(pid for name, pid in parts.items() if "alice" in name)
    bob_part_id = next(pid for name, pid in parts.items() if "bob" in name)

    await bind_participant(client, agreement_id, alice_part_id, "alice_rej@veritas.local", owner_token)
    await bind_participant(client, agreement_id, bob_part_id, "bob_rej@veritas.local", owner_token)

    # Alice accepts
    await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{alice_part_id}/respond",
        json={"response": "ACCEPTED"},
        headers={"Authorization": f"Bearer {alice_token}"},
    )

    # Bob rejects
    bob_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{bob_part_id}/respond",
        json={"response": "REJECTED", "comment": "Math is incorrect."},
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert bob_res.status_code == 200
    data = bob_res.json()
    assert data["status"] == "REJECTED"
    assert data["is_confirmed"] is False
    assert data["rejected_count"] == 1
    assert "Agreement rejected by Bob" in data["status_message"]


@pytest.mark.asyncio
async def test_changes_requested_status(client: AsyncClient):
    """Verify Scenario 5: If a participant requests changes, agreement moves to CHANGES_REQUESTED."""
    owner_token = await register_user(client, "owner_cr@veritas.local", "Owner CR")
    alice_token = await register_user(client, "alice_cr@veritas.local", "Alice Smith")
    bob_token = await register_user(client, "bob_cr@veritas.local", "Bob Miller")

    conv_id, agreement = await setup_test_agreement(client, owner_token)
    agreement_id = agreement["id"]

    consensus_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/consensus",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    parts = {p["name"].lower(): p["id"] for p in consensus_res.json()["participants"]}
    alice_part_id = next(pid for name, pid in parts.items() if "alice" in name)
    bob_part_id = next(pid for name, pid in parts.items() if "bob" in name)

    await bind_participant(client, agreement_id, alice_part_id, "alice_cr@veritas.local", owner_token)
    await bind_participant(client, agreement_id, bob_part_id, "bob_cr@veritas.local", owner_token)

    # Alice accepts
    await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{alice_part_id}/respond",
        json={"response": "ACCEPTED"},
        headers={"Authorization": f"Bearer {alice_token}"},
    )

    # Bob requests changes
    bob_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{bob_part_id}/respond",
        json={"response": "REQUESTED_CHANGES", "comment": "Grocery share should exclude alcohol."},
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert bob_res.status_code == 200
    data = bob_res.json()
    assert data["status"] == "CHANGES_REQUESTED"
    assert data["is_confirmed"] is False
    assert data["changes_requested_count"] == 1
    assert "Changes requested by Bob" in data["status_message"]


@pytest.mark.asyncio
async def test_editing_terms_increments_version_and_invalidates_acceptances(client: AsyncClient):
    """Verify Scenario 6: Editing agreement terms increments agreement version and resets previous acceptances."""
    owner_token = await register_user(client, "owner_rev@veritas.local", "Owner Rev")
    alice_token = await register_user(client, "alice_rev@veritas.local", "Alice Smith")
    bob_token = await register_user(client, "bob_rev@veritas.local", "Bob Miller")

    conv_id, agreement = await setup_test_agreement(client, owner_token)
    agreement_id = agreement["id"]
    assert agreement["version"] == 1

    consensus_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/consensus",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    parts = {p["name"].lower(): p["id"] for p in consensus_res.json()["participants"]}
    alice_part_id = next(pid for name, pid in parts.items() if "alice" in name)
    bob_part_id = next(pid for name, pid in parts.items() if "bob" in name)

    await bind_participant(client, agreement_id, alice_part_id, "alice_rev@veritas.local", owner_token)
    await bind_participant(client, agreement_id, bob_part_id, "bob_rev@veritas.local", owner_token)

    # Alice and Bob accept Version 1
    await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{alice_part_id}/respond",
        json={"response": "ACCEPTED"},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{bob_part_id}/respond",
        json={"response": "ACCEPTED"},
        headers={"Authorization": f"Bearer {bob_token}"},
    )

    c_before = (await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/consensus",
        headers={"Authorization": f"Bearer {owner_token}"},
    )).json()
    assert c_before["accepted_count"] == 2
    assert c_before["version"] == 1

    # Edit agreement terms
    edit_res = await client.patch(
        f"/api/v1/accord/agreements/{agreement_id}",
        json={"terms": ["Revised term 1", "Revised term 2"]},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert edit_res.status_code == 200
    revised = edit_res.json()
    assert revised["version"] == 2
    assert revised["status"] == "UNDER_REVIEW"
    assert revised["is_confirmed"] is False

    # Verify that previous acceptances did NOT carry over to Version 2
    c_after = (await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/consensus",
        headers={"Authorization": f"Bearer {owner_token}"},
    )).json()
    assert c_after["version"] == 2
    assert c_after["status"] == "UNDER_REVIEW"
    assert c_after["accepted_count"] == 0
    assert c_after["pending_count"] == 3
    assert c_after["is_confirmed"] is False

    for p in c_after["participants"]:
        assert p["consent_status"] == "PENDING"
        assert p["is_confirmed"] is False


@pytest.mark.asyncio
async def test_duplicate_response_handling_is_idempotent(client: AsyncClient):
    """Verify Scenario 7: Repeated submissions for the same participant and version do not crash or duplicate."""
    owner_token = await register_user(client, "owner_dup@veritas.local", "Owner Dup")
    alice_token = await register_user(client, "alice_dup@veritas.local", "Alice Smith")

    conv_id, agreement = await setup_test_agreement(client, owner_token)
    agreement_id = agreement["id"]

    consensus_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/consensus",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    parts = {p["name"].lower(): p["id"] for p in consensus_res.json()["participants"]}
    alice_part_id = next(pid for name, pid in parts.items() if "alice" in name)

    await bind_participant(client, agreement_id, alice_part_id, "alice_dup@veritas.local", owner_token)

    # First submission
    res1 = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{alice_part_id}/respond",
        json={"response": "ACCEPTED", "comment": "Initial approval"},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert res1.status_code == 200
    assert res1.json()["accepted_count"] == 1

    # Second submission with updated comment on same version
    res2 = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{alice_part_id}/respond",
        json={"response": "ACCEPTED", "comment": "Updated approval comment"},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert res2.status_code == 200
    assert res2.json()["accepted_count"] == 1


@pytest.mark.asyncio
async def test_unauthorized_participant_response_and_impersonation_blocked(client: AsyncClient):
    """Verify Scenarios 8 & 9:
    - User cannot respond for a participant they do not represent (HTTP 403).
    - Authenticated attacker cannot impersonate Alice or Bob (HTTP 403).
    """
    owner_token = await register_user(client, "owner_sec@veritas.local", "Owner Sec")
    alice_token = await register_user(client, "alice_sec@veritas.local", "Alice Smith")
    bob_token = await register_user(client, "bob_sec@veritas.local", "Bob Miller")
    attacker_token = await register_user(client, "attacker@veritas.local", "Mallory Attacker")

    conv_id, agreement = await setup_test_agreement(client, owner_token)
    agreement_id = agreement["id"]

    consensus_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/consensus",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    parts = {p["name"].lower(): p["id"] for p in consensus_res.json()["participants"]}
    bob_part_id = next(pid for name, pid in parts.items() if "bob" in name)

    # Bob is bound to Bob's account
    await bind_participant(client, agreement_id, bob_part_id, "bob_sec@veritas.local", owner_token)

    # Attacker tries to accept on behalf of Bob -> 403 Forbidden
    bad_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{bob_part_id}/respond",
        json={"response": "ACCEPTED", "comment": "Hacked approval"},
        headers={"Authorization": f"Bearer {attacker_token}"},
    )
    assert bad_res.status_code == 403
    err_body = bad_res.json()
    err_msg = err_body.get("error", {}).get("message") or err_body.get("detail", "")
    assert "not authorized" in err_msg.lower()

    # Alice tries to respond on behalf of Bob -> 403 Forbidden
    cross_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{bob_part_id}/respond",
        json={"response": "ACCEPTED", "comment": "Alice pretending to be Bob"},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert cross_res.status_code == 403
    cross_body = cross_res.json()
    cross_msg = cross_body.get("error", {}).get("message") or cross_body.get("detail", "")
    assert "not authorized" in cross_msg.lower()


@pytest.mark.asyncio
async def test_agreement_history_preserves_audit_trail(client: AsyncClient):
    """Verify Scenario 10: Agreement history audit trail records all participant responses and revisions."""
    owner_token = await register_user(client, "owner_hist@veritas.local", "Owner Hist")
    alice_token = await register_user(client, "alice_hist@veritas.local", "Alice Smith")

    conv_id, agreement = await setup_test_agreement(client, owner_token)
    agreement_id = agreement["id"]

    # Submit for review
    await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/submit-for-review",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    consensus_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/consensus",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    alice_part_id = next(p["id"] for p in consensus_res.json()["participants"] if "alice" in p["name"].lower())

    # Bind Alice
    await bind_participant(client, agreement_id, alice_part_id, "alice_hist@veritas.local", owner_token)

    # Alice accepts
    await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{alice_part_id}/respond",
        json={"response": "ACCEPTED", "comment": "Looks good to me."},
        headers={"Authorization": f"Bearer {alice_token}"},
    )

    # Retrieve history
    hist_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/history",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert hist_res.status_code == 200
    history = hist_res.json()
    actions = [h["action"] for h in history]
    assert "CREATED" in actions
    assert "SUBMITTED_FOR_REVIEW" in actions
    assert "PARTICIPANT_BOUND" in actions
    assert "PARTICIPANT_ACCEPTED" in actions


# =========================================================================
# STAGE 3.2 SECURITY CRITERIA TESTS: SECURE PARTICIPANT IDENTITY BINDING
# =========================================================================


@pytest.mark.asyncio
async def test_insecure_name_matching_rejected(client: AsyncClient):
    """Security Criterion 1: Unbound participants reject responses even if the caller has
    identical full name or matching email prefix. A matching name is NEVER proof of identity.
    """
    owner_token = await register_user(client, "owner_insec@veritas.local", "Owner")
    # Alice user with exact name "Alice Smith" and email prefix "alice"
    alice_imposter_token = await register_user(client, "alice@unrelated-domain.com", "Alice Smith")

    conv_id, agreement = await setup_test_agreement(client, owner_token)
    agreement_id = agreement["id"]

    consensus_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/consensus",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    alice_part_id = next(p["id"] for p in consensus_res.json()["participants"] if "alice" in p["name"].lower())

    # User attempts to vote without explicit binding -> MUST be rejected with HTTP 403
    vote_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{alice_part_id}/respond",
        json={"response": "ACCEPTED", "comment": "I have the same name!"},
        headers={"Authorization": f"Bearer {alice_imposter_token}"},
    )
    assert vote_res.status_code == 403
    err_body = vote_res.json()
    err_msg = err_body.get("error", {}).get("message") or err_body.get("detail", "")
    assert "not bound to a user account" in err_msg.lower()


@pytest.mark.asyncio
async def test_invitation_creation_and_acceptance(client: AsyncClient):
    """Security Criterion 2: Cryptographic single-use invitation tokens allow secure authenticated
    binding of participants.
    """
    owner_token = await register_user(client, "owner_inv@veritas.local", "Owner Inv")
    bob_token = await register_user(client, "bob_invited@veritas.local", "Bob Miller Real")

    conv_id, agreement = await setup_test_agreement(client, owner_token)
    agreement_id = agreement["id"]

    consensus_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/consensus",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    bob_part = next(p for p in consensus_res.json()["participants"] if "bob" in p["name"].lower())
    bob_part_id = bob_part["id"]
    assert bob_part["bound_user_email"] is None
    assert bob_part["has_pending_invitation"] is False

    # 1. Owner generates an invitation
    inv_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{bob_part_id}/invite",
        json={"expires_in_hours": 24},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert inv_res.status_code == 201
    inv_data = inv_res.json()
    raw_token = inv_data["invitation_token"]
    assert len(raw_token) >= 32
    assert inv_data["is_claimed"] is False

    # 2. Check public invitation details endpoint
    details_res = await client.get(f"/api/v1/accord/invitations/{raw_token}")
    assert details_res.status_code == 200
    details = details_res.json()
    assert details["participant_name"] == "Bob Miller"
    assert details["is_expired"] is False
    assert details["is_claimed"] is False
    assert details["is_valid"] is True

    # Check participant now reflects pending invitation
    c_check = (await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/consensus",
        headers={"Authorization": f"Bearer {owner_token}"},
    )).json()
    bob_check = next(p for p in c_check["participants"] if p["id"] == bob_part_id)
    assert bob_check["has_pending_invitation"] is True

    # 3. Bob accepts the invitation while authenticated
    accept_res = await client.post(
        f"/api/v1/accord/invitations/{raw_token}/accept",
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert accept_res.status_code == 200
    consensus_after_claim = accept_res.json()
    bob_p = next(p for p in consensus_after_claim["participants"] if p["id"] == bob_part_id)
    assert bob_p["bound_method"] == "INVITATION"
    assert bob_p["bound_user_email"] == "bob_invited@veritas.local"

    # 4. Bob can now submit consent
    vote_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{bob_part_id}/respond",
        json={"response": "ACCEPTED", "comment": "Claimed and confirmed!"},
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert vote_res.status_code == 200
    assert vote_res.json()["accepted_count"] == 1


@pytest.mark.asyncio
async def test_expired_invitation_fails(client: AsyncClient, test_db_session: AsyncSession):
    """Security Criterion 3: Expired invitations cannot be claimed (HTTP 400)."""
    owner_token = await register_user(client, "owner_exp@veritas.local", "Owner Exp")
    bob_token = await register_user(client, "bob_exp@veritas.local", "Bob Exp")

    conv_id, agreement = await setup_test_agreement(client, owner_token)
    agreement_id = agreement["id"]

    consensus_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/consensus",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    bob_part_id = next(p["id"] for p in consensus_res.json()["participants"] if "bob" in p["name"].lower())

    inv_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{bob_part_id}/invite",
        json={"expires_in_hours": 24},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert inv_res.status_code == 201
    raw_token = inv_res.json()["invitation_token"]

    # Manually expire the invitation in the database
    inv_id = uuid.UUID(inv_res.json()["id"])
    stmt = select(ParticipantInvitation).where(ParticipantInvitation.id == inv_id)
    result = await test_db_session.execute(stmt)
    invitation = result.scalar_one()
    invitation.expires_at = datetime.now(timezone.utc) - timedelta(hours=2)
    await test_db_session.commit()

    # Verify details reflect expiration
    details_res = await client.get(f"/api/v1/accord/invitations/{raw_token}")
    assert details_res.status_code == 200
    assert details_res.json()["is_expired"] is True
    assert details_res.json()["is_valid"] is False

    # Attempting to claim expired token fails
    accept_res = await client.post(
        f"/api/v1/accord/invitations/{raw_token}/accept",
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert accept_res.status_code == 400
    err_msg = accept_res.json().get("error", {}).get("message") or accept_res.json().get("detail", "")
    assert "expired" in err_msg.lower()


@pytest.mark.asyncio
async def test_reused_single_use_invitation_fails(client: AsyncClient):
    """Security Criterion 4: Invitation tokens are single-use; subsequent claims fail (HTTP 400)."""
    owner_token = await register_user(client, "owner_su@veritas.local", "Owner SU")
    bob_token = await register_user(client, "bob_su@veritas.local", "Bob SU")
    charlie_token = await register_user(client, "charlie_su@veritas.local", "Charlie SU")

    conv_id, agreement = await setup_test_agreement(client, owner_token)
    agreement_id = agreement["id"]

    consensus_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/consensus",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    bob_part_id = next(p["id"] for p in consensus_res.json()["participants"] if "bob" in p["name"].lower())

    inv_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{bob_part_id}/invite",
        json={"expires_in_hours": 24},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    raw_token = inv_res.json()["invitation_token"]

    # First claim succeeds
    accept1 = await client.post(
        f"/api/v1/accord/invitations/{raw_token}/accept",
        headers={"Authorization": f"Bearer {bob_token}"},
    )
    assert accept1.status_code == 200

    # Second claim with Charlie fails
    accept2 = await client.post(
        f"/api/v1/accord/invitations/{raw_token}/accept",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert accept2.status_code == 400
    err_msg = accept2.json().get("error", {}).get("message") or accept2.json().get("detail", "")
    assert "already been used" in err_msg.lower() or "single-use" in err_msg.lower()


@pytest.mark.asyncio
async def test_unauthorized_binding_and_reassignment_fails(client: AsyncClient):
    """Security Criterion 5:
    - Non-owners cannot bind or invite participants (HTTP 403).
    - Cannot bind one user account to multiple participants in the same agreement (HTTP 400).
    - Cannot reassign a participant once consent is cast (HTTP 400).
    """
    owner_token = await register_user(client, "owner_reassign@veritas.local", "Owner Reassign")
    alice_token = await register_user(client, "alice_reassign@veritas.local", "Alice Reassign")
    bob_token = await register_user(client, "bob_reassign@veritas.local", "Bob Reassign")
    stranger_token = await register_user(client, "stranger@veritas.local", "Stranger User")

    conv_id, agreement = await setup_test_agreement(client, owner_token)
    agreement_id = agreement["id"]

    consensus_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/consensus",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    parts = {p["name"].lower(): p["id"] for p in consensus_res.json()["participants"]}
    alice_part_id = next(pid for name, pid in parts.items() if "alice" in name)
    bob_part_id = next(pid for name, pid in parts.items() if "bob" in name)

    # 1. Non-owner cannot bind
    stranger_bind = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{alice_part_id}/bind",
        json={"email": "alice_reassign@veritas.local"},
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert stranger_bind.status_code == 403

    # Non-owner cannot invite
    stranger_invite = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{alice_part_id}/invite",
        json={"expires_in_hours": 12},
        headers={"Authorization": f"Bearer {stranger_token}"},
    )
    assert stranger_invite.status_code == 403

    # 2. Owner binds Alice
    await bind_participant(client, agreement_id, alice_part_id, "alice_reassign@veritas.local", owner_token)

    # Owner tries to bind Alice's account to Bob's participant card too -> 400 Bad Request
    multi_bind = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{bob_part_id}/bind",
        json={"email": "alice_reassign@veritas.local"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert multi_bind.status_code == 400
    multi_err = multi_bind.json().get("error", {}).get("message") or multi_bind.json().get("detail", "")
    assert "already bound to" in multi_err.lower()

    # 3. Alice casts consent
    await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{alice_part_id}/respond",
        json={"response": "ACCEPTED"},
        headers={"Authorization": f"Bearer {alice_token}"},
    )

    # Owner tries to reassign Alice's participant to Bob -> 400 Bad Request
    reassign_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{alice_part_id}/bind",
        json={"email": "bob_reassign@veritas.local"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert reassign_res.status_code == 400
    reassign_err = reassign_res.json().get("error", {}).get("message") or reassign_res.json().get("detail", "")
    assert "consent has already been submitted" in reassign_err.lower()


@pytest.mark.asyncio
async def test_owner_direct_assignment_and_unbind_flow(client: AsyncClient):
    """Security Criterion 6 & 7: Owner direct assignment, unbinding when PENDING, and voting authorization."""
    owner_token = await register_user(client, "owner_direct@veritas.local", "Owner Direct")
    alice_token = await register_user(client, "alice_direct@veritas.local", "Alice Direct")

    conv_id, agreement = await setup_test_agreement(client, owner_token)
    agreement_id = agreement["id"]

    consensus_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/consensus",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    alice_part_id = next(p["id"] for p in consensus_res.json()["participants"] if "alice" in p["name"].lower())

    # 1. Owner directly binds Alice
    bound_res = await bind_participant(client, agreement_id, alice_part_id, "alice_direct@veritas.local", owner_token)
    assert bound_res["bound_method"] in ["DIRECT_ASSIGNMENT", "MANUAL_ASSIGNMENT"]
    assert bound_res["bound_user_email"] == "alice_direct@veritas.local"
    assert bound_res["bound_at"] is not None

    # 2. Owner unbinds Alice while consent is PENDING
    unbind_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{alice_part_id}/unbind",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert unbind_res.status_code == 200
    unbound_data = unbind_res.json()
    assert unbound_data["user_id"] is None
    assert unbound_data["bound_user_email"] is None
    assert unbound_data["bound_at"] is None

    # 3. Alice cannot vote now -> 403 Forbidden
    vote_fail = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{alice_part_id}/respond",
        json={"response": "ACCEPTED"},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert vote_fail.status_code == 403

    # 4. Re-bind Alice
    await bind_participant(client, agreement_id, alice_part_id, "alice_direct@veritas.local", owner_token)

    # 5. Alice votes successfully
    vote_ok = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{alice_part_id}/respond",
        json={"response": "ACCEPTED"},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert vote_ok.status_code == 200
    assert vote_ok.json()["accepted_count"] == 1

