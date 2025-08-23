"""
Custom exception handlers and error response formatting for PyDialer API.

This module provides standardized error responses across all API endpoints,
ensuring consistent error handling for the call center system.
"""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler
from django.http import Http404
from django.core.exceptions import PermissionDenied
from rest_framework.exceptions import (
    ValidationError, 
    PermissionDenied as DRFPermissionDenied,
    NotAuthenticated,
    AuthenticationFailed,
    NotFound,
    MethodNotAllowed,
    Throttled,
    UnsupportedMediaType,
    ParseError
)
import logging

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Custom exception handler that provides standardized error responses.
    
    This handler catches all exceptions and formats them into a consistent
    JSON response structure for better API client handling.
    
    Args:
        exc: The exception instance
        context: Context information including request, view, args, kwargs
        
    Returns:
        Response: Standardized error response with consistent format
    """
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)
    
    # Get request information for logging
    request = context.get('request')
    view = context.get('view')
    
    # If DRF didn't handle it, we handle it ourselves
    if response is None:
        # Handle Django's built-in exceptions
        if isinstance(exc, Http404):
            response_data = {
                'success': False,
                'error': {
                    'code': 'NOT_FOUND',
                    'message': 'Resource not found',
                    'details': str(exc)
                },
                'timestamp': _get_timestamp(),
                'path': request.path if request else None,
            }
            response = Response(response_data, status=status.HTTP_404_NOT_FOUND)
        
        elif isinstance(exc, PermissionDenied):
            response_data = {
                'success': False,
                'error': {
                    'code': 'PERMISSION_DENIED',
                    'message': 'Permission denied',
                    'details': str(exc)
                },
                'timestamp': _get_timestamp(),
                'path': request.path if request else None,
            }
            response = Response(response_data, status=status.HTTP_403_FORBIDDEN)
        
        else:
            # Handle unexpected errors
            logger.error(f"Unhandled exception in {view.__class__.__name__ if view else 'Unknown'}: {exc}", 
                        exc_info=True, extra={'request': request})
            
            response_data = {
                'success': False,
                'error': {
                    'code': 'INTERNAL_ERROR',
                    'message': 'An internal server error occurred',
                    'details': 'Please contact support if this error persists'
                },
                'timestamp': _get_timestamp(),
                'path': request.path if request else None,
            }
            response = Response(response_data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    else:
        # Standardize DRF exception responses
        custom_response_data = _format_drf_error(exc, response, request)
        response.data = custom_response_data
    
    # Log the error for monitoring
    _log_exception(exc, context, response)
    
    return response


def _format_drf_error(exc, response, request):
    """
    Format DRF exceptions into standardized response structure.
    
    Args:
        exc: Exception instance
        response: DRF response object
        request: Django request object
        
    Returns:
        dict: Standardized error response data
    """
    error_code = _get_error_code(exc)
    error_message = _get_error_message(exc)
    
    response_data = {
        'success': False,
        'error': {
            'code': error_code,
            'message': error_message,
            'details': _extract_error_details(response.data)
        },
        'timestamp': _get_timestamp(),
        'path': request.path if request else None,
    }
    
    # Add field-specific validation errors if present
    if isinstance(exc, ValidationError) and hasattr(response, 'data'):
        if isinstance(response.data, dict):
            field_errors = {}
            for field, errors in response.data.items():
                if field != 'non_field_errors':
                    field_errors[field] = errors if isinstance(errors, list) else [str(errors)]
            
            if field_errors:
                response_data['error']['field_errors'] = field_errors
            
            # Add non-field errors
            if 'non_field_errors' in response.data:
                response_data['error']['non_field_errors'] = response.data['non_field_errors']
    
    return response_data


def _get_error_code(exc):
    """Get standardized error code based on exception type."""
    error_code_map = {
        ValidationError: 'VALIDATION_ERROR',
        NotAuthenticated: 'NOT_AUTHENTICATED',
        AuthenticationFailed: 'AUTHENTICATION_FAILED',
        DRFPermissionDenied: 'PERMISSION_DENIED',
        NotFound: 'NOT_FOUND',
        MethodNotAllowed: 'METHOD_NOT_ALLOWED',
        Throttled: 'RATE_LIMIT_EXCEEDED',
        UnsupportedMediaType: 'UNSUPPORTED_MEDIA_TYPE',
        ParseError: 'PARSE_ERROR',
    }
    
    return error_code_map.get(type(exc), 'API_ERROR')


def _get_error_message(exc):
    """Get user-friendly error message based on exception type."""
    message_map = {
        ValidationError: 'Validation failed',
        NotAuthenticated: 'Authentication required',
        AuthenticationFailed: 'Authentication failed',
        DRFPermissionDenied: 'Permission denied',
        NotFound: 'Resource not found',
        MethodNotAllowed: 'Method not allowed',
        Throttled: 'Rate limit exceeded',
        UnsupportedMediaType: 'Unsupported media type',
        ParseError: 'Request data could not be parsed',
    }
    
    return message_map.get(type(exc), 'An error occurred')


def _extract_error_details(data):
    """Extract error details from DRF response data."""
    if isinstance(data, dict):
        if 'detail' in data:
            return str(data['detail'])
        elif 'non_field_errors' in data:
            return data['non_field_errors'][0] if data['non_field_errors'] else None
    elif isinstance(data, list):
        return data[0] if data else None
    
    return str(data) if data else None


def _get_timestamp():
    """Get current timestamp in ISO format."""
    from datetime import datetime
    return datetime.utcnow().isoformat() + 'Z'


def _log_exception(exc, context, response):
    """Log exception details for monitoring and debugging."""
    request = context.get('request')
    view = context.get('view')
    
    log_data = {
        'exception_type': exc.__class__.__name__,
        'status_code': response.status_code,
        'path': request.path if request else None,
        'method': request.method if request else None,
        'user': str(request.user) if request and hasattr(request, 'user') else None,
        'view': view.__class__.__name__ if view else None,
    }
    
    # Log at appropriate level based on status code
    if response.status_code >= 500:
        logger.error(f"Server error: {exc}", extra=log_data)
    elif response.status_code >= 400:
        logger.warning(f"Client error: {exc}", extra=log_data)
    else:
        logger.info(f"Exception handled: {exc}", extra=log_data)


class PyDialerAPIException(Exception):
    """
    Custom base exception for PyDialer-specific errors.
    
    This can be extended for domain-specific exceptions like:
    - CallCenterException
    - CampaignException  
    - AgentException
    - TelephonyException
    """
    def __init__(self, message, code=None, status_code=status.HTTP_400_BAD_REQUEST):
        self.message = message
        self.code = code or 'PYDIALER_ERROR'
        self.status_code = status_code
        super().__init__(message)


class CampaignException(PyDialerAPIException):
    """Exception for campaign-related errors."""
    def __init__(self, message, code=None):
        super().__init__(message, code or 'CAMPAIGN_ERROR')


class AgentException(PyDialerAPIException):
    """Exception for agent-related errors."""
    def __init__(self, message, code=None):
        super().__init__(message, code or 'AGENT_ERROR')


class CallException(PyDialerAPIException):
    """Exception for call-related errors."""
    def __init__(self, message, code=None):
        super().__init__(message, code or 'CALL_ERROR')


class TelephonyException(PyDialerAPIException):
    """Exception for telephony integration errors."""
    def __init__(self, message, code=None, status_code=status.HTTP_503_SERVICE_UNAVAILABLE):
        super().__init__(message, code or 'TELEPHONY_ERROR', status_code)
