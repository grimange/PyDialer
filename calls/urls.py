"""
URL configuration for the calls app.

This module defines API endpoints for call management, including:
- Call tasks
- Call detail records (CDR)
- Dispositions
- Recordings
- Compliance audit logs
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Create a router and register our ViewSets with it
router = DefaultRouter()
router.register(r'tasks', views.CallTaskViewSet, basename='calltask')
router.register(r'cdr', views.CallDetailRecordViewSet, basename='calldetailrecord')
router.register(r'recordings', views.RecordingViewSet, basename='recording')
router.register(r'dispositions', views.DispositionViewSet, basename='disposition')

# The API URLs are now determined automatically by the router
urlpatterns = [
    path('', include(router.urls)),
]

# URL patterns will generate the following endpoints:
# /api/v1/calls/tasks/ - CallTask CRUD operations
# /api/v1/calls/cdr/ - CallDetailRecord read operations  
# /api/v1/calls/recordings/ - Recording read operations
# /api/v1/calls/dispositions/ - Disposition CRUD operations
# /api/v1/calls/dispositions/statistics/ - Disposition statistics
# /api/v1/calls/dispositions/callbacks_due/ - Callbacks due today
# /api/v1/calls/dispositions/pending_review/ - Dispositions pending supervisor review
# /api/v1/calls/dispositions/{id}/supervisor_review/ - Mark disposition as reviewed
