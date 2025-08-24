"""
Answer Machine Detection (AMD) Processor

This module handles answer machine detection integration for the predictive dialing system.
It processes AMD results, updates call and lead statuses, and provides AMD analytics.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple
from django.utils import timezone
from django.db.models import Count, Avg, Q, Min, Max
from django.db import transaction
from django.contrib.auth import get_user_model

from .models import Campaign, CampaignStatistics
from calls.models import CallTask
from leads.models import Lead

User = get_user_model()
logger = logging.getLogger(__name__)


class AMDConfiguration:
    """
    Configuration settings for Answer Machine Detection processing.
    """
    
    # AMD confidence thresholds
    HIGH_CONFIDENCE_THRESHOLD = 0.85
    MEDIUM_CONFIDENCE_THRESHOLD = 0.70
    LOW_CONFIDENCE_THRESHOLD = 0.50
    
    # AMD result handling strategies
    AMD_STRATEGIES = {
        'human': {
            'connect_to_agent': True,
            'update_lead_status': 'contacted',
            'schedule_callback': False,
            'increment_attempts': True
        },
        'machine_high_confidence': {
            'connect_to_agent': False,
            'update_lead_status': 'answering_machine',
            'schedule_callback': True,
            'increment_attempts': True,
            'callback_delay_hours': 4
        },
        'machine_medium_confidence': {
            'connect_to_agent': False,
            'update_lead_status': 'answering_machine',
            'schedule_callback': True,
            'increment_attempts': True,
            'callback_delay_hours': 6
        },
        'machine_low_confidence': {
            'connect_to_agent': True,  # Connect due to uncertainty
            'update_lead_status': 'contacted',
            'schedule_callback': False,
            'increment_attempts': True,
            'flag_for_review': True
        },
        'unknown': {
            'connect_to_agent': True,  # Default to connecting
            'update_lead_status': 'contacted',
            'schedule_callback': False,
            'increment_attempts': True,
            'flag_for_review': True
        }
    }


class AMDProcessor:
    """
    Processes Answer Machine Detection results and updates call/lead status accordingly.
    """
    
    def __init__(self, campaign: Campaign):
        self.campaign = campaign
        self.config = AMDConfiguration()
        
    def process_amd_result(self, call_task: CallTask, amd_result: str, 
                          amd_confidence: Optional[float] = None) -> Dict[str, Any]:
        """
        Process AMD result for a call task and take appropriate actions.
        
        Args:
            call_task: CallTask instance to process
            amd_result: AMD result ('human', 'machine', 'unknown')
            amd_confidence: Confidence level (0.0 to 1.0)
            
        Returns:
            Dict with processing results and actions taken
        """
        logger.info(f"Processing AMD result for call {call_task.task_id}: "
                   f"{amd_result} (confidence: {amd_confidence})")
        
        # Validate inputs
        if amd_result not in ['human', 'machine', 'unknown']:
            logger.warning(f"Invalid AMD result '{amd_result}' for call {call_task.task_id}")
            amd_result = 'unknown'
            
        if amd_confidence is None:
            amd_confidence = 0.0
            
        # Update call task with AMD results
        with transaction.atomic():
            call_task.amd_result = amd_result
            call_task.amd_confidence = Decimal(str(amd_confidence))
            call_task.save(update_fields=['amd_result', 'amd_confidence'])
            
            # Determine processing strategy
            strategy_key = self._get_strategy_key(amd_result, amd_confidence)
            strategy = self.config.AMD_STRATEGIES[strategy_key]
            
            # Process according to strategy
            result = self._execute_strategy(call_task, strategy, strategy_key)
            
            # Update statistics
            self._update_amd_statistics(amd_result, amd_confidence, strategy_key)
            
            logger.info(f"AMD processing completed for call {call_task.task_id}: "
                       f"strategy={strategy_key}, connect_agent={result['connect_to_agent']}")
            
            return result
    
    def _get_strategy_key(self, amd_result: str, amd_confidence: float) -> str:
        """
        Determine which strategy to use based on AMD result and confidence.
        
        Args:
            amd_result: AMD detection result
            amd_confidence: Confidence level
            
        Returns:
            Strategy key for AMD_STRATEGIES
        """
        if amd_result == 'human':
            return 'human'
        elif amd_result == 'machine':
            if amd_confidence >= self.config.HIGH_CONFIDENCE_THRESHOLD:
                return 'machine_high_confidence'
            elif amd_confidence >= self.config.MEDIUM_CONFIDENCE_THRESHOLD:
                return 'machine_medium_confidence'
            else:
                return 'machine_low_confidence'
        else:  # unknown
            return 'unknown'
    
    def _execute_strategy(self, call_task: CallTask, strategy: Dict[str, Any], 
                         strategy_key: str) -> Dict[str, Any]:
        """
        Execute the determined AMD processing strategy.
        
        Args:
            call_task: CallTask to process
            strategy: Strategy configuration
            strategy_key: Strategy identifier
            
        Returns:
            Dict with execution results
        """
        actions_taken = []
        
        # Update lead status if specified
        if strategy.get('update_lead_status'):
            old_status = call_task.lead.status
            call_task.lead.status = strategy['update_lead_status']
            call_task.lead.save(update_fields=['status'])
            actions_taken.append(f"Updated lead status: {old_status} -> {strategy['update_lead_status']}")
        
        # Schedule callback if needed
        if strategy.get('schedule_callback'):
            callback_delay = strategy.get('callback_delay_hours', 2)
            callback_time = timezone.now() + timedelta(hours=callback_delay)
            
            # Create callback task (this would integrate with callback scheduling system)
            self._schedule_callback(call_task.lead, callback_time, f"AMD: {strategy_key}")
            actions_taken.append(f"Scheduled callback in {callback_delay} hours")
        
        # Flag for review if needed
        if strategy.get('flag_for_review'):
            # This could create a review task or add to a queue
            actions_taken.append("Flagged for manual review")
        
        # Increment attempts if specified
        if strategy.get('increment_attempts'):
            call_task.lead.attempts += 1
            call_task.lead.last_call_attempt = timezone.now()
            call_task.lead.save(update_fields=['attempts', 'last_call_attempt'])
            actions_taken.append("Incremented lead attempts")
        
        return {
            'call_task_id': str(call_task.task_id),
            'amd_result': call_task.amd_result,
            'amd_confidence': float(call_task.amd_confidence),
            'strategy_used': strategy_key,
            'connect_to_agent': strategy.get('connect_to_agent', False),
            'actions_taken': actions_taken,
            'processed_at': timezone.now().isoformat()
        }
    
    def _schedule_callback(self, lead: Lead, callback_time: datetime, reason: str):
        """
        Schedule a callback for the lead (placeholder for callback system integration).
        
        Args:
            lead: Lead to schedule callback for
            callback_time: When to schedule the callback
            reason: Reason for the callback
        """
        # This would integrate with a callback scheduling system
        # For now, we'll update the lead with callback information
        lead.status = 'callback'
        lead.callback_datetime = callback_time
        lead.notes = f"{lead.notes or ''}\nAMD Callback scheduled: {reason}".strip()
        lead.save(update_fields=['status', 'callback_datetime', 'notes'])
        
        logger.info(f"Scheduled callback for lead {lead.id} at {callback_time} ({reason})")
    
    def _update_amd_statistics(self, amd_result: str, amd_confidence: float, strategy_key: str):
        """
        Update campaign AMD statistics.
        
        Args:
            amd_result: AMD result
            amd_confidence: Confidence level
            strategy_key: Strategy used
        """
        # This could update campaign statistics or create AMD-specific statistics
        # For now, we'll log the information
        logger.debug(f"AMD statistics update for {self.campaign.name}: "
                    f"result={amd_result}, confidence={amd_confidence:.2f}, strategy={strategy_key}")


class AMDAnalyzer:
    """
    Analyzes AMD performance and provides insights for optimization.
    """
    
    def __init__(self, campaign: Campaign):
        self.campaign = campaign
        
    def get_amd_statistics(self, days: int = 7) -> Dict[str, Any]:
        """
        Get AMD statistics for the campaign over the specified period.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Dict with AMD statistics
        """
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # Get all call tasks with AMD results from the period
        amd_calls = CallTask.objects.filter(
            campaign=self.campaign,
            created_at__gte=cutoff_date,
            amd_result__isnull=False
        )
        
        total_amd_calls = amd_calls.count()
        
        if total_amd_calls == 0:
            return {
                'period_days': days,
                'total_calls_with_amd': 0,
                'amd_enabled': self.campaign.enable_amd,
                'message': 'No AMD data available for the specified period'
            }
        
        # Calculate result distribution
        result_counts = {
            'human': amd_calls.filter(amd_result='human').count(),
            'machine': amd_calls.filter(amd_result='machine').count(),
            'unknown': amd_calls.filter(amd_result='unknown').count()
        }
        
        # Calculate percentages
        result_percentages = {
            result: (count / total_amd_calls) * 100 
            for result, count in result_counts.items()
        }
        
        # Calculate confidence statistics
        confidence_stats = amd_calls.aggregate(
            avg_confidence=Avg('amd_confidence'),
            min_confidence=Min('amd_confidence'),
            max_confidence=Max('amd_confidence')
        )
        
        # Analyze confidence distribution
        high_confidence = amd_calls.filter(amd_confidence__gte=0.85).count()
        medium_confidence = amd_calls.filter(
            amd_confidence__gte=0.70, amd_confidence__lt=0.85
        ).count()
        low_confidence = amd_calls.filter(amd_confidence__lt=0.70).count()
        
        # Calculate effectiveness metrics
        human_calls = amd_calls.filter(amd_result='human')
        machine_calls = amd_calls.filter(amd_result='machine')
        
        # Analyze outcomes (this would need additional data about call outcomes)
        connected_humans = human_calls.filter(state='completed').count()
        avoided_machines = machine_calls.count()
        
        return {
            'period_days': days,
            'analysis_date': timezone.now().isoformat(),
            'total_calls_with_amd': total_amd_calls,
            'amd_enabled': self.campaign.enable_amd,
            'result_distribution': {
                'counts': result_counts,
                'percentages': result_percentages
            },
            'confidence_statistics': {
                'average': float(confidence_stats['avg_confidence'] or 0),
                'minimum': float(confidence_stats['min_confidence'] or 0),
                'maximum': float(confidence_stats['max_confidence'] or 0),
                'distribution': {
                    'high_confidence': high_confidence,
                    'medium_confidence': medium_confidence,
                    'low_confidence': low_confidence
                }
            },
            'effectiveness_metrics': {
                'connected_humans': connected_humans,
                'avoided_machines': avoided_machines,
                'human_connection_rate': (connected_humans / max(1, human_calls.count())) * 100,
                'machine_detection_rate': (avoided_machines / total_amd_calls) * 100
            }
        }
    
    def analyze_amd_accuracy(self, days: int = 30) -> Dict[str, Any]:
        """
        Analyze AMD accuracy by looking at patterns and potential false positives/negatives.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Dict with accuracy analysis
        """
        cutoff_date = timezone.now() - timedelta(days=days)
        
        amd_calls = CallTask.objects.filter(
            campaign=self.campaign,
            created_at__gte=cutoff_date,
            amd_result__isnull=False
        )
        
        # Analyze confidence vs outcome patterns
        # This is a simplified analysis - in practice, you'd need more sophisticated metrics
        high_confidence_humans = amd_calls.filter(
            amd_result='human',
            amd_confidence__gte=0.85
        )
        
        high_confidence_machines = amd_calls.filter(
            amd_result='machine',
            amd_confidence__gte=0.85
        )
        
        low_confidence_calls = amd_calls.filter(amd_confidence__lt=0.70)
        
        # Identify potential issues
        issues = []
        
        if low_confidence_calls.count() / max(1, amd_calls.count()) > 0.3:
            issues.append("High percentage of low-confidence AMD results")
        
        machine_rate = amd_calls.filter(amd_result='machine').count() / max(1, amd_calls.count())
        if machine_rate > 0.7:
            issues.append("Very high machine detection rate - possible over-detection")
        elif machine_rate < 0.1:
            issues.append("Very low machine detection rate - possible under-detection")
        
        return {
            'analysis_period': days,
            'total_analyzed_calls': amd_calls.count(),
            'high_confidence_results': {
                'human': high_confidence_humans.count(),
                'machine': high_confidence_machines.count()
            },
            'low_confidence_calls': low_confidence_calls.count(),
            'potential_issues': issues,
            'recommendations': self._generate_amd_recommendations(amd_calls, issues)
        }
    
    def _generate_amd_recommendations(self, amd_calls, issues: List[str]) -> List[str]:
        """Generate recommendations based on AMD analysis."""
        recommendations = []
        
        if "High percentage of low-confidence AMD results" in issues:
            recommendations.append("Consider adjusting AMD sensitivity settings")
            recommendations.append("Review AMD model training or configuration")
        
        if "Very high machine detection rate" in issues:
            recommendations.append("Investigate potential AMD over-sensitivity")
            recommendations.append("Review recent changes to AMD configuration")
        
        if "Very low machine detection rate" in issues:
            recommendations.append("Consider increasing AMD sensitivity")
            recommendations.append("Verify AMD system is functioning properly")
        
        # General recommendations
        total_calls = amd_calls.count()
        if total_calls > 100:
            recommendations.append("AMD system has sufficient data for analysis")
        else:
            recommendations.append("Collect more AMD data for comprehensive analysis")
        
        if not recommendations:
            recommendations.append("AMD performance appears normal")
            recommendations.append("Continue monitoring for optimization opportunities")
        
        return recommendations


class AMDIntegrationService:
    """
    Service that integrates AMD processing with the predictive dialing system.
    """
    
    def __init__(self, campaign: Campaign):
        self.campaign = campaign
        self.processor = AMDProcessor(campaign)
        self.analyzer = AMDAnalyzer(campaign)
        
    def handle_amd_webhook(self, call_id: str, amd_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle AMD webhook from telephony system.
        
        Args:
            call_id: Unique call identifier
            amd_data: AMD result data from telephony system
            
        Returns:
            Dict with handling results
        """
        try:
            # Find the call task
            call_task = CallTask.objects.get(pbx_call_id=call_id)
            
            # Extract AMD information
            amd_result = amd_data.get('result', 'unknown').lower()
            amd_confidence = float(amd_data.get('confidence', 0.0))
            
            # Process the AMD result
            result = self.processor.process_amd_result(call_task, amd_result, amd_confidence)
            
            # Return result with connection decision
            return {
                'success': True,
                'call_task_id': str(call_task.task_id),
                'connect_to_agent': result['connect_to_agent'],
                'amd_result': amd_result,
                'amd_confidence': amd_confidence,
                'actions_taken': result['actions_taken']
            }
            
        except CallTask.DoesNotExist:
            logger.error(f"CallTask not found for call_id: {call_id}")
            return {
                'success': False,
                'error': 'Call task not found',
                'call_id': call_id
            }
        except Exception as e:
            logger.error(f"Error processing AMD webhook for call {call_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'call_id': call_id
            }
    
    def should_enable_amd_for_call(self, call_task: CallTask) -> bool:
        """
        Determine if AMD should be enabled for a specific call.
        
        Args:
            call_task: CallTask to evaluate
            
        Returns:
            Boolean indicating if AMD should be enabled
        """
        # Check campaign AMD setting
        if not self.campaign.enable_amd:
            return False
        
        # Check lead history - if we've already detected answering machine, 
        # we might want to skip AMD on subsequent attempts
        if call_task.lead.status == 'answering_machine':
            return False
        
        # Could add more sophisticated logic here based on:
        # - Time of day (less likely to get machines during business hours)
        # - Lead demographics
        # - Previous campaign performance
        
        return True
    
    def get_amd_performance_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive AMD performance report.
        
        Returns:
            Dict with AMD performance metrics and analysis
        """
        statistics_7d = self.analyzer.get_amd_statistics(days=7)
        statistics_30d = self.analyzer.get_amd_statistics(days=30)
        accuracy_analysis = self.analyzer.analyze_amd_accuracy(days=30)
        
        return {
            'campaign_name': self.campaign.name,
            'amd_enabled': self.campaign.enable_amd,
            'report_generated': timezone.now().isoformat(),
            'statistics': {
                'last_7_days': statistics_7d,
                'last_30_days': statistics_30d
            },
            'accuracy_analysis': accuracy_analysis,
            'overall_recommendations': self._generate_overall_recommendations(
                statistics_7d, statistics_30d, accuracy_analysis
            )
        }
    
    def _generate_overall_recommendations(self, stats_7d: Dict[str, Any], 
                                        stats_30d: Dict[str, Any], 
                                        accuracy: Dict[str, Any]) -> List[str]:
        """Generate overall AMD recommendations."""
        recommendations = []
        
        if not self.campaign.enable_amd:
            recommendations.append("Consider enabling AMD to improve efficiency")
            return recommendations
        
        # Check if we have sufficient data
        if stats_7d.get('total_calls_with_amd', 0) < 50:
            recommendations.append("Increase call volume to get better AMD insights")
        
        # Add accuracy recommendations
        recommendations.extend(accuracy.get('recommendations', []))
        
        return recommendations
