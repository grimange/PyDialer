"""
WebRTC Gateway using aiortc for peer connections.
Handles browser-based audio connections for AI Media Gateway integration.
"""

import asyncio
import logging
import json
import uuid
from typing import Dict, Optional, Any, Set, Callable
from datetime import datetime
import aiohttp
from aiohttp import web
import aiortc
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack
from aiortc.contrib.media import MediaRelay, MediaBlackhole
import webrtcvad
import numpy as np
from django.conf import settings

logger = logging.getLogger(__name__)


class AudioProcessor:
    """
    Processes audio from WebRTC connections for AI analysis.
    Handles voice activity detection and audio chunking.
    """
    
    def __init__(self, sample_rate: int = 48000, frame_duration: int = 30):
        self.sample_rate = sample_rate
        self.frame_duration = frame_duration  # ms
        self.frame_size = int(sample_rate * frame_duration / 1000)  # samples per frame
        
        # Voice Activity Detection
        self.vad = webrtcvad.Vad(2)  # Aggressiveness level 0-3
        self.speech_buffer = []
        self.silence_frames = 0
        self.max_silence_frames = 10  # ~300ms of silence
        
        # Audio callbacks
        self.on_speech_detected: Optional[Callable] = None
        self.on_audio_chunk: Optional[Callable] = None
    
    def process_audio_frame(self, audio_data: bytes, sample_rate: int = 16000) -> None:
        """
        Process incoming audio frame for VAD and chunking.
        
        Args:
            audio_data: Raw audio data (16-bit PCM)
            sample_rate: Sample rate of the audio data
        """
        try:
            # Convert to 16kHz if needed for VAD
            if sample_rate != 16000:
                audio_data = self._resample_audio(audio_data, sample_rate, 16000)
            
            # Ensure frame size is correct for VAD (10, 20, or 30ms at 16kHz)
            frame_bytes = 320  # 20ms at 16kHz = 320 bytes
            
            for i in range(0, len(audio_data), frame_bytes):
                frame = audio_data[i:i + frame_bytes]
                if len(frame) == frame_bytes:
                    is_speech = self.vad.is_speech(frame, 16000)
                    
                    if is_speech:
                        self.silence_frames = 0
                        self.speech_buffer.append(frame)
                        
                        # Notify of speech detection
                        if self.on_speech_detected:
                            self.on_speech_detected(frame)
                    else:
                        self.silence_frames += 1
                        
                        # Add some silence frames to buffer for natural speech
                        if self.silence_frames < 5:  # ~100ms
                            self.speech_buffer.append(frame)
                        
                        # Send audio chunk when silence detected
                        if (self.silence_frames >= self.max_silence_frames and 
                            len(self.speech_buffer) > 0):
                            self._send_audio_chunk()
            
        except Exception as e:
            logger.error(f"Error processing audio frame: {e}")
    
    def _send_audio_chunk(self) -> None:
        """Send buffered audio chunk for processing."""
        if self.speech_buffer and self.on_audio_chunk:
            chunk_data = b''.join(self.speech_buffer)
            self.on_audio_chunk(chunk_data)
            self.speech_buffer = []
    
    def _resample_audio(self, audio_data: bytes, from_rate: int, to_rate: int) -> bytes:
        """
        Resample audio data (simplified implementation).
        In production, use soxr library for high-quality resampling.
        """
        # This is a basic implementation - use soxr for production
        if from_rate == to_rate:
            return audio_data
        
        # Convert bytes to numpy array
        audio_array = np.frombuffer(audio_data, dtype=np.int16)
        
        # Simple linear interpolation resampling
        ratio = to_rate / from_rate
        new_length = int(len(audio_array) * ratio)
        resampled = np.interp(
            np.linspace(0, len(audio_array), new_length),
            np.arange(len(audio_array)),
            audio_array
        ).astype(np.int16)
        
        return resampled.tobytes()
    
    def flush_buffer(self) -> None:
        """Flush any remaining audio in buffer."""
        if self.speech_buffer:
            self._send_audio_chunk()


