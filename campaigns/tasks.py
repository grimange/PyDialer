"""
Celery tasks for predictive dialing operations.

This module contains background tasks for processing campaigns, initiating calls,
and managing the predictive dialing engine.
"""

import logging
from typing import Dict, List
from celery import shared_task
from django.utils import timezone
from django.db import transaction

from .models import Campaign, CampaignStatistics
from .services import PredictiveDialingService, PredictiveDialingManager, LeadRecyclingService
from calls.models import CallTask
from leads.models import Lead

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_predictive_dialing(self):
    """
    Main task for processing predictive dialing across all active campaigns.
    
    This task runs periodically (typically every 30-60 seconds) to:
    1. Check all active campaigns
    2. Calculate calls needed based on agent availability
    3. Queue calls for dialing
    
    Returns:
        dict: Summary of calls initiated per campaign
    """
    try:
        logger.info("Starting predictive dialing process")
        
        # Get system capacity overview
        capacity = PredictiveDialingManager.get_system_capacity()
        logger.info(f"System capacity: {capacity}")
        
        # Process all campaigns
        results = PredictiveDialingManager.process_all_campaigns()
        
        # Schedule actual call tasks
        total_calls_scheduled = 0
        for campaign_name, calls_to_make in results.items():
            if calls_to_make > 0:
                # Schedule call initiation for this campaign
                schedule_campaign_calls.delay(campaign_name, calls_to_make)
                total_calls_scheduled += calls_to_make
        
        logger.info(f"Predictive dialing completed. Scheduled {total_calls_scheduled} calls across {len(results)} campaigns")
        
        return {
            'success': True,
            'total_calls_scheduled': total_calls_scheduled,
            'campaigns_processed': len(results),
            'campaign_results': results,
            'system_capacity': capacity
        }
        
    except Exception as exc:
        logger.error(f"Error in predictive dialing process: {exc}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=3)
def schedule_campaign_calls(self, campaign_name: str, calls_to_make: int):
    """
    Schedule call tasks for a specific campaign.
    
    Args:
        campaign_name: Name of the campaign
        calls_to_make: Number of calls to schedule
        
    Returns:
        dict: Result summary with call tasks created
    """
    try:
        # Get campaign
        campaign = Campaign.objects.get(name=campaign_name)
        dialer = PredictiveDialingService(campaign)
        
        # Get dialable leads
        leads = dialer.get_dialable_leads(limit=calls_to_make)
        
        if not leads:
            logger.warning(f"No dialable leads found for campaign {campaign_name}")
            return {'success': True, 'calls_created': 0, 'reason': 'no_leads'}
        
        # Create call tasks
        call_tasks_created = []
        
        with transaction.atomic():
            for lead in leads[:calls_to_make]:
                # Create call task
                call_task = CallTask.objects.create(
                    lead=lead,
                    campaign=campaign,
                    phone_number=lead.phone_number,
                    caller_id=campaign.caller_id,
                    call_type='outbound',
                    state='pending',
                    priority=lead.priority or 5
                )
                call_tasks_created.append(call_task.task_id)
                
                # Update lead status
                lead.status = 'dialing'
                lead.attempts += 1
                lead.last_call_attempt = timezone.now()
                lead.save(update_fields=['status', 'attempts', 'last_call_attempt'])
        
        # Queue call tasks for dialing
        for task_id in call_tasks_created:
            initiate_call.delay(str(task_id))
        
        logger.info(f"Created {len(call_tasks_created)} call tasks for campaign {campaign_name}")
        
        return {
            'success': True,
            'calls_created': len(call_tasks_created),
            'call_task_ids': call_tasks_created
        }
        
    except Campaign.DoesNotExist:
        logger.error(f"Campaign {campaign_name} not found")
        return {'success': False, 'error': 'campaign_not_found'}
        
    except Exception as exc:
        logger.error(f"Error scheduling calls for campaign {campaign_name}: {exc}")
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


@shared_task(bind=True, max_retries=5)
def initiate_call(self, call_task_id: str):
    """
    Initiate a specific call task.
    
    This task handles the actual call initiation process:
    1. Update call task state to 'queued'
    2. Interface with telephony system (Asterisk/PBX)
    3. Monitor call progress
    
    Args:
        call_task_id: UUID of the call task to initiate
        
    Returns:
        dict: Result of call initiation
    """
    try:
        # Get call task
        call_task = CallTask.objects.get(task_id=call_task_id)
        
        # Update state to queued
        call_task.update_state('queued')
        
        # TODO: Interface with telephony system
        # This is where integration with Asterisk/PBX would happen
        # For now, we'll simulate the process
        
        logger.info(f"Call task {call_task_id} queued for dialing to {call_task.phone_number}")
        
        # In a real implementation, this would:
        # 1. Send call origination request to Asterisk via ARI
        # 2. Monitor call progress via AMI events
        # 3. Update call task state based on call progress
        
        # For now, schedule call monitoring
        monitor_call_progress.delay(call_task_id)
        
        return {
            'success': True,
            'call_task_id': call_task_id,
            'phone_number': call_task.phone_number,
            'state': call_task.state
        }
        
    except CallTask.DoesNotExist:
        logger.error(f"Call task {call_task_id} not found")
        return {'success': False, 'error': 'call_task_not_found'}
        
    except Exception as exc:
        logger.error(f"Error initiating call {call_task_id}: {exc}")
        raise self.retry(exc=exc, countdown=15 * (2 ** self.request.retries))


@shared_task(bind=True)
def monitor_call_progress(self, call_task_id: str):
    """
    Monitor call progress and handle call events.
    
    This task would typically be triggered by PBX events in a real implementation.
    For now, it serves as a placeholder for call monitoring logic.
    
    Args:
        call_task_id: UUID of the call task to monitor
    """
    try:
        call_task = CallTask.objects.get(task_id=call_task_id)
        
        # TODO: Implement actual call monitoring
        # This would listen to AMI/ARI events from Asterisk
        # and update call task state accordingly
        
        logger.info(f"Monitoring call progress for task {call_task_id}")
        
        return {
            'success': True,
            'call_task_id': call_task_id,
            'monitoring': True
        }
        
    except CallTask.DoesNotExist:
        logger.error(f"Call task {call_task_id} not found for monitoring")
        return {'success': False, 'error': 'call_task_not_found'}


@shared_task(bind=True)
def update_campaign_statistics(self, campaign_id: int):
    """
    Update real-time campaign statistics.
    
    This task runs periodically to update campaign metrics used by
    the predictive dialing algorithms.
    
    Args:
        campaign_id: ID of the campaign to update
    """
    try:
        campaign = Campaign.objects.get(id=campaign_id)
        
        # Get or create statistics record
        statistics, created = CampaignStatistics.objects.get_or_create(
            campaign=campaign
        )
        
        # Update real-time metrics
        statistics.active_calls = CallTask.objects.filter(
            campaign=campaign,
            state__in=['dialing', 'ringing', 'connected']
        ).count()
        
        statistics.agents_logged_in = campaign.assigned_agents.filter(
            is_active=True
        ).count()
        
        statistics.agents_available = campaign.get_available_agents().count()
        
        statistics.agents_on_call = campaign.assigned_agents.filter(
            current_status__status__in=['on_call', 'connected']
        ).count()
        
        # Update daily statistics
        today = timezone.now().date()
        if statistics.last_reset_date != today:
            statistics.reset_daily_stats()
        
        # Calculate today's metrics from call tasks
        today_calls = CallTask.objects.filter(
            campaign=campaign,
            created_at__date=today
        )
        
        statistics.calls_attempted_today = today_calls.count()
        statistics.calls_completed_today = today_calls.filter(
            state='completed'
        ).count()
        statistics.calls_answered_today = today_calls.filter(
            answered_at__isnull=False
        ).count()
        statistics.calls_dropped_today = today_calls.filter(
            state='abandoned'
        ).count()
        
        # Update rates
        if statistics.calls_attempted_today > 0:
            statistics.contact_rate_today = (
                statistics.calls_answered_today / statistics.calls_attempted_today * 100
            )
        
        statistics.save()
        
        logger.debug(f"Updated statistics for campaign {campaign.name}")
        
        return {
            'success': True,
            'campaign_id': campaign_id,
            'statistics': {
                'active_calls': statistics.active_calls,
                'agents_available': statistics.agents_available,
                'calls_attempted_today': statistics.calls_attempted_today,
                'contact_rate_today': float(statistics.contact_rate_today)
            }
        }
        
    except Campaign.DoesNotExist:
        logger.error(f"Campaign {campaign_id} not found")
        return {'success': False, 'error': 'campaign_not_found'}
        
    except Exception as exc:
        logger.error(f"Error updating statistics for campaign {campaign_id}: {exc}")
        return {'success': False, 'error': str(exc)}


@shared_task(bind=True)
def cleanup_completed_calls(self, hours_old: int = 24):
    """
    Clean up completed call tasks older than specified hours.
    
    This task helps maintain database performance by archiving or
    removing old completed call tasks.
    
    Args:
        hours_old: Age threshold in hours for cleanup
    """
    try:
        from datetime import timedelta
        
        cutoff_time = timezone.now() - timedelta(hours=hours_old)
        
        # Find completed call tasks older than cutoff
        old_tasks = CallTask.objects.filter(
            state__in=['completed', 'failed', 'abandoned'],
            completed_at__lt=cutoff_time
        )
        
        count = old_tasks.count()
        
        if count > 0:
            # In a real implementation, you might want to archive these
            # instead of deleting them outright
            old_tasks.delete()
            logger.info(f"Cleaned up {count} completed call tasks older than {hours_old} hours")
        
        return {
            'success': True,
            'tasks_cleaned': count,
            'cutoff_time': cutoff_time.isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Error cleaning up completed calls: {exc}")
        return {'success': False, 'error': str(exc)}


@shared_task(bind=True)
def reset_daily_statistics(self):
    """
    Reset daily statistics for all campaigns.
    
    This task should be run daily (typically at midnight) to reset
    daily statistics counters.
    """
    try:
        reset_count = 0
        
        for statistics in CampaignStatistics.objects.all():
            statistics.reset_daily_stats()
            reset_count += 1
        
        logger.info(f"Reset daily statistics for {reset_count} campaigns")
        
        return {
            'success': True,
            'campaigns_reset': reset_count
        }
        
    except Exception as exc:
        logger.error(f"Error resetting daily statistics: {exc}")
        return {'success': False, 'error': str(exc)}


@shared_task(bind=True)
def recycle_campaign_leads(self, campaign_id: int = None):
    """
    Recycle leads based on campaign rules.
    
    This task processes leads that have been in certain statuses (no_answer, busy, 
    disconnected) for a specified period and resets them for another attempt.
    
    Args:
        campaign_id: Specific campaign ID to process, or None to process all active campaigns
    """
    try:
        # Get campaigns to process
        if campaign_id:
            campaigns = Campaign.objects.filter(id=campaign_id, status='active')
        else:
            campaigns = Campaign.objects.filter(status='active', recycle_inactive_leads=True)
        
        total_recycled = 0
        campaigns_processed = 0
        
        for campaign in campaigns:
            logger.info(f"Processing lead recycling for campaign: {campaign.name}")
            
            # Use the LeadRecyclingService for business logic
            recycling_service = LeadRecyclingService(campaign)
            
            if recycling_service.can_recycle_now():
                results = recycling_service.process_campaign_recycling(batch_size=100)
                campaign_total = sum(results.values())
                total_recycled += campaign_total
                campaigns_processed += 1
                
                logger.info(f"Recycled {campaign_total} leads for campaign {campaign.name}")
                logger.debug(f"Recycling breakdown for {campaign.name}: {results}")
            else:
                logger.info(f"Skipping campaign {campaign.name} - recycling not allowed at this time")
        
        logger.info(f"Lead recycling completed. Total recycled: {total_recycled}")
        return {
            'success': True,
            'total_recycled': total_recycled,
            'campaigns_processed': campaigns_processed
        }
        
    except Exception as exc:
        logger.error(f"Error recycling leads: {exc}")
        return {'success': False, 'error': str(exc)}
