"""
Base settings for PyDialer project.

This file contains common settings shared across all environments.
Environment-specific settings should be defined in separate files that import from this base.
"""

import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Django Channels
    'channels',
    # Django REST Framework (for API functionality)
    'rest_framework',
    'rest_framework_simplejwt',
    # PyDialer apps
    'agents',
    'campaigns',
    'calls',
    'leads',
    'reporting',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'PyDialer.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'PyDialer.wsgi.application'
ASGI_APPLICATION = 'PyDialer.asgi.application'

# Channel layer configuration (will be overridden in staging/production with Redis)
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files (uploaded content)
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom User Model
AUTH_USER_MODEL = 'agents.User'

# Django REST Framework Configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,
    'DEFAULT_FILTER_BACKENDS': [
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour'
    },
    'EXCEPTION_HANDLER': 'PyDialer.exceptions.custom_exception_handler',
    'TEST_REQUEST_DEFAULT_FORMAT': 'json',
    'DATETIME_FORMAT': '%Y-%m-%d %H:%M:%S',
    'DATE_FORMAT': '%Y-%m-%d',
    'TIME_FORMAT': '%H:%M:%S',
    # API Versioning Configuration
    'DEFAULT_VERSIONING_CLASS': 'rest_framework.versioning.URLPathVersioning',
    'DEFAULT_VERSION': 'v1',
    'ALLOWED_VERSIONS': ['v1', 'v2'],
    'VERSION_PARAM': 'version',
}

# Simple JWT Configuration
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': 'django-insecure-temp-key',  # Will be overridden in production
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': 'PyDialer',
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'JTI_CLAIM': 'jti',
    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=60),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=7),
}

# Security settings (will be overridden in production)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'

# Celery Configuration
# Base Celery settings - will be overridden in staging/production with Redis
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/1')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/2')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # 25 minutes
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_DISABLE_RATE_LIMITS = False

# Celery Beat Schedule (for scheduled tasks)
CELERY_BEAT_SCHEDULE = {
    # Example scheduled task - can be expanded later
    'cleanup-old-cdrs': {
        'task': 'calls.tasks.cleanup_old_cdrs',
        'schedule': 3600.0,  # Run every hour
    },
}

# Celery Queue Configuration
CELERY_TASK_ROUTES = {
    'campaigns.tasks.predictive_dial': {'queue': 'dialing'},
    'calls.tasks.*': {'queue': 'calls'},
    'leads.tasks.*': {'queue': 'leads'},
    'reporting.tasks.*': {'queue': 'reporting'},
}

CELERY_TASK_DEFAULT_QUEUE = 'default'
CELERY_TASK_QUEUES = {
    'default': {
        'exchange': 'default',
        'routing_key': 'default',
    },
    'dialing': {
        'exchange': 'dialing',
        'routing_key': 'dialing',
    },
    'calls': {
        'exchange': 'calls',
        'routing_key': 'calls',
    },
    'leads': {
        'exchange': 'leads',
        'routing_key': 'leads',
    },
    'reporting': {
        'exchange': 'reporting',
        'routing_key': 'reporting',
    },
}

# Celery Flower Configuration (Monitoring)
CELERY_FLOWER_USER = os.environ.get('CELERY_FLOWER_USER', 'admin')
CELERY_FLOWER_PASSWORD = os.environ.get('CELERY_FLOWER_PASSWORD', 'admin')
CELERY_FLOWER_URL_PREFIX = os.environ.get('CELERY_FLOWER_URL_PREFIX', '/flower')
CELERY_FLOWER_BASIC_AUTH = f"{CELERY_FLOWER_USER}:{CELERY_FLOWER_PASSWORD}"

# Additional Flower settings
FLOWER_BASIC_AUTH = [CELERY_FLOWER_BASIC_AUTH]
FLOWER_UNAUTHENTICATED_API = False
FLOWER_AUTO_REFRESH = True
FLOWER_PERSISTENT = True
FLOWER_DB = os.environ.get('FLOWER_DB', BASE_DIR / 'flower.db')
FLOWER_MAX_TASKS = int(os.environ.get('FLOWER_MAX_TASKS', '10000'))

# Call Center specific settings
CALL_CENTER_SETTINGS = {
    'DEFAULT_TIMEZONE': 'America/New_York',
    'MAX_CALL_DURATION': 3600,  # 1 hour in seconds
    'DEFAULT_WRAP_UP_TIME': 30,  # 30 seconds
    'MAX_CONCURRENT_CALLS_PER_AGENT': 1,
}
