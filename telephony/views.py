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

from .ari_controller import ARIController
from .ami_controller import get_ami_controller, start_ami_controller, stop_ami_controller

logger = logging.getLogger('vicidial.telephony')
channel_layer = get_channel_layer()

# Global ARI controller instance
_ari_controller = None


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


# ARI Controller Service Management Endpoints

def get_ari_controller():
    """Get or create the global ARI controller instance."""
    global _ari_controller
    if _ari_controller is None:
        _ari_controller = ARIController(
            ari_url=getattr(settings, 'ASTERISK_ARI_URL', 'http://localhost:8088'),
            username=getattr(settings, 'ASTERISK_ARI_USERNAME', 'asterisk'),
            password=getattr(settings, 'ASTERISK_ARI_PASSWORD', 'asterisk'),
            app_name=getattr(settings, 'ASTERISK_STASIS_APP', 'pydialer')
        )
    return _ari_controller


@csrf_exempt
@require_http_methods(["POST"])
def ari_controller_start(request):
    """
    Start the ARI Controller service.
    
    Returns service status and connection information.
    """
    try:
        controller = get_ari_controller()
        
        if controller.connected:
            return JsonResponse({
                'status': 'already_running',
                'message': 'ARI Controller is already running',
                'connected': True
            })
        
        # Start controller asynchronously
        import asyncio
        
        async def start_controller():
            await controller.start()
        
        # Run in thread to avoid blocking the request
        import threading
        
        def run_start():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(start_controller())
            except Exception as e:
                logger.error(f"Error starting ARI controller: {e}")
            finally:
                loop.close()
        
        thread = threading.Thread(target=run_start, daemon=True)
        thread.start()
        thread.join(timeout=10)  # Wait up to 10 seconds
        
        return JsonResponse({
            'status': 'started' if controller.connected else 'starting',
            'message': 'ARI Controller start initiated',
            'connected': controller.connected,
            'ari_url': controller.ari_url,
            'app_name': controller.app_name
        })
        
    except Exception as e:
        logger.error(f"Error starting ARI controller: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': f'Failed to start ARI Controller: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def ari_controller_stop(request):
    """
    Stop the ARI Controller service.
    
    Returns shutdown status.
    """
    try:
        controller = get_ari_controller()
        
        if not controller.connected:
            return JsonResponse({
                'status': 'already_stopped',
                'message': 'ARI Controller is not running',
                'connected': False
            })
        
        # Stop controller asynchronously
        import asyncio
        
        async def stop_controller():
            await controller.stop()
        
        # Run in thread to avoid blocking the request
        import threading
        
        def run_stop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(stop_controller())
            except Exception as e:
                logger.error(f"Error stopping ARI controller: {e}")
            finally:
                loop.close()
        
        thread = threading.Thread(target=run_stop, daemon=True)
        thread.start()
        thread.join(timeout=10)  # Wait up to 10 seconds
        
        return JsonResponse({
            'status': 'stopped',
            'message': 'ARI Controller stopped successfully',
            'connected': controller.connected
        })
        
    except Exception as e:
        logger.error(f"Error stopping ARI controller: {e}", exc_info=True)
        return JsonResponse({
            'status': 'error',
            'message': f'Failed to stop ARI Controller: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def ari_controller_status(request):
    """
    Get ARI Controller service status.
    
    Returns detailed status information including connection state,
    active channels, and configuration.
    """
    try:
        controller = get_ari_controller()
        
        status_info = {
            'service': 'ARI Controller',
            'connected': controller.connected,
            'ari_url': controller.ari_url,
            'app_name': controller.app_name,
            'active_channels': len(controller.active_channels),
            'channel_list': list(controller.active_channels),
            'reconnect_attempts': controller.reconnect_attempts,
            'max_reconnect_attempts': controller.max_reconnect_attempts
        }
        
        # Import datetime here to avoid circular imports
        from datetime import datetime
        status_info['timestamp'] = datetime.utcnow().isoformat() + 'Z'
        
        if controller.connected:
            status_info['status'] = 'running'
            status_info['message'] = 'ARI Controller is running and connected'
        else:
            status_info['status'] = 'stopped'
            status_info['message'] = 'ARI Controller is not connected'
        
        http_status = 200 if controller.connected else 503
        
        return JsonResponse(status_info, status=http_status)
        
    except Exception as e:
        logger.error(f"Error getting ARI controller status: {e}", exc_info=True)
        return JsonResponse({
            'service': 'ARI Controller',
            'status': 'error',
            'message': f'Error retrieving status: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def ari_controller_test(request):
    """
    Test ARI Controller connection to Asterisk.
    
    Performs a connection test without starting the full service.
    """
    try:
        # Create a temporary controller for testing
        test_controller = ARIController(
            ari_url=getattr(settings, 'ASTERISK_ARI_URL', 'http://localhost:8088'),
            username=getattr(settings, 'ASTERISK_ARI_USERNAME', 'asterisk'),
            password=getattr(settings, 'ASTERISK_ARI_PASSWORD', 'asterisk'),
            app_name=getattr(settings, 'ASTERISK_STASIS_APP', 'pydialer')
        )
        
        # Test connection asynchronously
        import asyncio
        
        async def test_connection():
            try:
                # Test HTTP connection first
                import aiohttp
                timeout = aiohttp.ClientTimeout(total=5)
                async with aiohttp.ClientSession(
                    timeout=timeout,
                    auth=aiohttp.BasicAuth(test_controller.username, test_controller.password)
                ) as session:
                    url = f"{test_controller.ari_url}/ari/asterisk/info"
                    async with session.get(url) as response:
                        if response.status == 200:
                            asterisk_info = await response.json()
                            return {
                                'connection_test': True,
                                'asterisk_version': asterisk_info.get('version', 'unknown'),
                                'asterisk_info': asterisk_info
                            }
                        else:
                            return {
                                'connection_test': False,
                                'error': f'HTTP connection failed: {response.status}'
                            }
            except Exception as e:
                return {
                    'connection_test': False,
                    'error': str(e)
                }
        
        # Run test in thread
        import threading
        test_result = {}
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                test_result.update(loop.run_until_complete(test_connection()))
            except Exception as e:
                test_result['connection_test'] = False
                test_result['error'] = str(e)
            finally:
                loop.close()
        
        thread = threading.Thread(target=run_test)
        thread.start()
        thread.join(timeout=10)  # Wait up to 10 seconds
        
        if not test_result:
            test_result = {
                'connection_test': False,
                'error': 'Test timeout'
            }
        
        # Import datetime here
        from datetime import datetime
        test_result['timestamp'] = datetime.utcnow().isoformat() + 'Z'
        test_result['ari_url'] = test_controller.ari_url
        test_result['app_name'] = test_controller.app_name
        
        status_code = 200 if test_result.get('connection_test') else 503
        
        return JsonResponse(test_result, status=status_code)
        
    except Exception as e:
        logger.error(f"Error testing ARI controller connection: {e}", exc_info=True)
        return JsonResponse({
            'connection_test': False,
            'error': f'Test failed: {str(e)}'
        }, status=500)


# AMI Controller Management Endpoints

@csrf_exempt
@require_http_methods(["POST"])
def ami_controller_start(request):
    """
    Start AMI Controller service.
    
    Establishes connection to Asterisk Manager Interface and begins
    event processing for real-time call state updates.
    """
    try:
        controller = get_ami_controller()
        
        if controller and controller.connected:
            return JsonResponse({
                'service': 'AMI Controller',
                'status': 'already_running',
                'message': 'AMI Controller is already running',
                'host': controller.host,
                'port': controller.port
            })
        
        # Start controller asynchronously
        import asyncio
        import threading
        
        result = {}
        
        async def start_controller():
            try:
                controller = await start_ami_controller()
                return {
                    'success': True,
                    'host': controller.host,
                    'port': controller.port,
                    'connected': controller.connected,
                    'authenticated': controller.authenticated
                }
            except Exception as e:
                return {
                    'success': False,
                    'error': str(e)
                }
        
        def run_start():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result.update(loop.run_until_complete(start_controller()))
            except Exception as e:
                result['success'] = False
                result['error'] = str(e)
            finally:
                loop.close()
        
        thread = threading.Thread(target=run_start)
        thread.start()
        thread.join(timeout=30)  # Wait up to 30 seconds
        
        if result.get('success'):
            return JsonResponse({
                'service': 'AMI Controller',
                'status': 'started',
                'message': 'AMI Controller started successfully',
                'host': result.get('host'),
                'port': result.get('port'),
                'connected': result.get('connected'),
                'authenticated': result.get('authenticated')
            })
        else:
            return JsonResponse({
                'service': 'AMI Controller',
                'status': 'error',
                'message': f'Failed to start AMI Controller: {result.get("error", "Unknown error")}'
            }, status=500)
    
    except Exception as e:
        logger.error(f"Error starting AMI controller: {e}", exc_info=True)
        return JsonResponse({
            'service': 'AMI Controller',
            'status': 'error',
            'message': f'Error starting service: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def ami_controller_stop(request):
    """
    Stop AMI Controller service.
    
    Cleanly shuts down the AMI connection and stops event processing.
    """
    try:
        controller = get_ami_controller()
        
        if not controller or not controller.connected:
            return JsonResponse({
                'service': 'AMI Controller',
                'status': 'not_running',
                'message': 'AMI Controller is not running'
            })
        
        # Stop controller asynchronously
        import asyncio
        import threading
        
        result = {}
        
        async def stop_controller():
            try:
                await stop_ami_controller()
                return {'success': True}
            except Exception as e:
                return {'success': False, 'error': str(e)}
        
        def run_stop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result.update(loop.run_until_complete(stop_controller()))
            except Exception as e:
                result['success'] = False
                result['error'] = str(e)
            finally:
                loop.close()
        
        thread = threading.Thread(target=run_stop)
        thread.start()
        thread.join(timeout=15)  # Wait up to 15 seconds
        
        if result.get('success'):
            return JsonResponse({
                'service': 'AMI Controller',
                'status': 'stopped',
                'message': 'AMI Controller stopped successfully'
            })
        else:
            return JsonResponse({
                'service': 'AMI Controller',
                'status': 'error',
                'message': f'Failed to stop AMI Controller: {result.get("error", "Unknown error")}'
            }, status=500)
    
    except Exception as e:
        logger.error(f"Error stopping AMI controller: {e}", exc_info=True)
        return JsonResponse({
            'service': 'AMI Controller',
            'status': 'error',
            'message': f'Error stopping service: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def ami_controller_status(request):
    """
    Get AMI Controller service status.
    
    Returns detailed status information including connection state,
    authentication status, and configuration.
    """
    try:
        controller = get_ami_controller()
        
        if not controller:
            return JsonResponse({
                'service': 'AMI Controller',
                'status': 'stopped',
                'message': 'AMI Controller is not initialized',
                'connected': False,
                'authenticated': False
            }, status=503)
        
        # Get status asynchronously
        import asyncio
        import threading
        
        status_result = {}
        
        async def get_status():
            try:
                status = await controller.get_connection_status()
                return status
            except Exception as e:
                return {
                    'connected': False,
                    'authenticated': False,
                    'error': str(e)
                }
        
        def run_status():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                status_result.update(loop.run_until_complete(get_status()))
            except Exception as e:
                status_result['connected'] = False
                status_result['authenticated'] = False
                status_result['error'] = str(e)
            finally:
                loop.close()
        
        thread = threading.Thread(target=run_status)
        thread.start()
        thread.join(timeout=5)  # Wait up to 5 seconds
        
        status_info = {
            'service': 'AMI Controller',
            'connected': status_result.get('connected', False),
            'authenticated': status_result.get('authenticated', False),
            'host': status_result.get('host', 'unknown'),
            'port': status_result.get('port', 'unknown'),
            'reconnect_attempts': status_result.get('reconnect_attempts', 0),
            'pending_actions': status_result.get('pending_actions', 0),
            'event_handlers': status_result.get('event_handlers', 0)
        }
        
        # Import datetime here to avoid circular imports
        from datetime import datetime
        status_info['timestamp'] = datetime.utcnow().isoformat() + 'Z'
        
        if status_info['connected'] and status_info['authenticated']:
            status_info['status'] = 'running'
            status_info['message'] = 'AMI Controller is running and authenticated'
            http_status = 200
        elif status_info['connected']:
            status_info['status'] = 'connecting'
            status_info['message'] = 'AMI Controller is connected but not authenticated'
            http_status = 503
        else:
            status_info['status'] = 'stopped'
            status_info['message'] = 'AMI Controller is not connected'
            http_status = 503
        
        if 'error' in status_result:
            status_info['error'] = status_result['error']
        
        return JsonResponse(status_info, status=http_status)
        
    except Exception as e:
        logger.error(f"Error getting AMI controller status: {e}", exc_info=True)
        return JsonResponse({
            'service': 'AMI Controller',
            'status': 'error',
            'message': f'Error retrieving status: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def ami_controller_test(request):
    """
    Test AMI Controller connection to Asterisk.
    
    Performs a connection test without starting the full service.
    """
    try:
        # Import AMI Controller for testing
        from .ami_controller import AMIController
        
        # Create a temporary controller for testing
        ami_config = getattr(settings, 'AMI_CONFIG', {})
        test_controller = AMIController(
            host=ami_config.get('HOST', 'localhost'),
            port=ami_config.get('PORT', 5038),
            username=ami_config.get('USERNAME', 'pydialer'),
            password=ami_config.get('PASSWORD', 'pydialer123')
        )
        
        # Test connection asynchronously
        import asyncio
        import threading
        
        test_result = {}
        
        async def test_connection():
            try:
                # Try to connect and authenticate
                await test_controller._connect()
                await test_controller._authenticate()
                
                # Send a simple ping action
                response = await test_controller.send_action("Ping")
                
                # Clean up
                await test_controller.stop()
                
                if response and response.get('Response') == 'Success':
                    return {
                        'connection_test': True,
                        'authentication_test': True,
                        'ping_test': True
                    }
                else:
                    return {
                        'connection_test': True,
                        'authentication_test': True,
                        'ping_test': False,
                        'error': 'Ping action failed'
                    }
                    
            except Exception as e:
                # Clean up on error
                try:
                    await test_controller.stop()
                except:
                    pass
                return {
                    'connection_test': False,
                    'authentication_test': False,
                    'ping_test': False,
                    'error': str(e)
                }
        
        def run_test():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                test_result.update(loop.run_until_complete(test_connection()))
            except Exception as e:
                test_result.update({
                    'connection_test': False,
                    'authentication_test': False,
                    'ping_test': False,
                    'error': str(e)
                })
            finally:
                loop.close()
        
        thread = threading.Thread(target=run_test)
        thread.start()
        thread.join(timeout=15)  # Wait up to 15 seconds
        
        if not test_result:
            test_result = {
                'connection_test': False,
                'authentication_test': False,
                'ping_test': False,
                'error': 'Test timeout'
            }
        
        # Import datetime here
        from datetime import datetime
        test_result['timestamp'] = datetime.utcnow().isoformat() + 'Z'
        test_result['host'] = test_controller.host
        test_result['port'] = test_controller.port
        
        # Determine overall success
        overall_success = (test_result.get('connection_test', False) and 
                          test_result.get('authentication_test', False) and 
                          test_result.get('ping_test', False))
        
        status_code = 200 if overall_success else 503
        
        return JsonResponse(test_result, status=status_code)
        
    except Exception as e:
        logger.error(f"Error testing AMI controller connection: {e}", exc_info=True)
        return JsonResponse({
            'connection_test': False,
            'authentication_test': False,
            'ping_test': False,
            'error': f'Test failed: {str(e)}'
        }, status=500)
