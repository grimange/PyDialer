"""
URL configuration for the reporting app.

This module defines API endpoints for real-time statistics and reporting:
- Agent performance metrics
- Campaign statistics
- Call analytics
- Disposition reports
- Dashboard overview
"""

from django.urls import path
from . import views

urlpatterns = [
    # Dashboard overview
    path('dashboard/', views.dashboard_overview, name='dashboard_overview'),
    
    # Agent statistics
    path('agents/performance/', views.AgentPerformanceStatsView.as_view(), name='agent_performance'),
    path('agents/rankings/', views.AgentRankingsView.as_view(), name='agent_rankings'),
    
    # Campaign statistics
    path('campaigns/stats/', views.CampaignStatsView.as_view(), name='campaign_stats'),
    path('campaigns/<int:campaign_id>/hourly/', views.CampaignHourlyStatsView.as_view(), name='campaign_hourly_stats'),
    
    # Call analytics
    path('calls/analytics/', views.CallAnalyticsView.as_view(), name='call_analytics'),
    path('calls/volume/', views.CallVolumeView.as_view(), name='call_volume'),
    
    # Disposition statistics
    path('dispositions/stats/', views.DispositionStatsView.as_view(), name='disposition_stats'),
    path('dispositions/funnel/', views.ConversionFunnelView.as_view(), name='conversion_funnel'),
]

# URL patterns will generate the following endpoints:
# /api/v1/reporting/dashboard/ - Real-time dashboard overview
# /api/v1/reporting/agents/performance/ - Agent performance statistics
# /api/v1/reporting/agents/rankings/ - Agent rankings and leaderboards
# /api/v1/reporting/campaigns/stats/ - Campaign performance statistics
# /api/v1/reporting/campaigns/{id}/hourly/ - Hourly campaign statistics
# /api/v1/reporting/calls/analytics/ - Call analytics overview
# /api/v1/reporting/calls/volume/ - Real-time call volume metrics
# /api/v1/reporting/dispositions/stats/ - Disposition statistics
# /api/v1/reporting/dispositions/funnel/ - Conversion funnel data
