from __future__ import annotations

import json
from datetime import timedelta, timezone as dt_timezone
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model, login, logout
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone

from . import catalog, models
from .utils import DEFAULT_ACTOR_EMAIL, build_token, format_compact, format_number, normalize_email, slugify


AUTH_COOKIE_NAME = "skillforge_session"
SESSION_TTL_DAYS = 30
PASSWORD_RESET_TTL_MINUTES = 30
SEED_PATH = Path(__file__).resolve().parent / "data" / "seed_store.json"


def now():
    return timezone.now()


def isoformat_z(value):
    if not value:
        return None
    return value.astimezone(dt_timezone.utc).isoformat().replace("+00:00", "Z")


def load_seed_data() -> dict[str, Any]:
    with SEED_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def user_role(user) -> str:
    return "admin" if getattr(user, "is_staff", False) else "student"


def serialize_user(user) -> dict[str, Any]:
    return {
        "id": str(user.pk),
        "firstName": user.first_name,
        "lastName": user.last_name,
        "email": user.email,
        "role": user_role(user),
        "createdAt": isoformat_z(user.date_joined),
    }


def serialize_session(session: models.ApiSession | None) -> dict[str, Any] | None:
    if not session:
        return None
    return {
        "id": str(session.pk),
        "createdAt": isoformat_z(session.created_at),
        "expiresAt": isoformat_z(session.expires_at),
        "lastSeenAt": isoformat_z(session.last_seen_at),
        "revokedAt": isoformat_z(session.revoked_at),
    }


def serialize_course(course: models.Course) -> dict[str, Any]:
    return {
        "id": course.slug,
        "cat": course.category,
        "mark": course.mark,
        "title": course.title,
        "instructor": course.instructor_name,
        "rating": float(course.rating),
        "reviews": course.reviews_count,
        "reviewLabel": format_compact(course.reviews_count) if course.reviews_count else "New",
        "students": course.students_count,
        "studentsLabel": format_number(course.students_count),
        "price": format_number(course.price_value),
        "priceValue": course.price_value,
        "orig": format_number(course.original_price_value),
        "badge": course.badge,
        "badgeClass": course.badge_class,
        "lessons": course.lessons_count,
        "hours": course.hours,
        "level": course.level,
        "updated": course.updated_label,
        "updatedSort": course.updated_sort,
        "projects": course.projects_count,
        "gradient": course.gradient,
        "overview": course.overview,
        "thumbnail": course.thumbnail,
        "track": course.track,
        "requirements": course.requirements,
        "learn": course.learn,
        "resources": course.resources,
        "qa": course.qa,
        "modules": course.modules,
    }


def parse_course_input(source: dict[str, Any], existing: models.Course | None = None) -> dict[str, Any]:
    existing_payload = serialize_course(existing) if existing else None
    normalized = catalog.normalize_course_input(source, existing_payload)
    normalized = catalog.enrich_course(normalized)
    return normalized


def apply_course_payload(course: models.Course, payload: dict[str, Any], *, is_custom: bool, created_by=None) -> models.Course:
    course.slug = payload["id"]
    course.category = payload["cat"]
    course.mark = payload["mark"]
    course.title = payload["title"]
    course.instructor_name = payload["instructor"]
    course.rating = payload["rating"]
    course.reviews_count = payload["reviews"]
    course.students_count = payload["students"]
    course.price_value = payload["priceValue"]
    course.original_price_value = int(str(payload["orig"]).replace(",", ""))
    course.badge = payload["badge"]
    course.badge_class = payload["badgeClass"]
    course.lessons_count = payload["lessons"]
    course.hours = payload["hours"]
    course.level = payload["level"]
    course.updated_label = payload["updated"]
    course.updated_sort = payload["updatedSort"]
    course.projects_count = payload["projects"]
    course.gradient = payload["gradient"]
    course.overview = payload["overview"]
    course.thumbnail = payload["thumbnail"]
    course.track = payload["track"]
    course.requirements = payload["requirements"]
    course.learn = payload["learn"]
    course.resources = payload["resources"]
    course.qa = payload["qa"]
    course.modules = payload["modules"]
    course.is_custom = is_custom
    course.created_by = created_by if is_custom else None
    return course


@transaction.atomic
def seed_database(force: bool = False) -> None:
    User = get_user_model()
    seed = load_seed_data()

    demo = seed.get("users", [{}])[0]
    demo_email = normalize_email(demo.get("email") or "demo@skillforge.local")
    demo_user, created = User.objects.get_or_create(
        username=demo_email,
        defaults={
            "email": demo_email,
            "first_name": demo.get("firstName", "Demo"),
            "last_name": demo.get("lastName", "Learner"),
        },
    )
    if created or force:
        demo_user.email = demo_email
        demo_user.first_name = demo.get("firstName", "Demo")
        demo_user.last_name = demo.get("lastName", "Learner")
        demo_user.set_password("skillforge123")
        demo_user.save()

    for raw_course in seed.get("courses", {}).get("base", []):
        payload = catalog.enrich_course(raw_course)
        course, _created = models.Course.objects.get_or_create(slug=payload["id"])
        apply_course_payload(course, payload, is_custom=False)
        course.save()

    for raw_coupon in seed.get("coupons", []):
        models.Coupon.objects.update_or_create(
            code=raw_coupon["code"],
            defaults={
                "type": raw_coupon["type"],
                "value": raw_coupon["value"],
                "active": raw_coupon.get("active", True),
                "description": raw_coupon.get("description", ""),
            },
        )

    for raw_notification in seed.get("notifications", []):
        models.PlatformNotification.objects.get_or_create(
            title=raw_notification["title"],
            message=raw_notification["message"],
            defaults={
                "audience_scope": models.PlatformNotification.SCOPE_ALL
                if raw_notification.get("audience") == "all"
                else models.PlatformNotification.SCOPE_EMAIL,
                "audience_email": "" if raw_notification.get("audience") == "all" else raw_notification.get("audience", ""),
            },
        )


