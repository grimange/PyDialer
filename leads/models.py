from django.db import models
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.contrib.auth import get_user_model
from campaigns.models import Campaign
import pytz

User = get_user_model()


class Lead(models.Model):
    """
    Lead model for managing contact information and call attempts
    """
    STATUS_CHOICES = [
        ('new', 'New'),
        ('active', 'Active'),
        ('called', 'Called'),
        ('answered', 'Answered'),
        ('no_answer', 'No Answer'),
        ('busy', 'Busy'),
        ('disconnected', 'Disconnected'),
        ('callback', 'Callback'),
        ('dnc', 'Do Not Call'),
        ('completed', 'Completed'),
        ('invalid', 'Invalid'),
        ('duplicate', 'Duplicate'),
    ]

    PRIORITY_CHOICES = [
        (1, 'Highest'),
        (2, 'High'),
        (3, 'Normal'),
        (4, 'Low'),
        (5, 'Lowest'),
    ]

    # Contact Information
    phone_regex = RegexValidator(regex=r'^\+?1?\d{9,15}$', 
                                message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed.")
    phone = models.CharField(validators=[phone_regex], max_length=17, db_index=True)
    alt_phone = models.CharField(validators=[phone_regex], max_length=17, blank=True, 
                                help_text="Alternative phone number")
    
    # Personal Information
    first_name = models.CharField(max_length=50, blank=True)
    last_name = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    
    # Address Information
    address = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=50, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=50, default="US")
    
    # Campaign Assignment
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='leads')
    list_id = models.CharField(max_length=50, blank=True, help_text="Source list identifier")
    
    # Lead Status and Priority
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new', db_index=True)
    priority = models.IntegerField(choices=PRIORITY_CHOICES, default=3, db_index=True)
    
    # Call Attempt Tracking
    attempts = models.IntegerField(default=0, db_index=True)
    max_attempts = models.IntegerField(default=3)
    last_call_at = models.DateTimeField(null=True, blank=True, db_index=True)
    next_call_at = models.DateTimeField(null=True, blank=True, db_index=True)
    
    # Timezone and Scheduling
    timezone = models.CharField(max_length=50, default='UTC', help_text="Lead's timezone")
    best_call_time_start = models.TimeField(null=True, blank=True)
    best_call_time_end = models.TimeField(null=True, blank=True)
    do_not_call_after = models.DateTimeField(null=True, blank=True)
    
    # Callback Information
    callback_datetime = models.DateTimeField(null=True, blank=True, db_index=True)
    callback_agent = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='callback_leads')
    callback_notes = models.TextField(blank=True)
    
    # Lead Scoring and Classification
    lead_score = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    lead_source = models.CharField(max_length=100, blank=True)
    lead_type = models.CharField(max_length=50, blank=True)
    
    # Custom Fields (JSON for flexibility)
    custom_fields = models.JSONField(default=dict, blank=True, 
                                   help_text="Additional custom fields as JSON")
    
    # Compliance and DNC
    is_dnc = models.BooleanField(default=False, db_index=True)
    dnc_reason = models.CharField(max_length=100, blank=True)
    consent_to_call = models.BooleanField(default=True)
    consent_date = models.DateTimeField(null=True, blank=True)
    
    # Audit Fields
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_modified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='modified_leads')
    
    # Import Information
    import_batch_id = models.CharField(max_length=50, blank=True, db_index=True)
    source_file = models.CharField(max_length=200, blank=True)
    source_row = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = 'leads'
        ordering = ['priority', '-created_at']
        indexes = [
            models.Index(fields=['campaign', 'status']),
            models.Index(fields=['phone']),
            models.Index(fields=['next_call_at']),
            models.Index(fields=['callback_datetime']),
            models.Index(fields=['attempts', 'status']),
        ]

    def __str__(self):
        name = self.get_full_name()
        if name:
            return f"{name} ({self.phone})"
        return self.phone

    def get_full_name(self):
        """Return the full name with proper formatting"""
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name if full_name else None

    def is_callable(self):
        """Check if lead is available for calling"""
        if self.is_dnc or not self.consent_to_call:
            return False
        
        if self.attempts >= self.max_attempts:
            return False
        
        if self.status in ['completed', 'invalid', 'duplicate']:
            return False
        
        if self.do_not_call_after and timezone.now() > self.do_not_call_after:
            return False
        
        return True

    def is_in_call_window(self, check_datetime=None):
        """Check if current time is within the lead's preferred call window"""
        if check_datetime is None:
            check_datetime = timezone.now()
        
        # Convert to lead's timezone
        try:
            lead_tz = pytz.timezone(self.timezone)
            local_time = check_datetime.astimezone(lead_tz).time()
        except:
            local_time = check_datetime.time()
        
        # Check call window if specified
        if self.best_call_time_start and self.best_call_time_end:
            return self.best_call_time_start <= local_time <= self.best_call_time_end
        
        return True

    def schedule_next_attempt(self, minutes_delay=None):
        """Schedule the next call attempt"""
        if minutes_delay is None:
            minutes_delay = self.campaign.retry_delay_minutes
        
        self.next_call_at = timezone.now() + timezone.timedelta(minutes=minutes_delay)
        self.save(update_fields=['next_call_at'])

    def increment_attempts(self):
        """Increment call attempts counter"""
        self.attempts += 1
        self.last_call_at = timezone.now()
        self.save(update_fields=['attempts', 'last_call_at'])

    def set_callback(self, callback_datetime, agent=None, notes=""):
        """Set callback information"""
        self.callback_datetime = callback_datetime
        self.callback_agent = agent
        self.callback_notes = notes
        self.status = 'callback'
        self.save()

    def mark_as_dnc(self, reason=""):
        """Mark lead as Do Not Call"""
        self.is_dnc = True
        self.dnc_reason = reason
        self.status = 'dnc'
        self.save()


