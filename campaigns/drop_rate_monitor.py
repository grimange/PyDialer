"""
Drop Rate Monitor for Predictive Dialing

This module implements comprehensive drop rate monitoring, SLA compliance tracking,
and automatic pacing adjustments to maintain acceptable abandonment rates.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Tuple, Optional, Any
from django.utils import timezone
from django.db.models import Count, Avg, Q
from django.db import transaction
from django.contrib.auth import get_user_model

from .models import Campaign, CampaignStatistics
from calls.models import CallTask
from .pacing import PacingCalculator

User = get_user_model()
logger = logging.getLogger(__name__)


class DropRateCalculator:
    """
    Calculates drop rates using various time windows and methodologies.
    """
    
    def __init__(self, campaign: Campaign):
        self.campaign = campaign
        
    def calculate_real_time_drop_rate(self, minutes: int = 60) -> Dict[str, Any]:
        """
        Calculate drop rate over the last N minutes for real-time monitoring.
        
        Args:
            minutes: Time window in minutes
            
        Returns:
            Dict with drop rate metrics
        """
        cutoff_time = timezone.now() - timedelta(minutes=minutes)
        
        # Get call tasks from the specified time window
        recent_calls = CallTask.objects.filter(
            campaign=self.campaign,
            created_at__gte=cutoff_time
        )
        
        total_calls = recent_calls.count()
        abandoned_calls = recent_calls.filter(state='abandoned').count()
        answered_calls = recent_calls.filter(answered_at__isnull=False).count()
        failed_calls = recent_calls.filter(state='failed').count()
        
        # Calculate drop rate (abandoned calls / total attempted calls)
        if total_calls > 0:
            drop_rate = (abandoned_calls / total_calls) * 100
        else:
            drop_rate = 0.0
            
        # Calculate answer rate for context
        if total_calls > 0:
            answer_rate = (answered_calls / total_calls) * 100
        else:
            answer_rate = 0.0
            
        return {
            'time_window_minutes': minutes,
            'total_calls': total_calls,
            'abandoned_calls': abandoned_calls,
            'answered_calls': answered_calls,
            'failed_calls': failed_calls,
            'drop_rate': drop_rate,
            'answer_rate': answer_rate,
            'sla_threshold': float(self.campaign.drop_sla),
            'exceeds_sla': drop_rate > float(self.campaign.drop_sla),
            'calculated_at': timezone.now().isoformat()
        }
    
    def calculate_daily_drop_rate(self, date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Calculate drop rate for a specific day.
        
        Args:
            date: Date to calculate for (defaults to today)
            
        Returns:
            Dict with daily drop rate metrics
        """
        if date is None:
            date = timezone.now().date()
        
        # Get all call tasks for the specified date
        daily_calls = CallTask.objects.filter(
            campaign=self.campaign,
            created_at__date=date
        )
        
        total_calls = daily_calls.count()
        abandoned_calls = daily_calls.filter(state='abandoned').count()
        answered_calls = daily_calls.filter(answered_at__isnull=False).count()
        completed_calls = daily_calls.filter(state='completed').count()
        
        # Calculate rates
        drop_rate = (abandoned_calls / max(1, total_calls)) * 100
        answer_rate = (answered_calls / max(1, total_calls)) * 100
        completion_rate = (completed_calls / max(1, total_calls)) * 100
        
        return {
            'date': date.isoformat(),
            'total_calls': total_calls,
            'abandoned_calls': abandoned_calls,
            'answered_calls': answered_calls,
            'completed_calls': completed_calls,
            'drop_rate': drop_rate,
            'answer_rate': answer_rate,
            'completion_rate': completion_rate,
            'sla_threshold': float(self.campaign.drop_sla),
            'exceeds_sla': drop_rate > float(self.campaign.drop_sla)
        }
    
    def calculate_rolling_average_drop_rate(self, hours: int = 24, window_size: int = 60) -> List[Dict[str, Any]]:
        """
        Calculate rolling average drop rate over time periods.
        
        Args:
            hours: Total hours to analyze
            window_size: Size of each window in minutes
            
        Returns:
            List of drop rate measurements over time
        """
        end_time = timezone.now()
        start_time = end_time - timedelta(hours=hours)
        
        measurements = []
        current_time = start_time
        
        while current_time < end_time:
            window_end = current_time + timedelta(minutes=window_size)
            
            window_calls = CallTask.objects.filter(
                campaign=self.campaign,
                created_at__gte=current_time,
                created_at__lt=window_end
            )
            
            total_calls = window_calls.count()
            abandoned_calls = window_calls.filter(state='abandoned').count()
            
            if total_calls > 0:
                drop_rate = (abandoned_calls / total_calls) * 100
            else:
                drop_rate = 0.0
                
            measurements.append({
                'timestamp': current_time.isoformat(),
                'window_end': window_end.isoformat(),
                'total_calls': total_calls,
                'abandoned_calls': abandoned_calls,
                'drop_rate': drop_rate,
                'exceeds_sla': drop_rate > float(self.campaign.drop_sla)
            })
            
            current_time = window_end
            
        return measurements


