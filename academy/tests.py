from __future__ import annotations

import json
import uuid
from datetime import timedelta
from tempfile import TemporaryDirectory

import jwt

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.utils import timezone

from . import models
from .services import AUTH_COOKIE_NAME, JWT_ALGORITHM, JWT_ISSUER, auth_version_for_user, seed_database


class SkillForgeApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_database(force=True)

    def setUp(self):
        self.client = Client()
        cache.clear()
        if hasattr(mail, "outbox"):
            mail.outbox.clear()

    def auth_headers(self, token: str) -> dict[str, str]:
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_custom_user_model_is_active(self):
        self.assertEqual(get_user_model()._meta.label, "accounts.User")

    def test_role_profiles_are_created_for_users(self):
        User = get_user_model()
        student = User.objects.create_user(email="student-profile@example.com", password="strongpass1")
        instructor = User.objects.create_user(
            email="instructor-profile@example.com",
            password="strongpass1",
            role="instructor",
        )

        self.assertTrue(hasattr(student, "student_profile"))
        self.assertFalse(hasattr(student, "instructor_profile"))
        self.assertFalse(hasattr(instructor, "student_profile"))
        self.assertTrue(hasattr(instructor, "instructor_profile"))

    def test_health_and_courses_endpoints_are_available(self):
        admin_response = self.client.get("/admin/login/")
        self.assertEqual(admin_response.status_code, 200)
        self.assertIn("SkillForge Admin", admin_response.content.decode("utf-8"))

        index_response = self.client.get("/")
        self.assertEqual(index_response.status_code, 200)
        self.assertIn('/frontend-auth.js', index_response.content.decode("utf-8"))

        script_response = self.client.get("/frontend-auth.js")
        self.assertEqual(script_response.status_code, 200)
        self.assertIn("Log Out", script_response.content.decode("utf-8"))

        health_response = self.client.get("/api/health")
        self.assertEqual(health_response.status_code, 200)
        health = health_response.json()
        self.assertTrue(health["ok"])

        courses_response = self.client.get("/api/courses")
        self.assertEqual(courses_response.status_code, 200)
        courses = courses_response.json()
        self.assertTrue(courses["ok"])
        self.assertGreaterEqual(courses["count"], 9)

        detail_response = self.client.get("/api/courses/claude-ai-engineering")
        self.assertEqual(detail_response.status_code, 200)
        detail = detail_response.json()
        self.assertEqual(detail["course"]["id"], "claude-ai-engineering")

    def test_authentication_docs_endpoints_are_available(self):
        openapi_response = self.client.get("/api/docs/openapi.json")
        self.assertEqual(openapi_response.status_code, 200)
        openapi = openapi_response.json()
        self.assertEqual(openapi["info"]["title"], "SkillForge Authentication API")
        self.assertIn("/api/auth/login", openapi["paths"])
        self.assertIn("BearerAuth", openapi["components"]["securitySchemes"])

        yaml_response = self.client.get("/api/docs/openapi.yaml")
        self.assertEqual(yaml_response.status_code, 200)
        self.assertIn("/api/auth/login", yaml_response.content.decode("utf-8"))

        swagger_response = self.client.get("/api/docs/swagger/")
        self.assertEqual(swagger_response.status_code, 200)
        self.assertIn("swagger", swagger_response.content.decode("utf-8").lower())

    def test_auth_signup_and_login_work(self):
        signup_response = self.client.post(
            "/api/auth/signup",
            data=json.dumps(
                {
                    "firstName": "Abebe",
                    "lastName": "Kebede",
                    "email": "abebe@example.com",
                    "password": "strongpass1",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(signup_response.status_code, 201)
        signup = signup_response.json()
        self.assertTrue(signup["ok"])
        self.assertEqual(signup["user"]["email"], "abebe@example.com")
        self.assertIsNotNone(signup["user"]["username"])
        self.assertIn("studentProfile", signup["user"])
        self.assertIsNotNone(signup["user"]["studentProfile"])
        self.assertIsNone(signup["user"]["instructorProfile"])
        self.assertFalse(signup["user"]["capabilities"]["canCreateCourses"])
        self.assertIn(AUTH_COOKIE_NAME, self.client.cookies)
        self.assertIn("session", signup)
        self.assertIn("token", signup)
        self.assertEqual(signup["token"], signup["accessToken"])
        self.assertTrue(signup["verificationRequired"])
        self.assertTrue(signup["verificationEmailSent"])
        self.assertIn("verificationToken", signup)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Verify your SkillForge account", mail.outbox[0].subject)

        me_response = self.client.get("/api/auth/me", **self.auth_headers(signup["token"]))
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.json()["user"]["email"], "abebe@example.com")

        fresh_client = Client()
        login_response = fresh_client.post(
            "/api/auth/login",
            data=json.dumps({"email": "abebe@example.com", "password": "strongpass1"}),
            content_type="application/json",
        )
        self.assertEqual(login_response.status_code, 200)
        login = login_response.json()
        self.assertTrue(login["ok"])
        self.assertIn("token", login)
        self.assertEqual(login["token"], login["accessToken"])
        self.assertIn("session", login)

    def test_instructor_signup_creates_instructor_profile(self):
        signup_response = self.client.post(
            "/api/auth/signup",
            data=json.dumps(
                {
                    "firstName": "Yonas",
                    "lastName": "Tesfaye",
                    "email": "yonas@example.com",
                    "password": "strongpass1",
                    "role": "instructor",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(signup_response.status_code, 201)
        signup = signup_response.json()
        self.assertEqual(signup["user"]["role"], "instructor")
        self.assertIsNone(signup["user"]["studentProfile"])
        self.assertIsNotNone(signup["user"]["instructorProfile"])
        self.assertTrue(signup["user"]["capabilities"]["canCreateCourses"])

    def test_instructor_login_requires_two_factor(self):
        signup_response = self.client.post(
            "/api/auth/signup",
            data=json.dumps(
                {
                    "firstName": "Instructor",
                    "lastName": "Secure",
                    "email": "instructor-secure@example.com",
                    "password": "strongpass1",
                    "role": "instructor",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(signup_response.status_code, 201)
        mail.outbox.clear()

        fresh_client = Client()
        login_response = fresh_client.post(
            "/api/auth/login",
            data=json.dumps({"email": "instructor-secure@example.com", "password": "strongpass1"}),
            content_type="application/json",
        )
        self.assertEqual(login_response.status_code, 202)
        login = login_response.json()
        self.assertTrue(login["twoFactorRequired"])
        self.assertEqual(login["method"], "email_otp")
        self.assertIn("challengeId", login)
        self.assertIn("otpCode", login)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(models.AuthAuditLog.objects.filter(email="instructor-secure@example.com", action="two_factor.challenge").exists())

        failed_response = fresh_client.post(
            "/api/auth/2fa/verify",
            data=json.dumps({"challengeId": login["challengeId"], "code": "000000"}),
            content_type="application/json",
        )
        self.assertEqual(failed_response.status_code, 400)
        self.assertTrue(models.AuthAuditLog.objects.filter(email="instructor-secure@example.com", action="two_factor.failed").exists())

        verify_response = fresh_client.post(
            "/api/auth/2fa/verify",
            data=json.dumps({"challengeId": login["challengeId"], "code": login["otpCode"]}),
            content_type="application/json",
        )
        self.assertEqual(verify_response.status_code, 200)
        verify_payload = verify_response.json()
        self.assertEqual(verify_payload["user"]["email"], "instructor-secure@example.com")
        self.assertIn(AUTH_COOKIE_NAME, fresh_client.cookies)

    def test_signup_rejects_unsupported_roles(self):
        signup_response = self.client.post(
            "/api/auth/signup",
            data=json.dumps(
                {
                    "firstName": "Root",
                    "lastName": "User",
                    "email": "root@example.com",
                    "password": "strongpass1",
                    "role": "admin",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(signup_response.status_code, 400)

    def test_signup_rejects_weak_password_and_invalid_username(self):
        weak_password_response = self.client.post(
            "/api/auth/signup",
            data=json.dumps(
                {
                    "firstName": "Weak",
                    "lastName": "Password",
                    "email": "weak@example.com",
                    "password": "password",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(weak_password_response.status_code, 400)

        invalid_username_response = self.client.post(
            "/api/auth/signup",
            data=json.dumps(
                {
                    "firstName": "Bad",
                    "lastName": "Username",
                    "email": "username@example.com",
                    "password": "strongpass1",
                    "username": "###",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(invalid_username_response.status_code, 400)

    def test_verify_email_request_and_confirm_flow(self):
        signup_response = self.client.post(
            "/api/auth/signup",
            data=json.dumps(
                {
                    "firstName": "Verify",
                    "lastName": "Me",
                    "email": "verify@example.com",
                    "password": "strongpass1",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(signup_response.status_code, 201)
        signup = signup_response.json()
        self.assertIn("verificationToken", signup)

        resend_response = self.client.post(
            "/api/auth/verify-email/request",
            data=json.dumps({"email": "verify@example.com"}),
            content_type="application/json",
        )
        self.assertEqual(resend_response.status_code, 200)
        resend = resend_response.json()
        self.assertTrue(resend["verificationEmailSent"])
        self.assertIn("verificationToken", resend)
        self.assertNotEqual(signup["verificationToken"], resend["verificationToken"])

        confirm_response = self.client.post(
            "/api/auth/verify-email/confirm",
            data=json.dumps({"token": resend["verificationToken"]}),
            content_type="application/json",
        )
        self.assertEqual(confirm_response.status_code, 200)
        confirm = confirm_response.json()
        self.assertTrue(confirm["verificationConfirmed"])
        self.assertFalse(confirm["verificationRequired"])
        self.assertTrue(confirm["user"]["verified"])

        user = get_user_model().objects.get(email="verify@example.com")
        self.assertTrue(user.is_email_verified)
        self.assertEqual(user.status, user.Status.ACTIVE)
        self.assertEqual(len(mail.outbox), 2)

    def test_signup_rate_limiting_blocks_excessive_attempts(self):
        for index in range(8):
            response = self.client.post(
                "/api/auth/signup",
                data=json.dumps(
                    {
                        "firstName": "Rate",
                        "lastName": "Limit",
                        "email": f"invalid-email-{index}",
                        "password": "strongpass1",
                    }
                ),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 400)

        blocked_response = self.client.post(
            "/api/auth/signup",
            data=json.dumps(
                {
                    "firstName": "Rate",
                    "lastName": "Limit",
                    "email": "invalid-email-blocked",
                    "password": "strongpass1",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(blocked_response.status_code, 429)
        self.assertIn("Retry-After", blocked_response.headers)

    def test_login_rate_limiting_blocks_repeated_failures(self):
        User = get_user_model()
        User.objects.create_user(email="rate-login@example.com", password="strongpass1")

        for _index in range(8):
            response = self.client.post(
                "/api/auth/login",
                data=json.dumps({"email": "rate-login@example.com", "password": "wrongpass1"}),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 401)

        blocked_response = self.client.post(
            "/api/auth/login",
            data=json.dumps({"email": "rate-login@example.com", "password": "wrongpass1"}),
            content_type="application/json",
        )
        self.assertEqual(blocked_response.status_code, 429)
        self.assertIn("Retry-After", blocked_response.headers)

    def test_password_reset_rate_limiting_blocks_repeated_requests(self):
        User = get_user_model()
        User.objects.create_user(email="rate-reset@example.com", password="strongpass1")

        for _index in range(3):
            response = self.client.post(
                "/api/auth/password/reset-request",
                data=json.dumps({"email": "rate-reset@example.com"}),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200)

        blocked_response = self.client.post(
            "/api/auth/password/reset-request",
            data=json.dumps({"email": "rate-reset@example.com"}),
            content_type="application/json",
        )
        self.assertEqual(blocked_response.status_code, 429)
        self.assertIn("Retry-After", blocked_response.headers)

    def test_auth_me_logout_and_password_reset_flow(self):
        signup_response = self.client.post(
            "/api/auth/signup",
            data=json.dumps(
                {
                    "firstName": "Liya",
                    "lastName": "Hailu",
                    "email": "liya@example.com",
                    "password": "initialpass1",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(signup_response.status_code, 201)
        signup = signup_response.json()
        token = signup["token"]
        original_refresh = self.client.cookies[AUTH_COOKIE_NAME].value

        me_response = self.client.get("/api/auth/me", **self.auth_headers(token))
        self.assertEqual(me_response.status_code, 200)
        me = me_response.json()
        self.assertTrue(me["authenticated"])
        self.assertEqual(me["user"]["email"], "liya@example.com")

        refresh_response = self.client.post("/api/auth/refresh", data=json.dumps({}), content_type="application/json")
        self.assertEqual(refresh_response.status_code, 200)
        refreshed = refresh_response.json()
        self.assertEqual(refreshed["user"]["email"], "liya@example.com")
        self.assertNotEqual(original_refresh, self.client.cookies[AUTH_COOKIE_NAME].value)

        bearer_client = Client()
        bearer_response = bearer_client.get("/api/auth/me", **self.auth_headers(refreshed["token"]))
        self.assertEqual(bearer_response.status_code, 200)
        self.assertEqual(bearer_response.json()["user"]["email"], "liya@example.com")

        logout_response = self.client.post(
            "/api/auth/logout",
            data=json.dumps({}),
            content_type="application/json",
            **self.auth_headers(refreshed["token"]),
        )
        self.assertEqual(logout_response.status_code, 200)
        self.assertTrue(logout_response.json()["loggedOut"])

        me_after_logout = self.client.get("/api/auth/me")
        self.assertEqual(me_after_logout.status_code, 401)

        refresh_after_logout = self.client.post("/api/auth/refresh", data=json.dumps({}), content_type="application/json")
        self.assertEqual(refresh_after_logout.status_code, 401)

        reset_request_response = self.client.post(
            "/api/auth/password/reset-request",
            data=json.dumps({"email": "liya@example.com"}),
            content_type="application/json",
        )
        self.assertEqual(reset_request_response.status_code, 200)
        reset_request = reset_request_response.json()
        self.assertTrue(reset_request["emailSent"])
        self.assertIn("resetToken", reset_request)
        self.assertIn("resetUrl", reset_request)
        self.assertEqual(len(mail.outbox), 2)

        reset_validate_response = self.client.get(f"/api/reset-password?token={reset_request['resetToken']}")
        self.assertEqual(reset_validate_response.status_code, 200)
        self.assertTrue(reset_validate_response.json()["valid"])

        reset_confirm_response = self.client.post(
            "/api/auth/password/reset-confirm",
            data=json.dumps({"token": reset_request["resetToken"], "password": "newstrongpass2"}),
            content_type="application/json",
        )
        self.assertEqual(reset_confirm_response.status_code, 200)
        self.assertEqual(reset_confirm_response.json()["user"]["email"], "liya@example.com")
        self.assertIn("token", reset_confirm_response.json())

        fresh_client = Client()
        login_response = fresh_client.post(
            "/api/auth/login",
            data=json.dumps({"email": "liya@example.com", "password": "newstrongpass2"}),
            content_type="application/json",
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertTrue(login_response.json()["ok"])

    def test_profile_update_and_change_password_apis(self):
        signup_response = self.client.post(
            "/api/auth/signup",
            data=json.dumps(
                {
                    "firstName": "Profile",
                    "lastName": "Owner",
                    "email": "profile-owner@example.com",
                    "password": "strongpass1",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(signup_response.status_code, 201)
        token = signup_response.json()["token"]

        update_response = self.client.put(
            "/api/profile/update",
            data=json.dumps(
                {
                    "firstName": "Updated",
                    "lastName": "Owner",
                    "username": "updated.owner",
                    "bio": "Building the SkillForge profile API.",
                }
            ),
            content_type="application/json",
            **self.auth_headers(token),
        )
        self.assertEqual(update_response.status_code, 200)
        updated_user = update_response.json()["user"]
        self.assertEqual(updated_user["firstName"], "Updated")
        self.assertEqual(updated_user["username"], "updated.owner")

        profile_response = self.client.get("/api/profile", **self.auth_headers(token))
        self.assertEqual(profile_response.status_code, 200)
        self.assertEqual(profile_response.json()["user"]["bio"], "Building the SkillForge profile API.")

        change_password_response = self.client.post(
            "/api/change-password",
            data=json.dumps({"currentPassword": "strongpass1", "newPassword": "strongpass2"}),
            content_type="application/json",
            **self.auth_headers(token),
        )
        self.assertEqual(change_password_response.status_code, 200)
        self.assertIn("token", change_password_response.json())

        fresh_client = Client()
        login_response = fresh_client.post(
            "/api/login",
            data=json.dumps({"email": "profile-owner@example.com", "password": "strongpass2"}),
            content_type="application/json",
        )
        self.assertEqual(login_response.status_code, 200)

    def test_profile_management_supports_avatar_social_links_and_two_factor_preferences(self):
        signup_response = self.client.post(
            "/api/auth/signup",
            data=json.dumps(
                {
                    "firstName": "Security",
                    "lastName": "Student",
                    "email": "security-student@example.com",
                    "password": "strongpass1",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(signup_response.status_code, 201)
        token = signup_response.json()["token"]

        update_response = self.client.put(
            "/api/profile/update",
            data=json.dumps(
                {
                    "avatar": "https://example.com/avatar.png",
                    "bio": "I want a strong account profile.",
                    "socialLinks": {"github": "https://github.com/security-student"},
                    "twoFactorEnabled": True,
                    "twoFactorMethod": "email_otp",
                }
            ),
            content_type="application/json",
            **self.auth_headers(token),
        )
        self.assertEqual(update_response.status_code, 200)
        updated_user = update_response.json()["user"]
        self.assertEqual(updated_user["avatar"], "https://example.com/avatar.png")
        self.assertEqual(updated_user["bio"], "I want a strong account profile.")
        self.assertEqual(updated_user["socialLinks"]["github"], "https://github.com/security-student")
        self.assertTrue(updated_user["twoFactorEnabled"])

        fresh_client = Client()
        login_response = fresh_client.post(
            "/api/auth/login",
            data=json.dumps({"email": "security-student@example.com", "password": "strongpass1"}),
            content_type="application/json",
        )
        self.assertEqual(login_response.status_code, 202)
        challenge = login_response.json()
        verify_response = fresh_client.post(
            "/api/auth/2fa/verify",
            data=json.dumps({"challengeId": challenge["challengeId"], "code": challenge["otpCode"]}),
            content_type="application/json",
        )
        self.assertEqual(verify_response.status_code, 200)

    def test_security_headers_and_csrf_cookie_are_sent(self):
        index_response = self.client.get("/")
        self.assertEqual(index_response.status_code, 200)
        self.assertIn("Content-Security-Policy", index_response.headers)
        self.assertEqual(index_response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(index_response.headers["Referrer-Policy"], "same-origin")
        self.assertEqual(index_response.headers["Permissions-Policy"], "camera=(), microphone=(), geolocation=()")
        self.assertIn("csrftoken", self.client.cookies)

        signup_response = self.client.post(
            "/api/auth/signup",
            data=json.dumps(
                {
                    "firstName": "Header",
                    "lastName": "Tester",
                    "email": "header-tester@example.com",
                    "password": "strongpass1",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(signup_response.status_code, 201)
        self.assertEqual(signup_response.headers["Cache-Control"], "no-store")

    def test_expired_access_token_is_rejected(self):
        User = get_user_model()
        user = User.objects.create_user(email="expired-token@example.com", password="strongpass1")
        issued_at = timezone.now() - timedelta(minutes=20)
        expired_payload = {
            "iss": JWT_ISSUER,
            "sub": str(user.pk),
            "email": user.email,
            "role": user.role,
            "type": "access",
            "jti": uuid.uuid4().hex,
            "ver": auth_version_for_user(user),
            "iat": int(issued_at.timestamp()),
            "exp": int((issued_at + timedelta(minutes=1)).timestamp()),
        }
        expired_token = jwt.encode(expired_payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)

        response = self.client.get("/api/profile", **self.auth_headers(expired_token))
        self.assertEqual(response.status_code, 401)

    def test_public_alias_endpoints_cover_register_verify_refresh_and_reset(self):
        register_response = self.client.post(
            "/api/register",
            data=json.dumps(
                {
                    "firstName": "Alias",
                    "lastName": "Flow",
                    "email": "alias-flow@example.com",
                    "password": "strongpass1",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(register_response.status_code, 201)
        register_payload = register_response.json()

        verify_response = self.client.post(
            "/api/verify-email",
            data=json.dumps({"token": register_payload["verificationToken"]}),
            content_type="application/json",
        )
        self.assertEqual(verify_response.status_code, 200)
        self.assertTrue(verify_response.json()["user"]["verified"])

        refresh_response = self.client.post("/api/refresh-token", data=json.dumps({}), content_type="application/json")
        self.assertEqual(refresh_response.status_code, 200)

        forgot_response = self.client.post(
            "/api/forgot-password",
            data=json.dumps({"email": "alias-flow@example.com"}),
            content_type="application/json",
        )
        self.assertEqual(forgot_response.status_code, 200)
        reset_payload = forgot_response.json()
        self.assertIn("resetToken", reset_payload)

        reset_response = self.client.post(
            "/api/reset-password",
            data=json.dumps({"token": reset_payload["resetToken"], "password": "strongpass2"}),
            content_type="application/json",
        )
        self.assertEqual(reset_response.status_code, 200)

        login_response = self.client.post(
            "/api/login",
            data=json.dumps({"email": "alias-flow@example.com", "password": "strongpass2"}),
            content_type="application/json",
        )
        self.assertEqual(login_response.status_code, 200)

    def test_admin_user_management_apis(self):
        User = get_user_model()
        admin = User.objects.create_superuser(email="admin-api@example.com", password="strongpass1")
        target = User.objects.create_user(
            email="target-user@example.com",
            password="strongpass1",
            first_name="Target",
            last_name="User",
            role="student",
        )
        self.client.force_login(admin)

        list_response = self.client.get("/api/users")
        self.assertEqual(list_response.status_code, 200)
        self.assertGreaterEqual(list_response.json()["count"], 1)

        suspend_response = self.client.patch(
            "/api/users/suspend",
            data=json.dumps({"userId": str(target.pk), "suspended": True}),
            content_type="application/json",
        )
        self.assertEqual(suspend_response.status_code, 200)
        target.refresh_from_db()
        self.assertFalse(target.is_active)
        self.assertEqual(target.status, target.Status.SUSPENDED)

        verify_response = self.client.patch(
            "/api/users/verify",
            data=json.dumps({"userId": str(target.pk)}),
            content_type="application/json",
        )
        self.assertEqual(verify_response.status_code, 200)
        target.refresh_from_db()
        self.assertTrue(target.is_email_verified)

        role_response = self.client.patch(
            "/api/users/change-role",
            data=json.dumps({"userId": str(target.pk), "role": "instructor"}),
            content_type="application/json",
        )
        self.assertEqual(role_response.status_code, 200)
        target.refresh_from_db()
        self.assertEqual(target.role, target.Role.INSTRUCTOR)
        self.assertTrue(hasattr(target, "instructor_profile"))
        self.assertTrue(models.AuthAuditLog.objects.filter(user=target, action="admin.user_suspend").exists())
        self.assertTrue(models.AuthAuditLog.objects.filter(user=target, action="admin.user_verify").exists())
        self.assertTrue(models.AuthAuditLog.objects.filter(user=target, action="admin.user_change_role").exists())

    def test_student_cannot_access_admin_user_api(self):
        signup_response = self.client.post(
            "/api/auth/signup",
            data=json.dumps(
                {
                    "firstName": "Student",
                    "lastName": "Blocked",
                    "email": "student-blocked-admin@example.com",
                    "password": "strongpass1",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(signup_response.status_code, 201)
        token = signup_response.json()["token"]

        response = self.client.get("/api/users", **self.auth_headers(token))
        self.assertEqual(response.status_code, 403)

    def test_refresh_token_reuse_revokes_the_entire_family(self):
        signup_response = self.client.post(
            "/api/auth/signup",
            data=json.dumps(
                {
                    "firstName": "Refresh",
                    "lastName": "Tester",
                    "email": "refresh@example.com",
                    "password": "strongpass1",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(signup_response.status_code, 201)
        original_refresh = self.client.cookies[AUTH_COOKIE_NAME].value

        first_refresh = self.client.post("/api/auth/refresh", data=json.dumps({}), content_type="application/json")
        self.assertEqual(first_refresh.status_code, 200)
        rotated_refresh = self.client.cookies[AUTH_COOKIE_NAME].value
        self.assertNotEqual(original_refresh, rotated_refresh)

        replay_client = Client()
        replay_response = replay_client.post(
            "/api/auth/refresh",
            data=json.dumps({"refreshToken": original_refresh}),
            content_type="application/json",
        )
        self.assertEqual(replay_response.status_code, 401)

        family_revoked_response = self.client.post("/api/auth/refresh", data=json.dumps({}), content_type="application/json")
        self.assertEqual(family_revoked_response.status_code, 401)

    def test_learning_workflows_persist_through_api(self):
        enrollment_response = self.client.post(
            "/api/enrollments",
            data=json.dumps({"courseId": "claude-ai-engineering", "email": "demo@skillforge.local"}),
            content_type="application/json",
        )
        self.assertEqual(enrollment_response.status_code, 201)

        wishlist_response = self.client.post(
            "/api/wishlist",
            data=json.dumps({"courseId": "claude-ai-engineering", "email": "demo@skillforge.local", "saved": True}),
            content_type="application/json",
        )
        self.assertEqual(wishlist_response.status_code, 200)
        self.assertEqual(wishlist_response.json()["courseIds"], ["claude-ai-engineering"])

        notes_response = self.client.post(
            "/api/notes",
            data=json.dumps(
                {
                    "courseId": "claude-ai-engineering",
                    "email": "demo@skillforge.local",
                    "notes": "Remember to turn the API contract into real handlers.",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(notes_response.status_code, 200)

        ai_response = self.client.post(
            "/api/ai/tutor",
            data=json.dumps({"courseId": "claude-ai-engineering", "prompt": "How should I start my API integration?"}),
            content_type="application/json",
        )
        self.assertEqual(ai_response.status_code, 200)
        self.assertIn("Start by defining one job", ai_response.json()["reply"])

    def test_course_categories_and_structured_course_data_are_available(self):
        categories_response = self.client.get("/api/categories")
        self.assertEqual(categories_response.status_code, 200)
        categories_payload = categories_response.json()
        self.assertTrue(categories_payload["ok"])
        self.assertGreaterEqual(categories_payload["count"], 6)

        ai_category = next(category for category in categories_payload["categories"] if category["slug"] == "ai")
        self.assertGreaterEqual(ai_category["courseCount"], 1)

        detail_response = self.client.get("/api/courses/claude-ai-engineering")
        self.assertEqual(detail_response.status_code, 200)
        detail = detail_response.json()["course"]
        self.assertEqual(detail["categoryDetail"]["slug"], "ai")
        self.assertGreaterEqual(detail["moduleCount"], 1)
        self.assertGreaterEqual(detail["freeLessonCount"], 1)
        self.assertTrue(detail["modules"][0]["lessons"][0]["id"].startswith("claude-ai-engineering-"))

    def test_course_list_supports_category_and_search_filters(self):
        category_response = self.client.get("/api/courses?category=ai")
        self.assertEqual(category_response.status_code, 200)
        category_payload = category_response.json()
        self.assertGreaterEqual(category_payload["count"], 1)
        self.assertTrue(all(course["cat"] == "ai" for course in category_payload["courses"]))

        search_response = self.client.get("/api/courses?q=Claude")
        self.assertEqual(search_response.status_code, 200)
        search_payload = search_response.json()
        self.assertGreaterEqual(search_payload["count"], 1)
        self.assertTrue(any(course["id"] == "claude-ai-engineering" for course in search_payload["courses"]))

    def test_progress_updates_and_dashboard_tabs_persist(self):
        signup_response = self.client.post(
            "/api/auth/signup",
            data=json.dumps(
                {
                    "firstName": "Mimi",
                    "lastName": "Ali",
                    "email": "mimi@example.com",
                    "password": "strongpass1",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(signup_response.status_code, 201)
        token = signup_response.json()["token"]

        enrollment_response = self.client.post(
            "/api/enrollments",
            data=json.dumps({"courseId": "claude-ai-engineering"}),
            content_type="application/json",
            **self.auth_headers(token),
        )
        self.assertEqual(enrollment_response.status_code, 201)

        progress_response = self.client.post(
            "/api/enrollments/progress",
            data=json.dumps({"courseId": "claude-ai-engineering", "progressPercent": 72}),
            content_type="application/json",
            **self.auth_headers(token),
        )
        self.assertEqual(progress_response.status_code, 200)
        self.assertEqual(progress_response.json()["enrollment"]["progressPercent"], 72)

        enrollment_list_response = self.client.get("/api/enrollments", **self.auth_headers(token))
        self.assertEqual(enrollment_list_response.status_code, 200)
        enrollments = enrollment_list_response.json()["enrollments"]
        self.assertEqual(enrollments[0]["courseId"], "claude-ai-engineering")
        self.assertEqual(enrollments[0]["progressPercent"], 72)

        dashboard_tab_response = self.client.post(
            "/api/dashboard/tab",
            data=json.dumps({"tab": "progress"}),
            content_type="application/json",
            **self.auth_headers(token),
        )
        self.assertEqual(dashboard_tab_response.status_code, 200)

        dashboard_tab_get_response = self.client.get("/api/dashboard/tab", **self.auth_headers(token))
        self.assertEqual(dashboard_tab_get_response.status_code, 200)
        self.assertEqual(dashboard_tab_get_response.json()["selection"]["tab"], "progress")

    def test_lesson_progress_rolls_up_to_course_progress(self):
        signup_response = self.client.post(
            "/api/auth/signup",
            data=json.dumps(
                {
                    "firstName": "Lesson",
                    "lastName": "Tracker",
                    "email": "lesson-tracker@example.com",
                    "password": "strongpass1",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(signup_response.status_code, 201)
        token = signup_response.json()["token"]

        enroll_response = self.client.post(
            "/api/enrollments",
            data=json.dumps({"courseId": "claude-ai-engineering"}),
            content_type="application/json",
            **self.auth_headers(token),
        )
        self.assertEqual(enroll_response.status_code, 201)

        course_detail_response = self.client.get("/api/courses/claude-ai-engineering", **self.auth_headers(token))
        self.assertEqual(course_detail_response.status_code, 200)
        first_lesson_id = course_detail_response.json()["course"]["modules"][0]["lessons"][0]["id"]

        progress_response = self.client.post(
            "/api/enrollments/progress",
            data=json.dumps(
                {
                    "courseId": "claude-ai-engineering",
                    "lessonId": first_lesson_id,
                    "progressPercent": 100,
                    "positionSeconds": 420,
                }
            ),
            content_type="application/json",
            **self.auth_headers(token),
        )
        self.assertEqual(progress_response.status_code, 200)
        progress_payload = progress_response.json()
        self.assertEqual(progress_payload["lessonProgress"]["lessonId"], first_lesson_id)
        self.assertEqual(progress_payload["lessonProgress"]["progressPercent"], 100)
        self.assertGreater(progress_payload["enrollment"]["progressPercent"], 0)
        self.assertEqual(progress_payload["enrollment"]["currentLessonId"], first_lesson_id)
        self.assertEqual(progress_payload["enrollment"]["lessonProgress"][0]["lessonId"], first_lesson_id)

    def test_instructor_endpoints_create_and_update_courses(self):
        create_response = self.client.post(
            "/api/instructor/courses",
            data=json.dumps(
                {
                    "course": {
                        "title": "Backend Systems for Creators",
                        "overview": "Build a practical backend around a frontend-first product.",
                        "instructor": "Yonas Tesfaye",
                        "cat": "ai",
                        "price": 2200,
                        "lessons": 14,
                        "hours": 7,
                        "level": "Intermediate",
                    }
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 401)

        User = get_user_model()
        instructor = User.objects.create_user(
            email="course-author@example.com",
            password="strongpass1",
            first_name="Course",
            last_name="Author",
            role="instructor",
        )
        self.client.force_login(instructor)
        create_response = self.client.post(
            "/api/instructor/courses",
            data=json.dumps(
                {
                    "course": {
                        "title": "Backend Systems for Creators",
                        "overview": "Build a practical backend around a frontend-first product.",
                        "instructor": "Yonas Tesfaye",
                        "cat": "ai",
                        "price": 2200,
                        "lessons": 14,
                        "hours": 7,
                        "level": "Intermediate",
                    }
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        created = create_response.json()
        self.assertTrue(created["ok"])
        self.assertEqual(created["course"]["title"], "Backend Systems for Creators")
        self.assertTrue(created["course"]["isCustom"])

        thumbnail_response = self.client.post(
            "/api/instructor/courses/thumbnail",
            data=json.dumps({"courseId": created["course"]["id"], "thumbnail": "https://example.com/thumbnail.png"}),
            content_type="application/json",
        )
        self.assertEqual(thumbnail_response.status_code, 200)
        self.assertEqual(thumbnail_response.json()["course"]["thumbnail"], "https://example.com/thumbnail.png")
        self.assertTrue(thumbnail_response.json()["course"]["isCustom"])
        self.assertTrue(models.Course.objects.filter(slug=created["course"]["id"]).exists())
        list_response = self.client.get("/api/courses")
        self.assertEqual(list_response.status_code, 200)
        self.assertTrue(any(course["id"] == created["course"]["id"] for course in list_response.json()["courses"]))

        self.client.logout()
        student = User.objects.create_user(email="student-blocked@example.com", password="strongpass1", role="student")
        self.client.force_login(student)
        forbidden_response = self.client.post(
            "/api/instructor/courses",
            data=json.dumps(
                {
                    "course": {
                        "title": "Blocked Course",
                        "overview": "This should not be created by a student.",
                        "instructor": "Blocked User",
                    }
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(forbidden_response.status_code, 403)

    def test_instructor_course_creation_persists_modules_and_lessons(self):
        User = get_user_model()
        instructor = User.objects.create_user(
            email="structured-author@example.com",
            password="strongpass1",
            first_name="Structured",
            last_name="Author",
            role="instructor",
        )
        self.client.force_login(instructor)
        create_response = self.client.post(
            "/api/instructor/courses",
            data=json.dumps(
                {
                    "course": {
                        "title": "Structured LMS Backend",
                        "overview": "A full backend course with real modules and lessons.",
                        "instructor": "Structured Author",
                        "cat": "ai",
                        "price": 2500,
                        "level": "Intermediate",
                        "modules": [
                            {
                                "title": "Planning",
                                "duration": "45m",
                                "lessons": [
                                    {"title": "Architecture decisions", "duration": "12:00", "type": "video", "free": True},
                                    {"title": "Quiz checkpoint", "duration": "6 min", "type": "quiz"},
                                ],
                            },
                            {
                                "title": "Implementation",
                                "duration": "1h 10m",
                                "lessons": [
                                    {"title": "Build the API layer", "duration": "24:00", "type": "video"},
                                ],
                            },
                        ],
                    }
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        created_course = create_response.json()["course"]
        self.assertEqual(created_course["moduleCount"], 2)
        self.assertEqual(created_course["lessons"], 3)

        course = models.Course.objects.get(slug=created_course["id"])
        self.assertEqual(course.created_by, instructor)
        self.assertEqual(course.course_modules.count(), 2)
        self.assertEqual(models.CourseLesson.objects.filter(module__course=course).count(), 3)

    def test_instructor_can_upload_lesson_asset_for_player(self):
        User = get_user_model()
        instructor = User.objects.create_user(
            email="asset-author@example.com",
            password="strongpass1",
            first_name="Asset",
            last_name="Author",
            role="instructor",
        )
        self.client.force_login(instructor)
        create_response = self.client.post(
            "/api/instructor/courses",
            data=json.dumps(
                {
                    "course": {
                        "title": "Playable Video Course",
                        "overview": "A course that should play uploaded media.",
                        "instructor": "Asset Author",
                        "cat": "video",
                        "price": 1800,
                        "hours": 3,
                        "modules": [
                            {
                                "title": "Launch",
                                "duration": "30m",
                                "lessons": [
                                    {"title": "Watch this first", "duration": "08:00", "type": "video"},
                                ],
                            }
                        ],
                    }
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        course_payload = create_response.json()["course"]
        lesson_id = course_payload["modules"][0]["lessons"][0]["id"]

        with TemporaryDirectory() as media_root:
            with self.settings(MEDIA_ROOT=media_root):
                upload = SimpleUploadedFile("intro.mp4", b"fake-video-content", content_type="video/mp4")
                upload_response = self.client.post(
                    "/api/instructor/courses/assets",
                    data={"courseId": course_payload["id"], "lessonId": lesson_id, "file": upload},
                )
                self.assertEqual(upload_response.status_code, 201)
                uploaded_payload = upload_response.json()
                self.assertTrue(uploaded_payload["asset"]["attachedToLesson"])
                self.assertIn("/media/course-assets/", uploaded_payload["asset"]["url"])
                self.assertEqual(uploaded_payload["course"]["modules"][0]["lessons"][0]["assetUrl"], uploaded_payload["asset"]["url"])

                lesson = models.CourseLesson.objects.get(lesson_key=lesson_id)
                self.assertEqual(lesson.asset_url, uploaded_payload["asset"]["url"])

    def test_instructor_cannot_modify_another_instructors_course(self):
        User = get_user_model()
        owner = User.objects.create_user(email="owner-course@example.com", password="strongpass1", role="instructor")
        other = User.objects.create_user(email="other-course@example.com", password="strongpass1", role="instructor")
        owned_course, _created = models.Course.objects.get_or_create(
            slug="owner-only-course",
            defaults={
                "category": "ai",
                "mark": "AI",
                "title": "Owner Only Course",
                "instructor_name": "Owner Instructor",
                "price_value": 1000,
                "original_price_value": 1800,
                "overview": "Only the creator should be able to change this.",
                "track": "AI Engineering",
            },
        )
        owned_course.created_by = owner
        owned_course.save(update_fields=["created_by", "updated_at"])

        self.client.force_login(other)
        forbidden_response = self.client.post(
            "/api/instructor/courses/thumbnail",
            data=json.dumps({"courseId": "owner-only-course", "thumbnail": "https://example.com/blocked.png"}),
            content_type="application/json",
        )
        self.assertEqual(forbidden_response.status_code, 403)