class LeadImportBatch(models.Model):
    """
    Track bulk lead imports for auditing and rollback
    """
    batch_id = models.CharField(max_length=50, unique=True)
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='import_batches')
    filename = models.CharField(max_length=200)
    total_records = models.IntegerField(default=0)
    successful_imports = models.IntegerField(default=0)
    failed_imports = models.IntegerField(default=0)
    duplicates_found = models.IntegerField(default=0)
    
    # Import Status
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Audit Fields
    imported_by = models.ForeignKey(User, on_delete=models.PROTECT)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_log = models.TextField(blank=True)

    class Meta:
        db_table = 'lead_import_batches'
        ordering = ['-started_at']

    def __str__(self):
        return f"Batch {self.batch_id} - {self.filename}"

    def complete_import(self):
        """Mark import as completed"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save()

    def get_success_rate(self):
        """Calculate import success rate"""
        if self.total_records == 0:
            return 0.0
        return (self.successful_imports / self.total_records) * 100


class DispositionCode(models.Model):
    """
    Disposition codes for call outcomes
    """
    DISPOSITION_TYPES = [
        ('contact', 'Contact Made'),
        ('no_contact', 'No Contact'),
        ('callback', 'Callback'),
        ('system', 'System'),
        ('compliance', 'Compliance'),
    ]

    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    disposition_type = models.CharField(max_length=20, choices=DISPOSITION_TYPES, default='contact')
    
    # Behavior Settings
    is_sale = models.BooleanField(default=False, help_text="Mark as successful sale")
    is_contact = models.BooleanField(default=True, help_text="Count as contact made")
    requires_callback = models.BooleanField(default=False)
    allows_retry = models.BooleanField(default=True, help_text="Allow lead to be called again")
    remove_from_campaign = models.BooleanField(default=False)
    
    # Campaign Association
    campaigns = models.ManyToManyField(Campaign, blank=True, 
                                     help_text="Campaigns where this disposition is available")
    
    # Display Settings
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    
    # Audit Fields
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        db_table = 'disposition_codes'
        ordering = ['display_order', 'name']

    def __str__(self):
        return f"{self.code} - {self.name}"


class Disposition(models.Model):
    """
    Disposition records for call outcomes and notes
    """
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='dispositions')
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='dispositions')
    disposition_code = models.ForeignKey(DispositionCode, on_delete=models.PROTECT)
    
    # Call Information
    agent = models.ForeignKey(User, on_delete=models.PROTECT, related_name='dispositions_made')
    call_duration = models.DurationField(null=True, blank=True)
    talk_time = models.DurationField(null=True, blank=True, help_text="Actual talk time with customer")
    
    # Disposition Details
    notes = models.TextField(blank=True)
    callback_datetime = models.DateTimeField(null=True, blank=True)
    callback_notes = models.TextField(blank=True)
    
    # Sale Information (if applicable)
    sale_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    product_interest = models.CharField(max_length=100, blank=True)
    
    # Custom Fields
    custom_data = models.JSONField(default=dict, blank=True)
    
    # System Information
    phone_dialed = models.CharField(max_length=17, blank=True)
    caller_id_used = models.CharField(max_length=17, blank=True)
    
    # Audit Fields
    created_at = models.DateTimeField(auto_now_add=True)
    wrap_up_time = models.DurationField(null=True, blank=True, help_text="Time spent in wrap-up")

    class Meta:
        db_table = 'dispositions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['lead', 'created_at']),
            models.Index(fields=['campaign', 'created_at']),
            models.Index(fields=['agent', 'created_at']),
            models.Index(fields=['disposition_code']),
        ]

    def __str__(self):
        return f"{self.lead} - {self.disposition_code.name} by {self.agent.get_full_name()}"

    def is_sale(self):
        """Check if this disposition represents a sale"""
        return self.disposition_code.is_sale

    def is_contact(self):
        """Check if this disposition represents contact made"""
        return self.disposition_code.is_contact

    def requires_callback(self):
        """Check if this disposition requires a callback"""
        return self.disposition_code.requires_callback

    def process_disposition(self):
        """Process the disposition and update lead accordingly"""
        # Update lead status based on disposition
        if self.disposition_code.remove_from_campaign:
            self.lead.status = 'completed'
        elif self.disposition_code.requires_callback and self.callback_datetime:
            self.lead.set_callback(self.callback_datetime, self.agent, self.callback_notes)
        elif not self.disposition_code.allows_retry:
            self.lead.status = 'completed'
        else:
            # Schedule next attempt if allowed
            if self.lead.attempts < self.lead.max_attempts:
                self.lead.schedule_next_attempt()
            else:
                self.lead.status = 'completed'
        
        self.lead.save()


class LeadNote(models.Model):
    """
    Additional notes and comments for leads
    """
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='notes')
    agent = models.ForeignKey(User, on_delete=models.PROTECT, related_name='lead_notes')
    note = models.TextField()
    is_private = models.BooleanField(default=False, help_text="Private note visible only to agent")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'lead_notes'
        ordering = ['-created_at']

    def __str__(self):
        return f"Note for {self.lead} by {self.agent.get_full_name()}"
