"""
RTP Gateway for direct G.711 μ/A-law audio processing.
Handles RTP streams from Asterisk ExternalMedia channels for AI Media Gateway integration.
"""

import asyncio
import logging
import socket
import struct
from typing import Dict, Optional, Any, Callable, Tuple
from datetime import datetime
import numpy as np
from django.conf import settings

logger = logging.getLogger(__name__)


class G711Codec:
    """
    G.711 μ-law and A-law codec implementation.
    Handles conversion between G.711 and linear PCM.
    """
    
    # μ-law compression tables
    MULAW_BIAS = 0x84
    MULAW_CLIP = 32635
    
    # A-law compression tables  
    ALAW_CLIP = 32635
    
    @staticmethod
    def mulaw_to_linear(mulaw_byte: int) -> int:
        """
        Convert μ-law encoded byte to linear PCM sample.
        
        Args:
            mulaw_byte: μ-law encoded byte (0-255)
            
        Returns:
            Linear PCM sample (-32768 to 32767)
        """
        mulaw_byte = ~mulaw_byte
        sign = (mulaw_byte & 0x80)
        exponent = (mulaw_byte >> 4) & 0x07
        mantissa = mulaw_byte & 0x0F
        
        sample = mantissa << (exponent + 3)
        if exponent > 0:
            sample += (0x84 << exponent)
        
        if sign != 0:
            sample = -sample
            
        return max(-32768, min(32767, sample))
    
    @staticmethod
    def linear_to_mulaw(linear_sample: int) -> int:
        """
        Convert linear PCM sample to μ-law encoded byte.
        
        Args:
            linear_sample: Linear PCM sample (-32768 to 32767)
            
        Returns:
            μ-law encoded byte (0-255)
        """
        # Clip the sample
        sample = max(-G711Codec.MULAW_CLIP, min(G711Codec.MULAW_CLIP, linear_sample))
        
        # Get the sign bit
        sign = (sample >> 8) & 0x80
        if sign != 0:
            sample = -sample
        
        # Add bias
        sample += G711Codec.MULAW_BIAS
        
        # Find the exponent
        exponent = 0
        temp = sample >> 7
        while temp > 0 and exponent < 7:
            temp >>= 1
            exponent += 1
        
        # Extract mantissa
        mantissa = (sample >> (exponent + 3)) & 0x0F
        
        # Combine to create μ-law byte
        mulaw_byte = ~(sign | (exponent << 4) | mantissa)
        return mulaw_byte & 0xFF
    
    @staticmethod
    def alaw_to_linear(alaw_byte: int) -> int:
        """
        Convert A-law encoded byte to linear PCM sample.
        
        Args:
            alaw_byte: A-law encoded byte (0-255)
            
        Returns:
            Linear PCM sample (-32768 to 32767)
        """
        alaw_byte ^= 0x55  # XOR with 0x55 (A-law inversion)
        
        sign = alaw_byte & 0x80
        exponent = (alaw_byte >> 4) & 0x07
        mantissa = alaw_byte & 0x0F
        
        if exponent == 0:
            sample = (mantissa << 4) + 8
        else:
            sample = ((mantissa << 4) + 0x108) << (exponent - 1)
        
        if sign != 0:
            sample = -sample
            
        return max(-32768, min(32767, sample))
    
    @staticmethod
    def linear_to_alaw(linear_sample: int) -> int:
        """
        Convert linear PCM sample to A-law encoded byte.
        
        Args:
            linear_sample: Linear PCM sample (-32768 to 32767)
            
        Returns:
            A-law encoded byte (0-255)
        """
        # Clip the sample
        sample = max(-G711Codec.ALAW_CLIP, min(G711Codec.ALAW_CLIP, linear_sample))
        
        # Get the sign bit
        sign = (sample >> 8) & 0x80
        if sign != 0:
            sample = -sample
        
        # Find the exponent
        if sample >= 256:
            exponent = 0
            temp = sample >> 8
            while temp > 0 and exponent < 7:
                temp >>= 1
                exponent += 1
            mantissa = (sample >> (exponent + 3)) & 0x0F
        else:
            exponent = 0
            mantissa = sample >> 4
        
        # Combine to create A-law byte
        alaw_byte = sign | (exponent << 4) | mantissa
        return alaw_byte ^ 0x55  # XOR with 0x55 (A-law inversion)
    
    @classmethod
    def decode_g711_to_pcm(cls, g711_data: bytes, codec_type: str = "ulaw") -> bytes:
        """
        Decode G.711 data to linear PCM.
        
        Args:
            g711_data: G.711 encoded audio data
            codec_type: "ulaw" or "alaw"
            
        Returns:
            Linear PCM data (16-bit signed)
        """
        pcm_samples = []
        
        for byte in g711_data:
            if codec_type == "ulaw":
                sample = cls.mulaw_to_linear(byte)
            elif codec_type == "alaw":
                sample = cls.alaw_to_linear(byte)
            else:
                raise ValueError(f"Unsupported codec type: {codec_type}")
            
            pcm_samples.append(sample)
        
        # Convert to bytes (16-bit signed, little-endian)
        return struct.pack('<' + 'h' * len(pcm_samples), *pcm_samples)
    
    @classmethod
    def encode_pcm_to_g711(cls, pcm_data: bytes, codec_type: str = "ulaw") -> bytes:
        """
        Encode linear PCM to G.711.
        
        Args:
            pcm_data: Linear PCM data (16-bit signed)
            codec_type: "ulaw" or "alaw"
            
        Returns:
            G.711 encoded audio data
        """
        # Unpack PCM samples (16-bit signed, little-endian)
        sample_count = len(pcm_data) // 2
        pcm_samples = struct.unpack('<' + 'h' * sample_count, pcm_data)
        
        g711_bytes = []
        for sample in pcm_samples:
            if codec_type == "ulaw":
                encoded_byte = cls.linear_to_mulaw(sample)
            elif codec_type == "alaw":
                encoded_byte = cls.linear_to_alaw(sample)
            else:
                raise ValueError(f"Unsupported codec type: {codec_type}")
            
            g711_bytes.append(encoded_byte)
        
        return bytes(g711_bytes)


