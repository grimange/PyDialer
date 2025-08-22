from django.db import models
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.core.validators import RegexValidator
from django.utils import timezone


class Department(models.Model):
    """
    Department model for organizational structure
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'departments'
        ordering = ['name']

    def __str__(self):
        return self.name


class Team(models.Model):
    """
    Team model for organizational structure within departments
    """
    name = models.CharField(max_length=100)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='teams')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'teams'
        unique_together = ['name', 'department']
        ordering = ['department__name', 'name']

    def __str__(self):
        return f"{self.department.name} - {self.name}"


class UserRole(models.Model):
    """
    User role model for role-based permissions
    """
    ROLE_CHOICES = [
        ('agent', 'Agent'),
        ('supervisor', 'Supervisor'),
        ('manager', 'Manager'),
        ('admin', 'Administrator'),
    ]

    name = models.CharField(max_length=20, choices=ROLE_CHOICES, unique=True)
    display_name = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    permissions = models.ManyToManyField(Permission, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_roles'
        ordering = ['name']

    def __str__(self):
        return self.display_name


class User(AbstractUser):
    """
    Extended User model for agents, supervisors, and admins
    """
    # Personal Information
    employee_id = models.CharField(max_length=20, unique=True, null=True, blank=True)
    phone_regex = RegexValidator(regex=r'^\+?1?\d{9,15}$', 
                                message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed.")
    phone_number = models.CharField(validators=[phone_regex], max_length=17, blank=True)
    extension = models.CharField(max_length=10, blank=True)
    
    # Organizational Structure
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True)
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True)
    role = models.ForeignKey(UserRole, on_delete=models.PROTECT)
    supervisor = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, 
                                 related_name='supervised_agents')
    
    # Agent-specific fields
    agent_skill_level = models.IntegerField(default=1, help_text="Skill level from 1-10")
    max_concurrent_calls = models.IntegerField(default=1)
    is_available = models.BooleanField(default=False)
    
    # Audit fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = 'users'
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f"{self.get_full_name()} ({self.username})"

    def get_full_name(self):
        """Return the full name with proper formatting"""
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name if full_name else self.username

    def is_agent(self):
        """Check if user has agent role"""
        return self.role.name == 'agent'

    def is_supervisor(self):
        """Check if user has supervisor role"""
        return self.role.name in ['supervisor', 'manager', 'admin']

    def is_manager(self):
        """Check if user has manager role"""
        return self.role.name in ['manager', 'admin']

    def is_admin(self):
        """Check if user has admin role"""
        return self.role.name == 'admin'

    def get_supervised_agents(self):
        """Get all agents supervised by this user"""
        return self.supervised_agents.filter(is_active=True)


class AgentStatus(models.Model):
    """
    Agent status tracking model for real-time presence
    """
    STATUS_CHOICES = [
        ('offline', 'Offline'),
        ('available', 'Available'),
        ('busy', 'Busy'),
        ('on_call', 'On Call'),
        ('wrap_up', 'Wrap Up'),
        ('break', 'Break'),
        ('lunch', 'Lunch'),
        ('meeting', 'Meeting'),
        ('training', 'Training'),
        ('not_ready', 'Not Ready'),
    ]

    agent = models.OneToOneField(User, on_delete=models.CASCADE, related_name='current_status')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='offline')
    status_reason = models.CharField(max_length=100, blank=True)
    status_changed_at = models.DateTimeField(auto_now=True)
    login_time = models.DateTimeField(null=True, blank=True)
    logout_time = models.DateTimeField(null=True, blank=True)
    total_login_duration = models.DurationField(null=True, blank=True)
    
    # Call statistics
    calls_handled_today = models.IntegerField(default=0)
    average_call_duration = models.DurationField(null=True, blank=True)
    
    class Meta:
        db_table = 'agent_status'
        ordering = ['agent__last_name', 'agent__first_name']

    def __str__(self):
        return f"{self.agent.get_full_name()} - {self.get_status_display()}"

    def set_status(self, new_status, reason=""):
        """Update agent status with timestamp"""
        self.status = new_status
        self.status_reason = reason
        self.status_changed_at = timezone.now()
        
        if new_status == 'available' and not self.login_time:
            self.login_time = timezone.now()
        elif new_status == 'offline' and self.login_time:
            self.logout_time = timezone.now()
            if self.login_time:
                self.total_login_duration = self.logout_time - self.login_time
        
        self.save()

    def is_available_for_calls(self):
        """Check if agent is available to receive calls"""
        return self.status in ['available']

    def is_logged_in(self):
        """Check if agent is currently logged in"""
        return self.status != 'offline'


class AgentSkill(models.Model):
    """
    Skills that agents can have for skill-based routing
    """
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'agent_skills'
        ordering = ['name']

    def __str__(self):
        return self.name


class AgentSkillAssignment(models.Model):
    """
    Many-to-many relationship between agents and skills with proficiency levels
    """
    agent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='skill_assignments')
    skill = models.ForeignKey(AgentSkill, on_delete=models.CASCADE)
    proficiency_level = models.IntegerField(default=1, help_text="Proficiency level from 1-10")
    assigned_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'agent_skill_assignments'
        unique_together = ['agent', 'skill']
        ordering = ['agent__last_name', 'skill__name']

    def __str__(self):
        return f"{self.agent.get_full_name()} - {self.skill.name} (Level {self.proficiency_level})"
