"""
WebSocket consumers for agent-related real-time functionality.

This module implements WebSocket consumers for handling agent presence,
status updates, and real-time communication in the call center system.
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


class AgentConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for agent presence and real-time status updates.
    
    Handles:
    - Agent authentication and authorization
    - Agent presence status (online, busy, available, break, etc.)
    - Real-time status broadcasting to supervisors
    - Channel group management for agent-specific communication
    """

    async def connect(self):
        """
        Called when WebSocket connection is established.
        Authenticates user and adds to appropriate channel groups.
        """
        self.agent_id = self.scope['url_route']['kwargs']['agent_id']
        self.user = self.scope['user']
        
        # Check if user is authenticated
        if not self.user.is_authenticated:
            logger.warning(f"Unauthenticated WebSocket connection attempt for agent {self.agent_id}")
            await self.close()
            return
        
        # Verify user has agent permissions and matches the agent_id
        if not await self.verify_agent_permissions():
            logger.warning(f"Unauthorized agent WebSocket connection attempt: {self.user.username} for agent {self.agent_id}")
            await self.close()
            return
        
        # Channel group names for different types of communications
        self.agent_group_name = f'agent_{self.agent_id}'
        self.agents_group_name = 'agents_all'  # For broadcasting to all agents
        self.supervisors_group_name = 'supervisors'  # For supervisor notifications
        
        # Add to channel groups
        await self.channel_layer.group_add(
            self.agent_group_name,
            self.channel_name
        )
        
        await self.channel_layer.group_add(
            self.agents_group_name,
            self.channel_name
        )
        
        # Accept the WebSocket connection
        await self.accept()
        
        # Set agent as online and broadcast presence update
        await self.update_agent_status('online')
        
        logger.info(f"Agent {self.agent_id} WebSocket connected")

    async def disconnect(self, close_code):
        """
        Called when WebSocket connection is closed.
        Updates agent status and removes from channel groups.
        """
        if hasattr(self, 'agent_group_name'):
            # Remove from channel groups
            await self.channel_layer.group_discard(
                self.agent_group_name,
                self.channel_name
            )
            
            await self.channel_layer.group_discard(
                self.agents_group_name,
                self.channel_name
            )
            
            # Set agent as offline and broadcast presence update
            await self.update_agent_status('offline')
            
            logger.info(f"Agent {self.agent_id} WebSocket disconnected with code {close_code}")

    async def receive(self, text_data):
        """
        Called when a message is received from WebSocket.
        Handles various agent actions and status updates.
        """
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')
            
            # Handle different message types
            if message_type == 'status_update':
                await self.handle_status_update(text_data_json)
            elif message_type == 'heartbeat':
                await self.handle_heartbeat(text_data_json)
            elif message_type == 'call_action':
                await self.handle_call_action(text_data_json)
            else:
                logger.warning(f"Unknown message type received from agent {self.agent_id}: {message_type}")
                await self.send_error("Unknown message type")
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received from agent {self.agent_id}")
            await self.send_error("Invalid JSON format")
        except Exception as e:
            logger.error(f"Error processing message from agent {self.agent_id}: {str(e)}")
            await self.send_error("Error processing message")

    async def handle_status_update(self, data):
        """
        Handle agent status updates (available, busy, break, etc.)
        """
        new_status = data.get('status')
        valid_statuses = ['available', 'busy', 'break', 'wrapup', 'offline']
        
        if new_status not in valid_statuses:
            await self.send_error(f"Invalid status: {new_status}")
            return
        
        # Update agent status in database
        await self.update_agent_status(new_status)
        
        # Send confirmation back to agent
        await self.send(text_data=json.dumps({
            'type': 'status_updated',
            'status': new_status,
            'timestamp': await self.get_current_timestamp()
        }))

    async def handle_heartbeat(self, data):
        """
        Handle heartbeat messages to keep connection alive
        """
        await self.send(text_data=json.dumps({
            'type': 'heartbeat_ack',
            'timestamp': await self.get_current_timestamp()
        }))

    async def handle_call_action(self, data):
        """
        Handle call-related actions from agents
        """
        action = data.get('action')
        call_id = data.get('call_id')
        
        # This will be expanded when call management is implemented
        logger.info(f"Agent {self.agent_id} call action: {action} for call {call_id}")
        
        await self.send(text_data=json.dumps({
            'type': 'call_action_ack',
            'action': action,
            'call_id': call_id,
            'timestamp': await self.get_current_timestamp()
        }))

    # Channel layer group message handlers
    async def agent_notification(self, event):
        """
        Handler for messages sent to specific agent group
        """
        await self.send(text_data=json.dumps(event['message']))

    async def broadcast_message(self, event):
        """
        Handler for broadcast messages to all agents
        """
        await self.send(text_data=json.dumps(event['message']))

    async def system_alert(self, event):
        """
        Handler for system-wide alerts
        """
        await self.send(text_data=json.dumps({
            'type': 'system_alert',
            'message': event['message'],
            'level': event.get('level', 'info'),
            'timestamp': await self.get_current_timestamp()
        }))

    # Helper methods
    @database_sync_to_async
    def verify_agent_permissions(self):
        """
        Verify that the authenticated user has permission to access this agent channel
        """
        try:
            # Check if user is an agent and has access to this agent_id
            # This assumes the User model has agent-related fields or relationships
            user = User.objects.get(id=self.user.id)
            
            # For now, allow if user is authenticated and agent_id matches user id
            # This should be enhanced based on your specific agent model structure
            return str(user.id) == str(self.agent_id) or user.is_staff
            
        except ObjectDoesNotExist:
            return False

    @database_sync_to_async
    def update_agent_status(self, status):
        """
        Update agent status in database and broadcast to supervisors
        """
        try:
            # This would update agent status in your agent model
            # For now, we'll just log the status change
            logger.info(f"Agent {self.agent_id} status updated to: {status}")
            
            # Broadcast status change to supervisors
            from channels.layers import get_channel_layer
            channel_layer = get_channel_layer()
            
            # Send to supervisors group (will be implemented in supervisor consumer)
            sync_to_async(channel_layer.group_send)(
                'supervisors',
                {
                    'type': 'agent_status_update',
                    'message': {
                        'type': 'agent_status_change',
                        'agent_id': self.agent_id,
                        'status': status,
                        'timestamp': self.get_current_timestamp_sync()
                    }
                }
            )
            
        except Exception as e:
            logger.error(f"Error updating agent status: {str(e)}")

    @sync_to_async
    def get_current_timestamp(self):
        """
        Get current timestamp for messages
        """
        from datetime import datetime
        return datetime.now().isoformat()

    def get_current_timestamp_sync(self):
        """
        Synchronous version of get_current_timestamp
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
            'timestamp': await self.get_current_timestamp()
        }))


class SupervisorConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for supervisor dashboard and monitoring functionality.
    
    Handles:
    - Real-time dashboard updates for supervisors
    - Agent monitoring and supervision
    - Campaign statistics and performance metrics
    - System-wide alerts and notifications
    - Live call monitoring interface
    """

    async def connect(self):
        """
        Called when WebSocket connection is established.
        Authenticates supervisor and sets up monitoring channel groups.
        """
        self.supervisor_id = self.scope['url_route']['kwargs']['supervisor_id']
        self.user = self.scope['user']
        
        # Check if user is authenticated
        if not self.user.is_authenticated:
            logger.warning(f"Unauthenticated WebSocket connection attempt for supervisor {self.supervisor_id}")
            await self.close()
            return
        
        # Verify user has supervisor permissions
        if not await self.verify_supervisor_permissions():
            logger.warning(f"Unauthorized supervisor WebSocket connection attempt: {self.user.username} for supervisor {self.supervisor_id}")
            await self.close()
            return
        
        # Channel group names for supervisor communications
        self.supervisor_group_name = f'supervisor_{self.supervisor_id}'
        self.supervisors_group_name = 'supervisors'  # All supervisors
        self.dashboard_group_name = 'dashboard_updates'  # Dashboard-specific updates
        
        # Add to channel groups
        await self.channel_layer.group_add(
            self.supervisor_group_name,
            self.channel_name
        )
        
        await self.channel_layer.group_add(
            self.supervisors_group_name,
            self.channel_name
        )
        
        await self.channel_layer.group_add(
            self.dashboard_group_name,
            self.channel_name
        )
        
        # Accept the WebSocket connection
        await self.accept()
        
        # Send initial dashboard data
        await self.send_dashboard_data()
        
        logger.info(f"Supervisor {self.supervisor_id} WebSocket connected")

    async def disconnect(self, close_code):
        """
        Called when WebSocket connection is closed.
        Removes from channel groups and logs disconnection.
        """
        if hasattr(self, 'supervisor_group_name'):
            # Remove from channel groups
            await self.channel_layer.group_discard(
                self.supervisor_group_name,
                self.channel_name
            )
            
            await self.channel_layer.group_discard(
                self.supervisors_group_name,
                self.channel_name
            )
            
            await self.channel_layer.group_discard(
                self.dashboard_group_name,
                self.channel_name
            )
            
            logger.info(f"Supervisor {self.supervisor_id} WebSocket disconnected with code {close_code}")

    async def receive(self, text_data):
        """
        Called when a message is received from WebSocket.
        Handles supervisor actions and dashboard interactions.
        """
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')
            
            # Handle different message types
            if message_type == 'dashboard_request':
                await self.handle_dashboard_request(text_data_json)
            elif message_type == 'agent_action':
                await self.handle_agent_action(text_data_json)
            elif message_type == 'campaign_control':
                await self.handle_campaign_control(text_data_json)
            elif message_type == 'monitoring_request':
                await self.handle_monitoring_request(text_data_json)
            elif message_type == 'report_request':
                await self.handle_report_request(text_data_json)
            elif message_type == 'alert_action':
                await self.handle_alert_action(text_data_json)
            elif message_type == 'heartbeat':
                await self.handle_heartbeat(text_data_json)
            else:
                logger.warning(f"Unknown message type received from supervisor {self.supervisor_id}: {message_type}")
                await self.send_error("Unknown message type")
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received from supervisor {self.supervisor_id}")
            await self.send_error("Invalid JSON format")
        except Exception as e:
            logger.error(f"Error processing message from supervisor {self.supervisor_id}: {str(e)}")
            await self.send_error("Error processing message")

    async def handle_dashboard_request(self, data):
        """
        Handle requests for dashboard data updates
        """
        request_type = data.get('request_type')
        valid_requests = ['agents_status', 'campaign_stats', 'call_metrics', 'system_health']
        
        if request_type not in valid_requests:
            await self.send_error(f"Invalid dashboard request: {request_type}")
            return
        
        # Get requested dashboard data
        dashboard_data = await self.get_dashboard_data(request_type)
        
        await self.send(text_data=json.dumps({
            'type': 'dashboard_data',
            'request_type': request_type,
            'data': dashboard_data,
            'timestamp': await self.get_current_timestamp()
        }))

    async def handle_agent_action(self, data):
        """
        Handle supervisor actions on agents (force status change, assign, etc.)
        """
        action = data.get('action')
        agent_id = data.get('agent_id')
        
        if not action or not agent_id:
            await self.send_error("Action and agent_id are required")
            return
        
        valid_actions = ['force_available', 'force_break', 'force_offline', 'assign_campaign', 'send_message']
        
        if action not in valid_actions:
            await self.send_error(f"Invalid agent action: {action}")
            return
        
        # Process supervisor action on agent
        success = await self.process_agent_action(action, agent_id, data)
        
        if success:
            # Notify agent and other supervisors
            await self.broadcast_supervisor_action('agent_action', {
                'action': action,
                'agent_id': agent_id,
                'supervisor_id': self.supervisor_id,
                'timestamp': await self.get_current_timestamp(),
                'additional_data': data.get('additional_data', {})
            })
            
            await self.send(text_data=json.dumps({
                'type': 'agent_action_success',
                'action': action,
                'agent_id': agent_id,
                'timestamp': await self.get_current_timestamp()
            }))
        else:
            await self.send_error(f"Failed to perform agent action: {action}")

    async def handle_campaign_control(self, data):
        """
        Handle campaign control actions from supervisor
        """
        action = data.get('action')
        campaign_id = data.get('campaign_id')
        
        valid_actions = ['start', 'pause', 'stop', 'adjust_pacing', 'reset_stats']
        
        if action not in valid_actions:
            await self.send_error(f"Invalid campaign action: {action}")
            return
        
        # Process campaign control action
        success = await self.process_campaign_control(action, campaign_id, data)
        
        if success:
            await self.broadcast_supervisor_action('campaign_control', {
                'action': action,
                'campaign_id': campaign_id,
                'supervisor_id': self.supervisor_id,
                'timestamp': await self.get_current_timestamp()
            })
            
            await self.send(text_data=json.dumps({
                'type': 'campaign_control_success',
                'action': action,
                'campaign_id': campaign_id,
                'timestamp': await self.get_current_timestamp()
            }))
        else:
            await self.send_error(f"Failed to perform campaign action: {action}")

    async def handle_monitoring_request(self, data):
        """
        Handle call monitoring requests from supervisor
        """
        action = data.get('action')
        call_id = data.get('call_id')
        
        valid_actions = ['start_monitoring', 'stop_monitoring', 'whisper', 'barge']
        
        if action not in valid_actions:
            await self.send_error(f"Invalid monitoring action: {action}")
            return
        
        # Process monitoring request
        success = await self.process_monitoring_action(action, call_id, data)
        
        if success:
            await self.send(text_data=json.dumps({
                'type': 'monitoring_success',
                'action': action,
                'call_id': call_id,
                'timestamp': await self.get_current_timestamp()
            }))
        else:
            await self.send_error(f"Failed to {action}")

    async def handle_report_request(self, data):
        """
        Handle real-time report requests
        """
        report_type = data.get('report_type')
        parameters = data.get('parameters', {})
        
        # Generate requested report
        report_data = await self.generate_report(report_type, parameters)
        
        await self.send(text_data=json.dumps({
            'type': 'report_data',
            'report_type': report_type,
            'data': report_data,
            'timestamp': await self.get_current_timestamp()
        }))

    async def handle_alert_action(self, data):
        """
        Handle supervisor actions on alerts (acknowledge, dismiss, escalate)
        """
        action = data.get('action')
        alert_id = data.get('alert_id')
        
        # Process alert action
        success = await self.process_alert_action(action, alert_id)
        
        if success:
            await self.send(text_data=json.dumps({
                'type': 'alert_action_success',
                'action': action,
                'alert_id': alert_id,
                'timestamp': await self.get_current_timestamp()
            }))
        else:
            await self.send_error(f"Failed to {action} alert")

    async def handle_heartbeat(self, data):
        """
        Handle heartbeat messages
        """
        await self.send(text_data=json.dumps({
            'type': 'heartbeat_ack',
            'timestamp': await self.get_current_timestamp()
        }))

    # Channel layer group message handlers
    async def agent_status_update(self, event):
        """
        Handler for agent status updates
        """
        await self.send(text_data=json.dumps(event['message']))

    async def dashboard_update(self, event):
        """
        Handler for dashboard updates
        """
        await self.send(text_data=json.dumps(event['message']))

    async def system_alert(self, event):
        """
        Handler for system alerts
        """
        await self.send(text_data=json.dumps({
            'type': 'system_alert',
            'message': event['message'],
            'level': event.get('level', 'info'),
            'timestamp': await self.get_current_timestamp()
        }))

    async def campaign_update(self, event):
        """
        Handler for campaign updates
        """
        await self.send(text_data=json.dumps(event['message']))

    async def call_event(self, event):
        """
        Handler for call events that supervisors should see
        """
        await self.send(text_data=json.dumps(event['message']))

    # Helper methods
    @database_sync_to_async
    def verify_supervisor_permissions(self):
        """
        Verify that the authenticated user has supervisor permissions
        """
        try:
            user = User.objects.get(id=self.user.id)
            # Check if user is supervisor and matches supervisor_id
            return (str(user.id) == str(self.supervisor_id) and user.is_staff) or user.is_superuser
            
        except ObjectDoesNotExist:
            return False

    async def send_dashboard_data(self):
        """
        Send initial dashboard data to connected supervisor
        """
        dashboard_data = await self.get_initial_dashboard_data()
        await self.send(text_data=json.dumps({
            'type': 'dashboard_initial',
            'data': dashboard_data,
            'timestamp': await self.get_current_timestamp()
        }))

    @database_sync_to_async
    def get_initial_dashboard_data(self):
        """
        Get initial dashboard data for supervisor
        """
        # This would fetch real dashboard data from database
        return {
            'agents_online': 0,
            'active_calls': 0,
            'campaigns_active': 0,
            'queue_size': 0,
            'system_health': 'good'
        }

    @database_sync_to_async
    def get_dashboard_data(self, request_type):
        """
        Get specific dashboard data based on request type
        """
        # Implement specific data fetching logic
        return {'placeholder': f'data for {request_type}'}

    async def process_agent_action(self, action, agent_id, data):
        """
        Process supervisor action on agent
        """
        logger.info(f"Supervisor {self.supervisor_id} performing {action} on agent {agent_id}")
        return True  # Placeholder

    async def process_campaign_control(self, action, campaign_id, data):
        """
        Process campaign control action
        """
        logger.info(f"Supervisor {self.supervisor_id} performing {action} on campaign {campaign_id}")
        return True  # Placeholder

    async def process_monitoring_action(self, action, call_id, data):
        """
        Process monitoring action
        """
        logger.info(f"Supervisor {self.supervisor_id} performing {action} on call {call_id}")
        return True  # Placeholder

    async def generate_report(self, report_type, parameters):
        """
        Generate real-time report data
        """
        return {'report': f'data for {report_type}', 'parameters': parameters}

    async def process_alert_action(self, action, alert_id):
        """
        Process alert action
        """
        logger.info(f"Supervisor {self.supervisor_id} performing {action} on alert {alert_id}")
        return True  # Placeholder

    async def broadcast_supervisor_action(self, action_type, action_data):
        """
        Broadcast supervisor actions to relevant parties
        """
        message = {
            'type': action_type,
            'data': action_data
        }
        
        # Send to all supervisors
        await self.channel_layer.group_send(
            self.supervisors_group_name,
            {'type': 'dashboard_update', 'message': message}
        )
        
        # Send to affected agents if applicable
        if 'agent_id' in action_data:
            await self.channel_layer.group_send(
                f'agent_{action_data["agent_id"]}',
                {'type': 'agent_notification', 'message': message}
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
        Send error message to the supervisor
        """
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': error_message,
            'timestamp': await self.get_current_timestamp()
        }))
