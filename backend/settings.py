import os
import sys
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlparse


BASE_DIR = Path(__file__).resolve().parent.parent


def load_local_env():
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


load_local_env()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: list[str] | None = None) -> list[str]:
    value = os.environ.get(name, "")
    if not value:
        return list(default or [])
    return [item.strip() for item in value.split(",") if item.strip()]


def database_from_url(database_url: str) -> dict:
    parsed = urlparse(database_url)
    if parsed.scheme in {"postgres", "postgresql"}:
        database = {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": unquote(parsed.path.lstrip("/")),
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "",
            "PORT": str(parsed.port or ""),
        }
        options = dict(parse_qsl(parsed.query))
        if options:
            database["OPTIONS"] = options
        return database
    if parsed.scheme == "sqlite":
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": unquote(parsed.path.lstrip("/") or str(BASE_DIR / "db.sqlite3")),
        }
    raise ValueError("Unsupported DATABASE_URL scheme. Use postgres://, postgresql://, or sqlite://.")


RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
IS_RENDER = env_bool("RENDER", False)
IS_TESTING = "test" in sys.argv
SECRET_KEY = os.environ.get("SECRET_KEY", "skillforge-local-django-secret-key")
DEBUG = env_bool("DEBUG", not IS_RENDER)
if IS_TESTING:
    DEBUG = True
ALLOWED_HOSTS = env_list(
    "ALLOWED_HOSTS",
    ["127.0.0.1", "localhost", "testserver", "0.0.0.0", "[::1]"],
)
if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

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

if not DEBUG or env_bool("ENABLE_WHITENOISE", False):
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

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

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DATABASES = {
    "default": database_from_url(DATABASE_URL)
    if DATABASE_URL
    else {
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
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT") or os.environ.get("RENDER_DISK_PATH") or BASE_DIR / "media")
AUTH_USER_MODEL = "accounts.User"
DEFAULT_FROM_EMAIL = "noreply@skillforge.local"
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
if RENDER_EXTERNAL_HOSTNAME:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")
if IS_RENDER and "https://*.onrender.com" not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append("https://*.onrender.com")
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_SSL_REDIRECT = False if IS_TESTING else env_bool("SECURE_SSL_REDIRECT", not DEBUG)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "31536000" if not DEBUG else "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", not DEBUG)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)
X_FRAME_OPTIONS = "SAMEORIGIN"
if not DEBUG:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
SEED_DEMO_USER = env_bool("SEED_DEMO_USER", DEBUG)
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

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_API_BASE_URL = os.environ.get("GROQ_API_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_TIMEOUT_SECONDS = int(os.environ.get("GROQ_TIMEOUT_SECONDS", "20"))
GROQ_MAX_COMPLETION_TOKENS = int(os.environ.get("GROQ_MAX_COMPLETION_TOKENS", "500"))
GROQ_TEMPERATURE = float(os.environ.get("GROQ_TEMPERATURE", "0.35"))
GROQ_USE_LOCAL_FALLBACK = os.environ.get("GROQ_USE_LOCAL_FALLBACK", "true").lower() in {"1", "true", "yes", "on"}
