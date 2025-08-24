"""
Real-time statistics API views for the reporting app.

This module provides REST API endpoints for real-time statistics including:
- Agent performance metrics
- Campaign statistics
- Call analytics
- Disposition reports
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from django.utils import timezone
from datetime import datetime, timedelta
from django.db.models import Count, Sum, Avg
from django.core.cache import cache

from .models import AgentPerformanceReport, CampaignPerformanceReport, CallAnalyticsReport, DispositionReport
from agents.permissions import IsSupervisorOrAbove
from agents.models import User, AgentStatus
from campaigns.models import Campaign
from calls.models import CallDetailRecord, Disposition


class AgentPerformanceStatsView(APIView):
    """
    Real-time agent performance statistics endpoint.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Get agent performance statistics"""
        agent_id = request.query_params.get('agent_id')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        # Parse dates if provided
        if start_date:
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00')).date()
        if end_date:
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00')).date()
        
        # Get agent stats
        stats = AgentPerformanceReport.get_agent_stats(
            agent_id=agent_id,
            start_date=start_date,
            end_date=end_date
        )
        
        return Response({
            'success': True,
            'data': stats,
            'timestamp': timezone.now().isoformat()
        })

    def post(self, request):
        """Get hourly performance for specific agent and date"""
        agent_id = request.data.get('agent_id')
        date_str = request.data.get('date')
        
        date = None
        if date_str:
            date = datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
        
        hourly_stats = AgentPerformanceReport.get_hourly_performance(
            agent_id=agent_id,
            date=date
        )
        
        return Response({
            'success': True,
            'data': hourly_stats,
            'timestamp': timezone.now().isoformat()
        })


class AgentRankingsView(APIView):
    """
    Agent rankings and leaderboard statistics.
    """
    permission_classes = [permissions.IsAuthenticated, IsSupervisorOrAbove]

    def get(self, request):
        """Get agent rankings"""
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        metric = request.query_params.get('metric', 'total_calls')
        
        # Parse dates if provided
        if start_date:
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00')).date()
        if end_date:
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00')).date()
        
        rankings = AgentPerformanceReport.get_agent_rankings(
            start_date=start_date,
            end_date=end_date,
            metric=metric
        )
        
        return Response({
            'success': True,
            'data': rankings,
            'metric': metric,
            'timestamp': timezone.now().isoformat()
        })


class CampaignStatsView(APIView):
    """
    Real-time campaign performance statistics endpoint.
    """
    permission_classes = [permissions.IsAuthenticated, IsSupervisorOrAbove]

    def get(self, request):
        """Get campaign statistics"""
        campaign_id = request.query_params.get('campaign_id')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        # Parse dates if provided
        if start_date:
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00')).date()
        if end_date:
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00')).date()
        
        # Get campaign stats
        stats = CampaignPerformanceReport.get_campaign_stats(
            campaign_id=campaign_id,
            start_date=start_date,
            end_date=end_date
        )
        
        return Response({
            'success': True,
            'data': stats,
            'timestamp': timezone.now().isoformat()
        })


class CampaignHourlyStatsView(APIView):
    """
    Hourly campaign performance statistics.
    """
    permission_classes = [permissions.IsAuthenticated, IsSupervisorOrAbove]

    def get(self, request, campaign_id):
        """Get hourly campaign statistics"""
        date_str = request.query_params.get('date')
        
        date = None
        if date_str:
            date = datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
        
        hourly_stats = CampaignPerformanceReport.get_campaign_hourly_stats(
            campaign_id=campaign_id,
            date=date
        )
        
        return Response({
            'success': True,
            'data': hourly_stats,
            'campaign_id': campaign_id,
            'timestamp': timezone.now().isoformat()
        })


class CallAnalyticsView(APIView):
    """
    Real-time call analytics and volume statistics.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Get call analytics overview"""
        days = int(request.query_params.get('days', 30))
        
        # Get daily call volume
        daily_volume = CallAnalyticsReport.get_daily_call_volume(days=days)
        
        # Get today's hourly pattern
        hourly_pattern = CallAnalyticsReport.get_hourly_call_pattern()
        
        # Get call outcome distribution
        start_date = timezone.now().date() - timedelta(days=days)
        outcome_distribution = CallAnalyticsReport.get_call_outcome_distribution(
            start_date=start_date
        )
        
        return Response({
            'success': True,
            'data': {
                'daily_volume': daily_volume,
                'hourly_pattern': hourly_pattern,
                'outcome_distribution': outcome_distribution
            },
            'period_days': days,
            'timestamp': timezone.now().isoformat()
        })


class CallVolumeView(APIView):
    """
    Real-time call volume statistics.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Get call volume metrics"""
        # Cache key for call volume stats
        cache_key = 'call_volume_stats'
        cached_stats = cache.get(cache_key)
        
        if cached_stats is None:
            # Calculate current stats
            now = timezone.now()
            today = now.date()
            
            stats = {
                'today_total': CallDetailRecord.objects.filter(call_date=today).count(),
                'today_answered': CallDetailRecord.objects.filter(
                    call_date=today, 
                    answer_time__isnull=False
                ).count(),
                'current_hour': CallDetailRecord.objects.filter(
                    call_date=today,
                    call_time__hour=now.hour
                ).count(),
                'active_calls': CallDetailRecord.objects.filter(
                    call_date=today,
                    end_time__isnull=True
                ).count()
            }
            
            # Calculate answer rate
            stats['answer_rate'] = (
                (stats['today_answered'] / stats['today_total'] * 100) 
                if stats['today_total'] > 0 else 0
            )
            
            # Cache for 30 seconds
            cache.set(cache_key, stats, 30)
            cached_stats = stats
        
        return Response({
            'success': True,
            'data': cached_stats,
            'timestamp': timezone.now().isoformat()
        })


class DispositionStatsView(APIView):
    """
    Real-time disposition statistics endpoint.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Get disposition statistics"""
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        campaign_id = request.query_params.get('campaign_id')
        
        # Parse dates if provided
        if start_date:
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00')).date()
        if end_date:
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00')).date()
        
        # Get disposition stats
        stats = DispositionReport.get_disposition_stats(
            start_date=start_date,
            end_date=end_date,
            campaign_id=campaign_id
        )
        
        return Response({
            'success': True,
            'data': stats,
            'campaign_id': campaign_id,
            'timestamp': timezone.now().isoformat()
        })


class ConversionFunnelView(APIView):
    """
    Conversion funnel statistics for campaigns.
    """
    permission_classes = [permissions.IsAuthenticated, IsSupervisorOrAbove]

    def get(self, request):
        """Get conversion funnel data"""
        campaign_id = request.query_params.get('campaign_id')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        # Parse dates if provided
        if start_date:
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00')).date()
        if end_date:
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00')).date()
        
        funnel_data = DispositionReport.get_conversion_funnel(
            campaign_id=campaign_id,
            start_date=start_date,
            end_date=end_date
        )
        
        return Response({
            'success': True,
            'data': funnel_data,
            'campaign_id': campaign_id,
            'timestamp': timezone.now().isoformat()
        })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def dashboard_overview(request):
    """
    Real-time dashboard overview with key metrics.
    """
    cache_key = 'dashboard_overview'
    cached_data = cache.get(cache_key)
    
    if cached_data is None:
        now = timezone.now()
        today = now.date()
        
        # Key metrics
        overview = {
            'agents_online': User.objects.filter(
                agentstatus__status='available',
                agentstatus__last_activity__gte=now - timedelta(minutes=5)
            ).count(),
            'total_calls_today': CallDetailRecord.objects.filter(call_date=today).count(),
            'answered_calls_today': CallDetailRecord.objects.filter(
                call_date=today, 
                answer_time__isnull=False
            ).count(),
            'active_campaigns': Campaign.objects.filter(is_active=True).count(),
            'pending_callbacks': Disposition.objects.filter(
                schedule_callback=True,
                callback_date__lte=today
            ).count()
        }
        
        # Calculate derived metrics
        overview['answer_rate'] = (
            (overview['answered_calls_today'] / overview['total_calls_today'] * 100) 
            if overview['total_calls_today'] > 0 else 0
        )
        
        # Cache for 1 minute
        cache.set(cache_key, overview, 60)
        cached_data = overview
    
    return Response({
        'success': True,
        'data': cached_data,
        'timestamp': timezone.now().isoformat()
    })
