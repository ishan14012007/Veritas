import pytest
from decimal import Decimal
from httpx import AsyncClient

from app.ai.adapter import MockAIServiceAdapter, set_ai_adapter
from app.payments.currency_service import get_currency_service, PAYPAL_SUPPORTED_CURRENCIES
from app.payments.paypal_client import PayPalClient, set_paypal_client


@pytest.fixture(autouse=True)
def setup_mock_services():
    adapter = MockAIServiceAdapter()
    set_ai_adapter(adapter)
    mock_paypal = PayPalClient(mock_mode=True)
    set_paypal_client(mock_paypal)
    yield
    set_ai_adapter(None)
    set_paypal_client(None)


async def register_user(client: AsyncClient, email: str, full_name: str) -> str:
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
    res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/participants/{participant_id}/bind",
        json={"email": email},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert res.status_code == 200, res.text
    return res.json()


@pytest.mark.asyncio
async def test_currency_service_conversion():
    """Verify CurrencyService converts INR to USD with live exchange rate and retains USD unchanged."""
    service = get_currency_service()
    
    assert not service.is_paypal_supported("INR")
    assert service.is_paypal_supported("USD")
    assert service.is_paypal_supported("EUR")
    assert service.is_paypal_supported("GBP")

    res = await service.convert_for_paypal(Decimal("500.00"), "INR")
    assert res.is_converted is True
    assert res.original_amount == Decimal("500.00")
    assert res.original_currency == "INR"
    assert res.paypal_currency == "USD"
    assert res.paypal_amount > Decimal("0.00")
    assert res.exchange_rate > Decimal("50.00")

    usd_res = await service.convert_for_paypal(Decimal("100.00"), "USD")
    assert usd_res.is_converted is False
    assert usd_res.paypal_amount == Decimal("100.00")
    assert usd_res.paypal_currency == "USD"
    assert usd_res.exchange_rate == Decimal("1.00")


@pytest.mark.asyncio
async def test_inr_payment_request_order_creation_and_capture(client: AsyncClient):
    """Verify that an INR obligation is converted to USD for PayPal checkout
    while preserving the original INR obligation and settlement in VERITAS records.
    """
    owner_token = await register_user(client, "tester@veritas.local", "Veritas QA Tester")
    rahul_token = await register_user(client, "rahul@veritas.local", "Rahul")
    aman_token = await register_user(client, "aman@veritas.local", "Aman")
    priya_token = await register_user(client, "priya@veritas.local", "Priya")
    karan_token = await register_user(client, "karan@veritas.local", "Karan")

    chat = """[10/11/24, 10:00:00] Rahul: Let's settle our Goa trip expenses!
[10/11/24, 10:01:00] Aman: I paid ₹12,000 for the villa and ₹2,400 for petrol.
[10/11/24, 10:02:00] Priya: I paid ₹6,000 for the car and ₹1,600 for lunch.
[10/11/24, 10:03:00] Rahul: I paid ₹3,200 for dinner.
[10/11/24, 10:04:00] Karan: Groceries were ₹1,850. Also I borrowed ₹500 from Rahul personally.
[10/11/24, 10:05:00] Rahul: Agreed, keep the ₹500 personal loan separate. Let's split trip expenses equally 25% each."""

    ingest_res = await client.post(
        "/api/v1/accord/conversations/text",
        json={"title": "Goa Trip Settlement", "content": chat},
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
    agreement_id = agreement["id"]

    # Bind and record ACCEPTED consent for all 4 participants to confirm agreement
    tokens_map = {
        "rahul": rahul_token,
        "aman": aman_token,
        "priya": priya_token,
        "karan": karan_token,
    }
    for p in agreement["participants"]:
        p_name = p["name"].lower()
        for k, tok in tokens_map.items():
            if k in p_name:
                await bind_participant(client, agreement_id, p["id"], f"{k}@veritas.local", owner_token)
                c_res = await client.post(
                    f"/api/v1/accord/agreements/{agreement_id}/participants/{p['id']}/respond",
                    json={"response": "ACCEPTED", "comment": f"{k.capitalize()} accepts settlement terms"},
                    headers={"Authorization": f"Bearer {tok}"},
                )
                assert c_res.status_code == 200

    # Retrieve settlement overview
    settle_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/settlement",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert settle_res.status_code == 200
    settle_data = settle_res.json()
    assert settle_data["consensus_achieved"] is True
    assert settle_data["agreement_status"] == "CONFIRMED"
    assert settle_data["currency"] == "INR"

    # Find the personal borrowing obligation: Karan owes Rahul ₹500.00
    personal_ob = next(
        (o for o in settle_data["obligations"] if "karan" in (o.get("debtor_name") or "").lower() and Decimal(str(o["amount"])) == Decimal("500.00")),
        None,
    )
    assert personal_ob is not None
    assert personal_ob["currency"] == "INR"
    assert Decimal(str(personal_ob["amount"])) == Decimal("500.00")

    # 1. Create Payment Request for Karan's ₹500 obligation
    req_res = await client.post(
        f"/api/v1/accord/agreements/{agreement_id}/payment-requests",
        json={"obligation_id": personal_ob["obligation_id"]},
        headers={"Authorization": f"Bearer {karan_token}"},
    )
    assert req_res.status_code == 201
    req_data = req_res.json()
    assert req_data["currency"] == "INR"
    assert Decimal(str(req_data["amount"])) == Decimal("500.00")
    req_id = req_data["id"]

    # 2. Create PayPal Order: Must convert INR to USD for PayPal
    order_res = await client.post(
        "/api/v1/payments/paypal/orders",
        json={"payment_request_id": req_id},
        headers={"Authorization": f"Bearer {karan_token}"},
    )
    assert order_res.status_code == 201
    order_data = order_res.json()

    # The PayPal order must be in USD with positive converted value
    assert order_data["currency"] == "USD"
    assert Decimal(str(order_data["amount"])) > Decimal("0.00")
    assert order_data["is_converted"] is True
    assert Decimal(str(order_data["original_amount"])) == Decimal("500.00")
    assert order_data["original_currency"] == "INR"
    order_id = order_data["paypal_order_id"]

    # 3. Capture PayPal Order
    cap_res = await client.post(
        f"/api/v1/payments/paypal/orders/{order_id}/capture",
        headers={"Authorization": f"Bearer {karan_token}"},
    )
    assert cap_res.status_code == 200
    cap_data = cap_res.json()
    assert cap_data["status"] == "COMPLETED"
    assert cap_data["currency"] == "USD"

    # 4. Verify that in VERITAS internal settlement ledger, obligation is FULFILLED in INR
    final_settle_res = await client.get(
        f"/api/v1/accord/agreements/{agreement_id}/settlement",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert final_settle_res.status_code == 200
    final_summary = final_settle_res.json()
    settled_ob = next(o for o in final_summary["obligations"] if o["obligation_id"] == personal_ob["obligation_id"])
    assert settled_ob["is_settled"] is True
    assert settled_ob["obligation_status"] == "FULFILLED"
    assert Decimal(str(settled_ob["settled_amount"])) == Decimal("500.00")
    assert settled_ob["currency"] == "INR"
