from django.db import models
from django.core.validators import RegexValidator, URLValidator
from django.utils import timezone
from django.contrib.auth import get_user_model
from campaigns.models import Campaign
from leads.models import Lead
import uuid

User = get_user_model()


class CallTask(models.Model):
    """
    Call task model for managing call state and queue management
    """
    CALL_STATES = [
        ('pending', 'Pending'),
        ('queued', 'Queued'),
        ('dialing', 'Dialing'),
        ('ringing', 'Ringing'),
        ('answered', 'Answered'),
        ('connected', 'Connected'),
        ('on_hold', 'On Hold'),
        ('transferring', 'Transferring'),
        ('conferenced', 'Conferenced'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('abandoned', 'Abandoned'),
        ('no_answer', 'No Answer'),
        ('busy', 'Busy'),
        ('invalid', 'Invalid Number'),
    ]

    CALL_TYPES = [
        ('outbound', 'Outbound'),
        ('inbound', 'Inbound'),
        ('callback', 'Callback'),
        ('transfer', 'Transfer'),
        ('conference', 'Conference'),
    ]

    # Unique identifier
    task_id = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    
    # Call relationships
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='call_tasks')
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='call_tasks')
    agent = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, 
                            related_name='call_tasks')
    
    # Call information
    call_type = models.CharField(max_length=20, choices=CALL_TYPES, default='outbound')
    state = models.CharField(max_length=20, choices=CALL_STATES, default='pending', db_index=True)
    
    # Phone numbers
    phone_regex = RegexValidator(regex=r'^\+?1?\d{9,15}$')
    phone_number = models.CharField(validators=[phone_regex], max_length=17)
    caller_id = models.CharField(validators=[phone_regex], max_length=17, blank=True)
    
    # PBX Integration
    pbx_call_id = models.CharField(max_length=100, blank=True, db_index=True, 
                                 help_text="PBX system call identifier")
    channel_name = models.CharField(max_length=100, blank=True)
    pbx_server = models.CharField(max_length=50, blank=True)
    
    # Call timing
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    queued_at = models.DateTimeField(null=True, blank=True)
    dialing_started_at = models.DateTimeField(null=True, blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    connected_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Call metrics
    dial_delay = models.DurationField(null=True, blank=True, help_text="Time from queue to dial")
    ring_duration = models.DurationField(null=True, blank=True)
    call_duration = models.DurationField(null=True, blank=True)
    talk_time = models.DurationField(null=True, blank=True)
    
    # Call outcome
    hangup_reason = models.CharField(max_length=100, blank=True)
    hangup_by = models.CharField(max_length=20, blank=True, 
                               choices=[('agent', 'Agent'), ('customer', 'Customer'), ('system', 'System')])
    
    # AMD (Answer Machine Detection)
    amd_result = models.CharField(max_length=20, blank=True, 
                                choices=[('human', 'Human'), ('machine', 'Machine'), ('unknown', 'Unknown')])
    amd_confidence = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    # Priority and retry
    priority = models.IntegerField(default=5, db_index=True, help_text="Priority for queue processing")
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    
    # Error handling
    last_error = models.TextField(blank=True)
    error_count = models.IntegerField(default=0)

    class Meta:
        db_table = 'call_tasks'
        ordering = ['priority', 'created_at']
        indexes = [
            models.Index(fields=['state', 'priority']),
            models.Index(fields=['campaign', 'state']),
            models.Index(fields=['agent', 'state']),
            models.Index(fields=['pbx_call_id']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Call {self.task_id} - {self.phone_number} ({self.get_state_display()})"

    def update_state(self, new_state, **kwargs):
        """Update call state with timestamp tracking"""
        old_state = self.state
        self.state = new_state
        now = timezone.now()
        
        # Set appropriate timestamps
        if new_state == 'queued':
            self.queued_at = now
        elif new_state == 'dialing':
            self.dialing_started_at = now
            if self.queued_at:
                self.dial_delay = now - self.queued_at
        elif new_state == 'answered':
            self.answered_at = now
            if self.dialing_started_at:
                self.ring_duration = now - self.dialing_started_at
        elif new_state == 'connected':
            self.connected_at = now
        elif new_state in ['completed', 'failed', 'abandoned']:
            self.completed_at = now
            
            # Calculate durations
            if self.answered_at and self.completed_at:
                self.call_duration = self.completed_at - self.answered_at
            
            # Set hangup information
            if 'hangup_reason' in kwargs:
                self.hangup_reason = kwargs['hangup_reason']
            if 'hangup_by' in kwargs:
                self.hangup_by = kwargs['hangup_by']
        
        self.save()
        return old_state

    def can_retry(self):
        """Check if call can be retried"""
        return (self.retry_count < self.max_retries and 
                self.state in ['failed', 'no_answer', 'busy'])

    def schedule_retry(self, minutes_delay=5):
        """Schedule a retry attempt"""
        if self.can_retry():
            self.next_retry_at = timezone.now() + timezone.timedelta(minutes=minutes_delay)
            self.retry_count += 1
            self.state = 'pending'
            self.save()

    def is_active(self):
        """Check if call is currently active"""
        return self.state in ['queued', 'dialing', 'ringing', 'answered', 'connected', 'on_hold']


class CallDetailRecord(models.Model):
    """
    Call Detail Records (CDR) for comprehensive call tracking and billing
    """
    # Unique identifier
    cdr_id = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    
    # Call relationships
    call_task = models.OneToOneField(CallTask, on_delete=models.CASCADE, related_name='cdr')
    campaign = models.ForeignKey(Campaign, on_delete=models.PROTECT)
    lead = models.ForeignKey(Lead, on_delete=models.PROTECT)
    agent = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)
    
    # Call identification
    pbx_call_id = models.CharField(max_length=100, db_index=True)
    unique_id = models.CharField(max_length=100, blank=True, help_text="PBX unique call identifier")
    linked_id = models.CharField(max_length=100, blank=True, help_text="Linked call for transfers")
    
    # Phone numbers
    phone_regex = RegexValidator(regex=r'^\+?1?\d{9,15}$')
    caller_number = models.CharField(validators=[phone_regex], max_length=17)
    called_number = models.CharField(validators=[phone_regex], max_length=17)
    caller_id_name = models.CharField(max_length=100, blank=True)
    
    # Call timing (comprehensive)
    call_date = models.DateField(db_index=True)
    call_time = models.TimeField()
    answer_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(db_index=True)
    
    # Duration fields
    total_duration = models.DurationField(help_text="Total call duration from dial to hangup")
    billable_duration = models.DurationField(help_text="Billable duration (answered time)")
    ring_duration = models.DurationField(null=True, blank=True)
    talk_duration = models.DurationField(null=True, blank=True)
    hold_duration = models.DurationField(null=True, blank=True)
    wrap_duration = models.DurationField(null=True, blank=True)
    
    # Call outcome and disposition
    call_result = models.CharField(max_length=50, db_index=True)
    hangup_cause = models.CharField(max_length=100, blank=True)
    hangup_party = models.CharField(max_length=20, blank=True,
                                  choices=[('caller', 'Caller'), ('called', 'Called'), ('system', 'System')])
    
    # Answer Machine Detection
    amd_result = models.CharField(max_length=20, blank=True)
    amd_duration = models.DurationField(null=True, blank=True)
    
    # Quality and metrics
    call_quality_score = models.IntegerField(null=True, blank=True, help_text="Call quality score 1-10")
    audio_quality_problems = models.TextField(blank=True)
    
    # Geographic information
    caller_location = models.CharField(max_length=100, blank=True)
    called_location = models.CharField(max_length=100, blank=True)
    timezone_offset = models.CharField(max_length=10, blank=True)
    
    # Cost and billing
    cost_per_minute = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    total_cost = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    billing_increment = models.IntegerField(default=6, help_text="Billing increment in seconds")
    
    # PBX specific fields
    channel_name = models.CharField(max_length=100, blank=True)
    destination_channel = models.CharField(max_length=100, blank=True)
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)
    
    # Compliance and recording
    recording_consent = models.BooleanField(null=True, blank=True)
    recording_url = models.URLField(blank=True)
    
    # System information
    server_name = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Data retention
    archive_date = models.DateField(null=True, blank=True)
    is_archived = models.BooleanField(default=False)

    class Meta:
        db_table = 'call_detail_records'
        ordering = ['-call_date', '-call_time']
        indexes = [
            models.Index(fields=['call_date']),
            models.Index(fields=['campaign', 'call_date']),
            models.Index(fields=['agent', 'call_date']),
            models.Index(fields=['pbx_call_id']),
            models.Index(fields=['caller_number']),
            models.Index(fields=['called_number']),
            models.Index(fields=['call_result']),
        ]

    def __str__(self):
        return f"CDR {self.cdr_id} - {self.called_number} on {self.call_date}"

    def calculate_cost(self, rate_per_minute=None):
        """Calculate call cost based on duration and rate"""
        if rate_per_minute and self.billable_duration:
            minutes = self.billable_duration.total_seconds() / 60
            # Round up to billing increment
            if self.billing_increment:
                seconds = self.billable_duration.total_seconds()
                rounded_seconds = ((seconds + self.billing_increment - 1) // self.billing_increment) * self.billing_increment
                minutes = rounded_seconds / 60
            
            self.total_cost = float(rate_per_minute) * minutes
            self.cost_per_minute = rate_per_minute
            self.save(update_fields=['total_cost', 'cost_per_minute'])

    def is_answered(self):
        """Check if call was answered"""
        return self.answer_time is not None

    def is_successful_contact(self):
        """Check if call resulted in successful contact"""
        return self.call_result in ['ANSWERED', 'COMPLETED'] and self.is_answered()


class Recording(models.Model):
    """
    Call recording metadata and storage information
    """
    RECORDING_TYPES = [
        ('full', 'Full Call'),
        ('agent_only', 'Agent Side Only'),
        ('customer_only', 'Customer Side Only'),
        ('conference', 'Conference'),
        ('whisper', 'Whisper/Monitor'),
    ]

    STORAGE_TYPES = [
        ('local', 'Local Storage'),
        ('s3', 'Amazon S3'),
        ('azure', 'Azure Blob'),
        ('gcs', 'Google Cloud Storage'),
        ('ftp', 'FTP Server'),
    ]

    # Unique identifier
    recording_id = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    
    # Call relationships
    call_task = models.ForeignKey(CallTask, on_delete=models.CASCADE, related_name='recordings')
    cdr = models.ForeignKey(CallDetailRecord, on_delete=models.CASCADE, related_name='recordings')
    campaign = models.ForeignKey(Campaign, on_delete=models.PROTECT)
    agent = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)
    
    # Recording information
    recording_type = models.CharField(max_length=20, choices=RECORDING_TYPES, default='full')
    filename = models.CharField(max_length=200, db_index=True)
    file_format = models.CharField(max_length=10, default='wav')
    file_size = models.BigIntegerField(null=True, blank=True, help_text="File size in bytes")
    duration = models.DurationField(help_text="Recording duration")
    
    # Storage information
    storage_type = models.CharField(max_length=20, choices=STORAGE_TYPES, default='local')
    storage_path = models.CharField(max_length=500, help_text="Full path to recording file")
    storage_url = models.URLField(blank=True, help_text="URL for accessing recording")
    bucket_name = models.CharField(max_length=100, blank=True, help_text="Cloud storage bucket")
    
    # Quality information
    audio_quality = models.CharField(max_length=20, blank=True, 
                                   choices=[('excellent', 'Excellent'), ('good', 'Good'), 
                                          ('fair', 'Fair'), ('poor', 'Poor')])
    sample_rate = models.IntegerField(null=True, blank=True, help_text="Audio sample rate in Hz")
    bit_rate = models.IntegerField(null=True, blank=True, help_text="Audio bit rate in kbps")
    
    # Compliance and access control
    requires_consent = models.BooleanField(default=True)
    consent_obtained = models.BooleanField(default=False)
    retention_policy = models.CharField(max_length=50, default='7_years')
    delete_after = models.DateField(null=True, blank=True)
    
    # Access tracking
    access_count = models.IntegerField(default=0)
    last_accessed_at = models.DateTimeField(null=True, blank=True)
    last_accessed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='accessed_recordings')
    
    # Processing status
    is_processed = models.BooleanField(default=False)
    is_transcribed = models.BooleanField(default=False)
    transcription_text = models.TextField(blank=True)
    processing_error = models.TextField(blank=True)
    
    # Timestamps
    recorded_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'recordings'
        ordering = ['-recorded_at']
        indexes = [
            models.Index(fields=['campaign', 'recorded_at']),
            models.Index(fields=['agent', 'recorded_at']),
            models.Index(fields=['filename']),
            models.Index(fields=['delete_after']),
        ]

    def __str__(self):
        return f"Recording {self.recording_id} - {self.filename}"

    def get_download_url(self):
        """Generate secure download URL for recording"""
        if self.storage_url:
            return self.storage_url
        # Implementation would generate signed URL for cloud storage
        return f"/recordings/download/{self.recording_id}/"

    def log_access(self, user):
        """Log recording access for compliance"""
        self.access_count += 1
        self.last_accessed_at = timezone.now()
        self.last_accessed_by = user
        self.save(update_fields=['access_count', 'last_accessed_at', 'last_accessed_by'])

    def should_be_deleted(self):
        """Check if recording should be deleted based on retention policy"""
        if self.delete_after:
            return timezone.now().date() >= self.delete_after
        return False


