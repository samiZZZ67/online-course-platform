from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .seed import build_tutor_reply, find_course_by_id, get_catalog_courses, normalize_course_input
from .store import read_store, update_store
from .utils import (
    DEFAULT_ACTOR_EMAIL,
    build_id,
    build_token,
    format_number,
    hash_password,
    normalize_email,
    slugify,
    validate_email,
    verify_password,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = PROJECT_ROOT / "index.html"


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


def actor_email_from(data: dict[str, Any] | None = None, query: dict[str, Any] | None = None) -> str:
    data = data or {}
    query = query or {}
    email = normalize_email(
        data.get("email")
        or data.get("userEmail")
        or data.get("actorEmail")
        or query.get("email")
    )
    return email if validate_email(email) else DEFAULT_ACTOR_EMAIL


def to_public_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "firstName": user["firstName"],
        "lastName": user["lastName"],
        "email": user["email"],
        "role": user["role"],
        "createdAt": user["createdAt"],
    }


def resolve_unique_course_id(
    store: dict[str, Any],
    requested_id: str,
    title: str,
    existing_custom_id: str | None = None,
) -> str:
    taken = {
        course["id"]
        for course in store.get("courses", {}).get("base", [])
    }
    taken.update(
        course["id"]
        for course in store.get("courses", {}).get("custom", [])
        if course["id"] != existing_custom_id
    )
    base = (requested_id or slugify(title)).strip()
    if base not in taken:
        return base
    suffix = 2
    candidate = f"{base}-{suffix}"
    while candidate in taken:
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


def index(request):
    if request.method not in {"GET", "HEAD"}:
        return error_response("Method not allowed", 405)
    html = INDEX_PATH.read_text(encoding="utf-8")
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    return add_cors_headers(response)


def api_not_found(request):
    if request.method == "OPTIONS":
        return options_response()
    return error_response("Route not found", 404)


@csrf_exempt
def health(request):
    if response := guard_method(request, {"GET"}):
        return response
    store = read_store()
    return json_response(
        {
            "ok": True,
            "service": "skillforge-backend-django",
            "now": datetime.utcnow().isoformat() + "Z",
            "stats": {
                "users": len(store.get("users", [])),
                "courses": len(get_catalog_courses(store)),
                "enrollments": len(store.get("enrollments", [])),
                "newsletterSubscribers": len(store.get("newsletterSubscribers", [])),
            },
        }
    )


@csrf_exempt
def course_list(request):
    if response := guard_method(request, {"GET"}):
        return response
    store = read_store()
    courses = get_catalog_courses(store)
    return json_response({"ok": True, "count": len(courses), "courses": courses})


@csrf_exempt
def course_detail(request, course_id: str):
    if response := guard_method(request, {"GET"}):
        return response
    store = read_store()
    course = find_course_by_id(store, course_id)
    if not course:
        return error_response("Course not found", 404)
    return json_response({"ok": True, "course": course})


