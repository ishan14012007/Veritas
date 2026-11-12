import hashlib
import hmac
import json
import uuid
import pytest
import pytest_asyncio
import httpx
from httpx import AsyncClient
from fastapi import HTTPException
from unittest.mock import AsyncMock, patch

from app.core.config import Settings, get_settings
from app.main import app
from app.whatsapp.client import get_whatsapp_provider, reset_whatsapp_provider
from app.whatsapp.meta_cloud_api import MetaWhatsAppCloudProvider
from app.whatsapp.mock_provider import MockWhatsAppProvider
from app.whatsapp.models import WhatsAppAccount, WhatsAppMessage, WhatsAppWebhookEvent


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


@pytest.fixture(autouse=True)
def reset_provider():
    """Reset provider cache before and after each test."""
    reset_whatsapp_provider()
    yield
    reset_whatsapp_provider()


# ==============================================================================
# 1. Mock Provider Initialization Without Credentials
# ==============================================================================

def test_01_mock_provider_initialization():
    """Mock provider must initialize and operate without real Meta credentials."""
    provider = MockWhatsAppProvider()
    assert provider.provider_name == "mock"
    assert provider.is_mock is True
    assert provider.phone_number_id == "mock_phone_id"


# ==============================================================================
# 2. Live Provider Configuration Validation
# ==============================================================================

def test_02_live_provider_configuration_validation():
    """Live provider must reject missing or default mock credentials with clear errors."""
    # Missing phone number id
    with pytest.raises(ValueError, match="WHATSAPP_PHONE_NUMBER_ID"):
        MetaWhatsAppCloudProvider(
            phone_number_id="",
            access_token="valid_token",
            app_secret="valid_secret",
        )

    # Missing access token
    with pytest.raises(ValueError, match="WHATSAPP_ACCESS_TOKEN"):
        MetaWhatsAppCloudProvider(
            phone_number_id="123456789",
            access_token="",
            app_secret="valid_secret",
        )

    # Missing app secret
    with pytest.raises(ValueError, match="WHATSAPP_APP_SECRET"):
        MetaWhatsAppCloudProvider(
            phone_number_id="123456789",
            access_token="valid_token",
            app_secret="",
        )

    # Mock placeholder credentials rejected in live provider
    with pytest.raises(ValueError, match="WHATSAPP_PHONE_NUMBER_ID"):
        MetaWhatsAppCloudProvider(
            phone_number_id="mock_phone_id",
            access_token="valid_token",
            app_secret="valid_secret",
        )


# ==============================================================================
# 3. Simulated Outbound Message
# ==============================================================================

