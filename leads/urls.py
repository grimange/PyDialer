"""
URL configuration for the leads app.

This module defines URL patterns using DRF routers for ViewSet-based endpoints
including lead management, bulk import functionality, and disposition management.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'leads'

# Create router and register viewsets
router = DefaultRouter()
router.register(r'leads', views.LeadViewSet)
router.register(r'dispositions', views.DispositionViewSet)
router.register(r'disposition-codes', views.DispositionCodeViewSet)
router.register(r'notes', views.LeadNoteViewSet)
router.register(r'import-batches', views.LeadImportBatchViewSet)

urlpatterns = [
    # Include router URLs
    path('', include(router.urls)),
]
