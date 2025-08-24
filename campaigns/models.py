from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.utils import timezone
from django.contrib.auth import get_user_model
from agents.models import AgentSkill

User = get_user_model()


class Campaign(models.Model):
    """
    Campaign model for managing outbound and inbound call campaigns
    """
    CAMPAIGN_TYPES = [
        ('outbound', 'Outbound'),
        ('inbound', 'Inbound'),
        ('blended', 'Blended'),
    ]
    
    DIAL_METHODS = [
        ('manual', 'Manual'),
        ('ratio', 'Ratio'),
        ('predictive', 'Predictive'),
        ('progressive', 'Progressive'),
        ('auto', 'Auto'),
    ]
    
    STATUS_CHOICES = [
        ('inactive', 'Inactive'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('completed', 'Completed'),
        ('archived', 'Archived'),
    ]

    # Basic Information
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    campaign_type = models.CharField(max_length=20, choices=CAMPAIGN_TYPES, default='outbound')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='inactive')
    
    # Dialing Configuration
    dial_method = models.CharField(max_length=20, choices=DIAL_METHODS, default='ratio')
    pacing_ratio = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        default=2.5,
        validators=[MinValueValidator(1.0), MaxValueValidator(10.0)],
        help_text="Ratio of calls to available agents (1.0-10.0)"
    )
    
    # SLA and Performance Settings
    drop_sla = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=5.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
        help_text="Maximum acceptable abandonment rate percentage"
    )
    answer_timeout = models.IntegerField(default=30, help_text="Timeout in seconds for call answer")
    wrap_up_time = models.IntegerField(default=30, help_text="Default wrap-up time in seconds")
    
    # Caller ID Configuration
    phone_regex = RegexValidator(regex=r'^\+?1?\d{9,15}$', 
                                message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed.")
    caller_id = models.CharField(
        validators=[phone_regex], 
        max_length=17,
        help_text="Outbound caller ID number"
    )
    caller_id_name = models.CharField(max_length=50, blank=True, help_text="Caller ID name")
    
    # Campaign Scheduling
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    start_time = models.TimeField(default="08:00", help_text="Daily start time")
    end_time = models.TimeField(default="18:00", help_text="Daily end time")
    timezone_name = models.CharField(max_length=50, default="UTC")
    
    # Days of Week (bit field for efficient storage)
    monday = models.BooleanField(default=True)
    tuesday = models.BooleanField(default=True)
    wednesday = models.BooleanField(default=True)
    thursday = models.BooleanField(default=True)
    friday = models.BooleanField(default=True)
    saturday = models.BooleanField(default=False)
    sunday = models.BooleanField(default=False)
    
    # Lead Management
    max_attempts = models.IntegerField(default=3, help_text="Maximum call attempts per lead")
    retry_delay_minutes = models.IntegerField(default=60, help_text="Minutes between retry attempts")
    recycle_inactive_leads = models.BooleanField(default=True)
    
    # Lead Recycling Rules
    recycle_no_answer_days = models.IntegerField(
        default=7, 
        help_text="Days after which 'no answer' leads are recycled"
    )
    recycle_busy_days = models.IntegerField(
        default=1, 
        help_text="Days after which 'busy' leads are recycled"
    )
    recycle_disconnected_days = models.IntegerField(
        default=30, 
        help_text="Days after which 'disconnected' leads are recycled"
    )
    max_recycle_attempts = models.IntegerField(
        default=2, 
        help_text="Maximum number of times a lead can be recycled"
    )
    exclude_dnc_from_recycling = models.BooleanField(
        default=True, 
        help_text="Exclude DNC leads from recycling"
    )
    recycle_only_business_hours = models.BooleanField(
        default=True, 
        help_text="Only recycle leads during campaign business hours"
    )
    
    # Agent Assignment
    assigned_agents = models.ManyToManyField(User, through='CampaignAgentAssignment', 
                                           through_fields=('campaign', 'agent'),
                                           related_name='assigned_campaigns')
    required_skills = models.ManyToManyField(AgentSkill, blank=True, 
                                           help_text="Skills required for agents on this campaign")
    
    # Compliance Settings
    enable_amd = models.BooleanField(default=True, help_text="Enable Answer Machine Detection")
    enable_call_recording = models.BooleanField(default=True)
    require_agent_confirmation = models.BooleanField(default=False)
    
    # Performance Tracking
    total_leads = models.IntegerField(default=0)
    completed_calls = models.IntegerField(default=0)
    successful_contacts = models.IntegerField(default=0)
    current_drop_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    
    # Audit Fields
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='created_campaigns')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_started_at = models.DateTimeField(null=True, blank=True)
    last_stopped_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'campaigns'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"

    def is_active(self):
        """Check if campaign is currently active"""
        return self.status == 'active'

    def is_in_time_window(self, current_datetime=None):
        """Check if campaign should be running based on schedule"""
        if current_datetime is None:
            current_datetime = timezone.now()
        
        # Check date range
        if self.start_date and current_datetime.date() < self.start_date:
            return False
        if self.end_date and current_datetime.date() > self.end_date:
            return False
        
        # Check time of day
        current_time = current_datetime.time()
        if current_time < self.start_time or current_time > self.end_time:
            return False
        
        # Check day of week
        weekday = current_datetime.weekday()  # 0 = Monday, 6 = Sunday
        day_enabled = [
            self.monday, self.tuesday, self.wednesday, self.thursday,
            self.friday, self.saturday, self.sunday
        ][weekday]
        
        return day_enabled

    def get_available_agents(self):
        """Get agents available for this campaign"""
        from agents.models import AgentStatus
        return User.objects.filter(
            assigned_campaigns=self,
            campaignagentassignment__is_active=True,
            current_status__status='available'
        )

    def calculate_contact_rate(self):
        """Calculate successful contact rate"""
        if self.completed_calls == 0:
            return 0.0
        return (self.successful_contacts / self.completed_calls) * 100

    def update_drop_rate(self, dropped_calls, total_calls):
        """Update current drop rate"""
        if total_calls > 0:
            self.current_drop_rate = (dropped_calls / total_calls) * 100
            self.save(update_fields=['current_drop_rate'])

    def should_reduce_pace(self):
        """Check if pacing should be reduced due to high drop rate"""
        return self.current_drop_rate > self.drop_sla


