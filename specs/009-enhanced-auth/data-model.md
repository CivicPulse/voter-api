# Data Model: Enhanced Authentication (009)

**Branch**: `009-enhanced-auth` | **Date**: 2026-02-22

---

## Existing Model: User (modified)

No new columns are added to the `users` table. The `User` model gains relationships to all new entities defined below.

---

## New Entity 1: PasswordResetToken

**Table**: `password_reset_tokens`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK, default gen_random_uuid() | |
| `user_id` | UUID | FK → users.id, ON DELETE CASCADE, indexed | One-to-many; a user may have multiple (only latest is active) |
| `token_hash` | VARCHAR(64) | NOT NULL, UNIQUE | SHA-256 hex digest of the raw token; raw token sent by email only |
| `expires_at` | TIMESTAMPTZ | NOT NULL | `created_at + 24 hours` |
| `used_at` | TIMESTAMPTZ | NULL | Set on successful use; non-null means consumed |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**State transitions**: created → used (via `used_at`) or expired (via `expires_at`).

**Validation rules**:
- A valid token satisfies: `used_at IS NULL AND expires_at > now()`
- On new reset request for same user: all prior rows for that user are deleted (one active at a time)
- Rate limit: system checks if a row exists for that user with `created_at > now() - RESET_RATE_LIMIT_MINUTES`; if so, the request is silently accepted but no new row or email is created

---

## New Entity 2: UserInvite

**Table**: `user_invites`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK, default gen_random_uuid() | |
| `email` | VARCHAR(255) | NOT NULL, indexed | Target email for the invite |
| `role` | VARCHAR(20) | NOT NULL | One of: admin, analyst, viewer |
| `invited_by_id` | UUID | FK → users.id, ON DELETE SET NULL, nullable | Admin who sent the invite |
| `token_hash` | VARCHAR(64) | NOT NULL, UNIQUE | SHA-256 hex digest of raw token |
| `expires_at` | TIMESTAMPTZ | NOT NULL | `created_at + 7 days` |
| `accepted_at` | TIMESTAMPTZ | NULL | Set when invitee completes registration |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**State transitions**: pending → accepted (via `accepted_at`) or expired (via `expires_at`) or cancelled (row deleted).

**Validation rules**:
- A valid invite satisfies: `accepted_at IS NULL AND expires_at > now()`
- Inviting an email already in `users.email` → error before creating row
- Only one pending invite per email at a time; resend cancels the previous row and creates a new one
- On delivery failure: the row is NOT created (fail-fast)

---

## New Entity 3: TOTPCredential

**Table**: `totp_credentials`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK, default gen_random_uuid() | |
| `user_id` | UUID | FK → users.id, ON DELETE CASCADE, UNIQUE | One TOTP credential per user |
| `encrypted_secret` | TEXT | NOT NULL | Fernet-encrypted TOTP shared secret (base32 before encryption) |
| `is_verified` | BOOLEAN | NOT NULL, default false | True only after enrollment confirmation with valid code |
| `enrolled_at` | TIMESTAMPTZ | NULL | Set when `is_verified` becomes true |
| `failed_attempts` | INTEGER | NOT NULL, default 0 | Consecutive failed TOTP verifications |
| `locked_until` | TIMESTAMPTZ | NULL | If set and `> now()`, TOTP is locked (recovery code still bypasses) |
| `last_used_otp` | VARCHAR(6) | NULL | Last successfully accepted 6-digit TOTP code; used for replay prevention |
| `last_used_otp_at` | TIMESTAMPTZ | NULL | Timestamp of last accepted code; replay check window is 30 seconds |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**State transitions**:
- `is_verified=false` → enrollment pending (user has URI/QR but TOTP not yet active)
- `is_verified=true, locked_until IS NULL` → active
- `is_verified=true, locked_until > now()` → locked (recovery code bypasses)
- Deleted → TOTP disabled

