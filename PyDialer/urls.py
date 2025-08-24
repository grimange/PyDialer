"""
URL configuration for PyDialer project.

This file routes URLs to views for the PyDialer call center system.
Includes API endpoints for authentication, agents, campaigns, calls, and leads.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def api_root(request, version=None):
    """
    API root endpoint that provides information about available endpoints.
    Version-aware endpoint that adapts to the requested API version.
    """
    api_version = version or request.version or 'v1'
    
    return JsonResponse({
        'success': True,
        'message': f'PyDialer API {api_version}',
        'endpoints': {
            'authentication': {
                'register': f'/api/{api_version}/agents/auth/register/',
                'login': f'/api/{api_version}/agents/auth/login/',
                'logout': f'/api/{api_version}/agents/auth/logout/',
                'token_refresh': f'/api/{api_version}/agents/auth/token/refresh/',
                'profile': f'/api/{api_version}/agents/auth/profile/',
                'password_change': f'/api/{api_version}/agents/auth/password-change/',
                'status': f'/api/{api_version}/agents/auth/status/',
            },
            'agents': {
                'departments': f'/api/{api_version}/agents/departments/',
                'teams': f'/api/{api_version}/agents/teams/',
                'roles': f'/api/{api_version}/agents/roles/',
            },
            'campaigns': f'/api/{api_version}/campaigns/',
            'calls': f'/api/{api_version}/calls/',
            'leads': f'/api/{api_version}/leads/',
            'admin': '/admin/',
        },
        'version': '1.0.0',
        'api_version': api_version,
        'documentation': f'/api/{api_version}/schema/',
    })


urlpatterns = [
    # Admin interface
    path('admin/', admin.site.urls),
    
    # API versioned routes
    path('api/<version>/', api_root, name='api_root'),
    
    # Authentication and agent management
    path('api/<version>/agents/', include('agents.urls')),
    
    # Campaign management
    path('api/<version>/campaigns/', include('campaigns.urls')),
    
    # Call management
    path('api/<version>/calls/', include('calls.urls')),
    
    # Lead management
    path('api/<version>/leads/', include('leads.urls')),
    
    # Reporting and statistics
    path('api/<version>/reporting/', include('reporting.urls')),
    
    # Default API root (backwards compatibility)
    path('api/', api_root, name='api_root_default'),
    
    # Health check endpoint
    path('health/', lambda request: JsonResponse({
        'status': 'healthy',
        'service': 'PyDialer API',
        'version': '1.0.0'
    }), name='health_check'),
]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