class WebRTCAudioTrack(MediaStreamTrack):
    """
    Custom WebRTC audio track for receiving audio from browsers.
    Processes audio and forwards to AI Media Gateway.
    """
    
    kind = "audio"
    
    def __init__(self, connection_id: str, audio_processor: AudioProcessor):
        super().__init__()
        self.connection_id = connection_id
        self.audio_processor = audio_processor
        self.frame_count = 0
    
    async def recv(self):
        """Receive audio frames from WebRTC connection."""
        frame = await super().recv()
        
        try:
            # Convert frame to raw audio data
            audio_data = frame.to_ndarray()
            
            # Process audio (convert to bytes if needed)
            if audio_data.dtype == np.float32:
                # Convert float32 to int16
                audio_data = (audio_data * 32767).astype(np.int16)
            
            raw_audio = audio_data.tobytes()
            
            # Process through VAD and chunking
            self.audio_processor.process_audio_frame(raw_audio, frame.sample_rate)
            
            self.frame_count += 1
            
        except Exception as e:
            logger.error(f"Error processing WebRTC audio frame: {e}")
        
        return frame


class WebRTCConnection:
    """
    Manages individual WebRTC peer connection.
    Handles signaling, audio processing, and AI integration.
    """
    
    def __init__(self, connection_id: str, ai_callback: Optional[Callable] = None):
        self.connection_id = connection_id
        self.ai_callback = ai_callback
        
        # WebRTC components
        self.pc = RTCPeerConnection()
        self.relay = MediaRelay()
        self.audio_processor = AudioProcessor()
        self.audio_track: Optional[WebRTCAudioTrack] = None
        
        # Connection state
        self.connected = False
        self.created_at = datetime.now()
        
        # Setup audio processing callbacks
        self.audio_processor.on_audio_chunk = self._handle_audio_chunk
        self.audio_processor.on_speech_detected = self._handle_speech_detected
        
        # Setup WebRTC event handlers
        self._setup_pc_handlers()
    
    def _setup_pc_handlers(self) -> None:
        """Setup WebRTC PeerConnection event handlers."""
        
        @self.pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(f"WebRTC connection {self.connection_id} state: {self.pc.connectionState}")
            
            if self.pc.connectionState == "connected":
                self.connected = True
            elif self.pc.connectionState in ["disconnected", "failed", "closed"]:
                self.connected = False
        
        @self.pc.on("track")
        def on_track(track):
            logger.info(f"WebRTC track received: {track.kind}")
            
            if track.kind == "audio":
                # Create custom audio track for processing
                self.audio_track = WebRTCAudioTrack(self.connection_id, self.audio_processor)
                
                # Add to relay for processing
                processed_track = self.relay.subscribe(track)
                
                # Setup track event handlers
                @track.on("ended")
                async def on_ended():
                    logger.info(f"WebRTC audio track ended for connection {self.connection_id}")
                    self.audio_processor.flush_buffer()
    
    async def create_answer(self, offer: RTCSessionDescription) -> RTCSessionDescription:
        """
        Create answer for WebRTC offer.
        
        Args:
            offer: WebRTC offer from browser
            
        Returns:
            WebRTC answer
        """
        try:
            # Set remote description
            await self.pc.setRemoteDescription(offer)
            
            # Create answer
            answer = await self.pc.createAnswer()
            await self.pc.setLocalDescription(answer)
            
            logger.info(f"WebRTC answer created for connection {self.connection_id}")
            return answer
            
        except Exception as e:
            logger.error(f"Error creating WebRTC answer: {e}")
            raise
    
    async def close(self) -> None:
        """Close WebRTC connection and cleanup resources."""
        try:
            self.connected = False
            
            # Flush any remaining audio
            self.audio_processor.flush_buffer()
            
            # Close peer connection
            await self.pc.close()
            
            logger.info(f"WebRTC connection {self.connection_id} closed")
            
        except Exception as e:
            logger.error(f"Error closing WebRTC connection: {e}")
    
    def _handle_audio_chunk(self, audio_data: bytes) -> None:
        """Handle processed audio chunk for AI analysis."""
        try:
            if self.ai_callback:
                # Send audio chunk to AI processing
                asyncio.create_task(self.ai_callback(
                    connection_id=self.connection_id,
                    audio_data=audio_data,
                    timestamp=datetime.now().isoformat()
                ))
            
            logger.debug(f"Audio chunk processed for connection {self.connection_id}: {len(audio_data)} bytes")
            
        except Exception as e:
            logger.error(f"Error handling audio chunk: {e}")
    
    def _handle_speech_detected(self, audio_frame: bytes) -> None:
        """Handle speech detection event."""
        logger.debug(f"Speech detected for connection {self.connection_id}")


