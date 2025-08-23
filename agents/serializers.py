"""
Serializers for the agents app.

This module contains serializers for user authentication, registration,
and profile management functionality.
"""

from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from .models import User, Department, Team, UserRole, AgentStatus, AgentSkill, AgentSkillAssignment


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for user registration.
    
    Handles validation for user creation including password confirmation,
    unique email validation, and proper role assignment.
    """
    email = serializers.EmailField(
        required=True,
        validators=[UniqueValidator(queryset=User.objects.all())]
    )
    password = serializers.CharField(
        write_only=True, 
        required=True, 
        validators=[validate_password]
    )
    password_confirm = serializers.CharField(write_only=True, required=True)
    
    # Role assignment fields
    role = serializers.PrimaryKeyRelatedField(
        queryset=UserRole.objects.all(),
        required=False,
        allow_null=True
    )
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(),
        required=False,
        allow_null=True
    )
    team = serializers.PrimaryKeyRelatedField(
        queryset=Team.objects.all(),
        required=False,
        allow_null=True
    )

    class Meta:
        model = User
        fields = (
            'username', 'password', 'password_confirm', 'email', 
            'first_name', 'last_name', 'role', 'department', 
            'team', 'phone_number', 'extension'
        )
        extra_kwargs = {
            'first_name': {'required': True},
            'last_name': {'required': True}
        }

    def validate(self, attrs):
        """
        Validate password confirmation and role constraints.
        """
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError(
                {"password": "Password fields didn't match."}
            )
        return attrs

    def validate_team(self, value):
        """
        Validate that team belongs to the specified department if both are provided.
        """
        if value and 'department' in self.initial_data:
            department_id = self.initial_data.get('department')
            if department_id and str(value.department.id) != str(department_id):
                raise serializers.ValidationError(
                    "Team must belong to the specified department."
                )
        return value

    def create(self, validated_data):
        """
        Create user with validated data.
        """
        validated_data.pop('password_confirm', None)
        password = validated_data.pop('password')
        
        user = User.objects.create_user(
            password=password,
            **validated_data
        )
        return user


class UserLoginSerializer(serializers.Serializer):
    """
    Serializer for user login.
    
    Validates username/password and returns user data if authentication succeeds.
    """
    username = serializers.CharField(required=True)
    password = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        """
        Validate user credentials and return user if authentication succeeds.
        """
        username = attrs.get('username')
        password = attrs.get('password')

        if username and password:
            user = authenticate(username=username, password=password)
            
            if not user:
                raise serializers.ValidationError(
                    'Invalid username or password.',
                    code='authorization'
                )
            
            if not user.is_active:
                raise serializers.ValidationError(
                    'User account is disabled.',
                    code='authorization'
                )
            
            attrs['user'] = user
            return attrs
        else:
            raise serializers.ValidationError(
                'Must include username and password.',
                code='authorization'
            )


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for user profile management.
    
    Used for retrieving and updating user profile information.
    """
    role_name = serializers.CharField(source='role.name', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    team_name = serializers.CharField(source='team.name', read_only=True)
    supervisor_name = serializers.CharField(source='supervisor.get_full_name', read_only=True)
    full_name = serializers.CharField(read_only=True)
    avatar_url = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'first_name', 'last_name', 
            'full_name', 'employee_id', 'phone_number', 'extension',
            'avatar', 'avatar_url', 'bio', 'timezone', 'is_active',
            'date_joined', 'last_login', 'role', 'role_name', 
            'department', 'department_name', 'team', 'team_name',
            'supervisor', 'supervisor_name', 'agent_skill_level',
            'max_concurrent_calls', 'email_notifications',
            'desktop_notifications', 'sound_notifications',
            'preferred_language'
        )
        read_only_fields = ('id', 'username', 'date_joined', 'last_login')

    def get_avatar_url(self, obj):
        """Get full URL for avatar image"""
        if obj.avatar:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.avatar.url)
            return obj.avatar.url
        return None

    def update(self, instance, validated_data):
        """
        Update user profile with validation.
        """
        # Prevent updating certain fields through profile endpoint
        validated_data.pop('username', None)
        validated_data.pop('is_active', None)
        
        return super().update(instance, validated_data)


