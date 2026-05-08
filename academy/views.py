from __future__ import annotations

import json
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
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
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


def index(request):
    if request.method not in {"GET", "HEAD"}:
        return error_response("Method not allowed", 405)
    get_token(request)
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
