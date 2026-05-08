from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import timedelta, timezone as dt_timezone
from pathlib import Path
from typing import Any

import jwt
from accounts.models import EmailVerificationToken, RefreshToken
from accounts.permissions import build_user_capabilities, can_manage_instructor_content, user_role
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone

from . import catalog, models
from .utils import DEFAULT_ACTOR_EMAIL, build_token, format_compact, format_number, normalize_email, slugify


AUTH_COOKIE_NAME = "skillforge_session"
ACCESS_TOKEN_TTL_MINUTES = 15
REFRESH_TOKEN_TTL_DAYS = 14
REFRESH_SESSION_TTL_DAYS = 30
EMAIL_VERIFICATION_TTL_HOURS = 24
PASSWORD_RESET_TTL_MINUTES = 30
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "skillforge-django"
SEED_PATH = Path(__file__).resolve().parent / "data" / "seed_store.json"
AUTH_RATE_LIMITS = {
    "signup.ip": (8, 15 * 60),
    "signup.email": (4, 15 * 60),
    "login.ip": (12, 15 * 60),
    "login.email": (8, 15 * 60),
    "verify.request.ip": (6, 60 * 60),
    "verify.request.email": (3, 60 * 60),
    "password_reset.ip": (6, 60 * 60),
    "password_reset.email": (3, 60 * 60),
}


class AuthTokenError(Exception):
    pass


class RefreshTokenReuseDetected(AuthTokenError):
    pass


class VerificationTokenError(Exception):
    pass


class RateLimitExceeded(Exception):
    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after


def now():
    return timezone.now()


def isoformat_z(value):
    if not value:
        return None
    return value.astimezone(dt_timezone.utc).isoformat().replace("+00:00", "Z")


def load_seed_data() -> dict[str, Any]:
    with SEED_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def related_or_none(instance, attribute: str):
    try:
        return getattr(instance, attribute)
    except (AttributeError, ObjectDoesNotExist):
        return None


def serialize_student_profile(profile) -> dict[str, Any]:
    return {
        "learningStreakDays": profile.learning_streak_days,
        "completedCourses": profile.completed_courses_count,
        "currentCourses": profile.current_courses_count,
        "savedCourses": profile.saved_courses_count,
        "averageProgressPercent": profile.average_progress_percent,
        "totalLearningMinutes": profile.total_learning_minutes,
        "learningStatistics": profile.learning_statistics,
        "lastActivityAt": isoformat_z(profile.last_activity_at),
    }


def serialize_instructor_profile(profile) -> dict[str, Any]:
    return {
        "expertise": profile.expertise,
        "biography": profile.biography,
        "revenueTotal": float(profile.revenue_total),
        "publishedCourses": profile.published_courses_count,
        "totalStudentsTaught": profile.total_students_taught,
        "averageRating": float(profile.average_rating),
        "teachingStatistics": profile.teaching_statistics,
        "socialLinks": profile.social_links,
        "verifiedBadge": profile.is_verified_instructor,
        "verifiedAt": isoformat_z(profile.verified_at),
    }


def serialize_user(user) -> dict[str, Any]:
    student_profile = related_or_none(user, "student_profile")
    instructor_profile = related_or_none(user, "instructor_profile")
    return {
        "id": str(user.pk),
        "firstName": user.first_name,
        "lastName": user.last_name,
        "email": user.email,
        "username": getattr(user, "username", None),
        "avatar": getattr(user, "avatar", ""),
        "bio": getattr(user, "bio", ""),
        "role": user_role(user),
        "capabilities": build_user_capabilities(user),
        "verified": bool(getattr(user, "is_email_verified", False)),
        "status": getattr(user, "status", "active"),
        "studentProfile": serialize_student_profile(student_profile) if student_profile else None,
        "instructorProfile": serialize_instructor_profile(instructor_profile) if instructor_profile else None,
        "createdAt": isoformat_z(user.date_joined),
    }


def serialize_session(session: RefreshToken | None) -> dict[str, Any] | None:
    if not session:
        return None
    return {
        "id": str(session.pk),
        "familyId": str(session.family_id),
        "jti": session.jti,
        "createdAt": isoformat_z(session.created_at),
        "expiresAt": isoformat_z(session.expires_at),
        "lastSeenAt": isoformat_z(session.last_used_at),
        "sessionExpiresAt": isoformat_z(session.session_expires_at),
        "lastUsedAt": isoformat_z(session.last_used_at),
        "rotatedAt": isoformat_z(session.rotated_at),
        "revokedAt": isoformat_z(session.revoked_at),
        "reuseDetectedAt": isoformat_z(session.reuse_detected_at),
    }


