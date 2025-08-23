"""
URL configuration for the campaigns app.

This module defines URL patterns using DRF routers for ViewSet-based endpoints.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'campaigns'

# Create router and register viewsets
router = DefaultRouter()
router.register(r'campaigns', views.CampaignViewSet)
router.register(r'assignments', views.CampaignAgentAssignmentViewSet)
router.register(r'schedules', views.CampaignScheduleViewSet)
router.register(r'statistics', views.CampaignStatisticsViewSet)

urlpatterns = [
    # Include router URLs
    path('', include(router.urls)),
]
