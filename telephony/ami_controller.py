"""
AMI Controller for Asterisk Manager Interface integration.
Handles TCP connections, event processing, and command execution.
"""

import asyncio
import logging
import re
import time
from typing import Dict, Optional, Callable, Any, List, Tuple
from datetime import datetime
from django.conf import settings
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

logger = logging.getLogger(__name__)


class AMIEvent:
    """
    Represents an AMI event with parsed headers and data.
    """
    
    def __init__(self, raw_event: str):
        self.raw_event = raw_event
        self.headers = {}
        self.event_type = ""
        self.timestamp = datetime.now()
        self._parse_event()
    
    def _parse_event(self) -> None:
        """Parse raw AMI event string into headers."""
        lines = self.raw_event.strip().split('\r\n')
        
        for line in lines:
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                self.headers[key] = value
                
                if key == 'Event':
                    self.event_type = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get header value by key."""
        return self.headers.get(key, default)
    
    def __str__(self) -> str:
        return f"AMIEvent({self.event_type}): {dict(list(self.headers.items())[:3])}"


class AMIController:
    """
    Asterisk Manager Interface Controller with asyncio support.
    Handles TCP connections, authentication, and event processing.
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5038,
        username: str = "pydialer",
        password: str = "pydialer123",
        timeout: int = 30
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        
        # Connection management
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.connected = False
        self.authenticated = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.reconnect_delay = 5  # seconds
        
        # Event handling
        self.event_handlers: Dict[str, List[Callable]] = {}
        self.action_id_counter = 0
        self.pending_actions: Dict[str, asyncio.Future] = {}
        
        # Tasks
        self.event_loop_task: Optional[asyncio.Task] = None
        self.keepalive_task: Optional[asyncio.Task] = None
        
        # Channel layer for WebSocket broadcasting
        self.channel_layer = get_channel_layer()
        
        # Default event handlers
        self._setup_default_handlers()
    
    def _setup_default_handlers(self) -> None:
        """Set up default event handlers for common AMI events."""
        self.register_event_handler('Newchannel', self._handle_new_channel)
        self.register_event_handler('Newstate', self._handle_channel_state_change)
        self.register_event_handler('Hangup', self._handle_hangup)
        self.register_event_handler('DialBegin', self._handle_dial_begin)
        self.register_event_handler('DialEnd', self._handle_dial_end)
        self.register_event_handler('Bridge', self._handle_bridge)
        self.register_event_handler('Unbridge', self._handle_unbridge)
        self.register_event_handler('AgentLogin', self._handle_agent_login)
        self.register_event_handler('AgentLogoff', self._handle_agent_logoff)
        self.register_event_handler('QueueMember', self._handle_queue_member)
        self.register_event_handler('QueueMemberStatus', self._handle_queue_member_status)
    
    async def start(self) -> None:
        """Start the AMI controller and establish connection."""
        logger.info(f"Starting AMI Controller for {self.host}:{self.port}")
        
        try:
            await self._connect()
            await self._authenticate()
            
            # Start event processing loop
            self.event_loop_task = asyncio.create_task(self._event_loop())
            
            # Start keepalive task
            self.keepalive_task = asyncio.create_task(self._keepalive_loop())
            
            logger.info("AMI Controller started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start AMI Controller: {e}", exc_info=True)
            await self.stop()
            raise
    
    async def stop(self) -> None:
        """Stop the AMI controller and cleanup resources."""
        logger.info("Stopping AMI Controller")
        
        self.connected = False
        self.authenticated = False
        
        # Cancel tasks
        if self.event_loop_task and not self.event_loop_task.done():
            self.event_loop_task.cancel()
        
        if self.keepalive_task and not self.keepalive_task.done():
            self.keepalive_task.cancel()
        
        # Close connection
        if self.writer:
            try:
                await self.send_action("Logoff")
                self.writer.close()
                await self.writer.wait_closed()
            except Exception as e:
                logger.error(f"Error closing AMI connection: {e}")
        
        logger.info("AMI Controller stopped")
    
    async def _connect(self) -> None:
        """Establish TCP connection to AMI."""
        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout
            )
            
            # Read welcome message
            welcome = await asyncio.wait_for(
                self.reader.readline(),
                timeout=self.timeout
            )
            
            welcome_text = welcome.decode('utf-8').strip()
            logger.info(f"AMI Welcome: {welcome_text}")
            
            self.connected = True
            self.reconnect_attempts = 0
            
        except Exception as e:
            logger.error(f"Failed to connect to AMI: {e}")
            raise
    
    async def _authenticate(self) -> None:
        """Authenticate with AMI using Login action."""
        try:
            response = await self.send_action(
                "Login",
                Username=self.username,
                Secret=self.password
            )
            
            if response and response.get("Response") == "Success":
                self.authenticated = True
                logger.info("AMI authentication successful")
            else:
                error_msg = response.get("Message", "Unknown error") if response else "No response"
                raise Exception(f"AMI authentication failed: {error_msg}")
                
        except Exception as e:
            logger.error(f"AMI authentication error: {e}")
            raise
    
    async def send_action(self, action: str, **kwargs) -> Optional[Dict[str, str]]:
        """
        Send an AMI action and wait for response.
        
        Args:
            action: AMI action name
            **kwargs: Action parameters
            
        Returns:
            Response dictionary or None if failed
        """
        if not self.connected or not self.writer:
            logger.error("AMI not connected")
            return None
        
        # Generate unique action ID
        self.action_id_counter += 1
        action_id = f"PyDialer-{self.action_id_counter}-{int(time.time())}"
        
        # Build action message
        message_lines = [f"Action: {action}", f"ActionID: {action_id}"]
        
        for key, value in kwargs.items():
            message_lines.append(f"{key}: {value}")
        
        message = "\r\n".join(message_lines) + "\r\n\r\n"
        
        try:
            # Create future for response
            response_future = asyncio.Future()
            self.pending_actions[action_id] = response_future
            
            # Send message
            self.writer.write(message.encode('utf-8'))
            await self.writer.drain()
            
            # Wait for response with timeout
            response = await asyncio.wait_for(response_future, timeout=self.timeout)
            
            return response
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout waiting for AMI action response: {action}")
            return None
        except Exception as e:
            logger.error(f"Error sending AMI action {action}: {e}")
            return None
        finally:
            # Clean up pending action
            self.pending_actions.pop(action_id, None)
    
    async def _event_loop(self) -> None:
        """Main event processing loop."""
        logger.info("Starting AMI event loop")
        
        buffer = ""
        
        while self.connected and self.reader:
            try:
                # Read data with timeout
                data = await asyncio.wait_for(
                    self.reader.read(4096),
                    timeout=60  # Longer timeout for event loop
                )
                
                if not data:
                    logger.warning("AMI connection closed by server")
                    break
                
                buffer += data.decode('utf-8')
                
                # Process complete messages (ending with \r\n\r\n)
                while '\r\n\r\n' in buffer:
                    message, buffer = buffer.split('\r\n\r\n', 1)
                    await self._process_message(message)
                
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await self.send_action("Ping")
            except Exception as e:
                logger.error(f"Error in AMI event loop: {e}", exc_info=True)
                if self.connected:
                    await asyncio.sleep(1)  # Brief pause before retry
                    continue
                else:
                    break
        
        logger.info("AMI event loop stopped")
    
    async def _process_message(self, message: str) -> None:
        """Process a complete AMI message."""
        try:
            lines = message.strip().split('\r\n')
            if not lines:
                return
            
            headers = {}
            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    headers[key.strip()] = value.strip()
            
            # Check if it's a response to an action
            action_id = headers.get('ActionID')
            if action_id and action_id in self.pending_actions:
                future = self.pending_actions[action_id]
                if not future.done():
                    future.set_result(headers)
                return
            
            # Check if it's an event
            event_type = headers.get('Event')
            if event_type:
                event = AMIEvent(message)
                await self._handle_event(event)
            
        except Exception as e:
            logger.error(f"Error processing AMI message: {e}", exc_info=True)
    
    async def _handle_event(self, event: AMIEvent) -> None:
        """Handle AMI event by calling registered handlers."""
        try:
            # Call registered handlers for this event type
            handlers = self.event_handlers.get(event.event_type, [])
            for handler in handlers:
                try:
                    await handler(event)
                except Exception as e:
                    logger.error(f"Error in event handler for {event.event_type}: {e}")
            
            # Broadcast event via WebSocket if channel layer is available
            if self.channel_layer:
                await self._broadcast_event(event)
                
        except Exception as e:
            logger.error(f"Error handling AMI event {event.event_type}: {e}", exc_info=True)
    
    async def _broadcast_event(self, event: AMIEvent) -> None:
        """Broadcast AMI event via WebSocket channels."""
        try:
            # Prepare event data for WebSocket broadcast
            event_data = {
                'type': 'ami_event',
                'event_type': event.event_type,
                'headers': event.headers,
                'timestamp': event.timestamp.isoformat()
            }
            
            # Broadcast to supervisor dashboard
            await self.channel_layer.group_send(
                'supervisors',
                {
                    'type': 'ami_event',
                    'data': event_data
                }
            )
            
            # Broadcast call-related events to specific channels
            channel = event.get('Channel')
            if channel:
                # Extract call ID or agent ID from channel name
                call_group = self._extract_call_group(channel)
                if call_group:
                    await self.channel_layer.group_send(
                        call_group,
                        {
                            'type': 'ami_event',
                            'data': event_data
                        }
                    )
                    
        except Exception as e:
            logger.error(f"Error broadcasting AMI event: {e}")
    
    def _extract_call_group(self, channel: str) -> Optional[str]:
        """Extract WebSocket group name from channel identifier."""
        # Example: SIP/agent1-00000001 -> agent_agent1
        # This can be customized based on channel naming conventions
        match = re.match(r'SIP/([^-]+)', channel)
        if match:
            return f"agent_{match.group(1)}"
        return None
    
    async def _keepalive_loop(self) -> None:
        """Send periodic ping to keep connection alive."""
        while self.connected:
            try:
                await asyncio.sleep(60)  # Ping every minute
                if self.connected:
                    await self.send_action("Ping")
            except Exception as e:
                logger.error(f"Error in keepalive loop: {e}")
                break
    
    def register_event_handler(self, event_type: str, handler: Callable) -> None:
        """Register an event handler for specific AMI event type."""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)
        logger.debug(f"Registered handler for AMI event: {event_type}")
    
    def unregister_event_handler(self, event_type: str, handler: Callable) -> None:
        """Unregister an event handler."""
        if event_type in self.event_handlers:
            try:
                self.event_handlers[event_type].remove(handler)
            except ValueError:
                pass
    
    # Default event handlers
    async def _handle_new_channel(self, event: AMIEvent) -> None:
        """Handle Newchannel event."""
        channel = event.get('Channel')
        state = event.get('ChannelState')
        logger.debug(f"New channel: {channel} in state {state}")
    
    async def _handle_channel_state_change(self, event: AMIEvent) -> None:
        """Handle Newstate event."""
        channel = event.get('Channel')
        state = event.get('ChannelState')
        state_desc = event.get('ChannelStateDesc')
        logger.debug(f"Channel state change: {channel} -> {state} ({state_desc})")
    
    async def _handle_hangup(self, event: AMIEvent) -> None:
        """Handle Hangup event."""
        channel = event.get('Channel')
        cause = event.get('Cause')
        cause_txt = event.get('Cause-txt')
        logger.info(f"Channel hangup: {channel}, Cause: {cause} ({cause_txt})")
    
    async def _handle_dial_begin(self, event: AMIEvent) -> None:
        """Handle DialBegin event."""
        channel = event.get('Channel')
        destination = event.get('DestChannel')
        logger.info(f"Dial begin: {channel} -> {destination}")
    
    async def _handle_dial_end(self, event: AMIEvent) -> None:
        """Handle DialEnd event."""
        channel = event.get('Channel')
        dial_status = event.get('DialStatus')
        logger.info(f"Dial end: {channel}, Status: {dial_status}")
    
    async def _handle_bridge(self, event: AMIEvent) -> None:
        """Handle Bridge event."""
        channel1 = event.get('Channel1')
        channel2 = event.get('Channel2')
        logger.info(f"Bridge: {channel1} <-> {channel2}")
    
    async def _handle_unbridge(self, event: AMIEvent) -> None:
        """Handle Unbridge event."""
        channel1 = event.get('Channel1')
        channel2 = event.get('Channel2')
        logger.info(f"Unbridge: {channel1} <-> {channel2}")
    
    async def _handle_agent_login(self, event: AMIEvent) -> None:
        """Handle AgentLogin event."""
        agent = event.get('Agent')
        channel = event.get('Channel')
        logger.info(f"Agent login: {agent} on {channel}")
    
    async def _handle_agent_logoff(self, event: AMIEvent) -> None:
        """Handle AgentLogoff event."""
        agent = event.get('Agent')
        logger.info(f"Agent logoff: {agent}")
    
    async def _handle_queue_member(self, event: AMIEvent) -> None:
        """Handle QueueMember event."""
        queue = event.get('Queue')
        member = event.get('Location')
        status = event.get('Status')
        logger.debug(f"Queue member: {member} in {queue}, Status: {status}")
    
    async def _handle_queue_member_status(self, event: AMIEvent) -> None:
        """Handle QueueMemberStatus event."""
        queue = event.get('Queue')
        member = event.get('Location')
        status = event.get('Status')
        logger.info(f"Queue member status: {member} in {queue} -> {status}")
    
    async def get_connection_status(self) -> Dict[str, Any]:
        """Get current connection status."""
        return {
            'connected': self.connected,
            'authenticated': self.authenticated,
            'host': self.host,
            'port': self.port,
            'reconnect_attempts': self.reconnect_attempts,
            'pending_actions': len(self.pending_actions),
            'event_handlers': len(self.event_handlers)
        }


