"""Django settings for the FoodBridge platform (weeks 1-2 backend)."""
import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BASE_DIR.parent


def env(key, default=None):
    v = os.environ.get(key)
    return default if v is None or v.strip() == "" else v   # blank dashboard values count as "not set"


def env_bool(key, default=False):
    return str(env(key, default)).lower() in {"1", "true", "yes", "on"}


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-insecure-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS", "*").split(",")
CSRF_TRUSTED_ORIGINS = [o for o in env("CSRF_TRUSTED_ORIGINS", "").split(",") if o]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")   # Render / Vercel / most PaaS terminate TLS

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "core",
    "accounts",
    "inventory",
    "predictions",
    "marketplace",
    "analytics",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.TenantMiddleware",
]
try:  # whitenoise is optional in local dev
    import whitenoise  # noqa: F401
except ImportError:
    MIDDLEWARE.remove("whitenoise.middleware.WhiteNoiseMiddleware")

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"

# ---- Database: one shared (multi-tenant) database. PostgreSQL in production. ----
if env("DATABASE_URL"):
    # e.g. postgresql://user:pass@host:5432/db?sslmode=require  (Render, Neon, Supabase, Railway…)
    from urllib.parse import parse_qsl, unquote, urlparse
    _u = urlparse(env("DATABASE_URL"))
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(_u.path.lstrip("/")),
        "USER": unquote(_u.username or ""),
        "PASSWORD": unquote(_u.password or ""),
        "HOST": _u.hostname,
        "PORT": str(_u.port or 5432),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": dict(parse_qsl(_u.query)),
    }}
elif env("POSTGRES_DB"):
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER", "postgres"),
        "PASSWORD": env("POSTGRES_PASSWORD", ""),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3",
                             "NAME": env("SQLITE_PATH", BASE_DIR / "db.sqlite3"),
                             # WAL + IMMEDIATE transactions: readers never block, writers queue instead of
                             # failing with "database is locked" under concurrent requests
                             "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE",
                                         "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;"}}}

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOW_ALL_ORIGINS = env_bool("CORS_ALLOW_ALL", True)
CORS_ALLOW_HEADERS = ["accept", "authorization", "content-type", "origin", "x-pos-key", "x-service-key"]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # stress protection (tunable per deployment; load tests raise them)
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle",
                                 "rest_framework.throttling.UserRateThrottle",
                                 "rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": env("THROTTLE_ANON", "120/min"), "user": env("THROTTLE_USER", "1200/min"),
                               "login": env("THROTTLE_LOGIN", "20/min"), "pos": env("THROTTLE_POS", "600/min")},
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=8),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=14),
    "ROTATE_REFRESH_TOKENS": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "FoodBridge Platform API",
    "DESCRIPTION": (
        "Inventory & expiry tracking, POS integration, waste-risk predictions, surplus "
        "redistribution marketplace and analytics for food businesses and NGOs.\n\n"
        "**Auth:** call `POST /api/auth/login/`, then click *Authorize* and paste the `access` token.\n"
        "POS endpoints use the `X-POS-Key` header instead."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SWAGGER_UI_SETTINGS": {"persistAuthorization": True, "displayRequestDuration": True, "filter": True},
    "ENUM_NAME_OVERRIDES": {
        "ListingStatusEnum": "marketplace.models.SurplusListing.Status",
        "PickupStatusEnum": "marketplace.models.Pickup.Status",
        "BatchStatusEnum": "inventory.models.InventoryBatch.Status",
        "OrgKindEnum": "accounts.models.Organization.BusinessKind",
        "NotificationKindEnum": "core.models.Notification.Kind",
    },
    "TAGS": [
        {"name": "auth", "description": "Registration, login, profile"},
        {"name": "organizations", "description": "Tenants: food businesses and NGOs"},
        {"name": "taxonomy", "description": "Food taxonomy, perishability and storage rules"},
        {"name": "inventory", "description": "Products, batches, CSV upload, barcode scanning"},
        {"name": "expiry", "description": "Expiry thresholds and alerts"},
        {"name": "pos", "description": "Point-of-sale integration (X-POS-Key)"},
        {"name": "predictions", "description": "Waste-risk scores, forecasts, reorder recommendations"},
        {"name": "marketplace", "description": "Surplus listings, NGO needs, AI matching"},
        {"name": "pickups", "description": "Pickup scheduling and confirmations"},
        {"name": "analytics", "description": "Business, NGO and sustainability dashboards"},
        {"name": "notifications", "description": "In-app notifications"},
        {"name": "internal", "description": "Service-to-service endpoints for the ML microservice"},
    ],
}

EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "FoodBridge <no-reply@foodbridge.local>")
EMAIL_HOST = env("EMAIL_HOST", "localhost")
EMAIL_PORT = int(env("EMAIL_PORT", "25"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)

# ---- Cache (dashboards/feeds). REDIS_URL shares it across gunicorn workers & instances. ----
if env("REDIS_URL"):
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": env("REDIS_URL")}}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "foodbridge"}}
DASHBOARD_CACHE_SECONDS = int(env("DASHBOARD_CACHE_SECONDS", "30"))

# ---- FoodBridge-specific settings ----
ML_SERVICE_URL = env("ML_SERVICE_URL", "http://localhost:8001")
ML_SERVICE_TIMEOUT = float(env("ML_SERVICE_TIMEOUT", "20"))
SERVICE_API_KEY = env("SERVICE_API_KEY", "dev-service-key")  # shared secret with the ML service
DATASET_DIR = Path(env("DATASET_DIR", REPO_ROOT / "data" / "freshretailnet"))
IMPACT = {
    "KG_PER_MEAL": 0.42,          # WRAP / UK food-banking convention
    "DEFAULT_CO2E_PER_KG": 2.5,   # kg CO2e avoided per kg of food not wasted
}
EXPIRY_SCAN_INTERVAL_MIN = int(env("EXPIRY_SCAN_INTERVAL_MIN", "60"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,   # keep Django's own loggers so 500s are logged with tracebacks
    "formatters": {"std": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "std"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False}},
}
