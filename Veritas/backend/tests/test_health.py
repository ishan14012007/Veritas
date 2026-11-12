from unittest.mock import patch
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_liveness(client: AsyncClient):
    """Verify that the /health liveness probe returns status ok."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "VERITAS"


@pytest.mark.asyncio
async def test_health_readiness_healthy(client: AsyncClient):
    """Verify that the /ready probe returns ready when DB and Redis are reachable."""
    with patch("app.api.v1.health.check_database_connection", return_value=True), \
         patch("app.api.v1.health.check_redis_connection", return_value=True):
        response = await client.get("/api/v1/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["database"] is True
        assert data["redis"] is True


@pytest.mark.asyncio
async def test_health_readiness_db_failure(client: AsyncClient):
    """Verify that the /ready probe returns 503 when the database is unreachable."""
    with patch("app.api.v1.health.check_database_connection", return_value=False), \
         patch("app.api.v1.health.check_redis_connection", return_value=True):
        response = await client.get("/api/v1/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unavailable"
        assert data["database"] is False
        assert data["redis"] is True


@pytest.mark.asyncio
async def test_health_readiness_redis_failure(client: AsyncClient):
    """Verify that the /ready probe returns 503 when Redis is unreachable."""
    with patch("app.api.v1.health.check_database_connection", return_value=True), \
         patch("app.api.v1.health.check_redis_connection", return_value=False):
        response = await client.get("/api/v1/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unavailable"
        assert data["database"] is True
        assert data["redis"] is False


@pytest.mark.asyncio
async def test_cors_localhost_allowed(client: AsyncClient):
    """Verify that localhost frontend origin is allowed with CORS credentials."""
    response = await client.get(
        "/api/v1/health",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.asyncio
async def test_cors_lan_ip_allowed_in_development(client: AsyncClient):
    """Verify that local network LAN IP (e.g. 10.16.54.221:5173) is allowed in development."""
    response = await client.get(
        "/api/v1/health",
        headers={"Origin": "http://10.16.54.221:5173"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://10.16.54.221:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.asyncio
async def test_cors_preflight_lan_ip(client: AsyncClient):
    """Verify that OPTIONS preflight request for LAN IP succeeds."""
    response = await client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://10.16.54.221:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://10.16.54.221:5173"


@pytest.mark.asyncio
async def test_cors_untrusted_origin_rejected(client: AsyncClient):
    """Verify that untrusted foreign origins are not reflected in CORS headers."""
    response = await client.get(
        "/api/v1/health",
        headers={"Origin": "http://evil-attacker-site.com"},
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers

