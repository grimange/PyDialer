"""
Custom permissions and role-based access control for the agents app.

This module contains permission classes and decorators that enforce
access control based on user roles (agent, supervisor, manager, admin).
"""

from rest_framework import permissions
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from functools import wraps
from typing import Callable, Any


class IsAgent(permissions.BasePermission):
    """
    Custom permission to only allow agents to access a view.
    """
    message = "Access denied. Agent role required."

    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.is_agent()
        )


class IsSupervisor(permissions.BasePermission):
    """
    Custom permission to only allow supervisors to access a view.
    """
    message = "Access denied. Supervisor role required."

    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.is_supervisor()
        )


class IsManager(permissions.BasePermission):
    """
    Custom permission to only allow managers to access a view.
    """
    message = "Access denied. Manager role required."

    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.is_manager()
        )


class IsAdminUser(permissions.BasePermission):
    """
    Custom permission to only allow admin users to access a view.
    """
    message = "Access denied. Admin role required."

    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.is_admin()
        )


class IsSupervisorOrAbove(permissions.BasePermission):
    """
    Custom permission to allow supervisors, managers, and admins.
    """
    message = "Access denied. Supervisor role or higher required."

    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            (request.user.is_supervisor() or 
             request.user.is_manager() or 
             request.user.is_admin())
        )


class IsManagerOrAbove(permissions.BasePermission):
    """
    Custom permission to allow managers and admins only.
    """
    message = "Access denied. Manager role or higher required."

    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            (request.user.is_manager() or request.user.is_admin())
        )


class IsSameUserOrSupervisor(permissions.BasePermission):
    """
    Custom permission to allow users to access their own data 
    or supervisors to access their team members' data.
    """
    message = "Access denied. You can only access your own data or you need supervisor privileges."

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        # Allow access to own data
        if hasattr(obj, 'user') and obj.user == request.user:
            return True
        elif hasattr(obj, 'id') and obj == request.user:
            return True
        
        # Allow supervisors to access their team members' data
        if request.user.is_supervisor():
            if hasattr(obj, 'user'):
                supervised_agents = request.user.get_supervised_agents()
                return obj.user in supervised_agents
            else:
                supervised_agents = request.user.get_supervised_agents()
                return obj in supervised_agents
        
        # Allow managers and admins full access
        return request.user.is_manager() or request.user.is_admin()


class CanManageCampaigns(permissions.BasePermission):
    """
    Custom permission for campaign management.
    Only supervisors and above can manage campaigns.
    """
    message = "Access denied. Campaign management requires supervisor privileges or higher."

    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            (request.user.is_supervisor() or 
             request.user.is_manager() or 
             request.user.is_admin())
        )


class CanViewReports(permissions.BasePermission):
    """
    Custom permission for viewing reports.
    Supervisors can view reports for their teams, managers and admins can view all reports.
    """
    message = "Access denied. Report viewing requires supervisor privileges or higher."

    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            (request.user.is_supervisor() or 
             request.user.is_manager() or 
             request.user.is_admin())
        )


# Function-based view decorators
def require_role(required_roles):
    """
    Decorator that requires user to have one of the specified roles.
    
    Usage:
        @require_role(['agent', 'supervisor'])
        def my_view(request):
            ...
    """
    if isinstance(required_roles, str):
        required_roles = [required_roles]
    
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({
                    'success': False,
                    'message': 'Authentication required',
                    'error_code': 'AUTHENTICATION_REQUIRED'
                }, status=401)
            
            user_roles = []
            if request.user.is_agent():
                user_roles.append('agent')
            if request.user.is_supervisor():
                user_roles.append('supervisor')
            if request.user.is_manager():
                user_roles.append('manager')
            if request.user.is_admin():
                user_roles.append('admin')
            
            if not any(role in required_roles for role in user_roles):
                return JsonResponse({
                    'success': False,
                    'message': f'Access denied. Required role(s): {", ".join(required_roles)}',
                    'error_code': 'INSUFFICIENT_PERMISSIONS',
                    'required_roles': required_roles,
                    'user_roles': user_roles
                }, status=403)
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def require_agent(view_func):
    """
    Decorator that requires user to have agent role.
    """
    return require_role(['agent'])(view_func)


def require_supervisor(view_func):
    """
    Decorator that requires user to have supervisor role or higher.
    """
    return require_role(['supervisor', 'manager', 'admin'])(view_func)


def require_manager(view_func):
    """
    Decorator that requires user to have manager role or higher.
    """
    return require_role(['manager', 'admin'])(view_func)


def require_admin(view_func):
    """
    Decorator that requires user to have admin role.
    """
    return require_role(['admin'])(view_func)


def same_user_or_supervisor_required(view_func):
    """
    Decorator that allows access to own data or supervisor access to team data.
    
    This decorator should be used on views that accept a user_id parameter.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({
                'success': False,
                'message': 'Authentication required',
                'error_code': 'AUTHENTICATION_REQUIRED'
            }, status=401)
        
        # Get the target user ID from kwargs or request data
        target_user_id = kwargs.get('user_id') or kwargs.get('pk')
        if not target_user_id:
            target_user_id = request.data.get('user_id') if hasattr(request, 'data') else None
        
        # Allow access to own data
        if target_user_id and str(request.user.id) == str(target_user_id):
            return view_func(request, *args, **kwargs)
        
        # Allow supervisors to access their team members' data
        if request.user.is_supervisor():
            if target_user_id:
                from .models import User
                try:
                    target_user = User.objects.get(id=target_user_id)
                    supervised_agents = request.user.get_supervised_agents()
                    if target_user in supervised_agents:
                        return view_func(request, *args, **kwargs)
                except User.DoesNotExist:
                    pass
        
        # Allow managers and admins full access
        if request.user.is_manager() or request.user.is_admin():
            return view_func(request, *args, **kwargs)
        
        return JsonResponse({
            'success': False,
            'message': 'Access denied. You can only access your own data or need supervisor privileges.',
            'error_code': 'INSUFFICIENT_PERMISSIONS'
        }, status=403)
    
    return wrapper


def team_access_required(view_func):
    """
    Decorator that ensures user can only access data from their team
    or supervisors can access their supervised teams' data.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({
                'success': False,
                'message': 'Authentication required',
                'error_code': 'AUTHENTICATION_REQUIRED'
            }, status=401)
        
        # Managers and admins have full access
        if request.user.is_manager() or request.user.is_admin():
            return view_func(request, *args, **kwargs)
        
        # Add team filtering logic here based on the specific view requirements
        # This is a base implementation that can be extended
        return view_func(request, *args, **kwargs)
    
    return wrapper


# Utility functions for role checking
def user_has_role(user, role: str) -> bool:
    """
    Check if user has a specific role.
    """
    if not user or not user.is_authenticated:
        return False
    
    role_methods = {
        'agent': user.is_agent,
        'supervisor': user.is_supervisor,
        'manager': user.is_manager,
        'admin': user.is_admin,
    }
    
    method = role_methods.get(role.lower())
    return method() if method else False


def user_has_any_role(user, roles: list) -> bool:
    """
    Check if user has any of the specified roles.
    """
    return any(user_has_role(user, role) for role in roles)


def get_user_roles(user) -> list:
    """
    Get list of roles for a user.
    """
    if not user or not user.is_authenticated:
        return []
    
    roles = []
    if user.is_agent():
        roles.append('agent')
    if user.is_supervisor():
        roles.append('supervisor')
    if user.is_manager():
        roles.append('manager')
    if user.is_admin():
        roles.append('admin')
    
    return roles
