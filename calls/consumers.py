"""
WebSocket consumers for call-related real-time functionality.

This module implements WebSocket consumers for handling call state management,
real-time call events, and live call monitoring in the call center system.
"""

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from asgiref.sync import sync_to_async
import logging

User = get_user_model()
logger = logging.getLogger(__name__)


class CallConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for call state management and real-time call events.
    
    Handles:
    - Real-time call state updates (ringing, answered, on-hold, ended, etc.)
    - Call event broadcasting to agents, supervisors, and monitoring systems
    - Live call monitoring and supervision features
    - Call recording status and controls
    - Call transfer and conference management
    """

    async def connect(self):
        """
        Called when WebSocket connection is established.
        Authenticates user and sets up call-specific channel groups.
        """
        self.call_id = self.scope['url_route']['kwargs']['call_id']
        self.user = self.scope['user']
        
        # Check if user is authenticated
        if not self.user.is_authenticated:
            logger.warning(f"Unauthenticated WebSocket connection attempt for call {self.call_id}")
            await self.close()
            return
        
        # Verify user has permissions to monitor this call
        if not await self.verify_call_permissions():
            logger.warning(f"Unauthorized call WebSocket connection attempt: {self.user.username} for call {self.call_id}")
            await self.close()
            return
        
        # Channel group names for different types of communications
        self.call_group_name = f'call_{self.call_id}'
        self.calls_group_name = 'calls_all'  # For system-wide call events
        self.agents_group_name = 'agents_all'  # For agent notifications
        self.supervisors_group_name = 'supervisors'  # For supervisor monitoring
        
        # Add to channel groups
        await self.channel_layer.group_add(
            self.call_group_name,
            self.channel_name
        )
        
        await self.channel_layer.group_add(
            self.calls_group_name,
            self.channel_name
        )
        
        # Accept the WebSocket connection
        await self.accept()
        
        # Send current call status to the connected client
        await self.send_call_status()
        
        logger.info(f"Call {self.call_id} WebSocket connected for user {self.user.username}")

    async def disconnect(self, close_code):
        """
        Called when WebSocket connection is closed.
        Removes from channel groups and logs disconnection.
        """
        if hasattr(self, 'call_group_name'):
            # Remove from channel groups
            await self.channel_layer.group_discard(
                self.call_group_name,
                self.channel_name
            )
            
            await self.channel_layer.group_discard(
                self.calls_group_name,
                self.channel_name
            )
            
            logger.info(f"Call {self.call_id} WebSocket disconnected with code {close_code}")

    async def receive(self, text_data):
        """
        Called when a message is received from WebSocket.
        Handles call control actions and monitoring requests.
        """
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')
            
            # Handle different message types
            if message_type == 'call_action':
                await self.handle_call_action(text_data_json)
            elif message_type == 'recording_control':
                await self.handle_recording_control(text_data_json)
            elif message_type == 'monitoring_request':
                await self.handle_monitoring_request(text_data_json)
            elif message_type == 'transfer_request':
                await self.handle_transfer_request(text_data_json)
            elif message_type == 'heartbeat':
                await self.handle_heartbeat(text_data_json)
            else:
                logger.warning(f"Unknown message type received for call {self.call_id}: {message_type}")
                await self.send_error("Unknown message type")
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received for call {self.call_id}")
            await self.send_error("Invalid JSON format")
        except Exception as e:
            logger.error(f"Error processing message for call {self.call_id}: {str(e)}")
            await self.send_error("Error processing message")

    async def handle_call_action(self, data):
        """
        Handle call control actions (answer, hangup, hold, unhold, etc.)
        """
        action = data.get('action')
        valid_actions = ['answer', 'hangup', 'hold', 'unhold', 'mute', 'unmute', 'transfer']
        
        if action not in valid_actions:
            await self.send_error(f"Invalid call action: {action}")
            return
        
        # Check if user has permission to perform this action
        if not await self.can_perform_call_action(action):
            await self.send_error(f"Insufficient permissions for action: {action}")
            return
        
        # Process the call action (this would integrate with telephony system)
        success = await self.process_call_action(action, data)
        
        if success:
            # Broadcast call action to all relevant parties
            await self.broadcast_call_event('call_action', {
                'action': action,
                'call_id': self.call_id,
                'user': self.user.username,
                'timestamp': await self.get_current_timestamp(),
                'additional_data': data.get('additional_data', {})
            })
            
            # Send confirmation back to sender
            await self.send(text_data=json.dumps({
                'type': 'call_action_success',
                'action': action,
                'call_id': self.call_id,
                'timestamp': await self.get_current_timestamp()
            }))
        else:
            await self.send_error(f"Failed to perform call action: {action}")

    async def handle_recording_control(self, data):
        """
        Handle call recording control (start, stop, pause, resume)
        """
        action = data.get('action')
        valid_actions = ['start', 'stop', 'pause', 'resume']
        
        if action not in valid_actions:
            await self.send_error(f"Invalid recording action: {action}")
            return
        
        # Check if user has permission to control recording
        if not await self.can_control_recording():
            await self.send_error("Insufficient permissions to control recording")
            return
        
        # Process recording control (integrate with recording system)
        success = await self.process_recording_control(action, data)
        
        if success:
            # Broadcast recording status change
            await self.broadcast_call_event('recording_status', {
                'action': action,
                'call_id': self.call_id,
                'user': self.user.username,
                'timestamp': await self.get_current_timestamp()
            })
            
            await self.send(text_data=json.dumps({
                'type': 'recording_control_success',
                'action': action,
                'call_id': self.call_id,
                'timestamp': await self.get_current_timestamp()
            }))
        else:
            await self.send_error(f"Failed to control recording: {action}")

    async def handle_monitoring_request(self, data):
        """
        Handle supervisor monitoring requests (listen, whisper, barge)
        """
        action = data.get('action')
        valid_actions = ['listen', 'whisper', 'barge', 'stop_monitoring']
        
        if action not in valid_actions:
            await self.send_error(f"Invalid monitoring action: {action}")
            return
        
        # Check if user has supervisor permissions
        if not await self.is_supervisor():
            await self.send_error("Insufficient permissions for monitoring")
            return
        
        # Process monitoring request
        success = await self.process_monitoring_request(action, data)
        
        if success:
            # Notify relevant parties about monitoring
            await self.broadcast_call_event('monitoring_change', {
                'action': action,
                'call_id': self.call_id,
                'supervisor': self.user.username,
                'timestamp': await self.get_current_timestamp()
            })
            
            await self.send(text_data=json.dumps({
                'type': 'monitoring_success',
                'action': action,
                'call_id': self.call_id,
                'timestamp': await self.get_current_timestamp()
            }))
        else:
            await self.send_error(f"Failed to {action}")

    async def handle_transfer_request(self, data):
        """
        Handle call transfer requests
        """
        transfer_type = data.get('transfer_type')  # 'blind', 'warm', 'conference'
        target = data.get('target')  # agent_id, phone_number, etc.
        
        if not transfer_type or not target:
            await self.send_error("Transfer type and target are required")
            return
        
        # Check if user can perform transfers
        if not await self.can_perform_transfer():
            await self.send_error("Insufficient permissions for call transfer")
            return
        
        # Process transfer request
        success = await self.process_transfer_request(transfer_type, target, data)
        
        if success:
            await self.broadcast_call_event('call_transfer', {
                'transfer_type': transfer_type,
                'target': target,
                'call_id': self.call_id,
                'user': self.user.username,
                'timestamp': await self.get_current_timestamp()
            })
            
            await self.send(text_data=json.dumps({
                'type': 'transfer_success',
                'transfer_type': transfer_type,
                'target': target,
                'call_id': self.call_id,
                'timestamp': await self.get_current_timestamp()
            }))
        else:
            await self.send_error("Failed to initiate transfer")

    async def handle_heartbeat(self, data):
        """
        Handle heartbeat messages to keep connection alive
        """
        await self.send(text_data=json.dumps({
            'type': 'heartbeat_ack',
            'call_id': self.call_id,
            'timestamp': await self.get_current_timestamp()
        }))

    # Channel layer group message handlers
    async def call_state_update(self, event):
        """
        Handler for call state updates from external systems
        """
        await self.send(text_data=json.dumps(event['message']))

    async def call_event(self, event):
        """
        Handler for general call events
        """
        await self.send(text_data=json.dumps(event['message']))

    async def system_alert(self, event):
        """
        Handler for system-wide alerts related to calls
        """
        await self.send(text_data=json.dumps({
            'type': 'system_alert',
            'message': event['message'],
            'level': event.get('level', 'info'),
            'timestamp': await self.get_current_timestamp()
        }))

    # Helper methods
    @database_sync_to_async
    def verify_call_permissions(self):
        """
        Verify that the authenticated user has permission to access this call
        """
        try:
            # This should check if the user is an agent assigned to this call,
            # a supervisor, or has other valid permissions
            # For now, allow authenticated users
            return True
            
        except Exception as e:
            logger.error(f"Error verifying call permissions: {str(e)}")
            return False

    @database_sync_to_async
    def can_perform_call_action(self, action):
        """
        Check if user can perform specific call actions
        """
        # Implement specific permission logic based on user role and call state
        return True

    @database_sync_to_async
    def can_control_recording(self):
        """
        Check if user can control call recording
        """
        return self.user.is_staff or hasattr(self.user, 'is_supervisor')

    @database_sync_to_async
    def is_supervisor(self):
        """
        Check if user is a supervisor
        """
        return self.user.is_staff or hasattr(self.user, 'is_supervisor')

    @database_sync_to_async
    def can_perform_transfer(self):
        """
        Check if user can perform call transfers
        """
        return True  # Implement based on your business rules

    async def send_call_status(self):
        """
        Send current call status to the connected client
        """
        call_status = await self.get_call_status()
        await self.send(text_data=json.dumps({
            'type': 'call_status',
            'call_id': self.call_id,
            'status': call_status,
            'timestamp': await self.get_current_timestamp()
        }))

    @database_sync_to_async
    def get_call_status(self):
        """
        Get current call status from database
        """
        try:
            # This would fetch call status from your call model
            # For now, return a placeholder status
            return {
                'state': 'active',
                'duration': 0,
                'recording': False,
                'on_hold': False
            }
        except Exception as e:
            logger.error(f"Error getting call status: {str(e)}")
            return {'state': 'unknown'}

    async def process_call_action(self, action, data):
        """
        Process call action with telephony system
        """
        # This would integrate with your telephony system (Asterisk, etc.)
        logger.info(f"Processing call action {action} for call {self.call_id}")
        return True  # Placeholder

    async def process_recording_control(self, action, data):
        """
        Process recording control with recording system
        """
        logger.info(f"Processing recording control {action} for call {self.call_id}")
        return True  # Placeholder

    async def process_monitoring_request(self, action, data):
        """
        Process supervisor monitoring request
        """
        logger.info(f"Processing monitoring request {action} for call {self.call_id}")
        return True  # Placeholder

    async def process_transfer_request(self, transfer_type, target, data):
        """
        Process call transfer request
        """
        logger.info(f"Processing transfer {transfer_type} to {target} for call {self.call_id}")
        return True  # Placeholder

    async def broadcast_call_event(self, event_type, event_data):
        """
        Broadcast call events to relevant channel groups
        """
        message = {
            'type': event_type,
            'data': event_data
        }
        
        # Send to all call participants
        await self.channel_layer.group_send(
            self.call_group_name,
            {'type': 'call_event', 'message': message}
        )
        
        # Send to supervisors
        await self.channel_layer.group_send(
            self.supervisors_group_name,
            {'type': 'call_event', 'message': message}
        )

    @sync_to_async
    def get_current_timestamp(self):
        """
        Get current timestamp for messages
        """
        from datetime import datetime
        return datetime.now().isoformat()

    async def send_error(self, error_message):
        """
        Send error message to the client
        """
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': error_message,
            'call_id': self.call_id,
            'timestamp': await self.get_current_timestamp()
        }))
