from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "skillforge-local-django-secret-key"
DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver", "0.0.0.0", "[::1]"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
]

MIDDLEWARE = []

ROOT_URLCONF = "backend.urls"
WSGI_APPLICATION = "backend.wsgi.application"
ASGI_APPLICATION = "backend.asgi.application"

TEMPLATES = []

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Addis_Ababa"
USE_I18N = True
USE_TZ = True
APPEND_SLASH = False
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