class DNCList(models.Model):
    """
    Do Not Call list management
    """
    LIST_TYPES = [
        ('internal', 'Internal DNC'),
        ('federal', 'Federal DNC'),
        ('state', 'State DNC'),
        ('custom', 'Custom DNC'),
    ]

    list_name = models.CharField(max_length=100, unique=True)
    list_type = models.CharField(max_length=20, choices=LIST_TYPES, default='internal')
    description = models.TextField(blank=True)
    
    # Source information
    source_file = models.CharField(max_length=200, blank=True)
    last_updated = models.DateTimeField(auto_now=True)
    update_frequency = models.CharField(max_length=50, blank=True, help_text="e.g., 'monthly', 'weekly'")
    
    # Statistics
    total_numbers = models.IntegerField(default=0)
    active_numbers = models.IntegerField(default=0)
    
    # Compliance settings
    is_active = models.BooleanField(default=True)
    applies_to_campaigns = models.ManyToManyField(Campaign, blank=True)
    
    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        db_table = 'dnc_lists'
        ordering = ['list_name']

    def __str__(self):
        return f"{self.list_name} ({self.get_list_type_display()})"

    def update_statistics(self):
        """Update DNC list statistics"""
        self.total_numbers = self.numbers.count()
        self.active_numbers = self.numbers.filter(is_active=True).count()
        self.save(update_fields=['total_numbers', 'active_numbers'])