def serialize_enrollment(enrollment: models.Enrollment) -> dict[str, Any]:
    return {
        "id": str(enrollment.pk),
        "courseId": enrollment.course.slug,
        "email": enrollment.email,
        "status": enrollment.status,
        "progressPercent": enrollment.progress_percent,
        "createdAt": isoformat_z(enrollment.created_at),
        "course": serialize_course(enrollment.course),
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
        email=demo_email,
        defaults={
            "email": demo_email,
            "username": "demo_learner",
            "first_name": demo.get("firstName", "Demo"),
            "last_name": demo.get("lastName", "Learner"),
            "role": "student",
            "status": "active",
            "is_email_verified": True,
        },
    )
    if created or force:
        demo_user.email = demo_email
        demo_user.username = demo_user.username or "demo_learner"
        demo_user.first_name = demo.get("firstName", "Demo")
        demo_user.last_name = demo.get("lastName", "Learner")
        if hasattr(demo_user, "role"):
            demo_user.role = "student"
        if hasattr(demo_user, "status"):
            demo_user.status = "active"
        if hasattr(demo_user, "is_email_verified"):
            demo_user.is_email_verified = True
        if hasattr(demo_user, "email_verified_at") and not demo_user.email_verified_at:
            demo_user.email_verified_at = now()
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


def auth_version_for_user(user) -> int:
    version_source = getattr(user, "last_password_changed_at", None) or getattr(user, "date_joined", None) or now()
    return int(version_source.timestamp())


def normalize_username(value: str | None) -> str:
    username = re.sub(r"[^a-z0-9_.]+", ".", str(value or "").strip().lower())
    username = re.sub(r"\.+", ".", username).strip("._")
    return username[:32]


def generate_unique_username(first_name: str, last_name: str, email: str) -> str:
    email_local = str(email or "").split("@", 1)[0]
    base = normalize_username(".".join(part for part in [first_name, last_name] if part))
    if not base:
        base = normalize_username(email_local)
    if not base:
        base = "skillforge.user"
    User = get_user_model()
    candidate = base[:32]
    suffix = 2
    while User.objects.filter(username=candidate).exists():
        suffix_text = f".{suffix}"
        trimmed_base = base[: max(1, 32 - len(suffix_text))]
        candidate = f"{trimmed_base}{suffix_text}"
        suffix += 1
    return candidate


def client_ip_for_request(request) -> str:
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _rate_limit_cache_key(scope: str, identifier: str) -> str:
    normalized_identifier = re.sub(r"[^a-z0-9_.:@-]+", "_", str(identifier or "anonymous").strip().lower())
    return f"skillforge:rate-limit:{scope}:{normalized_identifier}"


def enforce_rate_limit(scope: str, identifier: str, *, message: str):
    limit, window_seconds = getattr(settings, "AUTH_RATE_LIMITS", AUTH_RATE_LIMITS).get(scope, AUTH_RATE_LIMITS[scope])
    cache_key = _rate_limit_cache_key(scope, identifier)
    current_ts = int(now().timestamp())
    record = cache.get(cache_key)
    if not record or int(record.get("resetAt", 0)) <= current_ts:
        record = {"count": 0, "resetAt": current_ts + window_seconds}
    if int(record.get("count", 0)) >= limit:
        raise RateLimitExceeded(message, max(1, int(record["resetAt"]) - current_ts))
    record["count"] = int(record.get("count", 0)) + 1
    cache.set(cache_key, record, timeout=window_seconds)


def create_email_verification_token(user, request, *, invalidate_existing: bool = True):
    if invalidate_existing:
        EmailVerificationToken.objects.filter(user=user, consumed_at__isnull=True).update(consumed_at=now())
    raw_token = build_token("verify")
    token_record = EmailVerificationToken.objects.create(
        user=user,
        token_hash=hash_token(raw_token),
        expires_at=now() + timedelta(hours=EMAIL_VERIFICATION_TTL_HOURS),
        sent_to_email=user.email or "",
        created_ip=client_ip_for_request(request),
        created_user_agent=request.headers.get("User-Agent", ""),
    )
    return raw_token, token_record