class WebRTCGateway:
    """
    WebRTC Gateway server for handling browser-based audio connections.
    Manages multiple WebRTC connections and coordinates with AI Media Gateway.
    """
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        
        # Connection management
        self.connections: Dict[str, WebRTCConnection] = {}
        self.app = web.Application()
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        
        # AI callback
        self.ai_callback: Optional[Callable] = None
        
        # Setup routes
        self._setup_routes()
    
    def _setup_routes(self) -> None:
        """Setup HTTP routes for WebRTC signaling."""
        self.app.router.add_post('/webrtc/offer', self.handle_offer)
        self.app.router.add_get('/webrtc/status', self.handle_status)
        self.app.router.add_delete('/webrtc/connection/{connection_id}', self.handle_disconnect)
        
        # CORS middleware
        self.app.middlewares.append(self._cors_middleware)
    
    async def _cors_middleware(self, request, handler):
        """CORS middleware for WebRTC signaling."""
        response = await handler(request)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response
    
    async def start(self) -> None:
        """Start WebRTC Gateway server."""
        try:
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            
            self.site = web.TCPSite(self.runner, self.host, self.port)
            await self.site.start()
            
            logger.info(f"WebRTC Gateway started on {self.host}:{self.port}")
            
        except Exception as e:
            logger.error(f"Failed to start WebRTC Gateway: {e}")
            raise
    
    async def stop(self) -> None:
        """Stop WebRTC Gateway server."""
        try:
            # Close all connections
            for connection in list(self.connections.values()):
                await connection.close()
            self.connections.clear()
            
            # Stop server
            if self.site:
                await self.site.stop()
            
            if self.runner:
                await self.runner.cleanup()
            
            logger.info("WebRTC Gateway stopped")
            
        except Exception as e:
            logger.error(f"Error stopping WebRTC Gateway: {e}")
    
    async def handle_offer(self, request) -> web.Response:
        """
        Handle WebRTC offer from browser.
        
        Creates peer connection and returns answer.
        """
        try:
            data = await request.json()
            offer_sdp = data.get('sdp')
            offer_type = data.get('type')
            connection_id = data.get('connection_id') or str(uuid.uuid4())
            
            if not offer_sdp or offer_type != 'offer':
                return web.json_response(
                    {'error': 'Invalid offer data'}, 
                    status=400
                )
            
            # Create WebRTC offer object
            offer = RTCSessionDescription(sdp=offer_sdp, type=offer_type)
            
            # Create WebRTC connection
            connection = WebRTCConnection(
                connection_id=connection_id,
                ai_callback=self.ai_callback
            )
            
            # Create answer
            answer = await connection.create_answer(offer)
            
            # Store connection
            self.connections[connection_id] = connection
            
            # Return answer
            response_data = {
                'sdp': answer.sdp,
                'type': answer.type,
                'connection_id': connection_id
            }
            
            logger.info(f"WebRTC offer processed for connection {connection_id}")
            return web.json_response(response_data)
            
        except Exception as e:
            logger.error(f"Error handling WebRTC offer: {e}")
            return web.json_response(
                {'error': 'Failed to process offer'}, 
                status=500
            )
    
    async def handle_status(self, request) -> web.Response:
        """Handle status request - return gateway statistics."""
        try:
            active_connections = sum(1 for conn in self.connections.values() if conn.connected)
            
            status = {
                'status': 'running',
                'total_connections': len(self.connections),
                'active_connections': active_connections,
                'uptime': (datetime.now() - datetime.now()).total_seconds(),  # Will be actual uptime
                'connections': {
                    conn_id: {
                        'connected': conn.connected,
                        'created_at': conn.created_at.isoformat()
                    }
                    for conn_id, conn in self.connections.items()
                }
            }
            
            return web.json_response(status)
            
        except Exception as e:
            logger.error(f"Error getting gateway status: {e}")
            return web.json_response(
                {'error': 'Failed to get status'}, 
                status=500
            )
    
    async def handle_disconnect(self, request) -> web.Response:
        """Handle connection disconnect request."""
        try:
            connection_id = request.match_info['connection_id']
            
            if connection_id in self.connections:
                await self.connections[connection_id].close()
                del self.connections[connection_id]
                
                logger.info(f"WebRTC connection {connection_id} disconnected")
                return web.json_response({'status': 'disconnected'})
            else:
                return web.json_response(
                    {'error': 'Connection not found'}, 
                    status=404
                )
                
        except Exception as e:
            logger.error(f"Error disconnecting WebRTC connection: {e}")
            return web.json_response(
                {'error': 'Failed to disconnect'}, 
                status=500
            )
    
    def set_ai_callback(self, callback: Callable) -> None:
        """
        Set callback for AI audio processing.
        
        Args:
            callback: Async function to handle audio chunks
                     Signature: async def callback(connection_id, audio_data, timestamp)
        """
        self.ai_callback = callback
        logger.info("AI audio callback configured")
    
    def get_connection(self, connection_id: str) -> Optional[WebRTCConnection]:
        """Get WebRTC connection by ID."""
        return self.connections.get(connection_id)
    
    def get_active_connections(self) -> Dict[str, WebRTCConnection]:
        """Get all active WebRTC connections."""
        return {
            conn_id: conn for conn_id, conn in self.connections.items() 
            if conn.connected
        }


