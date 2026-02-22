# Tasks: Enhanced Authentication (009)

**Input**: Design documents from `/specs/009-enhanced-auth/`
**Prerequisites**: plan.md, spec.md, data-model.md, research.md, contracts/openapi.yaml, quickstart.md

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks in the same phase)
- **[Story]**: Which user story this task belongs to (US1–US4)
- Exact file paths are included in every task description

---

## Phase 1: Setup (Dependencies & Configuration)

**Purpose**: Install new packages and update shared configuration before any library or model work begins.

- [X] T001 Install new dependencies via `uv add pyotp segno cryptography py-webauthn mailgun`
- [X] T002 [P] Extend src/voter_api/core/config.py with 11 new Settings fields: MAILGUN_API_KEY, MAILGUN_DOMAIN, MAILGUN_FROM_EMAIL, MAILGUN_FROM_NAME, TOTP_SECRET_ENCRYPTION_KEY, TOTP_MAX_ATTEMPTS (default 5), TOTP_LOCKOUT_MINUTES (default 15), RESET_RATE_LIMIT_MINUTES (default 5), WEBAUTHN_RP_ID, WEBAUTHN_RP_NAME, WEBAUTHN_ORIGIN
- [X] T003 [P] Extend .env.example with all 11 new env vars with placeholder values per quickstart.md

---

## Phase 2: Foundational (Auth Libraries — Library-First Architecture)

**Purpose**: Implement standalone, testable libraries for email delivery, TOTP, and passkeys before any service or route integration. Per the Library-First architecture principle, all three libraries must be in place before user story phases begin.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 [P] Implement src/voter_api/lib/mailer/mailer.py with MailgunMailer class: async send_email(to, subject, html_body) via mailgun AsyncClient, render_template(name, context) via Jinja2, MailDeliveryError (RuntimeError subclass) raised on non-2xx response; create src/voter_api/lib/mailer/__init__.py exporting MailgunMailer
- [X] T005 [P] Create Jinja2 HTML email templates: src/voter_api/lib/mailer/templates/password_reset.html (token link, 24h expiry notice, app name) and src/voter_api/lib/mailer/templates/invite.html (invite link, assigned role, 7-day expiry, app name)
- [X] T006 [P] Implement src/voter_api/lib/totp/manager.py with TOTPManager: generate_secret() → Fernet-encrypted base32, get_provisioning_uri(encrypted_secret, username, issuer) → otpauth:// URI, get_qr_svg(provisioning_uri) → inline SVG string via segno, verify_code(encrypted_secret, code) → bool with 30s window tolerance, generate_recovery_codes(n=10) → (raw_codes_list, sha256_hashes_list), verify_recovery_code(raw_code, stored_hashes) → bool; create src/voter_api/lib/totp/__init__.py exporting TOTPManager
- [X] T007 [P] Implement src/voter_api/lib/passkey/manager.py with PasskeyManager: generate_registration_options(user_id, username, existing_credentials) → (options_dict, challenge_bytes), verify_registration(credential_response, expected_challenge, expected_origin, expected_rp_id) → verified_credential, generate_authentication_options(credentials) → (options_dict, challenge_bytes), verify_authentication(credential_response, expected_challenge, credential_public_key, sign_count, expected_origin, expected_rp_id) → new_sign_count; create src/voter_api/lib/passkey/__init__.py exporting PasskeyManager
- [X] T008 [P] Add create_passkey_challenge_token(username, challenge_b64, settings) → signed JWT (5-min exp, type="passkey_challenge") and decode_passkey_challenge_token(token, settings) → dict{"username", "challenge_b64"} to src/voter_api/core/security.py

