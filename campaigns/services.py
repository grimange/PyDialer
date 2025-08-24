"""
Predictive Dialing Service

This module implements the core predictive dialing algorithms for the PyDialer system.
It provides intelligent call pacing, agent availability monitoring, and drop rate optimization.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict, Tuple
from django.utils import timezone
from django.db.models import Q, Count, Avg
from django.contrib.auth import get_user_model

from .models import Campaign, CampaignStatistics
from leads.models import Lead
from calls.models import CallTask
from agents.models import AgentStatus

User = get_user_model()
logger = logging.getLogger(__name__)


class PredictiveDialingService:
    """
    Core service for predictive dialing operations.
    
    This service implements various dialing modes:
    - Predictive: Automatically dials multiple leads per available agent
    - Progressive: Dials one lead per available agent
    - Preview: Presents lead to agent before dialing
    - Ratio: Fixed ratio dialing based on pacing_ratio setting
    """
    
    def __init__(self, campaign: Campaign):
        self.campaign = campaign
        self.statistics = getattr(campaign, 'statistics', None)
        
    def should_make_calls(self) -> bool:
        """
        Determine if the campaign should initiate calls based on current conditions.
        
        Returns:
            bool: True if calls should be made, False otherwise
        """
        # Check if campaign is active and in time window
        if not self.campaign.is_active() or not self.campaign.is_in_time_window():
            logger.info(f"Campaign {self.campaign.name} is not active or outside time window")
            return False
            
        # Check if we have available agents
        available_agents = self.get_available_agent_count()
        if available_agents == 0:
            logger.debug(f"No available agents for campaign {self.campaign.name}")
            return False
            
        # Check drop rate compliance
        if self.campaign.should_reduce_pace():
            current_drop_rate = self.get_current_drop_rate()
            logger.warning(f"Campaign {self.campaign.name} exceeding drop SLA: "
                         f"{current_drop_rate:.2f}% > {self.campaign.drop_sla}%")
            # Still allow calls but with reduced pacing
            
        # Check if we have dialable leads
        dialable_leads = self.get_dialable_leads_count()
        if dialable_leads == 0:
            logger.info(f"No dialable leads available for campaign {self.campaign.name}")
            return False
            
        return True
    
    def calculate_calls_to_make(self) -> int:
        """
        Calculate the number of calls to initiate based on the campaign's dial method.
        
        Returns:
            int: Number of calls to make
        """
        available_agents = self.get_available_agent_count()
        
        if available_agents == 0:
            return 0
            
        if self.campaign.dial_method == 'manual':
            # Manual dialing - no automatic calls
            return 0
            
        elif self.campaign.dial_method == 'preview':
            # Preview mode - one lead per agent, agent initiates
            return 0  # Agents will manually dial after preview
            
        elif self.campaign.dial_method == 'progressive':
            # Progressive - one call per available agent
            active_calls = self.get_active_calls_count()
            return max(0, available_agents - active_calls)
            
        elif self.campaign.dial_method == 'ratio':
            # Fixed ratio dialing
            return self._calculate_ratio_calls(available_agents)
            
        elif self.campaign.dial_method == 'predictive':
            # Intelligent predictive dialing
            return self._calculate_predictive_calls(available_agents)
            
        else:
            # Default to progressive
            logger.warning(f"Unknown dial method {self.campaign.dial_method}, defaulting to progressive")
            active_calls = self.get_active_calls_count()
            return max(0, available_agents - active_calls)
    
    def _calculate_ratio_calls(self, available_agents: int) -> int:
        """
        Calculate calls for ratio dialing mode.
        
        Args:
            available_agents: Number of available agents
            
        Returns:
            int: Number of calls to make
        """
        active_calls = self.get_active_calls_count()
        target_calls = int(available_agents * float(self.campaign.pacing_ratio))
        
        # Apply drop rate adjustment
        if self.campaign.should_reduce_pace():
            drop_rate_factor = max(0.5, 1.0 - (self.get_current_drop_rate() / 100))
            target_calls = int(target_calls * drop_rate_factor)
            
        return max(0, target_calls - active_calls)
    
    def _calculate_predictive_calls(self, available_agents: int) -> int:
        """
        Calculate calls for predictive dialing mode using advanced algorithms.
        
        This implements a sophisticated predictive algorithm that considers:
        - Historical answer rates
        - Average call duration
        - Agent availability patterns
        - Current drop rate
        
        Args:
            available_agents: Number of available agents
            
        Returns:
            int: Number of calls to make
        """
        # Get historical metrics
        contact_rate = self.get_contact_rate() / 100.0  # Convert percentage to decimal
        avg_call_duration = self.get_average_call_duration_minutes()
        avg_wrap_time = self.get_average_wrap_time_minutes()
        
        # Calculate agent capacity
        total_agent_time = avg_call_duration + avg_wrap_time
        if total_agent_time <= 0:
            total_agent_time = 5.0  # Default assumption: 5 minutes per call cycle
            
        # Base predictive ratio calculation
        if contact_rate > 0:
            # Predictive ratio = 1 / contact_rate, adjusted for agent utilization
            base_ratio = min(10.0, 1.0 / max(0.1, contact_rate))
        else:
            # No historical data, use conservative ratio
            base_ratio = float(self.campaign.pacing_ratio)
            
        # Adjust for current performance
        current_drop_rate = self.get_current_drop_rate()
        
        if current_drop_rate > self.campaign.drop_sla:
            # Reduce aggressiveness if exceeding drop SLA
            drop_penalty = 1.0 - min(0.5, (current_drop_rate - self.campaign.drop_sla) / 10.0)
            base_ratio *= drop_penalty
            
        elif current_drop_rate < self.campaign.drop_sla * 0.5:
            # Increase aggressiveness if well below drop SLA
            drop_bonus = 1.0 + min(0.3, (self.campaign.drop_sla * 0.5 - current_drop_rate) / 10.0)
            base_ratio *= drop_bonus
            
        # Calculate target calls
        active_calls = self.get_active_calls_count()
        target_calls = int(available_agents * base_ratio)
        
        # Apply safety limits
        target_calls = min(target_calls, available_agents * 5)  # Never exceed 5x agents
        target_calls = max(target_calls, available_agents)       # Always at least 1x agents
        
        calls_to_make = max(0, target_calls - active_calls)
        
        logger.info(f"Predictive calculation for {self.campaign.name}: "
                   f"agents={available_agents}, contact_rate={contact_rate:.2%}, "
                   f"base_ratio={base_ratio:.2f}, target_calls={target_calls}, "
                   f"active_calls={active_calls}, calls_to_make={calls_to_make}")
        
        return calls_to_make
    
    def get_dialable_leads(self, limit: int = None) -> List[Lead]:
        """
        Get leads that are ready to be dialed with timezone-aware filtering.
        
        Args:
            limit: Maximum number of leads to return
            
        Returns:
            List[Lead]: Dialable leads ordered by priority, filtered by timezone
        """
        from leads.models import Lead
        
        now = timezone.now()
        
        # Base query for dialable leads
        queryset = Lead.objects.filter(
            campaign=self.campaign,
            status__in=['new', 'callback', 'retry'],
            attempts__lt=self.campaign.max_attempts,
            is_dnc=False,  # Use is_dnc instead of do_not_call
        ).exclude(
            # Exclude leads in retry delay period
            Q(last_call_at__isnull=False) & 
            Q(last_call_at__gt=now - timedelta(minutes=self.campaign.retry_delay_minutes))
        ).order_by('-priority', 'last_call_at', 'created_at')
        
        # Get initial leads (might be more than limit for timezone filtering)
        initial_limit = limit * 3 if limit else 1000  # Get extra to account for timezone filtering
        initial_leads = list(queryset[:initial_limit])
        
        # Apply timezone-aware filtering
        callable_leads = TimezoneSchedulingService.filter_callable_leads(
            initial_leads, self.campaign
        )
        
        # Apply final limit after timezone filtering
        if limit and len(callable_leads) > limit:
            callable_leads = callable_leads[:limit]
            
        return callable_leads
    
    def get_dialable_leads_count(self) -> int:
        """
        Get count of dialable leads with timezone awareness.
        
        Note: This provides an estimate as timezone filtering requires 
        individual lead evaluation which is expensive for counting.
        """
        from leads.models import Lead
        
        now = timezone.now()
        
        # Get base count without timezone filtering (for performance)
        base_count = Lead.objects.filter(
            campaign=self.campaign,
            status__in=['new', 'callback', 'retry'],
            attempts__lt=self.campaign.max_attempts,
            is_dnc=False,  # Use is_dnc instead of do_not_call
        ).exclude(
            Q(last_call_at__isnull=False) & 
            Q(last_call_at__gt=now - timedelta(minutes=self.campaign.retry_delay_minutes))
        ).count()
        
        # For accurate count, we'd need to apply timezone filtering,
        # but that's expensive for large datasets. Return base count as estimate.
        # For precise counts when needed, use len(get_dialable_leads())
        return base_count
    
    def get_available_agent_count(self) -> int:
        """Get number of agents available for this campaign."""
        return self.campaign.get_available_agents().count()
    
    def get_active_calls_count(self) -> int:
        """Get number of active calls for this campaign."""
        if self.statistics:
            return self.statistics.active_calls
        
        # Fallback to direct query if statistics not available
        return CallTask.objects.filter(
            campaign=self.campaign,
            state__in=['dialing', 'ringing', 'connected']
        ).count()
    
    def get_current_drop_rate(self) -> float:
        """Get current drop rate percentage."""
        if self.statistics:
            return float(self.statistics.calculate_drop_rate_today())
        return float(self.campaign.current_drop_rate)
    
    def get_contact_rate(self) -> float:
        """Get current contact rate percentage."""
        if self.statistics:
            return float(self.statistics.contact_rate_today)
        return self.campaign.calculate_contact_rate()
    
    def get_average_call_duration_minutes(self) -> float:
        """Get average call duration in minutes."""
        if self.statistics and self.statistics.average_call_duration:
            return self.statistics.average_call_duration.total_seconds() / 60.0
        
        # Fallback calculation from recent calls
        recent_calls = CallTask.objects.filter(
            campaign=self.campaign,
            state='completed',
            completed_at__isnull=False,
            call_duration__isnull=False,
            created_at__gte=timezone.now() - timedelta(days=7)
        )
        
        if recent_calls.exists():
            avg_duration = recent_calls.aggregate(
                avg_duration=Avg('call_duration')
            )['avg_duration']
            if avg_duration:
                return avg_duration.total_seconds() / 60.0
        
        return 3.0  # Default assumption
    
    def get_average_wrap_time_minutes(self) -> float:
        """Get average wrap-up time in minutes."""
        if self.statistics and self.statistics.average_wrap_time:
            return self.statistics.average_wrap_time.total_seconds() / 60.0
        
        return float(self.campaign.wrap_up_time) / 60.0  # Convert seconds to minutes
    
    def update_statistics(self, call_attempted: bool = False, call_answered: bool = False, 
                         call_dropped: bool = False) -> None:
        """
        Update campaign statistics after call events.
        
        Args:
            call_attempted: Whether a call was attempted
            call_answered: Whether a call was answered
            call_dropped: Whether a call was dropped (abandoned)
        """
        if not self.statistics:
            # Create statistics if they don't exist
            self.statistics = CampaignStatistics.objects.create(campaign=self.campaign)
            
        if call_attempted:
            self.statistics.calls_attempted_today += 1
            
        if call_answered:
            self.statistics.calls_answered_today += 1
            
        if call_dropped:
            self.statistics.calls_dropped_today += 1
            
        # Update contact rate
        if self.statistics.calls_attempted_today > 0:
            self.statistics.contact_rate_today = (
                self.statistics.calls_answered_today / 
                self.statistics.calls_attempted_today * 100
            )
            
        self.statistics.save()
        
        # Also update the campaign's drop rate
        if self.statistics.calls_attempted_today > 0:
            self.campaign.update_drop_rate(
                self.statistics.calls_dropped_today,
                self.statistics.calls_attempted_today
            )


class PredictiveDialingManager:
    """
    Manager class for handling multiple campaigns and coordinating dialing operations.
    """
    
    @staticmethod
    def get_active_campaigns() -> List[Campaign]:
        """Get all campaigns that should be considered for dialing."""
        return Campaign.objects.filter(
            status='active',
            dial_method__in=['predictive', 'progressive', 'ratio']
        ).select_related('statistics')
    
    @staticmethod
    def process_all_campaigns() -> Dict[str, int]:
        """
        Process all active campaigns and return summary of calls initiated.
        
        Returns:
            Dict[str, int]: Campaign name to calls initiated mapping
        """
        results = {}
        
        for campaign in PredictiveDialingManager.get_active_campaigns():
            dialer = PredictiveDialingService(campaign)
            
            if dialer.should_make_calls():
                calls_to_make = dialer.calculate_calls_to_make()
                
                if calls_to_make > 0:
                    # This would trigger the actual call initiation
                    # Implementation depends on telephony integration
                    logger.info(f"Campaign {campaign.name}: scheduling {calls_to_make} calls")
                    results[campaign.name] = calls_to_make
                else:
                    results[campaign.name] = 0
            else:
                results[campaign.name] = 0
                
        return results
    
    @staticmethod
    def get_system_capacity() -> Dict[str, int]:
        """
        Get overall system capacity information.
        
        Returns:
            Dict with system capacity metrics
        """
        total_agents = User.objects.filter(is_active=True).count()
        available_agents = User.objects.filter(
            current_status__status='available'
        ).count()
        active_calls = sum(
            campaign.statistics.active_calls if campaign.statistics else 0
            for campaign in Campaign.objects.filter(status='active')
        )
        
        return {
            'total_agents': total_agents,
            'available_agents': available_agents,
            'active_calls': active_calls,
            'system_utilization': (active_calls / max(1, available_agents)) * 100
        }


class LeadRecyclingService:
    """
    Service class for handling lead recycling operations based on campaign rules.
    """
    
    def __init__(self, campaign: Campaign):
        """Initialize with a specific campaign."""
        self.campaign = campaign
        self.logger = logging.getLogger(__name__)
    
    def get_recyclable_leads(self, status: str, days_threshold: int, limit: int = 100) -> List[Lead]:
        """
        Get leads eligible for recycling based on status and time threshold.
        
        Args:
            status: Lead status to filter by
            days_threshold: Number of days after last call to consider for recycling
            limit: Maximum number of leads to return
            
        Returns:
            List of Lead objects eligible for recycling
        """
        current_time = timezone.now()
        cutoff_time = current_time - timedelta(days=days_threshold)
        
        # Base query for recyclable leads
        leads_query = Lead.objects.filter(
            campaign=self.campaign,
            status=status,
            last_call_at__lte=cutoff_time,
            recycle_count__lt=self.campaign.max_recycle_attempts
        )
        
        # Exclude DNC leads if configured
        if self.campaign.exclude_dnc_from_recycling:
            leads_query = leads_query.filter(is_dnc=False)
        
        return list(leads_query[:limit])
    
    def recycle_lead(self, lead: Lead) -> bool:
        """
        Recycle a single lead by resetting its status and attempt counters.
        
        Args:
            lead: Lead object to recycle
            
        Returns:
            bool: True if successfully recycled, False otherwise
        """
        try:
            # Validate lead can be recycled
            if lead.recycle_count >= self.campaign.max_recycle_attempts:
                self.logger.warning(f"Lead {lead.phone} has reached max recycle attempts")
                return False
            
            if self.campaign.exclude_dnc_from_recycling and lead.is_dnc:
                self.logger.warning(f"Lead {lead.phone} is DNC and cannot be recycled")
                return False
            
            # Reset lead for recycling
            lead.status = 'new'
            lead.attempts = 0
            lead.recycle_count += 1
            lead.next_call_at = None
            lead.last_call_at = None
            
            lead.save(update_fields=[
                'status', 'attempts', 'recycle_count', 
                'next_call_at', 'last_call_at', 'updated_at'
            ])
            
            self.logger.debug(f"Recycled lead {lead.phone} (recycle #{lead.recycle_count})")
            return True
            
        except Exception as e:
            self.logger.error(f"Error recycling lead {lead.phone}: {e}")
            return False
    
    def can_recycle_now(self) -> bool:
        """
        Check if lead recycling can be performed now based on campaign rules.
        
        Returns:
            bool: True if recycling can proceed, False otherwise
        """
        # Check if campaign allows recycling
        if not self.campaign.recycle_inactive_leads:
            return False
        
        # Check if campaign is active
        if self.campaign.status != 'active':
            return False
        
        # Check business hours restriction
        if self.campaign.recycle_only_business_hours and not self.campaign.is_in_time_window():
            return False
        
        return True
    
    def process_campaign_recycling(self, batch_size: int = 100) -> Dict[str, int]:
        """
        Process lead recycling for this campaign based on its rules.
        
        Args:
            batch_size: Maximum number of leads to process per status
            
        Returns:
            Dict with recycling results by status
        """
        if not self.can_recycle_now():
            return {}
        
        results = {}
        
        # Define recyclable statuses and their time thresholds
        recycle_rules = {
            'no_answer': self.campaign.recycle_no_answer_days,
            'busy': self.campaign.recycle_busy_days,
            'disconnected': self.campaign.recycle_disconnected_days,
        }
        
        for status, days_threshold in recycle_rules.items():
            # Get eligible leads
            leads = self.get_recyclable_leads(status, days_threshold, batch_size)
            
            recycled_count = 0
            for lead in leads:
                if self.recycle_lead(lead):
                    recycled_count += 1
            
            results[status] = recycled_count
            
            if recycled_count > 0:
                self.logger.info(f"Recycled {recycled_count} '{status}' leads for campaign {self.campaign.name}")
        
        return results
    
    def get_recycling_stats(self) -> Dict[str, int]:
        """
        Get statistics about leads available for recycling.
        
        Returns:
            Dict with recycling statistics
        """
        stats = {}
        current_time = timezone.now()
        
        recycle_rules = {
            'no_answer': self.campaign.recycle_no_answer_days,
            'busy': self.campaign.recycle_busy_days,
            'disconnected': self.campaign.recycle_disconnected_days,
        }
        
        for status, days_threshold in recycle_rules.items():
            cutoff_time = current_time - timedelta(days=days_threshold)
            
            count = Lead.objects.filter(
                campaign=self.campaign,
                status=status,
                last_call_at__lte=cutoff_time,
                recycle_count__lt=self.campaign.max_recycle_attempts
            ).count()
            
            if self.campaign.exclude_dnc_from_recycling:
                count = Lead.objects.filter(
                    campaign=self.campaign,
                    status=status,
                    last_call_at__lte=cutoff_time,
                    recycle_count__lt=self.campaign.max_recycle_attempts,
                    is_dnc=False
                ).count()
            
            stats[f'{status}_recyclable'] = count
        
        return stats


class TimezoneSchedulingService:
    """
    Service class for handling timezone-aware call scheduling operations.
    """
    
    @staticmethod
    def is_lead_callable_now(lead, campaign=None) -> bool:
        """
        Check if a lead can be called right now based on timezone and business hours.
        
        Args:
            lead: Lead object to check
            campaign: Campaign object (uses lead.campaign if not provided)
            
        Returns:
            bool: True if lead can be called now, False otherwise
        """
        import pytz
        from django.utils import timezone
        
        if campaign is None:
            campaign = lead.campaign
        
        current_utc = timezone.now()
        
        # Convert current time to lead's timezone
        try:
            lead_tz = pytz.timezone(lead.timezone)
            lead_local_time = current_utc.astimezone(lead_tz)
        except (pytz.UnknownTimeZoneError, AttributeError):
            # Fallback to campaign timezone
            try:
                campaign_tz = pytz.timezone(campaign.timezone_name)
                lead_local_time = current_utc.astimezone(campaign_tz)
            except pytz.UnknownTimeZoneError:
                # Fallback to UTC
                lead_local_time = current_utc
        
        # Check if current time is within campaign business hours
        if not TimezoneSchedulingService._is_time_in_campaign_window(
            lead_local_time, campaign
        ):
            return False
        
        # Check if lead has specific call time preferences
        if lead.best_call_time_start and lead.best_call_time_end:
            current_time = lead_local_time.time()
            
            if lead.best_call_time_start <= lead.best_call_time_end:
                # Same day window (e.g., 9:00 AM - 5:00 PM)
                if not (lead.best_call_time_start <= current_time <= lead.best_call_time_end):
                    return False
            else:
                # Cross midnight window (e.g., 10:00 PM - 6:00 AM)
                if not (current_time >= lead.best_call_time_start or 
                       current_time <= lead.best_call_time_end):
                    return False
        
        # Check do_not_call_after restriction
        if lead.do_not_call_after and current_utc > lead.do_not_call_after:
            return False
        
        return True
    
    @staticmethod
    def _is_time_in_campaign_window(local_datetime, campaign) -> bool:
        """
        Check if a local datetime is within campaign business hours.
        
        Args:
            local_datetime: datetime in lead's local timezone
            campaign: Campaign object
            
        Returns:
            bool: True if time is within business hours
        """
        # Check day of week
        weekday = local_datetime.weekday()  # 0 = Monday, 6 = Sunday
        
        day_flags = [
            campaign.monday,    # 0
            campaign.tuesday,   # 1 
            campaign.wednesday, # 2
            campaign.thursday,  # 3
            campaign.friday,    # 4
            campaign.saturday,  # 5
            campaign.sunday,    # 6
        ]
        
        if not day_flags[weekday]:
            return False
        
        # Check time of day
        current_time = local_datetime.time()
        
        if campaign.start_time <= campaign.end_time:
            # Same day window
            return campaign.start_time <= current_time <= campaign.end_time
        else:
            # Cross midnight window
            return current_time >= campaign.start_time or current_time <= campaign.end_time
    
    @staticmethod
    def get_next_callable_time(lead, campaign=None):
        """
        Calculate the next time this lead can be called.
        
        Args:
            lead: Lead object
            campaign: Campaign object (uses lead.campaign if not provided)
            
        Returns:
            datetime: Next callable time in UTC, or None if never callable
        """
        import pytz
        from django.utils import timezone
        from datetime import datetime, timedelta
        
        if campaign is None:
            campaign = lead.campaign
        
        # If lead is callable now, return current time
        if TimezoneSchedulingService.is_lead_callable_now(lead, campaign):
            return timezone.now()
        
        try:
            lead_tz = pytz.timezone(lead.timezone)
        except (pytz.UnknownTimeZoneError, AttributeError):
            try:
                lead_tz = pytz.timezone(campaign.timezone_name)
            except pytz.UnknownTimeZoneError:
                lead_tz = pytz.UTC
        
        current_utc = timezone.now()
        current_local = current_utc.astimezone(lead_tz)
        
        # Start checking from tomorrow if we're past business hours today
        check_date = current_local.date()
        max_days_ahead = 14  # Don't look more than 2 weeks ahead
        
        for days_ahead in range(max_days_ahead):
            check_datetime = lead_tz.localize(
                datetime.combine(check_date + timedelta(days=days_ahead), 
                               campaign.start_time)
            )
            
            # Convert to UTC for comparison
            check_utc = check_datetime.astimezone(pytz.UTC).replace(tzinfo=None)
            
            if check_utc > current_utc.replace(tzinfo=None):
                # Create a temporary lead with this future time for checking
                if TimezoneSchedulingService._is_time_in_campaign_window(
                    check_datetime, campaign
                ):
                    return timezone.make_aware(check_utc)
        
        return None  # No callable time found within the next 2 weeks
    
    @staticmethod
    def filter_callable_leads(leads, campaign=None):
        """
        Filter a list of leads to only include those callable right now.
        
        Args:
            leads: List or QuerySet of Lead objects
            campaign: Campaign object (uses lead.campaign if not provided)
            
        Returns:
            List[Lead]: Filtered list of callable leads
        """
        callable_leads = []
        
        for lead in leads:
            if TimezoneSchedulingService.is_lead_callable_now(lead, campaign):
                callable_leads.append(lead)
        
        return callable_leads
    
    @staticmethod
    def schedule_lead_callback(lead, callback_minutes_from_now=60):
        """
        Schedule a lead for callback at the next appropriate time.
        
        Args:
            lead: Lead object to schedule
            callback_minutes_from_now: Minimum minutes from now for the callback
            
        Returns:
            datetime: Scheduled callback time in UTC
        """
        from django.utils import timezone
        from datetime import timedelta
        
        earliest_callback = timezone.now() + timedelta(minutes=callback_minutes_from_now)
        next_callable = TimezoneSchedulingService.get_next_callable_time(lead)
        
        if next_callable and next_callable > earliest_callback:
            scheduled_time = next_callable
        else:
            scheduled_time = earliest_callback
        
        # Update lead with callback time
        lead.callback_datetime = scheduled_time
        lead.status = 'callback'
        lead.save(update_fields=['callback_datetime', 'status', 'updated_at'])
        
        return scheduled_time
