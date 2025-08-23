from django.db import models
from django.db.models import Count, Sum, Avg, Max, Min, Q, F, Case, When, Value
from django.db.models.functions import Extract, TruncDate, TruncHour
from django.utils import timezone
from datetime import datetime, timedelta
from agents.models import User, AgentStatus
from campaigns.models import Campaign, CampaignStatistics
from calls.models import CallDetailRecord, Recording
from leads.models import Lead, Disposition, DispositionCode


class ReportingQuerySet(models.QuerySet):
    """Base queryset with common reporting methods"""
    
    def today(self):
        return self.filter(created_at__date=timezone.now().date())
    
    def this_week(self):
        start_week = timezone.now().date() - timedelta(days=timezone.now().weekday())
        return self.filter(created_at__date__gte=start_week)
    
    def this_month(self):
        return self.filter(created_at__year=timezone.now().year, 
                          created_at__month=timezone.now().month)
    
    def date_range(self, start_date, end_date):
        return self.filter(created_at__date__range=[start_date, end_date])


class AgentPerformanceReport:
    """Agent performance reporting utility class"""
    
    @classmethod
    def get_agent_stats(cls, agent_id=None, start_date=None, end_date=None):
        """Get comprehensive agent performance statistics"""
        queryset = CallDetailRecord.objects.all()
        
        if agent_id:
            queryset = queryset.filter(agent_id=agent_id)
        
        if start_date:
            queryset = queryset.filter(call_date__gte=start_date)
        
        if end_date:
            queryset = queryset.filter(call_date__lte=end_date)
        
        return queryset.aggregate(
            total_calls=Count('id'),
            answered_calls=Count('id', filter=Q(call_result='ANSWERED')),
            completed_calls=Count('id', filter=Q(call_result='COMPLETED')),
            dropped_calls=Count('id', filter=Q(call_result='DROPPED')),
            total_talk_time=Sum('talk_duration'),
            avg_talk_time=Avg('talk_duration'),
            total_cost=Sum('cost'),
            avg_cost=Avg('cost'),
        )
    
    @classmethod
    def get_hourly_performance(cls, agent_id=None, date=None):
        """Get hourly call performance for an agent"""
        if date is None:
            date = timezone.now().date()
            
        queryset = CallDetailRecord.objects.filter(call_date=date)
        
        if agent_id:
            queryset = queryset.filter(agent_id=agent_id)
        
        return queryset.annotate(
            hour=Extract('start_time', 'hour')
        ).values('hour').annotate(
            total_calls=Count('id'),
            answered_calls=Count('id', filter=Q(call_result='ANSWERED')),
            avg_talk_time=Avg('talk_duration'),
        ).order_by('hour')
    
    @classmethod
    def get_agent_rankings(cls, start_date=None, end_date=None, metric='total_calls'):
        """Get agent rankings by specified metric"""
        queryset = CallDetailRecord.objects.select_related('agent')
        
        if start_date:
            queryset = queryset.filter(call_date__gte=start_date)
        
        if end_date:
            queryset = queryset.filter(call_date__lte=end_date)
        
        return queryset.values(
            'agent_id',
            'agent__username',
            'agent__first_name',
            'agent__last_name'
        ).annotate(
            total_calls=Count('id'),
            answered_calls=Count('id', filter=Q(call_result='ANSWERED')),
            completed_calls=Count('id', filter=Q(call_result='COMPLETED')),
            total_talk_time=Sum('talk_duration'),
            avg_talk_time=Avg('talk_duration'),
            contact_rate=Case(
                When(total_calls__gt=0, then=F('answered_calls') * 100.0 / F('total_calls')),
                default=Value(0.0)
            )
        ).order_by(f'-{metric}')


class CampaignPerformanceReport:
    """Campaign performance reporting utility class"""
    
    @classmethod
    def get_campaign_stats(cls, campaign_id=None, start_date=None, end_date=None):
        """Get comprehensive campaign performance statistics"""
        queryset = CallDetailRecord.objects.all()
        
        if campaign_id:
            queryset = queryset.filter(campaign_id=campaign_id)
        
        if start_date:
            queryset = queryset.filter(call_date__gte=start_date)
        
        if end_date:
            queryset = queryset.filter(call_date__lte=end_date)
        
        return queryset.aggregate(
            total_calls=Count('id'),
            answered_calls=Count('id', filter=Q(call_result='ANSWERED')),
            completed_calls=Count('id', filter=Q(call_result='COMPLETED')),
            dropped_calls=Count('id', filter=Q(call_result='DROPPED')),
            busy_calls=Count('id', filter=Q(call_result='BUSY')),
            no_answer_calls=Count('id', filter=Q(call_result='NO_ANSWER')),
            failed_calls=Count('id', filter=Q(call_result='FAILED')),
            total_talk_time=Sum('talk_duration'),
            avg_talk_time=Avg('talk_duration'),
            total_cost=Sum('cost'),
            avg_cost=Avg('cost'),
        )
    
    @classmethod
    def get_campaign_hourly_stats(cls, campaign_id, date=None):
        """Get hourly campaign performance"""
        if date is None:
            date = timezone.now().date()
            
        return CallDetailRecord.objects.filter(
            campaign_id=campaign_id,
            call_date=date
        ).annotate(
            hour=Extract('start_time', 'hour')
        ).values('hour').annotate(
            total_calls=Count('id'),
            answered_calls=Count('id', filter=Q(call_result='ANSWERED')),
            dropped_calls=Count('id', filter=Q(call_result='DROPPED')),
            avg_talk_time=Avg('talk_duration'),
        ).order_by('hour')
    
    @classmethod
    def get_campaign_lead_stats(cls, campaign_id):
        """Get lead statistics for a campaign"""
        return Lead.objects.filter(campaign_id=campaign_id).aggregate(
            total_leads=Count('id'),
            fresh_leads=Count('id', filter=Q(status='NEW', call_attempts=0)),
            callback_leads=Count('id', filter=Q(status='CALLBACK')),
            dnc_leads=Count('id', filter=Q(status='DNC')),
            completed_leads=Count('id', filter=Q(status='COMPLETED')),
            avg_attempts=Avg('call_attempts'),
            max_attempts=Max('call_attempts'),
        )


