from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import Client, SimpleTestCase


class SkillForgeApiTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.temp_dir = TemporaryDirectory()
        cls.original_store_path = os.environ.get("SKILLFORGE_STORE_PATH")
        cls.store_path = Path(cls.temp_dir.name) / "store.json"
        os.environ["SKILLFORGE_STORE_PATH"] = str(cls.store_path)
        cls.seed_path = Path(__file__).resolve().parent / "data" / "store.seed.json"

    @classmethod
    def tearDownClass(cls):
        if cls.original_store_path is None:
            os.environ.pop("SKILLFORGE_STORE_PATH", None)
        else:
            os.environ["SKILLFORGE_STORE_PATH"] = cls.original_store_path
        cls.temp_dir.cleanup()
        super().tearDownClass()

    def setUp(self):
        shutil.copyfile(self.seed_path, self.store_path)
        self.client = Client()

    def test_health_and_courses_endpoints_are_available(self):
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

        login_response = self.client.post(
            "/api/auth/login",
            data=json.dumps({"email": "abebe@example.com", "password": "strongpass1"}),
            content_type="application/json",
        )
        self.assertEqual(login_response.status_code, 200)
        login = login_response.json()
        self.assertTrue(login["ok"])
        self.assertIn("token", login)

    def test_learning_workflows_persist_through_api(self):
        enrollment_response = self.client.post(
            "/api/enrollments",
            data=json.dumps({"courseId": "claude-ai-engineering", "email": "demo@skillforge.local"}),
            content_type="application/json",
        )
        self.assertEqual(enrollment_response.status_code, 201)

        wishlist_response = self.client.post(
            "/api/wishlist",
            data=json.dumps(
                {
                    "courseId": "claude-ai-engineering",
                    "email": "demo@skillforge.local",
                    "saved": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(wishlist_response.status_code, 200)
        wishlist = wishlist_response.json()
        self.assertEqual(wishlist["courseIds"], ["claude-ai-engineering"])

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
            data=json.dumps(
                {
                    "courseId": "claude-ai-engineering",
                    "prompt": "How should I start my API integration?",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(ai_response.status_code, 200)
        ai = ai_response.json()
        self.assertIn("Start by defining one job", ai["reply"])

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
            data=json.dumps(
                {
                    "courseId": created["course"]["id"],
                    "thumbnail": "https://example.com/thumbnail.png",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(thumbnail_response.status_code, 200)
        thumbnail = thumbnail_response.json()
        self.assertEqual(thumbnail["course"]["thumbnail"], "https://example.com/thumbnail.png")
