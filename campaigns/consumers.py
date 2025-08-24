"""
WebSocket consumers for campaign-related real-time functionality.

This module implements WebSocket consumers for handling campaign statistics,
performance metrics, and real-time campaign management in the call center system.
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


class CampaignConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for campaign statistics and management.
    
    Handles:
    - Real-time campaign performance statistics
    - Live campaign metrics (calls made, connects, drop rate, etc.)
    - Campaign status updates and control
    - Lead queue status and management
    - Pacing ratio adjustments and monitoring
    - Agent assignment and utilization tracking
    """

    async def connect(self):
        """
        Called when WebSocket connection is established.
        Authenticates user and sets up campaign-specific channel groups.
        """
        self.campaign_id = self.scope['url_route']['kwargs']['campaign_id']
        self.user = self.scope['user']
        
        # Check if user is authenticated
        if not self.user.is_authenticated:
            logger.warning(f"Unauthenticated WebSocket connection attempt for campaign {self.campaign_id}")
            await self.close()
            return
        
        # Verify user has permissions to monitor this campaign
        if not await self.verify_campaign_permissions():
            logger.warning(f"Unauthorized campaign WebSocket connection attempt: {self.user.username} for campaign {self.campaign_id}")
            await self.close()
            return
        
        # Channel group names for different types of communications
        self.campaign_group_name = f'campaign_{self.campaign_id}'
        self.campaigns_group_name = 'campaigns_all'  # For system-wide campaign events
        self.supervisors_group_name = 'supervisors'  # For supervisor notifications
        self.dashboard_group_name = 'dashboard_updates'  # For dashboard updates
        
        # Add to channel groups
        await self.channel_layer.group_add(
            self.campaign_group_name,
            self.channel_name
        )
        
        await self.channel_layer.group_add(
            self.campaigns_group_name,
            self.channel_name
        )
        
        # Accept the WebSocket connection
        await self.accept()
        
        # Send current campaign statistics
        await self.send_campaign_statistics()
        
        logger.info(f"Campaign {self.campaign_id} WebSocket connected for user {self.user.username}")

    async def disconnect(self, close_code):
        """
        Called when WebSocket connection is closed.
        Removes from channel groups and logs disconnection.
        """
        if hasattr(self, 'campaign_group_name'):
            # Remove from channel groups
            await self.channel_layer.group_discard(
                self.campaign_group_name,
                self.channel_name
            )
            
            await self.channel_layer.group_discard(
                self.campaigns_group_name,
                self.channel_name
            )
            
            logger.info(f"Campaign {self.campaign_id} WebSocket disconnected with code {close_code}")

    async def receive(self, text_data):
        """
        Called when a message is received from WebSocket.
        Handles campaign management actions and statistics requests.
        """
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')
            
            # Handle different message types
            if message_type == 'statistics_request':
                await self.handle_statistics_request(text_data_json)
            elif message_type == 'campaign_control':
                await self.handle_campaign_control(text_data_json)
            elif message_type == 'pacing_adjustment':
                await self.handle_pacing_adjustment(text_data_json)
            elif message_type == 'lead_management':
                await self.handle_lead_management(text_data_json)
            elif message_type == 'agent_assignment':
                await self.handle_agent_assignment(text_data_json)
            elif message_type == 'schedule_update':
                await self.handle_schedule_update(text_data_json)
            elif message_type == 'heartbeat':
                await self.handle_heartbeat(text_data_json)
            else:
                logger.warning(f"Unknown message type received for campaign {self.campaign_id}: {message_type}")
                await self.send_error("Unknown message type")
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received for campaign {self.campaign_id}")
            await self.send_error("Invalid JSON format")
        except Exception as e:
            logger.error(f"Error processing message for campaign {self.campaign_id}: {str(e)}")
            await self.send_error("Error processing message")

    async def handle_statistics_request(self, data):
        """
        Handle requests for campaign statistics updates
        """
        stats_type = data.get('stats_type')
        valid_types = ['performance', 'agents', 'leads', 'calls', 'realtime', 'summary']
        
        if stats_type not in valid_types:
            await self.send_error(f"Invalid statistics type: {stats_type}")
            return
        
        # Get requested statistics
        statistics = await self.get_campaign_statistics(stats_type)
        
        await self.send(text_data=json.dumps({
            'type': 'statistics_update',
            'stats_type': stats_type,
            'campaign_id': self.campaign_id,
            'data': statistics,
            'timestamp': await self.get_current_timestamp()
        }))

    async def handle_campaign_control(self, data):
        """
        Handle campaign control actions (start, pause, stop, reset)
        """
        action = data.get('action')
        valid_actions = ['start', 'pause', 'stop', 'reset', 'force_start', 'emergency_stop']
        
        if action not in valid_actions:
            await self.send_error(f"Invalid campaign action: {action}")
            return
        
        # Check if user has permission to control campaigns
        if not await self.can_control_campaign():
            await self.send_error(f"Insufficient permissions for campaign control: {action}")
            return
        
        # Process campaign control action
        success = await self.process_campaign_control(action, data)
        
        if success:
            # Broadcast campaign control event
            await self.broadcast_campaign_event('campaign_control', {
                'action': action,
                'campaign_id': self.campaign_id,
                'user': self.user.username,
                'timestamp': await self.get_current_timestamp(),
                'parameters': data.get('parameters', {})
            })
            
            await self.send(text_data=json.dumps({
                'type': 'campaign_control_success',
                'action': action,
                'campaign_id': self.campaign_id,
                'timestamp': await self.get_current_timestamp()
            }))
        else:
            await self.send_error(f"Failed to {action} campaign")

    async def handle_pacing_adjustment(self, data):
        """
        Handle pacing ratio adjustments for predictive dialing
        """
        adjustment_type = data.get('adjustment_type')  # 'auto', 'manual', 'emergency'
        new_ratio = data.get('pacing_ratio')
        
        if not adjustment_type or new_ratio is None:
            await self.send_error("Adjustment type and pacing ratio are required")
            return
        
        # Validate pacing ratio range
        if not (0.1 <= new_ratio <= 10.0):
            await self.send_error("Pacing ratio must be between 0.1 and 10.0")
            return
        
        # Check permissions for pacing adjustments
        if not await self.can_adjust_pacing():
            await self.send_error("Insufficient permissions for pacing adjustment")
            return
        
        # Process pacing adjustment
        success = await self.process_pacing_adjustment(adjustment_type, new_ratio, data)
        
        if success:
            # Broadcast pacing adjustment
            await self.broadcast_campaign_event('pacing_adjustment', {
                'adjustment_type': adjustment_type,
                'new_ratio': new_ratio,
                'campaign_id': self.campaign_id,
                'user': self.user.username,
                'timestamp': await self.get_current_timestamp()
            })
            
            await self.send(text_data=json.dumps({
                'type': 'pacing_adjustment_success',
                'new_ratio': new_ratio,
                'campaign_id': self.campaign_id,
                'timestamp': await self.get_current_timestamp()
            }))
        else:
            await self.send_error("Failed to adjust pacing ratio")

    async def handle_lead_management(self, data):
        """
        Handle lead queue management actions
        """
        action = data.get('action')
        valid_actions = ['reset_leads', 'skip_leads', 'priority_boost', 'add_leads', 'remove_leads']
        
        if action not in valid_actions:
            await self.send_error(f"Invalid lead management action: {action}")
            return
        
        # Check permissions
        if not await self.can_manage_leads():
            await self.send_error(f"Insufficient permissions for lead management: {action}")
            return
        
        # Process lead management action
        success = await self.process_lead_management(action, data)
        
        if success:
            await self.broadcast_campaign_event('lead_management', {
                'action': action,
                'campaign_id': self.campaign_id,
                'user': self.user.username,
                'timestamp': await self.get_current_timestamp(),
                'parameters': data.get('parameters', {})
            })
            
            await self.send(text_data=json.dumps({
                'type': 'lead_management_success',
                'action': action,
                'campaign_id': self.campaign_id,
                'timestamp': await self.get_current_timestamp()
            }))
        else:
            await self.send_error(f"Failed to {action}")

    async def handle_agent_assignment(self, data):
        """
        Handle agent assignment to campaigns
        """
        action = data.get('action')  # 'assign', 'unassign', 'reassign'
        agent_ids = data.get('agent_ids', [])
        
        if not action or not agent_ids:
            await self.send_error("Action and agent IDs are required")
            return
        
        # Check permissions
        if not await self.can_assign_agents():
            await self.send_error("Insufficient permissions for agent assignment")
            return
        
        # Process agent assignment
        success = await self.process_agent_assignment(action, agent_ids, data)
        
        if success:
            await self.broadcast_campaign_event('agent_assignment', {
                'action': action,
                'agent_ids': agent_ids,
                'campaign_id': self.campaign_id,
                'user': self.user.username,
                'timestamp': await self.get_current_timestamp()
            })
            
            await self.send(text_data=json.dumps({
                'type': 'agent_assignment_success',
                'action': action,
                'agent_ids': agent_ids,
                'campaign_id': self.campaign_id,
                'timestamp': await self.get_current_timestamp()
            }))
        else:
            await self.send_error(f"Failed to {action} agents")

    async def handle_schedule_update(self, data):
        """
        Handle campaign schedule updates
        """
        schedule_data = data.get('schedule')
        
        if not schedule_data:
            await self.send_error("Schedule data is required")
            return
        
        # Check permissions
        if not await self.can_update_schedule():
            await self.send_error("Insufficient permissions for schedule update")
            return
        
        # Process schedule update
        success = await self.process_schedule_update(schedule_data)
        
        if success:
            await self.broadcast_campaign_event('schedule_update', {
                'schedule': schedule_data,
                'campaign_id': self.campaign_id,
                'user': self.user.username,
                'timestamp': await self.get_current_timestamp()
            })
            
            await self.send(text_data=json.dumps({
                'type': 'schedule_update_success',
                'campaign_id': self.campaign_id,
                'timestamp': await self.get_current_timestamp()
            }))
        else:
            await self.send_error("Failed to update schedule")

    async def handle_heartbeat(self, data):
        """
        Handle heartbeat messages
        """
        await self.send(text_data=json.dumps({
            'type': 'heartbeat_ack',
            'campaign_id': self.campaign_id,
            'timestamp': await self.get_current_timestamp()
        }))

    # Channel layer group message handlers
    async def campaign_statistics_update(self, event):
        """
        Handler for campaign statistics updates from external systems
        """
        await self.send(text_data=json.dumps(event['message']))

    async def campaign_event(self, event):
        """
        Handler for general campaign events
        """
        await self.send(text_data=json.dumps(event['message']))

    async def system_alert(self, event):
        """
        Handler for system alerts related to campaigns
        """
        await self.send(text_data=json.dumps({
            'type': 'system_alert',
            'message': event['message'],
            'level': event.get('level', 'info'),
            'timestamp': await self.get_current_timestamp()
        }))

    # Helper methods
    @database_sync_to_async
    def verify_campaign_permissions(self):
        """
        Verify that the authenticated user has permission to access this campaign
        """
        try:
            # Check if user has access to this campaign
            # This should be implemented based on your campaign access control logic
            return True
            
        except Exception as e:
            logger.error(f"Error verifying campaign permissions: {str(e)}")
            return False

    @database_sync_to_async
    def can_control_campaign(self):
        """
        Check if user can control campaign operations
        """
        return self.user.is_staff or hasattr(self.user, 'is_supervisor')

    @database_sync_to_async
    def can_adjust_pacing(self):
        """
        Check if user can adjust pacing ratios
        """
        return self.user.is_staff or hasattr(self.user, 'is_supervisor')

    @database_sync_to_async
    def can_manage_leads(self):
        """
        Check if user can manage campaign leads
        """
        return self.user.is_staff or hasattr(self.user, 'is_supervisor')

    @database_sync_to_async
    def can_assign_agents(self):
        """
        Check if user can assign agents to campaigns
        """
        return self.user.is_staff or hasattr(self.user, 'is_supervisor')

    @database_sync_to_async
    def can_update_schedule(self):
        """
        Check if user can update campaign schedules
        """
        return self.user.is_staff or hasattr(self.user, 'is_supervisor')

    async def send_campaign_statistics(self):
        """
        Send current campaign statistics to connected client
        """
        statistics = await self.get_current_campaign_statistics()
        await self.send(text_data=json.dumps({
            'type': 'campaign_statistics',
            'campaign_id': self.campaign_id,
            'data': statistics,
            'timestamp': await self.get_current_timestamp()
        }))

    @database_sync_to_async
    def get_current_campaign_statistics(self):
        """
        Get current campaign statistics from database
        """
        try:
            # This would fetch real campaign statistics
            return {
                'status': 'active',
                'calls_made': 0,
                'calls_answered': 0,
                'connects': 0,
                'drop_rate': 0.0,
                'agents_assigned': 0,
                'agents_active': 0,
                'leads_remaining': 0,
                'pacing_ratio': 1.0,
                'answer_rate': 0.0
            }
        except Exception as e:
            logger.error(f"Error getting campaign statistics: {str(e)}")
            return {'status': 'unknown'}

    @database_sync_to_async
    def get_campaign_statistics(self, stats_type):
        """
        Get specific campaign statistics based on request type
        """
        # Implement specific statistics fetching logic
        return {'stats_type': stats_type, 'placeholder': 'data'}

    async def process_campaign_control(self, action, data):
        """
        Process campaign control action
        """
        logger.info(f"Processing campaign control {action} for campaign {self.campaign_id}")
        return True  # Placeholder

    async def process_pacing_adjustment(self, adjustment_type, new_ratio, data):
        """
        Process pacing ratio adjustment
        """
        logger.info(f"Processing pacing adjustment {adjustment_type} to {new_ratio} for campaign {self.campaign_id}")
        return True  # Placeholder

    async def process_lead_management(self, action, data):
        """
        Process lead management action
        """
        logger.info(f"Processing lead management {action} for campaign {self.campaign_id}")
        return True  # Placeholder

    async def process_agent_assignment(self, action, agent_ids, data):
        """
        Process agent assignment
        """
        logger.info(f"Processing agent assignment {action} for agents {agent_ids} in campaign {self.campaign_id}")
        return True  # Placeholder

    async def process_schedule_update(self, schedule_data):
        """
        Process campaign schedule update
        """
        logger.info(f"Processing schedule update for campaign {self.campaign_id}")
        return True  # Placeholder

    async def broadcast_campaign_event(self, event_type, event_data):
        """
        Broadcast campaign events to relevant channel groups
        """
        message = {
            'type': event_type,
            'data': event_data
        }
        
        # Send to all campaign participants
        await self.channel_layer.group_send(
            self.campaign_group_name,
            {'type': 'campaign_event', 'message': message}
        )
        
        # Send to supervisors
        await self.channel_layer.group_send(
            self.supervisors_group_name,
            {'type': 'campaign_event', 'message': message}
        )
        
        # Send to dashboard
        await self.channel_layer.group_send(
            self.dashboard_group_name,
            {'type': 'dashboard_update', 'message': message}
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
            'campaign_id': self.campaign_id,
            'timestamp': await self.get_current_timestamp()
        }))
