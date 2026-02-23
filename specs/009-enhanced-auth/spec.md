# Feature Specification: Enhanced Authentication

**Feature Branch**: `009-enhanced-auth`
**Created**: 2026-02-22
**Status**: Draft
**Input**: User description: "We need a way to have user invites, password resets, TOTP, and passkey logins (iphone, bitwarden, etc)"

## Clarifications

### Session 2026-02-22

- Q: How does the TOTP two-step login work at the API level? → A: Single combined call — a TOTP-enabled user submits username, password, and TOTP code together in one login request; if the TOTP field is absent on a TOTP-enabled account, the login returns a specific error indicating MFA is required.
- Q: Should the system enforce rate limiting or brute force protection on auth endpoints? → A: Targeted limits — lock a TOTP-enabled account after N consecutive failed MFA attempts; throttle password reset requests to 1 per email per 5 minutes to prevent email bombing.
- Q: What should happen when email delivery fails for an invite or password reset? → A: Fail fast — if email delivery fails, the API call returns an error; the token is not persisted and the operation must be re-initiated by the caller.
- Q: How does passkey login identify the account — username required upfront, or passkey-only discovery? → A: Username-first — client sends username to receive a challenge; passkey signs it; account is identified by username before the ceremony begins.
- Q: Can a TOTP recovery code bypass an active lockout? → A: Yes — a valid recovery code is accepted even during a TOTP lockout, restoring access immediately and consuming the recovery code.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Password Self-Service Reset (Priority: P1)

An authenticated user has forgotten their password and cannot log in. They submit their email address to request a reset, receive a secure time-limited email link, click it, and set a new password. The old password no longer works after the reset completes.

**Why this priority**: Password reset is the most foundational self-service auth feature. Without it, every forgotten password requires admin intervention, creating support burden and blocking user access.

**Independent Test**: Can be fully tested by requesting a reset for a known email, following the secure token flow, and confirming login with the new password — delivering a fully working account recovery flow.

**Acceptance Scenarios**:

1. **Given** a user account with a verified email, **When** the user submits that email to request a reset, **Then** a reset email is sent within 2 minutes containing a single-use, time-limited link.
2. **Given** a valid reset link, **When** the user submits a new password, **Then** the password is updated and the link is permanently invalidated.
3. **Given** an invalid or expired reset link, **When** used to attempt a reset, **Then** the system rejects the attempt with a clear error.
4. **Given** an email address not associated with any account, **When** submitted for password reset, **Then** the system responds identically to a valid submission (preventing email enumeration).
5. **Given** a successful password reset, **When** the previous password is used to log in, **Then** login fails.
6. **Given** two reset requests submitted in quick succession for the same account, **When** the first link is later used, **Then** it is rejected because the second request invalidated it.

---

### User Story 2 - Admin-Initiated User Invites (Priority: P2)

An admin wants to onboard a new team member without setting a password on their behalf. The admin sends an invitation to the new user's email with a designated role. The invitee receives the email, clicks the link, chooses their own username and password, and activates their account.

**Why this priority**: Invites improve the security posture of user onboarding — no passwords need to be shared out-of-band — and allow the new user to complete registration themselves.

**Independent Test**: Can be fully tested by having an admin create an invite, following the activation link, and confirming a functioning account is created with the specified role.

**Acceptance Scenarios**:

1. **Given** an admin is authenticated, **When** they submit an invite with an email and role, **Then** an invitation email is sent to that address with a time-limited activation link.
2. **Given** a valid invite link, **When** the invitee submits a username and password, **Then** an active user account is created with the specified role.
3. **Given** an invite link that has already been accepted, **When** accessed again, **Then** the system rejects it.
4. **Given** an invite link older than 7 days, **When** accessed, **Then** the system rejects it and the admin can re-send a new invite.
5. **Given** an invite for an email already associated with an existing account, **When** the admin submits it, **Then** the system rejects it with a clear error.
6. **Given** pending invitations, **When** an admin lists them, **Then** all unused, unexpired invites are visible with re-send and cancel options.

