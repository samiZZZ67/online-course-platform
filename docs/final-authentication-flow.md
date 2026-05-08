# Final Authentication Flow

The SkillForge authentication phase is now complete enough to stabilize before course-management work begins.

## Runtime Flow

1. User registers with email, password, and a public role (`student` or `instructor`).
2. The custom `accounts.User` record is created.
3. A role-specific profile is auto-created through Django signals.
4. A verification email token is generated and sent.
5. The user verifies the account.
6. The user logs in with email and password.
7. If the account requires 2FA, an email OTP challenge is issued and verified.
8. Django returns a short-lived JWT access token plus a rotating refresh-token cookie.
9. Protected APIs validate the JWT and enforce role-based permissions.
10. Audit logs record critical authentication and admin identity events.

## Completed Authentication Features

- Custom user model
- JWT access tokens
- Rotating refresh tokens
- Registration system
- Login system
- Role-based permissions
- Student profiles
- Instructor profiles
- Email verification
- Password reset
- 2FA via email OTP
- Secure protected APIs
- Profile management
- Admin user management
- Security headers and cookie hardening
- Rate limiting for signup, login, verification, password reset, and 2FA
- Authentication logging and auditing
- OpenAPI + Swagger authentication documentation

## Stabilization Checklist Before Moving On

- Run `python manage.py migrate`
- Run `python manage.py test`
- Review the contract in Swagger UI at `/api/docs/swagger/`
- Create an admin account with `python manage.py createsuperuser` if you need to inspect live auth data
- Verify instructor login, student login, email verification, password reset, and admin role management manually

## Next Phase

Only after auth is stable should the backend move into the course-management phase:

- Categories
- Courses
- Modules
- Lessons
- Enrollments
- Progress tracking
