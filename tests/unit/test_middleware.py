"""Tests for CORS, security headers, and rate limiting middleware."""

import time
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from voter_api.api.middleware import RateLimitMiddleware, SecurityHeadersMiddleware, get_client_ip


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


def _make_request(headers: dict[str, str] | None = None, client_host: str | None = "127.0.0.1") -> Request:
    """Build a minimal Starlette Request with given headers and client address."""
    scope: dict = {
        "type": "http",
        "method": "GET",
        "path": "/test",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }
    if client_host is not None:
        scope["client"] = (client_host, 0)
    return Request(scope)


class TestGetClientIp:
    """Tests for the get_client_ip helper function."""

    def test_cf_connecting_ip_takes_priority(self) -> None:
        request = _make_request(
            headers={
                "CF-Connecting-IP": "203.0.113.1",
                "X-Forwarded-For": "198.51.100.1, 10.0.0.1",
                "X-Real-IP": "192.0.2.1",
            }
        )
        assert get_client_ip(request) == "203.0.113.1"

    def test_x_forwarded_for_uses_leftmost_ip(self) -> None:
        request = _make_request(headers={"X-Forwarded-For": "203.0.113.1, 10.0.0.1, 10.0.0.2"})
        assert get_client_ip(request) == "203.0.113.1"

    def test_x_forwarded_for_single_ip(self) -> None:
        request = _make_request(headers={"X-Forwarded-For": "203.0.113.1"})
        assert get_client_ip(request) == "203.0.113.1"

    def test_x_real_ip_fallback(self) -> None:
        request = _make_request(headers={"X-Real-IP": "203.0.113.1"})
        assert get_client_ip(request) == "203.0.113.1"

    def test_falls_back_to_client_host(self) -> None:
        request = _make_request(client_host="10.0.0.1")
        assert get_client_ip(request) == "10.0.0.1"

    def test_returns_unknown_when_no_client(self) -> None:
        request = _make_request(headers={}, client_host=None)
        assert get_client_ip(request) == "unknown"

    def test_custom_header_order(self) -> None:
        request = _make_request(
            headers={
                "CF-Connecting-IP": "203.0.113.1",
                "X-Real-IP": "192.0.2.1",
            }
        )
        # With reversed priority, X-Real-IP should win
        assert get_client_ip(request, ["X-Real-IP", "CF-Connecting-IP"]) == "192.0.2.1"

    def test_empty_header_value_skipped(self) -> None:
        request = _make_request(
            headers={"CF-Connecting-IP": "  ", "X-Real-IP": "203.0.113.1"},
        )
        assert get_client_ip(request) == "203.0.113.1"

    def test_strips_whitespace_from_ip(self) -> None:
        request = _make_request(headers={"CF-Connecting-IP": "  203.0.113.1  "})
        assert get_client_ip(request) == "203.0.113.1"


class TestRateLimitMiddlewareProxyHeaders:
    """Tests for rate limiting with proxy header IP extraction."""

    def test_different_proxy_ips_have_separate_limits(self) -> None:
        app = _create_test_app()
        app.add_middleware(RateLimitMiddleware, requests_per_minute=2)
        client = TestClient(app)

        # Client A uses 2 requests (fills limit)
        for _ in range(2):
            resp = client.get("/test", headers={"CF-Connecting-IP": "203.0.113.1"})
            assert resp.status_code == 200

        # Client A is now rate-limited
        resp = client.get("/test", headers={"CF-Connecting-IP": "203.0.113.1"})
        assert resp.status_code == 429

        # Client B should still be allowed
        resp = client.get("/test", headers={"CF-Connecting-IP": "203.0.113.2"})
        assert resp.status_code == 200

    def test_same_proxy_ip_shares_limit(self) -> None:
        app = _create_test_app()
        app.add_middleware(RateLimitMiddleware, requests_per_minute=2)
        client = TestClient(app)

        for _ in range(2):
            client.get("/test", headers={"CF-Connecting-IP": "203.0.113.1"})

        resp = client.get("/test", headers={"CF-Connecting-IP": "203.0.113.1"})
        assert resp.status_code == 429

    def test_xff_used_when_cf_header_absent(self) -> None:
        app = _create_test_app()
        app.add_middleware(RateLimitMiddleware, requests_per_minute=2)
        client = TestClient(app)

        # XFF client A fills limit
        for _ in range(2):
            resp = client.get("/test", headers={"X-Forwarded-For": "198.51.100.1, 10.0.0.1"})
            assert resp.status_code == 200

        # XFF client A is rate-limited
        resp = client.get("/test", headers={"X-Forwarded-For": "198.51.100.1, 10.0.0.1"})
        assert resp.status_code == 429

        # XFF client B should still be allowed
        resp = client.get("/test", headers={"X-Forwarded-For": "198.51.100.2, 10.0.0.1"})
        assert resp.status_code == 200
