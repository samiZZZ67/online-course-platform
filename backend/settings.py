from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "skillforge-local-django-secret-key"
DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver", "0.0.0.0", "[::1]"]

INSTALLED_APPS = [
    "accounts.apps.AccountsConfig",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "academy.apps.AcademyConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "academy.middleware.SecurityHeadersMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "academy.middleware.JwtAuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "backend.urls"
WSGI_APPLICATION = "backend.wsgi.application"
ASGI_APPLICATION = "backend.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Addis_Ababa"
USE_I18N = True
USE_TZ = True
APPEND_SLASH = False
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "static/"
AUTH_USER_MODEL = "accounts.User"
DEFAULT_FROM_EMAIL = "noreply@skillforge.local"
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "SAMEORIGIN"
AUTH_RATE_LIMITS = {
    "signup.ip": (8, 15 * 60),
    "signup.email": (4, 15 * 60),
    "login.ip": (12, 15 * 60),
    "login.email": (8, 15 * 60),
    "verify.request.ip": (6, 60 * 60),
    "verify.request.email": (3, 60 * 60),
    "2fa.challenge.ip": (10, 15 * 60),
    "2fa.verify.challenge": (8, 15 * 60),
    "password_reset.ip": (6, 60 * 60),
    "password_reset.email": (3, 60 * 60),
}
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
SPECTACULAR_SETTINGS = {
    "TITLE": "SkillForge Authentication API",
    "DESCRIPTION": "OpenAPI documentation for the SkillForge authentication, profile, and admin identity APIs.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}
