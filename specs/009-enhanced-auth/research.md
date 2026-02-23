# Research: Enhanced Authentication (009)

**Branch**: `009-enhanced-auth` | **Date**: 2026-02-22

---

## Decision 1: TOTP Library

**Decision**: `pyotp`

**Rationale**: pyotp is the de-facto standard Python TOTP library. It generates RFC 6238-compliant time-based codes, produces `otpauth://` provisioning URIs directly compatible with Google Authenticator, Authy, and 1Password. It is synchronous but CPU-bound (no I/O), so it is safe to call from async FastAPI route handlers without blocking. API surface is minimal and stable.

**Alternatives considered**:
- `mintotp` — minimal and educational but lacks provisioning URI generation and is not production-maintained.

**Not in pyproject.toml**: `pyotp` must be added via `uv add pyotp`.

---

## Decision 2: QR Code Generation

**Decision**: `segno`

**Rationale**: `segno` is a pure-Python QR code library with no Pillow/image dependency. It generates SVG directly as a string, making it trivial to return an inline SVG from the TOTP enrollment endpoint. This avoids adding Pillow (a large binary dependency) for a single feature.

**Alternatives considered**:
- `qrcode[pil]` — requires Pillow; overkill for a single endpoint.
- Return URI only — valid but the spec explicitly requires a QR code in the API response.

**Not in pyproject.toml**: `segno` must be added via `uv add segno`.

---

## Decision 3: TOTP Secret Encryption at Rest

**Decision**: `cryptography` (Fernet symmetric encryption)

**Rationale**: The spec requires TOTP secrets to be encrypted at rest. Fernet (from the `cryptography` package) provides authenticated symmetric encryption with a simple key-rotation-friendly API. The encryption key is sourced from the environment (`TOTP_SECRET_ENCRYPTION_KEY`), satisfying the 12-factor config principle.

**Alternatives considered**:
- Store raw secrets — violates the spec requirement that tokens/secrets not be stored in plaintext.
- `hashlib` — hashing is one-way and cannot recover the secret for verification; not suitable.

**Already present as transitive dependency**: `cryptography` is likely already installed (bcrypt pulls it in), but will be added explicitly to `pyproject.toml`.

---

## Decision 4: WebAuthn / Passkey Library

**Decision**: `py-webauthn` (Duo Security, `pywebauthn` import name)

**Rationale**: `py-webauthn` is the industry-standard Python WebAuthn library, maintained by Duo Security. It provides high-level `generate_registration_options`, `verify_registration_response`, `generate_authentication_options`, and `verify_authentication_response` functions that handle CBOR/COSE decoding internally. Supports multiple credentials per user and sign-count tracking (cloning detection). The API maps directly to the username-first passkey flow selected in clarifications.

**Alternatives considered**:
- `fido2` (Yubico) — lower-level, better for protocol implementors than application developers; requires significantly more boilerplate for a standard WebAuthn flow.
- `webauthn` (generic) — less maintained, smaller community.

**Not in pyproject.toml**: `py-webauthn` must be added via `uv add py-webauthn`.

---

## Decision 5: Email Delivery — Official Mailgun Python SDK

**Decision**: `mailgun` (official Mailgun Python SDK, v1.6.0, released 2026-01-08)

**Rationale**: The official Mailgun SDK provides a purpose-built `AsyncClient` that supports `async with` and `await` patterns, offering a cleaner and more maintainable abstraction than constructing raw HTTP requests manually. It handles Mailgun-specific auth, error response parsing, and API versioning internally. Version 1.6.0 was released January 2026 and supports Python 3.10–3.14 (covers Python 3.13). Using the official SDK is preferable to raw httpx for a named external service: it stays in sync with Mailgun API changes, reduces boilerplate, and makes the intent of the code immediately clear.

```python
from mailgun.client import AsyncClient

async with AsyncClient(auth=("api", settings.mailgun_api_key)) as client:
    await client.messages.create(
        data={
            "from": settings.mailgun_from_email,
            "to": recipient,
            "subject": subject,
            "html": html_body,
        },
        domain=settings.mailgun_domain,
    )
```

**New env vars**: `MAILGUN_API_KEY`, `MAILGUN_DOMAIN`, `MAILGUN_FROM_EMAIL`, `MAILGUN_FROM_NAME`.

**Alternatives considered**:
- Raw `httpx` — works but requires manually constructing Mailgun auth, endpoint URLs, and error parsing; no advantage over the official SDK.
- `fastapi-mail` — SMTP-oriented wrapper; no native Mailgun API support.
- `aiosmtplib` — SMTP-based; Mailgun's HTTP API is preferred for deliverability and tracking.

