import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_user_success(client: AsyncClient):
    """Verify successful user registration and JWT token issuance."""
    payload = {
        "email": "sarah.connor@example.com",
        "password": "SecurePassword2026!",
        "full_name": "Sarah Connor",
        "phone_number": "+14155552671",
        "whatsapp_opt_in": True,
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "user" in data
    assert "tokens" in data
    assert data["user"]["email"] == "sarah.connor@example.com"
    assert data["user"]["full_name"] == "Sarah Connor"
    assert data["user"]["whatsapp_opt_in"] is True
    assert "password_hash" not in data["user"]
    assert "access_token" in data["tokens"]
    assert "refresh_token" in data["tokens"]


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    """Verify that registering with an already existing email returns 409 Conflict."""
    payload = {
        "email": "duplicate@example.com",
        "password": "SecurePassword123!",
        "full_name": "First User",
    }
    # Initial registration
    res1 = await client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    # Second registration with same email
    res2 = await client.post("/api/v1/auth/register", json=payload)
    assert res2.status_code == 409
    data = res2.json()
    assert data["success"] is False
    assert "already exists" in data["error"]["message"]


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    """Verify successful login with valid credentials."""
    # Register first
    reg_payload = {
        "email": "login.test@example.com",
        "password": "MySecretPassword123!",
        "full_name": "Login User",
    }
    await client.post("/api/v1/auth/register", json=reg_payload)

    # Login
    login_payload = {
        "email": "login.test@example.com",
        "password": "MySecretPassword123!",
    }
    response = await client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["email"] == "login.test@example.com"
    assert "access_token" in data["tokens"]


@pytest.mark.asyncio
async def test_login_invalid_password(client: AsyncClient):
    """Verify that invalid password returns 401 Unauthorized."""
    # Register
    reg_payload = {
        "email": "wrongpwd@example.com",
        "password": "CorrectPassword123!",
        "full_name": "Wrong Pwd User",
    }
    await client.post("/api/v1/auth/register", json=reg_payload)

    # Attempt login with wrong password
    login_payload = {
        "email": "wrongpwd@example.com",
        "password": "WrongPassword!",
    }
    response = await client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert "Invalid email address or password" in data["error"]["message"]


@pytest.mark.asyncio
async def test_login_nonexistent_email(client: AsyncClient):
    """Verify that logging in with non-existent email returns 401 Unauthorized."""
    login_payload = {
        "email": "does.not.exist@example.com",
        "password": "AnyPassword123!",
    }
    response = await client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_endpoint_me_success(client: AsyncClient):
    """Verify that /auth/me returns the user profile when authenticated."""
    reg_payload = {
        "email": "protected.me@example.com",
        "password": "Password123!",
        "full_name": "Protected User",
    }
    reg_res = await client.post("/api/v1/auth/register", json=reg_payload)
    token = reg_res.json()["tokens"]["access_token"]

    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "protected.me@example.com"
    assert data["full_name"] == "Protected User"


@pytest.mark.asyncio
async def test_protected_endpoint_without_token(client: AsyncClient):
    """Verify that /auth/me rejects unauthenticated requests with 401."""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert "missing" in data["error"]["message"].lower()


@pytest.mark.asyncio
async def test_protected_endpoint_with_invalid_token(client: AsyncClient):
    """Verify that /auth/me rejects invalid/tampered token with 401."""
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer totally-invalid-token-payload"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert "invalid" in data["error"]["message"].lower()


# ==============================================================================
# Development Quick Auth & Validation Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_first_time_dev_account_creation_and_login(client: AsyncClient):
    """Verify first-time creation of development account with .local domain and immediate login."""
    dev_email = "new.dev@veritas.local"
    dev_password = "TesterPass123!"

    # 1. First-time registration
    reg_payload = {
        "email": dev_email,
        "password": dev_password,
        "full_name": "Veritas QA Tester",
    }
    reg_res = await client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 201
    reg_data = reg_res.json()
    assert reg_data["user"]["email"] == dev_email
    assert "access_token" in reg_data["tokens"]

    # 2. Login immediately after creation
    login_payload = {
        "email": dev_email,
        "password": dev_password,
    }
    login_res = await client.post("/api/v1/auth/login", json=login_payload)
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert login_data["user"]["email"] == dev_email
    assert "access_token" in login_data["tokens"]


@pytest.mark.asyncio
async def test_repeated_quick_dev_auth_attempts(client: AsyncClient):
    """Verify that repeated Quick Dev Auth attempts succeed via login for existing account."""
    dev_email = "repeated.dev@veritas.local"
    dev_password = "TesterPass123!"

    # First attempt: register account
    reg_payload = {
        "email": dev_email,
        "password": dev_password,
        "full_name": "Veritas QA Tester",
    }
    res1 = await client.post("/api/v1/auth/register", json=reg_payload)
    assert res1.status_code == 201

    # Second attempt: login with existing credentials (simulating repeat button click)
    login_payload = {"email": dev_email, "password": dev_password}
    res2 = await client.post("/api/v1/auth/login", json=login_payload)
    assert res2.status_code == 200
    assert res2.json()["user"]["email"] == dev_email

    # Third attempt: login again
    res3 = await client.post("/api/v1/auth/login", json=login_payload)
    assert res3.status_code == 200
    assert "access_token" in res3.json()["tokens"]


@pytest.mark.asyncio
async def test_existing_account_login_with_correct_credentials(client: AsyncClient):
    """Verify that an existing account logs in cleanly with correct credentials."""
    email = "existing.user@veritas.local"
    password = "CorrectDevPassword123!"

    reg_payload = {"email": email, "password": password, "full_name": "Existing User"}
    await client.post("/api/v1/auth/register", json=reg_payload)

    # Login
    login_res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login_res.status_code == 200
    data = login_res.json()
    assert data["user"]["email"] == email
    assert data["tokens"]["token_type"] == "Bearer"


@pytest.mark.asyncio
async def test_invalid_credentials_returns_401(client: AsyncClient):
    """Verify that wrong password for existing user returns 401 Unauthorized."""
    email = "test.cred@veritas.local"
    password = "CorrectPassword123!"

    reg_payload = {"email": email, "password": password, "full_name": "Cred User"}
    await client.post("/api/v1/auth/register", json=reg_payload)

    # Wrong password
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPassword!"},
    )
    assert login_res.status_code == 401
    assert "Invalid email address or password" in login_res.json()["error"]["message"]

    # Non-existent email
    nonexistent_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@veritas.local", "password": "AnyPassword123!"},
    )
    assert nonexistent_res.status_code == 401


@pytest.mark.asyncio
async def test_registration_validation_errors(client: AsyncClient):
    """Verify that invalid registration inputs return 422 with structured field details."""
    # 1. Invalid email format
    res_bad_email = await client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "Password123!", "full_name": "Tester"},
    )
    assert res_bad_email.status_code == 422
    data_bad_email = res_bad_email.json()
    assert data_bad_email["error"]["code"] == "VALIDATION_FAILED"
    assert any("email" in str(d["loc"]) for d in data_bad_email["error"]["details"])

    # 2. Short password (< 8 chars)
    res_short_pwd = await client.post(
        "/api/v1/auth/register",
        json={"email": "valid@veritas.local", "password": "short", "full_name": "Tester"},
    )
    assert res_short_pwd.status_code == 422
    data_short_pwd = res_short_pwd.json()
    assert any("password" in str(d["loc"]) for d in data_short_pwd["error"]["details"])

    # 3. Missing full_name
    res_no_name = await client.post(
        "/api/v1/auth/register",
        json={"email": "valid2@veritas.local", "password": "Password123!", "full_name": ""},
    )
    assert res_no_name.status_code == 422


