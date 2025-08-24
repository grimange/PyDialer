"""
Serializers for the calls app.

This module contains basic DRF serializers for call management functionality.
"""

from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import CallTask, CallDetailRecord, Recording, DNCList, ComplianceAuditLog, Disposition

User = get_user_model()


class CallTaskSerializer(serializers.ModelSerializer):
    """
    Comprehensive serializer for CallTask model.
    """
    campaign_name = serializers.CharField(source='campaign.name', read_only=True)
    lead_phone = serializers.CharField(source='lead.phone', read_only=True)
    agent_name = serializers.CharField(source='agent.get_full_name', read_only=True)
    state_display = serializers.CharField(source='get_state_display', read_only=True)
    call_type_display = serializers.CharField(source='get_call_type_display', read_only=True)
    amd_result_display = serializers.CharField(source='get_amd_result_display', read_only=True)

    class Meta:
        model = CallTask
        fields = [
            'id', 'task_id', 'campaign', 'campaign_name', 'lead', 'lead_phone',
            'agent', 'agent_name', 'call_type', 'call_type_display', 'state', 'state_display',
            'phone_number', 'caller_id', 'pbx_call_id', 'channel_name', 'pbx_server',
            'created_at', 'queued_at', 'dialing_started_at', 'answered_at', 
            'connected_at', 'completed_at', 'dial_delay', 'ring_duration', 
            'call_duration', 'talk_time', 'hangup_reason', 'hangup_by',
            'amd_result', 'amd_result_display', 'amd_confidence', 'priority', 
            'retry_count', 'max_retries', 'next_retry_at', 'last_error', 'error_count'
        ]
        read_only_fields = [
            'id', 'task_id', 'created_at', 'queued_at', 'dialing_started_at', 
            'answered_at', 'connected_at', 'completed_at', 'dial_delay', 
            'ring_duration', 'call_duration', 'talk_time', 'error_count'
        ]


class CallDetailRecordSerializer(serializers.ModelSerializer):
    """
    Comprehensive serializer for CallDetailRecord model.
    """
    campaign_name = serializers.CharField(source='campaign.name', read_only=True)
    agent_name = serializers.CharField(source='agent.get_full_name', read_only=True)
    lead_phone = serializers.CharField(source='lead.phone', read_only=True)
    hangup_party_display = serializers.CharField(source='get_hangup_party_display', read_only=True)
    audio_quality_display = serializers.CharField(source='get_audio_quality_display', read_only=True)

    class Meta:
        model = CallDetailRecord
        fields = [
            'id', 'cdr_id', 'call_task', 'campaign', 'campaign_name', 
            'lead', 'lead_phone', 'agent', 'agent_name', 'pbx_call_id', 
            'unique_id', 'linked_id', 'caller_number', 'called_number', 
            'caller_id_name', 'call_date', 'call_time', 'answer_time', 'end_time',
            'total_duration', 'billable_duration', 'ring_duration', 'talk_duration',
            'hold_duration', 'wrap_duration', 'call_result', 'hangup_cause',
            'hangup_party', 'hangup_party_display', 'amd_result', 'amd_duration',
            'call_quality_score', 'audio_quality_problems', 'caller_location',
            'called_location', 'timezone_offset', 'cost_per_minute', 'total_cost',
            'billing_increment', 'channel_name', 'destination_channel', 'source_ip',
            'user_agent', 'recording_consent', 'recording_url', 'server_name',
            'archive_date', 'is_archived', 'created_at'
        ]
        read_only_fields = [
            'id', 'cdr_id', 'call_date', 'call_time', 'answer_time', 'end_time',
            'total_duration', 'billable_duration', 'ring_duration', 'talk_duration',
            'hold_duration', 'wrap_duration', 'amd_duration', 'total_cost', 'created_at'
        ]