class DNCNumber(models.Model):
    """
    Individual phone numbers in DNC lists
    """
    dnc_list = models.ForeignKey(DNCList, on_delete=models.CASCADE, related_name='numbers')
    
    phone_regex = RegexValidator(regex=r'^\+?1?\d{9,15}$')
    phone_number = models.CharField(validators=[phone_regex], max_length=17, db_index=True)
    
    # DNC details
    added_date = models.DateField(auto_now_add=True, db_index=True)
    source = models.CharField(max_length=100, blank=True, help_text="Source of DNC request")
    reason = models.CharField(max_length=200, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    verified = models.BooleanField(default=False)
    
    # Audit trail
    added_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        db_table = 'dnc_numbers'
        unique_together = ['dnc_list', 'phone_number']
        indexes = [
            models.Index(fields=['phone_number']),
            models.Index(fields=['added_date']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.phone_number} ({self.dnc_list.list_name})"

    def is_expired(self):
        """Check if DNC entry has expired"""
        if self.expiry_date:
            return timezone.now().date() > self.expiry_date
        return False

    @classmethod
    def is_number_on_dnc(cls, phone_number):
        """Check if a phone number is on any active DNC list"""
        return cls.objects.filter(
            phone_number=phone_number,
            is_active=True,
            dnc_list__is_active=True
        ).exists()


class ComplianceAuditLog(models.Model):
    """
    Comprehensive audit trail for compliance tracking
    """
    AUDIT_TYPES = [
        ('call_attempt', 'Call Attempt'),
        ('dnc_check', 'DNC Check'),
        ('consent_verification', 'Consent Verification'),
        ('recording_access', 'Recording Access'),
        ('data_export', 'Data Export'),
        ('campaign_change', 'Campaign Change'),
        ('agent_action', 'Agent Action'),
        ('system_event', 'System Event'),
    ]

    SEVERITY_LEVELS = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    # Unique identifier
    audit_id = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    
    # Event information
    audit_type = models.CharField(max_length=30, choices=AUDIT_TYPES, db_index=True)
    event_name = models.CharField(max_length=100)
    description = models.TextField()
    severity = models.CharField(max_length=10, choices=SEVERITY_LEVELS, default='low')
    
    # Related objects (optional)
    campaign = models.ForeignKey(Campaign, on_delete=models.SET_NULL, null=True, blank=True)
    lead = models.ForeignKey(Lead, on_delete=models.SET_NULL, null=True, blank=True)
    call_task = models.ForeignKey(CallTask, on_delete=models.SET_NULL, null=True, blank=True)
    recording = models.ForeignKey(Recording, on_delete=models.SET_NULL, null=True, blank=True)
    
    # User and system information
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    session_id = models.CharField(max_length=100, blank=True)
    
    # Event data
    before_data = models.JSONField(null=True, blank=True, help_text="Data state before change")
    after_data = models.JSONField(null=True, blank=True, help_text="Data state after change")
    additional_data = models.JSONField(null=True, blank=True, help_text="Additional event data")
    
    # Compliance flags
    requires_review = models.BooleanField(default=False)
    reviewed = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='reviewed_audit_logs')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    event_timestamp = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'compliance_audit_logs'
        ordering = ['-event_timestamp']
        indexes = [
            models.Index(fields=['audit_type', 'event_timestamp']),
            models.Index(fields=['campaign', 'event_timestamp']),
            models.Index(fields=['user', 'event_timestamp']),
            models.Index(fields=['severity']),
            models.Index(fields=['requires_review']),
        ]

    def __str__(self):
        return f"{self.event_name} - {self.event_timestamp}"

    @classmethod
    def log_event(cls, audit_type, event_name, description, **kwargs):
        """Convenience method to create audit log entries"""
        return cls.objects.create(
            audit_type=audit_type,
            event_name=event_name,
            description=description,
            event_timestamp=timezone.now(),
            **kwargs
        )

    def mark_reviewed(self, reviewer):
        """Mark audit log as reviewed"""
        self.reviewed = True
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.save(update_fields=['reviewed', 'reviewed_by', 'reviewed_at'])

    def requires_compliance_review(self):
        """Check if this event requires compliance review"""
        return (self.severity in ['high', 'critical'] or 
                self.audit_type in ['dnc_check', 'consent_verification'] or
                self.requires_review)


class Disposition(models.Model):
    """
    Call disposition management for comprehensive call outcomes and follow-up actions
    """
    DISPOSITION_CATEGORIES = [
        ('contact', 'Contact Made'),
        ('no_contact', 'No Contact'),
        ('callback', 'Callback Required'),
        ('dnc', 'Do Not Call'),
        ('sale', 'Sale/Success'),
        ('system', 'System Related'),
    ]

    PRIORITY_LEVELS = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    CALLBACK_TYPES = [
        ('specific_time', 'Specific Time'),
        ('anytime', 'Anytime'),
        ('best_time', 'Best Time to Call'),
        ('appointment', 'Scheduled Appointment'),
    ]

    # Unique identifier
    disposition_id = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    
    # Related call information
    call_task = models.ForeignKey(CallTask, on_delete=models.CASCADE, related_name='dispositions')
    cdr = models.OneToOneField(CallDetailRecord, on_delete=models.CASCADE, related_name='disposition', null=True, blank=True)
    
    # Basic disposition information
    disposition_code = models.CharField(max_length=50, db_index=True, help_text="Standardized disposition code")
    disposition_name = models.CharField(max_length=100, help_text="Human-readable disposition name")
    category = models.CharField(max_length=20, choices=DISPOSITION_CATEGORIES, db_index=True)
    
    # Agent and timing
    agent = models.ForeignKey(User, on_delete=models.PROTECT, related_name='agent_dispositions')
    disposition_time = models.DateTimeField(auto_now_add=True, db_index=True)
    wrap_up_time = models.DateTimeField(null=True, blank=True, help_text="Time when wrap-up was completed")
    
    # Disposition details
    notes = models.TextField(blank=True, help_text="Agent notes about the call")
    is_final = models.BooleanField(default=True, help_text="Whether this is a final disposition")
    requires_followup = models.BooleanField(default=False)
    
    # Callback scheduling
    schedule_callback = models.BooleanField(default=False)
    callback_date = models.DateField(null=True, blank=True)
    callback_time = models.TimeField(null=True, blank=True)
    callback_type = models.CharField(max_length=20, choices=CALLBACK_TYPES, blank=True)
    callback_notes = models.TextField(blank=True)
    callback_priority = models.CharField(max_length=10, choices=PRIORITY_LEVELS, default='normal')
    
    # Best time to call preferences
    best_time_start = models.TimeField(null=True, blank=True)
    best_time_end = models.TimeField(null=True, blank=True)
    best_days = models.CharField(max_length=20, blank=True, help_text="Preferred days of week")
    timezone_preference = models.CharField(max_length=50, blank=True)
    
    # Sale/Success tracking
    sale_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    products_sold = models.JSONField(null=True, blank=True, help_text="List of products/services sold")
    commission_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Quality and compliance
    quality_score = models.IntegerField(null=True, blank=True, help_text="Call quality score 1-10")
    compliance_flags = models.JSONField(null=True, blank=True, help_text="Any compliance issues noted")
    requires_supervisor_review = models.BooleanField(default=False)
    supervisor_reviewed = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name='reviewed_dispositions')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    # System fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Data validation
    is_valid = models.BooleanField(default=True, help_text="Whether disposition data is valid")
    validation_errors = models.JSONField(null=True, blank=True, help_text="Any validation errors")

    class Meta:
        db_table = 'call_dispositions'
        ordering = ['-disposition_time']
        indexes = [
            models.Index(fields=['disposition_code']),
            models.Index(fields=['category', 'disposition_time']),
            models.Index(fields=['agent', 'disposition_time']),
            models.Index(fields=['schedule_callback', 'callback_date']),
            models.Index(fields=['requires_followup']),
            models.Index(fields=['is_final']),
            models.Index(fields=['requires_supervisor_review']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(schedule_callback=False) | (
                    models.Q(schedule_callback=True) & models.Q(callback_date__isnull=False)
                ),
                name='callback_date_required_when_scheduled'
            ),
        ]

    def __str__(self):
        return f"{self.disposition_name} - {self.call_task.lead.phone} by {self.agent.get_full_name()}"

    def save(self, *args, **kwargs):
        """Override save to handle automatic callback task creation"""
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        # Create callback task if scheduled
        if is_new and self.schedule_callback and self.callback_date:
            self.create_callback_task()

    def create_callback_task(self):
        """Create a new CallTask for the scheduled callback"""
        from datetime import datetime, time
        
        # Determine callback datetime
        callback_time = self.callback_time or time(10, 0)  # Default to 10 AM
        callback_datetime = datetime.combine(self.callback_date, callback_time)
        
        # Create new call task
        CallTask.objects.create(
            campaign=self.call_task.campaign,
            lead=self.call_task.lead,
            call_type='callback',
            state='pending',
            phone_number=self.call_task.phone_number,
            caller_id=self.call_task.caller_id,
            scheduled_at=callback_datetime,
            priority=self.callback_priority,
            notes=f"Callback scheduled from disposition {self.disposition_id}"
        )

    def mark_supervisor_reviewed(self, supervisor):
        """Mark disposition as reviewed by supervisor"""
        self.supervisor_reviewed = True
        self.reviewed_by = supervisor
        self.reviewed_at = timezone.now()
        self.save(update_fields=['supervisor_reviewed', 'reviewed_by', 'reviewed_at'])

    def validate_disposition(self):
        """Validate disposition data integrity"""
        errors = []
        
        # Check callback scheduling consistency
        if self.schedule_callback and not self.callback_date:
            errors.append("Callback date is required when scheduling callback")
        
        # Check sale information consistency
        if self.category == 'sale' and not self.sale_amount:
            errors.append("Sale amount should be specified for sales dispositions")
        
        # Check DNC compliance
        if self.category == 'dnc' and self.schedule_callback:
            errors.append("Cannot schedule callback for DNC disposition")
        
        self.validation_errors = errors if errors else None
        self.is_valid = len(errors) == 0
        return self.is_valid

    @classmethod
    def get_disposition_statistics(cls, campaign=None, agent=None, date_range=None):
        """Get disposition statistics for reporting"""
        queryset = cls.objects.all()
        
        if campaign:
            queryset = queryset.filter(call_task__campaign=campaign)
        if agent:
            queryset = queryset.filter(agent=agent)
        if date_range:
            queryset = queryset.filter(disposition_time__range=date_range)
        
        return queryset.values('category', 'disposition_code').annotate(
            count=models.Count('id'),
            avg_quality=models.Avg('quality_score'),
            total_sales=models.Sum('sale_amount')
        ).order_by('-count')