class CampaignAgentAssignment(models.Model):
    """
    Many-to-many through model for campaign-agent assignments with additional fields
    """
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE)
    agent = models.ForeignKey(User, on_delete=models.CASCADE)
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='agent_assignments_made')
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=1, help_text="Priority for call distribution (1=highest)")
    max_calls_per_hour = models.IntegerField(null=True, blank=True, 
                                           help_text="Maximum calls per hour for this agent on this campaign")

    class Meta:
        db_table = 'campaign_agent_assignments'
        unique_together = ['campaign', 'agent']
        ordering = ['priority', 'assigned_at']

    def __str__(self):
        return f"{self.campaign.name} - {self.agent.get_full_name()}"


class CampaignSchedule(models.Model):
    """
    Advanced scheduling rules for campaigns (holidays, special dates, etc.)
    """
    SCHEDULE_TYPES = [
        ('holiday', 'Holiday'),
        ('special_hours', 'Special Hours'),
        ('blackout', 'Blackout Period'),
    ]

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='schedules')
    schedule_type = models.CharField(max_length=20, choices=SCHEDULE_TYPES)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    
    # Date/Time Configuration
    start_date = models.DateField()
    end_date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    
    # Override Settings
    is_active_override = models.BooleanField(default=False, 
                                           help_text="Override campaign active status during this period")
    pacing_ratio_override = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
                                              help_text="Override pacing ratio during this period")
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        db_table = 'campaign_schedules'
        ordering = ['start_date', 'start_time']

    def __str__(self):
        return f"{self.campaign.name} - {self.name}"

    def is_active_period(self, check_datetime=None):
        """Check if this schedule is currently active"""
        if check_datetime is None:
            check_datetime = timezone.now()
        
        date_check = self.start_date <= check_datetime.date() <= self.end_date
        
        if self.start_time and self.end_time:
            time_check = self.start_time <= check_datetime.time() <= self.end_time
            return date_check and time_check
        
        return date_check


class CampaignStatistics(models.Model):
    """
    Real-time and historical statistics for campaigns
    """
    campaign = models.OneToOneField(Campaign, on_delete=models.CASCADE, related_name='statistics')
    
    # Real-time Statistics
    active_calls = models.IntegerField(default=0)
    agents_logged_in = models.IntegerField(default=0)
    agents_available = models.IntegerField(default=0)
    agents_on_call = models.IntegerField(default=0)
    
    # Daily Statistics
    calls_attempted_today = models.IntegerField(default=0)
    calls_completed_today = models.IntegerField(default=0)
    calls_answered_today = models.IntegerField(default=0)
    calls_dropped_today = models.IntegerField(default=0)
    
    # Performance Metrics
    average_call_duration = models.DurationField(null=True, blank=True)
    average_wrap_time = models.DurationField(null=True, blank=True)
    contact_rate_today = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    conversion_rate_today = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    
    # Last Updated
    last_updated = models.DateTimeField(auto_now=True)
    last_reset_date = models.DateField(auto_now_add=True)

    class Meta:
        db_table = 'campaign_statistics'

    def __str__(self):
        return f"{self.campaign.name} Statistics"

    def reset_daily_stats(self):
        """Reset daily statistics (called by scheduled task)"""
        self.calls_attempted_today = 0
        self.calls_completed_today = 0
        self.calls_answered_today = 0
        self.calls_dropped_today = 0
        self.contact_rate_today = 0.0
        self.conversion_rate_today = 0.0
        self.last_reset_date = timezone.now().date()
        self.save()

    def calculate_drop_rate_today(self):
        """Calculate today's drop rate"""
        if self.calls_attempted_today == 0:
            return 0.0
        return (self.calls_dropped_today / self.calls_attempted_today) * 100
