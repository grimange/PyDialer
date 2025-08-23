"""
Serializers for the campaigns app.

This module contains DRF serializers for campaign management functionality.
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from agents.models import AgentSkill
from .models import (
    Campaign, 
    CampaignAgentAssignment, 
    CampaignSchedule, 
    CampaignStatistics
)

User = get_user_model()


class CampaignSerializer(serializers.ModelSerializer):
    """
    Serializer for Campaign model with comprehensive field coverage.
    """
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    updated_by_name = serializers.CharField(source='updated_by.get_full_name', read_only=True)
    active_agents_count = serializers.SerializerMethodField()
    leads_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Campaign
        fields = [
            'id', 'name', 'description', 'campaign_type', 'status',
            'dial_method', 'pacing_ratio', 'drop_rate_threshold',
            'caller_id', 'caller_name', 'recording_enabled', 
            'amd_enabled', 'amd_sensitivity', 'max_attempts',
            'retry_delay_minutes', 'recycle_hours', 'start_date',
            'end_date', 'start_time', 'end_time', 'timezone',
            'max_concurrent_calls', 'priority', 'is_active',
            'created_at', 'updated_at', 'created_by', 'updated_by',
            'created_by_name', 'updated_by_name', 'active_agents_count',
            'leads_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_active_agents_count(self, obj):
        """Get count of active agents assigned to this campaign"""
        return obj.campaignagentassignment_set.filter(is_active=True).count()

    def get_leads_count(self, obj):
        """Get count of leads associated with this campaign"""
        # This will be implemented when leads models are connected
        return 0

    def validate(self, attrs):
        """
        Validate campaign data with business rules
        """
        # Validate pacing ratio
        if attrs.get('pacing_ratio', 0) < 1.0 or attrs.get('pacing_ratio', 0) > 5.0:
            raise serializers.ValidationError({
                'pacing_ratio': 'Pacing ratio must be between 1.0 and 5.0'
            })

        # Validate drop rate threshold
        if attrs.get('drop_rate_threshold', 0) < 0 or attrs.get('drop_rate_threshold', 0) > 100:
            raise serializers.ValidationError({
                'drop_rate_threshold': 'Drop rate threshold must be between 0 and 100'
            })

        # Validate date range
        start_date = attrs.get('start_date')
        end_date = attrs.get('end_date')
        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError({
                'end_date': 'End date must be after start date'
            })

        return attrs


class CampaignAgentAssignmentSerializer(serializers.ModelSerializer):
    """
    Serializer for CampaignAgentAssignment model.
    """
    agent_name = serializers.CharField(source='agent.get_full_name', read_only=True)
    campaign_name = serializers.CharField(source='campaign.name', read_only=True)
    assigned_by_name = serializers.CharField(source='assigned_by.get_full_name', read_only=True)

    class Meta:
        model = CampaignAgentAssignment
        fields = [
            'id', 'campaign', 'campaign_name', 'agent', 'agent_name',
            'priority', 'max_calls_per_hour', 'skill_requirements',
            'is_active', 'assigned_at', 'assigned_by', 'assigned_by_name'
        ]
        read_only_fields = ['id', 'assigned_at']

    def validate(self, attrs):
        """
        Validate agent assignment with business rules
        """
        campaign = attrs.get('campaign')
        agent = attrs.get('agent')
        
        # Check if agent is already assigned to this campaign
        if campaign and agent:
            existing = CampaignAgentAssignment.objects.filter(
                campaign=campaign, 
                agent=agent,
                is_active=True
            ).exclude(pk=self.instance.pk if self.instance else None)
            
            if existing.exists():
                raise serializers.ValidationError({
                    'agent': 'Agent is already assigned to this campaign'
                })

        return attrs


class CampaignScheduleSerializer(serializers.ModelSerializer):
    """
    Serializer for CampaignSchedule model.
    """
    campaign_name = serializers.CharField(source='campaign.name', read_only=True)

    class Meta:
        model = CampaignSchedule
        fields = [
            'id', 'campaign', 'campaign_name', 'day_of_week',
            'start_time', 'end_time', 'timezone', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, attrs):
        """
        Validate schedule with business rules
        """
        start_time = attrs.get('start_time')
        end_time = attrs.get('end_time')
        
        if start_time and end_time and start_time >= end_time:
            raise serializers.ValidationError({
                'end_time': 'End time must be after start time'
            })

        return attrs


class CampaignStatisticsSerializer(serializers.ModelSerializer):
    """
    Serializer for CampaignStatistics model - mostly read-only.
    """
    campaign_name = serializers.CharField(source='campaign.name', read_only=True)

    class Meta:
        model = CampaignStatistics
        fields = [
            'id', 'campaign', 'campaign_name', 'date', 'calls_attempted',
            'calls_connected', 'calls_dropped', 'calls_answered',
            'total_talk_time', 'average_talk_time', 'leads_contacted',
            'appointments_set', 'sales_made', 'current_drop_rate'
        ]
        read_only_fields = [
            'id', 'date', 'calls_attempted', 'calls_connected',
            'calls_dropped', 'calls_answered', 'total_talk_time',
            'average_talk_time', 'leads_contacted', 'appointments_set',
            'sales_made', 'current_drop_rate'
        ]


class CampaignListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for campaign lists.
    """
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    active_agents_count = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = [
            'id', 'name', 'campaign_type', 'status', 'dial_method',
            'is_active', 'created_at', 'created_by_name', 'active_agents_count'
        ]

    def get_active_agents_count(self, obj):
        """Get count of active agents assigned to this campaign"""
        return obj.campaignagentassignment_set.filter(is_active=True).count()
