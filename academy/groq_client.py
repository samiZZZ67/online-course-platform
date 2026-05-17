from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from django.conf import settings


class GroqConfigurationError(Exception):
    pass


class GroqAPIError(Exception):
    pass


@dataclass(frozen=True)
class GroqTutorResult:
    reply: str
    model: str
    provider: str = "groq"


def build_tutor_messages(prompt: str, course: dict[str, Any] | None = None, lesson_id: str = "") -> list[dict[str, str]]:
    course = course or {}
    course_context = {
        "courseId": course.get("id"),
        "title": course.get("title"),
        "track": course.get("track"),
        "level": course.get("level"),
        "overview": course.get("overview"),
        "lessonId": lesson_id or None,
    }
    return [
        {
            "role": "system",
            "content": (
                "You are SkillForge's AI tutor. Help learners with concise, practical guidance. "
                "Anchor answers in the course context when it is provided. Prefer concrete next steps, "
                "small examples, and a friendly teaching tone. Do not invent private user data."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "course": {key: value for key, value in course_context.items() if value},
                    "question": prompt,
                },
                ensure_ascii=True,
            ),
        },
    ]


def ask_groq_tutor(prompt: str, *, course: dict[str, Any] | None = None, lesson_id: str = "") -> GroqTutorResult:
    api_key = getattr(settings, "GROQ_API_KEY", "").strip()
    if not api_key:
        raise GroqConfigurationError("GROQ_API_KEY is not configured.")

    model = getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile")
    payload = {
        "model": model,
        "messages": build_tutor_messages(prompt, course=course, lesson_id=lesson_id),
        "temperature": getattr(settings, "GROQ_TEMPERATURE", 0.35),
        "max_completion_tokens": getattr(settings, "GROQ_MAX_COMPLETION_TOKENS", 500),
    }
    base_url = getattr(settings, "GROQ_API_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    http_request = request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(http_request, timeout=getattr(settings, "GROQ_TIMEOUT_SECONDS", 20)) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GroqAPIError(f"Groq returned HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise GroqAPIError(f"Groq request failed: {exc.reason}") from exc
    except (TimeoutError, json.JSONDecodeError) as exc:
        raise GroqAPIError("Groq returned an invalid or timed out response.") from exc

    try:
        reply = response_payload["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError) as exc:
        raise GroqAPIError("Groq response did not include assistant content.") from exc

    if not reply:
        raise GroqAPIError("Groq returned an empty assistant response.")
    return GroqTutorResult(reply=reply, model=str(response_payload.get("model") or model))
