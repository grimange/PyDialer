"""
Telephony views for PyDialer.

This module contains views for telephony integration including:
- AI events webhook endpoint with HMAC validation
- Real-time transcript processing
- Call event handling
"""
import hmac
import hashlib
import json
import logging
from functools import wraps

from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger('vicidial.telephony')
channel_layer = get_channel_layer()


def validate_hmac_signature(f):
    """
    Decorator to validate HMAC signature for webhook endpoints.
    
    This decorator validates the HMAC signature in the request headers
    to ensure the request is authentic and comes from a trusted source.
    """
    @wraps(f)
    def decorated_function(request, *args, **kwargs):
        # Get the signature from headers
        signature_header = request.META.get('HTTP_X_SIGNATURE_256')
        if not signature_header:
            logger.warning("AI webhook request missing HMAC signature")
            return HttpResponseForbidden(
                json.dumps({'error': 'Missing HMAC signature'}),
                content_type='application/json'
            )
        
        # Extract signature (remove 'sha256=' prefix if present)
        if signature_header.startswith('sha256='):
            provided_signature = signature_header[7:]
        else:
            provided_signature = signature_header
        
        # Get the webhook secret from settings
        webhook_secret = getattr(settings, 'AI_WEBHOOK_SECRET', None)
        if not webhook_secret:
            logger.error("AI_WEBHOOK_SECRET not configured in settings")
            return JsonResponse(
                {'error': 'Server configuration error'}, 
                status=500
            )
        
        # Calculate expected signature
        body = request.body
        expected_signature = hmac.new(
            webhook_secret.encode('utf-8'),
            body,
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures securely
        if not hmac.compare_digest(provided_signature, expected_signature):
            logger.warning(
                f"AI webhook HMAC validation failed. "
                f"Expected: {expected_signature}, Got: {provided_signature}"
            )
            return HttpResponseForbidden(
                json.dumps({'error': 'Invalid HMAC signature'}),
                content_type='application/json'
            )
        
        return f(request, *args, **kwargs)
    
    return decorated_function


@method_decorator(csrf_exempt, name='dispatch')
@method_decorator(require_http_methods(["POST"]), name='dispatch')
class AIEventsWebhookView(View):
    """
    AI Events Webhook endpoint for processing AI-generated events.
    
    This endpoint receives webhooks from the AI Media Gateway containing:
    - Real-time speech-to-text transcripts
    - Call event notifications
    - AI processing status updates
    
    All requests must include valid HMAC signature for security.
    """
    
    @validate_hmac_signature
    def post(self, request):
        """
        Handle AI events webhook POST requests.
        
        Expected payload format:
        {
            "event_type": "transcript" | "call_event" | "status_update",
            "call_id": "unique_call_identifier",
            "timestamp": "ISO_8601_timestamp",
            "data": {
                // Event-specific data
            }
        }
        """
        try:
            # Parse JSON payload
            try:
                payload = json.loads(request.body)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in AI webhook: {e}")
                return HttpResponseBadRequest(
                    json.dumps({'error': 'Invalid JSON payload'}),
                    content_type='application/json'
                )
            
            # Validate required fields
            required_fields = ['event_type', 'call_id', 'timestamp', 'data']
            for field in required_fields:
                if field not in payload:
                    logger.error(f"Missing required field in AI webhook: {field}")
                    return HttpResponseBadRequest(
                        json.dumps({'error': f'Missing required field: {field}'}),
                        content_type='application/json'
                    )
            
            event_type = payload['event_type']
            call_id = payload['call_id']
            timestamp = payload['timestamp']
            data = payload['data']
            
            logger.info(
                f"Received AI webhook event: type={event_type}, "
                f"call_id={call_id}, timestamp={timestamp}"
            )
            
            # Process different event types
            if event_type == 'transcript':
                self._handle_transcript_event(call_id, data, timestamp)
            elif event_type == 'call_event':
                self._handle_call_event(call_id, data, timestamp)
            elif event_type == 'status_update':
                self._handle_status_update(call_id, data, timestamp)
            else:
                logger.warning(f"Unknown AI event type: {event_type}")
                return HttpResponseBadRequest(
                    json.dumps({'error': f'Unknown event type: {event_type}'}),
                    content_type='application/json'
                )
            
            # Return success response
            return JsonResponse({
                'status': 'success',
                'message': 'Event processed successfully',
                'event_type': event_type,
                'call_id': call_id
            })
            
        except Exception as e:
            logger.error(f"Error processing AI webhook: {e}", exc_info=True)
            return JsonResponse(
                {'error': 'Internal server error'}, 
                status=500
            )
    
    def _handle_transcript_event(self, call_id, data, timestamp):
        """
        Handle real-time transcript events.
        
        Broadcasts transcript data to relevant WebSocket groups.
        """
        try:
            # Extract transcript data
            transcript_text = data.get('transcript', '')
            confidence = data.get('confidence', 0.0)
            is_final = data.get('is_final', False)
            speaker = data.get('speaker', 'unknown')
            
            # Log transcript event
            logger.info(
                f"Transcript for call {call_id}: "
                f"speaker={speaker}, confidence={confidence}, "
                f"is_final={is_final}, text='{transcript_text[:100]}...'"
            )
            
            # Broadcast to call-specific WebSocket group
            group_name = f"call_{call_id}"
            message = {
                'type': 'transcript_message',
                'call_id': call_id,
                'timestamp': timestamp,
                'transcript': transcript_text,
                'confidence': confidence,
                'is_final': is_final,
                'speaker': speaker
            }
            
            # Send to WebSocket group (this will be implemented in task 92)
            async_to_sync(channel_layer.group_send)(group_name, {
                'type': 'send_transcript',
                'message': message
            })
            
            logger.debug(f"Broadcasted transcript to group: {group_name}")
            
        except Exception as e:
            logger.error(f"Error handling transcript event: {e}", exc_info=True)
            raise
    
    def _handle_call_event(self, call_id, data, timestamp):
        """
        Handle call-related events from AI Media Gateway.
        
        Processes events like call start, end, hold, transfer, etc.
        """
        try:
            event_name = data.get('event', '')
            event_data = data.get('event_data', {})
            
            logger.info(
                f"Call event for call {call_id}: "
                f"event={event_name}, data={event_data}"
            )
            
            # Broadcast to call-specific WebSocket group
            group_name = f"call_{call_id}"
            message = {
                'type': 'call_event_message',
                'call_id': call_id,
                'timestamp': timestamp,
                'event': event_name,
                'event_data': event_data
            }
            
            async_to_sync(channel_layer.group_send)(group_name, {
                'type': 'send_call_event',
                'message': message
            })
            
            logger.debug(f"Broadcasted call event to group: {group_name}")
            
        except Exception as e:
            logger.error(f"Error handling call event: {e}", exc_info=True)
            raise
    
    def _handle_status_update(self, call_id, data, timestamp):
        """
        Handle AI processing status updates.
        
        Processes status updates like processing started, completed, failed, etc.
        """
        try:
            status = data.get('status', '')
            message = data.get('message', '')
            details = data.get('details', {})
            
            logger.info(
                f"AI status update for call {call_id}: "
                f"status={status}, message='{message}'"
            )
            
            # Broadcast to call-specific WebSocket group
            group_name = f"call_{call_id}"
            status_message = {
                'type': 'ai_status_message',
                'call_id': call_id,
                'timestamp': timestamp,
                'status': status,
                'message': message,
                'details': details
            }
            
            async_to_sync(channel_layer.group_send)(group_name, {
                'type': 'send_ai_status',
                'message': status_message
            })
            
            logger.debug(f"Broadcasted AI status to group: {group_name}")
            
        except Exception as e:
            logger.error(f"Error handling status update: {e}", exc_info=True)
            raise


# Health check endpoint for AI webhook
@csrf_exempt
@require_http_methods(["GET"])
def ai_webhook_health(request):
    """
    Health check endpoint for AI webhook.
    
    Returns service status and configuration check.
    """
    try:
        # Check if webhook secret is configured
        webhook_secret_configured = hasattr(settings, 'AI_WEBHOOK_SECRET') and \
                                   bool(getattr(settings, 'AI_WEBHOOK_SECRET', None))
        
        # Check if channel layer is available
        channel_layer_available = channel_layer is not None
        
        status = {
            'service': 'AI Events Webhook',
            'status': 'healthy',
            'webhook_secret_configured': webhook_secret_configured,
            'channel_layer_available': channel_layer_available,
            'timestamp': json.dumps(None)  # Will be replaced with actual timestamp
        }
        
        # Import datetime here to avoid circular imports
        from datetime import datetime
        status['timestamp'] = datetime.utcnow().isoformat() + 'Z'
        
        if not webhook_secret_configured or not channel_layer_available:
            status['status'] = 'degraded'
            status['warnings'] = []
            if not webhook_secret_configured:
                status['warnings'].append('AI_WEBHOOK_SECRET not configured')
            if not channel_layer_available:
                status['warnings'].append('Channel layer not available')
        
        http_status = 200 if status['status'] == 'healthy' else 503
        
        return JsonResponse(status, status=http_status)
        
    except Exception as e:
        logger.error(f"Error in AI webhook health check: {e}", exc_info=True)
        return JsonResponse({
            'service': 'AI Events Webhook',
            'status': 'unhealthy',
            'error': str(e)
        }, status=500)