def set_auth_cookie(response: HttpResponse, token: str) -> HttpResponse:
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=SESSION_TTL_DAYS * 24 * 60 * 60,
        httponly=True,
        samesite="Lax",
        secure=not settings.DEBUG,
        path="/",
    )
    return response


def clear_auth_cookie(response: HttpResponse) -> HttpResponse:
    response.delete_cookie(AUTH_COOKIE_NAME, path="/", samesite="Lax")
    return response


def extract_session_token(request, data: dict[str, Any] | None = None) -> str:
    data = data or {}
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    if request.COOKIES.get(AUTH_COOKIE_NAME):
        return str(request.COOKIES[AUTH_COOKIE_NAME]).strip()
    token = data.get("token") or request.GET.get("token")
    return str(token).strip() if token else ""


def create_api_session(user, request) -> models.ApiSession:
    return models.ApiSession.objects.create(
        user=user,
        token=build_token("session"),
        expires_at=now() + timedelta(days=SESSION_TTL_DAYS),
        last_seen_at=now(),
        user_agent=request.headers.get("User-Agent", ""),
        ip_address=request.META.get("REMOTE_ADDR", ""),
    )


def get_api_session(token: str | None) -> models.ApiSession | None:
    if not token:
        return None
    session = (
        models.ApiSession.objects.select_related("user")
        .filter(token=token)
        .first()
    )
    if not session:
        return None
    if session.revoked_at or session.expires_at <= now():
        return None
    return session


def touch_api_session(session: models.ApiSession | None) -> None:
    if session:
        session.last_seen_at = now()
        session.save(update_fields=["last_seen_at"])


def get_authenticated_context(request, data: dict[str, Any] | None = None):
    if getattr(request, "user", None) is not None and request.user.is_authenticated:
        token = extract_session_token(request, data)
        session = get_api_session(token) if token else None
        touch_api_session(session)
        return request.user, session
    token = extract_session_token(request, data)
    session = get_api_session(token)
    if not session:
        return None, None
    touch_api_session(session)
    return session.user, session


def resolve_actor(request, data: dict[str, Any] | None = None, query: dict[str, Any] | None = None):
    user, session = get_authenticated_context(request, data)
    if user:
        return user, user.email or DEFAULT_ACTOR_EMAIL, session
    data = data or {}
    query = query or {}
    email = normalize_email(data.get("email") or data.get("userEmail") or data.get("actorEmail") or query.get("email"))
    return None, email or DEFAULT_ACTOR_EMAIL, None


def log_in_user(request, user):
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")


def log_out_user(request):
    logout(request)


def revoke_sessions(user, token: str | None = None, all_sessions: bool = False):
    queryset = models.ApiSession.objects.filter(user=user, revoked_at__isnull=True)
    if not all_sessions and token:
        queryset = queryset.filter(token=token)
    queryset.update(revoked_at=now())


def create_password_reset_token(user):
    return models.PasswordResetToken.objects.create(
        user=user,
        token=build_token("reset"),
        expires_at=now() + timedelta(minutes=PASSWORD_RESET_TTL_MINUTES),
    )


def active_notifications_for(email: str, user=None):
    queryset = models.PlatformNotification.objects.all()
    user_ids = [user.pk] if user else []
    return queryset.filter(
        Q(audience_scope=models.PlatformNotification.SCOPE_ALL)
        | Q(audience_scope=models.PlatformNotification.SCOPE_EMAIL, audience_email=email)
        | Q(audience_scope=models.PlatformNotification.SCOPE_USER, audience_user_id__in=user_ids)
    )


def course_by_slug_or_404(course_slug: str) -> models.Course | None:
    return models.Course.objects.filter(slug=course_slug).first()


def create_or_update_course_from_input(input_course: dict[str, Any], user=None) -> tuple[models.Course, bool]:
    requested_slug = str(input_course.get("id", "")).strip()
    title = str(input_course.get("title", "")).strip()
    if requested_slug:
        course = models.Course.objects.filter(slug=requested_slug).first()
    else:
        course = None
    normalized = parse_course_input(input_course, existing=course)
    slug_value = normalized["id"] or slugify(title)
    base_slug = slug_value
    suffix = 2
    while models.Course.objects.exclude(pk=getattr(course, "pk", None)).filter(slug=slug_value).exists():
        slug_value = f"{base_slug}-{suffix}"
        suffix += 1
    normalized["id"] = slug_value
    created = course is None
    course = course or models.Course(slug=slug_value)
    apply_course_payload(course, normalized, is_custom=True, created_by=user)
    course.save()
    return course, created
