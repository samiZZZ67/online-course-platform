# Authentication API Documentation

SkillForge now exposes authentication documentation in both machine-readable and browser-friendly formats.

## Live Documentation URLs

- OpenAPI JSON: `http://localhost:3000/api/docs/openapi.json`
- OpenAPI YAML: `http://localhost:3000/api/docs/openapi.yaml`
- Swagger UI: `http://localhost:3000/api/docs/swagger/`
- ReDoc: `http://localhost:3000/api/docs/redoc/`

## Covered API Areas

- Registration
- Login
- JWT refresh
- Logout
- Current-user lookup
- Email verification
- Password reset
- OAuth start payload
- Two-factor verification
- Profile management
- Password change
- Admin user management

## Authentication Model

- Access tokens use JWT bearer auth and currently live for `15 minutes`.
- Refresh tokens rotate on every refresh and are stored in the `HttpOnly` `skillforge_session` cookie.
- Instructor and admin accounts require `email_otp` two-factor verification at login.
- Student accounts can opt into `email_otp` through the profile API.

## Role and Permission Summary

- `student`: can learn, enroll, track progress, and manage their own profile.
- `instructor`: inherits student capabilities and can create/manage course content.
- `admin`: can manage users, suspend/verify accounts, and change roles.

## Alias Endpoints

The frontend/mobile aliases map to the same backend logic:

- `/api/register` -> `/api/auth/signup`
- `/api/login` -> `/api/auth/login`
- `/api/refresh-token` -> `/api/auth/refresh`
- `/api/forgot-password` -> `/api/auth/password/reset-request`
- `/api/reset-password` -> `/api/auth/password/reset-confirm`
- `/api/verify-email` -> `/api/auth/verify-email/request|confirm`
- `/api/logout` -> `/api/auth/logout`
- `/api/2fa/verify` -> `/api/auth/2fa/verify`

## Development Notes

- Verification tokens, reset tokens, and OTP codes are only exposed in local development and tests.
- Production clients should rely on email delivery and the documented response contracts instead of dev-only token fields.