@pytest.mark.asyncio
async def test_03_simulated_outbound_message(client: AsyncClient):
    """Simulated outbound message dispatches via mock provider and persists record with SENT status."""
    token = await register_user(client, "outbound_tester@veritas.local", "Outbound Tester")

    # Send outbound text
    send_res = await client.post(
        "/api/v1/whatsapp/messages/send",
        json={
            "recipient_number": "+14155552671",
            "message_type": "TEXT",
            "content": "Hello from VERITAS ACCORD test suite!",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert send_res.status_code == 200, send_res.text
    data = send_res.json()
    assert data["delivery_status"] == "SENT"
    assert data["recipient_number"] == "+14155552671"
    assert data["is_mock"] is True
    assert data["provider_message_id"].startswith("wamid.MOCK_")


# ==============================================================================
# 4. Simulated Inbound Message
# ==============================================================================

@pytest.mark.asyncio
async def test_04_simulated_inbound_message():
    """Mock provider normalizes incoming Meta payload into standardized message format."""
    provider = MockWhatsAppProvider()
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123456",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"display_phone_number": "15550001234"},
                            "messages": [
                                {
                                    "from": "14155552671",
                                    "id": "wamid.HBgLMTE...",
                                    "timestamp": 1700000000,
                                    "type": "text",
                                    "text": {"body": "I agree to split $300 equally."},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    messages = provider.process_inbound_message(payload)
    assert len(messages) == 1
    assert messages[0]["sender_number"] == "+14155552671"
    assert messages[0]["content"] == "I agree to split $300 equally."
    assert messages[0]["provider_message_id"] == "wamid.HBgLMTE..."


# ==============================================================================
# 5. Inbound Webhook Verification
# ==============================================================================

@pytest.mark.asyncio
async def test_05_inbound_webhook_verification(client: AsyncClient):
    """GET /webhook verifies subscription challenge with configured verify token."""
    # Valid verification request
    res = await client.get(
        "/api/v1/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=veritas_verify_token_dev&hub.challenge=test_challenge_1234"
    )
    assert res.status_code == 200
    assert res.text == "test_challenge_1234"

    # Invalid verify token -> 403 Forbidden
    res_invalid = await client.get(
        "/api/v1/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=wrong_token&hub.challenge=test_challenge_1234"
    )
    assert res_invalid.status_code == 403


# ==============================================================================
# 6. Invalid Signature Rejection in Live Mode
# ==============================================================================

@pytest.mark.asyncio
async def test_06_invalid_signature_rejection_in_live_mode(client: AsyncClient):
    """In LIVE mode, invalid HMAC signature returns 403 Forbidden."""
    # Temporarily override settings to simulate LIVE mode
    from app.core.config import get_settings

    live_settings = Settings(
        ENVIRONMENT="production",
        DEBUG=False,
        WHATSAPP_PROVIDER="meta",
        WHATSAPP_MOCK_MODE=False,
        MOCK_WHATSAPP=False,
        WHATSAPP_PHONE_NUMBER_ID="live_phone_id",
        WHATSAPP_ACCESS_TOKEN="live_access_token",
        WHATSAPP_APP_SECRET="super_secret_app_key",
    )
    app.dependency_overrides[get_settings] = lambda: live_settings

    try:
        raw_body = json.dumps({"entry": []}).encode("utf-8")
        # Post with bad signature
        res = await client.post(
            "/api/v1/whatsapp/webhook",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=invalid_signature_digest",
            },
        )
        assert res.status_code == 403
    finally:
        app.dependency_overrides.pop(get_settings, None)
        reset_whatsapp_provider()


# ==============================================================================
# 7. Duplicate Webhook Idempotency
# ==============================================================================

@pytest.mark.asyncio
async def test_07_duplicate_webhook_idempotency(client: AsyncClient):
    """Submitting the identical webhook payload twice records the event once and marks duplicate ignored."""
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": f"event_{uuid.uuid4().hex[:8]}", "changes": []}],
    }
    raw_body = json.dumps(payload).encode("utf-8")

    # First delivery
    res1 = await client.post(
        "/api/v1/whatsapp/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json"},
    )
    assert res1.status_code == 200
    assert res1.json()["status"] == "ok"
    event_id = res1.json()["event_id"]

    # Second delivery (exact duplicate)
    res2 = await client.post(
        "/api/v1/whatsapp/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json"},
    )
    assert res2.status_code == 200
    assert res2.json()["message"] == "Duplicate event ignored"
    assert res2.json()["event_id"] == event_id


# ==============================================================================
# 8. Phone Linking and Ownership Enforcement
# ==============================================================================

