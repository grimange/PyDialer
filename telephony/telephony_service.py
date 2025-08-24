"""
Telephony Service Abstraction Layer for PyDialer.

This module provides a unified interface for telephony operations,
abstracting the underlying ARI and AMI implementations to provide
a clean API for call management, channel operations, and event handling.
"""

import asyncio
import logging
from typing import Dict, Optional, List, Any, Callable, Union
from datetime import datetime
from enum import Enum

from django.conf import settings
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .ari_controller import get_ari_controller, start_ari_controller, stop_ari_controller
from .ami_controller import get_ami_controller, start_ami_controller, stop_ami_controller

logger = logging.getLogger(__name__)


class CallState(Enum):
    """Enumeration of possible call states."""
    IDLE = "idle"
    RINGING = "ringing"
    UP = "up"
    BUSY = "busy"
    CONGESTED = "congested"
    HANGUP = "hangup"
    ANSWERED = "answered"
    FAILED = "failed"


class ChannelType(Enum):
    """Enumeration of channel types."""
    SIP = "SIP"
    PJSIP = "PJSIP"
    IAX2 = "IAX2"
    DAHDI = "DAHDI"
    LOCAL = "Local"


class CallDirection(Enum):
    """Enumeration of call directions."""
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    INTERNAL = "internal"


class TelephonyException(Exception):
    """Base exception for telephony operations."""
    pass


