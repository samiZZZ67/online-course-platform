# SkillForge Authentication Architecture

## Purpose

This document defines the target authentication architecture for the Django backend before we change the implementation.

It is designed for the current project constraints:

- `index.html` must remain unchanged on disk.
- The frontend is a same-origin SPA served by Django.
- Authentication should move from the current custom session token model to JWT-based auth.
- The design must support refresh token rotation.
- Django admin must continue to work normally.

## Final Decisions

### Login identifier

- Use `email` as the only login identifier.
- Do not support username-based login in the product UI or API.
- Normalize email to lowercase and trim whitespace before lookup and storage.
- Enforce a unique email at the database level.

### JWT strategy

- Use short-lived access JWTs for API authorization.
- Use long-lived refresh JWTs only for session continuation.
- Access tokens are bearer tokens.
- Refresh tokens rotate on every successful refresh.
- Refresh tokens are stateful on the server side even though they are JWTs.

This gives us fast stateless authorization for normal API requests while still allowing revocation, logout, device tracking, and refresh-token reuse detection.

### Access token duration

- Access token TTL: `15 minutes`

Reasoning:

- Short enough to reduce exposure if leaked.
- Long enough to avoid constant refresh churn during active course usage.

### Refresh token duration

- Refresh token inactivity TTL: `14 days`
- Maximum session lifetime: `30 days`

Reasoning:

- Learners can stay signed in across normal use.
- Rotation plus family revocation keeps this safer than a single long-lived token.
- The absolute session cap prevents endless session extension.

### Role architecture

- Use role-based permissions.
- Keep a coarse `role` field on the user model.
- Use Django groups and permissions for actual authorization checks.

Initial roles:

- `student`
- `instructor`
- `admin`
- `support`

Rule:

- Never gate sensitive actions by role string alone.
- Use Django permissions such as `academy.add_course`, `academy.change_course`, `academy.view_authauditlog`, and custom permissions where needed.

### Verification workflow

- New accounts require email verification.
- Signup can return a session immediately, but the account is marked unverified.
- Unverified users may access low-risk endpoints only.
- Verified email is required before actions tied to ownership or money.

That means verification is required before:

- enrollment or purchase completion
- gifting
- instructor onboarding
- passwordless recovery flows beyond email ownership checks

### Security policies

- Refresh token stored in an `HttpOnly`, `Secure`, `SameSite=Lax` cookie.
- Access token kept in memory on the frontend runtime bridge, not in `localStorage`.
- CSRF protection stays enabled for cookie-backed auth endpoints.
- Login, refresh, reset, and verification resend endpoints must be rate-limited.
- Refresh token reuse revokes the entire token family.
- Password reset revokes all refresh tokens for the user.
- Changing password revokes all refresh tokens issued before the password change.
- Production CORS must be same-origin only. Remove wildcard `Access-Control-Allow-Origin: *`.
- Audit authentication events in the database.

## Recommended Django Structure

Create a dedicated `accounts` app for authentication concerns rather than expanding `academy` further.

Recommended files:

- `accounts/models.py`
- `accounts/admin.py`
- `accounts/urls.py`
- `accounts/views.py`
- `accounts/services.py`
- `accounts/authentication.py`
- `accounts/permissions.py`
- `accounts/tests.py`

Project routing:

- `backend/urls.py` includes `accounts.urls` under `/api/auth/`
- `academy` keeps domain endpoints like courses, enrollments, notes, wishlist, and instructor features

## User Model Decision

### Recommended model

Introduce a custom user model now:

- `accounts.User(AbstractBaseUser, PermissionsMixin)`

The detailed user-model spec lives in `docs/custom-user-model.md`.

Recommended fields:

- `email`
- `first_name`
- `last_name`
- `role`
- `is_active`
- `is_staff`
- `is_superuser`
- `email_verified_at`
- `last_password_changed_at`
- `created_at`
- `updated_at`

Recommended settings:

- `AUTH_USER_MODEL = "accounts.User"`
- `USERNAME_FIELD = "email"`
- `REQUIRED_FIELDS = []`

### Important warning

