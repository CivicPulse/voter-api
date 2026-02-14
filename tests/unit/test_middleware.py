"""Tests for CORS, security headers, and rate limiting middleware."""

import time
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from voter_api.api.middleware import RateLimitMiddleware, SecurityHeadersMiddleware


def _create_test_app() -> FastAPI:
    """Create a minimal FastAPI app for middleware testing."""
    app = FastAPI()

    @app.get("/test")
    async def test_route() -> dict:
        return {"ok": True}

    return app


class TestSecurityHeadersMiddleware:
    """Tests for SecurityHeadersMiddleware."""

    @pytest.fixture
    def client(self) -> TestClient:
        app = _create_test_app()
        app.add_middleware(SecurityHeadersMiddleware)
        return TestClient(app)

    def test_x_content_type_options(self, client: TestClient) -> None:
        response = client.get("/test")
        assert response.headers["X-Content-Type-Options"] == "nosniff"

    def test_x_frame_options(self, client: TestClient) -> None:
        response = client.get("/test")
        assert response.headers["X-Frame-Options"] == "DENY"

    def test_x_xss_protection(self, client: TestClient) -> None:
        response = client.get("/test")
        assert response.headers["X-XSS-Protection"] == "1; mode=block"

    def test_strict_transport_security(self, client: TestClient) -> None:
        response = client.get("/test")
        assert "max-age=31536000" in response.headers["Strict-Transport-Security"]
        assert "includeSubDomains" in response.headers["Strict-Transport-Security"]

    def test_all_security_headers_present(self, client: TestClient) -> None:
        response = client.get("/test")
        expected_headers = [
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
            "Strict-Transport-Security",
        ]
        for header in expected_headers:
            assert header in response.headers, f"Missing security header: {header}"


class TestRateLimitMiddleware:
    """Tests for RateLimitMiddleware."""

    @pytest.fixture
    def client(self) -> TestClient:
        app = _create_test_app()
        app.add_middleware(RateLimitMiddleware, requests_per_minute=5)
        return TestClient(app)

    def test_requests_within_limit_succeed(self, client: TestClient) -> None:
        for _ in range(5):
            response = client.get("/test")
            assert response.status_code == 200

    def test_request_over_limit_returns_429(self, client: TestClient) -> None:
        for _ in range(5):
            client.get("/test")

        response = client.get("/test")
        assert response.status_code == 429

    def test_429_response_has_json_body(self, client: TestClient) -> None:
        for _ in range(6):
            response = client.get("/test")

        assert response.json() == {"detail": "Rate limit exceeded"}

    def test_429_response_content_type(self, client: TestClient) -> None:
        for _ in range(6):
            response = client.get("/test")

        assert "application/json" in response.headers.get("content-type", "")

    def test_rate_limit_window_expires(self) -> None:
        """Old requests outside the 60s window are cleaned up."""
        app = _create_test_app()
        app.add_middleware(RateLimitMiddleware, requests_per_minute=2)
        client = TestClient(app)

        base_time = time.time()

        # Make 2 requests at base_time (fills the limit)
        with patch("voter_api.api.middleware.time.time", return_value=base_time):
            assert client.get("/test").status_code == 200
            assert client.get("/test").status_code == 200
            # Third request should be blocked
            assert client.get("/test").status_code == 429

        # Advance time by 61 seconds — old entries should be cleaned up
        with patch("voter_api.api.middleware.time.time", return_value=base_time + 61):
            response = client.get("/test")
            assert response.status_code == 200