class RTPPacket:
    """
    RTP packet parser and generator.
    Handles RTP packet structure and payload extraction.
    """
    
    def __init__(self):
        self.version = 2
        self.padding = 0
        self.extension = 0
        self.cc = 0  # CSRC count
        self.marker = 0
        self.payload_type = 0
        self.sequence_number = 0
        self.timestamp = 0
        self.ssrc = 0
        self.payload = b''
    
    @classmethod
    def parse(cls, packet_data: bytes) -> 'RTPPacket':
        """
        Parse RTP packet from raw data.
        
        Args:
            packet_data: Raw RTP packet data
            
        Returns:
            Parsed RTPPacket object
        """
        if len(packet_data) < 12:
            raise ValueError("RTP packet too short")
        
        packet = cls()
        
        # Parse RTP header (12 bytes minimum)
        header = struct.unpack('!BBHII', packet_data[:12])
        
        # First byte: V(2), P(1), X(1), CC(4)
        first_byte = header[0]
        packet.version = (first_byte >> 6) & 0x03
        packet.padding = (first_byte >> 5) & 0x01
        packet.extension = (first_byte >> 4) & 0x01
        packet.cc = first_byte & 0x0F
        
        # Second byte: M(1), PT(7)
        second_byte = header[1]
        packet.marker = (second_byte >> 7) & 0x01
        packet.payload_type = second_byte & 0x7F
        
        packet.sequence_number = header[2]
        packet.timestamp = header[3]
        packet.ssrc = header[4]
        
        # Calculate header length
        header_length = 12 + (packet.cc * 4)
        
        # Handle extension header if present
        if packet.extension:
            if len(packet_data) < header_length + 4:
                raise ValueError("RTP packet with extension too short")
            
            ext_header = struct.unpack('!HH', packet_data[header_length:header_length + 4])
            ext_length = ext_header[1] * 4
            header_length += 4 + ext_length
        
        # Extract payload
        if len(packet_data) > header_length:
            packet.payload = packet_data[header_length:]
        
        return packet
    
    def to_bytes(self) -> bytes:
        """
        Convert RTP packet to bytes.
        
        Returns:
            RTP packet as bytes
        """
        # First byte: V(2), P(1), X(1), CC(4)
        first_byte = (self.version << 6) | (self.padding << 5) | (self.extension << 4) | self.cc
        
        # Second byte: M(1), PT(7)
        second_byte = (self.marker << 7) | self.payload_type
        
        # Pack header
        header = struct.pack('!BBHII', 
                           first_byte, second_byte,
                           self.sequence_number, self.timestamp, self.ssrc)
        
        return header + self.payload