class UserPreferencesSerializer(serializers.ModelSerializer):
    """
    Serializer specifically for user preferences management.
    """
    class Meta:
        model = User
        fields = (
            'timezone', 'email_notifications', 'desktop_notifications',
            'sound_notifications', 'preferred_language'
        )


class UserAvatarSerializer(serializers.ModelSerializer):
    """
    Serializer for avatar upload functionality.
    """
    avatar_url = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ('avatar', 'avatar_url')
    
    def get_avatar_url(self, obj):
        """Get full URL for avatar image"""
        if obj.avatar:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.avatar.url)
            return obj.avatar.url
        return None

    def validate_avatar(self, value):
        """
        Validate avatar file size and type
        """
        if value:
            # Check file size (max 5MB)
            if value.size > 5 * 1024 * 1024:
                raise serializers.ValidationError("Avatar file size must be under 5MB.")
            
            # Check file type
            valid_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
            if value.content_type not in valid_types:
                raise serializers.ValidationError(
                    "Avatar must be a JPEG, PNG, GIF, or WebP image."
                )
        
        return value


class UserBasicInfoSerializer(serializers.ModelSerializer):
    """
    Serializer for basic user information updates.
    """
    full_name = serializers.CharField(read_only=True)
    
    class Meta:
        model = User
        fields = (
            'first_name', 'last_name', 'full_name', 'email', 
            'phone_number', 'extension', 'bio'
        )

    def validate_email(self, value):
        """
        Ensure email is unique across all users except current user.
        """
        user = self.instance
        if User.objects.exclude(pk=user.pk).filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value


class PasswordChangeSerializer(serializers.Serializer):
    """
    Serializer for password change functionality.
    """
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(
        required=True, 
        write_only=True,
        validators=[validate_password]
    )
    new_password_confirm = serializers.CharField(required=True, write_only=True)

    def validate_old_password(self, value):
        """
        Validate that the old password is correct.
        """
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Old password is incorrect.')
        return value

    def validate(self, attrs):
        """
        Validate that new passwords match.
        """
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError(
                {"new_password": "New password fields didn't match."}
            )
        return attrs

    def save(self, **kwargs):
        """
        Set the new password for the user.
        """
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user


class DepartmentSerializer(serializers.ModelSerializer):
    """
    Serializer for Department model.
    """
    class Meta:
        model = Department
        fields = '__all__'


class TeamSerializer(serializers.ModelSerializer):
    """
    Serializer for Team model.
    """
    department_name = serializers.CharField(source='department.name', read_only=True)
    
    class Meta:
        model = Team
        fields = '__all__'


class UserRoleSerializer(serializers.ModelSerializer):
    """
    Serializer for UserRole model.
    """
    class Meta:
        model = UserRole
        fields = '__all__'


class PasswordResetRequestSerializer(serializers.Serializer):
    """
    Serializer for password reset request functionality.
    
    Validates email and initiates password reset process.
    """
    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        """
        Validate that the email exists in the system.
        """
        try:
            user = User.objects.get(email=value, is_active=True)
            return value
        except User.DoesNotExist:
            # For security, we don't reveal if an email exists or not
            # We still return the value to avoid enumeration attacks
            return value

    def get_user(self, email):
        """
        Get user by email if exists and is active.
        """
        try:
            return User.objects.get(email=email, is_active=True)
        except User.DoesNotExist:
            return None


class PasswordResetConfirmSerializer(serializers.Serializer):
    """
    Serializer for password reset confirmation functionality.
    
    Validates token and sets new password.
    """
    uid = serializers.CharField(required=True)
    token = serializers.CharField(required=True)
    new_password = serializers.CharField(
        required=True, 
        write_only=True,
        validators=[validate_password]
    )
    new_password_confirm = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        """
        Validate token, uid, and password confirmation.
        """
        uid = attrs.get('uid')
        token = attrs.get('token')
        new_password = attrs.get('new_password')
        new_password_confirm = attrs.get('new_password_confirm')

        # Validate password confirmation
        if new_password != new_password_confirm:
            raise serializers.ValidationError({
                'new_password': "New password fields didn't match."
            })

        # Validate token and get user
        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({
                'uid': 'Invalid user ID.'
            })

        if not default_token_generator.check_token(user, token):
            raise serializers.ValidationError({
                'token': 'Invalid or expired token.'
            })

        attrs['user'] = user
        return attrs

    def save(self, **kwargs):
        """
        Set the new password for the user.
        """
        user = self.validated_data['user']
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user