# Global AMI controller instance
_ami_controller: Optional[AMIController] = None


def get_ami_controller() -> Optional[AMIController]:
    """Get the global AMI controller instance."""
    return _ami_controller


async def start_ami_controller(
    host: str = None,
    port: int = None,
    username: str = None,
    password: str = None
) -> AMIController:
    """
    Start the global AMI controller instance.
    
    Args:
        host: AMI host (default from settings)
        port: AMI port (default from settings)  
        username: AMI username (default from settings)
        password: AMI password (default from settings)
        
    Returns:
        AMIController instance
    """
    global _ami_controller
    
    if _ami_controller and _ami_controller.connected:
        logger.warning("AMI Controller already running")
        return _ami_controller
    
    # Get settings with defaults
    ami_config = getattr(settings, 'AMI_CONFIG', {})
    host = host or ami_config.get('HOST', 'localhost')
    port = port or ami_config.get('PORT', 5038)
    username = username or ami_config.get('USERNAME', 'pydialer')
    password = password or ami_config.get('PASSWORD', 'pydialer123')
    
    _ami_controller = AMIController(
        host=host,
        port=port,
        username=username,
        password=password
    )
    
    await _ami_controller.start()
    return _ami_controller


async def stop_ami_controller() -> None:
    """Stop the global AMI controller instance."""
    global _ami_controller
    
    if _ami_controller:
        await _ami_controller.stop()
        _ami_controller = None
        logger.info("Global AMI Controller stopped")