---

### User Story 3 - TOTP Two-Factor Authentication (Priority: P3)

A user wants to add extra security to their account using an authenticator app (Google Authenticator, Authy, 1Password, etc.). They enroll by scanning a QR code, then on each subsequent login must provide their password and a current 6-digit time-based code from their app. They also receive one-time backup recovery codes for emergencies.

**Why this priority**: TOTP provides significant security uplift for accounts with elevated access (admin/analyst). It defends against credential theft without requiring hardware or browser-specific features.

**Independent Test**: Can be fully tested by enrolling TOTP on an account, confirming that subsequent logins require both password and OTP, and confirming a valid code grants access while an invalid code does not.

**Acceptance Scenarios**:

1. **Given** an authenticated user, **When** they initiate TOTP enrollment, **Then** they receive a provisioning URI and QR code compatible with standard authenticator apps.
2. **Given** a user completing enrollment, **When** they submit a valid 6-digit code from their authenticator app, **Then** TOTP is activated and exactly 10 single-use recovery codes are issued to the user.
3. **Given** a TOTP-enabled account, **When** the user submits username and password without a TOTP code, **Then** the login is rejected with an error indicating that a TOTP code is required.
3b. **Given** a TOTP-enabled account, **When** the user submits username, password, and a valid TOTP code in a single request, **Then** access tokens are issued.
4. **Given** a TOTP-enabled account, **When** the user submits an incorrect TOTP code, **Then** login is denied and the failure is logged.
5. **Given** a TOTP-enabled user who has lost access to their authenticator app, **When** they use a valid recovery code, **Then** access is granted and that code is permanently consumed.
6. **Given** a TOTP-enabled user, **When** they disable TOTP from their account, **Then** subsequent logins only require username and password.
7. **Given** any account, **When** an admin disables TOTP for that user, **Then** the user can log in with only their password (admin-level account recovery).

---

### User Story 4 - Passkey Registration and Login (Priority: P4)

A user wants to log in using a passkey stored in their iPhone Face ID, Bitwarden, or another compatible credential manager. They register their passkey from a client application, and on subsequent visits can authenticate without typing a password. Passkeys are a standalone login alternative — users choose either passkey or password at login time. Existing password login continues to function independently; registering a passkey does not disable it.

**Why this priority**: Passkeys provide phishing-resistant, passwordless authentication broadly supported across iOS, Android, and password managers like Bitwarden. They represent the long-term direction of secure authentication.

**Independent Test**: Can be fully tested by registering a passkey, then authenticating exclusively via the passkey challenge without providing a password, and receiving valid session tokens.

**Acceptance Scenarios**:

1. **Given** an authenticated user, **When** they register a passkey from a compatible device or manager, **Then** the passkey is associated with their account and usable for future logins.
2. **Given** a registered passkey, **When** the user initiates a passkey login for their account, **Then** the system issues a cryptographic challenge that the passkey must sign.
3. **Given** a valid signed passkey assertion, **When** verified by the system, **Then** the user receives valid session tokens.
4. **Given** a user with multiple registered passkeys, **When** they manage their account, **Then** they can view all passkeys (with names and last-used dates), rename them, and remove individual ones.
5. **Given** a passkey that is no longer accessible (device lost), **When** the user logs in via password, **Then** they can remove the inaccessible passkey from their account.

---

### Edge Cases

- What happens if account is deactivated while a valid reset or invite token exists? Token should be invalidated when the account is deactivated.
- What happens when a TOTP-enabled user also has a passkey? Passkey authentication should satisfy the full login requirement without prompting for TOTP.
- What happens if email delivery fails for an invite or password reset? The API call fails immediately with an error; no token is persisted. The admin or user must re-initiate the request. Delivery failures are logged as errors.
- What happens if a user attempts TOTP login with a code that is currently valid but was already used in this window? The attempt is rejected (replay prevention).
- What happens if an admin resends an invite that was already pending? A new token is issued and the old one is invalidated.
- What if the user has no recovery codes left and also lost their authenticator? An admin can disable TOTP via the admin endpoint.
- What happens when a TOTP account is locked after 5 failed attempts? The system returns a lockout error. A valid recovery code bypasses the lockout immediately. Otherwise, the lock expires after 15 minutes. Admins can also clear it manually.
- What happens if a password reset is requested again within 5 minutes of the previous request? The system silently accepts but does not send another email (returns the same enumeration-safe response).

