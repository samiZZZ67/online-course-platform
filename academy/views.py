from __future__ import annotations

import json
import mimetypes
import re
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterable

from accounts.permissions import (
    can_access_admin_dashboard,
    can_configure_platform,
    can_manage_instructor_content,
    is_public_signup_role,
    user_has_role,
)
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db.models import Q
from django.http import FileResponse, HttpResponse, JsonResponse, StreamingHttpResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import csrf_exempt

from . import models
from .catalog import build_tutor_reply
from .services import (
    AuthTokenError,
    RateLimitExceeded,
    RefreshTokenReuseDetected,
    TwoFactorChallengeError,
    VerificationTokenError,
    active_notifications_for,
    clear_auth_cookie,
    confirm_email_verification,
    course_by_slug_or_404,
    create_or_update_course_from_input,
    enforce_rate_limit,
    generate_unique_username,
    create_password_reset_token,
    extract_refresh_token,
    get_authenticated_context,
    issue_email_verification,
    issue_auth_session,
    issue_two_factor_challenge,
    isoformat_z,
    lesson_by_key,
    list_course_categories,
    normalize_username,
    now,
    recalculate_enrollment_progress,
    requires_two_factor,
    rotate_refresh_session,
    resolve_actor,
    revoke_sessions,
    seed_database,
    send_password_reset_email,
    serialize_enrollment,
    serialize_course,
    serialize_session,
    serialize_user,
    set_auth_cookie,
    sync_student_profile_metrics,
    verify_two_factor_challenge,
)
from .utils import DEFAULT_ACTOR_EMAIL, build_token, format_number, normalize_email, validate_email


PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = PROJECT_ROOT / "index.html"
FRONTEND_AUTH_SCRIPT_PATH = Path(__file__).resolve().parent / "static" / "academy" / "frontend_auth.js"


def ensure_seeded():
    if not models.Course.objects.exists():
        seed_database()


def add_cors_headers(response: HttpResponse) -> HttpResponse:
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-CSRFToken"
    return response


def json_response(payload: dict[str, Any], status: int = 200) -> JsonResponse:
    return add_cors_headers(JsonResponse(payload, status=status))


def options_response() -> HttpResponse:
    return add_cors_headers(HttpResponse(status=204))


def error_response(message: str, status: int) -> JsonResponse:
    return json_response({"ok": False, "message": message}, status=status)


def rate_limit_response(error: RateLimitExceeded) -> JsonResponse:
    response = error_response(str(error), 429)
    response["Retry-After"] = str(error.retry_after)
    return response


def should_expose_dev_tokens(request) -> bool:
    email_backend = getattr(settings, "EMAIL_BACKEND", "")
    host = request.get_host() if hasattr(request, "get_host") else ""
    return bool(settings.DEBUG or "locmem" in email_backend or host.startswith("testserver"))


def require_instructor_access(user):
    if not user:
        return error_response("Authentication required.", 401)
    if not can_manage_instructor_content(user):
        return error_response("Instructor access is required for this action.", 403)
    return None


def require_authenticated_access(user):
    if not user:
        return error_response("Authentication required.", 401)
    return None


def require_admin_access(user, *, write: bool = False):
    if not user:
        return error_response("Authentication required.", 401)
    if write:
        if not (user_has_role(user, "admin") or can_configure_platform(user)):
            return error_response("Admin access is required for this action.", 403)
        return None
    if not can_access_admin_dashboard(user):
        return error_response("Admin access is required for this action.", 403)
    return None


def require_course_owner_access(user, course):
    if access_error := require_instructor_access(user):
        return access_error
    if not course:
        return error_response("Course not found", 404)
    if can_access_admin_dashboard(user):
        return None
    if getattr(course, "created_by_id", None) and str(course.created_by_id) != str(user.pk):
        return error_response("You can only manage courses you created.", 403)
    if not getattr(course, "created_by_id", None):
        return error_response("Only admins can modify platform-seeded courses.", 403)
    return None


def guard_method(request, methods: Iterable[str]) -> HttpResponse | None:
    if request.method == "OPTIONS":
        return options_response()
    if request.method not in set(methods):
        return error_response("Method not allowed", 405)
    return None


def parse_request_data(request) -> dict[str, Any]:
    if request.method == "GET":
        return request.GET.dict()
    content_type = request.headers.get("Content-Type", "")
    if "application/json" in content_type:
        try:
            raw_body = request.body.decode("utf-8") if request.body else "{}"
            return json.loads(raw_body or "{}")
        except json.JSONDecodeError:
            return {}
    if request.POST:
        return request.POST.dict()
    if request.body:
        try:
            return json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


NOTE_SIGNING_SALT = "skillforge.notebook.note.v1"


def parse_seconds(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError):
        return default