@csrf_exempt
def course_resources(request, course_id: str):
    if response := guard_method(request, {"GET", "POST"}):
        return response
    data = parse_request_data(request)
    store = read_store()
    course = find_course_by_id(store, course_id)
    if not course:
        return error_response("Course not found", 404)
    resource_name = str(data.get("resource") or request.GET.get("resource") or "").strip()
    if not resource_name:
        return json_response({"ok": True, "courseId": course_id, "resources": course.get("resources", [])})
    download_url = request.build_absolute_uri(
        f"/downloads/{course_id}/{resource_name}"
    )
    return json_response(
        {
            "ok": True,
            "courseId": course_id,
            "resource": resource_name,
            "downloadUrl": download_url,
            "message": "Resource delivery is prepared for signed URLs or authenticated downloads.",
        }
    )


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

    def mutate(store: dict[str, Any]):
        if any(user["email"] == email for user in store.get("users", [])):
            return {"type": "conflict"}
        now = datetime.utcnow().isoformat() + "Z"
        user = {
            "id": build_id("user"),
            "firstName": first_name,
            "lastName": last_name,
            "email": email,
            "passwordHash": hash_password(password),
            "role": "student",
            "createdAt": now,
        }
        session = {
            "id": build_id("session"),
            "userId": user["id"],
            "token": build_token("session"),
            "createdAt": now,
        }
        store.setdefault("users", []).append(user)
        store.setdefault("sessions", []).append(session)
        store.setdefault("authAudit", []).append(
            {"id": build_id("audit"), "type": "signup", "email": email, "createdAt": now}
        )
        store.setdefault("notifications", []).insert(
            0,
            {
                "id": build_id("notice"),
                "audience": email,
                "title": "Account created",
                "message": "Your SkillForge learner account is ready.",
                "createdAt": now,
            },
        )
        return {"type": "created", "user": user, "session": session}

    result = update_store(mutate)
    if result["type"] == "conflict":
        return error_response("An account with that email already exists.", 409)
    return json_response(
        {"ok": True, "user": to_public_user(result["user"]), "token": result["session"]["token"]},
        status=201,
    )


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

    def mutate(store: dict[str, Any]):
        user = next((entry for entry in store.get("users", []) if entry["email"] == email), None)
        if not user or not verify_password(password, user["passwordHash"]):
            return {"type": "invalid"}
        now = datetime.utcnow().isoformat() + "Z"
        session = {
            "id": build_id("session"),
            "userId": user["id"],
            "token": build_token("session"),
            "createdAt": now,
        }
        store.setdefault("sessions", []).append(session)
        store.setdefault("authAudit", []).append(
            {"id": build_id("audit"), "type": "login", "email": email, "createdAt": now}
        )
        return {"type": "ok", "user": user, "session": session}

    result = update_store(mutate)
    if result["type"] == "invalid":
        return error_response("Invalid email or password.", 401)
    return json_response({"ok": True, "user": to_public_user(result["user"]), "token": result["session"]["token"]})


