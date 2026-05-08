from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterable

from django.contrib.auth import get_user_model
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from . import models
from .catalog import build_tutor_reply
from .services import (
    AUTH_COOKIE_NAME,
    active_notifications_for,
    clear_auth_cookie,
    course_by_slug_or_404,
    create_api_session,
    create_or_update_course_from_input,
    create_password_reset_token,
    extract_session_token,
    get_authenticated_context,
    isoformat_z,
    log_in_user,
    log_out_user,
    now,
    resolve_actor,
    revoke_sessions,
    seed_database,
    serialize_course,
    serialize_session,
    serialize_user,
    set_auth_cookie,
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
    response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


def json_response(payload: dict[str, Any], status: int = 200) -> JsonResponse:
    return add_cors_headers(JsonResponse(payload, status=status))


def options_response() -> HttpResponse:
    return add_cors_headers(HttpResponse(status=204))


def error_response(message: str, status: int) -> JsonResponse:
    return json_response({"ok": False, "message": message}, status=status)


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


def index(request):
    if request.method not in {"GET", "HEAD"}:
        return error_response("Method not allowed", 405)
    html = INDEX_PATH.read_text(encoding="utf-8")
    script_tag = '<script src="/frontend-auth.js"></script>'
    if script_tag not in html:
        html = html.replace("</body>", f"{script_tag}\n</body>")
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    return add_cors_headers(response)


def frontend_auth_script(request):
    if request.method not in {"GET", "HEAD"}:
        return error_response("Method not allowed", 405)
    script = FRONTEND_AUTH_SCRIPT_PATH.read_text(encoding="utf-8")
    response = HttpResponse(script, content_type="application/javascript; charset=utf-8")
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
def course_list(request):
    if response := guard_method(request, {"GET"}):
        return response
    ensure_seeded()
    courses = [serialize_course(course) for course in models.Course.objects.all()]
    return json_response({"ok": True, "count": len(courses), "courses": courses})


@csrf_exempt
def course_detail(request, course_id: str):
    if response := guard_method(request, {"GET"}):
        return response
    ensure_seeded()
    course = course_by_slug_or_404(course_id)
    if not course:
        return error_response("Course not found", 404)
    return json_response({"ok": True, "course": serialize_course(course)})


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


def _auth_success_response(request, user, session, status=200):
    response = json_response(
        {
            "ok": True,
            "user": serialize_user(user),
            "token": session.token,
            "session": serialize_session(session),
        },
        status=status,
    )
    return set_auth_cookie(response, session.token)


@csrf_exempt
def auth_signup(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    first_name = str(data.get("firstName", "")).strip()
    last_name = str(data.get("lastName", "")).strip()
    email = normalize_email(data.get("email"))
    password = str(data.get("password", ""))
    if not first_name or not last_name:
        return error_response("First name and last name are required.", 400)
    if not validate_email(email):
        return error_response("A valid email address is required.", 400)
    if len(password) < 8:
        return error_response("Password must be at least 8 characters.", 400)

    User = get_user_model()
    if User.objects.filter(email=email).exists():
        return error_response("An account with that email already exists.", 409)

    user = User.objects.create_user(
        email=email,
        first_name=first_name,
        last_name=last_name,
        password=password,
    )
    models.AuthAuditLog.objects.create(user=user, email=email, action="signup")
    models.PlatformNotification.objects.create(
        audience_scope=models.PlatformNotification.SCOPE_USER,
        audience_user=user,
        audience_email=email,
        title="Account created",
        message="Your SkillForge learner account is ready.",
    )
    log_in_user(request, user)
    session = create_api_session(user, request)
    return _auth_success_response(request, user, session, status=201)


@csrf_exempt
def auth_login(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    email = normalize_email(data.get("email"))
    password = str(data.get("password", ""))
    if not validate_email(email):
        return error_response("A valid email address is required.", 400)
    if len(password) < 8:
        return error_response("Password must be at least 8 characters.", 400)

    User = get_user_model()
    user = User.objects.filter(email=email).first()
    if not user or not user.check_password(password):
        return error_response("Invalid email or password.", 401)

    log_in_user(request, user)
    session = create_api_session(user, request)
    models.AuthAuditLog.objects.create(user=user, email=user.email or email, action="login")
    return _auth_success_response(request, user, session)


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
    token = extract_session_token(request, data)
    if user:
        revoke_sessions(user, token=token, all_sessions=(str(data.get("allSessions", "")).lower() == "true" or data.get("allSessions") is True))
        models.AuthAuditLog.objects.create(user=user, email=user.email or DEFAULT_ACTOR_EMAIL, action="logout")
    log_out_user(request)
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
    if not validate_email(email):
        return error_response("A valid email address is required.", 400)
    User = get_user_model()
    user = User.objects.filter(email=email).first()
    payload = {"ok": True, "message": "If that email exists, a password reset has been prepared."}
    if user:
        reset_token = create_password_reset_token(user)
        models.AuthAuditLog.objects.create(user=user, email=email, action="password_reset.request")
        payload["resetToken"] = reset_token.token
        payload["expiresAt"] = isoformat_z(reset_token.expires_at)
    return json_response(payload)


@csrf_exempt
def auth_password_reset_confirm(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    token = str(data.get("token", "")).strip()
    password = str(data.get("password", ""))
    if not token:
        return error_response("Reset token is required.", 400)
    if len(password) < 8:
        return error_response("Password must be at least 8 characters.", 400)
    reset_record = models.PasswordResetToken.objects.select_related("user").filter(token=token).first()
    if not reset_record:
        return error_response("Reset token is invalid.", 400)
    if reset_record.consumed_at:
        return error_response("Reset token has already been used.", 409)
    if reset_record.expires_at <= now():
        return error_response("Reset token has expired.", 410)

    user = reset_record.user
    user.set_password(password)
    user.save(update_fields=["password"])
    revoke_sessions(user, all_sessions=True)
    reset_record.consumed_at = now()
    reset_record.save(update_fields=["consumed_at"])
    log_in_user(request, user)
    session = create_api_session(user, request)
    models.AuthAuditLog.objects.create(user=user, email=user.email or DEFAULT_ACTOR_EMAIL, action="password_reset.confirm")
    return _auth_success_response(request, user, session)


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
    if created:
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
            "enrollment": {
                "id": str(enrollment.pk),
                "courseId": course.slug,
                "email": enrollment.email,
                "status": enrollment.status,
                "progressPercent": enrollment.progress_percent,
                "createdAt": isoformat_z(enrollment.created_at),
            },
        },
        status=201 if created else 200,
    )


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
    if response := guard_method(request, {"GET"}):
        return response
    user, email, _session = resolve_actor(request, query=request.GET.dict())
    items = active_notifications_for(email, user=user)
    return json_response({"ok": True, "email": email, "count": items.count(), "notifications": [{"id": str(item.pk), "audience": item.audience_scope if item.audience_scope == models.PlatformNotification.SCOPE_ALL else (item.audience_email or email), "title": item.title, "message": item.message, "createdAt": isoformat_z(item.created_at)} for item in items]})


@csrf_exempt
def instructor_drafts(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    user, email, _session = resolve_actor(request, data=data)
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
        instructor = str(request.GET.get("instructor", "")).strip()
        queryset = models.Course.objects.all()
        if instructor:
            queryset = queryset.filter(instructor_name__iexact=instructor)
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
    course = course_by_slug_or_404(course_id)
    if not course:
        return error_response("Course not found", 404)
    course.thumbnail = thumbnail
    course.save(update_fields=["thumbnail", "updated_at"])
    return json_response({"ok": True, "course": serialize_course(course)})


@csrf_exempt
def dashboard_tab(request):
    if response := guard_method(request, {"POST"}):
        return response
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
