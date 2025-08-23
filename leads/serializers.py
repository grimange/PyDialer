"""
Serializers for the leads app.

This module contains basic DRF serializers for lead management functionality.
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from campaigns.models import Campaign
from .models import Lead, Disposition, DispositionCode, LeadNote, LeadImportBatch

User = get_user_model()


class LeadSerializer(serializers.ModelSerializer):
    """
    Basic serializer for Lead model.
    """
    campaign_name = serializers.CharField(source='campaign.name', read_only=True)
    full_name = serializers.CharField(read_only=True)
    assigned_agent_name = serializers.CharField(source='assigned_agent.get_full_name', read_only=True)

    class Meta:
        model = Lead
        fields = [
            'id', 'campaign', 'campaign_name', 'first_name', 'last_name',
            'full_name', 'email', 'phone', 'alt_phone', 'address',
            'city', 'state', 'zip_code', 'country', 'status',
            'priority', 'timezone', 'attempts', 'last_attempt_at',
            'next_attempt_at', 'assigned_agent', 'assigned_agent_name',
            'callback_datetime', 'is_dnc', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'attempts']

    def validate_phone(self, value):
        """
        Validate phone number format.
        """
        if value and not value.replace('+', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', '').isdigit():
            raise serializers.ValidationError("Phone number must contain only digits and valid formatting characters.")
        return value


class DispositionCodeSerializer(serializers.ModelSerializer):
    """
    Basic serializer for DispositionCode model.
    """
    class Meta:
        model = DispositionCode
        fields = [
            'id', 'code', 'name', 'description', 'category',
            'is_system_code', 'requires_callback', 'is_contact',
            'is_sale', 'order', 'is_active'
        ]
        read_only_fields = ['id']


class DispositionSerializer(serializers.ModelSerializer):
    """
    Basic serializer for Disposition model.
    """
    lead_name = serializers.CharField(source='lead.get_full_name', read_only=True)
    agent_name = serializers.CharField(source='agent.get_full_name', read_only=True)
    disposition_code_name = serializers.CharField(source='disposition_code.name', read_only=True)

    class Meta:
        model = Disposition
        fields = [
            'id', 'lead', 'lead_name', 'agent', 'agent_name',
            'disposition_code', 'disposition_code_name', 'notes',
            'callback_datetime', 'wrapup_seconds', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class LeadNoteSerializer(serializers.ModelSerializer):
    """
    Basic serializer for LeadNote model.
    """
    lead_name = serializers.CharField(source='lead.get_full_name', read_only=True)
    agent_name = serializers.CharField(source='agent.get_full_name', read_only=True)

    class Meta:
        model = LeadNote
        fields = [
            'id', 'lead', 'lead_name', 'agent', 'agent_name',
            'note', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class LeadImportBatchSerializer(serializers.ModelSerializer):
    """
    Serializer for LeadImportBatch model with bulk import functionality.
    """
    uploaded_by_name = serializers.CharField(source='uploaded_by.get_full_name', read_only=True)
    campaign_name = serializers.CharField(source='campaign.name', read_only=True)
    success_rate = serializers.SerializerMethodField()

    class Meta:
        model = LeadImportBatch
        fields = [
            'id', 'campaign', 'campaign_name', 'file_name', 'file_size',
            'total_records', 'processed_records', 'successful_records',
            'failed_records', 'status', 'error_log', 'uploaded_by',
            'uploaded_by_name', 'uploaded_at', 'completed_at', 'success_rate'
        ]
        read_only_fields = [
            'id', 'file_size', 'processed_records', 'successful_records',
            'failed_records', 'status', 'error_log', 'uploaded_at',
            'completed_at'
        ]

    def get_success_rate(self, obj):
        """Calculate and return success rate percentage"""
        return obj.get_success_rate()


class LeadBulkImportSerializer(serializers.Serializer):
    """
    Serializer for handling bulk lead import via file upload.
    """
    campaign = serializers.PrimaryKeyRelatedField(
        queryset=Campaign.objects.all(),  # Default queryset - will be filtered in view
        required=True,
        help_text="Campaign to import leads into"
    )
    file = serializers.FileField(
        required=True,
        help_text="CSV file containing lead data"
    )
    skip_duplicates = serializers.BooleanField(
        default=True,
        help_text="Skip leads with duplicate phone numbers"
    )
    update_existing = serializers.BooleanField(
        default=False,
        help_text="Update existing leads if found"
    )

    def validate_file(self, value):
        """
        Validate uploaded file format and size.
        """
        if not value.name.endswith('.csv'):
            raise serializers.ValidationError("Only CSV files are supported")
        
        # Check file size (limit to 50MB)
        if value.size > 50 * 1024 * 1024:
            raise serializers.ValidationError("File size cannot exceed 50MB")
        
        return value

    def validate(self, attrs):
        """
        Validate bulk import parameters.
        """
        if attrs.get('skip_duplicates') and attrs.get('update_existing'):
            raise serializers.ValidationError({
                'update_existing': 'Cannot update existing leads when skip_duplicates is enabled'
            })
        
        return attrs


class LeadListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for lead lists with essential fields only.
    """
    campaign_name = serializers.CharField(source='campaign.name', read_only=True)
    full_name = serializers.CharField(read_only=True)
    assigned_agent_name = serializers.CharField(source='assigned_agent.get_full_name', read_only=True)

    class Meta:
        model = Lead
        fields = [
            'id', 'campaign', 'campaign_name', 'full_name', 'phone',
            'email', 'status', 'priority', 'attempts', 'last_attempt_at',
            'next_attempt_at', 'assigned_agent_name', 'callback_datetime',
            'is_dnc', 'created_at'
        ]