class RTPSession:
    """
    RTP session handler for audio processing.
    Manages RTP stream reception and audio decoding.
    """
    
    def __init__(self, session_id: str, local_port: int, codec: str = "ulaw"):
        self.session_id = session_id
        self.local_port = local_port
        self.codec = codec.lower()
        
        # Socket for RTP reception
        self.socket: Optional[socket.socket] = None
        self.running = False
        
        # RTP state
        self.expected_sequence = None
        self.last_timestamp = None
        self.ssrc = None
        
        # Audio processing
        self.audio_buffer = bytearray()
        self.buffer_size_ms = 20  # 20ms buffer
        self.sample_rate = 8000  # G.711 is 8kHz
        self.buffer_size_bytes = (self.sample_rate * self.buffer_size_ms) // 1000
        
        # Callbacks
        self.on_audio_chunk: Optional[Callable] = None
        self.on_packet_lost: Optional[Callable] = None
        
        # Statistics
        self.packets_received = 0
        self.packets_lost = 0
        self.bytes_received = 0
        
        logger.info(f"RTP session created: {session_id} on port {local_port} with codec {codec}")
    
    async def start(self) -> None:
        """Start RTP session and begin receiving packets."""
        try:
            # Create UDP socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind(('0.0.0.0', self.local_port))
            self.socket.setblocking(False)
            
            self.running = True
            logger.info(f"RTP session {self.session_id} listening on port {self.local_port}")
            
            # Start receiving packets
            await self._receive_loop()
            
        except Exception as e:
            logger.error(f"Error starting RTP session {self.session_id}: {e}")
            raise
    
    async def stop(self) -> None:
        """Stop RTP session and cleanup resources."""
        try:
            self.running = False
            
            if self.socket:
                self.socket.close()
                self.socket = None
            
            # Process any remaining audio in buffer
            if len(self.audio_buffer) > 0:
                await self._process_audio_buffer(flush=True)
            
            logger.info(f"RTP session {self.session_id} stopped")
            
        except Exception as e:
            logger.error(f"Error stopping RTP session {self.session_id}: {e}")
    
    async def _receive_loop(self) -> None:
        """Main RTP packet reception loop."""
        while self.running:
            try:
                # Wait for data with timeout
                ready = await asyncio.wait_for(
                    asyncio.get_event_loop().sock_recv(self.socket, 2048),
                    timeout=1.0
                )
                
                if ready:
                    packet_data = ready
                    await self._process_rtp_packet(packet_data)
                
            except asyncio.TimeoutError:
                # Normal timeout, continue loop
                continue
            except Exception as e:
                if self.running:  # Only log if we're supposed to be running
                    logger.error(f"Error in RTP receive loop: {e}")
                break
    
    async def _process_rtp_packet(self, packet_data: bytes) -> None:
        """
        Process incoming RTP packet.
        
        Args:
            packet_data: Raw RTP packet data
        """
        try:
            # Parse RTP packet
            rtp_packet = RTPPacket.parse(packet_data)
            
            # Update statistics
            self.packets_received += 1
            self.bytes_received += len(packet_data)
            
            # Check for packet loss
            if self.expected_sequence is not None:
                sequence_diff = (rtp_packet.sequence_number - self.expected_sequence) & 0xFFFF
                if sequence_diff > 1:
                    lost_packets = sequence_diff - 1
                    self.packets_lost += lost_packets
                    
                    if self.on_packet_lost:
                        await self.on_packet_lost(self.session_id, lost_packets)
                    
                    logger.warning(f"RTP session {self.session_id}: {lost_packets} packets lost")
            
            self.expected_sequence = (rtp_packet.sequence_number + 1) & 0xFFFF
            
            # Store SSRC for session validation
            if self.ssrc is None:
                self.ssrc = rtp_packet.ssrc
            elif self.ssrc != rtp_packet.ssrc:
                logger.warning(f"RTP session {self.session_id}: SSRC mismatch")
            
            # Process audio payload
            if len(rtp_packet.payload) > 0:
                await self._process_audio_payload(rtp_packet.payload, rtp_packet.timestamp)
            
        except Exception as e:
            logger.error(f"Error processing RTP packet: {e}")
    
    async def _process_audio_payload(self, payload: bytes, timestamp: int) -> None:
        """
        Process RTP audio payload.
        
        Args:
            payload: Audio payload from RTP packet
            timestamp: RTP timestamp
        """
        try:
            # Decode G.711 to PCM
            pcm_data = G711Codec.decode_g711_to_pcm(payload, self.codec)
            
            # Add to audio buffer
            self.audio_buffer.extend(pcm_data)
            
            # Process buffer when we have enough data
            if len(self.audio_buffer) >= self.buffer_size_bytes * 2:  # *2 for 16-bit samples
                await self._process_audio_buffer()
            
        except Exception as e:
            logger.error(f"Error processing audio payload: {e}")
    
    async def _process_audio_buffer(self, flush: bool = False) -> None:
        """
        Process accumulated audio buffer.
        
        Args:
            flush: Whether to process all remaining data
        """
        try:
            if flush:
                # Process all remaining data
                if len(self.audio_buffer) > 0 and self.on_audio_chunk:
                    await self.on_audio_chunk(
                        session_id=self.session_id,
                        audio_data=bytes(self.audio_buffer),
                        sample_rate=self.sample_rate,
                        timestamp=datetime.now().isoformat()
                    )
                    self.audio_buffer.clear()
            else:
                # Process buffer_size chunks
                while len(self.audio_buffer) >= self.buffer_size_bytes * 2:
                    chunk_size = self.buffer_size_bytes * 2
                    chunk_data = bytes(self.audio_buffer[:chunk_size])
                    del self.audio_buffer[:chunk_size]
                    
                    if self.on_audio_chunk:
                        await self.on_audio_chunk(
                            session_id=self.session_id,
                            audio_data=chunk_data,
                            sample_rate=self.sample_rate,
                            timestamp=datetime.now().isoformat()
                        )
        
        except Exception as e:
            logger.error(f"Error processing audio buffer: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get RTP session statistics."""
        return {
            'session_id': self.session_id,
            'local_port': self.local_port,
            'codec': self.codec,
            'packets_received': self.packets_received,
            'packets_lost': self.packets_lost,
            'bytes_received': self.bytes_received,
            'loss_rate': self.packets_lost / max(1, self.packets_received + self.packets_lost),
            'running': self.running,
            'ssrc': self.ssrc
        }


class RTPGateway:
    """
    RTP Gateway for managing multiple RTP sessions.
    Coordinates RTP audio processing with AI Media Gateway.
    """
    
    def __init__(self, port_range: Tuple[int, int] = (10000, 10999)):
        self.port_range = port_range
        self.current_port = port_range[0]
        
        # Session management
        self.sessions: Dict[str, RTPSession] = {}
        self.port_to_session: Dict[int, str] = {}
        
        # Callbacks
        self.on_audio_chunk: Optional[Callable] = None
        self.on_session_started: Optional[Callable] = None
        self.on_session_stopped: Optional[Callable] = None
        
        logger.info(f"RTP Gateway initialized with port range {port_range}")
    
    def get_next_available_port(self) -> int:
        """Get next available port for RTP session."""
        # Find next available port
        while self.current_port <= self.port_range[1]:
            if self.current_port not in self.port_to_session:
                port = self.current_port
                self.current_port += 2  # Skip odd port for RTCP
                return port
            self.current_port += 2
        
        # Wrap around if we've used all ports
        self.current_port = self.port_range[0]
        
        # Try to find a free port by checking existing sessions
        for port in range(self.port_range[0], self.port_range[1] + 1, 2):
            if port not in self.port_to_session:
                return port
        
        raise RuntimeError("No available ports for RTP session")
    
    async def create_session(
        self,
        session_id: str,
        codec: str = "ulaw",
        port: Optional[int] = None
    ) -> RTPSession:
        """
        Create new RTP session.
        
        Args:
            session_id: Unique session identifier
            codec: Audio codec ("ulaw" or "alaw")
            port: Specific port to use (optional)
            
        Returns:
            Created RTPSession
        """
        try:
            if session_id in self.sessions:
                raise ValueError(f"Session {session_id} already exists")
            
            # Get port
            if port is None:
                port = self.get_next_available_port()
            elif port in self.port_to_session:
                raise ValueError(f"Port {port} already in use")
            
            # Create RTP session
            session = RTPSession(session_id, port, codec)
            
            # Set up callbacks
            session.on_audio_chunk = self._handle_audio_chunk
            session.on_packet_lost = self._handle_packet_lost
            
            # Store session
            self.sessions[session_id] = session
            self.port_to_session[port] = session_id
            
            logger.info(f"RTP session created: {session_id} on port {port}")
            
            if self.on_session_started:
                await self.on_session_started(session_id, session)
            
            return session
            
        except Exception as e:
            logger.error(f"Error creating RTP session {session_id}: {e}")
            raise
    
    async def start_session(self, session_id: str) -> None:
        """
        Start RTP session.
        
        Args:
            session_id: Session identifier
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session {session_id} not found")
        
        session = self.sessions[session_id]
        await session.start()
        
        logger.info(f"RTP session {session_id} started")
    
    async def stop_session(self, session_id: str) -> None:
        """
        Stop and remove RTP session.
        
        Args:
            session_id: Session identifier
        """
        if session_id not in self.sessions:
            logger.warning(f"Session {session_id} not found for stopping")
            return
        
        session = self.sessions[session_id]
        
        # Stop session
        await session.stop()
        
        # Remove from tracking
        self.port_to_session.pop(session.local_port, None)
        del self.sessions[session_id]
        
        logger.info(f"RTP session {session_id} stopped and removed")
        
        if self.on_session_stopped:
            await self.on_session_stopped(session_id)
    
    async def stop_all_sessions(self) -> None:
        """Stop all RTP sessions."""
        session_ids = list(self.sessions.keys())
        for session_id in session_ids:
            await self.stop_session(session_id)
        
        logger.info("All RTP sessions stopped")
    
    def get_session(self, session_id: str) -> Optional[RTPSession]:
        """Get RTP session by ID."""
        return self.sessions.get(session_id)
    
    def get_session_by_port(self, port: int) -> Optional[RTPSession]:
        """Get RTP session by port."""
        session_id = self.port_to_session.get(port)
        if session_id:
            return self.sessions.get(session_id)
        return None
    
    def get_all_sessions(self) -> Dict[str, RTPSession]:
        """Get all RTP sessions."""
        return self.sessions.copy()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get gateway statistics."""
        return {
            'total_sessions': len(self.sessions),
            'active_sessions': sum(1 for s in self.sessions.values() if s.running),
            'port_range': self.port_range,
            'used_ports': list(self.port_to_session.keys()),
            'sessions': {
                session_id: session.get_statistics()
                for session_id, session in self.sessions.items()
            }
        }
    
    async def _handle_audio_chunk(
        self,
        session_id: str,
        audio_data: bytes,
        sample_rate: int,
        timestamp: str
    ) -> None:
        """Handle audio chunk from RTP session."""
        try:
            if self.on_audio_chunk:
                await self.on_audio_chunk(
                    session_id=session_id,
                    audio_data=audio_data,
                    sample_rate=sample_rate,
                    timestamp=timestamp
                )
        except Exception as e:
            logger.error(f"Error handling audio chunk from session {session_id}: {e}")
    
    async def _handle_packet_lost(self, session_id: str, lost_count: int) -> None:
        """Handle packet loss notification."""
        logger.warning(f"RTP session {session_id}: {lost_count} packets lost")
    
    def set_audio_callback(self, callback: Callable) -> None:
        """
        Set callback for audio processing.
        
        Args:
            callback: Async function to handle audio chunks
                     Signature: async def callback(session_id, audio_data, sample_rate, timestamp)
        """
        self.on_audio_chunk = callback
        logger.info("RTP Gateway audio callback configured")


# Global RTP gateway instance
rtp_gateway: Optional[RTPGateway] = None


async def get_rtp_gateway() -> RTPGateway:
    """Get or create the global RTP gateway instance."""
    global rtp_gateway
    
    if rtp_gateway is None:
        # Get configuration from Django settings
        rtp_config = getattr(settings, 'RTP_GATEWAY_CONFIG', {})
        
        port_range = rtp_config.get('port_range', (10000, 10999))
        rtp_gateway = RTPGateway(port_range=port_range)
    
    return rtp_gateway


async def create_rtp_session_for_call(
    call_channel_id: str,
    codec: str = "ulaw"
) -> Optional[Tuple[str, int]]:
    """
    Create RTP session for a call channel.
    
    Args:
        call_channel_id: Call channel ID from Asterisk
        codec: Audio codec to use
        
    Returns:
        Tuple of (session_id, port) if successful, None otherwise
    """
    try:
        gateway = await get_rtp_gateway()
        
        session_id = f"call-{call_channel_id}"
        session = await gateway.create_session(session_id, codec)
        await gateway.start_session(session_id)
        
        logger.info(f"RTP session created for call {call_channel_id}: {session_id} on port {session.local_port}")
        return session_id, session.local_port
        
    except Exception as e:
        logger.error(f"Error creating RTP session for call {call_channel_id}: {e}")
        return None


async def stop_rtp_session_for_call(call_channel_id: str) -> None:
    """
    Stop RTP session for a call channel.
    
    Args:
        call_channel_id: Call channel ID from Asterisk
    """
    try:
        gateway = await get_rtp_gateway()
        session_id = f"call-{call_channel_id}"
        await gateway.stop_session(session_id)
        
        logger.info(f"RTP session stopped for call {call_channel_id}")
        
    except Exception as e:
        logger.error(f"Error stopping RTP session for call {call_channel_id}: {e}")


async def setup_rtp_audio_callback(ai_processor_callback: Callable) -> None:
    """
    Setup AI audio processing callback for RTP gateway.
    
    Args:
        ai_processor_callback: Function to process audio for AI analysis
    """
    gateway = await get_rtp_gateway()
    gateway.set_audio_callback(ai_processor_callback)
