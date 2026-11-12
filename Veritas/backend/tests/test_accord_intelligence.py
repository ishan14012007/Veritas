import uuid
from decimal import Decimal
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.accord.services.calculator import ExpenseCalculator, ExpenseEntry
from app.ai.adapter import AIServiceAdapter, MockAIServiceAdapter, set_ai_adapter


@pytest.fixture(autouse=True)
def setup_mock_ai():
    """Ensure tests run against the predictable MockAIServiceAdapter."""
    adapter = MockAIServiceAdapter()
    set_ai_adapter(adapter)
    yield
    set_ai_adapter(None)


async def get_auth_token(client: AsyncClient, email: str = "ai.tester@example.com") -> str:
    """Helper to register and return access token."""
    reg_payload = {
        "email": email,
        "password": "Password123!",
        "full_name": "AI Tester",
    }
    reg_res = await client.post("/api/v1/auth/register", json=reg_payload)
    if reg_res.status_code == 201:
        return reg_res.json()["tokens"]["access_token"]

    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    return login_res.json()["tokens"]["access_token"]


# ==============================================================================
# 1. Deterministic Expense Calculator Tests
# ==============================================================================


def test_expense_calculator_reference_test_case():
    """Verify Section 8 reference test case:
    Bob paid $450, Alice paid $180, total $630.
    3 participants: Alice, Bob, Charlie.
    Fair share = $210 each.
    Charlie owes Bob $210, Alice owes Bob $30.
    Total paid equals total fair shares ($630.00). Net balances sum to exactly $0.00.
    """
    expenses = [
        ExpenseEntry(payer_name="Bob", amount=Decimal("450.00"), description="Lodging"),
        ExpenseEntry(payer_name="Alice", amount=Decimal("180.00"), description="Groceries"),
    ]
    participants = ["Alice", "Bob", "Charlie"]

    result = ExpenseCalculator.calculate_split(
        expenses=expenses,
        participants=participants,
        split_method="EQUAL",
        currency="USD",
    )

    assert result.total_expenses == Decimal("630.00")
    assert result.discrepancy_cents == Decimal("0.00")

    shares_by_name = {s.participant_name: s for s in result.participant_shares}
    assert shares_by_name["Bob"].paid_amount == Decimal("450.00")
    assert shares_by_name["Bob"].fair_share == Decimal("210.00")
    assert shares_by_name["Bob"].net_balance == Decimal("240.00")

    assert shares_by_name["Alice"].paid_amount == Decimal("180.00")
    assert shares_by_name["Alice"].fair_share == Decimal("210.00")
    assert shares_by_name["Alice"].net_balance == Decimal("-30.00")

    assert shares_by_name["Charlie"].paid_amount == Decimal("0.00")
    assert shares_by_name["Charlie"].fair_share == Decimal("210.00")
    assert shares_by_name["Charlie"].net_balance == Decimal("-210.00")

    # Verify settlement transfers
    transfers = result.settlement_transfers
    assert len(transfers) == 2

    charlie_transfer = next(t for t in transfers if t.from_participant == "Charlie")
    assert charlie_transfer.to_participant == "Bob"
    assert charlie_transfer.amount == Decimal("210.00")

    alice_transfer = next(t for t in transfers if t.from_participant == "Alice")
    assert alice_transfer.to_participant == "Bob"
    assert alice_transfer.amount == Decimal("30.00")


