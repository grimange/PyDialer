"""
PyDialer - Django Channels-based Predictive Dialer System

This package initializes the PyDialer call center application with Celery
integration for background task processing.
"""

# Import Celery app to ensure it's loaded when Django starts
from .celery import app as celery_app

__all__ = ('celery_app',)
