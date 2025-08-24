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
]
