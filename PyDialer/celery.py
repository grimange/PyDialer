"""
Celery configuration for PyDialer project.

This module sets up Celery for background task processing in the PyDialer
call center system. It handles predictive dialing, lead processing, CDR 
management, and other asynchronous tasks.
"""

import os
from celery import Celery
from django.conf import settings

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PyDialer.settings.development')

# Create the Celery application
app = Celery('PyDialer')

# Configure Celery using Django settings
# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from all installed Django apps
app.autodiscover_tasks()

# Optional: Custom task for debugging
@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task to test Celery configuration."""
    print(f'Request: {self.request!r}')


# Celery signals for monitoring and logging
from celery.signals import task_prerun, task_postrun, task_failure
import logging

logger = logging.getLogger('celery')


@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **kwds):
    """Log when a task starts executing."""
    logger.info(f'Task {task.name} (ID: {task_id}) started with args: {args}, kwargs: {kwargs}')


@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **kwds):
    """Log when a task completes successfully."""
    logger.info(f'Task {task.name} (ID: {task_id}) completed successfully with state: {state}')


@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, traceback=None, einfo=None, **kwds):
    """Log when a task fails."""
    logger.error(f'Task {sender.name} (ID: {task_id}) failed with exception: {exception}')
    logger.error(f'Traceback: {traceback}')


# Custom task base class for call center operations
from celery import Task
from django.db import transaction


class CallCenterTask(Task):
    """
    Base task class for call center operations.
    
    Provides common functionality like database transaction handling,
    error logging, and retry logic specific to call center operations.
    """
    
    abstract = True
    autoretry_for = (Exception,)
    retry_kwargs = {'max_retries': 3, 'countdown': 60}
    retry_backoff = True
    retry_jitter = True
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure with call center specific logging."""
        logger.error(f'Call center task {self.name} failed: {exc}', extra={
            'task_id': task_id,
            'task_args': args,
            'task_kwargs': kwargs,
            'exception': str(exc)
        })
        
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Handle task retry with call center specific logging."""
        logger.warning(f'Call center task {self.name} retrying: {exc}', extra={
            'task_id': task_id,
            'task_args': args,
            'task_kwargs': kwargs,
            'retry_count': self.request.retries
        })
        
    def on_success(self, retval, task_id, args, kwargs):
        """Handle successful task completion."""
        logger.info(f'Call center task {self.name} completed successfully', extra={
            'task_id': task_id,
            'task_args': args,
            'task_kwargs': kwargs,
            'return_value': str(retval) if retval else None
        })


# Register the custom task base class
app.Task = CallCenterTask

# Health check task for monitoring
@app.task(bind=True, ignore_result=False)
def health_check(self):
    """Health check task for monitoring system status."""
    from django.db import connection
    from django.core.cache import cache
    import redis
    
    try:
        # Check database connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            
        # Check cache connection
        cache.set('health_check', 'ok', timeout=60)
        cache_status = cache.get('health_check')
        
        # Check Redis connection for Celery
        redis_client = redis.from_url(settings.CELERY_BROKER_URL)
        redis_client.ping()
        
        return {
            'status': 'healthy',
            'database': 'ok',
            'cache': 'ok' if cache_status == 'ok' else 'failed',
            'redis': 'ok',
            'timestamp': self.request.id
        }
        
    except Exception as e:
        logger.error(f'Health check failed: {e}')
        return {
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': self.request.id
        }