class AgentStatusSerializer(serializers.ModelSerializer):
    """
    Serializer for AgentStatus model.
    """
    agent_name = serializers.CharField(source='agent.get_full_name', read_only=True)
    agent_username = serializers.CharField(source='agent.username', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = AgentStatus
        fields = [
            'id', 'agent', 'agent_name', 'agent_username', 'status', 'status_display',
            'status_reason', 'status_changed_at', 'login_time', 'logout_time',
            'total_login_duration', 'calls_handled_today', 'average_call_duration'
        ]
        read_only_fields = ['status_changed_at', 'login_time', 'logout_time', 'total_login_duration']


class AgentStatusUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating agent status.
    """
    class Meta:
        model = AgentStatus
        fields = ['status', 'status_reason']
    
    def update(self, instance, validated_data):
        """
        Update agent status using the model's set_status method.
        """
        new_status = validated_data.get('status', instance.status)
        reason = validated_data.get('status_reason', '')
        instance.set_status(new_status, reason)
        return instance


class AgentSkillSerializer(serializers.ModelSerializer):
    """
    Serializer for AgentSkill model.
    """
    class Meta:
        model = AgentSkill
        fields = '__all__'


class AgentSkillAssignmentSerializer(serializers.ModelSerializer):
    """
    Serializer for AgentSkillAssignment model.
    """
    agent_name = serializers.CharField(source='agent.get_full_name', read_only=True)
    skill_name = serializers.CharField(source='skill.name', read_only=True)
    
    class Meta:
        model = AgentSkillAssignment
        fields = [
            'id', 'agent', 'agent_name', 'skill', 'skill_name', 
            'proficiency_level', 'assigned_at', 'is_active'
        ]
        read_only_fields = ['assigned_at']


class AgentListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing agents with basic information.
    """
    role_name = serializers.CharField(source='role.display_name', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    team_name = serializers.CharField(source='team.name', read_only=True)
    current_status = AgentStatusSerializer(read_only=True)
    supervisor_name = serializers.CharField(source='supervisor.get_full_name', read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'first_name', 'last_name', 'email', 'employee_id',
            'phone_number', 'extension', 'role_name', 'department_name', 'team_name',
            'agent_skill_level', 'max_concurrent_calls', 'is_available', 'is_active',
            'current_status', 'supervisor_name', 'last_login', 'created_at'
        ]


class AgentDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for detailed agent information including skills and status.
    """
    role = UserRoleSerializer(read_only=True)
    department = DepartmentSerializer(read_only=True)
    team = TeamSerializer(read_only=True)
    current_status = AgentStatusSerializer(read_only=True)
    supervisor = serializers.SerializerMethodField()
    skill_assignments = AgentSkillAssignmentSerializer(many=True, read_only=True)
    supervised_agents = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'first_name', 'last_name', 'email', 'employee_id',
            'phone_number', 'extension', 'avatar', 'bio', 'timezone',
            'email_notifications', 'desktop_notifications', 'sound_notifications',
            'preferred_language', 'role', 'department', 'team', 'supervisor',
            'agent_skill_level', 'max_concurrent_calls', 'is_available', 'is_active',
            'current_status', 'skill_assignments', 'supervised_agents',
            'last_login', 'created_at', 'updated_at'
        ]
    
    def get_supervisor(self, obj):
        """Get supervisor information if exists."""
        if obj.supervisor:
            return {
                'id': obj.supervisor.id,
                'name': obj.supervisor.get_full_name(),
                'username': obj.supervisor.username,
                'email': obj.supervisor.email
            }
        return None
    
    def get_supervised_agents(self, obj):
        """Get list of supervised agents if user is a supervisor."""
        if obj.is_supervisor():
            agents = obj.get_supervised_agents()
            return [{'id': agent.id, 'name': agent.get_full_name()} for agent in agents]
        return []