class DropRateMonitor:
    """
    Monitors drop rates in real-time and triggers adjustments when necessary.
    """
    
    def __init__(self, campaign: Campaign):
        self.campaign = campaign
        self.calculator = DropRateCalculator(campaign)
        self.pacing_calculator = PacingCalculator(campaign)
        
    def check_drop_rate_compliance(self) -> Dict[str, Any]:
        """
        Check current drop rate compliance against SLA.
        
        Returns:
            Dict with compliance status and metrics
        """
        # Check multiple time windows for comprehensive analysis
        current_hour = self.calculator.calculate_real_time_drop_rate(minutes=60)
        last_30_min = self.calculator.calculate_real_time_drop_rate(minutes=30)
        last_15_min = self.calculator.calculate_real_time_drop_rate(minutes=15)
        daily_stats = self.calculator.calculate_daily_drop_rate()
        
        # Determine overall compliance status
        violations = []
        
        if current_hour['exceeds_sla']:
            violations.append({
                'window': 'last_hour',
                'drop_rate': current_hour['drop_rate'],
                'threshold': current_hour['sla_threshold'],
                'severity': 'medium' if current_hour['drop_rate'] < current_hour['sla_threshold'] * 1.5 else 'high'
            })
            
        if last_30_min['exceeds_sla']:
            violations.append({
                'window': 'last_30_minutes',
                'drop_rate': last_30_min['drop_rate'],
                'threshold': last_30_min['sla_threshold'],
                'severity': 'medium' if last_30_min['drop_rate'] < last_30_min['sla_threshold'] * 1.5 else 'high'
            })
            
        if last_15_min['exceeds_sla'] and last_15_min['total_calls'] >= 10:  # Minimum sample size
            violations.append({
                'window': 'last_15_minutes',
                'drop_rate': last_15_min['drop_rate'],
                'threshold': last_15_min['sla_threshold'],
                'severity': 'high'  # Recent violations are more critical
            })
        
        # Determine overall severity
        if violations:
            max_severity = max(v['severity'] for v in violations)
            if 'high' in [v['severity'] for v in violations]:
                overall_severity = 'critical'
            elif len(violations) >= 2:
                overall_severity = 'high'
            else:
                overall_severity = 'medium'
        else:
            overall_severity = 'compliant'
            
        return {
            'campaign_name': self.campaign.name,
            'compliance_status': 'violation' if violations else 'compliant',
            'overall_severity': overall_severity,
            'violations': violations,
            'metrics': {
                'last_hour': current_hour,
                'last_30_minutes': last_30_min,
                'last_15_minutes': last_15_min,
                'today': daily_stats
            },
            'checked_at': timezone.now().isoformat()
        }
    
    def recommend_pacing_adjustment(self, compliance_check: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recommend pacing adjustments based on drop rate compliance.
        
        Args:
            compliance_check: Result from check_drop_rate_compliance()
            
        Returns:
            Dict with recommended actions
        """
        if compliance_check['compliance_status'] == 'compliant':
            # Check if we can increase pacing (drop rate well below SLA)
            current_drop_rate = compliance_check['metrics']['last_hour']['drop_rate']
            sla_threshold = float(self.campaign.drop_sla)
            
            if current_drop_rate < sla_threshold * 0.5:  # Well below SLA
                return {
                    'action': 'increase_pacing',
                    'reason': 'Drop rate well below SLA, can optimize efficiency',
                    'recommended_adjustment': 'increase_by_10_percent',
                    'urgency': 'low'
                }
            else:
                return {
                    'action': 'maintain_pacing',
                    'reason': 'Drop rate within acceptable range',
                    'recommended_adjustment': 'none',
                    'urgency': 'none'
                }
        
        # Handle violations
        severity = compliance_check['overall_severity']
        recent_drop_rate = compliance_check['metrics']['last_15_minutes']['drop_rate']
        
        if severity == 'critical':
            return {
                'action': 'emergency_reduction',
                'reason': 'Critical drop rate violation requiring immediate action',
                'recommended_adjustment': 'reduce_to_minimum',
                'urgency': 'immediate',
                'additional_actions': ['pause_new_calls', 'alert_supervisors']
            }
        elif severity == 'high':
            return {
                'action': 'significant_reduction',
                'reason': 'High drop rate violation',
                'recommended_adjustment': 'reduce_by_30_percent',
                'urgency': 'high',
                'additional_actions': ['alert_supervisors']
            }
        else:  # medium
            return {
                'action': 'moderate_reduction',
                'reason': 'Moderate drop rate violation',
                'recommended_adjustment': 'reduce_by_15_percent',
                'urgency': 'medium'
            }
    
    def apply_automatic_adjustment(self, recommendation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply automatic pacing adjustments based on recommendations.
        
        Args:
            recommendation: Result from recommend_pacing_adjustment()
            
        Returns:
            Dict with adjustment results
        """
        if recommendation['action'] == 'maintain_pacing':
            return {
                'adjusted': False,
                'reason': 'No adjustment needed',
                'old_ratio': float(self.campaign.pacing_ratio),
                'new_ratio': float(self.campaign.pacing_ratio)
            }
        
        old_ratio = float(self.campaign.pacing_ratio)
        new_ratio = old_ratio
        
        # Calculate new pacing ratio based on recommendation
        if recommendation['recommended_adjustment'] == 'reduce_to_minimum':
            new_ratio = 0.5  # Minimum safe ratio
        elif recommendation['recommended_adjustment'] == 'reduce_by_30_percent':
            new_ratio = max(0.5, old_ratio * 0.7)
        elif recommendation['recommended_adjustment'] == 'reduce_by_15_percent':
            new_ratio = max(0.5, old_ratio * 0.85)
        elif recommendation['recommended_adjustment'] == 'increase_by_10_percent':
            new_ratio = min(float(self.campaign.pacing_ratio) * 2, old_ratio * 1.1)
        
        # Apply the adjustment
        try:
            with transaction.atomic():
                self.campaign.pacing_ratio = Decimal(str(new_ratio))
                self.campaign.save(update_fields=['pacing_ratio'])
                
                # Log the adjustment
                logger.warning(f"Automatic pacing adjustment for {self.campaign.name}: "
                              f"{old_ratio:.2f} -> {new_ratio:.2f}. "
                              f"Reason: {recommendation['reason']}")
                
                return {
                    'adjusted': True,
                    'reason': recommendation['reason'],
                    'old_ratio': old_ratio,
                    'new_ratio': new_ratio,
                    'adjustment_type': recommendation['action'],
                    'urgency': recommendation['urgency'],
                    'timestamp': timezone.now().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Failed to apply automatic pacing adjustment for {self.campaign.name}: {e}")
            return {
                'adjusted': False,
                'reason': f'Adjustment failed: {str(e)}',
                'old_ratio': old_ratio,
                'new_ratio': old_ratio,
                'error': str(e)
            }
    
    def generate_drop_rate_alert(self, compliance_check: Dict[str, Any], 
                               adjustment_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate alert information for drop rate violations.
        
        Args:
            compliance_check: Compliance check results
            adjustment_result: Pacing adjustment results
            
        Returns:
            Dict with alert information
        """
        if compliance_check['compliance_status'] == 'compliant':
            return {'alert_required': False}
        
        severity = compliance_check['overall_severity']
        violations = compliance_check['violations']
        
        # Determine alert level and recipients
        if severity == 'critical':
            alert_level = 'CRITICAL'
            recipients = ['supervisors', 'managers', 'operations_team']
        elif severity == 'high':
            alert_level = 'HIGH'
            recipients = ['supervisors', 'managers']
        else:
            alert_level = 'MEDIUM'
            recipients = ['supervisors']
        
        # Create alert message
        message_parts = [
            f"Drop Rate Alert - {alert_level}",
            f"Campaign: {self.campaign.name}",
            f"Current SLA Threshold: {self.campaign.drop_sla}%",
            ""
        ]
        
        for violation in violations:
            message_parts.append(
                f"- {violation['window']}: {violation['drop_rate']:.1f}% "
                f"(exceeds {violation['threshold']:.1f}%)"
            )
        
        if adjustment_result.get('adjusted'):
            message_parts.extend([
                "",
                f"Automatic Action Taken:",
                f"- Pacing ratio adjusted from {adjustment_result['old_ratio']:.2f} "
                f"to {adjustment_result['new_ratio']:.2f}",
                f"- Reason: {adjustment_result['reason']}"
            ])
        
        return {
            'alert_required': True,
            'alert_level': alert_level,
            'severity': severity,
            'recipients': recipients,
            'subject': f"Drop Rate Alert - {self.campaign.name} ({alert_level})",
            'message': "\n".join(message_parts),
            'metrics': compliance_check['metrics'],
            'timestamp': timezone.now().isoformat(),
            'requires_immediate_attention': severity == 'critical'
        }


class DropRateAnalyzer:
    """
    Analyzes drop rate patterns and provides insights for optimization.
    """
    
    def __init__(self, campaign: Campaign):
        self.campaign = campaign
        self.calculator = DropRateCalculator(campaign)
        
    def analyze_drop_rate_trends(self, days: int = 7) -> Dict[str, Any]:
        """
        Analyze drop rate trends over multiple days.
        
        Args:
            days: Number of days to analyze
            
        Returns:
            Dict with trend analysis
        """
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
        
        daily_metrics = []
        current_date = start_date
        
        while current_date <= end_date:
            daily_data = self.calculator.calculate_daily_drop_rate(current_date)
            daily_metrics.append(daily_data)
            current_date += timedelta(days=1)
        
        # Calculate trends
        drop_rates = [d['drop_rate'] for d in daily_metrics]
        
        if len(drop_rates) >= 2:
            # Simple linear trend calculation
            x_values = list(range(len(drop_rates)))
            mean_x = sum(x_values) / len(x_values)
            mean_y = sum(drop_rates) / len(drop_rates)
            
            numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_values, drop_rates))
            denominator = sum((x - mean_x) ** 2 for x in x_values)
            
            if denominator != 0:
                slope = numerator / denominator
                trend_direction = 'improving' if slope < 0 else 'worsening' if slope > 0 else 'stable'
            else:
                slope = 0
                trend_direction = 'stable'
        else:
            slope = 0
            trend_direction = 'insufficient_data'
        
        # Identify patterns
        violations_count = sum(1 for d in daily_metrics if d['exceeds_sla'])
        avg_drop_rate = sum(drop_rates) / len(drop_rates) if drop_rates else 0
        max_drop_rate = max(drop_rates) if drop_rates else 0
        min_drop_rate = min(drop_rates) if drop_rates else 0
        
        return {
            'analysis_period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'days_analyzed': days
            },
            'trend_analysis': {
                'direction': trend_direction,
                'slope': slope,
                'average_drop_rate': avg_drop_rate,
                'max_drop_rate': max_drop_rate,
                'min_drop_rate': min_drop_rate,
                'sla_violations': violations_count,
                'compliance_percentage': ((days - violations_count) / days) * 100
            },
            'daily_metrics': daily_metrics,
            'recommendations': self._generate_trend_recommendations(
                trend_direction, avg_drop_rate, violations_count, days
            )
        }
    
    def _generate_trend_recommendations(self, trend_direction: str, avg_drop_rate: float, 
                                      violations_count: int, total_days: int) -> List[str]:
        """Generate recommendations based on trend analysis."""
        recommendations = []
        
        if trend_direction == 'worsening':
            recommendations.append("Drop rate trend is worsening - investigate recent changes")
            recommendations.append("Consider reviewing pacing strategy and agent training")
        
        if avg_drop_rate > float(self.campaign.drop_sla):
            recommendations.append("Average drop rate exceeds SLA - systematic review needed")
            recommendations.append("Consider more conservative pacing ratio settings")
        
        if violations_count / total_days > 0.3:  # More than 30% violation rate
            recommendations.append("Frequent SLA violations - review campaign configuration")
            recommendations.append("Consider implementing more aggressive automatic adjustments")
        
        if not recommendations:
            recommendations.append("Drop rate performance is within acceptable parameters")
            recommendations.append("Continue monitoring and consider optimizations for efficiency")
        
        return recommendations