- [X] T036 [P] Write unit tests for MailgunMailer in tests/unit/lib/test_mailer/test_mailer.py: mock mailgun AsyncClient, assert correct Mailgun payload (from, to, subject, html), verify template rendering with Jinja2 context variables, confirm MailDeliveryError raised on non-2xx response, test env var wiring
- [X] T037 [P] Write unit tests for TOTPManager in tests/unit/lib/test_totp/test_totp_manager.py: secret generation + Fernet encrypt/decrypt roundtrip, provisioning URI format compliance, code verification pass and fail, confirm that verify_code is stateless and does NOT track or reject replays (replay prevention is the service layer's responsibility per T026), recovery code generation (exactly 10 codes, each alphanumeric, at least 16 characters per spec), recovery code SHA-256 hash verification roundtrip; also extend T039 integration tests to cover replay prevention at the service layer (submit the same valid 6-digit code twice in the same 30-second window and assert the second call returns mfa_invalid)
- [X] T038 [P] Write unit tests for PasskeyManager in tests/unit/lib/test_passkey/test_passkey_manager.py: mock py_webauthn functions, verify correct argument passing for generate_registration_options and generate_authentication_options, assert error propagation from verify_registration and verify_authentication

**Checkpoint**: All auth libraries implemented, independently callable, and unit-tested — user story phases may now begin.

---

## Phase 3: User Story 1 — Password Self-Service Reset (Priority: P1) 🎯 MVP

**Goal**: Users can request a password reset email and set a new password via a secure single-use time-limited token, without any admin involvement.

**Independent Test**: POST /api/v1/auth/password-reset/request with a known email → 202 (always); POST /api/v1/auth/password-reset/confirm with raw token + new_password → 200; confirm old password login fails and new password works.

- [ ] T009 [P] [US1] Create PasswordResetToken model in src/voter_api/models/auth_tokens.py using UUIDMixin + Base: user_id (UUID FK → users.id ON DELETE CASCADE, indexed), token_hash (VARCHAR 64, UNIQUE NOT NULL), expires_at (TIMESTAMPTZ NOT NULL), used_at (TIMESTAMPTZ nullable), created_at (TIMESTAMPTZ default now()); add User.password_reset_tokens relationship (cascade delete)
- [ ] T010 [P] [US1] Add password reset schemas to src/voter_api/schemas/auth.py: PasswordResetRequest (email: EmailStr), PasswordResetConfirm (token: str, new_password: str minLength 8), MessageResponse (message: str); use Pydantic v2 with model_config = ConfigDict(from_attributes=True)
- [ ] T011 [US1] Write Alembic migration alembic/versions/025_create_password_reset_tokens.py creating password_reset_tokens table with all columns, UNIQUE constraint on token_hash, and index on user_id per data-model.md
- [ ] T012 [US1] Extend src/voter_api/models/__init__.py to export PasswordResetToken
- [ ] T013 [US1] Implement request_password_reset(session, mailer, settings, email) and confirm_password_reset(session, token, new_password) in src/voter_api/services/auth_service.py: request_password_reset MUST follow this exact branch order — (A) rate-limit check: if a token row for this email exists with created_at > now() - RESET_RATE_LIMIT_MINUTES, return 202 immediately with NO deletion, NO new row, and NO email sent (enumeration-safe throttle); (B) otherwise: delete all prior token rows for this user, generate raw token + SHA-256 hash, send email via MailgunMailer (fail-fast: if delivery raises MailDeliveryError, do NOT persist the new row — raise HTTP 503), commit new row only on delivery success, return 202; confirm_password_reset: load token by hash, validate (used_at IS NULL AND expires_at > now()), bcrypt-update password, set used_at; log password reset request (loguru info) and successful completion (loguru info) as security events per FR-007
- [ ] T014 [US1] Add POST /auth/password-reset/request (202, PasswordResetRequest) and POST /auth/password-reset/confirm (200, PasswordResetConfirm) endpoints to src/voter_api/api/v1/auth.py; inject MailgunMailer and Settings dependencies

**Checkpoint**: Password reset flow is fully functional — email request, token confirmation, new password login.

---

## Phase 4: User Story 2 — Admin-Initiated User Invites (Priority: P2)

**Goal**: Admins can invite new users by email with a designated role; invitees complete account registration via a secure 7-day activation link.

**Independent Test**: Admin POST /api/v1/users/invites with email + role → 201 + email sent; invitee POST /api/v1/auth/invite/accept with token + username + password → 201; verify new account exists with correct role and can log in.

- [ ] T015 [P] [US2] Extend src/voter_api/models/auth_tokens.py with UserInvite model: email (VARCHAR 255, NOT NULL, indexed), role (VARCHAR 20, NOT NULL), invited_by_id (UUID FK → users.id ON DELETE SET NULL, nullable), token_hash (VARCHAR 64, UNIQUE NOT NULL), expires_at (TIMESTAMPTZ NOT NULL), accepted_at (TIMESTAMPTZ nullable), created_at; add User.sent_invites relationship
- [ ] T016 [P] [US2] Add invite schemas to src/voter_api/schemas/auth.py: InviteCreate (email: EmailStr, role: Literal["admin","analyst","viewer"]), InviteResponse (id, email, role, invited_by_id, expires_at, accepted_at, created_at), PaginatedInvites (items: list[InviteResponse], total, page, page_size), InviteAccept (token: str, username: str minLength 3, password: str minLength 8), InviteAcceptResponse (message: str, user: UserResponse)
- [ ] T017 [US2] Write Alembic migration alembic/versions/026_create_user_invites.py creating user_invites table with all columns, UNIQUE on token_hash, and index on email per data-model.md
- [ ] T018 [US2] Extend src/voter_api/models/__init__.py to export UserInvite
- [ ] T019 [US2] Implement invite service functions in src/voter_api/services/auth_service.py: create_invite (check email not in users → generate token + hash → send email via MailgunMailer → fail-fast: no row on delivery failure → commit row), list_invites (paginated, only accepted_at IS NULL AND expires_at > now()), cancel_invite (delete row, 404 if not found), resend_invite (invalidate old token → generate new token → send email → update row), accept_invite (validate token → check username uniqueness → create User with assigned role → mark accepted_at → commit)
- [ ] T020 [US2] Add invite endpoints to src/voter_api/api/v1/auth.py: POST /users/invites (admin, 201), GET /users/invites (admin, paginated with page/page_size query params), DELETE /users/invites/{id} (admin, 204), POST /users/invites/{id}/resend (admin, 200), POST /auth/invite/accept (public, 201); enforce admin role on all management endpoints

**Checkpoint**: Full invite flow functional — admin creates invite, invitee activates account with chosen credentials, account has specified role.

---

## Phase 5: User Story 3 — TOTP Two-Factor Authentication (Priority: P3)

**Goal**: Users can enroll TOTP on their account; TOTP-enabled logins require password + 6-digit code in a single request; lockout after 5 failed attempts; recovery codes provide emergency access; admins can disable TOTP and clear lockouts.

**Independent Test**: POST /api/v1/auth/totp/enroll → POST /api/v1/auth/totp/confirm with valid code → 200 with 10 recovery codes; POST /api/v1/auth/login without totp_code → 403 mfa_required; with valid code → 200 tokens; 5 wrong codes → 429 locked.

- [ ] T021 [P] [US3] Create TOTPCredential and TOTPRecoveryCode models in src/voter_api/models/totp.py: TOTPCredential (user_id UUID FK → users.id ON DELETE CASCADE UNIQUE, encrypted_secret TEXT NOT NULL, is_verified BOOLEAN default false, enrolled_at nullable, failed_attempts INT default 0, locked_until TIMESTAMPTZ nullable, last_used_otp VARCHAR(6) nullable, last_used_otp_at TIMESTAMPTZ nullable, created_at); TOTPRecoveryCode (user_id FK → users.id ON DELETE CASCADE indexed, code_hash VARCHAR 64 NOT NULL, used_at nullable, created_at); add User.totp_credential and User.totp_recovery_codes relationships (cascade delete)
- [ ] T022 [P] [US3] Add TOTP schemas to src/voter_api/schemas/auth.py: TOTPEnrollmentResponse (provisioning_uri: str, qr_code_svg: str), TOTPConfirmRequest (code: str validated against ^[0-9]{6}$), TOTPConfirmResponse (recovery_codes: list[str]), TOTPRecoveryCodesCountResponse (remaining_codes: int), MFARequiredError (detail: str, error_code: Literal["mfa_required","mfa_invalid"]), TOTPLockedError (detail: str, locked_until: datetime); extend LoginRequest with totp_code: str | None = None
- [ ] T023 [US3] Write Alembic migration alembic/versions/027_create_totp_auth.py creating totp_credentials (with UNIQUE on user_id, and including last_used_otp VARCHAR(6) nullable and last_used_otp_at TIMESTAMPTZ nullable for replay prevention) and totp_recovery_codes tables per data-model.md
- [ ] T024 [US3] Extend src/voter_api/models/__init__.py to export TOTPCredential and TOTPRecoveryCode
- [ ] T025 [US3] Implement TOTP management service functions in src/voter_api/services/auth_service.py: enroll_totp(session, totp_manager, user) → create/replace pending TOTPCredential → return provisioning URI + QR SVG; confirm_totp(session, totp_manager, user, code) → verify code → set is_verified=True + enrolled_at → generate 10 recovery codes → store hashes in TOTPRecoveryCode rows → return raw codes; disable_totp(session, user_id) → delete TOTPCredential + all TOTPRecoveryCode rows; unlock_totp(session, user_id) → clear locked_until + failed_attempts=0; get_recovery_code_count(session, user_id) → count used_at IS NULL rows; log TOTP enrollment initiation, confirmation/activation, and disable/removal as security events (loguru info) per FR-024
- [ ] T026 [US3] Modify authenticate_user in src/voter_api/services/auth_service.py to enforce TOTP after password verification: if totp_credential.is_verified and totp_code is None → raise MFARequiredError; if locked_until > now() and totp_code is not a valid recovery code → raise TOTPLockedError; for 6-digit codes: (1) replay check — if totp_credential.last_used_otp == totp_code AND totp_credential.last_used_otp_at >= (now() - 30s) → raise MFARequiredError(error_code="mfa_invalid") (FR-020); (2) verify code via TOTPManager.verify_code (increment failed_attempts, set locked_until at TOTP_MAX_ATTEMPTS); (3) on success, set last_used_otp = totp_code and last_used_otp_at = now(); if totp_code length > 6, treat as recovery code (verify hash → mark used_at → bypass lockout → reset failed_attempts); log each TOTP failure (loguru warning), lockout trigger (loguru warning), recovery code use (loguru info), and successful TOTP-authenticated login (loguru info) as security events per FR-024
- [ ] T027 [US3] Modify POST /auth/login in src/voter_api/api/v1/auth.py to accept JSON LoginRequest body (replace OAuth2PasswordRequestForm); map MFARequiredError → HTTP 403 with MFARequiredError schema; map TOTPLockedError → HTTP 429 with TOTPLockedError schema
- [ ] T028 [US3] Add TOTP management endpoints to src/voter_api/api/v1/auth.py: POST /auth/totp/enroll (auth-required, 200, TOTPEnrollmentResponse), POST /auth/totp/confirm (auth-required, 200, TOTPConfirmResponse), DELETE /auth/totp (auth-required, 204), GET /auth/totp/recovery-codes/count (auth-required, 200, TOTPRecoveryCodesCountResponse), DELETE /users/{id}/totp (admin-only, 204), POST /users/{id}/totp/unlock (admin-only, 204)

**Checkpoint**: TOTP enrollment, login enforcement, lockout, recovery code bypass, self-service disable, and admin controls all functional.

---

## Phase 6: User Story 4 — Passkey Registration and Login (Priority: P4)

**Goal**: Users can register passkeys (iPhone Face ID, Bitwarden, etc.) and authenticate without a password via WebAuthn username-first challenge-response flow; existing password login is unaffected.

**Independent Test**: POST /api/v1/auth/passkeys/register/options (auth) → POST /api/v1/auth/passkeys/register/verify with credential + challenge_token → 201; POST /api/v1/auth/passkeys/login/options with username → POST /api/v1/auth/passkeys/login/verify with assertion → 200 TokenResponse.

- [ ] T029 [P] [US4] Create Passkey model in src/voter_api/models/passkey.py using UUIDMixin + Base: user_id (UUID FK → users.id ON DELETE CASCADE, indexed), credential_id (BYTEA NOT NULL UNIQUE, indexed), public_key (BYTEA NOT NULL), sign_count (INT NOT NULL default 0), name (VARCHAR 100, nullable), registered_at (TIMESTAMPTZ default now()), last_used_at (TIMESTAMPTZ nullable); add User.passkeys relationship (cascade delete)
- [ ] T030 [P] [US4] Add passkey schemas to src/voter_api/schemas/auth.py: PasskeyRegistrationOptionsResponse (options: dict, challenge_token: str), PasskeyRegistrationVerifyRequest (credential_response: dict, challenge_token: str, name: str | None maxLength 100), PasskeyResponse (id: UUID, name: str | None, registered_at: datetime, last_used_at: datetime | None), PasskeyRenameRequest (name: str maxLength 100), PasskeyLoginOptionsRequest (username: str), PasskeyLoginOptionsResponse (options: dict, challenge_token: str), PasskeyLoginVerifyRequest (username: str, credential_response: dict, challenge_token: str)
- [ ] T031 [US4] Write Alembic migration alembic/versions/028_create_passkeys.py creating passkeys table with all columns, UNIQUE on credential_id, and indexes on user_id and credential_id per data-model.md
- [ ] T032 [US4] Extend src/voter_api/models/__init__.py to export Passkey
- [ ] T033 [US4] Implement passkey registration service functions in src/voter_api/services/auth_service.py: get_passkey_registration_options(session, passkey_manager, settings, user) → call generate_registration_options → encode challenge JWT via create_passkey_challenge_token → return PasskeyRegistrationOptionsResponse; verify_passkey_registration(session, passkey_manager, settings, user, credential_response, challenge_token, name) → decode JWT → verify registration → create Passkey row (if name is None, default to ISO timestamp of registered_at); list_passkeys(session, user_id) → list of Passkey rows; rename_passkey(session, user_id, passkey_id, name) → update name; delete_passkey(session, user_id, passkey_id) → delete row; log passkey registration and removal as security events (loguru info) per FR-030
- [ ] T034 [US4] Implement passkey login service functions in src/voter_api/services/auth_service.py: get_passkey_login_options(session, passkey_manager, settings, username) → load user + passkeys → generate_authentication_options → encode challenge JWT → return PasskeyLoginOptionsResponse; verify_passkey_login(session, passkey_manager, settings, username, credential_response, challenge_token) → decode JWT → look up Passkey by credential_id → verify_authentication → update sign_count + last_used_at → call generate_tokens → return TokenResponse; log successful passkey authentication (loguru info) and failed assertion (loguru warning) as security events per FR-030
- [ ] T035 [US4] Add all 7 passkey endpoints to src/voter_api/api/v1/auth.py: POST /auth/passkeys/register/options (auth-required, 200), POST /auth/passkeys/register/verify (auth-required, 201), GET /auth/passkeys (auth-required, 200 list[PasskeyResponse]), PATCH /auth/passkeys/{id} (auth-required, 200), DELETE /auth/passkeys/{id} (auth-required, 204), POST /auth/passkeys/login/options (public, 200), POST /auth/passkeys/login/verify (public, 200)

**Checkpoint**: Full passkey registration and login flow functional — register, list, rename, delete passkeys; login via passkey and receive valid tokens.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Test coverage for all new libraries and endpoints; E2E smoke tests; lint and documentation.

- [ ] T039 Extend tests/integration/test_api/test_auth.py with integration tests for all new endpoints: full password reset flow (request → confirm → login), full invite flow (admin create → invitee accept), TOTP enrollment → confirm → login with valid code (200) → login without code (403) → login with wrong code × 5 → lockout (429) → recovery code bypass, passkey registration and login flows (mocked py_webauthn); update any existing test_login tests in this file to use JSON body {"username": ..., "password": ...} instead of OAuth2PasswordRequestForm — breaking change from T027; assert that passkey login for a TOTP-enabled account (is_verified=True) returns 200 tokens without requiring a totp_code — passkey path must bypass TOTP enforcement per spec edge case
- [ ] T040 Extend tests/e2e/conftest.py to add TOTP_USER_ID UUID constant, seed a TOTP-enrolled user fixture, seed a pending invite fixture, and configure MailgunMailer as a mock/no-op for E2E test runs
- [ ] T041 [P] Extend tests/e2e/test_smoke.py TestAuth class with smoke tests: password reset request (202), invite create by admin (201) + accept (201), TOTP login with valid code (200), TOTP login without code (403 mfa_required), passkey registration options (200), passkey login options (200); update any existing TestAuth login smoke tests that POST form-data to /auth/login to use JSON body instead; passkey login verify for a TOTP-enabled user returns 200 tokens (TOTP bypass confirmed)
- [ ] T044 [P] Update specs/009-enhanced-auth/contracts/openapi.yaml with all 17 new/modified endpoints from plan.md endpoint summary table; include request/response schemas for PasswordResetRequest, PasswordResetConfirm, InviteCreate, InviteResponse, InviteAccept, TOTPEnrollmentResponse, TOTPConfirmResponse, PasskeyResponse, PasskeyLoginVerifyRequest, and TokenResponse; mark POST /auth/login as modified (JSON body, optional totp_code field)
- [ ] T045 [depends on T044] Extend contract tests in tests/contract/ to validate all new request/response schemas in src/voter_api/schemas/auth.py against the updated specs/009-enhanced-auth/contracts/openapi.yaml; at minimum cover LoginRequest, PasswordResetRequest, InviteCreate, TOTPEnrollmentResponse, and PasskeyResponse
- [ ] T042 Run full lint and test suite: `uv run ruff check . && uv run ruff format --check . && uv run pytest --cov=voter_api --cov-report=term-missing`; confirm zero lint violations and ≥ 90% coverage threshold
- [ ] T043 Update CLAUDE.md Recent Changes section with 009-enhanced-auth summary: new libs (mailer, totp, passkey), new models (PasswordResetToken, UserInvite, TOTPCredential, TOTPRecoveryCode, Passkey), new migrations (025–028), 21 new/modified endpoints, login format change (form-data → JSON)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — **BLOCKS all user story phases**
- **Phase 3 (US1 — Password Reset)**: Depends on Phase 2 (mailer lib); no other story dependencies
- **Phase 4 (US2 — Invites)**: Depends on Phase 2 (mailer lib); shares auth_tokens.py with Phase 3 — recommended after Phase 3 complete to avoid file conflicts
- **Phase 5 (US3 — TOTP)**: Depends on Phase 2 (totp lib); independent of US1/US2
- **Phase 6 (US4 — Passkeys)**: Depends on Phase 2 (passkey lib + T008 JWT helpers); independent of US1–US3
- **Phase 7 (Polish)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (P1)**: Can start immediately after Phase 2 — no other story dependencies
- **US2 (P2)**: Recommended after US1 completes (both use auth_tokens.py); can be parallelized with care
- **US3 (P3)**: Fully independent of US1/US2 — can run in parallel once Phase 2 is complete
- **US4 (P4)**: Fully independent of US1–US3 — can run in parallel once Phase 2 is complete

### Within Each User Story

- Model + Schemas can be written in parallel (different files)
- Migration must follow model (needs schema to be defined)
- models/__init__.py export must follow model creation
- Service functions depend on model + schemas
- Endpoints depend on service functions

---

## Parallel Execution Examples

### Phase 2 (Foundational) — All tasks in parallel

```bash
Task T004: "Implement src/voter_api/lib/mailer/ (MailgunMailer)"
Task T005: "Create src/voter_api/lib/mailer/templates/ (password_reset.html, invite.html)"
Task T006: "Implement src/voter_api/lib/totp/ (TOTPManager)"
Task T007: "Implement src/voter_api/lib/passkey/ (PasskeyManager)"
Task T008: "Add passkey JWT helpers to src/voter_api/core/security.py"
Task T036: "Unit tests for src/voter_api/lib/mailer/"
Task T037: "Unit tests for src/voter_api/lib/totp/"
Task T038: "Unit tests for src/voter_api/lib/passkey/"
```

### Phase 3 (US1) — Parallel start then sequential

```bash
# Launch in parallel:
Task T009: "Create PasswordResetToken model in src/voter_api/models/auth_tokens.py"
Task T010: "Add password reset schemas to src/voter_api/schemas/auth.py"

# Then sequentially:
Task T011: "Write Alembic migration 025"
Task T012: "Extend src/voter_api/models/__init__.py"
Task T013: "Implement service functions in src/voter_api/services/auth_service.py"
Task T014: "Add endpoints to src/voter_api/api/v1/auth.py"
```

### Phase 7 (Polish) — Parallel tasks

```bash
# Launch in parallel:
Task T039: "Integration tests for all new endpoints (includes login format migration)"
Task T041: "E2E smoke tests (includes login format migration + TOTP bypass assertion)"
Task T044: "Update specs/009-enhanced-auth/contracts/openapi.yaml"
Task T040: "Extend tests/e2e/conftest.py"
# Then sequentially (requires T044 complete):
Task T045: "Extend tests/contract/ for new schemas"
```

---

## Implementation Strategy

### MVP First (US1 — Password Reset Only)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundational libs + unit tests (T004–T008, T036–T038)
3. Complete Phase 3: US1 Password Reset (T009–T014)
4. **STOP and VALIDATE**: Full reset flow works end-to-end
5. Deploy/demo if ready

### Incremental Delivery

1. Phase 1 + Phase 2 → Foundation ready
2. Phase 3 (US1) → Password reset live → Deploy (MVP)
3. Phase 4 (US2) → User invites live → Deploy
4. Phase 5 (US3) → TOTP 2FA live → Deploy
5. Phase 6 (US4) → Passkey login live → Deploy
6. Phase 7 → Tests, polish, and documentation complete

### Parallel Team Strategy

After Phase 2 completes:
- Developer A: US1 (Password Reset) — Phase 3
- Developer B: US3 (TOTP) — Phase 5, fully independent
- Developer C: US4 (Passkeys) — Phase 6, fully independent
- Developer D: US2 (Invites) — Phase 4, after Developer A creates auth_tokens.py

---

## Notes

- **[P] tasks** use different files with no dependencies on incomplete tasks in the same phase
- **[Story] labels** map each task to its user story for independent delivery
- **Login breaking change**: POST /auth/login changes from OAuth2 form-data to JSON body — see research.md Decision 7; existing API clients must be updated
- **TOTP encryption**: `TOTP_SECRET_ENCRYPTION_KEY` Fernet key is required for all TOTP operations; generate with `uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- **Email fail-fast**: MailgunMailer delivery failure → no token/invite row persisted; caller must re-initiate
- **Passkey challenges are stateless**: stored in short-lived JWTs (5-min TTL); no database table needed (see research.md Decision 6)
- **Commit cadence**: commit to git after each phase per plan.md suggested commit messages
- **Lint before each commit**: `uv run ruff check . && uv run ruff format .`
