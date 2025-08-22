"""
Settings package for PyDialer project.

This package contains environment-specific settings configurations.
The appropriate settings module is loaded based on the DJANGO_SETTINGS_MODULE
environment variable or defaults to development.
"""

import os
import warnings

# Default to development environment
ENVIRONMENT = os.environ.get('DJANGO_ENVIRONMENT', 'development').lower()

# Validate environment setting
VALID_ENVIRONMENTS = ['development', 'staging', 'production']
if ENVIRONMENT not in VALID_ENVIRONMENTS:
    warnings.warn(
        f"Invalid DJANGO_ENVIRONMENT '{ENVIRONMENT}'. "
        f"Valid options are: {', '.join(VALID_ENVIRONMENTS)}. "
        f"Defaulting to 'development'."
    )
    ENVIRONMENT = 'development'

# Import the appropriate settings module
if ENVIRONMENT == 'production':
    from .production import *
elif ENVIRONMENT == 'staging':
    from .staging import *
else:
    from .development import *

# Make environment available to other modules
CURRENT_ENVIRONMENT = ENVIRONMENT
