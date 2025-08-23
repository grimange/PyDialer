"""
Views for the agents app.

This module contains views for user authentication, registration,
and profile management functionality using Django REST Framework and JWT.
"""

from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth import login, logout
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.contrib.auth.tokens import default_token_generator
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction

from .serializers import (
    UserRegistrationSerializer,
    UserLoginSerializer, 
    UserProfileSerializer,
    PasswordChangeSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    DepartmentSerializer,
    TeamSerializer,
    UserRoleSerializer,
    AgentStatusSerializer,
    AgentStatusUpdateSerializer,
    AgentSkillSerializer,
    AgentSkillAssignmentSerializer,
    AgentListSerializer,
    AgentDetailSerializer
)
from .models import User, Department, Team, UserRole, AgentStatus, AgentSkill, AgentSkillAssignment


class UserRegistrationView(APIView):
    """
    Create a new user account.
    
    This endpoint allows registration of new users with proper validation
    and role assignment. Returns user data and JWT tokens upon successful creation.
    """
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            try:
                with transaction.atomic():
                    user = serializer.save()
                    
                    # Create AgentStatus for the new user if they have agent role
                    if user.role and user.role.name.lower() in ['agent', 'supervisor']:
                        AgentStatus.objects.create(
                            user=user,
                            status='offline',
                            last_update=timezone.now()
                        )
                    
                    # Generate tokens for immediate login
                    refresh = RefreshToken.for_user(user)
                    access_token = refresh.access_token
                    
                    # Update last login
                    user.last_login = timezone.now()
                    user.save(update_fields=['last_login'])
                    
                    # Trigger login signal
                    user_logged_in.send(sender=user.__class__, request=request, user=user)
                    
                    return Response({
                        'success': True,
                        'message': 'User registered successfully',
                        'user': UserProfileSerializer(user).data,
                        'tokens': {
                            'access': str(access_token),
                            'refresh': str(refresh),
                        }
                    }, status=status.HTTP_201_CREATED)
                    
            except Exception as e:
                return Response({
                    'success': False,
                    'message': 'Registration failed',
                    'errors': {'non_field_errors': [str(e)]}
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({
            'success': False,
            'message': 'Registration failed',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class UserLoginView(APIView):
    """
    Authenticate user and return JWT tokens.
    
    This endpoint validates user credentials and returns access and refresh tokens
    upon successful authentication. Also updates user login tracking.
    """
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        if serializer.is_valid():
            try:
                user = serializer.validated_data['user']
                
                # Generate tokens
                refresh = RefreshToken.for_user(user)
                access_token = refresh.access_token
                
                # Update last login and login tracking
                user.last_login = timezone.now()
                user.save(update_fields=['last_login'])
                
                # Update agent status to available if user is an agent
                if hasattr(user, 'agent_status'):
                    user.agent_status.set_status('available', 'Logged in')
                elif user.role and user.role.name.lower() in ['agent', 'supervisor']:
                    # Create agent status if it doesn't exist
                    AgentStatus.objects.get_or_create(
                        user=user,
                        defaults={
                            'status': 'available',
                            'last_update': timezone.now(),
                            'status_reason': 'Logged in'
                        }
                    )
                
                # Trigger login signal
                user_logged_in.send(sender=user.__class__, request=request, user=user)
                
                return Response({
                    'success': True,
                    'message': 'Login successful',
                    'user': UserProfileSerializer(user).data,
                    'tokens': {
                        'access': str(access_token),
                        'refresh': str(refresh),
                    }
                }, status=status.HTTP_200_OK)
                
            except Exception as e:
                return Response({
                    'success': False,
                    'message': 'Login failed',
                    'errors': {'non_field_errors': [str(e)]}
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({
            'success': False,
            'message': 'Login failed',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class UserLogoutView(APIView):
    """
    Logout user and blacklist refresh token.
    
    This endpoint handles user logout by blacklisting the refresh token
    and updating agent status if applicable.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        try:
            refresh_token = request.data.get("refresh_token")
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            
            # Update agent status to offline if user is an agent
            user = request.user
            if hasattr(user, 'agent_status'):
                user.agent_status.set_status('offline', 'Logged out')
            
            # Trigger logout signal
            user_logged_out.send(sender=user.__class__, request=request, user=user)
            
            return Response({
                'success': True,
                'message': 'Logout successful'
            }, status=status.HTTP_200_OK)
            
        except (InvalidToken, TokenError) as e:
            return Response({
                'success': False,
                'message': 'Invalid token',
                'errors': {'token': [str(e)]}
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'message': 'Logout failed',
                'errors': {'non_field_errors': [str(e)]}
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    Retrieve and update user profile information.
    
    This endpoint allows authenticated users to view and update their profile data.
    """
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_object(self):
        return self.request.user
    
    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        if response.status_code == 200:
            return Response({
                'success': True,
                'message': 'Profile updated successfully',
                'user': response.data
            }, status=status.HTTP_200_OK)
        return response


class PasswordChangeView(APIView):
    """
    Change user password.
    
    This endpoint allows authenticated users to change their password
    with proper validation and security checks.
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        serializer = PasswordChangeSerializer(
            data=request.data,
            context={'request': request}
        )
        if serializer.is_valid():
            try:
                serializer.save()
                return Response({
                    'success': True,
                    'message': 'Password changed successfully'
                }, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({
                    'success': False,
                    'message': 'Password change failed',
                    'errors': {'non_field_errors': [str(e)]}
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({
            'success': False,
            'message': 'Password change failed',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class CustomTokenRefreshView(TokenRefreshView):
    """
    Custom token refresh view with enhanced response format.
    
    Extends the default JWT token refresh view to provide consistent
    response formatting with the rest of the API.
    """
    
    def post(self, request, *args, **kwargs):
        try:
            response = super().post(request, *args, **kwargs)
            if response.status_code == 200:
                return Response({
                    'success': True,
                    'message': 'Token refreshed successfully',
                    'tokens': {
                        'access': response.data['access'],
                        'refresh': response.data.get('refresh')  # May not be present if rotation is disabled
                    }
                }, status=status.HTTP_200_OK)
            return response
        except (InvalidToken, TokenError) as e:
            return Response({
                'success': False,
                'message': 'Token refresh failed',
                'errors': {'token': [str(e)]}
            }, status=status.HTTP_401_UNAUTHORIZED)


# Supporting views for organizational data
class DepartmentListView(generics.ListAPIView):
    """
    List all departments.
    """
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [permissions.IsAuthenticated]


class TeamListView(generics.ListAPIView):
    """
    List teams, optionally filtered by department.
    """
    serializer_class = TeamSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = Team.objects.all()
        department_id = self.request.query_params.get('department_id')
        if department_id:
            queryset = queryset.filter(department_id=department_id)
        return queryset


class UserRoleListView(generics.ListAPIView):
    """
    List all user roles.
    """
    queryset = UserRole.objects.all()
    serializer_class = UserRoleSerializer
    permission_classes = [permissions.IsAuthenticated]


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def user_status(request):
    """
    Get current user status and authentication information.
    
    This endpoint provides information about the current authenticated user
    and their session status.
    """
    user = request.user
    agent_status = None
    
    if hasattr(user, 'agent_status'):
        agent_status = {
            'status': user.agent_status.status,
            'status_reason': user.agent_status.status_reason,
            'last_update': user.agent_status.last_update,
            'is_available_for_calls': user.agent_status.is_available_for_calls(),
            'is_logged_in': user.agent_status.is_logged_in()
        }
    
    return Response({
        'success': True,
        'user': UserProfileSerializer(user).data,
        'agent_status': agent_status,
        'authenticated': True,
        'timestamp': timezone.now()
    }, status=status.HTTP_200_OK)


class PasswordResetRequestView(APIView):
    """
    Request password reset.
    
    This endpoint allows users to request a password reset by providing
    their email address. A reset token will be sent to their email if valid.
    """
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            user = serializer.get_user(email)
            
            if user:
                # Generate password reset token and uid
                token = default_token_generator.make_token(user)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                
                # Prepare email context
                context = {
                    'user': user,
                    'domain': request.get_host(),
                    'site_name': getattr(settings, 'SITE_NAME', 'PyDialer'),
                    'uid': uid,
                    'token': token,
                    'protocol': 'https' if request.is_secure() else 'http',
                }
                
                # Send password reset email
                try:
                    subject = f"Password Reset - {context['site_name']}"
                    
                    # Create email body
                    message = render_to_string('registration/password_reset_email.txt', context)
                    html_message = render_to_string('registration/password_reset_email.html', context)
                    
                    send_mail(
                        subject=subject,
                        message=message,
                        from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@pydialer.com'),
                        recipient_list=[email],
                        html_message=html_message,
                        fail_silently=False,
                    )
                    
                except Exception as e:
                    # Log the error but don't reveal it to the user for security
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Failed to send password reset email: {str(e)}")
            
            # Always return success to prevent email enumeration attacks
            return Response({
                'success': True,
                'message': 'If a valid email address was provided, a password reset link has been sent.'
            }, status=status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'message': 'Password reset request failed',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


class PasswordResetConfirmView(APIView):
    """
    Confirm password reset with token.
    
    This endpoint allows users to confirm their password reset by providing
    the token received via email along with their new password.
    """
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if serializer.is_valid():
            try:
                user = serializer.save()
                
                return Response({
                    'success': True,
                    'message': 'Password has been reset successfully. You can now login with your new password.'
                }, status=status.HTTP_200_OK)
                
            except Exception as e:
                return Response({
                    'success': False,
                    'message': 'Password reset failed',
                    'errors': {'non_field_errors': [str(e)]}
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({
            'success': False,
            'message': 'Password reset failed',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)


# Agent Management API Views
class AgentListView(generics.ListAPIView):
    """
    List all agents with filtering capabilities.
    
    Supports filtering by department, team, role, and status.
    """
    serializer_class = AgentListSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = User.objects.select_related(
            'role', 'department', 'team', 'supervisor', 'current_status'
        ).filter(role__name__in=['agent', 'supervisor'])
        
        # Filter by department
        department_id = self.request.query_params.get('department')
        if department_id:
            queryset = queryset.filter(department_id=department_id)
        
        # Filter by team
        team_id = self.request.query_params.get('team')
        if team_id:
            queryset = queryset.filter(team_id=team_id)
        
        # Filter by role
        role = self.request.query_params.get('role')
        if role:
            queryset = queryset.filter(role__name=role)
        
        # Filter by status
        agent_status = self.request.query_params.get('status')
        if agent_status:
            queryset = queryset.filter(current_status__status=agent_status)
        
        # Filter by active status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        return queryset.order_by('last_name', 'first_name')


class AgentDetailView(generics.RetrieveUpdateAPIView):
    """
    Retrieve and update agent details.
    
    Provides comprehensive agent information including skills and status.
    """
    serializer_class = AgentDetailSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return User.objects.select_related(
            'role', 'department', 'team', 'supervisor', 'current_status'
        ).prefetch_related('skill_assignments__skill').filter(
            role__name__in=['agent', 'supervisor']
        )


# Agent Status Management API Views
class AgentStatusListView(generics.ListAPIView):
    """
    List all agent statuses with filtering capabilities.
    """
    serializer_class = AgentStatusSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = AgentStatus.objects.select_related('agent').all()
        
        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        # Filter by department
        department_id = self.request.query_params.get('department')
        if department_id:
            queryset = queryset.filter(agent__department_id=department_id)
        
        # Filter by team
        team_id = self.request.query_params.get('team')
        if team_id:
            queryset = queryset.filter(agent__team_id=team_id)
        
        return queryset.order_by('agent__last_name', 'agent__first_name')


class AgentStatusDetailView(generics.RetrieveUpdateAPIView):
    """
    Retrieve and update specific agent status.
    """
    serializer_class = AgentStatusSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return AgentStatus.objects.select_related('agent').all()
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return AgentStatusUpdateSerializer
        return AgentStatusSerializer


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def update_agent_status(request, agent_id):
    """
    Update agent status by agent ID.
    
    This endpoint allows updating agent status with proper validation
    and uses the model's set_status method for consistency.
    """
    try:
        agent = User.objects.get(id=agent_id, role__name__in=['agent', 'supervisor'])
        agent_status, created = AgentStatus.objects.get_or_create(agent=agent)
        
        serializer = AgentStatusUpdateSerializer(agent_status, data=request.data)
        if serializer.is_valid():
            serializer.save()
            
            # Return updated status information
            response_serializer = AgentStatusSerializer(agent_status)
            return Response({
                'success': True,
                'message': 'Agent status updated successfully',
                'agent_status': response_serializer.data
            }, status=status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'message': 'Invalid status data',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
        
    except User.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Agent not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'message': 'Status update failed',
            'errors': {'non_field_errors': [str(e)]}
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Agent Skills Management API Views
class AgentSkillListCreateView(generics.ListCreateAPIView):
    """
    List and create agent skills.
    """
    queryset = AgentSkill.objects.all()
    serializer_class = AgentSkillSerializer
    permission_classes = [permissions.IsAuthenticated]


class AgentSkillDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, and delete agent skills.
    """
    queryset = AgentSkill.objects.all()
    serializer_class = AgentSkillSerializer
    permission_classes = [permissions.IsAuthenticated]


class AgentSkillAssignmentListView(generics.ListCreateAPIView):
    """
    List and create agent skill assignments.
    """
    serializer_class = AgentSkillAssignmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = AgentSkillAssignment.objects.select_related(
            'agent', 'skill'
        ).all()
        
        # Filter by agent
        agent_id = self.request.query_params.get('agent')
        if agent_id:
            queryset = queryset.filter(agent_id=agent_id)
        
        # Filter by skill
        skill_id = self.request.query_params.get('skill')
        if skill_id:
            queryset = queryset.filter(skill_id=skill_id)
        
        # Filter by active status
        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        return queryset.order_by('agent__last_name', 'skill__name')


class AgentSkillAssignmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update, and delete agent skill assignments.
    """
    queryset = AgentSkillAssignment.objects.select_related('agent', 'skill').all()
    serializer_class = AgentSkillAssignmentSerializer
    permission_classes = [permissions.IsAuthenticated]


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def agent_dashboard_stats(request, agent_id=None):
    """
    Get dashboard statistics for a specific agent or current user.
    
    Provides key metrics for agent performance and current status.
    """
    try:
        if agent_id:
            agent = User.objects.get(id=agent_id, role__name__in=['agent', 'supervisor'])
        else:
            agent = request.user
        
        # Get agent status
        agent_status = getattr(agent, 'current_status', None)
        
        # Get skill assignments
        skills = AgentSkillAssignment.objects.filter(
            agent=agent, is_active=True
        ).select_related('skill')
        
        stats = {
            'agent': {
                'id': agent.id,
                'name': agent.get_full_name(),
                'username': agent.username,
                'role': agent.role.display_name if agent.role else None,
                'department': agent.department.name if agent.department else None,
                'team': agent.team.name if agent.team else None,
            },
            'current_status': {
                'status': agent_status.status if agent_status else 'offline',
                'status_display': agent_status.get_status_display() if agent_status else 'Offline',
                'status_reason': agent_status.status_reason if agent_status else '',
                'status_changed_at': agent_status.status_changed_at if agent_status else None,
                'login_time': agent_status.login_time if agent_status else None,
                'is_available_for_calls': agent_status.is_available_for_calls() if agent_status else False,
                'is_logged_in': agent_status.is_logged_in() if agent_status else False,
            },
            'daily_stats': {
                'calls_handled': agent_status.calls_handled_today if agent_status else 0,
                'average_call_duration': str(agent_status.average_call_duration) if agent_status and agent_status.average_call_duration else None,
                'total_login_duration': str(agent_status.total_login_duration) if agent_status and agent_status.total_login_duration else None,
            },
            'skills': [
                {
                    'name': skill.skill.name,
                    'proficiency_level': skill.proficiency_level,
                    'assigned_at': skill.assigned_at
                } for skill in skills
            ]
        }
        
        return Response({
            'success': True,
            'stats': stats
        }, status=status.HTTP_200_OK)
        
    except User.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Agent not found'
        }, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({
            'success': False,
            'message': 'Failed to retrieve agent stats',
            'errors': {'non_field_errors': [str(e)]}
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