---

## Decision 6: WebAuthn Challenge Storage

**Decision**: Short-lived JWT challenge tokens (stateless)

**Rationale**: Since the application is stateless (JWT-based, no server sessions), WebAuthn challenges are embedded in a short-lived JWT signed with `JWT_SECRET_KEY`. The "options" endpoints return a `challenge_token` (5-minute JWT containing the base64url challenge bytes and the username). The "verify" endpoints accept the `challenge_token`, decode it to recover the expected challenge, then pass it to py_webauthn for assertion verification. This avoids adding a `pending_challenges` database table while keeping the design secure (challenge token is signed and expiring).

**Alternatives considered**:
- Temporary DB table with TTL — adds a migration and cleanup job for a single-use ephemeral artifact; more complexity than needed.
- Redis cache — Redis is not in the constitutional tech stack.

---

## Decision 7: Login Endpoint Format Change

**Decision**: Change login from OAuth2 form-data to JSON body

**Rationale**: The current `POST /auth/login` uses `OAuth2PasswordRequestForm` (form-encoded). Adding `totp_code` as an optional field is non-standard for form-based OAuth2. Since this is an API-first backend with no browser form submission, switching to a JSON body (`LoginRequest` schema with optional `totp_code`) is the clean long-term approach. Swagger UI authorization can be handled via a custom example or separate documentation.

**Breaking change**: Existing API clients using the form-encoded login endpoint must be updated to send JSON. This is a known, intentional breaking change in this feature.

**Alternatives considered**:
- Keep form-data and add a parallel JSON endpoint — duplicates login logic.
- Extend `OAuth2PasswordRequestForm` with a custom subclass — non-standard and brittle.

---

## Decision 8: Existing Codebase Integration Points

**From exploration of `feat/auth-improvments` branch:**

| Item | Finding |
|---|---|
| Latest migration | `024_create_meeting_records_tables.py` — next: **025** |
| Login endpoint | `POST /auth/login` using `OAuth2PasswordRequestForm`; will be migrated to JSON |
| Router pattern | `APIRouter(tags=["auth"])`, no URL prefix; auth routes on root path |
| User model mixins | `Base` + `UUIDMixin` |
| Auth service functions | `authenticate_user`, `create_user`, `list_users`, `generate_tokens`, `refresh_access_token` |
| Existing libs | 11 libs in `src/voter_api/lib/`; none cover email, TOTP, or passkeys |
| Schema pattern | Pydantic v2, `Field()` for validation, `model_config = ConfigDict(from_attributes=True)` |
| Config | `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, `JWT_REFRESH_TOKEN_EXPIRE_DAYS` in `.env.example` |

---

## New Dependencies Summary

| Package | Purpose | Command |
|---|---|---|
| `pyotp` | TOTP secret generation, code verification, provisioning URIs | `uv add pyotp` |
| `segno` | QR code SVG generation for TOTP enrollment | `uv add segno` |
| `cryptography` | Fernet encryption of TOTP secrets at rest | `uv add cryptography` |
| `py-webauthn` | WebAuthn registration and authentication ceremony | `uv add py-webauthn` |
| `mailgun` | Official Mailgun Python SDK with AsyncClient | `uv add mailgun` |

---

## New Environment Variables Summary

| Variable | Purpose | Example |
|---|---|---|
| `MAILGUN_API_KEY` | Mailgun API key | `key-...` |
| `MAILGUN_DOMAIN` | Mailgun sending domain | `mg.example.com` |
| `MAILGUN_FROM_EMAIL` | Sender address | `noreply@mg.example.com` |
| `MAILGUN_FROM_NAME` | Sender display name | `Voter API` |
| `WEBAUTHN_RP_ID` | WebAuthn relying party ID (domain) | `localhost` |
| `WEBAUTHN_RP_NAME` | Relying party display name | `Voter API` |
| `WEBAUTHN_ORIGIN` | Expected origin for passkey ceremonies | `http://localhost:3000` |
| `TOTP_SECRET_ENCRYPTION_KEY` | Fernet key for TOTP secret encryption at rest | *(generated)* |
| `TOTP_MAX_ATTEMPTS` | Failed TOTP attempts before lockout | `5` |
| `TOTP_LOCKOUT_MINUTES` | Lockout duration in minutes | `15` |
| `RESET_RATE_LIMIT_MINUTES` | Password reset throttle window | `5` |