def build_verification_url(request, raw_token: str) -> str:
    return request.build_absolute_uri(f"/api/auth/verify-email/confirm?token={raw_token}")


def send_verification_email(user, request, raw_token: str) -> str:
    verification_url = build_verification_url(request, raw_token)
    message = (
        "Welcome to SkillForge.\n\n"
        f"Verify your email by opening this link:\n{verification_url}\n\n"
        f"Verification token:\n{raw_token}\n"
    )
    send_mail(
        subject="Verify your SkillForge account",
        message=message,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@skillforge.local"),
        recipient_list=[user.email],
        fail_silently=True,
    )
    return verification_url


def issue_email_verification(user, request):
    raw_token, token_record = create_email_verification_token(user, request)
    verification_url = send_verification_email(user, request, raw_token)
    models.AuthAuditLog.objects.create(
        user=user,
        email=user.email or DEFAULT_ACTOR_EMAIL,
        action="verify_email.request",
        metadata={"verificationUrl": verification_url},
    )
    return raw_token, token_record, verification_url


def confirm_email_verification(raw_token: str):
    if not raw_token:
        raise VerificationTokenError("Verification token is required.")
    token_hash = hash_token(raw_token)
    token_record = EmailVerificationToken.objects.select_related("user").filter(token_hash=token_hash).first()
    if not token_record:
        raise VerificationTokenError("Verification token is invalid.")
    if token_record.consumed_at:
        raise VerificationTokenError("Verification token has already been used.")
    if token_record.expires_at <= now():
        raise VerificationTokenError("Verification token has expired.")
    consumed_at = now()
    token_record.consumed_at = consumed_at
    token_record.save(update_fields=["consumed_at", "updated_at"])
    EmailVerificationToken.objects.filter(user=token_record.user, consumed_at__isnull=True).exclude(pk=token_record.pk).update(consumed_at=consumed_at)
    if not token_record.user.is_email_verified:
        token_record.user.mark_email_verified()
    models.AuthAuditLog.objects.create(
        user=token_record.user,
        email=token_record.user.email or DEFAULT_ACTOR_EMAIL,
        action="verify_email.confirm",
    )
    return token_record.user, token_record


