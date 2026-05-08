from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase

from . import models
from .services import AUTH_COOKIE_NAME, seed_database


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
        self.assertIn("resetToken", reset_request)

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

        thumbnail_response = self.client.post(
            "/api/instructor/courses/thumbnail",
            data=json.dumps({"courseId": created["course"]["id"], "thumbnail": "https://example.com/thumbnail.png"}),
            content_type="application/json",
        )
        self.assertEqual(thumbnail_response.status_code, 200)
        self.assertEqual(thumbnail_response.json()["course"]["thumbnail"], "https://example.com/thumbnail.png")
        self.assertTrue(models.Course.objects.filter(slug=created["course"]["id"]).exists())

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
