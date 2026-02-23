# Quickstart: Enhanced Authentication (009)

## New Environment Variables

Add these to your `.env` file (and `.env.example` with placeholder values):

```bash
# Mailgun email delivery
MAILGUN_API_KEY=key-your-mailgun-api-key
MAILGUN_DOMAIN=mg.yourdomain.com
MAILGUN_FROM_EMAIL=noreply@mg.yourdomain.com
MAILGUN_FROM_NAME=Voter API

# TOTP encryption (generate once: uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
TOTP_SECRET_ENCRYPTION_KEY=your-fernet-key-here

# TOTP brute force protection
TOTP_MAX_ATTEMPTS=5
TOTP_LOCKOUT_MINUTES=15

# Password reset rate limiting
RESET_RATE_LIMIT_MINUTES=5

# WebAuthn / Passkeys
WEBAUTHN_RP_ID=localhost
WEBAUTHN_RP_NAME=Voter API
WEBAUTHN_ORIGIN=http://localhost:3000
```

## Running Migrations

```bash
# Apply all new migrations (025–028)
DATABASE_URL=postgresql+asyncpg://voter_api:voter_api_dev@localhost:5432/voter_api \
  JWT_SECRET_KEY=test-secret-key-minimum-32-characters \
  uv run alembic upgrade head
```

## Testing: Password Reset

```bash
# 1. Request reset
curl -X POST http://localhost:8000/api/v1/auth/password-reset/request \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com"}'
# → 202 regardless of whether the email exists

# 2. (In dev) Get the raw token from the email or logs
# 3. Confirm reset
curl -X POST http://localhost:8000/api/v1/auth/password-reset/confirm \
  -H "Content-Type: application/json" \
  -d '{"token": "<raw-token>", "new_password": "newp@ssword1"}'
# → 200 {"message": "Password reset successfully"}
```

## Testing: User Invites

```bash
# 1. Admin creates invite
curl -X POST http://localhost:8000/api/v1/users/invites \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"email": "newuser@example.com", "role": "analyst"}'
# → 201 InviteResponse

# 2. (In dev) Get raw token from email/logs
# 3. Invitee accepts
curl -X POST http://localhost:8000/api/v1/auth/invite/accept \
  -H "Content-Type: application/json" \
  -d '{"token": "<raw-token>", "username": "newuser", "password": "str0ngp@ss"}'
# → 201 InviteAcceptResponse
```

## Testing: TOTP

```bash
# 1. Enroll (authenticated)
curl -X POST http://localhost:8000/api/v1/auth/totp/enroll \
  -H "Authorization: Bearer <token>"
# → 200 {"provisioning_uri": "otpauth://...", "qr_code_svg": "<svg ...>"}

# 2. Scan the QR code or import the URI into your authenticator app
# 3. Confirm with first code
curl -X POST http://localhost:8000/api/v1/auth/totp/confirm \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"code": "123456"}'
# → 200 {"recovery_codes": ["ABCD1234...", ...]}  (store these safely!)

# 4. Test TOTP login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "s3cur3p@ss", "totp_code": "123456"}'
# → 200 TokenResponse

# 5. Test missing TOTP code (should 403)
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "s3cur3p@ss"}'
# → 403 {"detail": "TOTP code required", "error_code": "mfa_required"}
```

## Testing: Passkeys

Passkey registration and authentication require a WebAuthn-capable client
(browser with `navigator.credentials` or a passkey manager like Bitwarden).

### Server-side flow summary

```bash
# 1. Get registration options (authenticated)
curl -X POST http://localhost:8000/api/v1/auth/passkeys/register/options \
  -H "Authorization: Bearer <token>"
# → 200 {"options": {...}, "challenge_token": "<short-lived-jwt>"}

# 2. Client calls navigator.credentials.create(options) and gets credential_response
# 3. Verify registration
curl -X POST http://localhost:8000/api/v1/auth/passkeys/register/verify \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"credential_response": {...}, "challenge_token": "...", "name": "iPhone"}'
# → 201 PasskeyResponse

# 4. Passkey login — get options
curl -X POST http://localhost:8000/api/v1/auth/passkeys/login/options \
  -H "Content-Type: application/json" \
  -d '{"username": "alice"}'
# → 200 {"options": {...}, "challenge_token": "..."}

# 5. Client calls navigator.credentials.get(options) and gets credential_response
# 6. Verify authentication
curl -X POST http://localhost:8000/api/v1/auth/passkeys/login/verify \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "credential_response": {...}, "challenge_token": "..."}'
# → 200 TokenResponse
```

### Local testing with a WebAuthn simulator

For automated passkey testing without a real device, use a WebAuthn test library
or a browser with Chrome's WebAuthn DevTools panel (DevTools → Security → WebAuthn).

## Running Tests

```bash
# Install new deps first (if not already done)
uv add pyotp segno cryptography py-webauthn mailgun

# Unit tests (no database needed)
uv run pytest tests/unit/lib/test_totp/ tests/unit/lib/test_passkey/ tests/unit/lib/test_mailer/ -v

# Integration tests
uv run pytest tests/integration/ -v

# E2E tests (requires PostGIS + env vars)
DATABASE_URL=postgresql+asyncpg://voter_api:voter_api_dev@localhost:5432/voter_api \
  JWT_SECRET_KEY=test-secret-key-minimum-32-characters \
  TOTP_SECRET_ENCRYPTION_KEY=<fernet-key> \
  MAILGUN_API_KEY=test-key \
  MAILGUN_DOMAIN=test.mailgun.org \
  MAILGUN_FROM_EMAIL=test@test.mailgun.org \
  WEBAUTHN_RP_ID=localhost \
  WEBAUTHN_ORIGIN=http://localhost \
  uv run pytest tests/e2e/ -v

# Lint before commit
uv run ruff check . && uv run ruff format --check .
```

## Generating a Fernet Key

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Store this value as `TOTP_SECRET_ENCRYPTION_KEY` in your `.env` and in piku's
`config:set` for deployed environments. Do **not** commit it to the repository.