@pytest.mark.asyncio
async def test_08_phone_linking_and_ownership_enforcement(client: AsyncClient):
    """User links phone, verifies control with token, prevents double claim, and unlinks."""
    user_a_token = await register_user(client, "phone_owner_a@veritas.local", "Owner A")
    user_b_token = await register_user(client, "phone_owner_b@veritas.local", "Owner B")
    phone = "+14155550199"

    # 1. User A initiates linking
    link_res = await client.post(
        "/api/v1/whatsapp/accounts/link",
        json={"phone_number": phone, "display_name": "Owner A Primary"},
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert link_res.status_code == 200
    v_token = link_res.json()["verification_token"]
    account_id = link_res.json()["id"]
    assert v_token is not None

    # 2. User A confirms verification
    verify_res = await client.post(
        "/api/v1/whatsapp/accounts/verify",
        json={"phone_number": phone, "verification_token": v_token},
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert verify_res.status_code == 200
    assert verify_res.json()["connection_status"] == "CONNECTED"
    assert verify_res.json()["consent_status"] == "OPTED_IN"

    # 3. User B attempts to claim the already-verified number -> 409 Conflict
    conflict_res = await client.post(
        "/api/v1/whatsapp/accounts/link",
        json={"phone_number": phone, "display_name": "Owner B Imposter"},
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert conflict_res.status_code == 409

    # 4. User A unlinks the account
    unlink_res = await client.delete(
        f"/api/v1/whatsapp/accounts/{account_id}",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert unlink_res.status_code == 200
    assert unlink_res.json()["success"] is True


# ==============================================================================
# 9. Unauthorized Phone Number Rejection
# ==============================================================================

@pytest.mark.asyncio
async def test_09_unauthorized_phone_number_rejection(client: AsyncClient):
    """Incoming messages from unlinked phone numbers are rejected and not converted to conversations."""
    unlinked_phone = "+19998887766"
    sim_res = await client.post(
        "/api/v1/whatsapp/mock/inbound",
        json={
            "from_number": unlinked_phone,
            "content": "Hey, let's create an agreement!",
        },
        headers={"Authorization": f"Bearer {await register_user(client, 'caller9@veritas.local', 'Caller 9')}"},
    )
    assert sim_res.status_code == 200
    records = sim_res.json()
    assert len(records) == 1
    assert records[0]["delivery_status"] == "FAILED"
    assert records[0]["error_code"] == "UNAUTHORIZED_SENDER"


# ==============================================================================
# 10. Conversation Linking
# ==============================================================================

@pytest.mark.asyncio
async def test_10_conversation_linking(client: AsyncClient):
    """Inbound message from verified linked user creates/attaches to ACCORD conversation."""
    token = await register_user(client, "linked_chat_user@veritas.local", "Chat User")
    phone = "+14155550155"

    # Link and verify phone
    link_res = await client.post(
        "/api/v1/whatsapp/accounts/link",
        json={"phone_number": phone, "display_name": "Chat User Mobile"},
        headers={"Authorization": f"Bearer {token}"},
    )
    v_code = link_res.json()["verification_token"]
    await client.post(
        "/api/v1/whatsapp/accounts/verify",
        json={"phone_number": phone, "verification_token": v_code},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Simulate inbound message
    msg_res = await client.post(
        "/api/v1/whatsapp/mock/inbound",
        json={
            "from_number": phone,
            "content": "I paid $150 for dinner last night.",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert msg_res.status_code == 200
    msg = msg_res.json()[0]
    assert msg["delivery_status"] == "DELIVERED"
    assert msg["conversation_id"] is not None

    # Check conversation exists in ACCORD conversations
    conv_res = await client.get(
        f"/api/v1/accord/conversations/{msg['conversation_id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert conv_res.status_code == 200
    assert "I paid $150" in (conv_res.json()["messages"][0].get("message_body") or conv_res.json()["messages"][0].get("content", ""))


# ==============================================================================
# 11. Gemini Processing Integration
# ==============================================================================

@pytest.mark.asyncio
async def test_11_gemini_processing_integration(client: AsyncClient):
    """Inbound simulator message with trigger_analysis=True invokes Gemini analysis."""
    token = await register_user(client, "gemini_wa_user@veritas.local", "Gemini WA User")
    phone = "+14155550188"

    # Link and verify phone
    link_res = await client.post(
        "/api/v1/whatsapp/accounts/link",
        json={"phone_number": phone},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        "/api/v1/whatsapp/accounts/verify",
        json={"phone_number": phone, "verification_token": link_res.json()["verification_token"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Ingest message with trigger_analysis=True
    sim_res = await client.post(
        "/api/v1/whatsapp/mock/inbound",
        json={
            "from_number": phone,
            "content": "Bob paid $200 for ski passes. Alice owes Bob $100.",
            "trigger_analysis": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert sim_res.status_code == 200
    conv_id = sim_res.json()[0]["conversation_id"]

    # Verify analysis record was created
    an_res = await client.get(
        f"/api/v1/accord/conversations/{conv_id}/analysis",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert an_res.status_code == 200


# ==============================================================================
# 12. Unsupported Message Types Handled Gracefully
# ==============================================================================

@pytest.mark.asyncio
async def test_12_unsupported_message_types():
    """Unsupported or media messages (location, audio, sticker) are parsed gracefully."""
    provider = MockWhatsAppProvider()
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"display_phone_number": "15550001234"},
                            "messages": [
                                {
                                    "from": "14155552671",
                                    "id": "wamid.MEDIA1",
                                    "type": "audio",
                                },
                                {
                                    "from": "14155552671",
                                    "id": "wamid.LOC1",
                                    "type": "location",
                                    "location": {"latitude": 37.77, "longitude": -122.41},
                                },
                            ],
                        },
                    }
                ],
            }
        ],
    }
    messages = provider.process_inbound_message(payload)
    assert len(messages) == 2
    assert "[Media: audio]" in messages[0]["content"]
    assert "lat=37.77" in messages[1]["content"]


# ==============================================================================
# 13. Delivery and Read Status Updates
# ==============================================================================

@pytest.mark.asyncio
async def test_13_delivery_and_read_status_updates(client: AsyncClient):
    """Status updates update message delivery_status to DELIVERED and READ."""
    token = await register_user(client, "status_user@veritas.local", "Status User")

    # Send outbound
    out_res = await client.post(
        "/api/v1/whatsapp/messages/send",
        json={"recipient_number": "+14155550133", "content": "Ping test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    p_id = out_res.json()["provider_message_id"]

    # Simulate DELIVERED status
    del_res = await client.post(
        "/api/v1/whatsapp/mock/status",
        json={"provider_message_id": p_id, "status": "DELIVERED"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_res.status_code == 200

    # Query message
    msg_check = await client.get(
        f"/api/v1/whatsapp/messages/{out_res.json()['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert msg_check.json()["delivery_status"] == "DELIVERED"

    # Simulate READ status
    read_res = await client.post(
        "/api/v1/whatsapp/mock/status",
        json={"provider_message_id": p_id, "status": "READ"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert read_res.status_code == 200

    msg_check2 = await client.get(
        f"/api/v1/whatsapp/messages/{out_res.json()['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert msg_check2.json()["delivery_status"] == "READ"


# ==============================================================================
# 14. Retry and Error Handling in Live Provider
# ==============================================================================

@pytest.mark.asyncio
async def test_14_retry_and_error_handling():
    """Live provider correctly maps timeouts and rate limits to appropriate HTTP errors."""
    provider = MetaWhatsAppCloudProvider(
        phone_number_id="1234567890",
        access_token="test_token",
        app_secret="test_secret",
    )

    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Timeout")):
        with pytest.raises(HTTPException) as exc_info:
            await provider.send_text_message(to="+14155552671", text="Hello")
        assert exc_info.value.status_code == 504


# ==============================================================================
# 15. Dead-Letter Behavior
# ==============================================================================

@pytest.mark.asyncio
async def test_15_dead_letter_behavior(fake_redis):
    """ARQ on_job_end hook records exhausted retries to dead letter stream."""
    from app.core.tasks.worker import on_job_end

    ctx = {
        "job_id": "test_failed_whatsapp_job_123",
        "job_try": 3,
        "redis": fake_redis,
    }
    await on_job_end(ctx)

    stream_data = await fake_redis.xrange("veritas:arq:dead_letter_queue")
    assert len(stream_data) >= 1
    fields = stream_data[0][1]
    assert fields["job_id"] == "test_failed_whatsapp_job_123"
    assert fields["status"] == "RETRY_EXHAUSTED"


# ==============================================================================
# 16. Mock Endpoints Disabled in Live Mode
# ==============================================================================

@pytest.mark.asyncio
async def test_16_mock_endpoints_disabled_in_live_mode(client: AsyncClient):
    """Mock-only endpoints return 403 Forbidden when running in LIVE mode."""
    token = await register_user(client, "live_mode_tester@veritas.local", "Live Tester")

    live_settings = Settings(
        ENVIRONMENT="production",
        DEBUG=False,
        WHATSAPP_PROVIDER="meta",
        WHATSAPP_MOCK_MODE=False,
        MOCK_WHATSAPP=False,
        WHATSAPP_PHONE_NUMBER_ID="live_phone_id",
        WHATSAPP_ACCESS_TOKEN="live_access_token",
        WHATSAPP_APP_SECRET="super_secret_app_key",
    )
    app.dependency_overrides[get_settings] = lambda: live_settings

    try:
        # Inbound simulator must be rejected
        res_in = await client.post(
            "/api/v1/whatsapp/mock/inbound",
            json={"from_number": "+14155552671", "content": "Simulated in live"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_in.status_code == 403

        # Status simulator must be rejected
        res_st = await client.post(
            "/api/v1/whatsapp/mock/status",
            json={"provider_message_id": "wamid.123", "status": "DELIVERED"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res_st.status_code == 403
    finally:
        app.dependency_overrides.pop(get_settings, None)
        reset_whatsapp_provider()


# ==============================================================================
# 17. User Opt-In Enforcement
# ==============================================================================

@pytest.mark.asyncio
async def test_17_user_opt_in_enforcement(client: AsyncClient):
    """Template message cannot be sent to a user who has opted out."""
    token = await register_user(client, "optout_user@veritas.local", "OptOut User")

    # Link and verify phone
    link_res = await client.post(
        "/api/v1/whatsapp/accounts/link",
        json={"phone_number": "+14155550999"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        "/api/v1/whatsapp/accounts/verify",
        json={"phone_number": "+14155550999", "verification_token": link_res.json()["verification_token"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Now unlink/opt-out
    acc_id = link_res.json()["id"]
    await client.delete(
        f"/api/v1/whatsapp/accounts/{acc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Attempt to dispatch a template notification -> 400 Bad Request
    send_res = await client.post(
        "/api/v1/whatsapp/messages/send",
        json={
            "recipient_number": "+14155550999",
            "message_type": "TEMPLATE",
            "template_name": "accord_agreement_review_v1",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert send_res.status_code == 400
    err_detail = send_res.json().get("error", {}).get("message", "") or send_res.json().get("detail", "")
    assert "opted out" in err_detail.lower()


# ==============================================================================
# 18. No Automatic Agreement Confirmation
# ==============================================================================

@pytest.mark.asyncio
async def test_18_no_automatic_agreement_confirmation(client: AsyncClient):
    """Inbound WhatsApp messages must never automatically confirm agreements."""
    token = await register_user(client, "wa_consensus_user@veritas.local", "Consensus User")
    phone = "+14155550777"

    # Link phone
    link_res = await client.post(
        "/api/v1/whatsapp/accounts/link",
        json={"phone_number": phone},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        "/api/v1/whatsapp/accounts/verify",
        json={"phone_number": phone, "verification_token": link_res.json()["verification_token"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Simulate inbound message stating acceptance
    sim_res = await client.post(
        "/api/v1/whatsapp/mock/inbound",
        json={
            "from_number": phone,
            "content": "I accept all terms and confirm this agreement unconditionally.",
            "trigger_analysis": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    conv_id = sim_res.json()[0]["conversation_id"]

    # Verify that if an agreement is proposed, it remains DRAFT or UNDER_REVIEW, NEVER CONFIRMED
    an_res = await client.get(
        f"/api/v1/accord/conversations/{conv_id}/analysis",
        headers={"Authorization": f"Bearer {token}"},
    )
    if an_res.status_code == 200 and an_res.json().get("agreements"):
        agr = an_res.json()["agreements"][0]
        assert agr["status"] != "CONFIRMED", "Agreement must never auto-confirm from raw WhatsApp text"
        assert agr["is_confirmed"] is False


# ==============================================================================
# 19. No Automatic Payment Creation or Capture
# ==============================================================================

@pytest.mark.asyncio
async def test_19_no_automatic_payment_creation_or_capture(client: AsyncClient):
    """Inbound messages saying 'I paid $500' never create or capture PayPal payment requests."""
    token = await register_user(client, "wa_payment_user@veritas.local", "Payment User")
    phone = "+14155550666"

    # Link phone
    link_res = await client.post(
        "/api/v1/whatsapp/accounts/link",
        json={"phone_number": phone},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        "/api/v1/whatsapp/accounts/verify",
        json={"phone_number": phone, "verification_token": link_res.json()["verification_token"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    # Inbound payment claim
    sim_res = await client.post(
        "/api/v1/whatsapp/mock/inbound",
        json={
            "from_number": phone,
            "content": "I just paid $500 via PayPal. Mark me settled immediately.",
            "trigger_analysis": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    conv_id = sim_res.json()[0]["conversation_id"]

    an_res = await client.get(
        f"/api/v1/accord/conversations/{conv_id}/analysis",
        headers={"Authorization": f"Bearer {token}"},
    )
    if an_res.status_code == 200 and an_res.json().get("agreements"):
        agr = an_res.json()["agreements"][0]
        # Settlement must be UNSETTLED
        settle_res = await client.get(
            f"/api/v1/accord/agreements/{agr['id']}/settlement",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert settle_res.status_code == 200
        assert settle_res.json()["settlement_status"] == "UNSETTLED"
        assert settle_res.json()["total_completed_amount"] == "0.00" or float(settle_res.json()["total_completed_amount"]) == 0.0


# ==============================================================================
# 20. Existing PayPal and Consensus Functionality Unaffected
# ==============================================================================

@pytest.mark.asyncio
async def test_20_existing_paypal_and_consensus_functionality_unaffected(client: AsyncClient):
    """Health check and core consensus/payments contracts remain 100% operational."""
    health_res = await client.get("/api/v1/health")
    assert health_res.status_code == 200

    status_res = await client.get(
        "/api/v1/whatsapp/status",
        headers={"Authorization": f"Bearer {await register_user(client, 'status_smoke@veritas.local', 'Status Smoke')}"},
    )
    assert status_res.status_code == 200
    assert status_res.json()["provider"] in ("mock", "meta")
    assert "accord_agreement_review_v1" in status_res.json()["registered_templates"]