def test_expense_calculator_penny_safe_rounding():
    """Verify that 3 participants splitting $100.00 equal shares sums to exactly $100.00
    without losing pennies ($33.34, $33.33, $33.33).
    """
    expenses = [
        ExpenseEntry(payer_name="Alice", amount=Decimal("100.00"), description="Dinner"),
    ]
    participants = ["Alice", "Bob", "Charlie"]

    result = ExpenseCalculator.calculate_split(
        expenses=expenses,
        participants=participants,
        split_method="EQUAL",
    )

    total_fair = sum(s.fair_share for s in result.participant_shares)
    assert total_fair == Decimal("100.00")
    assert result.discrepancy_cents == Decimal("0.00")

    amounts = sorted([s.fair_share for s in result.participant_shares], reverse=True)
    assert amounts == [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")]


def test_expense_calculator_percentage_split():
    """Verify percentage-based split (e.g. 60% / 40%)."""
    expenses = [
        ExpenseEntry(payer_name="Alice", amount=Decimal("200.00"), description="Equipment"),
    ]
    participants = ["Alice", "Bob"]
    percentages = {"Alice": Decimal("60"), "Bob": Decimal("40")}

    result = ExpenseCalculator.calculate_split(
        expenses=expenses,
        participants=participants,
        split_method="PERCENTAGE",
        percentages=percentages,
    )

    assert result.total_expenses == Decimal("200.00")
    shares_by_name = {s.participant_name: s for s in result.participant_shares}
    assert shares_by_name["Alice"].fair_share == Decimal("120.00")
    assert shares_by_name["Bob"].fair_share == Decimal("80.00")


def test_expense_calculator_custom_amounts():
    """Verify custom fixed amounts."""
    expenses = [
        ExpenseEntry(payer_name="Alice", amount=Decimal("150.00"), description="Party"),
    ]
    participants = ["Alice", "Bob"]
    custom_amounts = {"Alice": Decimal("100.00"), "Bob": Decimal("50.00")}

    result = ExpenseCalculator.calculate_split(
        expenses=expenses,
        participants=participants,
        split_method="CUSTOM",
        custom_amounts=custom_amounts,
    )

    shares_by_name = {s.participant_name: s for s in result.participant_shares}
    assert shares_by_name["Alice"].fair_share == Decimal("100.00")
    assert shares_by_name["Bob"].fair_share == Decimal("50.00")


# ==============================================================================
# 2. Conversation Intelligence API Endpoints E2E Tests
# ==============================================================================


@pytest.mark.asyncio
async def test_analyze_conversation_and_retrieve_analysis(client: AsyncClient):
    """Verify end-to-end flow: ingest text -> run analysis -> retrieve analysis and financial summary."""
    token = await get_auth_token(client, "user_analysis@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Ingest conversation
    ingest_res = await client.post(
        "/api/v1/accord/conversations/text",
        json={
            "title": "Lake Tahoe Weekend Trip",
            "content": """[11/04/26, 14:00] Bob: I booked the cabin for $450.
[11/04/26, 14:05] Alice: Great, I bought groceries for $180.
[11/04/26, 14:10] Charlie: Sounds good, we will split everything equally 3 ways.""",
        },
        headers=headers,
    )
    assert ingest_res.status_code == 201
    conv_id = ingest_res.json()["id"]

    # 2. Run analysis
    analyze_res = await client.post(
        f"/api/v1/accord/conversations/{conv_id}/analyze",
        headers=headers,
    )
    assert analyze_res.status_code == 200
    analysis = analyze_res.json()

    assert analysis["conversation_id"] == conv_id
    assert analysis["status"] == "COMPLETED"
    assert analysis["ai_model"] == "mock-gemini-v1"
    assert len(analysis["financial_facts"]) >= 1
    assert len(analysis["ambiguities"]) >= 1
    assert len(analysis["agreements"]) == 1

    agreement = analysis["agreements"][0]
    assert agreement["status"] == "DRAFT"
    assert agreement["is_confirmed"] is False
    assert len(agreement["history"]) >= 1

    # 3. Retrieve latest analysis for conversation
    latest_res = await client.get(
        f"/api/v1/accord/conversations/{conv_id}/analysis",
        headers=headers,
    )
    assert latest_res.status_code == 200
    assert latest_res.json()["id"] == analysis["id"]

    # 4. Retrieve analysis by analysis_id
    analysis_id = analysis["id"]
    by_id_res = await client.get(
        f"/api/v1/accord/analyses/{analysis_id}",
        headers=headers,
    )
    assert by_id_res.status_code == 200
    assert by_id_res.json()["id"] == analysis_id

    # 5. Retrieve ambiguities
    ambiguities_res = await client.get(
        f"/api/v1/accord/analyses/{analysis_id}/ambiguities",
        headers=headers,
    )
    assert ambiguities_res.status_code == 200
    ambiguities = ambiguities_res.json()
    assert len(ambiguities) >= 1
    assert ambiguities[0]["status"] == "UNRESOLVED"

    # 6. Resolve an ambiguity
    amb_id = ambiguities[0]["id"]
    resolve_res = await client.post(
        f"/api/v1/accord/ambiguities/{amb_id}/resolve",
        json={"resolution": "Equally split between Alice, Bob, and Charlie."},
        headers=headers,
    )
    assert resolve_res.status_code == 200
    resolved_amb = resolve_res.json()
    assert resolved_amb["status"] == "RESOLVED"
    assert resolved_amb["resolution_text"] == "Equally split between Alice, Bob, and Charlie."
    assert resolved_amb["resolved_at"] is not None

    # 7. Update draft agreement
    agreement_id = agreement["id"]
    update_res = await client.patch(
        f"/api/v1/accord/agreements/{agreement_id}",
        json={
            "title": "Lake Tahoe Final Agreement",
            "summary": "Agreed 3-way split for lodging and groceries.",
        },
        headers=headers,
    )
    assert update_res.status_code == 200
    updated_agr = update_res.json()
    assert updated_agr["title"] == "Lake Tahoe Final Agreement"
    assert updated_agr["status"] == "UNDER_REVIEW"

    # 8. Owner binds participants and participants accept the current agreement version
    parts_by_name = {p["name"]: p["id"] for p in updated_agr["participants"]}
    for name, email in [("Alice", "alice_test@example.com"), ("Bob", "bob_test@example.com"), ("Charlie", "charlie_test@example.com")]:
        reg_res = await client.post("/api/v1/auth/register", json={"email": email, "password": "Password123!", "full_name": name})
        p_token = reg_res.json()["tokens"]["access_token"]
        p_id = next(pid for pname, pid in parts_by_name.items() if name.lower() in pname.lower())
        bind_res = await client.post(
            f"/api/v1/accord/agreements/{agreement_id}/participants/{p_id}/bind",
            json={"email": email},
            headers=headers,
        )
        assert bind_res.status_code == 200
        await client.post(
            f"/api/v1/accord/agreements/{agreement_id}/participants/{p_id}/respond",
            json={"response": "ACCEPTED", "comment": f"I {name} agree to version 2."},
            headers={"Authorization": f"Bearer {p_token}"},
        )

    # 9. Confirm agreement
    confirm_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/confirm",
        json={"notes": "All parties verbally agreed on chat."},
        headers=headers,
    )
    assert confirm_res.status_code == 200
    confirmed_agr = confirm_res.json()
    assert confirmed_agr["status"] == "CONFIRMED"
    assert confirmed_agr["is_confirmed"] is True
    assert confirmed_agr["confirmed_at"] is not None

    # Editing a confirmed agreement should return 400
    bad_edit_res = await client.patch(
        f"/api/v1/accord/agreements/{agreement_id}",
        json={"title": "Should Fail"},
        headers=headers,
    )
    assert bad_edit_res.status_code == 400

    # 9. Get live financial summary
    fin_summary_res = await client.get(
        f"/api/v1/accord/conversations/{conv_id}/financial-summary",
        headers=headers,
    )
    assert fin_summary_res.status_code == 200
    fin_data = fin_summary_res.json()
    assert "total_expenses" in fin_data
    assert "participant_shares" in fin_data
    assert "settlement_transfers" in fin_data
    assert "disclaimer" in fin_data


@pytest.mark.asyncio
async def test_agreement_rejection_lifecycle(client: AsyncClient):
    """Verify rejecting an agreement draft records reason and audit trail."""
    token = await get_auth_token(client, "user_reject@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Ingest conversation
    ingest_res = await client.post(
        "/api/v1/accord/conversations/text",
        json={
            "title": "Freelance Milestone Disagreement",
            "content": """[11/04/26, 10:00] Client: We need redesign by Friday.
[11/04/26, 10:05] Freelancer: That is $500 milestone 1.""",
        },
        headers=headers,
    )
    conv_id = ingest_res.json()["id"]

    # Analyze
    analyze_res = await client.post(
        f"/api/v1/accord/conversations/{conv_id}/analyze",
        headers=headers,
    )
    agreement_id = analyze_res.json()["agreements"][0]["id"]

    # Reject agreement
    reject_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/reject",
        json={
            "rejection_reason": "Price terms were not mutually agreed.",
            "notes": "Freelancer wanted $500, Client offered $300.",
        },
        headers=headers,
    )
    assert reject_res.status_code == 200
    rejected_agr = reject_res.json()
    assert rejected_agr["status"] == "REJECTED"
    assert rejected_agr["is_confirmed"] is False
    assert rejected_agr["rejection_reason"] == "Price terms were not mutually agreed."
    assert len(rejected_agr["history"]) >= 2  # CREATED + REJECTED


@pytest.mark.asyncio
async def test_intelligence_idor_protection(client: AsyncClient):
    """Verify strict tenant isolation and IDOR protection on all intelligence endpoints."""
    token_owner = await get_auth_token(client, "owner@example.com")
    token_attacker = await get_auth_token(client, "attacker@example.com")

    # Owner creates conversation & runs analysis
    ingest_res = await client.post(
        "/api/v1/accord/conversations/text",
        json={
            "title": "Private Owner Conversation",
            "content": "[11/04/26, 09:00] Owner: Secret expense $500.",
        },
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    conv_id = ingest_res.json()["id"]

    analyze_res = await client.post(
        f"/api/v1/accord/conversations/{conv_id}/analyze",
        headers={"Authorization": f"Bearer {token_owner}"},
    )
    assert analyze_res.status_code == 200
    analysis_data = analyze_res.json()
    analysis_id = analysis_data["id"]
    agreement_id = analysis_data["agreements"][0]["id"]
    ambiguity_id = analysis_data["ambiguities"][0]["id"]

    attacker_headers = {"Authorization": f"Bearer {token_attacker}"}

    # 1. Attacker cannot trigger analysis on owner's conversation
    res = await client.post(f"/api/v1/accord/conversations/{conv_id}/analyze", headers=attacker_headers)
    assert res.status_code == 404

    # 2. Attacker cannot view analysis
    res = await client.get(f"/api/v1/accord/conversations/{conv_id}/analysis", headers=attacker_headers)
    assert res.status_code == 404

    res = await client.get(f"/api/v1/accord/analyses/{analysis_id}", headers=attacker_headers)
    assert res.status_code == 404

    # 3. Attacker cannot view or resolve ambiguities
    res = await client.get(f"/api/v1/accord/analyses/{analysis_id}/ambiguities", headers=attacker_headers)
    assert res.status_code == 404

    res = await client.post(
        f"/api/v1/accord/ambiguities/{ambiguity_id}/resolve",
        json={"resolution": "Hacked"},
        headers=attacker_headers,
    )
    assert res.status_code == 404

    # 4. Attacker cannot update, confirm, or reject agreement
    res = await client.patch(
        f"/api/v1/accord/agreements/{agreement_id}",
        json={"title": "Hacked Title"},
        headers=attacker_headers,
    )
    assert res.status_code == 404

    res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/confirm",
        headers=attacker_headers,
    )
    assert res.status_code == 404

    res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/reject",
        json={"rejection_reason": "Malicious reject"},
        headers=attacker_headers,
    )
    assert res.status_code == 404

    # 5. Attacker cannot get financial summary
    res = await client.get(
        f"/api/v1/accord/conversations/{conv_id}/financial-summary",
        headers=attacker_headers,
    )
    assert res.status_code == 404


