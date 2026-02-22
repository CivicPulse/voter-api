"""CORS, rate limiting, and security headers middleware."""

import time
from collections import defaultdict
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from voter_api.core.config import Settings

_DEFAULT_TRUSTED_HEADERS = ["CF-Connecting-IP", "X-Forwarded-For", "X-Real-IP"]


def get_client_ip(request: Request, trusted_headers: list[str] | None = None) -> str:
    """Extract the real client IP from proxy headers or direct connection.

    Checks headers in priority order. For X-Forwarded-For, uses the
    leftmost (client-supplied) IP. Falls back to request.client.host.

    Args:
        request: The incoming Starlette request.
        trusted_headers: Ordered list of header names to check.
            Defaults to ["CF-Connecting-IP", "X-Forwarded-For", "X-Real-IP"].

    Returns:
        The client IP address string, or "unknown" if not determinable.
    """
    headers = trusted_headers if trusted_headers is not None else _DEFAULT_TRUSTED_HEADERS

    for header in headers:
        value = request.headers.get(header, "").strip()
        if not value:
            continue
        # X-Forwarded-For can contain multiple IPs: "client, proxy1, proxy2"
        if header.lower() == "x-forwarded-for":
            return value.split(",")[0].strip()
        return value

    if request.client:
        return request.client.host
    return "unknown"


def setup_cors(app: FastAPI, settings: Settings) -> None:
    """Configure CORS middleware on the FastAPI app.

    Args:
        app: The FastAPI application.
        settings: Application settings.
    """
    kwargs: dict[str, Any] = {
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }
    if settings.cors_origin_list:
        kwargs["allow_origins"] = settings.cors_origin_list
    if settings.cors_origin_regex.strip():
        kwargs["allow_origin_regex"] = settings.cors_origin_regex.strip()
    app.add_middleware(CORSMiddleware, **kwargs)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Add security headers to the response.

        Args:
            request: The incoming request.
            call_next: The next middleware/handler.

        Returns:
            Response with security headers.
        """
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiting middleware.

    Limits requests per IP address with a sliding window approach.
    Uses proxy headers to identify real client IPs behind reverse proxies.
    """

    def __init__(
        self,
        app: ASGIApp,
        requests_per_minute: int = 60,
        trusted_proxy_headers: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.trusted_proxy_headers = trusted_proxy_headers
        self._request_counts: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Check rate limit and process request.

        Args:
            request: The incoming request.
            call_next: The next middleware/handler.

        Returns:
            Response, or 429 if rate limited.
        """
        client_ip = get_client_ip(request, self.trusted_proxy_headers)
        now = time.time()
        window_start = now - 60.0

        # Clean old entries
        self._request_counts[client_ip] = [t for t in self._request_counts[client_ip] if t > window_start]

        if len(self._request_counts[client_ip]) >= self.requests_per_minute:
            return Response(
                content='{"detail":"Rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
            )

        self._request_counts[client_ip].append(now)
        return await call_next(request)
