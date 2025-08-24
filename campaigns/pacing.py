"""
Pacing Calculator for Predictive Dialing

This module implements sophisticated pacing ratio calculations based on agent availability,
historical performance, and real-time metrics for optimal call center efficiency.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Tuple, Optional
from django.utils import timezone
from django.db.models import Count, Avg, Q
from django.contrib.auth import get_user_model

from .models import Campaign, CampaignStatistics
from calls.models import CallTask
from agents.models import AgentStatus

User = get_user_model()
logger = logging.getLogger(__name__)


class AgentAvailabilityTracker:
    """
    Tracks agent availability patterns and provides predictions for pacing calculations.
    """
    
    def __init__(self, campaign: Campaign):
        self.campaign = campaign
        
    def get_current_agent_metrics(self) -> Dict[str, int]:
        """
        Get real-time agent metrics for the campaign.
        
        Returns:
            Dict with current agent status counts
        """
        assigned_agents = self.campaign.assigned_agents.filter(is_active=True)
        
        # Get agent status counts
        status_counts = {
            'total_assigned': assigned_agents.count(),
            'logged_in': 0,
            'available': 0,
            'on_call': 0,
            'wrap_up': 0,
            'break': 0,
            'offline': 0
        }
        
        # Count agents by status
        for agent in assigned_agents:
            if hasattr(agent, 'current_status') and agent.current_status:
                status = agent.current_status.status
                if status == 'available':
                    status_counts['available'] += 1
                    status_counts['logged_in'] += 1
                elif status in ['on_call', 'connected']:
                    status_counts['on_call'] += 1
                    status_counts['logged_in'] += 1
                elif status == 'wrap_up':
                    status_counts['wrap_up'] += 1
                    status_counts['logged_in'] += 1
                elif status in ['break', 'lunch']:
                    status_counts['break'] += 1
                    status_counts['logged_in'] += 1
                else:
                    status_counts['offline'] += 1
            else:
                status_counts['offline'] += 1
        
        return status_counts
    
    def get_agent_utilization_history(self, hours: int = 24) -> Dict[str, float]:
        """
        Calculate agent utilization over the specified time period.
        
        Args:
            hours: Number of hours to look back
            
        Returns:
            Dict with utilization metrics
        """
        cutoff_time = timezone.now() - timedelta(hours=hours)
        
        # Get call tasks from the period
        recent_calls = CallTask.objects.filter(
            campaign=self.campaign,
            created_at__gte=cutoff_time,
            state__in=['completed', 'abandoned', 'failed']
        )
        
        total_calls = recent_calls.count()
        answered_calls = recent_calls.filter(answered_at__isnull=False).count()
        
        # Calculate average call and wrap times
        avg_metrics = recent_calls.filter(
            call_duration__isnull=False
        ).aggregate(
            avg_call_duration=Avg('call_duration'),
            avg_talk_time=Avg('talk_time')
        )
        
        avg_call_minutes = 0.0
        avg_talk_minutes = 0.0
        
        if avg_metrics['avg_call_duration']:
            avg_call_minutes = avg_metrics['avg_call_duration'].total_seconds() / 60.0
        
        if avg_metrics['avg_talk_time']:
            avg_talk_minutes = avg_metrics['avg_talk_time'].total_seconds() / 60.0
        
        # Calculate contact rate
        contact_rate = (answered_calls / max(1, total_calls)) * 100
        
        # Calculate agent productivity metrics
        agent_metrics = self.get_current_agent_metrics()
        available_agents = agent_metrics['available']
        
        # Estimate agent utilization
        if available_agents > 0 and avg_call_minutes > 0:
            # Theoretical calls per agent per hour
            calls_per_agent_hour = 60 / (avg_call_minutes + self.campaign.wrap_up_time / 60.0)
            utilization = min(100.0, (total_calls / max(1, available_agents) / hours) / calls_per_agent_hour * 100)
        else:
            utilization = 0.0
        
        return {
            'total_calls': total_calls,
            'answered_calls': answered_calls,
            'contact_rate': contact_rate,
            'avg_call_minutes': avg_call_minutes,
            'avg_talk_minutes': avg_talk_minutes,
            'utilization': utilization
        }
    
    def predict_agent_availability(self, minutes_ahead: int = 30) -> Dict[str, float]:
        """
        Predict agent availability for the next specified minutes.
        
        Args:
            minutes_ahead: Minutes to predict ahead
            
        Returns:
            Dict with availability predictions
        """
        current_metrics = self.get_current_agent_metrics()
        historical_data = self.get_agent_utilization_history(hours=168)  # Last week
        
        # Simple prediction based on current state and historical patterns
        current_available = current_metrics['available']
        current_on_call = current_metrics['on_call']
        
        # Estimate how many agents will become available
        avg_call_minutes = historical_data['avg_call_minutes']
        
        if avg_call_minutes > 0:
            # Estimate agents finishing calls in the prediction window
            agents_becoming_available = current_on_call * (minutes_ahead / avg_call_minutes)
            predicted_available = current_available + min(agents_becoming_available, current_on_call)
        else:
            predicted_available = current_available
        
        return {
            'current_available': current_available,
            'predicted_available': predicted_available,
            'prediction_confidence': min(100.0, historical_data['total_calls'] / 10.0),  # More calls = higher confidence
            'minutes_ahead': minutes_ahead
        }


class PacingCalculator:
    """
    Advanced pacing ratio calculator that optimizes dialing based on agent availability
    and performance metrics.
    """
    
    def __init__(self, campaign: Campaign):
        self.campaign = campaign
        self.availability_tracker = AgentAvailabilityTracker(campaign)
        self.statistics = getattr(campaign, 'statistics', None)
        
    def calculate_optimal_pacing_ratio(self) -> Tuple[float, Dict[str, any]]:
        """
        Calculate the optimal pacing ratio based on current conditions.
        
        Returns:
            Tuple of (pacing_ratio, calculation_details)
        """
        # Get current agent metrics
        agent_metrics = self.availability_tracker.get_current_agent_metrics()
        historical_data = self.availability_tracker.get_agent_utilization_history()
        
        # Base ratio from campaign configuration
        base_ratio = float(self.campaign.pacing_ratio)
        
        # Adjustment factors
        contact_rate_factor = self._calculate_contact_rate_factor(historical_data['contact_rate'])
        drop_rate_factor = self._calculate_drop_rate_factor()
        agent_availability_factor = self._calculate_agent_availability_factor(agent_metrics)
        utilization_factor = self._calculate_utilization_factor(historical_data['utilization'])
        time_of_day_factor = self._calculate_time_of_day_factor()
        
        # Calculate adjusted ratio
        adjusted_ratio = (
            base_ratio * 
            contact_rate_factor * 
            drop_rate_factor * 
            agent_availability_factor * 
            utilization_factor * 
            time_of_day_factor
        )
        
        # Apply safety bounds
        min_ratio = 0.5
        max_ratio = min(10.0, agent_metrics['total_assigned'] * 2.0)  # Never more than 2x total agents
        optimal_ratio = max(min_ratio, min(adjusted_ratio, max_ratio))
        
        calculation_details = {
            'base_ratio': base_ratio,
            'contact_rate_factor': contact_rate_factor,
            'drop_rate_factor': drop_rate_factor,
            'agent_availability_factor': agent_availability_factor,
            'utilization_factor': utilization_factor,
            'time_of_day_factor': time_of_day_factor,
            'adjusted_ratio': adjusted_ratio,
            'optimal_ratio': optimal_ratio,
            'agent_metrics': agent_metrics,
            'historical_data': historical_data
        }
        
        logger.info(f"Calculated optimal pacing ratio for {self.campaign.name}: {optimal_ratio:.2f} "
                   f"(base: {base_ratio}, factors: contact={contact_rate_factor:.2f}, "
                   f"drop={drop_rate_factor:.2f}, availability={agent_availability_factor:.2f})")
        
        return optimal_ratio, calculation_details
    
    def _calculate_contact_rate_factor(self, contact_rate: float) -> float:
        """
        Calculate pacing adjustment based on contact rate.
        
        Higher contact rate = need lower pacing ratio
        Lower contact rate = need higher pacing ratio
        """
        if contact_rate >= 50.0:
            # High contact rate, reduce pacing
            return 0.8 + (contact_rate - 50) / 100 * 0.1  # 0.8 to 0.9
        elif contact_rate >= 30.0:
            # Medium contact rate, slight adjustment
            return 0.9 + (contact_rate - 30) / 20 * 0.1  # 0.9 to 1.0
        elif contact_rate >= 15.0:
            # Low contact rate, increase pacing
            return 1.0 + (30 - contact_rate) / 15 * 0.3  # 1.0 to 1.3
        else:
            # Very low contact rate, significantly increase pacing
            return 1.3 + (15 - contact_rate) / 15 * 0.4  # 1.3 to 1.7
    
    def _calculate_drop_rate_factor(self) -> float:
        """
        Calculate pacing adjustment based on current drop rate vs SLA.
        """
        current_drop_rate = self.campaign.current_drop_rate
        sla_drop_rate = self.campaign.drop_sla
        
        if current_drop_rate > sla_drop_rate * 1.2:
            # Significantly over SLA, reduce pacing aggressively
            return 0.5
        elif current_drop_rate > sla_drop_rate:
            # Over SLA, reduce pacing
            excess_ratio = current_drop_rate / sla_drop_rate
            return max(0.6, 1.0 - (excess_ratio - 1.0) * 0.4)
        elif current_drop_rate < sla_drop_rate * 0.5:
            # Well under SLA, can increase pacing
            return min(1.3, 1.0 + (sla_drop_rate * 0.5 - current_drop_rate) / (sla_drop_rate * 0.5) * 0.3)
        else:
            # Within acceptable range
            return 1.0
    
    def _calculate_agent_availability_factor(self, agent_metrics: Dict[str, int]) -> float:
        """
        Calculate pacing adjustment based on current agent availability.
        """
        available = agent_metrics['available']
        total_logged_in = agent_metrics['logged_in']
        
        if total_logged_in == 0:
            return 0.0  # No agents, no calls
        
        availability_ratio = available / total_logged_in
        
        if availability_ratio >= 0.8:
            # High availability, can increase pacing
            return 1.2
        elif availability_ratio >= 0.6:
            # Good availability, normal pacing
            return 1.0
        elif availability_ratio >= 0.4:
            # Moderate availability, slight reduction
            return 0.9
        elif availability_ratio >= 0.2:
            # Low availability, reduce pacing
            return 0.7
        else:
            # Very low availability, minimal pacing
            return 0.5
    
    def _calculate_utilization_factor(self, utilization: float) -> float:
        """
        Calculate pacing adjustment based on agent utilization.
        """
        if utilization >= 90.0:
            # Very high utilization, reduce pacing
            return 0.8
        elif utilization >= 75.0:
            # High utilization, slight reduction
            return 0.9
        elif utilization >= 60.0:
            # Good utilization, maintain pacing
            return 1.0
        elif utilization >= 40.0:
            # Moderate utilization, increase pacing
            return 1.1
        else:
            # Low utilization, increase pacing significantly
            return 1.3
    
    def _calculate_time_of_day_factor(self) -> float:
        """
        Calculate pacing adjustment based on time of day patterns.
        """
        current_time = timezone.now().time()
        hour = current_time.hour
        
        # Peak hours (typically 10 AM - 2 PM and 6 PM - 8 PM)
        if (10 <= hour <= 14) or (18 <= hour <= 20):
            return 1.1  # Slightly more aggressive during peak hours
        
        # Off-peak but still business hours
        elif 8 <= hour <= 17:
            return 1.0  # Normal pacing
        
        # Early morning or evening
        elif 7 <= hour <= 9 or 17 <= hour <= 19:
            return 0.95  # Slightly more conservative
        
        # Very early or late
        else:
            return 0.8  # Conservative pacing for unusual hours
    
    def get_recommended_calls_per_agent(self) -> Tuple[float, Dict[str, any]]:
        """
        Get recommended number of concurrent calls per available agent.
        
        Returns:
            Tuple of (calls_per_agent, calculation_details)
        """
        optimal_ratio, details = self.calculate_optimal_pacing_ratio()
        agent_metrics = details['agent_metrics']
        
        available_agents = agent_metrics['available']
        
        if available_agents == 0:
            return 0.0, details
        
        # Calculate calls per agent
        calls_per_agent = optimal_ratio
        
        # Adjust based on agent experience/skill level if available
        # This could be enhanced with agent skill/experience data
        
        details['calls_per_agent'] = calls_per_agent
        details['available_agents'] = available_agents
        details['total_recommended_calls'] = available_agents * calls_per_agent
        
        return calls_per_agent, details
    
    def should_adjust_pacing(self) -> Tuple[bool, str, float]:
        """
        Determine if pacing should be adjusted and by how much.
        
        Returns:
            Tuple of (should_adjust, reason, new_ratio)
        """
        optimal_ratio, details = self.calculate_optimal_pacing_ratio()
        current_ratio = float(self.campaign.pacing_ratio)
        
        # Define adjustment threshold (5% difference)
        threshold = 0.05
        ratio_diff = abs(optimal_ratio - current_ratio) / current_ratio
        
        if ratio_diff > threshold:
            if optimal_ratio > current_ratio:
                reason = f"Increase pacing due to {self._get_primary_adjustment_reason(details, 'increase')}"
            else:
                reason = f"Decrease pacing due to {self._get_primary_adjustment_reason(details, 'decrease')}"
            
            return True, reason, optimal_ratio
        
        return False, "Pacing within acceptable range", current_ratio
    
    def _get_primary_adjustment_reason(self, details: Dict[str, any], direction: str) -> str:
        """Get the primary reason for pacing adjustment."""
        factors = {
            'contact_rate': details['contact_rate_factor'],
            'drop_rate': details['drop_rate_factor'],
            'agent_availability': details['agent_availability_factor'],
            'utilization': details['utilization_factor']
        }
        
        # Find the factor that deviates most from 1.0
        max_deviation = 0
        primary_factor = 'general_conditions'
        
        for factor_name, factor_value in factors.items():
            deviation = abs(factor_value - 1.0)
            if deviation > max_deviation:
                max_deviation = deviation
                primary_factor = factor_name
        
        reason_map = {
            'contact_rate': 'contact rate patterns',
            'drop_rate': 'drop rate SLA compliance',
            'agent_availability': 'agent availability changes',
            'utilization': 'agent utilization levels'
        }
        
        return reason_map.get(primary_factor, 'general_conditions')


class PacingMonitor:
    """
    Monitor pacing performance and provide recommendations.
    """
    
    def __init__(self, campaign: Campaign):
        self.campaign = campaign
        self.calculator = PacingCalculator(campaign)
    
    def get_pacing_performance_report(self) -> Dict[str, any]:
        """
        Generate a comprehensive pacing performance report.
        
        Returns:
            Dict with pacing performance metrics and recommendations
        """
        # Get current calculations
        optimal_ratio, calculation_details = self.calculator.calculate_optimal_pacing_ratio()
        calls_per_agent, agent_details = self.calculator.get_recommended_calls_per_agent()
        should_adjust, reason, new_ratio = self.calculator.should_adjust_pacing()
        
        # Get historical performance
        historical_data = self.calculator.availability_tracker.get_agent_utilization_history(hours=24)
        
        # Predict future availability
        availability_prediction = self.calculator.availability_tracker.predict_agent_availability(minutes_ahead=60)
        
        report = {
            'campaign_name': self.campaign.name,
            'current_pacing_ratio': float(self.campaign.pacing_ratio),
            'optimal_pacing_ratio': optimal_ratio,
            'calls_per_agent': calls_per_agent,
            'should_adjust': should_adjust,
            'adjustment_reason': reason,
            'recommended_ratio': new_ratio,
            'calculation_details': calculation_details,
            'historical_performance': historical_data,
            'availability_prediction': availability_prediction,
            'timestamp': timezone.now().isoformat()
        }
        
        return report
    
    def log_pacing_adjustment(self, old_ratio: float, new_ratio: float, reason: str):
        """
        Log pacing ratio adjustments for audit and analysis.
        
        Args:
            old_ratio: Previous pacing ratio
            new_ratio: New pacing ratio
            reason: Reason for adjustment
        """
        logger.info(f"Pacing adjustment for {self.campaign.name}: {old_ratio:.2f} -> {new_ratio:.2f}. Reason: {reason}")
        
        # Here you could also save to a PacingAdjustmentLog model if needed
        # for historical tracking and analysis
