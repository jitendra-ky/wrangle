"""
Production settings for zproject.

Key differences from settings_dev.py:
- Database: PostgreSQL (Neon or any pg-compatible host), configured via env vars.
  Falls back to parsing POSTGRESQL_CONNECTION_STRING if individual DB_* vars are absent.
- DEBUG: defaults to False, overridable via DEBUG env var.
- SECRET_KEY: read from env (falls back to insecure default — rotate in real prod).
- ALLOWED_HOSTS: read from ALLOWED_HOSTS env var (comma-separated).
- Redis: same Upstash TLS setup as dev; will be overridden per-container in docker-compose.
"""

import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

# Load .env from the project root.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Security ──────────────────────────────────────────────────────────────────

SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "django-insecure-1+6i9$zii17k28&qlsm0-u5$#sfq6y!kmfeyagf=l#&y2&=hlt",
)

DEBUG = os.environ.get("DEBUG", "0") == "1"

_allowed_hosts_env = os.environ.get("ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts_env.split(",") if h.strip()] or ["*"]

# ── Installed apps ────────────────────────────────────────────────────────────

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_celery_results",
    "zserver",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "zproject.urls"

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
    },
]

WSGI_APPLICATION = "zproject.wsgi.application"

# ── Database — PostgreSQL ─────────────────────────────────────────────────────
# Priority:
#   1. Individual DB_* env vars  (used by Docker Compose with a local pg container)
#   2. POSTGRESQL_CONNECTION_STRING  (Neon / Supabase / any connection-string format)
#   3. Error — prod must not silently fall back to SQLite.

_db_url = os.environ.get("POSTGRESQL_CONNECTION_STRING", "")
_parsed = urlparse(_db_url) if _db_url else None

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        # Individual env vars take precedence (Docker Compose sets these).
        "NAME":     os.environ.get("DB_NAME")     or (_parsed.path.lstrip("/") if _parsed else ""),
        "USER":     os.environ.get("DB_USER")     or (_parsed.username            if _parsed else ""),
        "PASSWORD": os.environ.get("DB_PASSWORD") or (_parsed.password            if _parsed else ""),
        "HOST":     os.environ.get("DB_HOST")     or (_parsed.hostname            if _parsed else ""),
        "PORT":     os.environ.get("DB_PORT")     or (str(_parsed.port or 5432)   if _parsed else "5432"),
        # OPTIONS: pass sslmode when the connection string demands it.
        "OPTIONS": (
            {"sslmode": "require"}
            if ("sslmode=require" in _db_url or "sslmode=prefer" in _db_url)
            and not os.environ.get("DB_HOST")   # skip ssl for local Docker pg
            else {}
        ),
    }
}

# ── Password validation ───────────────────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ── Internationalisation ──────────────────────────────────────────────────────

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ── Static / Media ────────────────────────────────────────────────────────────

STATIC_URL = "static/"

MEDIA_URL  = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Celery ────────────────────────────────────────────────────────────────────
# Supports two modes:
#   • Upstash (default prod):  REDIS_USE_TLS=1 (or unset) → rediss:// with auth
#   • Local Docker Redis:      REDIS_USE_TLS=0            → redis:// no auth/TLS

_redis_host     = os.environ.get("REDIS_HOST", "")
_redis_port     = os.environ.get("REDIS_PORT", "6379")
_redis_password = os.environ.get("REDIS_PASSWORD", "")
_redis_use_tls  = os.environ.get("REDIS_USE_TLS", "1") != "0"

if _redis_use_tls and _redis_password:
    # Upstash / TLS-secured Redis
    _REDIS_URL            = f"rediss://:{_redis_password}@{_redis_host}:{_redis_port}/0"
    CELERY_BROKER_USE_SSL = {"ssl_cert_reqs": None}   # Upstash uses self-signed cert
else:
    # Local container Redis (no password, no TLS)
    _REDIS_URL            = f"redis://{_redis_host}:{_redis_port}/0"
    CELERY_BROKER_USE_SSL = False

CELERY_BROKER_URL         = _REDIS_URL
CELERY_RESULT_BACKEND     = "django-db"   # persisted via django_celery_results
CELERY_CACHE_BACKEND      = "default"     # unused but avoids warnings
CELERY_TASK_SERIALIZER    = "json"
CELERY_RESULT_SERIALIZER  = "json"
CELERY_ACCEPT_CONTENT     = ["json"]
CELERY_TIMEZONE           = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_EAGER_PROPAGATES = True