Changing `AUTH_USER_MODEL` becomes painful after the project accumulates more migrations and data.

Because this project is still early, the best time to switch to a custom user model is now, before more auth features are built on top of Django's default `User`.

## Token Model

### Access token

Use a signed JWT with claims like:

- `sub`: user id
- `email`
- `role`
- `type`: `access`
- `jti`
- `iat`
- `exp`
- `ver`: token version or auth version

Recommended signing:

- `HS256` for the current single Django app deployment

Implementation note:

- Keep token creation and verification behind a service layer so we can move to `RS256` later if other services ever need independent verification.

### Refresh token

Use a signed JWT with claims like:

- `sub`: user id
- `type`: `refresh`
- `jti`
- `family`
- `iat`
- `exp`
- `ver`

The refresh token must also map to a database record so rotation and revocation are enforced server-side.

### Refresh token persistence

Replace the current `ApiSession` model with a model focused on rotating refresh tokens.

Recommended model:

- `accounts.RefreshToken`

Recommended fields:

- `user`
- `jti`
- `family_id`
- `token_hash`
- `expires_at`
- `last_used_at`
- `rotated_at`
- `revoked_at`
- `reuse_detected_at`
- `replaced_by`
- `created_ip`
- `created_user_agent`
- `created_at`

Rules:

- Store a hash of the refresh token, not the raw token.
- One refresh request invalidates the current token and issues a new one.
- If an already-rotated token is seen again, mark it as reuse and revoke the whole family.
- `logout` revokes the current token.
- `logout all` revokes every active token family for that user.

## Verification and Recovery Models

Recommended model:

- `accounts.EmailVerificationToken`

Recommended fields:

- `user`
- `token_hash`
- `expires_at`
- `consumed_at`
- `created_at`

Recommended model:

- `accounts.PasswordResetToken`

Recommended fields:

- `user`
- `token_hash`
- `expires_at`
- `consumed_at`
- `created_at`

Rules:

- Tokens are single-use.
- Raw tokens are never stored directly.
- Verification TTL: `24 hours`
- Password reset TTL: `30 minutes`

## Role and Permission Design

### Role meanings

- `student`: default learner account
- `instructor`: can create and manage own courses
- `admin`: full platform access and Django admin access
- `support`: read-heavy internal role with limited operational actions

### Permission strategy

Use Django permissions for enforcement.

Examples:

- students: authenticated access to their own enrollments, notes, wishlist, gifts, notifications
- instructors: `academy.add_course`, `academy.change_course` for owned courses, custom permission for thumbnail updates and draft submission
- admins: full `academy` permissions plus Django staff access
- support: custom read-only or limited-action permissions without full staff privileges unless explicitly needed

### Ownership checks

Use both permission checks and ownership checks.

Examples:

- instructors can update only courses where `created_by == request.user`
- students can read only notes and enrollments tied to their own user id or verified email

## Verification Workflow

### Signup flow

1. User submits `email`, `password`, `firstName`, and `lastName`.
2. Backend creates the user with `email_verified_at = null`.
3. Backend issues access and refresh tokens.
4. Backend creates an email verification token and sends a verification email.
5. Response includes `verificationRequired: true` plus the authenticated user payload and access token.
6. Refresh token is set in the secure cookie.

### Verify email flow

1. User clicks the verification link or submits the verification token.
2. Backend validates the token hash and expiry.
3. Backend sets `email_verified_at`.
4. Backend deletes or consumes outstanding verification tokens.
5. Backend optionally issues a fresh access token with updated claims.

### Resend verification flow

1. Authenticated unverified user requests resend.
2. Backend rate-limits the request.
3. Backend invalidates older unused verification tokens if desired.
4. Backend sends a fresh verification email.

### Login flow

1. User logs in with `email` and `password`.
2. Backend verifies password and account status.
3. Backend issues access token plus rotating refresh token.
4. Response includes `verified: true|false`.
5. Unverified users can still sign in but remain restricted.

### Password reset flow

