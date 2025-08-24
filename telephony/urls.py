"""
URL configuration for telephony app.

This module defines URL patterns for telephony-related endpoints including:
- AI events webhook endpoint
- Health check endpoints
- Future telephony integration endpoints
"""
from django.urls import path
from . import views

app_name = 'telephony'

urlpatterns = [
    # AI Events Webhook endpoint
    path('ai/events/', views.AIEventsWebhookView.as_view(), name='ai_events_webhook'),
    
    # AI Webhook health check
    path('ai/health/', views.ai_webhook_health, name='ai_webhook_health'),
    
    # ARI Controller Service Management endpoints
    path('ari/start/', views.ari_controller_start, name='ari_controller_start'),
    path('ari/stop/', views.ari_controller_stop, name='ari_controller_stop'),
    path('ari/status/', views.ari_controller_status, name='ari_controller_status'),
    path('ari/test/', views.ari_controller_test, name='ari_controller_test'),
    
    # AMI Controller Service Management endpoints
    path('ami/start/', views.ami_controller_start, name='ami_controller_start'),
    path('ami/stop/', views.ami_controller_stop, name='ami_controller_stop'),
    path('ami/status/', views.ami_controller_status, name='ami_controller_status'),
    path('ami/test/', views.ami_controller_test, name='ami_controller_test'),
]
