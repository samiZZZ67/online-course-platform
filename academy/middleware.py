from __future__ import annotations

from .services import AuthTokenError, authenticate_access_token, extract_access_token


class JwtAuthenticationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.api_user = None
        request.api_auth_payload = None
        request.api_auth_error = None
        if request.path.startswith("/api/"):
            raw_token = extract_access_token(request)
            if raw_token:
                try:
                    user, payload = authenticate_access_token(raw_token)
                except AuthTokenError as exc:
                    request.api_auth_error = exc
                else:
                    request.api_user = user
                    request.api_auth_payload = payload
                    if not getattr(request, "user", None) or not request.user.is_authenticated:
                        request.user = user
        return self.get_response(request)


class SecurityHeadersMiddleware:
    CONTENT_SECURITY_POLICY = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: https:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'self'"
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", self.CONTENT_SECURITY_POLICY)
        response.setdefault("Referrer-Policy", "same-origin")
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.setdefault("X-Content-Type-Options", "nosniff")
        if request.is_secure():
            response.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.path.startswith("/api/auth/") or request.path in {
            "/api/login",
            "/api/register",
            "/api/refresh-token",
            "/api/forgot-password",
            "/api/reset-password",
            "/api/verify-email",
            "/api/change-password",
            "/api/logout",
            "/api/profile",
            "/api/profile/update",
        }:
            response.setdefault("Cache-Control", "no-store")
            response.setdefault("Pragma", "no-cache")
        return response
