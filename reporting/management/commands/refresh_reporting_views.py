"""
Django management command to refresh materialized reporting views.
This command generates and caches reporting data to improve performance
for dashboards and analytics queries.

Usage:
    python manage.py refresh_reporting_views
    python manage.py refresh_reporting_views --days=30
    python manage.py refresh_reporting_views --views=agent,campaign
"""

from django.core.management.base import BaseCommand, CommandError
from django.core.cache import cache
from django.utils import timezone
from datetime import datetime, timedelta
import time
import json

from reporting.models import (
    AgentPerformanceReport, 
    CampaignPerformanceReport, 
    CallAnalyticsReport, 
    DispositionReport
)
from agents.models import User
from campaigns.models import Campaign


class Command(BaseCommand):
    help = 'Refresh materialized reporting views and cache reporting data'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=30,
            help='Number of days to include in reporting data (default: 30)'
        )
        parser.add_argument(
            '--views',
            type=str,
            default='all',
            help='Comma-separated list of views to refresh: agent,campaign,call,disposition,all (default: all)'
        )
        parser.add_argument(
            '--cache-timeout',
            type=int,
            default=3600,
            help='Cache timeout in seconds (default: 3600 = 1 hour)'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Enable verbose output'
        )

    def handle(self, *args, **options):
        start_time = time.time()
        days = options['days']
        views = options['views'].lower().split(',')
        cache_timeout = options['cache_timeout']
        verbose = options['verbose']
        
        # Calculate date range
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
        
        if verbose:
            self.stdout.write(f"Refreshing reporting views for date range: {start_date} to {end_date}")
            self.stdout.write(f"Cache timeout: {cache_timeout} seconds")
        
        refreshed_views = []
        
        try:
            # Refresh Agent Performance Views
            if 'all' in views or 'agent' in views:
                self._refresh_agent_performance_views(start_date, end_date, cache_timeout, verbose)
                refreshed_views.append('agent')
            
            # Refresh Campaign Performance Views
            if 'all' in views or 'campaign' in views:
                self._refresh_campaign_performance_views(start_date, end_date, cache_timeout, verbose)
                refreshed_views.append('campaign')
            
            # Refresh Call Analytics Views
            if 'all' in views or 'call' in views:
                self._refresh_call_analytics_views(start_date, end_date, cache_timeout, verbose)
                refreshed_views.append('call')
            
            # Refresh Disposition Views
            if 'all' in views or 'disposition' in views:
                self._refresh_disposition_views(start_date, end_date, cache_timeout, verbose)
                refreshed_views.append('disposition')
            
            # Store refresh metadata
            refresh_metadata = {
                'last_refreshed': timezone.now().isoformat(),
                'date_range': {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat()
                },
                'views_refreshed': refreshed_views,
                'execution_time': time.time() - start_time
            }
            cache.set('reporting_views_metadata', refresh_metadata, cache_timeout)
            
            execution_time = time.time() - start_time
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully refreshed {len(refreshed_views)} view types in {execution_time:.2f} seconds"
                )
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error refreshing reporting views: {str(e)}")
            )
            raise CommandError(f"Failed to refresh reporting views: {str(e)}")

    def _refresh_agent_performance_views(self, start_date, end_date, cache_timeout, verbose):
        """Refresh agent performance reporting data"""
        if verbose:
            self.stdout.write("Refreshing agent performance views...")
        
        # Overall agent performance summary
        overall_stats = AgentPerformanceReport.get_agent_stats(
            start_date=start_date, 
            end_date=end_date
        )
        cache.set('agent_performance_overall', overall_stats, cache_timeout)
        
        # Individual agent performance
        agents = User.objects.filter(role__name='agent', is_active=True)
        agent_stats = {}
        
        for agent in agents:
            stats = AgentPerformanceReport.get_agent_stats(
                agent_id=agent.id,
                start_date=start_date,
                end_date=end_date
            )
            agent_stats[agent.id] = stats
        
        cache.set('agent_performance_individual', agent_stats, cache_timeout)
        
        # Agent rankings
        rankings = AgentPerformanceReport.get_agent_rankings(
            start_date=start_date,
            end_date=end_date
        )
        cache.set('agent_performance_rankings', list(rankings), cache_timeout)
        
        # Hourly performance patterns for today
        today = timezone.now().date()
        hourly_patterns = {}
        
        for agent in agents:
            hourly_data = AgentPerformanceReport.get_hourly_performance(
                agent_id=agent.id,
                date=today
            )
            hourly_patterns[agent.id] = list(hourly_data)
        
        cache.set('agent_performance_hourly', hourly_patterns, cache_timeout)
        
        if verbose:
            self.stdout.write(f"  - Cached performance data for {agents.count()} agents")

    def _refresh_campaign_performance_views(self, start_date, end_date, cache_timeout, verbose):
        """Refresh campaign performance reporting data"""
        if verbose:
            self.stdout.write("Refreshing campaign performance views...")
        
        # Overall campaign performance
        overall_stats = CampaignPerformanceReport.get_campaign_stats(
            start_date=start_date,
            end_date=end_date
        )
        cache.set('campaign_performance_overall', overall_stats, cache_timeout)
        
        # Individual campaign performance
        campaigns = Campaign.objects.filter(is_active=True)
        campaign_stats = {}
        
        for campaign in campaigns:
            stats = CampaignPerformanceReport.get_campaign_stats(
                campaign_id=campaign.id,
                start_date=start_date,
                end_date=end_date
            )
            lead_stats = CampaignPerformanceReport.get_campaign_lead_stats(campaign.id)
            stats.update(lead_stats)
            campaign_stats[campaign.id] = stats
        
        cache.set('campaign_performance_individual', campaign_stats, cache_timeout)
        
        # Campaign hourly patterns for today
        today = timezone.now().date()
        hourly_patterns = {}
        
        for campaign in campaigns:
            hourly_data = CampaignPerformanceReport.get_campaign_hourly_stats(
                campaign_id=campaign.id,
                date=today
            )
            hourly_patterns[campaign.id] = list(hourly_data)
        
        cache.set('campaign_performance_hourly', hourly_patterns, cache_timeout)
        
        if verbose:
            self.stdout.write(f"  - Cached performance data for {campaigns.count()} campaigns")

    def _refresh_call_analytics_views(self, start_date, end_date, cache_timeout, verbose):
        """Refresh call analytics reporting data"""
        if verbose:
            self.stdout.write("Refreshing call analytics views...")
        
        # Daily call volume trends
        daily_volume = CallAnalyticsReport.get_daily_call_volume(
            days=(end_date - start_date).days
        )
        cache.set('call_analytics_daily_volume', list(daily_volume), cache_timeout)
        
        # Hourly call patterns for today
        today = timezone.now().date()
        hourly_patterns = CallAnalyticsReport.get_hourly_call_pattern(date=today)
        cache.set('call_analytics_hourly_patterns', list(hourly_patterns), cache_timeout)
        
        # Call outcome distribution
        outcome_distribution = CallAnalyticsReport.get_call_outcome_distribution(
            start_date=start_date,
            end_date=end_date
        )
        cache.set('call_analytics_outcomes', list(outcome_distribution), cache_timeout)
        
        # Recording statistics
        recording_stats = CallAnalyticsReport.get_recording_statistics(
            start_date=start_date,
            end_date=end_date
        )
        cache.set('call_analytics_recordings', recording_stats, cache_timeout)
        
        if verbose:
            self.stdout.write("  - Cached call analytics data")

    def _refresh_disposition_views(self, start_date, end_date, cache_timeout, verbose):
        """Refresh disposition reporting data"""
        if verbose:
            self.stdout.write("Refreshing disposition views...")
        
        # Overall disposition statistics
        overall_disposition_stats = DispositionReport.get_disposition_stats(
            start_date=start_date,
            end_date=end_date
        )
        cache.set('disposition_stats_overall', list(overall_disposition_stats), cache_timeout)
        
        # Overall conversion funnel
        overall_funnel = DispositionReport.get_conversion_funnel(
            start_date=start_date,
            end_date=end_date
        )
        cache.set('disposition_funnel_overall', overall_funnel, cache_timeout)
        
        # Per-campaign disposition statistics
        campaigns = Campaign.objects.filter(is_active=True)
        campaign_dispositions = {}
        campaign_funnels = {}
        
        for campaign in campaigns:
            disposition_stats = DispositionReport.get_disposition_stats(
                campaign_id=campaign.id,
                start_date=start_date,
                end_date=end_date
            )
            funnel_stats = DispositionReport.get_conversion_funnel(
                campaign_id=campaign.id,
                start_date=start_date,
                end_date=end_date
            )
            
            campaign_dispositions[campaign.id] = list(disposition_stats)
            campaign_funnels[campaign.id] = funnel_stats
        
        cache.set('disposition_stats_by_campaign', campaign_dispositions, cache_timeout)
        cache.set('disposition_funnels_by_campaign', campaign_funnels, cache_timeout)
        
        if verbose:
            self.stdout.write(f"  - Cached disposition data for {campaigns.count()} campaigns")
