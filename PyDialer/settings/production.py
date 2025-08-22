"""
Production settings for PyDialer project.

This file contains settings specific to the production environment.
All sensitive information should be provided via environment variables.
"""

import os
import logging.config
from .base import *

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ['DJANGO_SECRET_KEY']

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', '').split(',')

# Database
# Using PostgreSQL for production with connection pooling
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'vicidial_prod'),
        'USER': os.environ.get('DB_USER', 'vicidial_user'),
        'PASSWORD': os.environ['DB_PASSWORD'],
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        'OPTIONS': {
            'sslmode': 'require',
            'connect_timeout': 60,
        },
        'CONN_MAX_AGE': 600,  # Connection pooling
    }
}

# Read replica configuration (if needed)
if os.environ.get('DB_READ_HOST'):
    DATABASES['read_replica'] = {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_READ_NAME', DATABASES['default']['NAME']),
        'USER': os.environ.get('DB_READ_USER', DATABASES['default']['USER']),
        'PASSWORD': os.environ.get('DB_READ_PASSWORD', DATABASES['default']['PASSWORD']),
        'HOST': os.environ['DB_READ_HOST'],
        'PORT': os.environ.get('DB_READ_PORT', '5432'),
        'OPTIONS': {
            'sslmode': 'require',
            'connect_timeout': 60,
        },
        'CONN_MAX_AGE': 600,
    }

# Redis configuration for Channels and Celery
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.environ.get('REDIS_PORT', '6379'))
REDIS_PASSWORD = os.environ.get('REDIS_PASSWORD', '')
REDIS_DB = int(os.environ.get('REDIS_DB', '0'))

REDIS_URL = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}" if REDIS_PASSWORD else f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

# Cache configuration using Redis
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_URL,
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'CONNECTION_POOL_KWARGS': {
                'max_connections': 100,
                'retry_on_timeout': True,
            },
            'COMPRESSOR': 'django_redis.compressors.zlib.ZlibCompressor',
        },
        'TIMEOUT': 300,
        'KEY_PREFIX': 'vicidial_prod',
    }
}

# Channel layer configuration using Redis for WebSocket communication
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [REDIS_URL],
            'capacity': 5000,  # Higher capacity for production
            'expiry': 300,     # 5 minutes expiry for production
            'group_expiry': 86400,  # 24 hours for group expiry
            'symmetric_encryption_keys': [os.environ.get('CHANNELS_ENCRYPTION_KEY', '')],
            'prefix': 'vicidial_channels',
        },
    },
}

# Email configuration for production
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() == 'true'
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@yourdomain.com')
SERVER_EMAIL = os.environ.get('SERVER_EMAIL', DEFAULT_FROM_EMAIL)

# Logging configuration for production
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            'format': '{"level": "{levelname}", "time": "{asctime}", "module": "{module}", "process": "{process}", "thread": "{thread}", "message": "{message}"}',
            'style': '{',
        },
        'syslog': {
            'format': 'vicidial[{process}]: {levelname} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/vicidial/production.log',
            'maxBytes': 1024*1024*100,  # 100MB
            'backupCount': 10,
            'formatter': 'json',
        },
        'error_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/vicidial/production_errors.log',
            'maxBytes': 1024*1024*100,  # 100MB
            'backupCount': 10,
            'formatter': 'json',
            'level': 'ERROR',
        },
        'syslog': {
            'class': 'logging.handlers.SysLogHandler',
            'address': '/dev/log',
            'formatter': 'syslog',
            'facility': logging.handlers.SysLogHandler.LOG_LOCAL0,
        },
        'mail_admins': {
            'class': 'django.utils.log.AdminEmailHandler',
            'level': 'ERROR',
            'include_html': False,
        },
    },
    'root': {
        'handlers': ['file', 'syslog'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'error_file', 'mail_admins'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['file', 'error_file', 'mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['file'],
            'level': 'ERROR',
            'propagate': False,
        },
        'vicidial': {
            'handlers': ['file', 'error_file', 'syslog'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery': {
            'handlers': ['file', 'syslog'],
            'level': 'INFO',
            'propagate': False,
        },
        'channels': {
            'handlers': ['file', 'syslog'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Security settings for production
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Strict'
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Strict'
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# Additional security headers
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'

# Session configuration for production
SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
SESSION_CACHE_ALIAS = 'default'
SESSION_COOKIE_AGE = 28800  # 8 hours
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# Production-specific call center settings
CALL_CENTER_SETTINGS.update({
    'ENABLE_CALL_RECORDING': True,
    'PREDICTIVE_DIALING_ENABLED': True,
    'DEBUG_TELEPHONY': False,
    'RECORDING_STORAGE_PATH': os.environ.get('RECORDING_STORAGE_PATH', '/var/recordings'),
    'MAX_RECORDING_SIZE_MB': int(os.environ.get('MAX_RECORDING_SIZE_MB', '500')),
    'RECORDING_RETENTION_DAYS': int(os.environ.get('RECORDING_RETENTION_DAYS', '90')),
})

# Static and media files for production
STATIC_ROOT = os.environ.get('STATIC_ROOT', '/var/www/staticfiles')
MEDIA_ROOT = os.environ.get('MEDIA_ROOT', '/var/www/media')

# AWS S3 configuration (if using S3 for static/media files)
if os.environ.get('USE_S3', 'False').lower() == 'true':
    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME', 'us-east-1')
    AWS_S3_CUSTOM_DOMAIN = os.environ.get('AWS_S3_CUSTOM_DOMAIN')
    AWS_DEFAULT_ACL = 'private'
    AWS_S3_OBJECT_PARAMETERS = {
        'CacheControl': 'max-age=86400',
    }
    
    # Static files
    STATICFILES_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    STATIC_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/static/' if AWS_S3_CUSTOM_DOMAIN else f'https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/static/'
    
    # Media files
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/media/' if AWS_S3_CUSTOM_DOMAIN else f'https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/media/'

# Performance optimizations
CONN_MAX_AGE = 600
DATA_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB

# Error reporting
ADMINS = [
    (name.strip(), email.strip()) 
    for admin in os.environ.get('DJANGO_ADMINS', '').split(',') 
    if admin.strip()
    for name, email in [admin.split(':')]
]

MANAGERS = ADMINS

# Monitoring and health checks
ALLOWED_HEALTH_CHECK_IPS = os.environ.get('ALLOWED_HEALTH_CHECK_IPS', '').split(',')

# Rate limiting (if using django-ratelimit)
RATELIMIT_USE_CACHE = 'default'