class RecordingSerializer(serializers.ModelSerializer):
    """
    Comprehensive serializer for Recording model.
    """
    call_info = serializers.CharField(source='call_task.__str__', read_only=True)
    cdr_info = serializers.CharField(source='cdr.__str__', read_only=True)
    campaign_name = serializers.CharField(source='campaign.name', read_only=True)
    agent_name = serializers.CharField(source='agent.get_full_name', read_only=True)
    recording_type_display = serializers.CharField(source='get_recording_type_display', read_only=True)
    storage_type_display = serializers.CharField(source='get_storage_type_display', read_only=True)
    audio_quality_display = serializers.CharField(source='get_audio_quality_display', read_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = Recording
        fields = [
            'id', 'recording_id', 'call_task', 'call_info', 'cdr', 'cdr_info',
            'campaign', 'campaign_name', 'agent', 'agent_name', 'recording_type',
            'recording_type_display', 'filename', 'file_format', 'file_size',
            'duration', 'storage_type', 'storage_type_display', 'storage_path',
            'storage_url', 'bucket_name', 'audio_quality', 'audio_quality_display',
            'sample_rate', 'bit_rate', 'requires_consent', 'consent_obtained',
            'retention_policy', 'delete_after', 'access_count', 'last_accessed_at',
            'last_accessed_by', 'is_processed', 'is_transcribed', 'transcription_text',
            'processing_error', 'recorded_at', 'created_at', 'updated_at', 'download_url'
        ]
        read_only_fields = [
            'id', 'recording_id', 'file_size', 'access_count', 'last_accessed_at',
            'last_accessed_by', 'is_processed', 'processing_error', 'recorded_at',
            'created_at', 'updated_at', 'download_url'
        ]

    def get_download_url(self, obj):
        """Get secure download URL for recording"""
        return obj.get_download_url()


class DNCListSerializer(serializers.ModelSerializer):
    """
    Serializer for DNC List management.
    """
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    list_type_display = serializers.CharField(source='get_list_type_display', read_only=True)

    class Meta:
        model = DNCList
        fields = [
            'id', 'list_name', 'list_type', 'list_type_display', 'description',
            'source_file', 'last_updated', 'update_frequency', 'total_numbers',
            'active_numbers', 'is_active', 'created_at', 'created_by', 'created_by_name'
        ]
        read_only_fields = ['id', 'last_updated', 'total_numbers', 'active_numbers', 'created_at']


class ComplianceAuditLogSerializer(serializers.ModelSerializer):
    """
    Serializer for Compliance Audit Log entries.
    """
    audit_type_display = serializers.CharField(source='get_audit_type_display', read_only=True)
    severity_display = serializers.CharField(source='get_severity_display', read_only=True)
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.get_full_name', read_only=True)

    class Meta:
        model = ComplianceAuditLog
        fields = [
            'id', 'audit_id', 'audit_type', 'audit_type_display', 'event_name',
            'description', 'severity', 'severity_display', 'campaign', 'lead',
            'call_task', 'recording', 'user', 'user_name', 'ip_address',
            'user_agent', 'session_id', 'before_data', 'after_data', 'additional_data',
            'requires_review', 'reviewed', 'reviewed_by', 'reviewed_by_name',
            'reviewed_at', 'event_timestamp', 'created_at'
        ]
        read_only_fields = [
            'id', 'audit_id', 'event_timestamp', 'created_at', 'reviewed_at'
        ]


class DispositionSerializer(serializers.ModelSerializer):
    """
    Comprehensive serializer for Disposition model.
    """
    call_task_info = serializers.CharField(source='call_task.__str__', read_only=True)
    agent_name = serializers.CharField(source='agent.get_full_name', read_only=True)
    campaign_name = serializers.CharField(source='call_task.campaign.name', read_only=True)
    lead_phone = serializers.CharField(source='call_task.lead.phone', read_only=True)
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    callback_type_display = serializers.CharField(source='get_callback_type_display', read_only=True)
    callback_priority_display = serializers.CharField(source='get_callback_priority_display', read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.get_full_name', read_only=True)

    class Meta:
        model = Disposition
        fields = [
            'id', 'disposition_id', 'call_task', 'call_task_info', 'cdr',
            'disposition_code', 'disposition_name', 'category', 'category_display',
            'agent', 'agent_name', 'campaign_name', 'lead_phone',
            'disposition_time', 'wrap_up_time', 'notes', 'is_final', 'requires_followup',
            'schedule_callback', 'callback_date', 'callback_time', 'callback_type',
            'callback_type_display', 'callback_notes', 'callback_priority', 
            'callback_priority_display', 'best_time_start', 'best_time_end',
            'best_days', 'timezone_preference', 'sale_amount', 'products_sold',
            'commission_amount', 'quality_score', 'compliance_flags',
            'requires_supervisor_review', 'supervisor_reviewed', 'reviewed_by',
            'reviewed_by_name', 'reviewed_at', 'is_valid', 'validation_errors',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'disposition_id', 'disposition_time', 'supervisor_reviewed',
            'reviewed_at', 'is_valid', 'validation_errors', 'created_at', 'updated_at'
        ]

    def validate(self, data):
        """Custom validation for disposition data"""
        # Check callback scheduling consistency
        if data.get('schedule_callback') and not data.get('callback_date'):
            raise serializers.ValidationError({
                'callback_date': 'Callback date is required when scheduling callback.'
            })
        
        # Check sale information consistency
        if data.get('category') == 'sale' and not data.get('sale_amount'):
            raise serializers.ValidationError({
                'sale_amount': 'Sale amount should be specified for sales dispositions.'
            })
        
        # Check DNC compliance
        if data.get('category') == 'dnc' and data.get('schedule_callback'):
            raise serializers.ValidationError({
                'schedule_callback': 'Cannot schedule callback for DNC disposition.'
            })
        
        return data

    def create(self, validated_data):
        """Create disposition with automatic validation"""
        disposition = super().create(validated_data)
        disposition.validate_disposition()
        disposition.save()
        return disposition

    def update(self, instance, validated_data):
        """Update disposition with automatic validation"""
        disposition = super().update(instance, validated_data)
        disposition.validate_disposition()
        disposition.save()
        return disposition