def format_media_clock(seconds: Any) -> str:
    safe_seconds = parse_seconds(seconds)
    minutes, secs = divmod(safe_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def is_uuid_like(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True


def coerce_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def protect_note_body(body: Any) -> str:
    return signing.dumps({"body": str(body or "")}, salt=NOTE_SIGNING_SALT, compress=True)


def unprotect_note_body(value: str) -> str:
    if not value:
        return ""
    try:
        payload = signing.loads(value, salt=NOTE_SIGNING_SALT)
    except signing.BadSignature:
        return value
    return str(payload.get("body", ""))


def note_body_preview(body: str) -> str:
    text = re.sub(r"<[^>]+>", " ", str(body or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:320]


def lesson_for_course(course: models.Course, lesson_id: str | None):
    lesson_id = str(lesson_id or "").strip()
    if not lesson_id:
        return None
    lesson = lesson_by_key(lesson_id)
    if not lesson or lesson.module.course_id != course.pk:
        return None
    return lesson


def serialize_notebook_attachment(attachment: models.NotebookAttachment) -> dict[str, Any]:
    return {
        "id": str(attachment.pk),
        "courseId": attachment.course.slug,
        "noteId": str(attachment.note_id) if attachment.note_id else None,
        "name": attachment.name,
        "contentType": attachment.content_type,
        "size": attachment.size,
        "url": attachment.file.url if attachment.file else "",
        "createdAt": isoformat_z(attachment.created_at),
    }


def serialize_note_version(version: models.NotebookNoteVersion) -> dict[str, Any]:
    return {
        "id": str(version.pk),
        "version": version.version,
        "title": version.title,
        "body": unprotect_note_body(version.encrypted_body),
        "bodyPreview": version.body_preview,
        "category": version.category,
        "tags": version.tags,
        "timestamp": version.timestamp_seconds,
        "metadata": version.metadata,
        "createdAt": isoformat_z(version.created_at),
    }


def serialize_notebook_note(note: models.NotebookNote, *, include_history: bool = False) -> dict[str, Any]:
    body = unprotect_note_body(note.encrypted_body)
    payload = {
        "id": str(note.pk),
        "courseId": note.course.slug,
        "lessonId": note.lesson.lesson_key if note.lesson else None,
        "title": note.title,
        "body": body,
        "bodyPreview": note.body_preview,
        "category": note.category,
        "tags": note.tags,
        "pinned": note.pinned,
        "timestamp": note.timestamp_seconds,
        "metadata": note.metadata,
        "sharedWith": note.shared_with,
        "version": note.version,
        "isDeleted": note.is_deleted,
        "createdAt": isoformat_z(note.created_at),
        "updatedAt": isoformat_z(note.updated_at),
        "lastSyncedAt": isoformat_z(note.last_synced_at),
        "attachments": [serialize_notebook_attachment(item) for item in note.attachments.all()],
    }
    if include_history:
        payload["history"] = [serialize_note_version(item) for item in note.versions.all()[:12]]
    return payload


def snapshot_note_version(note: models.NotebookNote) -> None:
    models.NotebookNoteVersion.objects.create(
        note=note,
        version=note.version,
        title=note.title,
        encrypted_body=note.encrypted_body,
        body_preview=note.body_preview,
        category=note.category,
        tags=note.tags,
        timestamp_seconds=note.timestamp_seconds,
        metadata=note.metadata,
    )


def serialize_question(question: models.LessonQuestion, completed_keys: set[str]) -> dict[str, Any]:
    key = str(question.pk)
    return {
        "id": key,
        "courseId": question.course.slug,
        "lessonId": question.lesson.lesson_key if question.lesson else None,
        "question": question.question,
        "answer": question.answer,
        "timestamp": question.timestamp_seconds,
        "position": question.position,
        "metadata": question.metadata,
        "completed": key in completed_keys,
        "source": "database",
    }


def metadata_questions_for_lesson(course: models.Course, lesson, completed_keys: set[str]) -> list[dict[str, Any]]:
    raw_items = []
    if lesson:
        metadata = lesson.metadata if isinstance(lesson.metadata, dict) else {}
        raw_items = metadata.get("questions") or metadata.get("questionNav") or metadata.get("checkpoints") or []
    if not raw_items and isinstance(course.qa, list):
        raw_items = course.qa
    items: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_items if isinstance(raw_items, list) else [], start=1):
        if not isinstance(raw, dict):
            continue
        question_text = str(raw.get("question") or raw.get("prompt") or raw.get("title") or "").strip()
        if not question_text:
            continue
        timestamp = parse_seconds(raw.get("timestamp", raw.get("timestampSeconds", raw.get("time", index * 45))))
        key = str(raw.get("id") or f"metadata:{lesson.lesson_key if lesson else course.slug}:{index}")
        items.append(
            {
                "id": key,
                "courseId": course.slug,
                "lessonId": lesson.lesson_key if lesson else None,
                "question": question_text,
                "answer": str(raw.get("answer") or raw.get("hint") or "").strip(),
                "timestamp": timestamp,
                "position": index,
                "metadata": raw,
                "completed": key in completed_keys,
                "source": "metadata",
            }
        )
    return items


def index(request):
    if request.method not in {"GET", "HEAD"}:
        return error_response("Method not allowed", 405)
    get_token(request)
    html = INDEX_PATH.read_text(encoding="utf-8")
    script_tag = '<script src="/frontend-auth.js"></script>'
    if script_tag not in html:
        body_close_index = html.lower().rfind("</body>")
        if body_close_index >= 0:
            html = f"{html[:body_close_index]}{script_tag}\n{html[body_close_index:]}"
        else:
            html = f"{html}\n{script_tag}\n"
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    return add_cors_headers(response)


def frontend_auth_script(request):
    if request.method not in {"GET", "HEAD"}:
        return error_response("Method not allowed", 405)
    script = FRONTEND_AUTH_SCRIPT_PATH.read_text(encoding="utf-8")
    response = HttpResponse(script, content_type="application/javascript; charset=utf-8")
    return add_cors_headers(response)


def _iter_file_range(file_path: Path, start: int, length: int):
    with file_path.open("rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining > 0:
            chunk = handle.read(min(8192, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _resolve_course_asset_path(asset_path: str) -> Path | None:
    base_dir = (Path(settings.MEDIA_ROOT) / "course-assets").resolve()
    candidate = (base_dir / asset_path).resolve()
    try:
        candidate.relative_to(base_dir)
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate


def course_asset_media(request, asset_path: str):
    if request.method not in {"GET", "HEAD"}:
        return error_response("Method not allowed", 405)
    file_path = _resolve_course_asset_path(asset_path)
    if not file_path:
        return error_response("Asset not found", 404)

    file_size = file_path.stat().st_size
    content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    range_header = request.headers.get("Range", "").strip()

    if range_header.startswith("bytes="):
        requested_range = range_header.removeprefix("bytes=").split(",", 1)[0]
        start_text, separator, end_text = requested_range.partition("-")
        try:
            if start_text:
                start = int(start_text)
                end = int(end_text) if end_text else file_size - 1
            else:
                suffix_length = int(end_text)
                start = max(file_size - suffix_length, 0)
                end = file_size - 1
        except (TypeError, ValueError):
            start = file_size
            end = file_size - 1
        if not separator or start < 0 or end < start or start >= file_size:
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{file_size}"
            return add_cors_headers(response)
        end = min(end, file_size - 1)
        content_length = end - start + 1
        if request.method == "HEAD":
            response = HttpResponse(status=206, content_type=content_type)
        else:
            response = StreamingHttpResponse(
                _iter_file_range(file_path, start, content_length),
                status=206,
                content_type=content_type,
            )
        response["Content-Length"] = str(content_length)
        response["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    elif request.method == "HEAD":
        response = HttpResponse(content_type=content_type)
        response["Content-Length"] = str(file_size)
    else:
        response = FileResponse(file_path.open("rb"), content_type=content_type)
        response["Content-Length"] = str(file_size)

    response["Accept-Ranges"] = "bytes"
    response["Content-Disposition"] = f'inline; filename="{file_path.name}"'
    return add_cors_headers(response)


def api_not_found(request):
    if request.method == "OPTIONS":
        return options_response()
    return error_response("Route not found", 404)


@csrf_exempt
def health(request):
    if response := guard_method(request, {"GET"}):
        return response
    ensure_seeded()
    return json_response(
        {
            "ok": True,
            "service": "skillforge-backend-django",
            "now": isoformat_z(now()),
            "stats": {
                "users": get_user_model().objects.count(),
                "courses": models.Course.objects.count(),
                "enrollments": models.Enrollment.objects.count(),
                "newsletterSubscribers": models.NewsletterSubscriber.objects.count(),
            },
        }
    )


@csrf_exempt
def course_categories(request):
    if response := guard_method(request, {"GET"}):
        return response
    ensure_seeded()
    categories = []
    for category in list_course_categories():
        categories.append(
            {
                "id": category.slug,
                "slug": category.slug,
                "code": category.code,
                "label": category.label,
                "badgeClass": category.badge_class,
                "gradient": category.gradient,
                "description": category.description,
                "courseCount": category.courses.count(),
                "requirements": category.requirements,
                "learn": category.learn,
                "resources": category.resources,
                "qa": category.qa,
            }
        )
    return json_response({"ok": True, "count": len(categories), "categories": categories})


@csrf_exempt
def course_list(request):
    if response := guard_method(request, {"GET"}):
        return response
    ensure_seeded()
    queryset = models.Course.objects.select_related("category_ref", "created_by").prefetch_related("course_modules__lessons").all()
    category_filter = str(request.GET.get("category", "")).strip().lower()
    search_query = str(request.GET.get("q", "")).strip()
    instructor_filter = str(request.GET.get("instructor", "")).strip()
    if category_filter:
        queryset = queryset.filter(category=category_filter)
    if instructor_filter:
        queryset = queryset.filter(instructor_name__icontains=instructor_filter)
    if search_query:
        queryset = queryset.filter(
            Q(title__icontains=search_query)
            | Q(overview__icontains=search_query)
            | Q(instructor_name__icontains=search_query)
            | Q(track__icontains=search_query)
        )
    courses = [serialize_course(course) for course in queryset]
    return json_response({"ok": True, "count": len(courses), "courses": courses})


@csrf_exempt
def course_content_search(request):
    if response := guard_method(request, {"GET"}):
        return response
    ensure_seeded()
    course_id = str(request.GET.get("courseId", "")).strip()
    query = str(request.GET.get("q", "")).strip()
    if not course_id:
        return error_response("courseId query parameter is required.", 400)
    course = course_by_slug_or_404(course_id)
    if not course:
        return error_response("Course not found", 404)
    user, email, _session = resolve_actor(request, query=request.GET.dict())
    if not query:
        return json_response({"ok": True, "courseId": course.slug, "query": query, "count": 0, "results": []})

    lesson_queryset = (
        models.CourseLesson.objects.filter(module__course=course, is_published=True)
        .select_related("module")
        .filter(Q(title__icontains=query) | Q(summary__icontains=query) | Q(content_type__icontains=query))
    )
    results: list[dict[str, Any]] = [
        {
            "kind": "lesson",
            "type": lesson.content_type,
            "id": lesson.lesson_key,
            "courseId": course.slug,
            "lessonId": lesson.lesson_key,
            "title": lesson.title,
            "subtitle": f"{lesson.module.title} - {lesson.duration_label or 'Self-paced'}",
            "timestamp": 0,
        }
        for lesson in lesson_queryset[:20]
    ]

    question_queryset = (
        models.LessonQuestion.objects.filter(course=course, is_published=True)
        .select_related("lesson")
        .filter(Q(question__icontains=query) | Q(answer__icontains=query))
    )
    results.extend(
        {
            "kind": "question",
            "id": str(question.pk),
            "questionId": str(question.pk),
            "courseId": course.slug,
            "lessonId": question.lesson.lesson_key if question.lesson else "",
            "title": question.question,
            "subtitle": f"{question.lesson.title if question.lesson else course.title} - {format_media_clock(question.timestamp_seconds)}",
            "timestamp": question.timestamp_seconds,
        }
        for question in question_queryset[:20]
    )

    note_queryset = (
        models.NotebookNote.objects.filter(email=email, course=course, is_deleted=False)
        .select_related("lesson")
        .filter(Q(title__icontains=query) | Q(body_preview__icontains=query) | Q(category__icontains=query))
    )
    results.extend(
        {
            "kind": "note",
            "id": str(note.pk),
            "courseId": course.slug,
            "lessonId": note.lesson.lesson_key if note.lesson else "",
            "title": note.title or "Untitled note",
            "subtitle": f"Notebook - {note.category or 'General'}",
            "timestamp": note.timestamp_seconds,
        }
        for note in note_queryset[:20]
    )

    return json_response({"ok": True, "courseId": course.slug, "query": query, "count": len(results), "results": results[:40]})


@csrf_exempt
def course_detail(request, course_id: str):
    if response := guard_method(request, {"GET"}):
        return response
    ensure_seeded()
    course = course_by_slug_or_404(course_id)
    if not course:
        return error_response("Course not found", 404)
    _user, email, _session = resolve_actor(request, query=request.GET.dict())
    enrollment = models.Enrollment.objects.select_related("course", "current_lesson").filter(email=email, course=course).first()
    payload = {"ok": True, "course": serialize_course(course)}
    if enrollment:
        payload["enrollment"] = serialize_enrollment(enrollment)
    return json_response(payload)


@csrf_exempt
def course_resources(request, course_id: str):
    if response := guard_method(request, {"GET", "POST"}):
        return response
    ensure_seeded()
    data = parse_request_data(request)
    course = course_by_slug_or_404(course_id)
    if not course:
        return error_response("Course not found", 404)
    resource_name = str(data.get("resource") or request.GET.get("resource") or "").strip()
    if not resource_name:
        return json_response({"ok": True, "courseId": course_id, "resources": course.resources})
    return json_response(
        {
            "ok": True,
            "courseId": course_id,
            "resource": resource_name,
            "downloadUrl": request.build_absolute_uri(f"/downloads/{course_id}/{resource_name}"),
            "message": "Resource delivery is prepared for signed URLs or authenticated downloads.",
        }
    )


def _auth_success_response(user, access_token, refresh_token, session, status=200, extra: dict[str, Any] | None = None):
    payload = {
        "ok": True,
        "authenticated": True,
        "user": serialize_user(user),
        "token": access_token,
        "accessToken": access_token,
        "session": serialize_session(session),
        "verificationRequired": not bool(getattr(user, "is_email_verified", False)),
    }
    if extra:
        payload.update(extra)
    response = json_response(payload, status=status)
    return set_auth_cookie(response, refresh_token, expires_at=session.expires_at)


def _two_factor_challenge_response(user, challenge, *, otp_code: str | None = None):
    payload = {
        "ok": True,
        "authenticated": False,
        "twoFactorRequired": True,
        "challengeId": str(challenge.pk),
        "method": challenge.method,
        "expiresAt": isoformat_z(challenge.expires_at),
        "pendingUser": {
            "email": user.email,
            "role": user.role,
            "twoFactorMethod": challenge.method,
        },
        "message": "A verification code was sent to complete sign-in.",
    }
    if otp_code:
        payload["otpCode"] = otp_code
    return json_response(payload, status=202)


@csrf_exempt
def auth_signup(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    ip_address = request.META.get("REMOTE_ADDR", "unknown")
    first_name = str(data.get("firstName", "")).strip()
    last_name = str(data.get("lastName", "")).strip()
    email = normalize_email(data.get("email"))
    password = str(data.get("password", ""))
    requested_username = str(data.get("username", "")).strip()
    requested_role = str(data.get("role", "")).strip().lower()
    try:
        enforce_rate_limit("signup.ip", ip_address, message="Too many signup attempts from this address. Please try again shortly.")
        if email:
            enforce_rate_limit("signup.email", email, message="Too many signup attempts for this email. Please try again shortly.")
    except RateLimitExceeded as exc:
        return rate_limit_response(exc)
    if not first_name or not last_name:
        return error_response("First name and last name are required.", 400)
    if not validate_email(email):
        return error_response("A valid email address is required.", 400)
    User = get_user_model()
    username = normalize_username(requested_username)
    if requested_username and not username:
        return error_response("Username must contain letters, numbers, underscores, or dots.", 400)
    if username:
        try:
            User._meta.get_field("username").clean(username, None)
        except ValidationError as exc:
            return error_response(exc.messages[0], 400)
        if User.objects.filter(username=username).exists():
            return error_response("That username is already taken.", 409)
    else:
        username = generate_unique_username(first_name, last_name, email)
    try:
        validate_password(password)
    except ValidationError as exc:
        return error_response(exc.messages[0], 400)

    role = requested_role or User.Role.STUDENT
    if not is_public_signup_role(role):
        return error_response("Role must be either student or instructor.", 400)
    if User.objects.filter(email=email).exists():
        return error_response("An account with that email already exists.", 409)

    user = User.objects.create_user(
        email=email,
        username=username,
        first_name=first_name,
        last_name=last_name,
        password=password,
        role=role,
    )
    models.AuthAuditLog.objects.create(user=user, email=email, action="signup")
    models.PlatformNotification.objects.create(
        audience_scope=models.PlatformNotification.SCOPE_USER,
        audience_user=user,
        audience_email=email,
        title="Account created",
        message="Your SkillForge instructor account is ready." if role == User.Role.INSTRUCTOR else "Your SkillForge learner account is ready.",
    )
    verification_token, verification_record, verification_url = issue_email_verification(user, request)
    access_token, refresh_token, session = issue_auth_session(user, request)
    extra = {
        "verificationEmailSent": True,
        "verificationExpiresAt": isoformat_z(verification_record.expires_at),
    }
    if should_expose_dev_tokens(request):
        extra["verificationToken"] = verification_token
        extra["verificationUrl"] = verification_url
    return _auth_success_response(user, access_token, refresh_token, session, status=201, extra=extra)


@csrf_exempt
def auth_login(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    ip_address = request.META.get("REMOTE_ADDR", "unknown")
    email = normalize_email(data.get("email"))
    password = str(data.get("password", ""))
    try:
        enforce_rate_limit("login.ip", ip_address, message="Too many login attempts from this address. Please try again shortly.")
        if email:
            enforce_rate_limit("login.email", email, message="Too many login attempts for this email. Please try again shortly.")
    except RateLimitExceeded as exc:
        return rate_limit_response(exc)
    if not validate_email(email):
        return error_response("A valid email address is required.", 400)
    if len(password) < 8:
        return error_response("Password must be at least 8 characters.", 400)

    User = get_user_model()
    user = User.objects.filter(email=email).first()
    if not user or not user.check_password(password):
        models.AuthAuditLog.objects.create(user=user, email=email or DEFAULT_ACTOR_EMAIL, action="login_failed")
        return error_response("Invalid email or password.", 401)
    if not user.is_active or getattr(user, "status", "") in {"suspended", "deactivated"}:
        return error_response("This account is not active.", 403)
    if requires_two_factor(user):
        try:
            enforce_rate_limit("2fa.challenge.ip", ip_address, message="Too many verification code requests from this address. Please try again later.")
        except RateLimitExceeded as exc:
            return rate_limit_response(exc)
        otp_code, challenge, _delivery_target = issue_two_factor_challenge(user, request)
        return _two_factor_challenge_response(user, challenge, otp_code=otp_code if should_expose_dev_tokens(request) else None)

    access_token, refresh_token, session = issue_auth_session(user, request)
    models.AuthAuditLog.objects.create(user=user, email=user.email or email, action="login")
    return _auth_success_response(user, access_token, refresh_token, session)


@csrf_exempt
def auth_refresh(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    try:
        user, access_token, refresh_token, session = rotate_refresh_session(request, data)
    except RefreshTokenReuseDetected as exc:
        response = error_response(str(exc), 401)
        return clear_auth_cookie(response)
    except AuthTokenError as exc:
        response = error_response(str(exc), 401)
        return clear_auth_cookie(response)
    return _auth_success_response(user, access_token, refresh_token, session)


@csrf_exempt
def auth_two_factor_verify(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    challenge_id = str(data.get("challengeId", "")).strip()
    otp_code = str(data.get("otpCode") or data.get("code") or "").strip()
    if not challenge_id:
        return error_response("challengeId is required.", 400)
    if not otp_code:
        return error_response("otpCode is required.", 400)
    try:
        enforce_rate_limit("2fa.verify.challenge", challenge_id, message="Too many invalid verification attempts. Please request a new code.")
        user, _challenge = verify_two_factor_challenge(challenge_id, otp_code)
    except RateLimitExceeded as exc:
        return rate_limit_response(exc)
    except TwoFactorChallengeError as exc:
        return error_response(str(exc), 400)
    access_token, refresh_token, session = issue_auth_session(user, request)
    models.AuthAuditLog.objects.create(user=user, email=user.email or DEFAULT_ACTOR_EMAIL, action="login")
    return _auth_success_response(user, access_token, refresh_token, session)


@csrf_exempt
def auth_verify_email_request(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    user, _session = get_authenticated_context(request, data)
    email = normalize_email(data.get("email") or (user.email if user else ""))
    ip_address = request.META.get("REMOTE_ADDR", "unknown")
    try:
        enforce_rate_limit("verify.request.ip", ip_address, message="Too many verification email requests from this address. Please try again later.")
        if email:
            enforce_rate_limit("verify.request.email", email, message="Too many verification email requests for this email. Please try again later.")
    except RateLimitExceeded as exc:
        return rate_limit_response(exc)
    if not user and not validate_email(email):
        return error_response("A valid email address is required.", 400)
    target_user = user or get_user_model().objects.filter(email=email).first()
    payload = {"ok": True, "message": "If that account exists and is not verified, a verification email has been prepared."}
    if target_user and not target_user.is_email_verified:
        verification_token, verification_record, verification_url = issue_email_verification(target_user, request)
        payload["verificationEmailSent"] = True
        payload["verificationExpiresAt"] = isoformat_z(verification_record.expires_at)
        if should_expose_dev_tokens(request):
            payload["verificationToken"] = verification_token
            payload["verificationUrl"] = verification_url
    return json_response(payload)


@csrf_exempt
def auth_verify_email_confirm(request):
    if response := guard_method(request, {"GET", "POST"}):
        return response
    data = parse_request_data(request)
    token = str(data.get("token") or request.GET.get("token") or "").strip()
    try:
        user, verification_record = confirm_email_verification(token)
    except VerificationTokenError as exc:
        if request.method == "GET":
            response = HttpResponse(str(exc), status=400, content_type="text/plain; charset=utf-8")
            return add_cors_headers(response)
        return error_response(str(exc), 400)
    access_token, refresh_token, session = issue_auth_session(user, request)
    extra = {
        "verificationConfirmed": True,
        "verifiedAt": isoformat_z(user.email_verified_at),
        "verificationExpiresAt": isoformat_z(verification_record.expires_at),
    }
    if request.method == "GET":
        response = HttpResponse(
            f"Email verified for {user.email}. You can return to SkillForge now.",
            content_type="text/plain; charset=utf-8",
        )
        response = add_cors_headers(response)
        return set_auth_cookie(response, refresh_token, expires_at=session.expires_at)
    return _auth_success_response(user, access_token, refresh_token, session, extra=extra)


@csrf_exempt
def auth_me(request):
    if response := guard_method(request, {"GET"}):
        return response
    user, session = get_authenticated_context(request)
    if not user:
        response = error_response("Authentication required.", 401)
        return clear_auth_cookie(response)
    return json_response(
        {
            "ok": True,
            "authenticated": True,
            "user": serialize_user(user),
            "session": serialize_session(session),
        }
    )


@csrf_exempt
def auth_logout(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    user, session = get_authenticated_context(request, data)
    refresh_token = extract_refresh_token(request, data)
    if user:
        revoke_sessions(user, refresh_token=refresh_token, all_sessions=(str(data.get("allSessions", "")).lower() == "true" or data.get("allSessions") is True))
        models.AuthAuditLog.objects.create(user=user, email=user.email or DEFAULT_ACTOR_EMAIL, action="logout")
    response = json_response(
        {
            "ok": True,
            "authenticated": user is not None,
            "loggedOut": True,
            "allSessions": str(data.get("allSessions", "")).lower() == "true" or data.get("allSessions") is True,
        }
    )
    return clear_auth_cookie(response)


@csrf_exempt
def auth_oauth_start(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    provider = str(data.get("provider", "")).strip().lower()
    if provider != "google":
        return error_response("Only google is configured in the current frontend contract.", 400)
    oauth_state = models.OAuthState.objects.create(
        provider=provider,
        state=build_token("state"),
        expires_at=now() + timedelta(minutes=10),
    )
    return json_response(
        {
            "ok": True,
            "provider": provider,
            "state": oauth_state.state,
            "authorizationUrl": f"https://accounts.google.com/o/oauth2/v2/auth?state={oauth_state.state}",
        }
    )


@csrf_exempt
def auth_password_reset_request(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    email = normalize_email(data.get("email"))
    ip_address = request.META.get("REMOTE_ADDR", "unknown")
    try:
        enforce_rate_limit("password_reset.ip", ip_address, message="Too many password reset requests from this address. Please try again later.")
        if email:
            enforce_rate_limit("password_reset.email", email, message="Too many password reset requests for this email. Please try again later.")
    except RateLimitExceeded as exc:
        return rate_limit_response(exc)
    if not validate_email(email):
        return error_response("A valid email address is required.", 400)
    User = get_user_model()
    user = User.objects.filter(email=email).first()
    payload = {"ok": True, "message": "If that email exists, a password reset has been prepared."}
    if user:
        reset_token = create_password_reset_token(user)
        reset_url = send_password_reset_email(user, request, reset_token.token)
        models.AuthAuditLog.objects.create(user=user, email=email, action="password_reset.request")
        payload["emailSent"] = True
        payload["expiresAt"] = isoformat_z(reset_token.expires_at)
        if should_expose_dev_tokens(request):
            payload["resetToken"] = reset_token.token
            payload["resetUrl"] = reset_url
    return json_response(payload)


@csrf_exempt
def auth_password_reset_confirm(request):
    if response := guard_method(request, {"GET", "POST"}):
        return response
    data = parse_request_data(request)
    token = str(data.get("token") or request.GET.get("token") or "").strip()
    password = str(data.get("password", ""))
    if not token:
        return error_response("Reset token is required.", 400)
    reset_record = models.PasswordResetToken.objects.select_related("user").filter(token=token).first()
    if not reset_record:
        return error_response("Reset token is invalid.", 400)
    if reset_record.consumed_at:
        return error_response("Reset token has already been used.", 409)
    if reset_record.expires_at <= now():
        return error_response("Reset token has expired.", 410)
    if request.method == "GET":
        return json_response(
            {
                "ok": True,
                "valid": True,
                "email": reset_record.user.email,
                "expiresAt": isoformat_z(reset_record.expires_at),
            }
        )
    try:
        validate_password(password, reset_record.user)
    except ValidationError as exc:
        return error_response(exc.messages[0], 400)

    user = reset_record.user
    user.set_password(password)
    user.last_password_changed_at = now()
    user.save(update_fields=["password", "last_password_changed_at", "updated_at"])
    revoke_sessions(user, all_sessions=True)
    reset_record.consumed_at = now()
    reset_record.save(update_fields=["consumed_at"])
    access_token, refresh_token, session = issue_auth_session(user, request)
    models.AuthAuditLog.objects.create(user=user, email=user.email or DEFAULT_ACTOR_EMAIL, action="password_reset.confirm")
    return _auth_success_response(user, access_token, refresh_token, session)


@csrf_exempt
def public_register(request):
    return auth_signup(request)


@csrf_exempt
def public_login(request):
    return auth_login(request)


@csrf_exempt
def public_refresh_token(request):
    return auth_refresh(request)


@csrf_exempt
def public_forgot_password(request):
    return auth_password_reset_request(request)


@csrf_exempt
def public_reset_password(request):
    return auth_password_reset_confirm(request)


@csrf_exempt
def public_verify_email(request):
    data = parse_request_data(request)
    if str(data.get("token") or request.GET.get("token") or "").strip():
        return auth_verify_email_confirm(request)
    return auth_verify_email_request(request)


@csrf_exempt
def profile_detail(request):
    if response := guard_method(request, {"GET"}):
        return response
    user, session = get_authenticated_context(request)
    if access_error := require_authenticated_access(user):
        return access_error
    return json_response({"ok": True, "user": serialize_user(user), "session": serialize_session(session)})


@csrf_exempt
def profile_update(request):
    if response := guard_method(request, {"PUT", "PATCH"}):
        return response
    data = parse_request_data(request)
    user, _session = get_authenticated_context(request, data)
    if access_error := require_authenticated_access(user):
        return access_error

    updates: list[str] = []
    if "firstName" in data:
        user.first_name = str(data.get("firstName", "")).strip()
        updates.append("first_name")
    if "lastName" in data:
        user.last_name = str(data.get("lastName", "")).strip()
        updates.append("last_name")
    if "avatar" in data:
        user.avatar = str(data.get("avatar", "")).strip()
        updates.append("avatar")
    if "bio" in data:
        user.bio = str(data.get("bio", "")).strip()
        updates.append("bio")
    if "username" in data:
        requested_username = normalize_username(data.get("username"))
        if str(data.get("username", "")).strip() and not requested_username:
            return error_response("Username must contain letters, numbers, underscores, or dots.", 400)
        if requested_username and get_user_model().objects.exclude(pk=user.pk).filter(username=requested_username).exists():
            return error_response("That username is already taken.", 409)
        user.username = requested_username or None
        updates.append("username")
    if "twoFactorEnabled" in data:
        requested_two_factor_enabled = data.get("twoFactorEnabled")
        should_enable = requested_two_factor_enabled if isinstance(requested_two_factor_enabled, bool) else str(requested_two_factor_enabled).strip().lower() in {"1", "true", "yes", "on"}
        if not should_enable and user_has_role(user, "instructor", "admin"):
            return error_response("Two-factor authentication is required for instructor and admin accounts.", 400)
        user.two_factor_enabled = should_enable
        updates.append("two_factor_enabled")
    if "twoFactorMethod" in data:
        requested_method = str(data.get("twoFactorMethod", "")).strip().lower()
        if requested_method and requested_method != user.TwoFactorMethod.EMAIL_OTP:
            return error_response("Only email_otp is currently supported for two-factor authentication.", 400)
        user.two_factor_method = requested_method or user.TwoFactorMethod.EMAIL_OTP
        updates.append("two_factor_method")
    if updates:
        updates.append("updated_at")
        user.save(update_fields=updates)

    if "socialLinks" in data and isinstance(data.get("socialLinks"), dict):
        user.social_links = data.get("socialLinks")
        user.save(update_fields=["social_links", "updated_at"])

    instructor_payload = data.get("instructorProfile") if isinstance(data.get("instructorProfile"), dict) else data
    if user_has_role(user, "instructor", "admin"):
        profile = user.ensure_instructor_profile()
        profile_updates: list[str] = []
        if "expertise" in instructor_payload:
            expertise = instructor_payload.get("expertise") or []
            profile.expertise = expertise if isinstance(expertise, list) else [str(expertise)]
            profile_updates.append("expertise")
        if "biography" in instructor_payload:
            profile.biography = str(instructor_payload.get("biography", "")).strip()
            profile_updates.append("biography")
        if "socialLinks" in instructor_payload and isinstance(instructor_payload.get("socialLinks"), dict):
            profile.social_links = instructor_payload.get("socialLinks")
            profile_updates.append("social_links")
        if profile_updates:
            profile_updates.append("updated_at")
            profile.save(update_fields=profile_updates)

    return json_response({"ok": True, "user": serialize_user(get_user_model().objects.get(pk=user.pk))})


@csrf_exempt
def change_password(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    user, _session = get_authenticated_context(request, data)
    if access_error := require_authenticated_access(user):
        return access_error
    current_password = str(data.get("currentPassword") or data.get("oldPassword") or "")
    new_password = str(data.get("newPassword") or data.get("password") or "")
    if not user.check_password(current_password):
        return error_response("Current password is incorrect.", 400)
    try:
        validate_password(new_password, user)
    except ValidationError as exc:
        return error_response(exc.messages[0], 400)
    user.set_password(new_password)
    user.last_password_changed_at = now()
    user.save(update_fields=["password", "last_password_changed_at", "updated_at"])
    revoke_sessions(user, all_sessions=True)
    access_token, refresh_token, session = issue_auth_session(user, request)
    models.AuthAuditLog.objects.create(user=user, email=user.email or DEFAULT_ACTOR_EMAIL, action="password_change")
    return _auth_success_response(user, access_token, refresh_token, session)


def _admin_target_user(data):
    user_id = str(data.get("userId") or "").strip()
    email = normalize_email(data.get("email"))
    queryset = get_user_model().objects.all()
    if user_id:
        return queryset.filter(pk=user_id).first()
    if email:
        return queryset.filter(email=email).first()
    return None


@csrf_exempt
def admin_users(request):
    if response := guard_method(request, {"GET"}):
        return response
    user, _session = get_authenticated_context(request)
    if access_error := require_admin_access(user):
        return access_error
    queryset = get_user_model().objects.all().order_by("-date_joined")
    query = str(request.GET.get("q", "")).strip()
    role = str(request.GET.get("role", "")).strip().lower()
    status = str(request.GET.get("status", "")).strip().lower()
    if query:
        queryset = queryset.filter(Q(email__icontains=query) | Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query))
    if role:
        queryset = queryset.filter(role=role)
    if status:
        queryset = queryset.filter(status=status)
    users = [serialize_user(item) for item in queryset]
    return json_response({"ok": True, "count": len(users), "users": users})


@csrf_exempt
def admin_users_suspend(request):
    if response := guard_method(request, {"PATCH"}):
        return response
    data = parse_request_data(request)
    user, _session = get_authenticated_context(request, data)
    if access_error := require_admin_access(user, write=True):
        return access_error
    target = _admin_target_user(data)
    if not target:
        return error_response("User not found.", 404)
    suspend_flag = data.get("suspended")
    should_suspend = suspend_flag if isinstance(suspend_flag, bool) else str(suspend_flag).lower() != "false"
    target.is_active = not should_suspend
    target.status = target.Status.SUSPENDED if should_suspend else (target.Status.ACTIVE if target.is_email_verified else target.Status.PENDING_VERIFICATION)
    target.save(update_fields=["is_active", "status", "updated_at"])
    models.AuthAuditLog.objects.create(
        user=target,
        email=target.email or DEFAULT_ACTOR_EMAIL,
        action="admin.user_suspend",
        metadata={"suspended": should_suspend, "actorId": str(user.pk)},
    )
    return json_response({"ok": True, "suspended": should_suspend, "user": serialize_user(target)})


@csrf_exempt
def admin_users_verify(request):
    if response := guard_method(request, {"PATCH"}):
        return response
    data = parse_request_data(request)
    user, _session = get_authenticated_context(request, data)
    if access_error := require_admin_access(user, write=True):
        return access_error
    target = _admin_target_user(data)
    if not target:
        return error_response("User not found.", 404)
    target.mark_email_verified()
    models.AuthAuditLog.objects.create(
        user=target,
        email=target.email or DEFAULT_ACTOR_EMAIL,
        action="admin.user_verify",
        metadata={"actorId": str(user.pk)},
    )
    return json_response({"ok": True, "verified": True, "user": serialize_user(target)})


@csrf_exempt
def admin_users_change_role(request):
    if response := guard_method(request, {"PATCH"}):
        return response
    data = parse_request_data(request)
    user, _session = get_authenticated_context(request, data)
    if access_error := require_admin_access(user, write=True):
        return access_error
    target = _admin_target_user(data)
    if not target:
        return error_response("User not found.", 404)
    requested_role = str(data.get("role", "")).strip().lower()
    allowed_roles = {choice for choice, _label in get_user_model().Role.choices}
    if requested_role not in allowed_roles:
        return error_response("A valid role is required.", 400)
    previous_role = target.role
    target.role = requested_role
    if not target.is_superuser:
        target.is_staff = requested_role == target.Role.ADMIN
    target.save(update_fields=["role", "is_staff", "updated_at"])
    if requested_role == target.Role.STUDENT:
        target.ensure_student_profile()
    if requested_role == target.Role.INSTRUCTOR:
        target.ensure_instructor_profile()
    models.AuthAuditLog.objects.create(
        user=target,
        email=target.email or DEFAULT_ACTOR_EMAIL,
        action="admin.user_change_role",
        metadata={"actorId": str(user.pk), "previousRole": previous_role, "newRole": requested_role},
    )
    return json_response({"ok": True, "user": serialize_user(target)})


@csrf_exempt
def newsletter_subscribe(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    email = normalize_email(data.get("email"))
    if not validate_email(email):
        return error_response("A valid email address is required.", 400)
    subscriber, _created = models.NewsletterSubscriber.objects.update_or_create(
        email=email,
        defaults={"status": "subscribed", "subscribed_at": now()},
    )
    return json_response(
        {
            "ok": True,
            "subscriber": {
                "id": str(subscriber.pk),
                "email": subscriber.email,
                "status": subscriber.status,
                "subscribedAt": isoformat_z(subscriber.subscribed_at),
                "updatedAt": isoformat_z(subscriber.updated_at),
            },
        }
    )


@csrf_exempt
def enrollments(request):
    if response := guard_method(request, {"GET", "POST"}):
        return response
    ensure_seeded()
    if request.method == "GET":
        user, email, _session = resolve_actor(request, query=request.GET.dict())
        course_id = str(request.GET.get("courseId", "")).strip()
        queryset = (
            models.Enrollment.objects.filter(email=email)
            .select_related("course", "current_lesson", "course__category_ref")
            .prefetch_related("course__course_modules__lessons", "lesson_progress_items__lesson", "lesson_progress_items__lesson__module")
        )
        if course_id:
            queryset = queryset.filter(course__slug=course_id)
        items = [serialize_enrollment(item) for item in queryset]
        return json_response({"ok": True, "email": email, "count": len(items), "enrollments": items})

    data = parse_request_data(request)
    course_id = str(data.get("courseId", "")).strip()
    if not course_id:
        return error_response("courseId is required.", 400)
    course = course_by_slug_or_404(course_id)
    if not course:
        return error_response("Course not found", 404)
    user, email, _session = resolve_actor(request, data=data)
    enrollment, created = models.Enrollment.objects.get_or_create(
        email=email,
        course=course,
        defaults={
            "user": user,
            "status": "active",
            "progress_percent": 0,
        },
    )
    if user and enrollment.user_id != user.pk:
        enrollment.user = user
        enrollment.save(update_fields=["user"])
    sync_student_profile_metrics(user=user, email=email)
    if created:
        course.students_count = models.Enrollment.objects.filter(course=course).count()
        course.save(update_fields=["students_count", "updated_at"])
        models.PlatformNotification.objects.create(
            audience_scope=models.PlatformNotification.SCOPE_EMAIL,
            audience_email=email,
            title="Enrollment confirmed",
            message=f"You are enrolled in {course.title}.",
        )
    return json_response(
        {
            "ok": True,
            "created": created,
            "course": serialize_course(course),
            "enrollment": serialize_enrollment(enrollment),
        },
        status=201 if created else 200,
    )


@csrf_exempt
def enrollment_progress(request):
    if response := guard_method(request, {"POST"}):
        return response
    ensure_seeded()
    data = parse_request_data(request)
    user, email, _session = resolve_actor(request, data=data)
    if not user:
        return error_response("Authentication required.", 401)
    course_id = str(data.get("courseId", "")).strip()
    if not course_id:
        return error_response("courseId is required.", 400)
    course = course_by_slug_or_404(course_id)
    if not course:
        return error_response("Course not found", 404)
    try:
        progress_percent = int(data.get("progressPercent", 0))
    except (TypeError, ValueError):
        progress_percent = 0
    progress_percent = max(0, min(100, progress_percent))
    lesson_id = str(data.get("lessonId", "")).strip()
    position_seconds_raw = data.get("positionSeconds", data.get("lastPositionSeconds", 0))
    try:
        position_seconds = max(0, int(position_seconds_raw or 0))
    except (TypeError, ValueError):
        position_seconds = 0
    enrollment, _created = models.Enrollment.objects.get_or_create(
        email=email,
        course=course,
        defaults={"user": user, "status": "active", "progress_percent": progress_percent},
    )
    enrollment.user = user
    lesson_progress_payload = None
    if lesson_id:
        lesson = lesson_by_key(lesson_id)
        if not lesson or lesson.module.course_id != course.pk:
            return error_response("Lesson not found for this course.", 404)
        lesson_progress, _lp_created = models.LessonProgress.objects.get_or_create(
            enrollment=enrollment,
            lesson=lesson,
            defaults={
                "user": user,
                "email": email,
                "status": "in_progress" if progress_percent > 0 else "not_started",
                "progress_percent": progress_percent,
                "last_position_seconds": position_seconds,
                "last_viewed_at": now(),
            },
        )
        lesson_progress.user = user
        lesson_progress.email = email
        lesson_progress.progress_percent = progress_percent
        lesson_progress.status = "completed" if progress_percent >= 100 else ("in_progress" if progress_percent > 0 else "not_started")
        lesson_progress.last_position_seconds = position_seconds
        lesson_progress.last_viewed_at = now()
        lesson_progress.completed_at = now() if progress_percent >= 100 else None
        lesson_progress.save(
            update_fields=[
                "user",
                "email",
                "progress_percent",
                "status",
                "last_position_seconds",
                "last_viewed_at",
                "completed_at",
            ]
        )
        enrollment.current_lesson = lesson
        lesson_progress_payload = {
            "lessonId": lesson.lesson_key,
            "status": lesson_progress.status,
            "progressPercent": lesson_progress.progress_percent,
            "lastPositionSeconds": lesson_progress.last_position_seconds,
            "completedAt": isoformat_z(lesson_progress.completed_at),
        }
        recalculate_enrollment_progress(enrollment)
    else:
        enrollment.progress_percent = progress_percent
        enrollment.status = "completed" if progress_percent >= 100 else "active"
        enrollment.completed_at = now() if progress_percent >= 100 else None
        enrollment.last_activity_at = now()
    enrollment.save()
    sync_student_profile_metrics(user=user, email=email)
    response_payload = {"ok": True, "enrollment": serialize_enrollment(enrollment)}
    if lesson_progress_payload:
        response_payload["lessonProgress"] = lesson_progress_payload
    return json_response(response_payload)


@csrf_exempt
def wishlist(request):
    ensure_seeded()
    if response := guard_method(request, {"GET", "POST"}):
        return response
    if request.method == "GET":
        user, email, _session = resolve_actor(request, query=request.GET.dict())
        course_ids = list(models.WishlistItem.objects.filter(email=email).values_list("course__slug", flat=True))
        return json_response({"ok": True, "email": email, "courseIds": course_ids})

    data = parse_request_data(request)
    course_id = str(data.get("courseId", "")).strip()
    if not course_id:
        return error_response("courseId is required.", 400)
    course = course_by_slug_or_404(course_id)
    if not course:
        return error_response("Course not found", 404)
    user, email, _session = resolve_actor(request, data=data)
    saved = data.get("saved")
    requested_saved = saved if isinstance(saved, bool) else str(saved).lower() != "false"
    if requested_saved:
        item, _created = models.WishlistItem.objects.get_or_create(email=email, course=course, defaults={"user": user})
        if user and item.user_id != user.pk:
            item.user = user
            item.save(update_fields=["user"])
    else:
        models.WishlistItem.objects.filter(email=email, course=course).delete()
    sync_student_profile_metrics(user=user, email=email)
    course_ids = list(models.WishlistItem.objects.filter(email=email).values_list("course__slug", flat=True))
    return json_response(
        {
            "ok": True,
            "email": email,
            "saved": requested_saved,
            "courseIds": course_ids,
            "course": serialize_course(course),
        }
    )


@csrf_exempt
def ai_tutor(request):
    if response := guard_method(request, {"POST"}):
        return response
    ensure_seeded()
    data = parse_request_data(request)
    prompt = str(data.get("prompt", "")).strip()
    if not prompt:
        return error_response("prompt is required.", 400)
    course = course_by_slug_or_404(str(data.get("courseId", "")).strip()) if data.get("courseId") else None
    user, email, _session = resolve_actor(request, data=data)
    reply = build_tutor_reply(prompt, serialize_course(course) if course else None)
    models.AIPromptLog.objects.create(
        user=user,
        email=email,
        course=course,
        lesson_id=str(data.get("lessonId", "") or ""),
        prompt=prompt,
        reply=reply,
    )
    return json_response({"ok": True, "reply": reply, "courseId": course.slug if course else None, "lessonId": data.get("lessonId")})


@csrf_exempt
def course_share(request):
    if response := guard_method(request, {"POST"}):
        return response
    ensure_seeded()
    data = parse_request_data(request)
    course_id = str(data.get("courseId", "")).strip()
    if not course_id:
        return error_response("courseId is required.", 400)
    course = course_by_slug_or_404(course_id)
    if not course:
        return error_response("Course not found", 404)
    user, email, _session = resolve_actor(request, data=data)
    share = models.CourseShare.objects.create(
        user=user,
        email=email,
        course=course,
        url=str(data.get("url") or request.build_absolute_uri(f"/#detail/{course.slug}")),
    )
    return json_response({"ok": True, "share": {"id": str(share.pk), "courseId": course.slug, "url": share.url, "email": share.email, "createdAt": isoformat_z(share.created_at)}, "course": serialize_course(course)})


@csrf_exempt
def gifts(request):
    if response := guard_method(request, {"POST"}):
        return response
    ensure_seeded()
    data = parse_request_data(request)
    course_id = str(data.get("courseId", "")).strip()
    recipient = normalize_email(data.get("email"))
    if not course_id:
        return error_response("courseId is required.", 400)
    if not validate_email(recipient):
        return error_response("A valid recipient email is required.", 400)
    course = course_by_slug_or_404(course_id)
    if not course:
        return error_response("Course not found", 404)
    user, email, _session = resolve_actor(request, data=data)
    gift = models.Gift.objects.create(user=user, email=email, course=course, recipient_email=recipient, status="pending")
    return json_response({"ok": True, "gift": {"id": str(gift.pk), "courseId": course.slug, "recipientEmail": gift.recipient_email, "senderEmail": gift.email, "status": gift.status, "createdAt": isoformat_z(gift.created_at)}, "course": serialize_course(course)}, status=201)


@csrf_exempt
def coupon_validate(request):
    if response := guard_method(request, {"POST"}):
        return response
    ensure_seeded()
    data = parse_request_data(request)
    course_id = str(data.get("courseId", "")).strip()
    code = str(data.get("code", "")).strip().upper()
    if not course_id:
        return error_response("courseId is required.", 400)
    if not code:
        return error_response("Coupon code is required.", 400)
    course = course_by_slug_or_404(course_id)
    if not course:
        return error_response("Course not found", 404)
    coupon = models.Coupon.objects.filter(code=code, active=True).first()
    if not coupon:
        return json_response({"ok": True, "valid": False, "code": code, "message": "Coupon not found or inactive."})
    discount_value = round(course.price_value * (coupon.value / 100)) if coupon.type == models.Coupon.TYPE_PERCENT else min(course.price_value, coupon.value)
    final_price = max(0, course.price_value - discount_value)
    return json_response({"ok": True, "valid": True, "code": code, "coupon": {"code": coupon.code, "type": coupon.type, "value": coupon.value, "active": coupon.active, "description": coupon.description}, "courseId": course.slug, "discountValue": discount_value, "finalPrice": final_price, "finalPriceLabel": f"{format_number(final_price)} ETB"})


@csrf_exempt
def lesson_questions(request):
    if response := guard_method(request, {"GET", "POST"}):
        return response
    ensure_seeded()
    if request.method == "POST":
        data = parse_request_data(request)
        user, _email, _session = resolve_actor(request, data=data)
        if access_error := require_instructor_access(user):
            return access_error
        action = str(data.get("action", "save")).strip().lower()
        question_id = str(data.get("id") or data.get("questionId") or "").strip()
        if action == "delete":
            if not question_id:
                return error_response("questionId is required.", 400)
            question = models.LessonQuestion.objects.select_related("course").filter(pk=question_id).first()
            if not question:
                return error_response("Question not found.", 404)
            if owner_error := require_course_owner_access(user, question.course):
                return owner_error
            question.delete()
            return json_response({"ok": True, "deleted": True, "questionId": question_id})

        course_id = str(data.get("courseId", "")).strip()
        lesson_id = str(data.get("lessonId", "")).strip()
        question_text = str(data.get("question", "")).strip()
        if not course_id:
            return error_response("courseId is required.", 400)
        if not question_text:
            return error_response("question is required.", 400)
        course = course_by_slug_or_404(course_id)
        if not course:
            return error_response("Course not found", 404)
        if owner_error := require_course_owner_access(user, course):
            return owner_error
        lesson = lesson_for_course(course, lesson_id)
        if lesson_id and not lesson:
            return error_response("Lesson not found for this course.", 404)
        if question_id:
            question = models.LessonQuestion.objects.filter(pk=question_id, course=course).first()
            if not question:
                return error_response("Question not found.", 404)
        else:
            question = models.LessonQuestion(course=course)
        question.lesson = lesson
        question.question = question_text
        question.answer = str(data.get("answer", "")).strip()
        question.timestamp_seconds = parse_seconds(data.get("timestamp", data.get("timestampSeconds", 0)))
        question.position = parse_seconds(data.get("position", question.position or 1), default=1) or 1
        question.is_published = str(data.get("isPublished", data.get("published", True))).lower() != "false"
        if isinstance(data.get("metadata"), dict):
            question.metadata = data["metadata"]
        question.save()
        return json_response({"ok": True, "question": serialize_question(question, set())}, status=201 if not question_id else 200)

    course_id = str(request.GET.get("courseId", "")).strip()
    lesson_id = str(request.GET.get("lessonId", "")).strip()
    if not course_id:
        return error_response("courseId query parameter is required.", 400)
    course = course_by_slug_or_404(course_id)
    if not course:
        return error_response("Course not found", 404)
    lesson = lesson_for_course(course, lesson_id)
    if lesson_id and not lesson:
        return error_response("Lesson not found for this course.", 404)
    user, email, _session = resolve_actor(request, query=request.GET.dict())
    completions = models.QuestionCompletion.objects.filter(email=email, course=course, completed=True)
    if lesson:
        completions = completions.filter(Q(lesson=lesson) | Q(lesson__isnull=True))
    completed_keys = set(completions.values_list("question_key", flat=True))
    queryset = models.LessonQuestion.objects.select_related("course", "lesson").filter(course=course, is_published=True)
    if lesson:
        queryset = queryset.filter(Q(lesson=lesson) | Q(lesson__isnull=True))
    questions = [serialize_question(item, completed_keys) for item in queryset]
    seen_ids = {item["id"] for item in questions}
    questions.extend(item for item in metadata_questions_for_lesson(course, lesson, completed_keys) if item["id"] not in seen_ids)
    questions.sort(key=lambda item: (parse_seconds(item.get("timestamp")), parse_seconds(item.get("position"))))
    return json_response({"ok": True, "courseId": course.slug, "lessonId": lesson.lesson_key if lesson else None, "count": len(questions), "questions": questions})


@csrf_exempt
def question_completion(request):
    if response := guard_method(request, {"POST"}):
        return response
    ensure_seeded()
    data = parse_request_data(request)
    user, email, _session = resolve_actor(request, data=data)
    if access_error := require_authenticated_access(user):
        return access_error
    course_id = str(data.get("courseId", "")).strip()
    question_key = str(data.get("questionId") or data.get("questionKey") or "").strip()
    if not course_id or not question_key:
        return error_response("courseId and questionId are required.", 400)
    course = course_by_slug_or_404(course_id)
    if not course:
        return error_response("Course not found", 404)
    lesson = lesson_for_course(course, str(data.get("lessonId", "")).strip())
    question = None
    try:
        question = models.LessonQuestion.objects.filter(pk=question_key, course=course).first()
    except (ValidationError, ValueError):
        question = None
    completed = data.get("completed")
    completed = completed if isinstance(completed, bool) else str(completed).lower() != "false"
    item, _created = models.QuestionCompletion.objects.update_or_create(
        email=email,
        course=course,
        question_key=question_key,
        defaults={
            "user": user,
            "lesson": lesson or (question.lesson if question else None),
            "question": question,
            "completed": completed,
            "completed_at": now() if completed else None,
        },
    )
    return json_response(
        {
            "ok": True,
            "completion": {
                "id": str(item.pk),
                "courseId": course.slug,
                "lessonId": item.lesson.lesson_key if item.lesson else None,
                "questionId": item.question_key,
                "completed": item.completed,
                "completedAt": isoformat_z(item.completed_at),
            },
        }
    )


@csrf_exempt
def notebook_notes(request):
    if response := guard_method(request, {"GET", "POST"}):
        return response
    ensure_seeded()
    if request.method == "GET":
        user, email, _session = resolve_actor(request, query=request.GET.dict())
        if access_error := require_authenticated_access(user):
            return access_error
        course_id = str(request.GET.get("courseId", "")).strip()
        if not course_id:
            return error_response("courseId query parameter is required.", 400)
        course = course_by_slug_or_404(course_id)
        if not course:
            return error_response("Course not found", 404)
        lesson_id = str(request.GET.get("lessonId", "")).strip()
        include_deleted = str(request.GET.get("includeDeleted", "")).lower() in {"1", "true", "yes"}
        query = str(request.GET.get("q", "")).strip()
        queryset = (
            models.NotebookNote.objects.filter(email=email, course=course)
            .select_related("course", "lesson")
            .prefetch_related("attachments", "versions")
        )
        if not include_deleted:
            queryset = queryset.filter(is_deleted=False)
        if lesson_id:
            queryset = queryset.filter(lesson__lesson_key=lesson_id)
        if query:
            queryset = queryset.filter(Q(title__icontains=query) | Q(body_preview__icontains=query) | Q(category__icontains=query))
        notes = [serialize_notebook_note(item, include_history=True) for item in queryset]
        return json_response({"ok": True, "courseId": course.slug, "count": len(notes), "notes": notes})

    data = parse_request_data(request)
    user, email, _session = resolve_actor(request, data=data)
    if access_error := require_authenticated_access(user):
        return access_error
    note_data = data.get("note") if isinstance(data.get("note"), dict) else data
    action = str(data.get("action") or note_data.get("action") or "save").strip().lower()
    note_id = str(note_data.get("id") or data.get("noteId") or "").strip()
    client_note_id = note_id
    if note_id and not is_uuid_like(note_id):
        note_id = ""

    if action == "delete":
        if not note_id:
            if client_note_id:
                return json_response({"ok": True, "deleted": True, "noteId": client_note_id})
            return error_response("noteId is required.", 400)
        note = models.NotebookNote.objects.filter(pk=note_id, email=email).first()
        if not note:
            return error_response("Note not found.", 404)
        note.is_deleted = True
        note.deleted_at = now()
        note.last_synced_at = now()
        note.save(update_fields=["is_deleted", "deleted_at", "last_synced_at", "updated_at"])
        return json_response({"ok": True, "deleted": True, "note": serialize_notebook_note(note, include_history=True)})

    if action == "restore_version":
        version_id = str(data.get("versionId") or note_data.get("versionId") or "").strip()
        version = models.NotebookNoteVersion.objects.select_related("note", "note__course", "note__lesson").filter(pk=version_id, note__email=email).first()
        if not version:
            return error_response("Note version not found.", 404)
        note = version.note
        snapshot_note_version(note)
        note.title = version.title
        note.encrypted_body = version.encrypted_body
        note.body_preview = version.body_preview
        note.category = version.category
        note.tags = version.tags
        note.timestamp_seconds = version.timestamp_seconds
        note.metadata = version.metadata
        note.version += 1
        note.is_deleted = False
        note.deleted_at = None
        note.last_synced_at = now()
        note.save()
        return json_response({"ok": True, "note": serialize_notebook_note(note, include_history=True)})

    course_id = str(note_data.get("courseId", "")).strip()
    if not course_id and note_id:
        existing_note = models.NotebookNote.objects.filter(pk=note_id, email=email).select_related("course").first()
        course_id = existing_note.course.slug if existing_note else ""
    if not course_id:
        return error_response("courseId is required.", 400)
    course = course_by_slug_or_404(course_id)
    if not course:
        return error_response("Course not found", 404)
    lesson = lesson_for_course(course, str(note_data.get("lessonId", "")).strip())
    if note_data.get("lessonId") and not lesson:
        return error_response("Lesson not found for this course.", 404)
    body = str(note_data.get("body", note_data.get("html", note_data.get("content", ""))) or "")
    title = str(note_data.get("title") or note_body_preview(body)[:80] or "Untitled note").strip()
    if note_id:
        note = models.NotebookNote.objects.filter(pk=note_id, email=email, course=course).first()
        if not note:
            return error_response("Note not found.", 404)
        snapshot_note_version(note)
        note.version += 1
    else:
        note = models.NotebookNote(email=email, user=user, course=course, version=1)
    note.user = user
    note.email = email
    note.course = course
    note.lesson = lesson
    note.title = title[:255]
    note.encrypted_body = protect_note_body(body)
    note.body_preview = note_body_preview(body)
    note.category = str(note_data.get("category") or "General").strip()[:120] or "General"
    note.tags = coerce_string_list(note_data.get("tags"))
    note.pinned = bool(note_data.get("pinned", False))
    note.timestamp_seconds = parse_seconds(note_data.get("timestamp", note_data.get("timestampSeconds", 0)))
    note.metadata = note_data.get("metadata") if isinstance(note_data.get("metadata"), dict) else {}
    note.shared_with = coerce_string_list(note_data.get("sharedWith", note_data.get("shared_with", [])))
    note.is_deleted = False
    note.deleted_at = None
    note.last_synced_at = now()
    note.save()
    return json_response({"ok": True, "note": serialize_notebook_note(note, include_history=True)}, status=201 if not note_id else 200)


@csrf_exempt
def notebook_attachments(request):
    if response := guard_method(request, {"POST"}):
        return response
    ensure_seeded()
    user, email, _session = resolve_actor(request, data=request.POST.dict())
    if access_error := require_authenticated_access(user):
        return access_error
    course_id = str(request.POST.get("courseId", "")).strip()
    if not course_id:
        return error_response("courseId is required.", 400)
    course = course_by_slug_or_404(course_id)
    if not course:
        return error_response("Course not found", 404)
    note = None
    note_id = str(request.POST.get("noteId", "")).strip()
    if note_id:
        if not is_uuid_like(note_id):
            note = None
        else:
            note = models.NotebookNote.objects.filter(pk=note_id, email=email, course=course).first()
        if not note:
            note = None
    upload = request.FILES.get("file")
    if not upload:
        return error_response("file is required.", 400)
    attachment = models.NotebookAttachment.objects.create(
        user=user,
        email=email,
        course=course,
        note=note,
        file=upload,
        name=upload.name,
        content_type=getattr(upload, "content_type", "") or "",
        size=upload.size,
    )
    return json_response({"ok": True, "attachment": serialize_notebook_attachment(attachment)}, status=201)


@csrf_exempt
def assignments(request):
    if response := guard_method(request, {"GET", "POST"}):
        return response
    ensure_seeded()
    if request.method == "GET":
        user, email, _session = resolve_actor(request, query=request.GET.dict())
        if access_error := require_authenticated_access(user):
            return access_error
        course_id = str(request.GET.get("courseId", "")).strip()
        queryset = models.AssignmentSubmission.objects.select_related("course", "lesson", "lesson__module")
        if can_manage_instructor_content(user):
            if course_id:
                queryset = queryset.filter(course__slug=course_id)
            elif not can_access_admin_dashboard(user):
                queryset = queryset.filter(course__created_by=user)
        else:
            queryset = queryset.filter(email=email)
            if course_id:
                queryset = queryset.filter(course__slug=course_id)
        submissions = [
            {
                "id": str(item.pk),
                "courseId": item.course.slug,
                "courseTitle": item.course.title,
                "lessonId": item.lesson.lesson_key,
                "lessonTitle": item.lesson.title,
                "email": item.email,
                "response": item.response,
                "status": item.status,
                "grade": item.grade,
                "feedback": item.feedback,
                "updatedAt": isoformat_z(item.updated_at),
            }
            for item in queryset
        ]
        return json_response({"ok": True, "count": len(submissions), "submissions": submissions})

    data = parse_request_data(request)
    user, email, _session = resolve_actor(request, data=data)
    if access_error := require_authenticated_access(user):
        return access_error
    course_id = str(data.get("courseId", "")).strip()
    lesson_id = str(data.get("lessonId", "")).strip()
    if not course_id or not lesson_id:
        return error_response("courseId and lessonId are required.", 400)
    course = course_by_slug_or_404(course_id)
    if not course:
        return error_response("Course not found", 404)
    lesson = lesson_for_course(course, lesson_id)
    if not lesson:
        return error_response("Lesson not found for this course.", 404)
    submission, _created = models.AssignmentSubmission.objects.update_or_create(
        email=email,
        lesson=lesson,
        defaults={
            "user": user,
            "course": course,
            "response": str(data.get("response", "")),
            "status": str(data.get("status", "draft")).strip() or "draft",
        },
    )
    return json_response({"ok": True, "submissionId": str(submission.pk), "status": submission.status, "updatedAt": isoformat_z(submission.updated_at)})


@csrf_exempt
def notes(request):
    if response := guard_method(request, {"GET", "POST"}):
        return response
    ensure_seeded()
    if request.method == "GET":
        course_id = str(request.GET.get("courseId", "")).strip()
        if not course_id:
            return error_response("courseId query parameter is required.", 400)
        course = course_by_slug_or_404(course_id)
        if not course:
            return error_response("Course not found", 404)
        user, email, _session = resolve_actor(request, query=request.GET.dict())
        note = models.UserCourseNote.objects.filter(email=email, course=course).first()
        return json_response({"ok": True, "email": email, "courseId": course.slug, "note": {"notes": note.notes, "updatedAt": isoformat_z(note.updated_at)} if note else None})

    data = parse_request_data(request)
    course_id = str(data.get("courseId", "")).strip()
    if not course_id:
        return error_response("courseId is required.", 400)
    course = course_by_slug_or_404(course_id)
    if not course:
        return error_response("Course not found", 404)
    user, email, _session = resolve_actor(request, data=data)
    note, _created = models.UserCourseNote.objects.update_or_create(
        email=email,
        course=course,
        defaults={"user": user, "notes": str(data.get("notes", ""))},
    )
    return json_response({"ok": True, "email": email, "courseId": course.slug, "note": {"notes": note.notes, "updatedAt": isoformat_z(note.updated_at)}, "course": serialize_course(course)})


@csrf_exempt
def notifications(request):
    if response := guard_method(request, {"GET", "POST"}):
        return response
    if request.method == "POST":
        data = parse_request_data(request)
        user, email, _session = resolve_actor(request, data=data)
        if access_error := require_instructor_access(user):
            return access_error
        audience = str(data.get("audience", data.get("audienceEmail", "all"))).strip()
        title = str(data.get("title", "")).strip()
        message = str(data.get("message", "")).strip()
        if not title or not message:
            return error_response("title and message are required.", 400)
        notification = models.PlatformNotification.objects.create(
            audience_scope=models.PlatformNotification.SCOPE_ALL if audience == "all" else models.PlatformNotification.SCOPE_EMAIL,
            audience_email="" if audience == "all" else normalize_email(audience),
            title=title,
            message=message,
        )
        return json_response(
            {
                "ok": True,
                "notification": {
                    "id": str(notification.pk),
                    "audience": audience or email,
                    "title": notification.title,
                    "message": notification.message,
                    "createdAt": isoformat_z(notification.created_at),
                },
            },
            status=201,
        )
    user, email, _session = resolve_actor(request, query=request.GET.dict())
    items = active_notifications_for(email, user=user)
    return json_response({"ok": True, "email": email, "count": items.count(), "notifications": [{"id": str(item.pk), "audience": item.audience_scope if item.audience_scope == models.PlatformNotification.SCOPE_ALL else (item.audience_email or email), "title": item.title, "message": item.message, "createdAt": isoformat_z(item.created_at)} for item in items]})


@csrf_exempt
def instructor_drafts(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    user, email, _session = resolve_actor(request, data=data)
    if access_error := require_instructor_access(user):
        return access_error
    draft = models.InstructorDraftRequest.objects.create(
        user=user,
        email=email,
        instructor_name=str(data.get("instructor", "Yonas Tesfaye")).strip(),
        status="open",
    )
    return json_response({"ok": True, "draft": {"id": str(draft.pk), "instructor": draft.instructor_name, "status": draft.status, "createdAt": isoformat_z(draft.created_at)}}, status=201)


@csrf_exempt
def instructor_courses(request):
    ensure_seeded()
    if response := guard_method(request, {"GET", "POST"}):
        return response
    if request.method == "GET":
        user, _email, _session = resolve_actor(request, query=request.GET.dict())
        instructor = str(request.GET.get("instructor", "")).strip()
        mine_only = str(request.GET.get("mine", "")).strip().lower() in {"1", "true", "yes"}
        queryset = models.Course.objects.select_related("category_ref", "created_by").prefetch_related("course_modules__lessons").all()
        if instructor:
            queryset = queryset.filter(instructor_name__iexact=instructor)
        if mine_only and user:
            queryset = queryset.filter(created_by=user)
        courses = [serialize_course(course) for course in queryset]
        return json_response({"ok": True, "count": len(courses), "courses": courses})

    data = parse_request_data(request)
    input_course = data.get("course") if isinstance(data.get("course"), dict) else data
    title = str(input_course.get("title", "")).strip()
    overview = str(input_course.get("overview", "")).strip()
    instructor = str(input_course.get("instructor", "Yonas Tesfaye")).strip()
    if not title or not overview or not instructor:
        return error_response("title, overview, and instructor are required.", 400)
    user, _email, _session = resolve_actor(request, data=data)
    if access_error := require_instructor_access(user):
        return access_error
    existing_course_id = str(input_course.get("id", "")).strip()
    if existing_course_id:
        existing_course = course_by_slug_or_404(existing_course_id)
        if access_error := require_course_owner_access(user, existing_course):
            return access_error
    course, created = create_or_update_course_from_input(input_course, user=user)
    return json_response({"ok": True, "created": created, "course": serialize_course(course)}, status=201 if created else 200)


@csrf_exempt
def instructor_thumbnail(request):
    if response := guard_method(request, {"POST"}):
        return response
    ensure_seeded()
    data = parse_request_data(request)
    course_id = str(data.get("courseId", "")).strip()
    thumbnail = str(data.get("thumbnail", "")).strip()
    if not course_id:
        return error_response("courseId is required.", 400)
    user, _email, _session = resolve_actor(request, data=data)
    course = course_by_slug_or_404(course_id)
    if access_error := require_course_owner_access(user, course):
        return access_error
    course.thumbnail = thumbnail
    course.save(update_fields=["thumbnail", "updated_at"])
    return json_response({"ok": True, "course": serialize_course(course)})


@csrf_exempt
def instructor_course_assets(request):
    if response := guard_method(request, {"POST"}):
        return response
    ensure_seeded()
    course_id = str(request.POST.get("courseId", "")).strip()
    lesson_id = str(request.POST.get("lessonId", "")).strip()
    if not course_id:
        return error_response("courseId is required.", 400)
    upload = request.FILES.get("file")
    if not upload:
        return error_response("file is required.", 400)
    user, _email, _session = resolve_actor(request, data=request.POST.dict())
    course = course_by_slug_or_404(course_id)
    if access_error := require_course_owner_access(user, course):
        return access_error

    extension = Path(upload.name or "").suffix.lower()
    safe_filename = build_token(10)
    relative_path = default_storage.save(f"course-assets/{course.slug}/{safe_filename}{extension}", upload)
    asset_url = default_storage.url(relative_path)

    attached_lesson = None
    if lesson_id:
        attached_lesson = models.CourseLesson.objects.select_related("module", "module__course").filter(
            lesson_key=lesson_id,
            module__course=course,
        ).first()
        if attached_lesson:
            attached_lesson.asset_url = asset_url
            attached_lesson.save(update_fields=["asset_url", "updated_at"])

    refreshed_course = course_by_slug_or_404(course_id) or course
    return json_response(
        {
            "ok": True,
            "asset": {
                "name": upload.name,
                "size": upload.size,
                "contentType": getattr(upload, "content_type", "") or "",
                "url": asset_url,
                "path": relative_path,
                "lessonId": attached_lesson.lesson_key if attached_lesson else None,
                "attachedToLesson": bool(attached_lesson),
            },
            "course": serialize_course(refreshed_course),
        },
        status=201,
    )


@csrf_exempt
def dashboard_tab(request):
    if response := guard_method(request, {"GET", "POST"}):
        return response
    if request.method == "GET":
        user, email, _session = resolve_actor(request, query=request.GET.dict())
        selection = models.DashboardSelection.objects.filter(email=email).first()
        return json_response(
            {
                "ok": True,
                "selection": (
                    {
                        "id": str(selection.pk),
                        "tab": selection.tab,
                        "email": selection.email,
                        "createdAt": isoformat_z(selection.created_at),
                    }
                    if selection
                    else None
                ),
            }
        )
    data = parse_request_data(request)
    tab = str(data.get("tab", "")).strip()
    if not tab:
        return error_response("tab is required.", 400)
    user, email, _session = resolve_actor(request, data=data)
    selection = models.DashboardSelection.objects.create(user=user, email=email, tab=tab)
    return json_response({"ok": True, "selection": {"id": str(selection.pk), "tab": selection.tab, "email": selection.email, "createdAt": isoformat_z(selection.created_at)}})


def _certificate_action(request, action: str):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    user, email, _session = resolve_actor(request, data=data)
    record = models.CertificateAction.objects.create(user=user, email=email, action=action, name=str(data.get("name", "Certificate")).strip())
    return json_response({"ok": True, "action": action, "certificate": {"id": str(record.pk), "action": record.action, "name": record.name, "email": record.email, "createdAt": isoformat_z(record.created_at)}})


@csrf_exempt
def certificate_share(request):
    return _certificate_action(request, "share")


@csrf_exempt
def certificate_preview(request):
    return _certificate_action(request, "preview")