**Validation rules**:
- Login enforcement: check `is_verified = true` before requiring TOTP at login
- Lockout: after 5 consecutive failures, set `locked_until = now() + 15 minutes`; reset `failed_attempts = 0`
- Successful TOTP or recovery code use: reset `failed_attempts = 0`, clear `locked_until`
- Replay prevention (FR-020): before accepting a 6-digit TOTP code, check `last_used_otp = submitted_code AND last_used_otp_at >= (now() - 30 seconds)`; if true, reject the code with `mfa_invalid`. On acceptance, set `last_used_otp = submitted_code` and `last_used_otp_at = now()`. This is enforced at the service layer; `TOTPManager.verify_code` is stateless.

---

## New Entity 4: TOTPRecoveryCode

**Table**: `totp_recovery_codes`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK, default gen_random_uuid() | |
| `user_id` | UUID | FK → users.id, ON DELETE CASCADE, indexed | |
| `code_hash` | VARCHAR(64) | NOT NULL | SHA-256 hex digest of raw 16-char alphanumeric code |
| `used_at` | TIMESTAMPTZ | NULL | Set on use; non-null means consumed |
| `created_at` | TIMESTAMPTZ | NOT NULL, default now() | |

**Notes**:
- Exactly 10 rows created per user at TOTP enrollment confirmation
- A valid recovery code satisfies: `used_at IS NULL`
- All recovery codes for a user are deleted when TOTP is disabled or re-enrolled
- Raw codes displayed exactly once; only hashes stored

---

## New Entity 5: Passkey

**Table**: `passkeys`

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | UUID | PK, default gen_random_uuid() | |
| `user_id` | UUID | FK → users.id, ON DELETE CASCADE, indexed | Many passkeys per user |
| `credential_id` | BYTEA | NOT NULL, UNIQUE, indexed | WebAuthn credential ID (variable length binary) |
| `public_key` | BYTEA | NOT NULL | COSE-encoded public key bytes |
| `sign_count` | INTEGER | NOT NULL, default 0 | Monotonically increasing; used for cloning detection |
| `name` | VARCHAR(100) | NULL | User-assigned display name |
| `registered_at` | TIMESTAMPTZ | NOT NULL, default now() | |
| `last_used_at` | TIMESTAMPTZ | NULL | Updated on successful authentication |

**Validation rules**:
- `credential_id` must be globally unique (enforced by UNIQUE constraint)
- `sign_count` must be >= the stored value on each authentication (cloning detection); py_webauthn enforces this
- A user may register multiple passkeys (no per-user limit defined)
- Deleting the last passkey is allowed (password login remains available)

---

## Migrations Plan

| Migration | Number | Content |
|---|---|---|
| `025_create_password_reset_tokens` | 025 | `password_reset_tokens` table |
| `026_create_user_invites` | 026 | `user_invites` table |
| `027_create_totp_auth` | 027 | `totp_credentials` + `totp_recovery_codes` tables |
| `028_create_passkeys` | 028 | `passkeys` table |

---

## SQLAlchemy Relationship Summary

```
User
├── password_reset_tokens → PasswordResetToken (one-to-many, cascade delete)
├── sent_invites → UserInvite (one-to-many via invited_by_id)
├── totp_credential → TOTPCredential (one-to-one, cascade delete)
├── totp_recovery_codes → TOTPRecoveryCode (one-to-many, cascade delete)
└── passkeys → Passkey (one-to-many, cascade delete)
```

---

## Source File Locations

| Entity | Model file | Migration |
|---|---|---|
| PasswordResetToken | `src/voter_api/models/auth_tokens.py` | `alembic/versions/025_create_password_reset_tokens.py` |
| UserInvite | `src/voter_api/models/auth_tokens.py` | `alembic/versions/026_create_user_invites.py` |
| TOTPCredential | `src/voter_api/models/totp.py` | `alembic/versions/027_create_totp_auth.py` |
| TOTPRecoveryCode | `src/voter_api/models/totp.py` | `alembic/versions/027_create_totp_auth.py` |
| Passkey | `src/voter_api/models/passkey.py` | `alembic/versions/028_create_passkeys.py` |
