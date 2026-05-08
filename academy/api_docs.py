from __future__ import annotations

from django.http import HttpResponse, JsonResponse
import yaml


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def _json_content(schema: dict, example: dict | list | None = None) -> dict:
    payload = {"schema": schema}
    if example is not None:
        payload["example"] = example
    return {"application/json": payload}


def _json_response(description: str, schema: dict, example: dict | list | None = None) -> dict:
    return {"description": description, "content": _json_content(schema, example)}


def _request_body(schema: dict, example: dict | list | None = None, *, required: bool = True) -> dict:
    return {"required": required, "content": _json_content(schema, example)}


def _security(*names: str) -> list[dict[str, list]]:
    return [{name: []} for name in names]


def build_auth_openapi_schema(request=None) -> dict:
    server_url = None
    if request is not None:
        server_url = request.build_absolute_uri("/").rstrip("/")

    info_description = (
        "Developer-facing authentication documentation for SkillForge.\n\n"
        "Core flow: register -> profile auto-created -> verification email -> verify -> login -> "
        "JWT access token -> protected API access -> role-based permissions.\n\n"
        "Authentication model:\n"
        "- Access tokens: JWT bearer tokens, 15 minute lifetime\n"
        "- Refresh tokens: rotating `HttpOnly` cookie named `skillforge_session`\n"
        "- 2FA: email OTP for instructor and admin accounts, optional for students\n"
        "- Roles: student, instructor, admin\n\n"
        "Mobile-friendly aliases mirror the primary endpoints:\n"
        "- `/api/register` -> `/api/auth/signup`\n"
        "- `/api/login` -> `/api/auth/login`\n"
        "- `/api/refresh-token` -> `/api/auth/refresh`\n"
        "- `/api/forgot-password` -> `/api/auth/password/reset-request`\n"
        "- `/api/reset-password` -> `/api/auth/password/reset-confirm`\n"
        "- `/api/verify-email` -> `/api/auth/verify-email/request|confirm`\n"
        "- `/api/logout` -> `/api/auth/logout`\n"
        "- `/api/2fa/verify` -> `/api/auth/2fa/verify`\n"
    )

    schema = {
        "openapi": "3.0.3",
        "info": {
            "title": "SkillForge Authentication API",
            "version": "1.0.0",
            "description": info_description,
        },
        "tags": [
            {"name": "Authentication", "description": "Registration, login, JWT refresh, verification, 2FA, and account recovery."},
            {"name": "Profile", "description": "Authenticated user profile and password management."},
            {"name": "Admin", "description": "Admin-only identity and role management operations."},
        ],
        "paths": {
            "/api/auth/signup": {
                "post": {
                    "tags": ["Authentication"],
                    "operationId": "authSignup",
                    "summary": "Register a new user",
                    "description": "Creates a new student or instructor account, auto-creates the matching role profile, sends a verification email, and returns an authenticated session.",
                    "requestBody": _request_body(
                        _ref("SignupRequest"),
                        {
                            "firstName": "Abebe",
                            "lastName": "Kebede",
                            "email": "abebe@example.com",
                            "password": "strongpass1",
                            "role": "student",
                        },
                    ),
                    "responses": {
                        "201": _json_response("Account created and signed in.", _ref("AuthSuccessResponse")),
                        "400": _json_response("Validation failed.", _ref("ErrorResponse")),
                        "409": _json_response("Email or username already exists.", _ref("ErrorResponse")),
                        "429": _json_response("Registration was rate limited.", _ref("ErrorResponse")),
                    },
                }
            },
            "/api/auth/login": {
                "post": {
                    "tags": ["Authentication"],
                    "operationId": "authLogin",
                    "summary": "Authenticate with email and password",
                    "description": "Validates credentials. Returns a signed-in session for standard accounts, or a 2FA challenge for accounts that require email OTP verification.",
                    "requestBody": _request_body(
                        _ref("LoginRequest"),
                        {"email": "abebe@example.com", "password": "strongpass1"},
                    ),
                    "responses": {
                        "200": _json_response("Authenticated successfully.", _ref("AuthSuccessResponse")),
                        "202": _json_response("Two-factor verification is required.", _ref("TwoFactorChallengeResponse")),
                        "400": _json_response("Validation failed.", _ref("ErrorResponse")),
                        "401": _json_response("Credentials were invalid.", _ref("ErrorResponse")),
                        "403": _json_response("Account is not active.", _ref("ErrorResponse")),
                        "429": _json_response("Login was rate limited.", _ref("ErrorResponse")),
                    },
                }
            },
            "/api/auth/2fa/verify": {
                "post": {
                    "tags": ["Authentication"],
                    "operationId": "authTwoFactorVerify",
                    "summary": "Verify a two-factor login challenge",
                    "description": "Completes sign-in for accounts that require email OTP verification and returns JWT/session data.",
                    "requestBody": _request_body(
                        _ref("TwoFactorVerifyRequest"),
                        {"challengeId": "42", "otpCode": "123456"},
                    ),
                    "responses": {
                        "200": _json_response("Two-factor verification completed.", _ref("AuthSuccessResponse")),
                        "400": _json_response("Challenge or code was invalid.", _ref("ErrorResponse")),
                        "429": _json_response("Too many invalid verification attempts.", _ref("ErrorResponse")),
                    },
                }
            },
            "/api/auth/refresh": {
                "post": {
                    "tags": ["Authentication"],
                    "operationId": "authRefresh",
                    "summary": "Rotate a refresh token and mint a new access token",
                    "description": "Uses the rotating refresh cookie, or an explicit `refreshToken` in the request body, to issue a new JWT access token and a new refresh cookie.",
                    "security": _security("RefreshCookie"),
                    "requestBody": _request_body(
                        _ref("RefreshRequest"),
                        {"refreshToken": "optional-refresh-token-if-not-using-cookie"},
                        required=False,
                    ),
                    "responses": {
                        "200": _json_response("Session refreshed.", _ref("AuthSuccessResponse")),
                        "401": _json_response("Refresh token was missing, expired, revoked, or reused.", _ref("ErrorResponse")),
                    },
                }
            },
            "/api/auth/me": {
                "get": {
                    "tags": ["Authentication"],
                    "operationId": "authMe",
                    "summary": "Get the current authenticated user",
                    "description": "Returns the current user and refresh-session metadata for a valid bearer token or restored session.",
                    "security": _security("BearerAuth"),
                    "responses": {
                        "200": _json_response("Authenticated user payload.", _ref("ProfileResponse")),
                        "401": _json_response("Authentication is required.", _ref("ErrorResponse")),
                    },
                }
            },
            "/api/auth/logout": {
                "post": {
                    "tags": ["Authentication"],
                    "operationId": "authLogout",
                    "summary": "Log out the current session",
                    "description": "Revokes the current refresh-token family and clears the refresh cookie. Pass `allSessions=true` to revoke every active refresh session for the current user.",
                    "security": _security("BearerAuth", "RefreshCookie"),
                    "requestBody": _request_body(
                        _ref("LogoutRequest"),
                        {"allSessions": False},
                        required=False,
                    ),
                    "responses": {
                        "200": _json_response("Logout completed.", _ref("LogoutResponse")),
                        "401": _json_response("Authentication is required.", _ref("ErrorResponse")),
                    },
                }
            },
            "/api/auth/oauth/start": {
                "post": {
                    "tags": ["Authentication"],
                    "operationId": "authOauthStart",
                    "summary": "Start OAuth sign-in",
                    "description": "Prepares the current frontend contract for Google OAuth by generating a state token and an authorization URL.",
                    "requestBody": _request_body(
                        _ref("OAuthStartRequest"),
                        {"provider": "google"},
                    ),
                    "responses": {
                        "200": _json_response("OAuth flow prepared.", _ref("OAuthStartResponse")),
                        "400": _json_response("Unsupported provider.", _ref("ErrorResponse")),
                    },
                }
            },
            "/api/auth/verify-email/request": {
                "post": {
                    "tags": ["Authentication"],
                    "operationId": "authVerifyEmailRequest",
                    "summary": "Request a verification email",
                    "description": "Sends a new verification email if the account exists and is not already verified.",
                    "requestBody": _request_body(
                        _ref("VerifyEmailRequest"),
                        {"email": "abebe@example.com"},
                    ),
                    "responses": {
                        "200": _json_response("Verification email was prepared when appropriate.", _ref("VerificationRequestResponse")),
                        "400": _json_response("Validation failed.", _ref("ErrorResponse")),
                        "429": _json_response("Verification requests were rate limited.", _ref("ErrorResponse")),
                    },
                }
            },
            "/api/auth/verify-email/confirm": {
                "get": {
                    "tags": ["Authentication"],
                    "operationId": "authVerifyEmailConfirmGet",
                    "summary": "Confirm an email verification token",
                    "description": "Browser-friendly verification confirmation. When successful it verifies the account and activates the authenticated session.",
                    "parameters": [
                        {
                            "name": "token",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "Raw email verification token from the verification link.",
                        }
                    ],
                    "responses": {
                        "200": {"description": "Verification completed. Returns a plain-text success message and sets the refresh cookie."},
                        "400": {"description": "Verification token was invalid or expired."},
                    },
                },
                "post": {
                    "tags": ["Authentication"],
                    "operationId": "authVerifyEmailConfirmPost",
                    "summary": "Confirm an email verification token via JSON",
                    "description": "API-friendly verification confirmation that returns the authenticated user, JWT access token, and updated verification status.",
                    "requestBody": _request_body(
                        _ref("VerifyEmailConfirmRequest"),
                        {"token": "verify_abc123"},
                    ),
                    "responses": {
                        "200": _json_response("Verification completed.", _ref("VerificationConfirmResponse")),
                        "400": _json_response("Verification token was invalid or expired.", _ref("ErrorResponse")),
                    },
                },
            },
            "/api/auth/password/reset-request": {
                "post": {
                    "tags": ["Authentication"],
                    "operationId": "authPasswordResetRequest",
                    "summary": "Request a password reset email",
                    "description": "Creates a time-limited password reset token and prepares a reset email when the account exists.",
                    "requestBody": _request_body(
                        _ref("PasswordResetRequest"),
                        {"email": "abebe@example.com"},
                    ),
                    "responses": {
                        "200": _json_response("Password reset email was prepared when appropriate.", _ref("PasswordResetRequestResponse")),
                        "400": _json_response("Validation failed.", _ref("ErrorResponse")),
                        "429": _json_response("Password reset requests were rate limited.", _ref("ErrorResponse")),
                    },
                }
            },
            "/api/auth/password/reset-confirm": {
                "get": {
                    "tags": ["Authentication"],
                    "operationId": "authPasswordResetConfirmGet",
                    "summary": "Validate a password reset token",
                    "description": "Checks whether a password reset token is still valid before the new password is submitted.",
                    "parameters": [
                        {
                            "name": "token",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "Password reset token from the email link.",
                        }
                    ],
                    "responses": {
                        "200": _json_response("Reset token is valid.", _ref("PasswordResetValidateResponse")),
                        "400": _json_response("Reset token was invalid.", _ref("ErrorResponse")),
                        "410": _json_response("Reset token has expired.", _ref("ErrorResponse")),
                    },
                },
                "post": {
                    "tags": ["Authentication"],
                    "operationId": "authPasswordResetConfirmPost",
                    "summary": "Set a new password with a reset token",
                    "description": "Validates a reset token, stores the new password securely, revokes old sessions, and returns a fresh authenticated session.",
                    "requestBody": _request_body(
                        _ref("PasswordResetConfirmRequest"),
                        {"token": "reset_abc123", "password": "newstrongpass2"},
                    ),
                    "responses": {
                        "200": _json_response("Password was updated and the user was signed in.", _ref("AuthSuccessResponse")),
                        "400": _json_response("Reset token or password was invalid.", _ref("ErrorResponse")),
                        "409": _json_response("Reset token was already used.", _ref("ErrorResponse")),
                        "410": _json_response("Reset token has expired.", _ref("ErrorResponse")),
                    },
                },
            },
            "/api/profile": {
                "get": {
                    "tags": ["Profile"],
                    "operationId": "profileDetail",
                    "summary": "Get the current profile",
                    "description": "Returns the current authenticated user payload, including role capabilities and role-specific profile data.",
                    "security": _security("BearerAuth"),
                    "responses": {
                        "200": _json_response("Profile payload.", _ref("ProfileResponse")),
                        "401": _json_response("Authentication is required.", _ref("ErrorResponse")),
                    },
                }
            },
            "/api/profile/update": {
                "put": {
                    "tags": ["Profile"],
                    "operationId": "profileUpdatePut",
                    "summary": "Replace updatable profile fields",
                    "description": "Updates public profile fields like avatar, bio, username, social links, and 2FA preferences. Instructor/admin accounts can also update instructor-specific profile fields.",
                    "security": _security("BearerAuth"),
                    "requestBody": _request_body(
                        _ref("ProfileUpdateRequest"),
                        {
                            "firstName": "Abebe",
                            "lastName": "Kebede",
                            "avatar": "https://example.com/avatar.png",
                            "bio": "Backend and AI learner.",
                            "socialLinks": {"github": "https://github.com/abebe"},
                            "twoFactorEnabled": True,
                            "twoFactorMethod": "email_otp",
                        },
                    ),
                    "responses": {
                        "200": _json_response("Profile updated.", _ref("UserMutationResponse")),
                        "400": _json_response("Validation failed.", _ref("ErrorResponse")),
                        "401": _json_response("Authentication is required.", _ref("ErrorResponse")),
                        "409": _json_response("Username already exists.", _ref("ErrorResponse")),
                    },
                },
                "patch": {
                    "tags": ["Profile"],
                    "operationId": "profileUpdatePatch",
                    "summary": "Partially update profile fields",
                    "description": "Supports the same fields as `PUT /api/profile/update`, but can be used for partial updates.",
                    "security": _security("BearerAuth"),
                    "requestBody": _request_body(
                        _ref("ProfileUpdateRequest"),
                        {"bio": "Shipping the authentication phase cleanly."},
                    ),
                    "responses": {
                        "200": _json_response("Profile updated.", _ref("UserMutationResponse")),
                        "400": _json_response("Validation failed.", _ref("ErrorResponse")),
                        "401": _json_response("Authentication is required.", _ref("ErrorResponse")),
                        "409": _json_response("Username already exists.", _ref("ErrorResponse")),
                    },
                },
            },
            "/api/change-password": {
                "post": {
                    "tags": ["Profile"],
                    "operationId": "changePassword",
                    "summary": "Change the current password",
                    "description": "Validates the current password, stores the new password securely, revokes older refresh sessions, and returns a fresh authenticated session.",
                    "security": _security("BearerAuth"),
                    "requestBody": _request_body(
                        _ref("ChangePasswordRequest"),
                        {"currentPassword": "strongpass1", "newPassword": "strongpass2"},
                    ),
                    "responses": {
                        "200": _json_response("Password updated.", _ref("AuthSuccessResponse")),
                        "400": _json_response("Current password or new password was invalid.", _ref("ErrorResponse")),
                        "401": _json_response("Authentication is required.", _ref("ErrorResponse")),
                    },
                }
            },
            "/api/users": {
                "get": {
                    "tags": ["Admin"],
                    "operationId": "adminUsersList",
                    "summary": "List users",
                    "description": "Admin-only user search and listing endpoint. Supports optional `q`, `role`, and `status` filters.",
                    "security": _security("BearerAuth"),
                    "parameters": [
                        {"name": "q", "in": "query", "required": False, "schema": {"type": "string"}, "description": "Search by email, username, first name, or last name."},
                        {"name": "role", "in": "query", "required": False, "schema": {"type": "string", "enum": ["student", "instructor", "admin", "support"]}},
                        {"name": "status", "in": "query", "required": False, "schema": {"type": "string", "enum": ["pending_verification", "active", "suspended", "deactivated"]}},
                    ],
                    "responses": {
                        "200": _json_response("User list.", _ref("UsersListResponse")),
                        "401": _json_response("Authentication is required.", _ref("ErrorResponse")),
                        "403": _json_response("Admin access is required.", _ref("ErrorResponse")),
                    },
                }
            },
            "/api/users/suspend": {
                "patch": {
                    "tags": ["Admin"],
                    "operationId": "adminUsersSuspend",
                    "summary": "Suspend or unsuspend a user",
                    "description": "Admin-only operation that toggles account status and active state. All actions are written to the authentication audit log.",
                    "security": _security("BearerAuth"),
                    "requestBody": _request_body(
                        _ref("AdminSuspendRequest"),
                        {"userId": "f6a5fcb9-4af8-4cdd-b9a0-8d3f8cfd1e31", "suspended": True},
                    ),
                    "responses": {
                        "200": _json_response("User suspension state updated.", _ref("AdminSuspendResponse")),
                        "400": _json_response("Validation failed.", _ref("ErrorResponse")),
                        "401": _json_response("Authentication is required.", _ref("ErrorResponse")),
                        "403": _json_response("Admin access is required.", _ref("ErrorResponse")),
                        "404": _json_response("Target user was not found.", _ref("ErrorResponse")),
                    },
                }
            },
            "/api/users/verify": {
                "patch": {
                    "tags": ["Admin"],
                    "operationId": "adminUsersVerify",
                    "summary": "Mark a user as verified",
                    "description": "Admin-only operation that marks a user as email verified and writes the action to the authentication audit log.",
                    "security": _security("BearerAuth"),
                    "requestBody": _request_body(
                        _ref("AdminUserLookupRequest"),
                        {"email": "student@example.com"},
                    ),
                    "responses": {
                        "200": _json_response("User marked as verified.", _ref("AdminVerifyResponse")),
                        "400": _json_response("Validation failed.", _ref("ErrorResponse")),
                        "401": _json_response("Authentication is required.", _ref("ErrorResponse")),
                        "403": _json_response("Admin access is required.", _ref("ErrorResponse")),
                        "404": _json_response("Target user was not found.", _ref("ErrorResponse")),
                    },
                }
            },
            "/api/users/change-role": {
                "patch": {
                    "tags": ["Admin"],
                    "operationId": "adminUsersChangeRole",
                    "summary": "Change a user's role",
                    "description": "Admin-only operation that changes a user role, updates staff flags when needed, auto-creates the matching role profile, and records the action in the authentication audit log.",
                    "security": _security("BearerAuth"),
                    "requestBody": _request_body(
                        _ref("AdminChangeRoleRequest"),
                        {"userId": "f6a5fcb9-4af8-4cdd-b9a0-8d3f8cfd1e31", "role": "instructor"},
                    ),
                    "responses": {
                        "200": _json_response("User role updated.", _ref("UserMutationResponse")),
                        "400": _json_response("Validation failed.", _ref("ErrorResponse")),
                        "401": _json_response("Authentication is required.", _ref("ErrorResponse")),
                        "403": _json_response("Admin access is required.", _ref("ErrorResponse")),
                        "404": _json_response("Target user was not found.", _ref("ErrorResponse")),
                    },
                }
            },
        },
        "components": {
            "securitySchemes": {
                "BearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": "Short-lived JWT access token supplied as `Authorization: Bearer <token>`.",
                },
                "RefreshCookie": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "skillforge_session",
                    "description": "Rotating refresh token cookie used by `/api/auth/refresh` and logout flows.",
                },
            },
            "schemas": {
                "ErrorResponse": {
                    "type": "object",
                    "required": ["ok", "message"],
                    "properties": {
                        "ok": {"type": "boolean", "example": False},
                        "message": {"type": "string", "example": "Authentication required."},
                    },
                },
                "AuthCapabilities": {
                    "type": "object",
                    "properties": {
                        "canEnrollCourses": {"type": "boolean"},
                        "canWatchLessons": {"type": "boolean"},
                        "canSubmitAssignments": {"type": "boolean"},
                        "canTakeQuizzes": {"type": "boolean"},
                        "canLeaveReviews": {"type": "boolean"},
                        "canCreateCourses": {"type": "boolean"},
                        "canUploadLessons": {"type": "boolean"},
                        "canManageStudents": {"type": "boolean"},
                        "canViewInstructorAnalytics": {"type": "boolean"},
                        "canAccessAdminDashboard": {"type": "boolean"},
                        "canAccessAdminModeration": {"type": "boolean"},
                        "canConfigurePlatform": {"type": "boolean"},
                    },
                },
                "StudentProfile": {
                    "type": "object",
                    "properties": {
                        "learningStreakDays": {"type": "integer"},
                        "completedCourses": {"type": "integer"},
                        "currentCourses": {"type": "integer"},
                        "savedCourses": {"type": "integer"},
                        "averageProgressPercent": {"type": "integer"},
                        "totalLearningMinutes": {"type": "integer"},
                        "learningStatistics": {"type": "object", "additionalProperties": True},
                        "lastActivityAt": {"type": "string", "format": "date-time", "nullable": True},
                    },
                },
                "InstructorProfile": {
                    "type": "object",
                    "properties": {
                        "expertise": {"type": "array", "items": {"type": "string"}},
                        "biography": {"type": "string"},
                        "revenueTotal": {"type": "number", "format": "float"},
                        "publishedCourses": {"type": "integer"},
                        "totalStudentsTaught": {"type": "integer"},
                        "averageRating": {"type": "number", "format": "float"},
                        "teachingStatistics": {"type": "object", "additionalProperties": True},
                        "socialLinks": {"type": "object", "additionalProperties": {"type": "string"}},
                        "verifiedBadge": {"type": "boolean"},
                        "verifiedAt": {"type": "string", "format": "date-time", "nullable": True},
                    },
                },
                "User": {
                    "type": "object",
                    "required": ["id", "email", "role", "capabilities", "verified", "status", "createdAt"],
                    "properties": {
                        "id": {"type": "string", "format": "uuid"},
                        "firstName": {"type": "string"},
                        "lastName": {"type": "string"},
                        "email": {"type": "string", "format": "email"},
                        "username": {"type": "string", "nullable": True},
                        "avatar": {"type": "string"},
                        "bio": {"type": "string"},
                        "socialLinks": {"type": "object", "additionalProperties": {"type": "string"}},
                        "role": {"type": "string", "enum": ["student", "instructor", "admin", "support"]},
                        "capabilities": _ref("AuthCapabilities"),
                        "verified": {"type": "boolean"},
                        "twoFactorEnabled": {"type": "boolean"},
                        "twoFactorMethod": {"type": "string", "enum": ["email_otp", "authenticator_app", "sms_otp"]},
                        "requiresTwoFactor": {"type": "boolean"},
                        "status": {"type": "string", "enum": ["pending_verification", "active", "suspended", "deactivated"]},
                        "studentProfile": {"allOf": [_ref("StudentProfile")], "nullable": True},
                        "instructorProfile": {"allOf": [_ref("InstructorProfile")], "nullable": True},
                        "createdAt": {"type": "string", "format": "date-time"},
                    },
                },
                "Session": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "familyId": {"type": "string", "format": "uuid"},
                        "jti": {"type": "string"},
                        "createdAt": {"type": "string", "format": "date-time"},
                        "expiresAt": {"type": "string", "format": "date-time"},
                        "sessionExpiresAt": {"type": "string", "format": "date-time"},
                        "lastSeenAt": {"type": "string", "format": "date-time", "nullable": True},
                        "lastUsedAt": {"type": "string", "format": "date-time", "nullable": True},
                        "rotatedAt": {"type": "string", "format": "date-time", "nullable": True},
                        "revokedAt": {"type": "string", "format": "date-time", "nullable": True},
                        "reuseDetectedAt": {"type": "string", "format": "date-time", "nullable": True},
                    },
                },
                "PendingUser": {
                    "type": "object",
                    "properties": {
                        "email": {"type": "string", "format": "email"},
                        "role": {"type": "string", "enum": ["student", "instructor", "admin", "support"]},
                        "twoFactorMethod": {"type": "string", "enum": ["email_otp", "authenticator_app", "sms_otp"]},
                    },
                },
                "AuthSuccessResponse": {
                    "type": "object",
                    "required": ["ok", "authenticated", "user", "token", "accessToken", "session", "verificationRequired"],
                    "properties": {
                        "ok": {"type": "boolean", "example": True},
                        "authenticated": {"type": "boolean", "example": True},
                        "user": _ref("User"),
                        "token": {"type": "string", "description": "JWT access token."},
                        "accessToken": {"type": "string", "description": "JWT access token duplicate for frontend compatibility."},
                        "session": _ref("Session"),
                        "verificationRequired": {"type": "boolean"},
                        "verificationEmailSent": {"type": "boolean"},
                        "verificationExpiresAt": {"type": "string", "format": "date-time", "nullable": True},
                        "verificationToken": {"type": "string", "nullable": True, "description": "Development-only token exposure."},
                        "verificationUrl": {"type": "string", "nullable": True, "description": "Development-only verification URL exposure."},
                    },
                },
                "TwoFactorChallengeResponse": {
                    "type": "object",
                    "required": ["ok", "authenticated", "twoFactorRequired", "challengeId", "method", "expiresAt", "pendingUser", "message"],
                    "properties": {
                        "ok": {"type": "boolean", "example": True},
                        "authenticated": {"type": "boolean", "example": False},
                        "twoFactorRequired": {"type": "boolean", "example": True},
                        "challengeId": {"type": "string"},
                        "method": {"type": "string", "enum": ["email_otp"]},
                        "expiresAt": {"type": "string", "format": "date-time"},
                        "pendingUser": _ref("PendingUser"),
                        "message": {"type": "string"},
                        "otpCode": {"type": "string", "nullable": True, "description": "Development-only OTP exposure."},
                    },
                },
                "ProfileResponse": {
                    "type": "object",
                    "required": ["ok", "user"],
                    "properties": {
                        "ok": {"type": "boolean", "example": True},
                        "user": _ref("User"),
                        "session": {"allOf": [_ref("Session")], "nullable": True},
                    },
                },
                "UserMutationResponse": {
                    "type": "object",
                    "required": ["ok", "user"],
                    "properties": {
                        "ok": {"type": "boolean", "example": True},
                        "user": _ref("User"),
                    },
                },
                "LogoutResponse": {
                    "type": "object",
                    "properties": {
                        "ok": {"type": "boolean"},
                        "authenticated": {"type": "boolean"},
                        "loggedOut": {"type": "boolean"},
                        "allSessions": {"type": "boolean"},
                    },
                },
                "VerificationRequestResponse": {
                    "type": "object",
                    "properties": {
                        "ok": {"type": "boolean"},
                        "message": {"type": "string"},
                        "verificationEmailSent": {"type": "boolean"},
                        "verificationExpiresAt": {"type": "string", "format": "date-time", "nullable": True},
                        "verificationToken": {"type": "string", "nullable": True, "description": "Development-only token exposure."},
                        "verificationUrl": {"type": "string", "nullable": True, "description": "Development-only verification URL exposure."},
                    },
                },
                "VerificationConfirmResponse": {
                    "type": "object",
                    "allOf": [
                        _ref("AuthSuccessResponse"),
                        {
                            "type": "object",
                            "properties": {
                                "verificationConfirmed": {"type": "boolean"},
                                "verifiedAt": {"type": "string", "format": "date-time"},
                            },
                        },
                    ],
                },
                "PasswordResetRequestResponse": {
                    "type": "object",
                    "properties": {
                        "ok": {"type": "boolean"},
                        "message": {"type": "string"},
                        "emailSent": {"type": "boolean"},
                        "expiresAt": {"type": "string", "format": "date-time", "nullable": True},
                        "resetToken": {"type": "string", "nullable": True, "description": "Development-only token exposure."},
                        "resetUrl": {"type": "string", "nullable": True, "description": "Development-only reset URL exposure."},
                    },
                },
                "PasswordResetValidateResponse": {
                    "type": "object",
                    "properties": {
                        "ok": {"type": "boolean"},
                        "valid": {"type": "boolean"},
                        "email": {"type": "string", "format": "email"},
                        "expiresAt": {"type": "string", "format": "date-time"},
                    },
                },
                "OAuthStartResponse": {
                    "type": "object",
                    "properties": {
                        "ok": {"type": "boolean"},
                        "provider": {"type": "string", "example": "google"},
                        "state": {"type": "string"},
                        "authorizationUrl": {"type": "string", "format": "uri"},
                    },
                },
                "UsersListResponse": {
                    "type": "object",
                    "properties": {
                        "ok": {"type": "boolean"},
                        "count": {"type": "integer"},
                        "users": {"type": "array", "items": _ref("User")},
                    },
                },
                "AdminSuspendResponse": {
                    "type": "object",
                    "properties": {
                        "ok": {"type": "boolean"},
                        "suspended": {"type": "boolean"},
                        "user": _ref("User"),
                    },
                },
                "AdminVerifyResponse": {
                    "type": "object",
                    "properties": {
                        "ok": {"type": "boolean"},
                        "verified": {"type": "boolean"},
                        "user": _ref("User"),
                    },
                },
                "SignupRequest": {
                    "type": "object",
                    "required": ["firstName", "lastName", "email", "password"],
                    "properties": {
                        "firstName": {"type": "string"},
                        "lastName": {"type": "string"},
                        "email": {"type": "string", "format": "email"},
                        "password": {"type": "string", "minLength": 8},
                        "username": {"type": "string"},
                        "role": {"type": "string", "enum": ["student", "instructor"], "default": "student"},
                    },
                },
                "LoginRequest": {
                    "type": "object",
                    "required": ["email", "password"],
                    "properties": {
                        "email": {"type": "string", "format": "email"},
                        "password": {"type": "string", "minLength": 8},
                    },
                },
                "RefreshRequest": {
                    "type": "object",
                    "properties": {
                        "refreshToken": {"type": "string", "description": "Optional fallback when the refresh cookie is not available."},
                    },
                },
                "TwoFactorVerifyRequest": {
                    "type": "object",
                    "required": ["challengeId", "otpCode"],
                    "properties": {
                        "challengeId": {"type": "string"},
                        "otpCode": {"type": "string", "minLength": 6, "maxLength": 6},
                    },
                },
                "VerifyEmailRequest": {
                    "type": "object",
                    "properties": {
                        "email": {"type": "string", "format": "email"},
                    },
                },
                "VerifyEmailConfirmRequest": {
                    "type": "object",
                    "required": ["token"],
                    "properties": {
                        "token": {"type": "string"},
                    },
                },
                "PasswordResetRequest": {
                    "type": "object",
                    "required": ["email"],
                    "properties": {
                        "email": {"type": "string", "format": "email"},
                    },
                },
                "PasswordResetConfirmRequest": {
                    "type": "object",
                    "required": ["token", "password"],
                    "properties": {
                        "token": {"type": "string"},
                        "password": {"type": "string", "minLength": 8},
                    },
                },
                "OAuthStartRequest": {
                    "type": "object",
                    "required": ["provider"],
                    "properties": {
                        "provider": {"type": "string", "enum": ["google"]},
                    },
                },
                "ProfileUpdateRequest": {
                    "type": "object",
                    "properties": {
                        "firstName": {"type": "string"},
                        "lastName": {"type": "string"},
                        "username": {"type": "string"},
                        "avatar": {"type": "string", "format": "uri"},
                        "bio": {"type": "string"},
                        "socialLinks": {"type": "object", "additionalProperties": {"type": "string"}},
                        "twoFactorEnabled": {"type": "boolean"},
                        "twoFactorMethod": {"type": "string", "enum": ["email_otp", "authenticator_app", "sms_otp"]},
                        "expertise": {"type": "array", "items": {"type": "string"}},
                        "biography": {"type": "string"},
                        "instructorProfile": {
                            "type": "object",
                            "properties": {
                                "expertise": {"type": "array", "items": {"type": "string"}},
                                "biography": {"type": "string"},
                                "socialLinks": {"type": "object", "additionalProperties": {"type": "string"}},
                            },
                        },
                    },
                },
                "ChangePasswordRequest": {
                    "type": "object",
                    "required": ["currentPassword", "newPassword"],
                    "properties": {
                        "currentPassword": {"type": "string"},
                        "newPassword": {"type": "string", "minLength": 8},
                    },
                },
                "LogoutRequest": {
                    "type": "object",
                    "properties": {
                        "allSessions": {"type": "boolean", "default": False},
                    },
                },
                "AdminUserLookupRequest": {
                    "type": "object",
                    "properties": {
                        "userId": {"type": "string", "format": "uuid"},
                        "email": {"type": "string", "format": "email"},
                    },
                },
                "AdminSuspendRequest": {
                    "type": "object",
                    "allOf": [
                        _ref("AdminUserLookupRequest"),
                        {
                            "type": "object",
                            "properties": {
                                "suspended": {"type": "boolean", "default": True},
                            },
                        },
                    ],
                },
                "AdminChangeRoleRequest": {
                    "type": "object",
                    "allOf": [
                        _ref("AdminUserLookupRequest"),
                        {
                            "type": "object",
                            "required": ["role"],
                            "properties": {
                                "role": {"type": "string", "enum": ["student", "instructor", "admin", "support"]},
                            },
                        },
                    ],
                },
            },
        },
    }

    if server_url:
        schema["servers"] = [{"url": server_url}]
    return schema


def auth_openapi_json(request):
    return JsonResponse(build_auth_openapi_schema(request), json_dumps_params={"indent": 2})


def auth_openapi_yaml(request):
    payload = yaml.safe_dump(build_auth_openapi_schema(request), sort_keys=False, allow_unicode=True)
    return HttpResponse(payload, content_type="application/yaml; charset=utf-8")