class CallAnalyticsReport:
    """Call analytics and telephony performance reporting"""
    
    @classmethod
    def get_daily_call_volume(cls, days=30):
        """Get daily call volume for the last N days"""
        start_date = timezone.now().date() - timedelta(days=days)
        
        return CallDetailRecord.objects.filter(
            call_date__gte=start_date
        ).annotate(
            date=TruncDate('call_date')
        ).values('date').annotate(
            total_calls=Count('id'),
            answered_calls=Count('id', filter=Q(call_result='ANSWERED')),
            dropped_calls=Count('id', filter=Q(call_result='DROPPED')),
            avg_talk_time=Avg('talk_duration'),
        ).order_by('date')
    
    @classmethod
    def get_hourly_call_pattern(cls, date=None):
        """Get hourly call patterns for a specific date"""
        if date is None:
            date = timezone.now().date()
            
        return CallDetailRecord.objects.filter(
            call_date=date
        ).annotate(
            hour=Extract('start_time', 'hour')
        ).values('hour').annotate(
            total_calls=Count('id'),
            answered_calls=Count('id', filter=Q(call_result='ANSWERED')),
            avg_talk_time=Avg('talk_duration'),
            answer_rate=Case(
                When(total_calls__gt=0, then=F('answered_calls') * 100.0 / F('total_calls')),
                default=Value(0.0)
            )
        ).order_by('hour')
    
    @classmethod
    def get_call_outcome_distribution(cls, start_date=None, end_date=None):
        """Get distribution of call outcomes"""
        queryset = CallDetailRecord.objects.all()
        
        if start_date:
            queryset = queryset.filter(call_date__gte=start_date)
        
        if end_date:
            queryset = queryset.filter(call_date__lte=end_date)
        
        return queryset.values('call_result').annotate(
            count=Count('id'),
            percentage=Count('id') * 100.0 / Count('id', filter=Q())
        ).order_by('-count')
    
    @classmethod
    def get_recording_statistics(cls, start_date=None, end_date=None):
        """Get call recording statistics"""
        queryset = CallDetailRecord.objects.all()
        
        if start_date:
            queryset = queryset.filter(call_date__gte=start_date)
        
        if end_date:
            queryset = queryset.filter(call_date__lte=end_date)
        
        return queryset.aggregate(
            total_calls=Count('id'),
            recorded_calls=Count('id', filter=Q(recording__isnull=False)),
            recording_rate=Case(
                When(total_calls__gt=0, then=F('recorded_calls') * 100.0 / F('total_calls')),
                default=Value(0.0)
            ),
            total_recording_size=Sum('recording__file_size'),
        )


class DispositionReport:
    """Disposition and conversion reporting"""
    
    @classmethod
    def get_disposition_stats(cls, start_date=None, end_date=None, campaign_id=None):
        """Get disposition statistics"""
        queryset = Disposition.objects.select_related('disposition_code', 'lead')
        
        if start_date:
            queryset = queryset.filter(created_at__date__gte=start_date)
        
        if end_date:
            queryset = queryset.filter(created_at__date__lte=end_date)
        
        if campaign_id:
            queryset = queryset.filter(lead__campaign_id=campaign_id)
        
        return queryset.values(
            'disposition_code__code',
            'disposition_code__description'
        ).annotate(
            count=Count('id'),
            is_sale=F('disposition_code__is_sale'),
            requires_callback=F('disposition_code__requires_callback')
        ).order_by('-count')
    
    @classmethod
    def get_conversion_funnel(cls, campaign_id=None, start_date=None, end_date=None):
        """Get conversion funnel statistics"""
        base_query = {}
        
        if campaign_id:
            base_query['lead__campaign_id'] = campaign_id
        
        if start_date:
            base_query['created_at__date__gte'] = start_date
        
        if end_date:
            base_query['created_at__date__lte'] = end_date
        
        dispositions = Disposition.objects.filter(**base_query)
        
        return {
            'total_dispositions': dispositions.count(),
            'sales': dispositions.filter(disposition_code__is_sale=True).count(),
            'callbacks': dispositions.filter(disposition_code__requires_callback=True).count(),
            'total_sale_amount': dispositions.filter(
                disposition_code__is_sale=True
            ).aggregate(total=Sum('sale_amount'))['total'] or 0,
        }


# Create your models here.
# Note: The reporting functionality is implemented as utility classes above
# rather than traditional Django models to provide more flexibility
