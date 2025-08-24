"""
ARI Controller for Asterisk REST Interface integration.
Handles WebSocket connections, Stasis app management, and call events.
"""

import asyncio
import json
import logging
import aiohttp
from typing import Dict, Optional, Callable, Any, Set
from urllib.parse import urljoin
from datetime import datetime
from django.conf import settings

logger = logging.getLogger(__name__)


class ARIController:
    """
    Asterisk REST Interface Controller with asyncio support.
    Manages Stasis applications and WebSocket events.
    """
    
    def __init__(
        self,
        ari_url: str = "http://localhost:8088",
        username: str = "asterisk",
        password: str = "asterisk",
        app_name: str = "pydialer"
    ):
        self.ari_url = ari_url
        self.username = username
        self.password = password
        self.app_name = app_name
        
        # Connection management
        self.session: Optional[aiohttp.ClientSession] = None
        self.websocket: Optional[aiohttp.ClientWebSocketResponse] = None
        self.connected = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.reconnect_delay = 5  # seconds
        
        # Event handling
        self.event_handlers: Dict[str, Callable] = {}
        self.active_channels: Set[str] = set()
        self.channel_data: Dict[str, Dict[str, Any]] = {}
        
        # Tasks
        self.websocket_task: Optional[asyncio.Task] = None
        self.heartbeat_task: Optional[asyncio.Task] = None
        
        # Default event handlers
        self._setup_default_handlers()
    
    def _setup_default_handlers(self) -> None:
        """Set up default event handlers for common ARI events."""
        self.event_handlers.update({
            'StasisStart': self._handle_stasis_start,
            'StasisEnd': self._handle_stasis_end,
            'ChannelStateChange': self._handle_channel_state_change,
            'ChannelDestroyed': self._handle_channel_destroyed,
            'ChannelHangupRequest': self._handle_channel_hangup,
            'ChannelDtmfReceived': self._handle_dtmf_received,
            'PlaybackStarted': self._handle_playback_started,
            'PlaybackFinished': self._handle_playback_finished,
            'RecordingStarted': self._handle_recording_started,
            'RecordingFinished': self._handle_recording_finished,
        })
    
    async def start(self) -> None:
        """Start the ARI controller and establish connections."""
        logger.info(f"Starting ARI Controller for app: {self.app_name}")
        
        # Create HTTP session
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            auth=aiohttp.BasicAuth(self.username, self.password)
        )
        
        # Start WebSocket connection
        await self._connect_websocket()
        
        # Start heartbeat task
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        logger.info("ARI Controller started successfully")
    
    async def stop(self) -> None:
        """Stop the ARI controller and cleanup resources."""
        logger.info("Stopping ARI Controller")
        
        self.connected = False
        
        # Cancel tasks
        if self.websocket_task and not self.websocket_task.done():
            self.websocket_task.cancel()
        
        if self.heartbeat_task and not self.heartbeat_task.done():
            self.heartbeat_task.cancel()
        
        # Close WebSocket
        if self.websocket and not self.websocket.closed:
            await self.websocket.close()
        
        # Close HTTP session
        if self.session and not self.session.closed:
            await self.session.close()
        
        logger.info("ARI Controller stopped")
    
    async def _connect_websocket(self) -> None:
        """Establish WebSocket connection to ARI events."""
        ws_url = urljoin(self.ari_url, f"/ari/events?app={self.app_name}&api_key={self.username}:{self.password}")
        
        try:
            logger.info(f"Connecting to ARI WebSocket: {ws_url}")
            self.websocket = await self.session.ws_connect(ws_url)
            self.connected = True
            self.reconnect_attempts = 0
            
            # Start WebSocket message handling
            self.websocket_task = asyncio.create_task(self._handle_websocket_messages())
            
            logger.info("ARI WebSocket connected successfully")
            
        except Exception as e:
            logger.error(f"Failed to connect to ARI WebSocket: {e}")
            await self._schedule_reconnect()
    
    async def _handle_websocket_messages(self) -> None:
        """Handle incoming WebSocket messages from ARI."""
        try:
            async for msg in self.websocket:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        event_data = json.loads(msg.data)
                        await self._process_ari_event(event_data)
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to decode ARI event: {e}")
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {self.websocket.exception()}")
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSE:
                    logger.warning("WebSocket connection closed")
                    break
        except Exception as e:
            logger.error(f"WebSocket message handling error: {e}")
        finally:
            self.connected = False
            await self._schedule_reconnect()
    
    async def _process_ari_event(self, event_data: Dict[str, Any]) -> None:
        """Process ARI event and dispatch to appropriate handlers."""
        event_type = event_data.get('type')
        
        if not event_type:
            logger.warning("Received event without type field")
            return
        
        logger.debug(f"Processing ARI event: {event_type}")
        
        # Call registered handler if available
        handler = self.event_handlers.get(event_type)
        if handler:
            try:
                await handler(event_data)
            except Exception as e:
                logger.error(f"Error in event handler for {event_type}: {e}")
        else:
            logger.debug(f"No handler registered for event type: {event_type}")
    
    async def _schedule_reconnect(self) -> None:
        """Schedule WebSocket reconnection with exponential backoff."""
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            logger.error("Max reconnection attempts reached. Stopping ARI Controller.")
            return
        
        delay = min(self.reconnect_delay * (2 ** self.reconnect_attempts), 300)  # Max 5 minutes
        self.reconnect_attempts += 1
        
        logger.info(f"Scheduling reconnection attempt {self.reconnect_attempts} in {delay} seconds")
        await asyncio.sleep(delay)
        
        try:
            await self._connect_websocket()
        except Exception as e:
            logger.error(f"Reconnection attempt failed: {e}")
            await self._schedule_reconnect()
    
    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat to maintain connection."""
        while self.connected:
            try:
                # Check Asterisk info endpoint as heartbeat
                async with self.session.get(urljoin(self.ari_url, "/ari/asterisk/info")) as response:
                    if response.status != 200:
                        logger.warning(f"Heartbeat failed with status: {response.status}")
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
            
            await asyncio.sleep(30)  # Heartbeat every 30 seconds
    
    # Default event handlers
    async def _handle_stasis_start(self, event: Dict[str, Any]) -> None:
        """Handle StasisStart event - channel entered our application."""
        channel_id = event.get('channel', {}).get('id')
        if channel_id:
            self.active_channels.add(channel_id)
            self.channel_data[channel_id] = {
                'id': channel_id,
                'state': event.get('channel', {}).get('state'),
                'caller_id': event.get('channel', {}).get('caller', {}).get('number'),
                'connected_line': event.get('channel', {}).get('connected', {}).get('number'),
                'created_at': datetime.now().isoformat(),
                'args': event.get('args', [])
            }
            logger.info(f"Channel {channel_id} entered Stasis application")
    
    async def _handle_stasis_end(self, event: Dict[str, Any]) -> None:
        """Handle StasisEnd event - channel left our application."""
        channel_id = event.get('channel', {}).get('id')
        if channel_id:
            self.active_channels.discard(channel_id)
            self.channel_data.pop(channel_id, None)
            logger.info(f"Channel {channel_id} left Stasis application")
    
    async def _handle_channel_state_change(self, event: Dict[str, Any]) -> None:
        """Handle ChannelStateChange event."""
        channel_id = event.get('channel', {}).get('id')
        new_state = event.get('channel', {}).get('state')
        
        if channel_id and channel_id in self.channel_data:
            old_state = self.channel_data[channel_id].get('state')
            self.channel_data[channel_id]['state'] = new_state
            logger.info(f"Channel {channel_id} state changed: {old_state} -> {new_state}")
    
    async def _handle_channel_destroyed(self, event: Dict[str, Any]) -> None:
        """Handle ChannelDestroyed event."""
        channel_id = event.get('channel', {}).get('id')
        if channel_id:
            self.active_channels.discard(channel_id)
            self.channel_data.pop(channel_id, None)
            logger.info(f"Channel {channel_id} destroyed")
    
    async def _handle_channel_hangup(self, event: Dict[str, Any]) -> None:
        """Handle ChannelHangupRequest event."""
        channel_id = event.get('channel', {}).get('id')
        if channel_id:
            logger.info(f"Hangup request for channel {channel_id}")
    
    async def _handle_dtmf_received(self, event: Dict[str, Any]) -> None:
        """Handle ChannelDtmfReceived event."""
        channel_id = event.get('channel', {}).get('id')
        digit = event.get('digit')
        logger.info(f"DTMF received on channel {channel_id}: {digit}")
    
    async def _handle_playback_started(self, event: Dict[str, Any]) -> None:
        """Handle PlaybackStarted event."""
        playback_id = event.get('playback', {}).get('id')
        logger.info(f"Playback started: {playback_id}")
    
    async def _handle_playback_finished(self, event: Dict[str, Any]) -> None:
        """Handle PlaybackFinished event."""
        playback_id = event.get('playback', {}).get('id')
        logger.info(f"Playback finished: {playback_id}")
    
    async def _handle_recording_started(self, event: Dict[str, Any]) -> None:
        """Handle RecordingStarted event."""
        recording_name = event.get('recording', {}).get('name')
        logger.info(f"Recording started: {recording_name}")
    
    async def _handle_recording_finished(self, event: Dict[str, Any]) -> None:
        """Handle RecordingFinished event."""
        recording_name = event.get('recording', {}).get('name')
        logger.info(f"Recording finished: {recording_name}")
    
    # Public API methods
    def register_event_handler(self, event_type: str, handler: Callable) -> None:
        """Register a custom event handler for a specific ARI event type."""
        self.event_handlers[event_type] = handler
        logger.info(f"Registered handler for event type: {event_type}")
    
    async def originate_call(
        self,
        endpoint: str,
        app_args: Optional[list] = None,
        caller_id: Optional[str] = None,
        timeout: int = 30
    ) -> Optional[str]:
        """
        Originate a new call through ARI.
        
        Args:
            endpoint: The endpoint to call (e.g., 'PJSIP/1001')
            app_args: Arguments to pass to the Stasis application
            caller_id: Caller ID for the outgoing call
            timeout: Call timeout in seconds
            
        Returns:
            Channel ID if successful, None otherwise
        """
        try:
            url = urljoin(self.ari_url, "/ari/channels")
            
            data = {
                'endpoint': endpoint,
                'app': self.app_name,
                'timeout': timeout
            }
            
            if app_args:
                data['appArgs'] = ','.join(app_args)
            
            if caller_id:
                data['callerId'] = caller_id
            
            async with self.session.post(url, json=data) as response:
                if response.status == 200:
                    channel_data = await response.json()
                    channel_id = channel_data.get('id')
                    logger.info(f"Call originated successfully: {channel_id}")
                    return channel_id
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to originate call: {response.status} - {error_text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error originating call: {e}")
            return None
    
    async def hangup_channel(self, channel_id: str, reason: str = "normal") -> bool:
        """
        Hangup a channel.
        
        Args:
            channel_id: The channel ID to hang up
            reason: Hangup reason
            
        Returns:
            True if successful, False otherwise
        """
        try:
            url = urljoin(self.ari_url, f"/ari/channels/{channel_id}")
            
            async with self.session.delete(url, params={'reason': reason}) as response:
                if response.status == 204:
                    logger.info(f"Channel {channel_id} hung up successfully")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to hangup channel: {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error hanging up channel {channel_id}: {e}")
            return False
    
    async def answer_channel(self, channel_id: str) -> bool:
        """
        Answer a channel.
        
        Args:
            channel_id: The channel ID to answer
            
        Returns:
            True if successful, False otherwise
        """
        try:
            url = urljoin(self.ari_url, f"/ari/channels/{channel_id}/answer")
            
            async with self.session.post(url) as response:
                if response.status == 204:
                    logger.info(f"Channel {channel_id} answered successfully")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to answer channel: {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error answering channel {channel_id}: {e}")
            return False
    
    async def play_media(
        self,
        channel_id: str,
        media: str,
        language: str = "en"
    ) -> Optional[str]:
        """
        Play media to a channel.
        
        Args:
            channel_id: The channel ID to play media to
            media: Media URI to play (e.g., 'sound:hello-world')
            language: Language for the media
            
        Returns:
            Playback ID if successful, None otherwise
        """
        try:
            url = urljoin(self.ari_url, f"/ari/channels/{channel_id}/play")
            
            data = {
                'media': media,
                'lang': language
            }
            
            async with self.session.post(url, json=data) as response:
                if response.status == 201:
                    playback_data = await response.json()
                    playback_id = playback_data.get('id')
                    logger.info(f"Media playback started: {playback_id}")
                    return playback_id
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to play media: {response.status} - {error_text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error playing media to channel {channel_id}: {e}")
            return None
    
    def get_active_channels(self) -> Set[str]:
        """Get set of active channel IDs."""
        return self.active_channels.copy()
    
    def get_channel_data(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """Get data for a specific channel."""
        return self.channel_data.get(channel_id)
    
    def is_connected(self) -> bool:
        """Check if ARI controller is connected."""
        return self.connected


# Global ARI controller instance
ari_controller: Optional[ARIController] = None


async def get_ari_controller() -> ARIController:
    """Get or create the global ARI controller instance."""
    global ari_controller
    
    if ari_controller is None:
        # Get configuration from Django settings
        ari_config = getattr(settings, 'ARI_CONFIG', {})
        
        ari_controller = ARIController(
            ari_url=ari_config.get('url', 'http://localhost:8088'),
            username=ari_config.get('username', 'asterisk'),
            password=ari_config.get('password', 'asterisk'),
            app_name=ari_config.get('app_name', 'pydialer')
        )
    
    return ari_controller


async def start_ari_controller() -> None:
    """Start the global ARI controller."""
    controller = await get_ari_controller()
    if not controller.is_connected():
        await controller.start()


async def stop_ari_controller() -> None:
    """Stop the global ARI controller."""
    global ari_controller
    
    if ari_controller and ari_controller.is_connected():
        await ari_controller.stop()
        ari_controller = None