class CallInfo:
    """
    Represents information about a call/channel.
    """
    
    def __init__(
        self,
        channel_id: str,
        caller_id: str = "",
        called_number: str = "",
        state: CallState = CallState.IDLE,
        direction: CallDirection = CallDirection.OUTBOUND,
        channel_type: ChannelType = ChannelType.SIP,
        created_at: Optional[datetime] = None
    ):
        self.channel_id = channel_id
        self.caller_id = caller_id
        self.called_number = called_number
        self.state = state
        self.direction = direction
        self.channel_type = channel_type
        self.created_at = created_at or datetime.now()
        self.answered_at: Optional[datetime] = None
        self.hangup_at: Optional[datetime] = None
        self.hangup_cause: Optional[str] = None
        self.bridge_id: Optional[str] = None
        self.agent_id: Optional[str] = None
        self.campaign_id: Optional[str] = None
        self.lead_id: Optional[str] = None
        
        # Additional metadata
        self.metadata: Dict[str, Any] = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert CallInfo to dictionary."""
        return {
            'channel_id': self.channel_id,
            'caller_id': self.caller_id,
            'called_number': self.called_number,
            'state': self.state.value,
            'direction': self.direction.value,
            'channel_type': self.channel_type.value,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'answered_at': self.answered_at.isoformat() if self.answered_at else None,
            'hangup_at': self.hangup_at.isoformat() if self.hangup_at else None,
            'hangup_cause': self.hangup_cause,
            'bridge_id': self.bridge_id,
            'agent_id': self.agent_id,
            'campaign_id': self.campaign_id,
            'lead_id': self.lead_id,
            'metadata': self.metadata
        }
    
    def __str__(self) -> str:
        return f"CallInfo({self.channel_id}, {self.state.value}, {self.caller_id} -> {self.called_number})"


class TelephonyService:
    """
    Unified telephony service providing abstraction layer over ARI and AMI.
    
    This service provides high-level telephony operations while managing
    the underlying ARI and AMI controllers automatically.
    """
    
    def __init__(self):
        self.active_calls: Dict[str, CallInfo] = {}
        self.event_handlers: Dict[str, List[Callable]] = {}
        self.channel_layer = get_channel_layer()
        
        # Service status
        self.started = False
        self.ari_enabled = True
        self.ami_enabled = True
        
        # Statistics
        self.total_calls = 0
        self.active_call_count = 0
        self.successful_calls = 0
        self.failed_calls = 0
        
        # Default event handlers
        self._setup_default_handlers()
    
    def _setup_default_handlers(self) -> None:
        """Set up default event handlers."""
        self.register_event_handler('call_created', self._handle_call_created)
        self.register_event_handler('call_answered', self._handle_call_answered)
        self.register_event_handler('call_hangup', self._handle_call_hangup)
        self.register_event_handler('call_bridged', self._handle_call_bridged)
        self.register_event_handler('call_unbridged', self._handle_call_unbridged)
    
    async def start(
        self,
        enable_ari: bool = True,
        enable_ami: bool = True,
        ari_config: Optional[Dict] = None,
        ami_config: Optional[Dict] = None
    ) -> None:
        """
        Start the telephony service and underlying controllers.
        
        Args:
            enable_ari: Whether to enable ARI controller
            enable_ami: Whether to enable AMI controller
            ari_config: ARI configuration override
            ami_config: AMI configuration override
        """
        logger.info("Starting Telephony Service")
        
        self.ari_enabled = enable_ari
        self.ami_enabled = enable_ami
        
        try:
            # Start ARI controller if enabled
            if self.ari_enabled:
                try:
                    ari_controller = get_ari_controller()
                    if not ari_controller or not ari_controller.connected:
                        logger.info("Starting ARI Controller...")
                        ari_controller = await start_ari_controller()
                        
                        # Register event handlers for ARI events
                        ari_controller.register_event_handler('StasisStart', self._handle_ari_stasis_start)
                        ari_controller.register_event_handler('StasisEnd', self._handle_ari_stasis_end)
                        ari_controller.register_event_handler('ChannelStateChange', self._handle_ari_channel_state_change)
                        ari_controller.register_event_handler('ChannelDestroyed', self._handle_ari_channel_destroyed)
                        
                    logger.info("ARI Controller is ready")
                except Exception as e:
                    logger.error(f"Failed to start ARI Controller: {e}")
                    self.ari_enabled = False
            
            # Start AMI controller if enabled
            if self.ami_enabled:
                try:
                    ami_controller = get_ami_controller()
                    if not ami_controller or not ami_controller.connected:
                        logger.info("Starting AMI Controller...")
                        ami_controller = await start_ami_controller()
                        
                        # Register event handlers for AMI events
                        ami_controller.register_event_handler('Newchannel', self._handle_ami_new_channel)
                        ami_controller.register_event_handler('Hangup', self._handle_ami_hangup)
                        ami_controller.register_event_handler('DialBegin', self._handle_ami_dial_begin)
                        ami_controller.register_event_handler('DialEnd', self._handle_ami_dial_end)
                        ami_controller.register_event_handler('Bridge', self._handle_ami_bridge)
                        
                    logger.info("AMI Controller is ready")
                except Exception as e:
                    logger.error(f"Failed to start AMI Controller: {e}")
                    self.ami_enabled = False
            
            if not self.ari_enabled and not self.ami_enabled:
                raise TelephonyException("Failed to start any telephony controllers")
            
            self.started = True
            logger.info("Telephony Service started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start Telephony Service: {e}")
            await self.stop()
            raise
    
    async def stop(self) -> None:
        """Stop the telephony service and cleanup resources."""
        logger.info("Stopping Telephony Service")
        
        self.started = False
        
        # Stop ARI controller
        if self.ari_enabled:
            try:
                await stop_ari_controller()
            except Exception as e:
                logger.error(f"Error stopping ARI Controller: {e}")
        
        # Stop AMI controller
        if self.ami_enabled:
            try:
                await stop_ami_controller()
            except Exception as e:
                logger.error(f"Error stopping AMI Controller: {e}")
        
        # Clear active calls
        self.active_calls.clear()
        
        logger.info("Telephony Service stopped")
    
    async def originate_call(
        self,
        endpoint: str,
        context: str,
        extension: str,
        priority: int = 1,
        caller_id: str = "",
        timeout: int = 30,
        variables: Optional[Dict[str, str]] = None,
        agent_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        lead_id: Optional[str] = None
    ) -> Optional[CallInfo]:
        """
        Originate an outbound call.
        
        Args:
            endpoint: Channel endpoint (e.g., 'SIP/1234567890@trunk')
            context: Dialplan context
            extension: Extension to dial
            priority: Dialplan priority
            caller_id: Caller ID to present
            timeout: Call timeout in seconds
            variables: Channel variables to set
            agent_id: Associated agent ID
            campaign_id: Associated campaign ID
            lead_id: Associated lead ID
            
        Returns:
            CallInfo object or None if failed
        """
        if not self.started:
            raise TelephonyException("Telephony service not started")
        
        # Prefer ARI for call origination
        if self.ari_enabled:
            ari_controller = get_ari_controller()
            if ari_controller and ari_controller.connected:
                try:
                    channel_info = await ari_controller.originate_call(
                        endpoint=endpoint,
                        context=context,
                        extension=extension,
                        priority=priority,
                        caller_id=caller_id,
                        timeout=timeout,
                        variables=variables or {}
                    )
                    
                    if channel_info:
                        # Create CallInfo object
                        call_info = CallInfo(
                            channel_id=channel_info.get('id', ''),
                            caller_id=caller_id,
                            called_number=extension,
                            state=CallState.RINGING,
                            direction=CallDirection.OUTBOUND,
                            channel_type=self._parse_channel_type(endpoint)
                        )
                        
                        # Set metadata
                        call_info.agent_id = agent_id
                        call_info.campaign_id = campaign_id
                        call_info.lead_id = lead_id
                        call_info.metadata.update(variables or {})
                        
                        # Track call
                        self.active_calls[call_info.channel_id] = call_info
                        self.total_calls += 1
                        self.active_call_count += 1
                        
                        # Fire event
                        await self._fire_event('call_created', call_info)
                        
                        logger.info(f"Call originated: {call_info}")
                        return call_info
                        
                except Exception as e:
                    logger.error(f"Failed to originate call via ARI: {e}")
                    self.failed_calls += 1
        
        # Fallback to AMI if ARI not available
        if self.ami_enabled:
            ami_controller = get_ami_controller()
            if ami_controller and ami_controller.connected:
                try:
                    # Build AMI Originate action
                    action_params = {
                        'Channel': endpoint,
                        'Context': context,
                        'Exten': extension,
                        'Priority': str(priority),
                        'Timeout': str(timeout * 1000),  # AMI uses milliseconds
                        'CallerID': caller_id or 'PyDialer'
                    }
                    
                    # Add variables
                    if variables:
                        for key, value in variables.items():
                            action_params[f'Variable'] = f'{key}={value}'
                    
                    response = await ami_controller.send_action('Originate', **action_params)
                    
                    if response and response.get('Response') == 'Success':
                        # Create CallInfo (channel ID will be updated when we get events)
                        call_info = CallInfo(
                            channel_id=f"pending_{self.total_calls}",  # Temporary ID
                            caller_id=caller_id,
                            called_number=extension,
                            state=CallState.RINGING,
                            direction=CallDirection.OUTBOUND,
                            channel_type=self._parse_channel_type(endpoint)
                        )
                        
                        # Set metadata
                        call_info.agent_id = agent_id
                        call_info.campaign_id = campaign_id
                        call_info.lead_id = lead_id
                        call_info.metadata.update(variables or {})
                        
                        # Track call
                        self.active_calls[call_info.channel_id] = call_info
                        self.total_calls += 1
                        self.active_call_count += 1
                        
                        # Fire event
                        await self._fire_event('call_created', call_info)
                        
                        logger.info(f"Call originated via AMI: {call_info}")
                        return call_info
                        
                except Exception as e:
                    logger.error(f"Failed to originate call via AMI: {e}")
                    self.failed_calls += 1
        
        raise TelephonyException("No available telephony controllers for call origination")
    
    async def hangup_call(self, channel_id: str, cause: str = "normal") -> bool:
        """
        Hangup a call.
        
        Args:
            channel_id: Channel ID to hangup
            cause: Hangup cause
            
        Returns:
            True if successful, False otherwise
        """
        if not self.started:
            raise TelephonyException("Telephony service not started")
        
        # Try ARI first
        if self.ari_enabled:
            ari_controller = get_ari_controller()
            if ari_controller and ari_controller.connected:
                try:
                    await ari_controller.hangup_channel(channel_id, reason=cause)
                    logger.info(f"Call hung up via ARI: {channel_id}")
                    return True
                except Exception as e:
                    logger.error(f"Failed to hangup call via ARI: {e}")
        
        # Try AMI
        if self.ami_enabled:
            ami_controller = get_ami_controller()
            if ami_controller and ami_controller.connected:
                try:
                    response = await ami_controller.send_action(
                        'Hangup',
                        Channel=channel_id,
                        Cause=cause
                    )
                    if response and response.get('Response') == 'Success':
                        logger.info(f"Call hung up via AMI: {channel_id}")
                        return True
                except Exception as e:
                    logger.error(f"Failed to hangup call via AMI: {e}")
        
        return False
    
    def get_call_info(self, channel_id: str) -> Optional[CallInfo]:
        """Get information about a specific call."""
        return self.active_calls.get(channel_id)
    
    def get_active_calls(self) -> List[CallInfo]:
        """Get list of all active calls."""
        return list(self.active_calls.values())
    
    def get_calls_by_agent(self, agent_id: str) -> List[CallInfo]:
        """Get calls associated with a specific agent."""
        return [call for call in self.active_calls.values() if call.agent_id == agent_id]
    
    def get_calls_by_campaign(self, campaign_id: str) -> List[CallInfo]:
        """Get calls associated with a specific campaign."""
        return [call for call in self.active_calls.values() if call.campaign_id == campaign_id]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get telephony service statistics."""
        return {
            'started': self.started,
            'ari_enabled': self.ari_enabled,
            'ami_enabled': self.ami_enabled,
            'total_calls': self.total_calls,
            'active_calls': self.active_call_count,
            'successful_calls': self.successful_calls,
            'failed_calls': self.failed_calls,
            'active_call_list': [call.to_dict() for call in self.active_calls.values()]
        }
    
    def register_event_handler(self, event_type: str, handler: Callable) -> None:
        """Register an event handler."""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)
        logger.debug(f"Registered telephony event handler: {event_type}")
    
    def unregister_event_handler(self, event_type: str, handler: Callable) -> None:
        """Unregister an event handler."""
        if event_type in self.event_handlers:
            try:
                self.event_handlers[event_type].remove(handler)
            except ValueError:
                pass
    
    async def _fire_event(self, event_type: str, call_info: CallInfo, **kwargs) -> None:
        """Fire a telephony event."""
        try:
            # Call registered handlers
            handlers = self.event_handlers.get(event_type, [])
            for handler in handlers:
                try:
                    await handler(call_info, **kwargs)
                except Exception as e:
                    logger.error(f"Error in telephony event handler {event_type}: {e}")
            
            # Broadcast via WebSocket
            if self.channel_layer:
                await self._broadcast_telephony_event(event_type, call_info, **kwargs)
                
        except Exception as e:
            logger.error(f"Error firing telephony event {event_type}: {e}")
    
    async def _broadcast_telephony_event(self, event_type: str, call_info: CallInfo, **kwargs) -> None:
        """Broadcast telephony event via WebSocket."""
        try:
            event_data = {
                'type': 'telephony_event',
                'event_type': event_type,
                'call_info': call_info.to_dict(),
                'timestamp': datetime.now().isoformat(),
                **kwargs
            }
            
            # Broadcast to supervisors
            await self.channel_layer.group_send(
                'supervisors',
                {
                    'type': 'telephony_event',
                    'data': event_data
                }
            )
            
            # Broadcast to specific agent if available
            if call_info.agent_id:
                await self.channel_layer.group_send(
                    f'agent_{call_info.agent_id}',
                    {
                        'type': 'telephony_event',
                        'data': event_data
                    }
                )
                
        except Exception as e:
            logger.error(f"Error broadcasting telephony event: {e}")
    
    def _parse_channel_type(self, endpoint: str) -> ChannelType:
        """Parse channel type from endpoint string."""
        if endpoint.startswith('SIP/'):
            return ChannelType.SIP
        elif endpoint.startswith('PJSIP/'):
            return ChannelType.PJSIP
        elif endpoint.startswith('IAX2/'):
            return ChannelType.IAX2
        elif endpoint.startswith('DAHDI/'):
            return ChannelType.DAHDI
        elif endpoint.startswith('Local/'):
            return ChannelType.LOCAL
        else:
            return ChannelType.SIP  # Default
    
    # Event handlers for default processing
    async def _handle_call_created(self, call_info: CallInfo) -> None:
        """Handle call created event."""
        logger.debug(f"Call created: {call_info}")
    
    async def _handle_call_answered(self, call_info: CallInfo) -> None:
        """Handle call answered event."""
        call_info.answered_at = datetime.now()
        call_info.state = CallState.UP
        self.successful_calls += 1
        logger.info(f"Call answered: {call_info}")
    
    async def _handle_call_hangup(self, call_info: CallInfo) -> None:
        """Handle call hangup event."""
        call_info.hangup_at = datetime.now()
        call_info.state = CallState.HANGUP
        
        # Remove from active calls
        if call_info.channel_id in self.active_calls:
            del self.active_calls[call_info.channel_id]
            self.active_call_count = max(0, self.active_call_count - 1)
        
        logger.info(f"Call hung up: {call_info}")
    
    async def _handle_call_bridged(self, call_info: CallInfo, bridge_id: str) -> None:
        """Handle call bridged event."""
        call_info.bridge_id = bridge_id
        logger.info(f"Call bridged: {call_info} -> {bridge_id}")
    
    async def _handle_call_unbridged(self, call_info: CallInfo) -> None:
        """Handle call unbridged event."""
        call_info.bridge_id = None
        logger.info(f"Call unbridged: {call_info}")
    
    # ARI Event Handlers
    async def _handle_ari_stasis_start(self, event) -> None:
        """Handle ARI StasisStart event."""
        channel_id = event.get('channel', {}).get('id', '')
        if channel_id and channel_id not in self.active_calls:
            # Create call info from ARI event
            channel = event.get('channel', {})
            call_info = CallInfo(
                channel_id=channel_id,
                caller_id=channel.get('caller', {}).get('number', ''),
                called_number=channel.get('dialplan', {}).get('exten', ''),
                state=CallState.RINGING,
                direction=CallDirection.INBOUND
            )
            
            self.active_calls[channel_id] = call_info
            self.total_calls += 1
            self.active_call_count += 1
            
            await self._fire_event('call_created', call_info)
    
    async def _handle_ari_stasis_end(self, event) -> None:
        """Handle ARI StasisEnd event."""
        channel_id = event.get('channel', {}).get('id', '')
        call_info = self.active_calls.get(channel_id)
        if call_info:
            await self._fire_event('call_hangup', call_info)
    
    async def _handle_ari_channel_state_change(self, event) -> None:
        """Handle ARI ChannelStateChange event."""
        channel_id = event.get('channel', {}).get('id', '')
        call_info = self.active_calls.get(channel_id)
        if call_info:
            state = event.get('channel', {}).get('state', '')
            if state == 'Up':
                await self._fire_event('call_answered', call_info)
    
    async def _handle_ari_channel_destroyed(self, event) -> None:
        """Handle ARI ChannelDestroyed event."""
        channel_id = event.get('channel', {}).get('id', '')
        call_info = self.active_calls.get(channel_id)
        if call_info:
            await self._fire_event('call_hangup', call_info)
    
    # AMI Event Handlers
    async def _handle_ami_new_channel(self, event) -> None:
        """Handle AMI Newchannel event."""
        channel_id = event.get('Channel', '')
        if channel_id and channel_id not in self.active_calls:
            call_info = CallInfo(
                channel_id=channel_id,
                caller_id=event.get('CallerIDNum', ''),
                called_number=event.get('Exten', ''),
                state=CallState.RINGING
            )
            
            self.active_calls[channel_id] = call_info
            self.total_calls += 1
            self.active_call_count += 1
            
            await self._fire_event('call_created', call_info)
    
    async def _handle_ami_hangup(self, event) -> None:
        """Handle AMI Hangup event."""
        channel_id = event.get('Channel', '')
        call_info = self.active_calls.get(channel_id)
        if call_info:
            call_info.hangup_cause = event.get('Cause-txt', '')
            await self._fire_event('call_hangup', call_info)
    
    async def _handle_ami_dial_begin(self, event) -> None:
        """Handle AMI DialBegin event."""
        channel_id = event.get('Channel', '')
        call_info = self.active_calls.get(channel_id)
        if call_info and call_info.state == CallState.IDLE:
            call_info.state = CallState.RINGING
    
    async def _handle_ami_dial_end(self, event) -> None:
        """Handle AMI DialEnd event."""
        channel_id = event.get('Channel', '')
        call_info = self.active_calls.get(channel_id)
        if call_info:
            dial_status = event.get('DialStatus', '')
            if dial_status == 'ANSWER':
                await self._fire_event('call_answered', call_info)
            elif dial_status in ['BUSY', 'CONGESTION', 'NOANSWER']:
                call_info.hangup_cause = dial_status
                await self._fire_event('call_hangup', call_info)
    
    async def _handle_ami_bridge(self, event) -> None:
        """Handle AMI Bridge event."""
        channel1 = event.get('Channel1', '')
        channel2 = event.get('Channel2', '')
        bridge_id = event.get('Bridgeuniqueid', '')
        
        for channel_id in [channel1, channel2]:
            call_info = self.active_calls.get(channel_id)
            if call_info:
                await self._fire_event('call_bridged', call_info, bridge_id=bridge_id)


# Global telephony service instance
_telephony_service: Optional[TelephonyService] = None


def get_telephony_service() -> Optional[TelephonyService]:
    """Get the global telephony service instance."""
    return _telephony_service


async def start_telephony_service(**kwargs) -> TelephonyService:
    """Start the global telephony service instance."""
    global _telephony_service
    
    if _telephony_service and _telephony_service.started:
        logger.warning("Telephony Service already started")
        return _telephony_service
    
    _telephony_service = TelephonyService()
    await _telephony_service.start(**kwargs)
    return _telephony_service


async def stop_telephony_service() -> None:
    """Stop the global telephony service instance."""
    global _telephony_service
    
    if _telephony_service:
        await _telephony_service.stop()
        _telephony_service = None
        logger.info("Global Telephony Service stopped")