1. User requests reset by email.
2. Backend creates a single-use reset token.
3. Backend emails the reset link.
4. User submits token and new password.
5. Backend updates password and `last_password_changed_at`.
6. Backend revokes all refresh tokens for that user.
7. Backend optionally signs the user in with fresh tokens.

## API Contract

Keep the current frontend-friendly routes where possible.

Recommended auth endpoints:

- `POST /api/auth/signup`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `GET /api/auth/me`
- `POST /api/auth/logout`
- `POST /api/auth/logout-all`
- `POST /api/auth/verify-email/request`
- `POST /api/auth/verify-email/confirm`
- `POST /api/auth/password/reset-request`
- `POST /api/auth/password/reset-confirm`

Optional future endpoints:

- `POST /api/auth/oauth/start`
- `GET /api/auth/oauth/callback`

## Frontend Token Handling

Because `index.html` cannot be modified on disk, the runtime auth bridge remains the right place to manage client auth state.

Frontend rules:

- Keep the access token in memory only.
- Send `Authorization: Bearer <access>` for protected API requests.
- Store the refresh token only in the secure cookie.
- On page load, the runtime bridge calls `/api/auth/refresh` or `/api/auth/me` to restore auth state.
- On `401` from an API request, attempt one refresh, then retry once.
- If refresh fails, clear local auth state and show the signed-out UI.

## Security Controls

### Password policy

Use Django password validators with the current frontend contract in mind.

Recommended baseline:

- minimum length `8` for compatibility with the existing UI
- reject common passwords
- reject numeric-only passwords
- encourage stronger passwords in UI copy

If the frontend validation is updated later, raise the minimum to `12`.

### Rate limiting

Rate-limit:

- login attempts by IP and normalized email
- signup attempts by IP
- password reset requests by IP and email
- verification resend by user and IP
- refresh endpoint by token family and IP

### Audit logging

Keep and extend `AuthAuditLog`.

Track:

- signup
- login success
- login failure
- logout
- logout all
- refresh success
- refresh reuse detected
- password reset requested
- password reset completed
- verification email sent
- email verified

### Cookie policy

Use these refresh-cookie settings in production:

- `HttpOnly=True`
- `Secure=True`
- `SameSite=Lax`
- `Path=/api/auth/`

### CSRF policy

Keep Django CSRF protection enabled.

Apply CSRF checks to endpoints that rely on cookies:

- signup
- login
- refresh
- logout
- logout all
- verify-email request
- password-reset confirm when session cookies are involved

The runtime bridge can read the CSRF cookie and send `X-CSRFToken` without changing `index.html`.

### CORS policy

- Development can stay permissive if needed.
- Production should allow only the deployed frontend origin.
- Avoid wildcard CORS with credentialed requests.

## Migration From Current Implementation

Current state:

- default Django `User`
- `academy.ApiSession`
- custom token cookie named `skillforge_session`
- auth views in `academy/views.py`

Target state:

- custom `accounts.User`
- rotating refresh-token persistence
- access JWT bearer auth
- auth endpoints moved into `accounts`

Recommended order:

1. Create `accounts` app.
2. Introduce custom user model and switch `AUTH_USER_MODEL`.
3. Add refresh token, verification token, and reset token models.
4. Build token services and auth utilities.
5. Replace `ApiSession` usage in auth endpoints.
6. Update runtime auth bridge to use access JWT plus refresh endpoint.
7. Add role and permission enforcement to protected routes.
8. Remove legacy session-token code after tests pass.

## What Must Stay Compatible

- `index.html` stays unchanged on disk.
- `/admin/` continues to use Django admin auth normally.
- Existing frontend flows for signup, login, logout, and current-user lookup keep working with minimal contract changes.
- Existing domain endpoints can continue to call a helper such as `get_authenticated_user(request)`.

## Summary

The recommended architecture is:

- email-only login
- custom Django user model
- short-lived access JWTs
- rotating refresh JWTs stored in secure cookies
- server-side refresh token tracking with reuse detection
- role-based authorization using Django permissions
- email verification before high-trust actions
- strong audit, CSRF, rate limiting, and logout-all support

This is the cleanest path from the current prototype auth model to a production-ready Django authentication system without touching `index.html`.