## Requirements *(mandatory)*

### Functional Requirements

#### Password Reset

- **FR-001**: System MUST provide an unauthenticated endpoint for users to request a password reset by submitting their email address.
- **FR-002**: System MUST send a time-limited, single-use reset link to the submitted email within 2 minutes.
- **FR-003**: System MUST reject reset tokens older than 24 hours or already used.
- **FR-004**: System MUST respond identically whether the submitted email exists or not, preventing account enumeration.
- **FR-005**: System MUST invalidate any prior unused reset tokens for an account when a new reset is requested.
- **FR-006**: System MUST invalidate a reset token immediately upon successful use.
- **FR-007**: System MUST log all password reset requests and completions as security events.
- **FR-007a**: System MUST reject password reset requests for the same email address submitted more than once within any 5-minute window, returning the same response as a valid request (enumeration-safe throttling).

#### User Invites

- **FR-008**: Admins MUST be able to create an invitation by specifying an email address and target role.
- **FR-009**: System MUST send an invitation email with a time-limited activation link to the specified address.
- **FR-010**: System MUST reject invite tokens older than 7 days or already accepted.
- **FR-011**: Invitees MUST be able to choose their own username and password when accepting an invitation.
- **FR-012**: System MUST reject invitations for email addresses already associated with an existing account.
- **FR-013**: Admins MUST be able to list all pending (unused, unexpired) invitations.
- **FR-014**: Admins MUST be able to cancel a pending invitation or re-send a new one.
- **FR-015**: System MUST automatically treat invitations as expired after 7 days (implemented via query-time filtering on `expires_at`; no background job or explicit status column update required).

#### TOTP Two-Factor Authentication

- **FR-016**: Authenticated users MUST be able to initiate TOTP enrollment and receive a provisioning URI compatible with standard authenticator apps.
- **FR-017**: TOTP enrollment MUST be confirmed by the user submitting a valid code before TOTP is activated on the account.
- **FR-018**: Upon TOTP activation, system MUST issue exactly 10 single-use recovery codes displayed to the user once.
- **FR-019**: For TOTP-enabled accounts, the login request MUST include username, password, and TOTP code (or recovery code) in a single combined call. A login request that omits the TOTP field on a TOTP-enabled account MUST be rejected with a specific error indicating MFA is required (not a generic credential failure).
- **FR-020**: System MUST reject any TOTP code that has already been used within its validity window (replay prevention).
- **FR-021**: Each recovery code MUST be permanently invalidated after a single use.
- **FR-022**: Authenticated users MUST be able to disable TOTP on their own account.
- **FR-023**: Admins MUST be able to disable TOTP for any user account (account recovery).
- **FR-024**: System MUST log all TOTP enrollment, successful use, failed attempts, and removal events.
- **FR-024a**: System MUST temporarily lock TOTP verification for an account after 5 consecutive failed MFA attempts. The lockout duration is 15 minutes. Admins can clear a lockout manually. A valid recovery code MUST be accepted even during an active lockout, bypassing it and consuming the recovery code.

#### Passkey Login

- **FR-025**: Authenticated users MUST be able to register one or more passkeys on their account.
- **FR-026**: Passkey login MUST be username-first: the client submits the username to receive a server-generated challenge, the passkey signs the challenge, and the client submits the signed assertion to complete authentication and receive session tokens.
- **FR-027**: Users MUST be able to list all registered passkeys associated with their account (name, registered date, last used date).
- **FR-028**: Users MUST be able to remove any individual passkey from their account.
- **FR-028a**: Users MUST be able to rename any registered passkey on their account.
- **FR-029**: Passkey login MUST be available as a first-class authentication path, not requiring a password submission.
- **FR-030**: System MUST log all passkey registration, authentication, and removal events.