@csrf_exempt
def auth_oauth_start(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    provider = str(data.get("provider", "")).strip().lower()
    if provider != "google":
        return error_response("Only google is configured in the current frontend contract.", 400)

    def mutate(store: dict[str, Any]):
        oauth_state = {
            "id": build_id("oauth"),
            "provider": provider,
            "state": build_token("state"),
            "createdAt": datetime.utcnow().isoformat() + "Z",
        }
        store.setdefault("oauthStates", []).append(oauth_state)
        return oauth_state

    oauth_state = update_store(mutate)
    return json_response(
        {
            "ok": True,
            "provider": provider,
            "state": oauth_state["state"],
            "authorizationUrl": f"https://accounts.google.com/o/oauth2/v2/auth?state={oauth_state['state']}",
        }
    )


@csrf_exempt
def newsletter_subscribe(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    email = normalize_email(data.get("email"))
    if not validate_email(email):
        return error_response("A valid email address is required.", 400)

    def mutate(store: dict[str, Any]):
        now = datetime.utcnow().isoformat() + "Z"
        existing = next(
            (entry for entry in store.get("newsletterSubscribers", []) if entry["email"] == email),
            None,
        )
        if existing:
            existing["status"] = "subscribed"
            existing["updatedAt"] = now
            return existing
        subscriber = {
            "id": build_id("newsletter"),
            "email": email,
            "status": "subscribed",
            "subscribedAt": now,
            "updatedAt": now,
        }
        store.setdefault("newsletterSubscribers", []).append(subscriber)
        return subscriber

    subscriber = update_store(mutate)
    return json_response({"ok": True, "subscriber": subscriber})


@csrf_exempt
def enrollments(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    course_id = str(data.get("courseId", "")).strip()
    if not course_id:
        return error_response("courseId is required.", 400)

    def mutate(store: dict[str, Any]):
        course = find_course_by_id(store, course_id)
        if not course:
            return {"type": "missing-course"}
        email = actor_email_from(data)
        existing = next(
            (
                entry
                for entry in store.get("enrollments", [])
                if entry["courseId"] == course_id and entry["email"] == email
            ),
            None,
        )
        if existing:
            return {"type": "existing", "course": course, "enrollment": existing}
        now = datetime.utcnow().isoformat() + "Z"
        enrollment = {
            "id": build_id("enrollment"),
            "courseId": course_id,
            "email": email,
            "status": "active",
            "progressPercent": 0,
            "createdAt": now,
        }
        store.setdefault("enrollments", []).append(enrollment)
        store.setdefault("notifications", []).insert(
            0,
            {
                "id": build_id("notice"),
                "audience": email,
                "title": "Enrollment confirmed",
                "message": f"You are enrolled in {course['title']}.",
                "createdAt": now,
            },
        )
        return {"type": "created", "course": course, "enrollment": enrollment}

    result = update_store(mutate)
    if result["type"] == "missing-course":
        return error_response("Course not found", 404)
    status_code = 201 if result["type"] == "created" else 200
    return json_response(
        {
            "ok": True,
            "created": result["type"] == "created",
            "course": result["course"],
            "enrollment": result["enrollment"],
        },
        status=status_code,
    )


@csrf_exempt
def wishlist(request):
    if response := guard_method(request, {"GET", "POST"}):
        return response
    if request.method == "GET":
        store = read_store()
        email = actor_email_from(query=request.GET.dict())
        return json_response({"ok": True, "email": email, "courseIds": store.get("wishlist", {}).get(email, [])})

    data = parse_request_data(request)
    course_id = str(data.get("courseId", "")).strip()
    if not course_id:
        return error_response("courseId is required.", 400)

    def mutate(store: dict[str, Any]):
        course = find_course_by_id(store, course_id)
        if not course:
            return {"type": "missing-course"}
        email = actor_email_from(data)
        store.setdefault("wishlist", {})
        current = set(store["wishlist"].get(email, []))
        saved = data.get("saved")
        requested_saved = saved if isinstance(saved, bool) else str(saved).lower() != "false"
        if requested_saved:
            current.add(course_id)
        else:
            current.discard(course_id)
        store["wishlist"][email] = list(current)
        return {
            "type": "ok",
            "email": email,
            "saved": requested_saved,
            "courseIds": store["wishlist"][email],
            "course": course,
        }

    result = update_store(mutate)
    if result["type"] == "missing-course":
        return error_response("Course not found", 404)
    return json_response(
        {
            "ok": True,
            "email": result["email"],
            "saved": result["saved"],
            "courseIds": result["courseIds"],
            "course": result["course"],
        }
    )


@csrf_exempt
def ai_tutor(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    prompt = str(data.get("prompt", "")).strip()
    if not prompt:
        return error_response("prompt is required.", 400)

    def mutate(store: dict[str, Any]):
        course = find_course_by_id(store, str(data.get("courseId", "")).strip()) if data.get("courseId") else None
        reply = build_tutor_reply(prompt, course)
        record = {
            "id": build_id("ai"),
            "prompt": prompt,
            "reply": reply,
            "courseId": course["id"] if course else None,
            "lessonId": data.get("lessonId"),
            "createdAt": datetime.utcnow().isoformat() + "Z",
        }
        store.setdefault("aiPrompts", []).append(record)
        return record

    record = update_store(mutate)
    return json_response(
        {
            "ok": True,
            "reply": record["reply"],
            "courseId": record["courseId"],
            "lessonId": record["lessonId"],
        }
    )


@csrf_exempt
def course_share(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    course_id = str(data.get("courseId", "")).strip()
    if not course_id:
        return error_response("courseId is required.", 400)

    def mutate(store: dict[str, Any]):
        course = find_course_by_id(store, course_id)
        if not course:
            return {"type": "missing-course"}
        share = {
            "id": build_id("share"),
            "courseId": course_id,
            "url": str(data.get("url") or request.build_absolute_uri(f"/#detail/{course_id}")),
            "email": actor_email_from(data),
            "createdAt": datetime.utcnow().isoformat() + "Z",
        }
        store.setdefault("shares", []).append(share)
        return {"type": "ok", "share": share, "course": course}

    result = update_store(mutate)
    if result["type"] == "missing-course":
        return error_response("Course not found", 404)
    return json_response({"ok": True, "share": result["share"], "course": result["course"]})


@csrf_exempt
def gifts(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    course_id = str(data.get("courseId", "")).strip()
    recipient = normalize_email(data.get("email"))
    if not course_id:
        return error_response("courseId is required.", 400)
    if not validate_email(recipient):
        return error_response("A valid recipient email is required.", 400)

    def mutate(store: dict[str, Any]):
        course = find_course_by_id(store, course_id)
        if not course:
            return {"type": "missing-course"}
        gift = {
            "id": build_id("gift"),
            "courseId": course_id,
            "recipientEmail": recipient,
            "senderEmail": actor_email_from(data),
            "status": "pending",
            "createdAt": datetime.utcnow().isoformat() + "Z",
        }
        store.setdefault("gifts", []).append(gift)
        return {"type": "ok", "gift": gift, "course": course}

    result = update_store(mutate)
    if result["type"] == "missing-course":
        return error_response("Course not found", 404)
    return json_response({"ok": True, "gift": result["gift"], "course": result["course"]}, status=201)


@csrf_exempt
def coupon_validate(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    course_id = str(data.get("courseId", "")).strip()
    code = str(data.get("code", "")).strip().upper()
    if not course_id:
        return error_response("courseId is required.", 400)
    if not code:
        return error_response("Coupon code is required.", 400)
    store = read_store()
    course = find_course_by_id(store, course_id)
    if not course:
        return error_response("Course not found", 404)
    coupon = next(
        (entry for entry in store.get("coupons", []) if entry["code"] == code and entry.get("active")),
        None,
    )
    if not coupon:
        return json_response({"ok": True, "valid": False, "code": code, "message": "Coupon not found or inactive."})
    discount_value = (
        round(course["priceValue"] * (coupon["value"] / 100))
        if coupon["type"] == "percent"
        else min(course["priceValue"], coupon["value"])
    )
    final_price = max(0, course["priceValue"] - discount_value)
    return json_response(
        {
            "ok": True,
            "valid": True,
            "code": code,
            "coupon": coupon,
            "courseId": course_id,
            "discountValue": discount_value,
            "finalPrice": final_price,
            "finalPriceLabel": f"{format_number(final_price)} ETB",
        }
    )


@csrf_exempt
def notes(request):
    if response := guard_method(request, {"GET", "POST"}):
        return response
    if request.method == "GET":
        course_id = str(request.GET.get("courseId", "")).strip()
        if not course_id:
            return error_response("courseId query parameter is required.", 400)
        store = read_store()
        email = actor_email_from(query=request.GET.dict())
        note = store.get("notes", {}).get(email, {}).get(course_id)
        return json_response({"ok": True, "email": email, "courseId": course_id, "note": note})

    data = parse_request_data(request)
    course_id = str(data.get("courseId", "")).strip()
    if not course_id:
        return error_response("courseId is required.", 400)
    note_text = str(data.get("notes", ""))

    def mutate(store: dict[str, Any]):
        course = find_course_by_id(store, course_id)
        if not course:
            return {"type": "missing-course"}
        email = actor_email_from(data)
        store.setdefault("notes", {})
        store["notes"].setdefault(email, {})
        record = {"notes": note_text, "updatedAt": datetime.utcnow().isoformat() + "Z"}
        store["notes"][email][course_id] = record
        return {"type": "ok", "email": email, "courseId": course_id, "note": record, "course": course}

    result = update_store(mutate)
    if result["type"] == "missing-course":
        return error_response("Course not found", 404)
    return json_response(
        {
            "ok": True,
            "email": result["email"],
            "courseId": result["courseId"],
            "note": result["note"],
            "course": result["course"],
        }
    )


@csrf_exempt
def notifications(request):
    if response := guard_method(request, {"GET"}):
        return response
    store = read_store()
    email = actor_email_from(query=request.GET.dict())
    items = [
        item
        for item in store.get("notifications", [])
        if item.get("audience") in {"all", email}
    ]
    return json_response({"ok": True, "email": email, "count": len(items), "notifications": items})


@csrf_exempt
def instructor_drafts(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    instructor = str(data.get("instructor", "Yonas Tesfaye")).strip()

    def mutate(store: dict[str, Any]):
        draft = {
            "id": build_id("draft"),
            "instructor": instructor,
            "status": "open",
            "createdAt": datetime.utcnow().isoformat() + "Z",
        }
        store.setdefault("draftRequests", []).append(draft)
        return draft

    draft = update_store(mutate)
    return json_response({"ok": True, "draft": draft}, status=201)


@csrf_exempt
def instructor_courses(request):
    if response := guard_method(request, {"GET", "POST"}):
        return response
    if request.method == "GET":
        store = read_store()
        instructor = str(request.GET.get("instructor", "")).strip().lower()
        courses = get_catalog_courses(store)
        if instructor:
            courses = [course for course in courses if course["instructor"].lower() == instructor]
        return json_response({"ok": True, "count": len(courses), "courses": courses})

    data = parse_request_data(request)
    input_course = data.get("course") if isinstance(data.get("course"), dict) else data
    title = str(input_course.get("title", "")).strip()
    overview = str(input_course.get("overview", "")).strip()
    instructor = str(input_course.get("instructor", "Yonas Tesfaye")).strip()
    if not title or not overview or not instructor:
        return error_response("title, overview, and instructor are required.", 400)

    def mutate(store: dict[str, Any]):
        custom_courses = store.setdefault("courses", {}).setdefault("custom", [])
        existing_index = next(
            (index for index, course in enumerate(custom_courses) if course["id"] == input_course.get("id")),
            -1,
        )
        existing_custom = custom_courses[existing_index] if existing_index >= 0 else None
        next_id = resolve_unique_course_id(store, str(input_course.get("id", "")).strip(), title, existing_custom["id"] if existing_custom else None)
        normalized = normalize_course_input({**input_course, "id": next_id}, existing_custom)
        if existing_index >= 0:
            custom_courses[existing_index] = normalized
        else:
            custom_courses.append(normalized)
        return {"course": find_course_by_id(store, normalized["id"]), "created": existing_index < 0}

    result = update_store(mutate)
    return json_response({"ok": True, "created": result["created"], "course": result["course"]}, status=201 if result["created"] else 200)


@csrf_exempt
def instructor_thumbnail(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    course_id = str(data.get("courseId", "")).strip()
    thumbnail = str(data.get("thumbnail", "")).strip()
    if not course_id:
        return error_response("courseId is required.", 400)

    def mutate(store: dict[str, Any]):
        courses_bucket = store.setdefault("courses", {})
        custom_courses = courses_bucket.setdefault("custom", [])
        base_courses = courses_bucket.setdefault("base", [])
        thumbnail_overrides = courses_bucket.setdefault("thumbnailOverrides", {})
        custom_index = next((index for index, course in enumerate(custom_courses) if course["id"] == course_id), -1)
        base_index = next((index for index, course in enumerate(base_courses) if course["id"] == course_id), -1)
        if custom_index < 0 and base_index < 0:
            return {"type": "missing-course"}
        if custom_index >= 0:
            custom_courses[custom_index]["thumbnail"] = thumbnail
        elif thumbnail:
            thumbnail_overrides[course_id] = thumbnail
        else:
            thumbnail_overrides.pop(course_id, None)
        return {"type": "ok", "course": find_course_by_id(store, course_id)}

    result = update_store(mutate)
    if result["type"] == "missing-course":
        return error_response("Course not found", 404)
    return json_response({"ok": True, "course": result["course"]})


@csrf_exempt
def dashboard_tab(request):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    tab = str(data.get("tab", "")).strip()
    if not tab:
        return error_response("tab is required.", 400)

    def mutate(store: dict[str, Any]):
        selection = {
            "id": build_id("dashboard"),
            "tab": tab,
            "email": actor_email_from(data),
            "createdAt": datetime.utcnow().isoformat() + "Z",
        }
        store.setdefault("dashboardSelections", []).append(selection)
        return selection

    selection = update_store(mutate)
    return json_response({"ok": True, "selection": selection})


def _certificate_action(request, action: str):
    if response := guard_method(request, {"POST"}):
        return response
    data = parse_request_data(request)
    name = str(data.get("name", "Certificate")).strip()

    def mutate(store: dict[str, Any]):
        record = {
            "id": build_id("certificate"),
            "action": action,
            "name": name,
            "email": actor_email_from(data),
            "createdAt": datetime.utcnow().isoformat() + "Z",
        }
        store.setdefault("certificateActions", []).append(record)
        return record

    record = update_store(mutate)
    return json_response({"ok": True, "action": action, "certificate": record})


@csrf_exempt
def certificate_share(request):
    return _certificate_action(request, "share")


@csrf_exempt
def certificate_preview(request):
    return _certificate_action(request, "preview")
