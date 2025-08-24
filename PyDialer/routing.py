"""
WebSocket routing configuration for PyDialer project.

This file defines URL patterns for WebSocket connections used in the call center system.
These routes handle real-time communication for agent interfaces, supervisor dashboards,
and call management features.
"""

from django.urls import re_path, path
from channels.routing import URLRouter

# Import WebSocket consumers
from agents.consumers import AgentConsumer, SupervisorConsumer
from calls.consumers import CallConsumer
from campaigns.consumers import CampaignConsumer

# WebSocket URL patterns for the call center system
websocket_urlpatterns = [
    # Agent interface WebSocket connections
    re_path(r'ws/agent/(?P<agent_id>\w+)/$', AgentConsumer.as_asgi()),
    
    # Campaign management WebSocket connections
    re_path(r'ws/campaign/(?P<campaign_id>\w+)/$', CampaignConsumer.as_asgi()),
    
    # Supervisor dashboard WebSocket connections
    re_path(r'ws/supervisor/(?P<supervisor_id>\w+)/$', SupervisorConsumer.as_asgi()),
    
    # Real-time notifications for all authenticated users
    # path('ws/notifications/', NotificationConsumer.as_asgi()),
    
    # System-wide alerts and announcements
    # path('ws/system/', SystemConsumer.as_asgi()),
    
    # Call events and status updates
    re_path(r'ws/calls/(?P<call_id>\w+)/$', CallConsumer.as_asgi()),
    
    # For now, empty list - consumers will be added as they are implemented
]

# Additional routing configurations can be added here as needed
# For example, different routing for different user types or features
