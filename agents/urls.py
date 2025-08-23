"""
URL configuration for the agents app.

This module defines URL patterns for authentication and user management endpoints.
"""

from django.urls import path
from . import views

app_name = 'agents'

urlpatterns = [
    # Authentication endpoints
    path('auth/register/', views.UserRegistrationView.as_view(), name='register'),
    path('auth/login/', views.UserLoginView.as_view(), name='login'),
    path('auth/logout/', views.UserLogoutView.as_view(), name='logout'),
    path('auth/token/refresh/', views.CustomTokenRefreshView.as_view(), name='token_refresh'),
    
    # User profile management
    path('auth/profile/', views.UserProfileView.as_view(), name='profile'),
    path('auth/password-change/', views.PasswordChangeView.as_view(), name='password_change'),
    path('auth/password-reset/request/', views.PasswordResetRequestView.as_view(), name='password_reset_request'),
    path('auth/password-reset/confirm/', views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('auth/status/', views.user_status, name='user_status'),
    
    # Organizational data endpoints
    path('departments/', views.DepartmentListView.as_view(), name='departments'),
    path('teams/', views.TeamListView.as_view(), name='teams'),
    path('roles/', views.UserRoleListView.as_view(), name='roles'),
    
    # Agent management endpoints
    path('agents/', views.AgentListView.as_view(), name='agent_list'),
    path('agents/<int:pk>/', views.AgentDetailView.as_view(), name='agent_detail'),
    path('agents/<int:agent_id>/dashboard/', views.agent_dashboard_stats, name='agent_dashboard'),
    
    # Agent status management endpoints
    path('agent-status/', views.AgentStatusListView.as_view(), name='agent_status_list'),
    path('agent-status/<int:pk>/', views.AgentStatusDetailView.as_view(), name='agent_status_detail'),
    path('agents/<int:agent_id>/status/', views.update_agent_status, name='update_agent_status'),
    
    # Agent skills management endpoints
    path('skills/', views.AgentSkillListCreateView.as_view(), name='agent_skill_list'),
    path('skills/<int:pk>/', views.AgentSkillDetailView.as_view(), name='agent_skill_detail'),
    path('skill-assignments/', views.AgentSkillAssignmentListView.as_view(), name='skill_assignment_list'),
    path('skill-assignments/<int:pk>/', views.AgentSkillAssignmentDetailView.as_view(), name='skill_assignment_detail'),
]