#### Email Delivery

- **FR-031**: System MUST support a configurable email delivery provider for sending invite and password reset emails.
- **FR-031a**: If email delivery fails, the system MUST return an error to the caller immediately and MUST NOT persist the invite or reset token. The failure MUST be logged. The caller must re-initiate the request.
- **FR-032**: All authentication emails MUST include the application name, a clear call-to-action, and the expiry time of the link.

### Key Entities

- **PasswordResetToken**: A single-use, time-limited token tied to a user account. Attributes: hashed token value, user association, expiry timestamp, used-at timestamp.
- **UserInvite**: A pending invitation for a new user. Attributes: hashed invite token, target email, assigned role, invited-by (admin user), expiry timestamp, accepted-at timestamp.
- **TOTPCredential**: A TOTP secret bound to a user account. Attributes: encrypted shared secret, enrollment-verified flag, enrolled-at timestamp.
- **TOTPRecoveryCode**: A single-use backup code for TOTP-locked accounts. Attributes: hashed code value, used-at timestamp.
- **Passkey**: A registered passkey credential on a user account. Attributes: credential identifier, public key material, user-assigned name, registered-at timestamp, last-used-at timestamp, usage counter (for cloning detection).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can complete the full password reset flow (request → receive email → set new password → log in) without any admin involvement.
- **SC-002**: New users can complete account activation from an invite link (receive email → set credentials → log in) in under 3 minutes.
- **SC-003**: TOTP enrollment completes from initiation to first successful two-factor login in under 2 minutes.
- **SC-004**: Admin support requests for routine user onboarding and password resets are eliminated; no admin action is required for these flows.
- **SC-005**: All authentication events (reset requests, invite acceptances, TOTP use, passkey logins) are individually auditable in system logs.
- **SC-006**: A stolen password alone is insufficient to access any account that has TOTP or a passkey registered.
- **SC-007**: Users can register a passkey from any compatible device or credential manager without requiring application code changes.

## Scope

### In Scope

- Password reset via emailed token (unauthenticated self-service flow)
- Admin-initiated user invitations with role assignment
- TOTP enrollment, login enforcement, recovery codes, and admin reset
- Passkey registration and passkey-based login
- Configurable email delivery for invites and password resets
- Audit logging for all new authentication events
- User account management: list/remove passkeys, enable/disable TOTP

### Out of Scope

- Social or federated login (e.g., "Sign in with Google") — separate feature if needed
- SMS-based one-time passwords
- Admin-enforced TOTP enrollment policies (admin can disable, but cannot force enrollment in this version)
- Email verification for existing accounts (all new users arrive via invite flow)

## Assumptions

- The application will add an email delivery dependency. The specific provider (SMTP, transactional API) is configurable via environment variables and is not prescribed here.
- Passkey registration and authentication ceremonies are initiated from a client application (browser or mobile app); this feature defines the server-side API endpoints, not the client UI.
- TOTP codes follow the industry-standard time-based OTP algorithm (30-second windows, 6-digit codes).
- Recovery codes are alphanumeric strings of at least 16 characters, shown to the user exactly once at enrollment.
- Token and recovery code values stored in the database are hashed, not stored in plaintext, to limit exposure in the event of a database breach.
- Existing users created before this feature is deployed continue to log in with their current password-only flow; TOTP and passkeys are opt-in.
- Passkeys are identified by a user-assigned name for account management purposes (defaulting to registration timestamp if no name is provided).

## Dependencies

- Email delivery service (new capability required): needed for password reset and user invite flows.
- New database tables required for: password reset tokens, user invites, TOTP credentials, TOTP recovery codes, and passkeys.
- No changes to existing role definitions (admin/analyst/viewer) are required.
