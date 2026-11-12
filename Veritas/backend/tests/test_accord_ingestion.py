import io
import uuid
import pytest
from httpx import AsyncClient


async def get_auth_token(client: AsyncClient, email: str = "accord.tester@example.com") -> str:
    """Helper to register and return access token."""
    reg_payload = {
        "email": email,
        "password": "Password123!",
        "full_name": "ACCORD Tester",
    }
    reg_res = await client.post("/api/v1/auth/register", json=reg_payload)
    if reg_res.status_code == 201:
        return reg_res.json()["tokens"]["access_token"]

    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    return login_res.json()["tokens"]["access_token"]


@pytest.mark.asyncio
async def test_pasted_text_ingestion_success(client: AsyncClient):
    """Verify successful pasted conversation text submission."""
    token = await get_auth_token(client, "user1@example.com")
    payload = {
        "title": "Road Trip to Lake Tahoe",
        "content": """[11/04/26, 14:20] Alice: Total lodging was $600.
[11/04/26, 14:22] Bob: I will cover $200.
[11/04/26, 14:23] Charlie: I will cover $200 too.""",
    }
    response = await client.post(
        "/api/v1/accord/conversations/text",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Road Trip to Lake Tahoe"
    assert data["source_type"] == "PASTED_TEXT"
    assert data["total_messages"] == 3
    assert data["total_participants"] == 3
    assert len(data["participants"]) == 3
    assert len(data["messages"]) == 3

    # Verify participant deduplication & message ordering
    participant_names = {p["display_name"] for p in data["participants"]}
    assert participant_names == {"Alice", "Bob", "Charlie"}

    for idx, msg in enumerate(data["messages"]):
        assert msg["order_index"] == idx


@pytest.mark.asyncio
async def test_pasted_text_validation_errors(client: AsyncClient):
    """Verify rejection of empty, whitespace, or oversized pasted text."""
    token = await get_auth_token(client, "user_val@example.com")

    # 1. Empty content
    res_empty = await client.post(
        "/api/v1/accord/conversations/text",
        json={"content": "", "title": "Empty"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_empty.status_code == 422

    # 2. Whitespace-only content
    res_ws = await client.post(
        "/api/v1/accord/conversations/text",
        json={"content": "    \n\t   ", "title": "Whitespace"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_ws.status_code == 422

    # 3. Oversized content (> 2 MB)
    oversized = "Alice: Hello\n" * 200000
    res_oversized = await client.post(
        "/api/v1/accord/conversations/text",
        json={"content": oversized, "title": "Oversized"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_oversized.status_code == 413


@pytest.mark.asyncio
async def test_whatsapp_file_upload_success(client: AsyncClient):
    """Verify upload and parsing of WhatsApp .txt file."""
    token = await get_auth_token(client, "user_upload@example.com")

    chat_content = """[10/05/2026, 09:00:00] Messages and calls are end-to-end encrypted.
[10/05/2026, 09:05:00] Alice: The Airbnb bill is $900.
[10/05/2026, 09:06:00] Bob: <Media omitted>
[10/05/2026, 09:07:00] Bob: That works.
[10/05/2026, 09:08:00] Charlie: Confirmed."""

    files = {
        "file": ("chat_export.txt", io.BytesIO(chat_content.encode("utf-8")), "text/plain"),
    }
    data = {"title": "Cabin Retreat"}

    response = await client.post(
        "/api/v1/accord/conversations/upload",
        files=files,
        data=data,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    resp_data = response.json()
    assert resp_data["title"] == "Cabin Retreat"
    assert resp_data["source_type"] == "WHATSAPP_EXPORT"
    assert resp_data["original_filename"] == "chat_export.txt"
    assert resp_data["total_messages"] == 5
    assert resp_data["total_participants"] == 3  # Alice, Bob, Charlie (system message is not a participant)


@pytest.mark.asyncio
async def test_whatsapp_file_upload_validation(client: AsyncClient):
    """Verify rejection of invalid file extensions, binary files, and empty files."""
    token = await get_auth_token(client, "user_fileval@example.com")

    # 1. Non-txt extension
    pdf_file = {"file": ("malicious.pdf", io.BytesIO(b"%PDF-1.4 header"), "application/pdf")}
    res_ext = await client.post(
        "/api/v1/accord/conversations/upload",
        files=pdf_file,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_ext.status_code == 400
    assert "Only plain-text WhatsApp export files (.txt) are accepted" in res_ext.json()["error"]["message"]

    # 2. Binary content disguised as .txt
    binary_file = {"file": ("fake.txt", io.BytesIO(b"\x00\x01\x02\x03\xff"), "text/plain")}
    res_bin = await client.post(
        "/api/v1/accord/conversations/upload",
        files=binary_file,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_bin.status_code == 400
    assert "Binary files are not permitted" in res_bin.json()["error"]["message"]

    # 3. Empty .txt file
    empty_file = {"file": ("empty.txt", io.BytesIO(b""), "text/plain")}
    res_empty = await client.post(
        "/api/v1/accord/conversations/upload",
        files=empty_file,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_empty.status_code == 422


@pytest.mark.asyncio
async def test_conversation_listing_and_pagination(client: AsyncClient):
    """Verify conversation listing with pagination."""
    token = await get_auth_token(client, "user_listing@example.com")

    # Create 3 conversations
    for i in range(3):
        await client.post(
            "/api/v1/accord/conversations/text",
            json={"content": f"User: Message number {i}", "title": f"Chat {i}"},
            headers={"Authorization": f"Bearer {token}"},
        )

    # Page 1 with page_size=2
    res_page1 = await client.get(
        "/api/v1/accord/conversations?page=1&page_size=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_page1.status_code == 200
    data1 = res_page1.json()
    assert data1["total"] == 3
    assert len(data1["items"]) == 2
    assert data1["page"] == 1
    assert data1["pages"] == 2

    # Page 2 with page_size=2
    res_page2 = await client.get(
        "/api/v1/accord/conversations?page=2&page_size=2",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_page2.status_code == 200
    data2 = res_page2.json()
    assert len(data2["items"]) == 1


@pytest.mark.asyncio
async def test_conversation_details_and_ownership_enforcement(client: AsyncClient):
    """Verify that a user can retrieve their own conversation, but is blocked from accessing others'."""
    token_user_a = await get_auth_token(client, "user_a@example.com")
    token_user_b = await get_auth_token(client, "user_b@example.com")

    # User A creates a conversation
    create_res = await client.post(
        "/api/v1/accord/conversations/text",
        json={"content": "Alice: Confidential notes", "title": "Private Chat"},
        headers={"Authorization": f"Bearer {token_user_a}"},
    )
    conv_id = create_res.json()["id"]

    # User A retrieves their own conversation
    res_owner = await client.get(
        f"/api/v1/accord/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {token_user_a}"},
    )
    assert res_owner.status_code == 200
    assert res_owner.json()["title"] == "Private Chat"

    # User B attempts to access User A's conversation -> 404 (IDOR protection)
    res_unauthorized = await client.get(
        f"/api/v1/accord/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {token_user_b}"},
    )
    assert res_unauthorized.status_code == 404

    # Anonymous user access -> 401 Unauthorized
    res_anon = await client.get(f"/api/v1/accord/conversations/{conv_id}")
    assert res_anon.status_code == 401


@pytest.mark.asyncio
async def test_conversation_deletion_and_unauthorized_deletion(client: AsyncClient):
    """Verify secure deletion and protection against unauthorized deletion."""
    token_alice = await get_auth_token(client, "alice_del@example.com")
    token_bob = await get_auth_token(client, "bob_del@example.com")

    # Alice creates a conversation
    create_res = await client.post(
        "/api/v1/accord/conversations/text",
        json={"content": "Alice: Meeting notes", "title": "ToDelete"},
        headers={"Authorization": f"Bearer {token_alice}"},
    )
    conv_id = create_res.json()["id"]

    # Bob attempts to delete Alice's conversation -> 404
    del_bob = await client.delete(
        f"/api/v1/accord/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {token_bob}"},
    )
    assert del_bob.status_code == 404

    # Alice successfully deletes her conversation
    del_alice = await client.delete(
        f"/api/v1/accord/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {token_alice}"},
    )
    assert del_alice.status_code == 200

    # Verification: Subsequent GET returns 404
    get_again = await client.get(
        f"/api/v1/accord/conversations/{conv_id}",
        headers={"Authorization": f"Bearer {token_alice}"},
    )
    assert get_again.status_code == 404

