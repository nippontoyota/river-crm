import os
import json
from datetime import timedelta
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "development-only-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = [host for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if host]

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions",
    "django.contrib.messages", "django.contrib.staticfiles", "corsheaders", "rest_framework",
    "drf_spectacular", "rest_framework_simplejwt.token_blacklist", "accounts", "leads", "analytics", "uploads", "notifications", "complaints", "ceo", "intake", "feedback", "servicing",
]
MIDDLEWARE = [
    "config.middleware.PerformanceMiddleware", "django.middleware.security.SecurityMiddleware", "whitenoise.middleware.WhiteNoiseMiddleware", "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware", "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [], "APP_DIRS": True, "OPTIONS": {"context_processors": ["django.template.context_processors.request", "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages"]}}]

DATABASES = {"default": dj_database_url.config(default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}", conn_max_age=int(os.environ.get("DB_CONN_MAX_AGE", "0")))}
AUTH_USER_MODEL = "accounts.User"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.BCryptSHA256PasswordHasher"]
TIME_ZONE = "Asia/Kolkata"
USE_TZ = True

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["accounts.authentication.CookieJWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated", "accounts.permissions.ReadOnlyCEO"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle", "rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": "30/minute", "user": "120/minute"},
}
SIMPLE_JWT = {"ACCESS_TOKEN_LIFETIME": timedelta(minutes=15), "REFRESH_TOKEN_LIFETIME": timedelta(days=7), "ROTATE_REFRESH_TOKENS": True, "BLACKLIST_AFTER_ROTATION": True, "SIGNING_KEY": os.environ.get("JWT_SIGNING_KEY", SECRET_KEY)}
SPECTACULAR_SETTINGS = {"TITLE": "Incheon Mobility CRM API", "VERSION": "1.0.0", "SERVE_INCLUDE_SCHEMA": False}

CORS_ALLOWED_ORIGINS = [value for value in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",") if value] + ["https://frontend-alysajads-projects.vercel.app"]
CORS_ALLOWED_ORIGIN_REGEXES = [
    r"^https://.*\.vercel\.app$",
]
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = [value for value in os.environ.get("CSRF_TRUSTED_ORIGINS", "http://localhost:3000").split(",") if value] + ["https://frontend-alysajads-projects.vercel.app", "https://*.vercel.app"]
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax" if DEBUG else "None"
SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "false").lower() == "true"
SECURE_HSTS_SECONDS = 31_536_000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CACHE_URL = os.environ.get("CACHE_URL", "")
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "0"))
CACHES = {
    # DRF throttling stays local so an analytics Redis outage can fail open in the view.
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "default-cache",
    },
    "analytics": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": CACHE_URL,
        "OPTIONS": {"socket_connect_timeout": 1, "socket_timeout": 1},
    } if CACHE_URL else {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "analytics-cache",
    }
}

CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_TASK_ALWAYS_EAGER = os.environ.get("CELERY_TASK_ALWAYS_EAGER", str(DEBUG)).lower() == "true"
CELERY_TASK_EAGER_PROPAGATES = CELERY_TASK_ALWAYS_EAGER
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_TIME_LIMIT = 300
CELERY_BEAT_SCHEDULE = {"follow-up-reminders": {"task": "notifications.tasks.create_due_follow_up_notifications", "schedule": 900}}
CELERY_BEAT_SCHEDULE["feedback-reminders"] = {"task": "feedback.tasks.process_feedback_queue", "schedule": 60}

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY", os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""))
SUPABASE_BUCKET = os.environ.get("SUPABASE_UPLOAD_BUCKET", "crm-imports")

# Only credential-free preview or disabled mode is supported until a provider is selected.
WHATSAPP_MODE = os.environ.get("WHATSAPP_MODE", "preview").strip().lower()
WHATSAPP_BUSINESS_NAME = os.environ.get("WHATSAPP_BUSINESS_NAME", "Incheon Mobility")
WHATSAPP_LANGUAGE = os.environ.get("WHATSAPP_LANGUAGE", "en")
WHATSAPP_TEMPLATE_INTRODUCTION = os.environ.get("WHATSAPP_TEMPLATE_INTRODUCTION", "so_introduction")
WHATSAPP_TEMPLATE_REASSIGNMENT = os.environ.get("WHATSAPP_TEMPLATE_REASSIGNMENT", "so_reassignment")

# References are persisted; credentials are supplied only through backend secrets.
INTAKE_ENABLED = os.environ.get("INTAKE_ENABLED", "false").lower() == "true"
INTAKE_SECRETS = json.loads(os.environ.get("INTAKE_SECRETS_JSON", "{}"))
INTAKE_FINGERPRINT_KEY = os.environ.get("INTAKE_FINGERPRINT_KEY", SECRET_KEY)
INTAKE_MAX_BYTES = 64 * 1024
INTAKE_MAX_FIELDS = 100
INTAKE_RATE_PER_MINUTE = 120
META_APP_SECRET = os.environ.get("META_APP_SECRET", "")
META_VERIFY_TOKEN = os.environ.get("META_VERIFY_TOKEN", "")
# No moving/latest default: verify the supported version during account setup.
META_GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "")
CELERY_BEAT_SCHEDULER = "intake.scheduler:HeartbeatScheduler"
CELERY_BROKER_CONNECTION_TIMEOUT = 2
CELERY_TASK_PUBLISH_RETRY = False
CELERY_BEAT_SCHEDULE.update({
    "intake-recovery": {"task": "intake.tasks.sweep_receipts", "schedule": 60},
    "intake-reconciliation": {"task": "intake.tasks.reconcile_forms", "schedule": 900},
    "intake-retention": {"task": "intake.tasks.purge_expired_answers", "schedule": 3600},
})
