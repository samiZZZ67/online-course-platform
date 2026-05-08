from __future__ import annotations

import json

from django.test import Client, TestCase

from . import models
from .services import seed_database


class SkillForgeApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_database(force=True)

    def setUp(self):
        self.client = Client()

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
        self.assertIn("skillforge_session", self.client.cookies)
        self.assertIn("session", signup)

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
        self.assertIn("session", login)

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

        me_response = self.client.get("/api/auth/me")
        self.assertEqual(me_response.status_code, 200)
        me = me_response.json()
        self.assertTrue(me["authenticated"])
        self.assertEqual(me["user"]["email"], "liya@example.com")

        bearer_client = Client()
        bearer_response = bearer_client.get("/api/auth/me", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(bearer_response.status_code, 200)
        self.assertEqual(bearer_response.json()["user"]["email"], "liya@example.com")

        logout_response = self.client.post("/api/auth/logout", data=json.dumps({}), content_type="application/json")
        self.assertEqual(logout_response.status_code, 200)
        self.assertTrue(logout_response.json()["loggedOut"])

        me_after_logout = self.client.get("/api/auth/me")
        self.assertEqual(me_after_logout.status_code, 401)

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

        fresh_client = Client()
        login_response = fresh_client.post(
            "/api/auth/login",
            data=json.dumps({"email": "liya@example.com", "password": "newstrongpass2"}),
            content_type="application/json",
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertTrue(login_response.json()["ok"])

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