def build_access_token(user, issued_at=None) -> str:
    issued_at = issued_at or now()
    payload = {
        "iss": JWT_ISSUER,
        "sub": str(user.pk),
        "email": user.email,
        "role": user_role(user),
        "type": "access",
        "jti": uuid.uuid4().hex,
        "ver": auth_version_for_user(user),
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(raw_token: str, *, expected_type: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            raw_token,
            settings.SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub", "type", "jti", "ver"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthTokenError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthTokenError("Token is invalid.") from exc
    if payload.get("iss") != JWT_ISSUER or payload.get("type") != expected_type:
        raise AuthTokenError("Token is invalid.")
    return payload


def build_refresh_token(user, *, family_id, session_expires_at, issued_at=None) -> tuple[str, dict[str, Any], Any]:
    issued_at = issued_at or now()
    expires_at = min(issued_at + timedelta(days=REFRESH_TOKEN_TTL_DAYS), session_expires_at)
    payload = {
        "iss": JWT_ISSUER,
        "sub": str(user.pk),
        "type": "refresh",
        "jti": uuid.uuid4().hex,
        "family": str(family_id),
        "ver": auth_version_for_user(user),
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM), payload, expires_at


@transaction.atomic
def issue_auth_session(user, request, *, family_id=None, previous_session: RefreshToken | None = None, session_expires_at=None):
    issued_at = now()
    family_id = family_id or uuid.uuid4()
    session_expires_at = session_expires_at or issued_at + timedelta(days=REFRESH_SESSION_TTL_DAYS)
    if session_expires_at <= issued_at:
        raise AuthTokenError("Session has expired.")

    refresh_token, refresh_payload, refresh_expires_at = build_refresh_token(
        user,
        family_id=family_id,
        session_expires_at=session_expires_at,
        issued_at=issued_at,
    )
    refresh_session = RefreshToken.objects.create(
        user=user,
        jti=refresh_payload["jti"],
        family_id=family_id,
        token_hash=hash_token(refresh_token),
        expires_at=refresh_expires_at,
        session_expires_at=session_expires_at,
        created_ip=client_ip_for_request(request),
        created_user_agent=request.headers.get("User-Agent", ""),
    )
    if previous_session:
        previous_session.last_used_at = issued_at
        previous_session.rotated_at = issued_at
        previous_session.replaced_by = refresh_session
        previous_session.save(update_fields=["last_used_at", "rotated_at", "replaced_by", "updated_at"])

    access_token = build_access_token(user, issued_at=issued_at)
    return access_token, refresh_token, refresh_session


def set_auth_cookie(response: HttpResponse, token: str, *, expires_at=None) -> HttpResponse:
    max_age = REFRESH_TOKEN_TTL_DAYS * 24 * 60 * 60
    if expires_at:
        max_age = max(0, int((expires_at - now()).total_seconds()))
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=max_age,
        httponly=True,
        samesite="Lax",
        secure=not settings.DEBUG,
        path="/api/auth/",
    )
    return response


def clear_auth_cookie(response: HttpResponse) -> HttpResponse:
    response.delete_cookie(AUTH_COOKIE_NAME, path="/api/auth/", samesite="Lax")
    return response


def extract_access_token(request, data: dict[str, Any] | None = None) -> str:
    data = data or {}
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    token = data.get("accessToken") or data.get("token") or request.GET.get("token")
    return str(token).strip() if token else ""


def extract_refresh_token(request, data: dict[str, Any] | None = None) -> str:
    data = data or {}
    if request.COOKIES.get(AUTH_COOKIE_NAME):
        return str(request.COOKIES[AUTH_COOKIE_NAME]).strip()
    token = data.get("refreshToken") or request.GET.get("refreshToken")
    return str(token).strip() if token else ""


def revoke_refresh_family(family_id, *, reuse_detected=False) -> None:
    revoked_at = now()
    RefreshToken.objects.filter(family_id=family_id, revoked_at__isnull=True).update(revoked_at=revoked_at)
    if reuse_detected:
        RefreshToken.objects.filter(family_id=family_id, reuse_detected_at__isnull=True).update(reuse_detected_at=revoked_at)


def get_refresh_session_by_token(raw_token: str | None, *, allow_inactive: bool = False) -> RefreshToken | None:
    if not raw_token:
        return None
    payload = decode_token(raw_token, expected_type="refresh")
    session = RefreshToken.objects.select_related("user").filter(jti=payload["jti"]).first()
    if not session or str(session.user_id) != str(payload["sub"]):
        raise AuthTokenError("Refresh token is invalid.")
    if session.token_hash != hash_token(raw_token) or str(session.family_id) != str(payload.get("family", "")):
        if session:
            revoke_refresh_family(session.family_id, reuse_detected=True)
            models.AuthAuditLog.objects.create(
                user=session.user,
                email=session.user.email or DEFAULT_ACTOR_EMAIL,
                action="refresh.reuse_detected",
                metadata={"familyId": str(session.family_id), "jti": session.jti},
            )
        raise RefreshTokenReuseDetected("Refresh token reuse detected.")
    if auth_version_for_user(session.user) != int(payload["ver"]):
        revoke_sessions(session.user, all_sessions=True)
        raise AuthTokenError("Refresh token is no longer valid.")
    if not session.user.is_active or getattr(session.user, "status", "") in {"suspended", "deactivated"}:
        raise AuthTokenError("Account is not active.")
    if allow_inactive:
        return session
    if session.reuse_detected_at:
        raise RefreshTokenReuseDetected("Refresh token reuse detected.")
    if session.revoked_at:
        raise AuthTokenError("Refresh token has been revoked.")
    if session.rotated_at or session.replaced_by_id:
        revoke_refresh_family(session.family_id, reuse_detected=True)
        models.AuthAuditLog.objects.create(
            user=session.user,
            email=session.user.email or DEFAULT_ACTOR_EMAIL,
            action="refresh.reuse_detected",
            metadata={"familyId": str(session.family_id), "jti": session.jti},
        )
        raise RefreshTokenReuseDetected("Refresh token reuse detected.")
    if session.expires_at <= now() or session.session_expires_at <= now():
        session.revoked_at = session.revoked_at or now()
        session.save(update_fields=["revoked_at", "updated_at"])
        raise AuthTokenError("Refresh token has expired.")
    return session


def get_refresh_session_from_request(request, data: dict[str, Any] | None = None) -> RefreshToken | None:
    raw_token = extract_refresh_token(request, data)
    if not raw_token:
        return None
    try:
        return get_refresh_session_by_token(raw_token)
    except AuthTokenError:
        return None


def authenticate_access_token(raw_token: str):
    payload = decode_token(raw_token, expected_type="access")
    user = get_user_model().objects.filter(pk=payload["sub"]).first()
    if not user:
        raise AuthTokenError("Authentication required.")
    if auth_version_for_user(user) != int(payload["ver"]):
        raise AuthTokenError("Token is no longer valid.")
    if not user.is_active or getattr(user, "status", "") in {"suspended", "deactivated"}:
        raise AuthTokenError("Account is not active.")
    return user, payload


def rotate_refresh_session(request, data: dict[str, Any] | None = None):
    raw_token = extract_refresh_token(request, data)
    if not raw_token:
        raise AuthTokenError("Refresh token is required.")
    session = get_refresh_session_by_token(raw_token)
    access_token, refresh_token, refresh_session = issue_auth_session(
        session.user,
        request,
        family_id=session.family_id,
        previous_session=session,
        session_expires_at=session.session_expires_at,
    )
    models.AuthAuditLog.objects.create(
        user=session.user,
        email=session.user.email or DEFAULT_ACTOR_EMAIL,
        action="refresh",
        metadata={"familyId": str(session.family_id), "jti": refresh_session.jti},
    )
    return session.user, access_token, refresh_token, refresh_session


def get_authenticated_context(request, data: dict[str, Any] | None = None):
    access_token = extract_access_token(request, data)
    if access_token:
        try:
            user, _payload = authenticate_access_token(access_token)
        except AuthTokenError:
            return None, None
        return user, get_refresh_session_from_request(request, data)
    if getattr(request, "user", None) is not None and request.user.is_authenticated:
        return request.user, get_refresh_session_from_request(request, data)
    return None, None


def resolve_actor(request, data: dict[str, Any] | None = None, query: dict[str, Any] | None = None):
    user, session = get_authenticated_context(request, data)
    if user:
        return user, user.email or DEFAULT_ACTOR_EMAIL, session
    data = data or {}
    query = query or {}
    email = normalize_email(data.get("email") or data.get("userEmail") or data.get("actorEmail") or query.get("email"))
    return None, email or DEFAULT_ACTOR_EMAIL, None


def revoke_sessions(user, refresh_token: str | None = None, all_sessions: bool = False):
    queryset = RefreshToken.objects.filter(user=user, revoked_at__isnull=True)
    if all_sessions:
        queryset.update(revoked_at=now())
        return
    if not refresh_token:
        return
    try:
        session = get_refresh_session_by_token(refresh_token, allow_inactive=True)
    except AuthTokenError:
        return
    RefreshToken.objects.filter(family_id=session.family_id, revoked_at__isnull=True).update(revoked_at=now())


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


def sync_student_profile_metrics(user=None, email: str | None = None):
    if not user:
        return
    profile = related_or_none(user, "student_profile")
    if not profile:
        return
    actor_email = email or getattr(user, "email", "")
    enrollments = models.Enrollment.objects.filter(email=actor_email).select_related("course")
    wishlist_count = models.WishlistItem.objects.filter(email=actor_email).count()
    total_minutes = 0
    for enrollment in enrollments:
        course_minutes = max(0, enrollment.course.hours) * 60
        total_minutes += round(course_minutes * (enrollment.progress_percent / 100))
    enrollment_count = enrollments.count()
    completed_count = enrollments.filter(progress_percent__gte=100).count()
    average_progress = round(sum(item.progress_percent for item in enrollments) / enrollment_count) if enrollment_count else 0
    profile.completed_courses_count = completed_count
    profile.current_courses_count = enrollment_count
    profile.saved_courses_count = wishlist_count
    profile.average_progress_percent = average_progress
    profile.total_learning_minutes = total_minutes
    profile.learning_statistics = {
        "enrolledCourses": enrollment_count,
        "completedCourses": completed_count,
        "averageProgressPercent": average_progress,
    }
    profile.save(
        update_fields=[
            "completed_courses_count",
            "current_courses_count",
            "saved_courses_count",
            "average_progress_percent",
            "total_learning_minutes",
            "learning_statistics",
            "updated_at",
        ]
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