# Global WebRTC gateway instance
webrtc_gateway: Optional[WebRTCGateway] = None


async def get_webrtc_gateway() -> WebRTCGateway:
    """Get or create the global WebRTC gateway instance."""
    global webrtc_gateway
    
    if webrtc_gateway is None:
        # Get configuration from Django settings
        webrtc_config = getattr(settings, 'WEBRTC_GATEWAY_CONFIG', {})
        
        webrtc_gateway = WebRTCGateway(
            host=webrtc_config.get('host', '0.0.0.0'),
            port=webrtc_config.get('port', 8765)
        )
    
    return webrtc_gateway


async def start_webrtc_gateway() -> None:
    """Start the global WebRTC gateway."""
    gateway = await get_webrtc_gateway()
    await gateway.start()


async def stop_webrtc_gateway() -> None:
    """Stop the global WebRTC gateway."""
    global webrtc_gateway
    
    if webrtc_gateway:
        await webrtc_gateway.stop()
        webrtc_gateway = None


# Integration helper functions
async def setup_ai_audio_callback(ai_processor_callback: Callable) -> None:
    """
    Setup AI audio processing callback for WebRTC gateway.
    
    Args:
        ai_processor_callback: Function to process audio for AI analysis
    """
    gateway = await get_webrtc_gateway()
    gateway.set_ai_callback(ai_processor_callback)


async def create_webrtc_connection_for_call(call_channel_id: str) -> Optional[str]:
    """
    Create WebRTC connection associated with a call.
    
    Args:
        call_channel_id: The call channel ID from Asterisk
        
    Returns:
        WebRTC connection ID if successful, None otherwise
    """
    try:
        gateway = await get_webrtc_gateway()
        
        # Generate connection ID based on call
        connection_id = f"call-{call_channel_id}"
        
        # WebRTC connection will be created when browser sends offer
        logger.info(f"WebRTC connection prepared for call {call_channel_id}")
        return connection_id
        
    except Exception as e:
        logger.error(f"Error creating WebRTC connection for call: {e}")
        return None