# ==============================================================================
# 5. Reliability & Stuck-Job Regression Tests
# ==============================================================================


class TimeoutMockAIServiceAdapter(AIServiceAdapter):
    """Simulates Gemini API timeout."""

    def extract_conversation(self, messages, title=None):
        raise TimeoutError("Gemini API request timed out after 45.0s (hard limit: 45.0s) on model 'gemini-3.8-flash'.")


@pytest.mark.asyncio
async def test_gemini_timeout_recovery_marks_failed(client: AsyncClient):
    """Verify that when Gemini times out or fails, the analysis record is safely
    marked as FAILED with error details, and never marked as successful or left spinning.
    """
    token = await get_auth_token(client, "timeout_test@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Ingest conversation
    ingest_res = await client.post(
        "/api/v1/accord/conversations/text",
        json={
            "title": "Timeout Test Chat",
            "content": "[11/04/26, 14:00] Alice: $500 payment pending.",
        },
        headers=headers,
    )
    conv_id = ingest_res.json()["id"]

    # Temporarily set the timeout adapter
    set_ai_adapter(TimeoutMockAIServiceAdapter())
    try:
        analyze_res = await client.post(
            f"/api/v1/accord/conversations/{conv_id}/analyze?sync=true",
            headers=headers,
        )
        assert analyze_res.status_code == 200
        analysis = analyze_res.json()
        assert analysis["status"] == "FAILED"
        assert "timed out" in analysis["error_message"].lower()
        assert analysis["execution_duration_ms"] is not None
        assert len(analysis["agreements"]) == 0
    finally:
        set_ai_adapter(MockAIServiceAdapter())


@pytest.mark.asyncio
async def test_stale_processing_job_recovery(client: AsyncClient, test_db_session: AsyncSession):
    """Verify that stale PROCESSING and QUEUED jobs older than threshold are safely
    recovered to FAILED and never marked successful.
    """
    from datetime import datetime, timezone, timedelta
    from app.accord.models.analysis import ConversationAnalysis
    from app.accord.services.analyzer import ConversationAnalyzerService

    token = await get_auth_token(client, "stale_test@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Ingest conversation
    ingest_res = await client.post(
        "/api/v1/accord/conversations/text",
        json={
            "title": "Stale Recovery Chat",
            "content": "[11/04/26, 14:00] Bob: Total $300.",
        },
        headers=headers,
    )
    conv_id = uuid.UUID(ingest_res.json()["id"])
    me_res = await client.get("/api/v1/auth/me", headers=headers)
    user_id = uuid.UUID(me_res.json()["id"])

    # Insert a simulated stuck job that has been PROCESSING for 10 minutes
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    stuck_analysis = ConversationAnalysis(
        conversation_id=conv_id,
        created_by_user_id=user_id,
        status="PROCESSING",
        ai_model="gemini-3.8-flash",
        created_at=stale_time,
        updated_at=stale_time,
    )
    test_db_session.add(stuck_analysis)
    await test_db_session.commit()
    await test_db_session.refresh(stuck_analysis)

    assert stuck_analysis.status == "PROCESSING"

    # Recover stale jobs
    recovered_count = await ConversationAnalyzerService.recover_stale_analyses(
        db=test_db_session,
        conversation_id=conv_id,
        max_age_seconds=90,
    )
    assert recovered_count >= 1

    await test_db_session.refresh(stuck_analysis)
    assert stuck_analysis.status == "FAILED"
    assert "timed out" in stuck_analysis.error_message.lower()
    assert stuck_analysis.status != "COMPLETED"


@pytest.mark.asyncio
async def test_force_retry_clears_active_job_and_restarts(client: AsyncClient):
    """Verify that force_retry=True supersedes existing active/failed jobs and runs a fresh analysis."""
    token = await get_auth_token(client, "retry_test@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Ingest conversation
    ingest_res = await client.post(
        "/api/v1/accord/conversations/text",
        json={
            "title": "Retry Test Chat",
            "content": "[11/04/26, 14:00] Alice: We split $100.",
        },
        headers=headers,
    )
    conv_id = ingest_res.json()["id"]

    # First analysis with failing adapter
    set_ai_adapter(TimeoutMockAIServiceAdapter())
    try:
        res1 = await client.post(
            f"/api/v1/accord/conversations/{conv_id}/analyze?sync=true",
            headers=headers,
        )
        assert res1.json()["status"] == "FAILED"
    finally:
        set_ai_adapter(MockAIServiceAdapter())

    # Second analysis with force_retry=true and healthy adapter
    res2 = await client.post(
        f"/api/v1/accord/conversations/{conv_id}/analyze?sync=true&force_retry=true",
        headers=headers,
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] == "COMPLETED"
    assert len(data2["agreements"]) == 1
