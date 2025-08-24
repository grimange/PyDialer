"""
ExternalMedia channel management for AI Media Gateway integration.
Handles creation and bridge attachment of ExternalMedia channels for audio processing.
"""

import asyncio
import logging
import json
from typing import Dict, Optional, Any, Set, Tuple
from urllib.parse import urljoin
from datetime import datetime
from .ari_controller import ARIController

logger = logging.getLogger(__name__)


class ExternalMediaManager:
    """
    Manages ExternalMedia channels for AI audio processing.
    Creates channels, manages bridges, and handles media flow.
    """
    
    def __init__(self, ari_controller: ARIController):
        self.ari = ari_controller
        
        # Bridge and channel tracking
        self.active_bridges: Dict[str, Dict[str, Any]] = {}
        self.external_media_channels: Dict[str, Dict[str, Any]] = {}
        self.call_to_bridge_mapping: Dict[str, str] = {}
        
        # Configuration
        self.media_gateway_host = "127.0.0.1"  # Will be configurable
        self.media_gateway_port_range = (10000, 10999)  # RTP port range
        self.current_port = self.media_gateway_port_range[0]
        
    def get_next_rtp_port(self) -> int:
        """Get next available RTP port for ExternalMedia channel."""
        port = self.current_port
        self.current_port += 2  # RTP uses even ports, RTCP uses odd ports
        
        if self.current_port > self.media_gateway_port_range[1]:
            self.current_port = self.media_gateway_port_range[0]
        
        return port
    
    async def create_external_media_channel(
        self,
        call_channel_id: str,
        external_host: Optional[str] = None,
        format: str = "ulaw"
    ) -> Optional[Dict[str, Any]]:
        """
        Create an ExternalMedia channel for AI audio processing.
        
        Args:
            call_channel_id: The original call channel ID
            external_host: External media server host (defaults to configured host)
            format: Audio format (ulaw, alaw, gsm, etc.)
            
        Returns:
            Dictionary with external media channel info or None if failed
        """
        try:
            host = external_host or self.media_gateway_host
            rtp_port = self.get_next_rtp_port()
            
            # Create ExternalMedia channel
            url = urljoin(self.ari.ari_url, "/ari/channels/externalMedia")
            
            channel_data = {
                'app': self.ari.app_name,
                'external_host': host,
                'format': format,
                'connection_type': 'rtp',
                'direction': 'both'
            }
            
            async with self.ari.session.post(url, json=channel_data) as response:
                if response.status == 200:
                    external_channel_data = await response.json()
                    external_channel_id = external_channel_data.get('id')
                    
                    # Store channel information
                    self.external_media_channels[external_channel_id] = {
                        'id': external_channel_id,
                        'call_channel_id': call_channel_id,
                        'host': host,
                        'rtp_port': rtp_port,
                        'format': format,
                        'created_at': datetime.now().isoformat(),
                        'state': 'created'
                    }
                    
                    logger.info(f"ExternalMedia channel created: {external_channel_id}")
                    return self.external_media_channels[external_channel_id]
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to create ExternalMedia channel: {response.status} - {error_text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error creating ExternalMedia channel: {e}")
            return None
    
    async def create_bridge(
        self,
        bridge_type: str = "mixing",
        name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create a bridge for connecting channels.
        
        Args:
            bridge_type: Type of bridge (mixing, holding, dtmf_events, proxy_media)
            name: Optional bridge name
            
        Returns:
            Dictionary with bridge info or None if failed
        """
        try:
            url = urljoin(self.ari.ari_url, "/ari/bridges")
            
            bridge_data = {
                'type': bridge_type
            }
            
            if name:
                bridge_data['name'] = name
            
            async with self.ari.session.post(url, json=bridge_data) as response:
                if response.status == 200:
                    bridge_info = await response.json()
                    bridge_id = bridge_info.get('id')
                    
                    # Store bridge information
                    self.active_bridges[bridge_id] = {
                        'id': bridge_id,
                        'type': bridge_type,
                        'name': name or f"bridge-{bridge_id[:8]}",
                        'channels': set(),
                        'created_at': datetime.now().isoformat(),
                        'state': 'active'
                    }
                    
                    logger.info(f"Bridge created: {bridge_id}")
                    return self.active_bridges[bridge_id]
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to create bridge: {response.status} - {error_text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error creating bridge: {e}")
            return None
    
    async def add_channel_to_bridge(
        self,
        bridge_id: str,
        channel_id: str,
        role: Optional[str] = None
    ) -> bool:
        """
        Add a channel to a bridge.
        
        Args:
            bridge_id: The bridge ID
            channel_id: The channel ID to add
            role: Optional channel role in bridge
            
        Returns:
            True if successful, False otherwise
        """
        try:
            url = urljoin(self.ari.ari_url, f"/ari/bridges/{bridge_id}/addChannel")
            
            channel_data = {
                'channel': channel_id
            }
            
            if role:
                channel_data['role'] = role
            
            async with self.ari.session.post(url, json=channel_data) as response:
                if response.status == 204:
                    # Update bridge tracking
                    if bridge_id in self.active_bridges:
                        self.active_bridges[bridge_id]['channels'].add(channel_id)
                    
                    logger.info(f"Channel {channel_id} added to bridge {bridge_id}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to add channel to bridge: {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error adding channel {channel_id} to bridge {bridge_id}: {e}")
            return False
    
    async def remove_channel_from_bridge(
        self,
        bridge_id: str,
        channel_id: str
    ) -> bool:
        """
        Remove a channel from a bridge.
        
        Args:
            bridge_id: The bridge ID
            channel_id: The channel ID to remove
            
        Returns:
            True if successful, False otherwise
        """
        try:
            url = urljoin(self.ari.ari_url, f"/ari/bridges/{bridge_id}/removeChannel")
            
            channel_data = {
                'channel': channel_id
            }
            
            async with self.ari.session.post(url, json=channel_data) as response:
                if response.status == 204:
                    # Update bridge tracking
                    if bridge_id in self.active_bridges:
                        self.active_bridges[bridge_id]['channels'].discard(channel_id)
                    
                    logger.info(f"Channel {channel_id} removed from bridge {bridge_id}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to remove channel from bridge: {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error removing channel {channel_id} from bridge {bridge_id}: {e}")
            return False
    
    async def destroy_bridge(self, bridge_id: str) -> bool:
        """
        Destroy a bridge.
        
        Args:
            bridge_id: The bridge ID to destroy
            
        Returns:
            True if successful, False otherwise
        """
        try:
            url = urljoin(self.ari.ari_url, f"/ari/bridges/{bridge_id}")
            
            async with self.ari.session.delete(url) as response:
                if response.status == 204:
                    # Remove from tracking
                    self.active_bridges.pop(bridge_id, None)
                    
                    logger.info(f"Bridge {bridge_id} destroyed")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to destroy bridge: {response.status} - {error_text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error destroying bridge {bridge_id}: {e}")
            return False
    
    async def setup_ai_media_bridge(
        self,
        call_channel_id: str,
        external_host: Optional[str] = None,
        audio_format: str = "ulaw"
    ) -> Optional[Dict[str, Any]]:
        """
        Set up complete AI media bridge for a call.
        Creates ExternalMedia channel, bridge, and connects everything.
        
        Args:
            call_channel_id: The original call channel ID
            external_host: External media server host
            audio_format: Audio format for processing
            
        Returns:
            Dictionary with setup information or None if failed
        """
        try:
            # Step 1: Create ExternalMedia channel
            external_media_info = await self.create_external_media_channel(
                call_channel_id=call_channel_id,
                external_host=external_host,
                format=audio_format
            )
            
            if not external_media_info:
                logger.error("Failed to create ExternalMedia channel")
                return None
            
            external_channel_id = external_media_info['id']
            
            # Step 2: Create bridge
            bridge_info = await self.create_bridge(
                bridge_type="mixing",
                name=f"ai-media-{call_channel_id[:8]}"
            )
            
            if not bridge_info:
                logger.error("Failed to create bridge")
                # Cleanup external media channel
                await self.cleanup_external_media_channel(external_channel_id)
                return None
            
            bridge_id = bridge_info['id']
            
            # Step 3: Add both channels to bridge
            # Add original call channel
            if not await self.add_channel_to_bridge(bridge_id, call_channel_id):
                logger.error("Failed to add call channel to bridge")
                await self.cleanup_ai_media_setup(bridge_id, external_channel_id)
                return None
            
            # Add ExternalMedia channel
            if not await self.add_channel_to_bridge(bridge_id, external_channel_id):
                logger.error("Failed to add ExternalMedia channel to bridge")
                await self.cleanup_ai_media_setup(bridge_id, external_channel_id)
                return None
            
            # Step 4: Update tracking
            self.call_to_bridge_mapping[call_channel_id] = bridge_id
            
            setup_info = {
                'call_channel_id': call_channel_id,
                'external_channel_id': external_channel_id,
                'bridge_id': bridge_id,
                'external_media_info': external_media_info,
                'bridge_info': bridge_info,
                'setup_at': datetime.now().isoformat()
            }
            
            logger.info(f"AI media bridge setup completed for call {call_channel_id}")
            return setup_info
            
        except Exception as e:
            logger.error(f"Error setting up AI media bridge: {e}")
            return None
    
    async def cleanup_ai_media_setup(
        self,
        bridge_id: Optional[str] = None,
        external_channel_id: Optional[str] = None,
        call_channel_id: Optional[str] = None
    ) -> None:
        """
        Clean up AI media setup resources.
        
        Args:
            bridge_id: Bridge ID to destroy
            external_channel_id: ExternalMedia channel ID to cleanup
            call_channel_id: Call channel ID for mapping cleanup
        """
        try:
            # Remove call mapping
            if call_channel_id and call_channel_id in self.call_to_bridge_mapping:
                del self.call_to_bridge_mapping[call_channel_id]
            
            # Destroy bridge
            if bridge_id:
                await self.destroy_bridge(bridge_id)
            
            # Cleanup ExternalMedia channel
            if external_channel_id:
                await self.cleanup_external_media_channel(external_channel_id)
            
            logger.info("AI media setup cleanup completed")
            
        except Exception as e:
            logger.error(f"Error during AI media setup cleanup: {e}")
    
    async def cleanup_external_media_channel(self, external_channel_id: str) -> None:
        """
        Clean up ExternalMedia channel resources.
        
        Args:
            external_channel_id: The ExternalMedia channel ID to cleanup
        """
        try:
            # Hangup the ExternalMedia channel
            await self.ari.hangup_channel(external_channel_id, reason="normal")
            
            # Remove from tracking
            self.external_media_channels.pop(external_channel_id, None)
            
            logger.info(f"ExternalMedia channel {external_channel_id} cleaned up")
            
        except Exception as e:
            logger.error(f"Error cleaning up ExternalMedia channel: {e}")
    
    async def get_bridge_for_call(self, call_channel_id: str) -> Optional[str]:
        """
        Get bridge ID associated with a call channel.
        
        Args:
            call_channel_id: The call channel ID
            
        Returns:
            Bridge ID if found, None otherwise
        """
        return self.call_to_bridge_mapping.get(call_channel_id)
    
    def get_external_media_channels(self) -> Dict[str, Dict[str, Any]]:
        """Get all active ExternalMedia channels."""
        return self.external_media_channels.copy()
    
    def get_active_bridges(self) -> Dict[str, Dict[str, Any]]:
        """Get all active bridges."""
        return self.active_bridges.copy()
    
    async def handle_channel_destroyed(self, channel_id: str) -> None:
        """
        Handle cleanup when a channel is destroyed.
        
        Args:
            channel_id: The destroyed channel ID
        """
        # Check if this is an ExternalMedia channel
        if channel_id in self.external_media_channels:
            call_channel_id = self.external_media_channels[channel_id].get('call_channel_id')
            bridge_id = self.call_to_bridge_mapping.get(call_channel_id) if call_channel_id else None
            
            await self.cleanup_ai_media_setup(
                bridge_id=bridge_id,
                external_channel_id=channel_id,
                call_channel_id=call_channel_id
            )
        
        # Check if this is a call channel with AI media setup
        elif channel_id in self.call_to_bridge_mapping:
            bridge_id = self.call_to_bridge_mapping[channel_id]
            
            # Find associated ExternalMedia channel
            external_channel_id = None
            for ext_id, ext_info in self.external_media_channels.items():
                if ext_info.get('call_channel_id') == channel_id:
                    external_channel_id = ext_id
                    break
            
            await self.cleanup_ai_media_setup(
                bridge_id=bridge_id,
                external_channel_id=external_channel_id,
                call_channel_id=channel_id
            )


class AIMediaBridgeManager:
    """
    High-level manager for AI Media Gateway integration.
    Coordinates between ARI Controller and ExternalMedia management.
    """
    
    def __init__(self, ari_controller: ARIController):
        self.ari = ari_controller
        self.external_media = ExternalMediaManager(ari_controller)
        
        # Register event handlers
        self.ari.register_event_handler('ChannelDestroyed', self._handle_channel_destroyed)
        self.ari.register_event_handler('StasisStart', self._handle_stasis_start)
    
    async def enable_ai_for_call(
        self,
        call_channel_id: str,
        ai_gateway_host: Optional[str] = None,
        audio_format: str = "ulaw"
    ) -> Optional[Dict[str, Any]]:
        """
        Enable AI processing for a call by setting up ExternalMedia bridge.
        
        Args:
            call_channel_id: The call channel ID
            ai_gateway_host: AI Media Gateway host
            audio_format: Audio format for processing
            
        Returns:
            Setup information if successful, None otherwise
        """
        return await self.external_media.setup_ai_media_bridge(
            call_channel_id=call_channel_id,
            external_host=ai_gateway_host,
            audio_format=audio_format
        )
    
    async def disable_ai_for_call(self, call_channel_id: str) -> None:
        """
        Disable AI processing for a call by cleaning up ExternalMedia setup.
        
        Args:
            call_channel_id: The call channel ID
        """
        bridge_id = await self.external_media.get_bridge_for_call(call_channel_id)
        if bridge_id:
            # Find associated ExternalMedia channel
            external_channel_id = None
            for ext_id, ext_info in self.external_media.get_external_media_channels().items():
                if ext_info.get('call_channel_id') == call_channel_id:
                    external_channel_id = ext_id
                    break
            
            await self.external_media.cleanup_ai_media_setup(
                bridge_id=bridge_id,
                external_channel_id=external_channel_id,
                call_channel_id=call_channel_id
            )
    
    async def _handle_channel_destroyed(self, event: Dict[str, Any]) -> None:
        """Handle ChannelDestroyed event for cleanup."""
        channel_id = event.get('channel', {}).get('id')
        if channel_id:
            await self.external_media.handle_channel_destroyed(channel_id)
    
    async def _handle_stasis_start(self, event: Dict[str, Any]) -> None:
        """Handle StasisStart event for automatic AI enablement."""
        channel_id = event.get('channel', {}).get('id')
        args = event.get('args', [])
        
        # Check if AI processing should be enabled based on args
        if channel_id and 'enable_ai' in args:
            logger.info(f"Auto-enabling AI for call {channel_id}")
            await self.enable_ai_for_call(channel_id)
    
    def get_ai_status_for_call(self, call_channel_id: str) -> Dict[str, Any]:
        """
        Get AI processing status for a call.
        
        Args:
            call_channel_id: The call channel ID
            
        Returns:
            Status dictionary with AI processing information
        """
        bridge_id = self.external_media.call_to_bridge_mapping.get(call_channel_id)
        
        if not bridge_id:
            return {'enabled': False, 'status': 'not_configured'}
        
        # Find ExternalMedia channel
        external_channel_id = None
        external_info = None
        for ext_id, ext_data in self.external_media.get_external_media_channels().items():
            if ext_data.get('call_channel_id') == call_channel_id:
                external_channel_id = ext_id
                external_info = ext_data
                break
        
        bridge_info = self.external_media.active_bridges.get(bridge_id)
        
        return {
            'enabled': True,
            'status': 'active',
            'call_channel_id': call_channel_id,
            'bridge_id': bridge_id,
            'external_channel_id': external_channel_id,
            'bridge_info': bridge_info,
            'external_media_info': external_info
        }
