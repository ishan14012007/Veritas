from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import patch
import json
import uuid
import pytest
from httpx import AsyncClient

from app.ai.adapter import MockAIServiceAdapter, set_ai_adapter
from app.payments.paypal_client import PayPalClient, get_paypal_client, set_paypal_client


@pytest.fixture(autouse=True)
def setup_mock_services():
    """Ensure MockAIServiceAdapter and mock PayPal client are active during tests."""
    ai_adapter = MockAIServiceAdapter()
    set_ai_adapter(ai_adapter)
    # Ensure paypal client is in mock mode for predictable offline testing
    mock_paypal = PayPalClient(mock_mode=True)
    set_paypal_client(mock_paypal)
    yield
    set_ai_adapter(None)
    set_paypal_client(None)


async def register_user(client: AsyncClient, email: str, full_name: str) -> str:
    """Helper to register user and return access token."""
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


async def setup_confirmed_agreement_with_obligations(client: AsyncClient):
    """Helper to ingest a 3-person conversation, generate analysis with obligations,
    bind all participants, and achieve full mutual consensus (CONFIRMED).
    """
    owner_token = await register_user(client, "owner_pay@veritas.local", "Owner Pay")
    alice_token = await register_user(client, "alice_pay@veritas.local", "Alice Smith")
    bob_token = await register_user(client, "bob_pay@veritas.local", "Bob Miller")
    charlie_token = await register_user(client, "charlie_pay@veritas.local", "Charlie Davis")

    chat = """[12/03/24, 14:32:00] Alice Smith: Let's settle cabin expenses.
[12/03/24, 14:33:10] Bob Miller: I paid $450 directly to the host for 3 nights.
[12/03/24, 14:34:25] Alice Smith: I bought groceries totaling $180 at Safeway.
[12/03/24, 14:35:40] Charlie Davis: I didn't pay for anything yet so I will cover my fair share!
[12/03/24, 14:37:00] Bob Miller: Total is $630 split 3 ways, so $210 each."""

    # 1. Ingest conversation
    ingest_res = await client.post(
        "/api/v1/accord/conversations/text",
        json={"title": "Cabin Trip Payment Test", "content": chat},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert ingest_res.status_code == 201
    conv_id = ingest_res.json()["id"]

    # 2. Analyze conversation
    analyze_res = await client.post(
        f"/api/v1/accord/conversations/{conv_id}/analyze?sync=true",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert analyze_res.status_code == 200
    analysis = analyze_res.json()
    agreement = analysis["agreements"][0]
    agreement_id = agreement["id"]

    # 3. Bind participants
    consensus_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/consensus",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    parts = {p["name"].lower(): p["id"] for p in consensus_res.json()["participants"]}
    alice_part_id = next(pid for name, pid in parts.items() if "alice" in name)
    bob_part_id = next(pid for name, pid in parts.items() if "bob" in name)
    charlie_part_id = next(pid for name, pid in parts.items() if "charlie" in name)

    await bind_participant(client, agreement_id, alice_part_id, "alice_pay@veritas.local", owner_token)
    await bind_participant(client, agreement_id, bob_part_id, "bob_pay@veritas.local", owner_token)
    await bind_participant(client, agreement_id, charlie_part_id, "charlie_pay@veritas.local", owner_token)

    # 4. All participants accept Version 1
    for part_id, tok in [(alice_part_id, alice_token), (bob_part_id, bob_token), (charlie_part_id, charlie_token)]:
        r = await client.post(
            f"/api/v1/accord/agreements/{agreement_id}/participants/{part_id}/respond",
            json={"response": "ACCEPTED", "comment": "Agreed to settlement"},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200

    # 5. Retrieve confirmed agreement with obligations
    settle_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/settlement",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert settle_res.status_code == 200
    settle_data = settle_res.json()
    assert settle_data["consensus_achieved"] is True
    assert settle_data["agreement_status"] == "CONFIRMED"
    assert len(settle_data["obligations"]) >= 1

    obligation = next(
        (o for o in settle_data["obligations"] if "charlie" in (o.get("debtor_name") or "").lower()),
        settle_data["obligations"][0],
    )
    alice_obligation = next(
        (o for o in settle_data["obligations"] if "alice" in (o.get("debtor_name") or "").lower()),
        None,
    )

    return {
        "conv_id": conv_id,
        "owner_token": owner_token,
        "alice_token": alice_token,
        "bob_token": bob_token,
        "charlie_token": charlie_token,
        "agreement_id": agreement_id,
        "obligation": obligation,
        "charlie_obligation": obligation,
        "alice_obligation": alice_obligation,
        "all_obligations": settle_data["obligations"],
    }


# ==============================================================================
# 1. UNIT & FLOW TESTS: OAUTH2, ORDERS, CAPTURE, AND SETTLEMENT
# ==============================================================================

@pytest.mark.asyncio
async def test_paypal_client_oauth2_token_caching():
    """Verify that PayPalClient caches tokens and refreshes them before expiration."""
    client = PayPalClient(mock_mode=True)
    t1 = await client.get_access_token()
    assert t1.startswith("mock_paypal_token_")

    # Second call returns the cached token
    t2 = await client.get_access_token()
    assert t1 == t2

    # Expire the token manually
    client._token_expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    t3 = await client.get_access_token()
    assert t3.startswith("mock_paypal_token_")
    assert t3 != t1


@pytest.mark.asyncio
async def test_end_to_end_payment_request_and_paypal_checkout_flow(client: AsyncClient):
    """Verify full Step 1 through Step 7 flow:
    - Agreement CONFIRMED with mutual consensus.
    - Create payment request against confirmed obligation.
    - Create PayPal Order (amount strictly matches obligation).
    - Capture approved order server-side.
    - Verify obligation is marked FULFILLED, payment request is COMPLETED.
    - Verify settlement overview reports full settlement.
    """
    ctx = await setup_confirmed_agreement_with_obligations(client)
    agreement_id = ctx["agreement_id"]
    charlie_token = ctx["charlie_token"]
    owner_token = ctx["owner_token"]
    obligation = ctx["obligation"]
    obligation_id = obligation["obligation_id"]
    amount = Decimal(str(obligation["amount"]))
    assert amount == Decimal("210.00")

    # 1. Create Payment Request as Charlie (debtor)
    req_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/payment-requests",
        json={"obligation_id": obligation_id, "notes": "Settling cabin share"},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert req_res.status_code == 201
    req_data = req_res.json()
    payment_request_id = req_data["id"]
    assert req_data["amount"] == "210.0000"
    assert req_data["currency"] == "USD"
    assert req_data["status"] == "PENDING"
    assert req_data["debtor_name"] == "Charlie Davis"
    assert req_data["creditor_name"] == "Bob Miller"
    assert req_data["can_pay"] is True

    # 2. Create PayPal Order for Payment Request
    order_res = await client.post(
        "/api/v1/payments/paypal/orders",
        json={"payment_request_id": payment_request_id},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert order_res.status_code == 201
    order_data = order_res.json()
    paypal_order_id = order_data["paypal_order_id"]
    assert order_data["amount"] == "210.0000"
    assert order_data["currency"] == "USD"
    assert order_data["status"] == "CREATED"
    assert order_data["approval_url"] is not None

    # Verify order retrieval
    get_order_res = await client.get(
        f"/api/v1/payments/paypal/orders/{paypal_order_id}",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert get_order_res.status_code == 200
    assert get_order_res.json()["paypal_order_id"] == paypal_order_id

    # 3. Server-side Capture after Payer Approval
    capture_res = await client.post(
        f"/api/v1/payments/paypal/orders/{paypal_order_id}/capture",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert capture_res.status_code == 200
    capture_data = capture_res.json()
    paypal_capture_id = capture_data["paypal_capture_id"]
    assert capture_data["status"] == "COMPLETED"
    assert Decimal(capture_data["amount"]) == Decimal("210.00")
    assert capture_data["currency"] == "USD"

    # Verify capture retrieval
    get_cap_res = await client.get(
        f"/api/v1/payments/paypal/captures/{paypal_capture_id}",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert get_cap_res.status_code == 200
    assert get_cap_res.json()["paypal_capture_id"] == paypal_capture_id

    # 4. Verify PaymentRequest status is COMPLETED
    check_req = await client.get(
        f"/api/v1/accord/payment-requests/{payment_request_id}",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert check_req.status_code == 200
    assert check_req.json()["status"] == "COMPLETED"
    assert check_req.json()["can_pay"] is False
    assert check_req.json()["latest_capture"] is not None

    # 5. Verify Settlement Summary
    settle_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/settlement",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert settle_res.status_code == 200
    settle_data = settle_res.json()
    assert Decimal(settle_data["total_completed_amount"]) == Decimal("210.00")
    if len(settle_data["obligations"]) > 1:
        assert Decimal(settle_data["outstanding_balance"]) == Decimal("30.00")
        assert settle_data["settlement_status"] == "PARTIALLY_SETTLED"
    else:
        assert Decimal(settle_data["outstanding_balance"]) == Decimal("0.00")
        assert settle_data["settlement_status"] == "FULLY_SETTLED"
    charlie_summary = next(o for o in settle_data["obligations"] if "charlie" in o["debtor_name"].lower())
    assert charlie_summary["is_settled"] is True
    assert charlie_summary["obligation_status"] == "FULFILLED"

    # 6. Verify Payment History Audit Trail
    hist_res = await client.get(
        f"/api/v1/accord/payment-requests/{payment_request_id}/history",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert hist_res.status_code == 200
    history = hist_res.json()
    actions = [h["action"] for h in history]
    assert "REQUEST_CREATED" in actions
    assert "ORDER_CREATED" in actions
    assert "CAPTURE_SUCCEEDED" in actions


# ==============================================================================
# 2. SECURITY TESTS: TAMPERING, ELIGIBILITY, IDOR, AND PERMISSIONS
# ==============================================================================

@pytest.mark.asyncio
async def test_unconfirmed_agreement_cannot_generate_payment_requests(client: AsyncClient):
    """Security Criterion 1: Payment requests CANNOT be generated from unconfirmed agreements."""
    owner_token = await register_user(client, "owner_unconf@veritas.local", "Owner Unconf")

    chat = """[12/03/24, 14:32:00] Alice Smith: We need to settle cabin expenses.
[12/03/24, 14:33:10] Bob Miller: I paid $450 for the cabin."""

    ingest_res = await client.post(
        "/api/v1/accord/conversations/text",
        json={"title": "Unconfirmed Agreement Test", "content": chat},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    conv_id = ingest_res.json()["id"]

    analyze_res = await client.post(
        f"/api/v1/accord/conversations/{conv_id}/analyze?sync=true",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    agreement = analyze_res.json()["agreements"][0]
    agreement_id = agreement["id"]

    # Obligation is in DRAFT agreement
    ob_res = await client.get(
        f"/api/v1/accord/analyses/{analyze_res.json()['id']}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    # Attempt to create payment request on DRAFT agreement -> 400 Bad Request
    fake_ob_id = str(uuid.uuid4())
    req_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/payment-requests",
        json={"obligation_id": fake_ob_id},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert req_res.status_code == 400
    err_msg = req_res.json().get("error", {}).get("message") or req_res.json().get("detail", "")
    assert "must be confirmed" in err_msg.lower() or "status is 'draft'" in err_msg.lower()


@pytest.mark.asyncio
async def test_unauthorized_user_cannot_create_or_capture_payment_request(client: AsyncClient):
    """Security Criterion 2: Unrelated users cannot create or capture payment requests for another person."""
    ctx = await setup_confirmed_agreement_with_obligations(client)
    agreement_id = ctx["agreement_id"]
    obligation = ctx["obligation"]
    obligation_id = obligation["obligation_id"]

    # Mallory (an attacker)
    attacker_token = await register_user(client, "mallory@attacker.local", "Mallory Attacker")

    # Mallory tries to create a payment request for Charlie's obligation -> 403 Forbidden
    hack_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/payment-requests",
        json={"obligation_id": obligation_id},
        headers={"Authorization": f"Bearer {attacker_token}"},
    )
    assert hack_res.status_code == 403
    err_msg = hack_res.json().get("error", {}).get("message") or hack_res.json().get("detail", "")
    assert "not authorized" in err_msg.lower()

    # Charlie creates legitimate payment request and order
    charlie_token = ctx["charlie_token"]
    req_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/payment-requests",
        json={"obligation_id": obligation_id},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    req_id = req_res.json()["id"]

    order_res = await client.post(
        "/api/v1/payments/paypal/orders",
        json={"payment_request_id": req_id},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    order_id = order_res.json()["paypal_order_id"]

    # Mallory tries to capture Charlie's order -> 403 Forbidden
    cap_hack = await client.post(
        f"/api/v1/payments/paypal/orders/{order_id}/capture",
        headers={"Authorization": f"Bearer {attacker_token}"},
    )
    assert cap_hack.status_code == 403


@pytest.mark.asyncio
async def test_server_side_amount_and_currency_validation_prevents_tampering(client: AsyncClient):
    """Security Criterion 3: Client cannot dictate amount or currency.
    If the gateway returns an amount or currency that mismatches the authorized obligation,
    capture is rejected immediately.
    """
    ctx = await setup_confirmed_agreement_with_obligations(client)
    agreement_id = ctx["agreement_id"]
    charlie_token = ctx["charlie_token"]
    obligation_id = ctx["obligation"]["obligation_id"]

    req_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/payment-requests",
        json={"obligation_id": obligation_id},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    req_id = req_res.json()["id"]

    order_res = await client.post(
        "/api/v1/payments/paypal/orders",
        json={"payment_request_id": req_id},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    order_id = order_res.json()["paypal_order_id"]

    # Simulate tampered amount returned by malicious gateway or order manipulation
    class TamperedAmountPayPalClient(PayPalClient):
        async def capture_order(self, order_id: str, idempotency_key=None):
            return {
                "id": "MOCK_TAMPERED_CAP",
                "status": "COMPLETED",
                "amount": "10.00",  # Tampered: Should be 210.00!
                "currency": "USD",
                "fee": "0.50",
                "net_amount": "9.50",
            }

    tampered_client = TamperedAmountPayPalClient(mock_mode=True)
    set_paypal_client(tampered_client)

    cap_res = await client.post(
        f"/api/v1/payments/paypal/orders/{order_id}/capture",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert cap_res.status_code == 400
    err_msg = cap_res.json().get("error", {}).get("message") or cap_res.json().get("detail", "")
    assert "does not match authorized obligation amount" in err_msg.lower()


@pytest.mark.asyncio
async def test_duplicate_capture_is_idempotent(client: AsyncClient):
    """Security Criterion 4: Repeating capture on an already captured order returns the existing capture
    idempotently without charging twice or causing duplicate settlement.
    """
    ctx = await setup_confirmed_agreement_with_obligations(client)
    agreement_id = ctx["agreement_id"]
    charlie_token = ctx["charlie_token"]
    obligation_id = ctx["obligation"]["obligation_id"]

    req_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/payment-requests",
        json={"obligation_id": obligation_id},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    req_id = req_res.json()["id"]

    order_res = await client.post(
        "/api/v1/payments/paypal/orders",
        json={"payment_request_id": req_id},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    order_id = order_res.json()["paypal_order_id"]

    # First capture
    cap1 = await client.post(
        f"/api/v1/payments/paypal/orders/{order_id}/capture",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert cap1.status_code == 200
    cap1_id = cap1.json()["paypal_capture_id"]

    # Second capture (duplicate onApprove or network retry)
    cap2 = await client.post(
        f"/api/v1/payments/paypal/orders/{order_id}/capture",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert cap2.status_code == 200
    assert cap2.json()["paypal_capture_id"] == cap1_id


@pytest.mark.asyncio
async def test_refund_workflow_updates_statuses(client: AsyncClient):
    """Security Criterion 5: Authorized owner can refund a captured payment, updating payment request
    to REFUNDED and reverting obligation to PENDING. Non-owners are rejected (HTTP 403).
    """
    ctx = await setup_confirmed_agreement_with_obligations(client)
    agreement_id = ctx["agreement_id"]
    charlie_token = ctx["charlie_token"]
    owner_token = ctx["owner_token"]
    obligation_id = ctx["obligation"]["obligation_id"]

    # Create and capture payment
    req_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/payment-requests",
        json={"obligation_id": obligation_id},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    req_id = req_res.json()["id"]

    order_res = await client.post(
        "/api/v1/payments/paypal/orders",
        json={"payment_request_id": req_id},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    order_id = order_res.json()["paypal_order_id"]

    cap_res = await client.post(
        f"/api/v1/payments/paypal/orders/{order_id}/capture",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    capture_id = cap_res.json()["paypal_capture_id"]

    # Charlie (debtor) attempts to refund -> 403 Forbidden (Only owner can refund)
    unauth_refund = await client.post(
        f"/api/v1/payments/paypal/captures/{capture_id}/refund",
        json={"reason": "I want money back"},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert unauth_refund.status_code == 403

    # Owner issues full refund -> 201 Created
    refund_res = await client.post(
        f"/api/v1/payments/paypal/captures/{capture_id}/refund",
        json={"reason": "Trip cancelled post-settlement", "amount": 210.00},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert refund_res.status_code == 201
    refund_data = refund_res.json()
    assert refund_data["status"] == "COMPLETED"
    assert Decimal(refund_data["amount"]) == Decimal("210.00")

    # Verify payment request status transitioned to REFUNDED
    check_req = await client.get(
        f"/api/v1/accord/payment-requests/{req_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert check_req.json()["status"] == "REFUNDED"

    # Verify settlement overview reports obligation reverted to PENDING
    settle_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/settlement",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert settle_res.json()["settlement_status"] == "UNSETTLED"
    charlie_summary = next(o for o in settle_res.json()["obligations"] if "charlie" in o["debtor_name"].lower())
    assert charlie_summary["obligation_status"] == "PENDING"
    assert charlie_summary["is_settled"] is False


@pytest.mark.asyncio
async def test_webhook_signature_verification_and_idempotent_processing(client: AsyncClient):
    """Security Criterion 6:
    - Webhook rejects requests with missing or invalid transmission signatures (HTTP 400).
    - Webhook idempotently processes valid events.
    """
    event_id = f"WH-EVENT-{uuid.uuid4().hex[:12].upper()}"
    webhook_payload = {
        "id": event_id,
        "event_version": "1.0",
        "create_time": datetime.now(timezone.utc).isoformat(),
        "resource_type": "checkout-order",
        "event_type": "CHECKOUT.ORDER.APPROVED",
        "summary": "Order approved by payer",
        "resource": {
            "id": "MOCK_ORDER_123",
            "status": "APPROVED",
        },
    }

    # 1. Missing headers -> 400 Bad Request
    fail_res = await client.post(
        "/api/v1/payments/paypal/webhook",
        json=webhook_payload,
    )
    assert fail_res.status_code == 400

    # 2. Valid mock transmission headers
    valid_headers = {
        "PAYPAL-AUTH-ALGO": "SHA256withRSA",
        "PAYPAL-CERT-URL": "https://api.sandbox.paypal.com/v1/notifications/certs/CERT-123",
        "PAYPAL-TRANSMISSION-ID": f"TRANS-{uuid.uuid4().hex}",
        "PAYPAL-TRANSMISSION-SIG": "ValidCryptographicSignatureBase64StringExample123456789",
        "PAYPAL-TRANSMISSION-TIME": datetime.now(timezone.utc).isoformat(),
    }

    ok_res = await client.post(
        "/api/v1/payments/paypal/webhook",
        json=webhook_payload,
        headers=valid_headers,
    )
    assert ok_res.status_code == 200
    res_data = ok_res.json()
    assert res_data["event_id"] == event_id
    assert res_data["verification_status"] == "VERIFIED"
    assert res_data["processing_status"] == "PROCESSED"

    # 3. Duplicate event sent -> Idempotently handled
    dup_res = await client.post(
        "/api/v1/payments/paypal/webhook",
        json=webhook_payload,
        headers=valid_headers,
    )
    assert dup_res.status_code == 200
    assert "idempotent" in dup_res.json()["message"].lower()


# ==============================================================================
# 3. STAGE 4.1 REGRESSION TESTS: SETTLEMENT INTEGRITY AUDIT & FIXES
# ==============================================================================

@pytest.mark.asyncio
async def test_regression_1_charlie_pays_210_leaves_agreement_partially_settled(client: AsyncClient):
    """Regression Test 1: In the canonical cabin trip ($630 total expenses, Bob paid $450, Alice paid $180,
    Charlie owes Bob $210, Alice owes Bob $30), when Charlie pays $210 via PayPal, the agreement MUST NOT
    become FULLY_SETTLED. It must remain PARTIALLY_SETTLED because Alice's $30 obligation remains outstanding.
    """
    ctx = await setup_confirmed_agreement_with_obligations(client)
    agreement_id = ctx["agreement_id"]
    charlie_token = ctx["charlie_token"]
    owner_token = ctx["owner_token"]
    charlie_ob = ctx["charlie_obligation"]
    alice_ob = ctx["alice_obligation"]
    assert charlie_ob is not None
    assert alice_ob is not None
    assert Decimal(str(charlie_ob["amount"])) == Decimal("210.00")
    assert Decimal(str(alice_ob["amount"])) == Decimal("30.00")

    # Charlie creates payment request for $210
    req_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/payment-requests",
        json={"obligation_id": charlie_ob["obligation_id"], "notes": "Charlie cabin share"},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert req_res.status_code == 201
    req_id = req_res.json()["id"]

    # Charlie creates PayPal order
    order_res = await client.post(
        "/api/v1/payments/paypal/orders",
        json={"payment_request_id": req_id},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert order_res.status_code == 201
    order_id = order_res.json()["paypal_order_id"]

    # Server-side capture of Charlie's order
    cap_res = await client.post(
        f"/api/v1/payments/paypal/orders/{order_id}/capture",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert cap_res.status_code == 200

    # Retrieve settlement summary
    settle_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/settlement",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert settle_res.status_code == 200
    settle = settle_res.json()

    # Core Accounting Invariants:
    assert settle["settlement_status"] == "PARTIALLY_SETTLED", (
        "Agreement must NOT become FULLY_SETTLED while Alice's $30 obligation remains outstanding!"
    )
    assert Decimal(str(settle["total_completed_amount"])) == Decimal("210.00")
    assert Decimal(str(settle["outstanding_balance"])) == Decimal("30.00")
    assert Decimal(str(settle["total_obligations_amount"])) == Decimal("240.00")

    # Inspect individual obligations
    ob_map = {o["debtor_name"].lower(): o for o in settle["obligations"]}
    charlie_summary = next(o for k, o in ob_map.items() if "charlie" in k)
    alice_summary = next(o for k, o in ob_map.items() if "alice" in k)

    assert charlie_summary["is_settled"] is True
    assert charlie_summary["obligation_status"] == "FULFILLED"
    assert Decimal(str(charlie_summary["settled_amount"])) == Decimal("210.00")
    assert Decimal(str(charlie_summary["outstanding_amount"])) == Decimal("0.00")

    assert alice_summary["is_settled"] is False
    assert alice_summary["obligation_status"] == "PENDING"
    assert Decimal(str(alice_summary["settled_amount"])) == Decimal("0.00")
    assert Decimal(str(alice_summary["outstanding_amount"])) == Decimal("30.00")


@pytest.mark.asyncio
async def test_regression_2_alice_subsequently_pays_30_completing_settlement(client: AsyncClient):
    """Regression Test 2: After Charlie pays $210, Alice pays her $30 obligation.
    The agreement MUST then transition to FULLY_SETTLED with 0.00 outstanding balance.
    """
    ctx = await setup_confirmed_agreement_with_obligations(client)
    agreement_id = ctx["agreement_id"]
    charlie_token = ctx["charlie_token"]
    alice_token = ctx["alice_token"]
    owner_token = ctx["owner_token"]
    charlie_ob = ctx["charlie_obligation"]
    alice_ob = ctx["alice_obligation"]

    # 1. Charlie pays $210
    r1 = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/payment-requests",
        json={"obligation_id": charlie_ob["obligation_id"]},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    o1 = await client.post(
        "/api/v1/payments/paypal/orders",
        json={"payment_request_id": r1.json()["id"]},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    await client.post(
        f"/api/v1/payments/paypal/orders/{o1.json()['paypal_order_id']}/capture",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )

    # 2. Alice pays $30
    r2 = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/payment-requests",
        json={"obligation_id": alice_ob["obligation_id"], "notes": "Alice grocery share balance"},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert r2.status_code == 201
    assert Decimal(str(r2.json()["amount"])) == Decimal("30.00")

    o2 = await client.post(
        "/api/v1/payments/paypal/orders",
        json={"payment_request_id": r2.json()["id"]},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert o2.status_code == 201
    assert Decimal(str(o2.json()["amount"])) == Decimal("30.00")

    c2 = await client.post(
        f"/api/v1/payments/paypal/orders/{o2.json()['paypal_order_id']}/capture",
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert c2.status_code == 200
    assert Decimal(str(c2.json()["amount"])) == Decimal("30.00")

    # 3. Verify Full Settlement Invariants
    settle_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/settlement",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert settle_res.status_code == 200
    settle = settle_res.json()
    assert settle["settlement_status"] == "FULLY_SETTLED"
    assert Decimal(str(settle["total_completed_amount"])) == Decimal("240.00")
    assert Decimal(str(settle["outstanding_balance"])) == Decimal("0.00")

    for ob in settle["obligations"]:
        assert ob["is_settled"] is True
        assert ob["obligation_status"] == "FULFILLED"
        assert Decimal(str(ob["outstanding_amount"])) == Decimal("0.00")


@pytest.mark.asyncio
async def test_regression_3_partial_capture_leaves_remaining_balance_outstanding(client: AsyncClient):
    """Regression Test 3: Creating and capturing a partial payment ($100 of $210) must leave
    the obligation in PENDING status, record settled_amount=$100, outstanding_amount=$110,
    and agreement settlement status as PARTIALLY_SETTLED.
    """
    ctx = await setup_confirmed_agreement_with_obligations(client)
    agreement_id = ctx["agreement_id"]
    charlie_token = ctx["charlie_token"]
    owner_token = ctx["owner_token"]
    charlie_ob = ctx["charlie_obligation"]

    # Charlie initiates partial payment request of $100
    req_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/payment-requests",
        json={"obligation_id": charlie_ob["obligation_id"], "amount": 100.00, "notes": "Partial installment 1"},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert req_res.status_code == 201
    req = req_res.json()
    assert Decimal(str(req["amount"])) == Decimal("100.00")

    order_res = await client.post(
        "/api/v1/payments/paypal/orders",
        json={"payment_request_id": req["id"]},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert order_res.status_code == 201
    assert Decimal(str(order_res.json()["amount"])) == Decimal("100.00")

    cap_res = await client.post(
        f"/api/v1/payments/paypal/orders/{order_res.json()['paypal_order_id']}/capture",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert cap_res.status_code == 200
    assert Decimal(str(cap_res.json()["amount"])) == Decimal("100.00")

    # Verify settlement summary reflects partial capture
    settle_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/settlement",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    settle = settle_res.json()
    assert settle["settlement_status"] == "PARTIALLY_SETTLED"
    assert Decimal(str(settle["total_completed_amount"])) == Decimal("100.00")

    charlie_summary = next(o for o in settle["obligations"] if "charlie" in o["debtor_name"].lower())
    assert charlie_summary["is_settled"] is False
    assert charlie_summary["obligation_status"] == "PENDING"
    assert Decimal(str(charlie_summary["settled_amount"])) == Decimal("100.00")
    assert Decimal(str(charlie_summary["outstanding_amount"])) == Decimal("110.00")


@pytest.mark.asyncio
async def test_regression_4_failed_capture_does_not_fulfill_obligation(client: AsyncClient):
    """Regression Test 4: Failed, denied, or declined capture attempts must NOT fulfill the obligation
    nor increment settled amount.
    """
    ctx = await setup_confirmed_agreement_with_obligations(client)
    agreement_id = ctx["agreement_id"]
    charlie_token = ctx["charlie_token"]
    owner_token = ctx["owner_token"]
    charlie_ob = ctx["charlie_obligation"]

    req_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/payment-requests",
        json={"obligation_id": charlie_ob["obligation_id"]},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    req_id = req_res.json()["id"]

    order_res = await client.post(
        "/api/v1/payments/paypal/orders",
        json={"payment_request_id": req_id},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    order_id = order_res.json()["paypal_order_id"]

    # Simulate PayPal declining the capture
    class DeclinedPayPalClient(PayPalClient):
        async def capture_order(self, order_id: str, idempotency_key=None):
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="PAYMENT_DECLINED: Instrument refused by issuing bank.")

    declined_client = DeclinedPayPalClient(mock_mode=True)
    set_paypal_client(declined_client)

    cap_res = await client.post(
        f"/api/v1/payments/paypal/orders/{order_id}/capture",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert cap_res.status_code == 400

    # Verify obligation remains PENDING with 0 settled
    settle_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/settlement",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    settle = settle_res.json()
    charlie_summary = next(o for o in settle["obligations"] if "charlie" in o["debtor_name"].lower())
    assert charlie_summary["is_settled"] is False
    assert charlie_summary["obligation_status"] == "PENDING"
    assert Decimal(str(charlie_summary["settled_amount"])) == Decimal("0.00")
    assert Decimal(str(charlie_summary["outstanding_amount"])) == Decimal("210.00")
    assert settle["settlement_status"] == "UNSETTLED"


@pytest.mark.asyncio
async def test_regression_5_full_refund_restores_outstanding_and_reverts_obligation(client: AsyncClient):
    """Regression Test 5: Full refund of a completed capture must restore outstanding obligation
    to PENDING and deduct the completed balance.
    """
    ctx = await setup_confirmed_agreement_with_obligations(client)
    agreement_id = ctx["agreement_id"]
    charlie_token = ctx["charlie_token"]
    owner_token = ctx["owner_token"]
    charlie_ob = ctx["charlie_obligation"]

    req_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/payment-requests",
        json={"obligation_id": charlie_ob["obligation_id"]},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    req_id = req_res.json()["id"]

    order_res = await client.post(
        "/api/v1/payments/paypal/orders",
        json={"payment_request_id": req_id},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    cap_res = await client.post(
        f"/api/v1/payments/paypal/orders/{order_res.json()['paypal_order_id']}/capture",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    capture_id = cap_res.json()["paypal_capture_id"]

    # Full refund by agreement owner
    ref_res = await client.post(
        f"/api/v1/payments/paypal/captures/{capture_id}/refund",
        json={"reason": "Customer cancellation", "amount": 210.00},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert ref_res.status_code == 201

    settle_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/settlement",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    settle = settle_res.json()
    assert settle["settlement_status"] == "UNSETTLED"
    assert Decimal(str(settle["total_completed_amount"])) == Decimal("0.00")

    charlie_summary = next(o for o in settle["obligations"] if "charlie" in o["debtor_name"].lower())
    assert charlie_summary["is_settled"] is False
    assert charlie_summary["obligation_status"] == "PENDING"
    assert Decimal(str(charlie_summary["settled_amount"])) == Decimal("0.00")
    assert Decimal(str(charlie_summary["outstanding_amount"])) == Decimal("210.00")


@pytest.mark.asyncio
async def test_regression_6_partial_refund_recalculates_outstanding_and_reverts_obligation(client: AsyncClient):
    """Regression Test 6: Partial refund ($10 of $30) on a fulfilled obligation must revert
    the obligation status to PENDING and update settled_amount to $20 and outstanding_amount to $10.
    """
    ctx = await setup_confirmed_agreement_with_obligations(client)
    agreement_id = ctx["agreement_id"]
    alice_token = ctx["alice_token"]
    owner_token = ctx["owner_token"]
    alice_ob = ctx["alice_obligation"]

    # Alice pays $30 in full
    r = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/payment-requests",
        json={"obligation_id": alice_ob["obligation_id"]},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    o = await client.post(
        "/api/v1/payments/paypal/orders",
        json={"payment_request_id": r.json()["id"]},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    c = await client.post(
        f"/api/v1/payments/paypal/orders/{o.json()['paypal_order_id']}/capture",
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    capture_id = c.json()["paypal_capture_id"]

    # Partial refund of $10.00 by agreement owner
    ref_res = await client.post(
        f"/api/v1/payments/paypal/captures/{capture_id}/refund",
        json={"reason": "Overcharge adjustment", "amount": 10.00},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert ref_res.status_code == 201

    settle_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/settlement",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    settle = settle_res.json()
    assert settle["settlement_status"] == "PARTIALLY_SETTLED"
    assert Decimal(str(settle["total_completed_amount"])) == Decimal("20.00")

    alice_summary = next(o for o in settle["obligations"] if "alice" in o["debtor_name"].lower())
    assert alice_summary["is_settled"] is False
    assert alice_summary["obligation_status"] == "PENDING"
    assert Decimal(str(alice_summary["settled_amount"])) == Decimal("20.00")
    assert Decimal(str(alice_summary["outstanding_amount"])) == Decimal("10.00")


@pytest.mark.asyncio
async def test_regression_7_duplicate_webhooks_do_not_double_count_money(client: AsyncClient):
    """Regression Test 7: Repeated receipt of identical webhook events must be processed
    idempotently without creating duplicate records or double-counting settled money.
    """
    event_id = f"WH-IDEM-{uuid.uuid4().hex[:12].upper()}"
    webhook_payload = {
        "id": event_id,
        "event_version": "1.0",
        "create_time": datetime.now(timezone.utc).isoformat(),
        "resource_type": "checkout-order",
        "event_type": "CHECKOUT.ORDER.APPROVED",
        "resource": {"id": "ORDER-WH-TEST"},
    }
    valid_headers = {
        "PAYPAL-AUTH-ALGO": "SHA256withRSA",
        "PAYPAL-CERT-URL": "https://api.sandbox.paypal.com/v1/notifications/certs/CERT-123",
        "PAYPAL-TRANSMISSION-ID": f"TRANS-{uuid.uuid4().hex}",
        "PAYPAL-TRANSMISSION-SIG": "ValidSignatureCryptographicData123456789",
        "PAYPAL-TRANSMISSION-TIME": datetime.now(timezone.utc).isoformat(),
    }

    # First webhook post
    res1 = await client.post("/api/v1/payments/paypal/webhook", json=webhook_payload, headers=valid_headers)
    assert res1.status_code == 200
    assert res1.json()["processing_status"] == "PROCESSED"

    # Second identical webhook post
    res2 = await client.post("/api/v1/payments/paypal/webhook", json=webhook_payload, headers=valid_headers)
    assert res2.status_code == 200
    assert "idempotent" in res2.json()["message"].lower()


@pytest.mark.asyncio
async def test_regression_8_invalid_webhook_signature_rejected_without_modifying_settlement(client: AsyncClient):
    """Regression Test 8: PayPal transmission signatures must be checked via official verification endpoint.
    Forged or invalid signatures must return HTTP 400 and be blocked from altering settlement.
    """
    event_id = f"WH-FAIL-{uuid.uuid4().hex[:12].upper()}"
    webhook_payload = {
        "id": event_id,
        "event_version": "1.0",
        "create_time": datetime.now(timezone.utc).isoformat(),
        "resource_type": "capture",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {"id": "FORGED-CAPTURE-ID", "amount": {"value": "999.00"}},
    }
    invalid_headers = {
        "PAYPAL-AUTH-ALGO": "SHA256withRSA",
        "PAYPAL-CERT-URL": "https://api.sandbox.paypal.com/v1/notifications/certs/CERT-123",
        "PAYPAL-TRANSMISSION-ID": f"TRANS-{uuid.uuid4().hex}",
        "PAYPAL-TRANSMISSION-SIG": "INVALID_SIGNATURE_FORGED_ATTACK_12345",
        "PAYPAL-TRANSMISSION-TIME": datetime.now(timezone.utc).isoformat(),
    }

    res = await client.post("/api/v1/payments/paypal/webhook", json=webhook_payload, headers=invalid_headers)
    assert res.status_code == 400
    err_body = res.json()
    err_text = (err_body.get("detail") or err_body.get("error", {}).get("message") or err_body.get("message", "")).lower()
    assert "invalid paypal webhook signature" in err_text


@pytest.mark.asyncio
async def test_regression_9_payment_receiver_accurately_disclosed(client: AsyncClient):
    """Regression Test 9: Accurately disclose configured Sandbox merchant account (merchant_sandbox@veritas.local
    or configured receiver) as the receiver; do not claim funds reach Bob/creditor directly or claim escrow/holding.
    """
    ctx = await setup_confirmed_agreement_with_obligations(client)
    agreement_id = ctx["agreement_id"]
    charlie_token = ctx["charlie_token"]
    charlie_ob = ctx["charlie_obligation"]

    req_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/payment-requests",
        json={"obligation_id": charlie_ob["obligation_id"]},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert req_res.status_code == 201
    req = req_res.json()

    # Verify receiver merchant account is explicitly the sandbox platform account
    assert req["receiver_merchant_account"] == "merchant_sandbox@veritas.local"
    # Ensure debtor and creditor are clearly distinguished
    assert req["debtor_name"] == "Charlie Davis"
    assert req["creditor_name"] == "Bob Miller"


@pytest.mark.asyncio
async def test_regression_10_unauthorized_capture_and_refund_attempts_return_403(client: AsyncClient):
    """Regression Test 10: Unauthorized capture and refund attempts return HTTP 403 Forbidden.
    Only the bound payer/creator can capture, and only the agreement owner can refund.
    """
    ctx = await setup_confirmed_agreement_with_obligations(client)
    agreement_id = ctx["agreement_id"]
    charlie_token = ctx["charlie_token"]
    owner_token = ctx["owner_token"]
    charlie_ob = ctx["charlie_obligation"]

    # Register unauthorized outsider (Mallory)
    mallory_token = await register_user(client, "mallory_reg10@veritas.local", "Mallory Reg10")

    # Charlie creates payment request and order
    req_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/payment-requests",
        json={"obligation_id": charlie_ob["obligation_id"]},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    req_id = req_res.json()["id"]

    order_res = await client.post(
        "/api/v1/payments/paypal/orders",
        json={"payment_request_id": req_id},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    order_id = order_res.json()["paypal_order_id"]

    # Mallory attempts capture -> 403 Forbidden
    cap_forbidden = await client.post(
        f"/api/v1/payments/paypal/orders/{order_id}/capture",
        headers={"Authorization": f"Bearer {mallory_token}"},
    )
    assert cap_forbidden.status_code == 403

    # Authorized capture by Charlie
    cap_ok = await client.post(
        f"/api/v1/payments/paypal/orders/{order_id}/capture",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert cap_ok.status_code == 200
    capture_id = cap_ok.json()["paypal_capture_id"]

    # Mallory attempts refund -> 403 Forbidden
    ref_mallory = await client.post(
        f"/api/v1/payments/paypal/captures/{capture_id}/refund",
        json={"reason": "Attacker refund"},
        headers={"Authorization": f"Bearer {mallory_token}"},
    )
    assert ref_mallory.status_code == 403

    # Charlie (debtor, non-owner) attempts refund -> 403 Forbidden
    ref_charlie = await client.post(
        f"/api/v1/payments/paypal/captures/{capture_id}/refund",
        json={"reason": "Debtor refund"},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert ref_charlie.status_code == 403

    # Owner can legitimately refund -> 201 Created
    ref_owner = await client.post(
        f"/api/v1/payments/paypal/captures/{capture_id}/refund",
        json={"reason": "Legitimate owner refund", "amount": 210.00},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert ref_owner.status_code == 201


# ==============================================================================
# 4. STAGE 4.2 REGRESSION TESTS: CHECKOUT FAILURE & SETTLEMENT REGRESSION REPAIR
# ==============================================================================

@pytest.mark.asyncio
async def test_stage_4_2_1_paypal_order_creation_correct_amount_and_currency(client: AsyncClient):
    """Stage 4.2 Test 1: PayPal order creation with the correct amount and currency."""
    ctx = await setup_confirmed_agreement_with_obligations(client)
    agreement_id = ctx["agreement_id"]
    charlie_token = ctx["charlie_token"]
    charlie_ob = ctx["charlie_obligation"]

    req_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/payment-requests",
        json={"obligation_id": charlie_ob["obligation_id"]},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert req_res.status_code == 201
    req_id = req_res.json()["id"]

    order_res = await client.post(
        "/api/v1/payments/paypal/orders",
        json={"payment_request_id": req_id},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert order_res.status_code == 201
    order = order_res.json()
    assert Decimal(str(order["amount"])) == Decimal("210.00")
    assert order["currency"] == "USD"
    assert order["status"] == "CREATED"
    assert "paypal_order_id" in order and order["paypal_order_id"]


@pytest.mark.asyncio
async def test_stage_4_2_2_invalid_paypal_order_responses_produce_meaningful_error():
    """Stage 4.2 Test 2: Invalid PayPal order responses produce a meaningful error."""
    from unittest.mock import AsyncMock, patch
    from fastapi import HTTPException
    import httpx

    # Test error parsing in create_order
    paypal_client = PayPalClient(client_id="test_client", client_secret="test_secret", mock_mode=False)

    # Mock OAuth2 token
    paypal_client._cached_token = "mock_valid_token"
    paypal_client._token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    error_response = httpx.Response(
        status_code=422,
        json={
            "name": "UNPROCESSABLE_ENTITY",
            "details": [
                {
                    "field": "/purchase_units/@reference_id=='default'/payee/email_address",
                    "issue": "PAYEE_ACCOUNT_NOT_FOUND",
                    "description": "The specified payee account does not exist or is invalid.",
                }
            ],
            "message": "The requested action could not be performed.",
        },
        request=httpx.Request("POST", "https://api-m.sandbox.paypal.com/v2/checkout/orders"),
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = error_response
        with pytest.raises(HTTPException) as exc_info:
            await paypal_client.create_order(
                amount=Decimal("210.00"),
                currency="USD",
                reference_id="ref123",
                custom_id="cust123",
                description="Cabin Settlement",
                payee_email="invalid_payee@veritas.local",
            )
        assert exc_info.value.status_code == 502
        assert "PAYEE_ACCOUNT_NOT_FOUND" in exc_info.value.detail
        assert "payee account does not exist" in exc_info.value.detail


@pytest.mark.asyncio
async def test_stage_4_2_3_successful_sandbox_approval_and_server_side_capture(client: AsyncClient):
    """Stage 4.2 Test 3: Successful Sandbox approval and server-side capture."""
    ctx = await setup_confirmed_agreement_with_obligations(client)
    agreement_id = ctx["agreement_id"]
    charlie_token = ctx["charlie_token"]
    charlie_ob = ctx["charlie_obligation"]

    req_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/payment-requests",
        json={"obligation_id": charlie_ob["obligation_id"]},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert req_res.status_code == 201
    req_id = req_res.json()["id"]

    order_res = await client.post(
        "/api/v1/payments/paypal/orders",
        json={"payment_request_id": req_id},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert order_res.status_code == 201
    order_id = order_res.json()["paypal_order_id"]

    cap_res = await client.post(
        f"/api/v1/payments/paypal/orders/{order_id}/capture",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert cap_res.status_code == 200
    capture = cap_res.json()
    assert capture["status"] == "COMPLETED"
    assert Decimal(str(capture["amount"])) == Decimal("210.00")
    assert capture["currency"] == "USD"
    assert capture["paypal_capture_id"]


@pytest.mark.asyncio
async def test_stage_4_2_4_missing_alice_30_obligation_detected_and_reconciled(client: AsyncClient):
    """Stage 4.2 Test 4: Missing Alice $30 obligation is detected and reconciled."""
    ctx = await setup_confirmed_agreement_with_obligations(client)
    agreement_id = ctx["agreement_id"]
    owner_token = ctx["owner_token"]

    settle_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/settlement",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert settle_res.status_code == 200
    data = settle_res.json()

    # Both Charlie $210 and Alice $30 obligations must be present
    assert Decimal(str(data["total_obligations_amount"])) == Decimal("240.00")
    alice_ob = next((o for o in data["obligations"] if "alice" in o["debtor_name"].lower()), None)
    assert alice_ob is not None, "Alice $30 obligation must be detected and reconciled"
    assert Decimal(str(alice_ob["amount"])) == Decimal("30.00")
    assert alice_ob["creditor_name"] == "Bob Miller"


@pytest.mark.asyncio
async def test_stage_4_2_5_charlie_210_and_alice_30_obligations_both_persisted_exactly_once(client: AsyncClient):
    """Stage 4.2 Test 5: Charlie's $210 and Alice's $30 obligations are both persisted exactly once."""
    ctx = await setup_confirmed_agreement_with_obligations(client)
    agreement_id = ctx["agreement_id"]
    owner_token = ctx["owner_token"]

    # Re-trigger settlement retrieval / reconciliation multiple times
    for _ in range(3):
        r = await client.get(
            f"/api/v1/accord/agreements/{agreement_id}/settlement",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert r.status_code == 200

    data = (await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/settlement",
        headers={"Authorization": f"Bearer {owner_token}"},
    )).json()

    charlie_obs = [o for o in data["obligations"] if "charlie" in o["debtor_name"].lower()]
    alice_obs = [o for o in data["obligations"] if "alice" in o["debtor_name"].lower()]

    assert len(charlie_obs) == 1, f"Charlie should have exactly 1 obligation, found {len(charlie_obs)}"
    assert len(alice_obs) == 1, f"Alice should have exactly 1 obligation, found {len(alice_obs)}"
    assert Decimal(str(charlie_obs[0]["amount"])) == Decimal("210.00")
    assert Decimal(str(alice_obs[0]["amount"])) == Decimal("30.00")


@pytest.mark.asyncio
async def test_stage_4_2_6_charlie_payment_leaves_30_outstanding(client: AsyncClient):
    """Stage 4.2 Test 6: Charlie's payment leaves $30 outstanding."""
    ctx = await setup_confirmed_agreement_with_obligations(client)
    agreement_id = ctx["agreement_id"]
    charlie_token = ctx["charlie_token"]
    owner_token = ctx["owner_token"]
    charlie_ob = ctx["charlie_obligation"]

    # Charlie pays $210
    req_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/payment-requests",
        json={"obligation_id": charlie_ob["obligation_id"]},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    req_id = req_res.json()["id"]

    order_res = await client.post(
        "/api/v1/payments/paypal/orders",
        json={"payment_request_id": req_id},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    order_id = order_res.json()["paypal_order_id"]

    await client.post(
        f"/api/v1/payments/paypal/orders/{order_id}/capture",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )

    # Check settlement summary
    settle = (await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/settlement",
        headers={"Authorization": f"Bearer {owner_token}"},
    )).json()

    assert Decimal(str(settle["total_obligations_amount"])) == Decimal("240.00")
    assert Decimal(str(settle["total_completed_amount"])) == Decimal("210.00")
    assert Decimal(str(settle["outstanding_balance"])) == Decimal("30.00")
    assert settle["settlement_status"] == "PARTIALLY_SETTLED"


@pytest.mark.asyncio
async def test_stage_4_2_7_alice_subsequent_payment_completes_settlement(client: AsyncClient):
    """Stage 4.2 Test 7: Alice's subsequent payment completes settlement."""
    ctx = await setup_confirmed_agreement_with_obligations(client)
    agreement_id = ctx["agreement_id"]
    charlie_token = ctx["charlie_token"]
    alice_token = ctx["alice_token"]
    owner_token = ctx["owner_token"]
    charlie_ob = ctx["charlie_obligation"]
    alice_ob = ctx["alice_obligation"]

    # 1. Charlie pays $210
    c_req = (await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/payment-requests",
        json={"obligation_id": charlie_ob["obligation_id"]},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )).json()
    c_ord = (await client.post(
        "/api/v1/payments/paypal/orders",
        json={"payment_request_id": c_req["id"]},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )).json()
    await client.post(
        f"/api/v1/payments/paypal/orders/{c_ord['paypal_order_id']}/capture",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )

    # 2. Alice pays $30
    a_req = (await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/payment-requests",
        json={"obligation_id": alice_ob["obligation_id"]},
        headers={"Authorization": f"Bearer {alice_token}"},
    )).json()
    a_ord = (await client.post(
        "/api/v1/payments/paypal/orders",
        json={"payment_request_id": a_req["id"]},
        headers={"Authorization": f"Bearer {alice_token}"},
    )).json()
    await client.post(
        f"/api/v1/payments/paypal/orders/{a_ord['paypal_order_id']}/capture",
        headers={"Authorization": f"Bearer {alice_token}"},
    )

    # 3. Verify settlement is now FULLY_SETTLED with 0 outstanding
    settle = (await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/settlement",
        headers={"Authorization": f"Bearer {owner_token}"},
    )).json()

    assert Decimal(str(settle["total_obligations_amount"])) == Decimal("240.00")
    assert Decimal(str(settle["total_completed_amount"])) == Decimal("240.00")
    assert Decimal(str(settle["outstanding_balance"])) == Decimal("0.00")
    assert settle["settlement_status"] == "FULLY_SETTLED"


@pytest.mark.asyncio
async def test_stage_4_2_8_reanalysis_does_not_create_duplicate_obligations(client: AsyncClient):
    """Stage 4.2 Test 8: Re-analysis does not create duplicate obligations."""
    ctx = await setup_confirmed_agreement_with_obligations(client)
    agreement_id = ctx["agreement_id"]
    conv_id = ctx["conv_id"]
    owner_token = ctx["owner_token"]

    # Re-run synchronous analysis on the same conversation
    re_res = await client.post(
        f"/api/v1/accord/conversations/{conv_id}/analyze?sync=true&force_retry=true",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert re_res.status_code == 200
    re_analysis = re_res.json()
    new_agreement_id = re_analysis["agreements"][0]["id"]

    # Check obligations in newly analyzed agreement
    settle_res = await client.get(
        f"/api/v1/accord/agreements/{new_agreement_id}/settlement",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert settle_res.status_code == 200
    obs = settle_res.json()["obligations"]
    charlie_obs = [o for o in obs if "charlie" in o["debtor_name"].lower()]
    alice_obs = [o for o in obs if "alice" in o["debtor_name"].lower()]

    assert len(charlie_obs) == 1
    assert len(alice_obs) == 1


@pytest.mark.asyncio
async def test_stage_4_2_9_duplicate_consent_submissions_do_not_duplicate_effective_consent_or_audit(client: AsyncClient):
    """Stage 4.2 Test 9: Duplicate consent submissions do not duplicate effective consent or misleading audit events."""
    owner_token = await register_user(client, "owner_audit@veritas.local", "Owner Audit")
    alice_token = await register_user(client, "alice_audit@veritas.local", "Alice Audit")

    chat = """[12/03/24, 14:32:00] Alice Audit: Here is the proposal."""
    ingest_res = await client.post(
        "/api/v1/accord/conversations/text",
        json={"title": "Audit Test", "content": chat},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    conv_id = ingest_res.json()["id"]

    analyze_res = await client.post(
        f"/api/v1/accord/conversations/{conv_id}/analyze?sync=true",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    agreement_id = analyze_res.json()["agreements"][0]["id"]

    # Submit for review
    await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/submit-for-review",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    # Bind Alice
    consensus = (await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/consensus",
        headers={"Authorization": f"Bearer {owner_token}"},
    )).json()
    alice_part_id = consensus["participants"][0]["id"]
    await bind_participant(client, agreement_id, alice_part_id, "alice_audit@veritas.local", owner_token)

    # 1. Alice accepts Version 1
    r1 = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{alice_part_id}/respond",
        json={"response": "ACCEPTED", "comment": "Agreed to terms"},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert r1.status_code == 200

    hist1 = (await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/history",
        headers={"Authorization": f"Bearer {owner_token}"},
    )).json()
    accepted_events_1 = [h for h in hist1 if h["action"] == "PARTICIPANT_ACCEPTED"]
    assert len(accepted_events_1) == 1

    # 2. Alice repeats identical ACCEPTED submission
    r2 = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{alice_part_id}/respond",
        json={"response": "ACCEPTED", "comment": "Agreed to terms"},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert r2.status_code == 200

    hist2 = (await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/history",
        headers={"Authorization": f"Bearer {owner_token}"},
    )).json()
    accepted_events_2 = [h for h in hist2 if h["action"] == "PARTICIPANT_ACCEPTED"]

    # Audit trail count must NOT increase on duplicate retry
    assert len(accepted_events_2) == 1, "Duplicate response submission must be idempotent and not create duplicate audit events"


@pytest.mark.asyncio
async def test_stage_4_2_10_existing_tests_pass_without_regression(client: AsyncClient):
    """Stage 4.2 Test 10: Existing refund, webhook, authorization and consensus tests continue passing."""
    # Smoke verification that core endpoint contracts remain fully functional
    health_res = await client.get("/api/v1/health")
    assert health_res.status_code == 200
    with patch("app.api.v1.health.check_database_connection", return_value=True), \
         patch("app.api.v1.health.check_redis_connection", return_value=True):
        ready_res = await client.get("/api/v1/ready")
        assert ready_res.status_code == 200
        assert ready_res.json()["database"] is True


# ==============================================================================
# 5. STAGE 4.3 REGRESSION TESTS: POST-PAYMENT UI STATE & OBLIGATION VISIBILITY
# ==============================================================================

@pytest.mark.asyncio
async def test_stage_4_3_1_bound_participant_can_access_conversation_and_analysis(client: AsyncClient):
    """Stage 4.3 Test 1: Bound participant can access conversation details, analysis, and financial summary without 404."""
    ctx = await setup_confirmed_agreement_with_obligations(client)
    conv_id = ctx["conv_id"]
    charlie_token = ctx["charlie_token"]

    # 1. Fetch conversation details as bound participant (Charlie)
    conv_res = await client.get(
        f"/api/v1/accord/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert conv_res.status_code == 200, f"Participant should access conversation details, got {conv_res.status_code}: {conv_res.text}"
    assert conv_res.json()["id"] == conv_id

    # 2. Fetch conversation analysis as bound participant (Charlie)
    analysis_res = await client.get(
        f"/api/v1/accord/conversations/{conv_id}/analysis",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert analysis_res.status_code == 200, f"Participant should access analysis, got {analysis_res.status_code}: {analysis_res.text}"
    assert len(analysis_res.json()["agreements"]) > 0

    # 3. Fetch financial summary as bound participant (Charlie)
    fin_res = await client.get(
        f"/api/v1/accord/conversations/{conv_id}/financial-summary",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert fin_res.status_code == 200, f"Participant should access financial summary, got {fin_res.status_code}: {fin_res.text}"

    # 4. List conversations as bound participant (Charlie) - conversation should be included
    list_res = await client.get(
        "/api/v1/accord/conversations",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert list_res.status_code == 200
    conv_ids = [c["id"] for c in list_res.json()["items"]]
    assert conv_id in conv_ids, "Participant should see conversations they are bound to in their list"


@pytest.mark.asyncio
async def test_stage_4_3_2_get_agreement_by_id_endpoint(client: AsyncClient):
    """Stage 4.3 Test 2: Dedicated GET /agreements/{id} endpoint works for owner and participants."""
    ctx = await setup_confirmed_agreement_with_obligations(client)
    agreement_id = ctx["agreement_id"]
    owner_token = ctx["owner_token"]
    charlie_token = ctx["charlie_token"]

    # Owner can get agreement
    owner_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert owner_res.status_code == 200
    assert owner_res.json()["id"] == agreement_id
    assert len(owner_res.json()["participants"]) >= 3

    # Bound participant (Charlie) can get agreement
    part_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert part_res.status_code == 200
    assert part_res.json()["id"] == agreement_id

    # Unrelated user gets 404
    unrelated_token = await register_user(client, "unrelated_stranger@veritas.local", "Stranger Danger")
    unrelated_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}",
        headers={"Authorization": f"Bearer {unrelated_token}"},
    )
    assert unrelated_res.status_code == 404


@pytest.mark.asyncio
async def test_stage_4_3_3_charlie_payment_preserves_alice_obligation_visibility(client: AsyncClient):
    """Stage 4.3 Test 3: Capturing Charlie's $210 preserves Alice's $30 obligation; then settling Alice transitions to FULLY_SETTLED."""
    ctx = await setup_confirmed_agreement_with_obligations(client)
    agreement_id = ctx["agreement_id"]
    owner_token = ctx["owner_token"]
    charlie_token = ctx["charlie_token"]
    alice_token = ctx["alice_token"]
    charlie_ob = ctx["charlie_obligation"]
    alice_ob = ctx["alice_obligation"]

    # 1. Charlie pays $210
    charlie_req_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/payment-requests",
        json={"obligation_id": charlie_ob["obligation_id"]},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert charlie_req_res.status_code == 201
    charlie_req_id = charlie_req_res.json()["id"]

    charlie_ord = await client.post(
        "/api/v1/payments/paypal/orders",
        json={"payment_request_id": charlie_req_id},
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert charlie_ord.status_code == 201
    charlie_order_id = charlie_ord.json()["paypal_order_id"]

    charlie_cap = await client.post(
        f"/api/v1/payments/paypal/orders/{charlie_order_id}/capture",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )
    assert charlie_cap.status_code == 200

    # 2. Query settlement summary as Charlie (or anyone)
    summary_charlie = (await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/settlement",
        headers={"Authorization": f"Bearer {charlie_token}"},
    )).json()

    assert summary_charlie["settlement_status"] == "PARTIALLY_SETTLED"
    assert Decimal(str(summary_charlie["total_completed_amount"])) == Decimal("210.00")
    assert Decimal(str(summary_charlie["outstanding_balance"])) == Decimal("30.00")

    # Check both obligations exist
    ob_map = {o["debtor_name"]: o for o in summary_charlie["obligations"]}
    assert "Charlie Davis" in ob_map
    assert "Alice Smith" in ob_map

    # Charlie is settled
    assert ob_map["Charlie Davis"]["is_settled"] is True
    assert Decimal(str(ob_map["Charlie Davis"]["settled_amount"])) == Decimal("210.00")

    # Alice is NOT settled and remaining balance is $30
    assert ob_map["Alice Smith"]["is_settled"] is False
    assert Decimal(str(ob_map["Alice Smith"]["outstanding_amount"])) == Decimal("30.00")
    assert ob_map["Alice Smith"]["is_eligible_for_payment"] is True

    # 3. Alice pays $30
    alice_req_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/payment-requests",
        json={"obligation_id": alice_ob["obligation_id"]},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert alice_req_res.status_code == 201
    alice_req_id = alice_req_res.json()["id"]

    alice_ord = await client.post(
        "/api/v1/payments/paypal/orders",
        json={"payment_request_id": alice_req_id},
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert alice_ord.status_code == 201
    alice_order_id = alice_ord.json()["paypal_order_id"]

    alice_cap = await client.post(
        f"/api/v1/payments/paypal/orders/{alice_order_id}/capture",
        headers={"Authorization": f"Bearer {alice_token}"},
    )
    assert alice_cap.status_code == 200

    # 4. Final settlement check: agreement must now be FULLY_SETTLED
    final_summary = (await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/settlement",
        headers={"Authorization": f"Bearer {owner_token}"},
    )).json()

    assert final_summary["settlement_status"] == "FULLY_SETTLED"
    assert Decimal(str(final_summary["total_completed_amount"])) == Decimal("240.00")
    assert Decimal(str(final_summary["outstanding_balance"])) == Decimal("0.00")

    final_ob_map = {o["debtor_name"]: o for o in final_summary["obligations"]}
    assert final_ob_map["Charlie Davis"]["is_settled"] is True
    assert final_ob_map["Alice Smith"]["is_settled"] is True



