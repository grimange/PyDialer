"""
Voice Activity Detection (VAD) module for audio chunking optimization.

This module implements Voice Activity Detection using webrtcvad to optimize
audio chunking for OpenAI Whisper transcription, reducing processing costs
and improving transcription quality by filtering out silence periods.
"""

import logging
import numpy as np
from typing import List, Optional, Tuple, Union
import struct
from collections import deque
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Try to import webrtcvad
try:
    import webrtcvad
    HAS_WEBRTCVAD = True
    logger.info("Using webrtcvad for Voice Activity Detection")
except ImportError:
    HAS_WEBRTCVAD = False
    logger.warning("webrtcvad not available, VAD will use fallback detection")


class VoiceActivityDetector:
    """
    Voice Activity Detection system for optimizing audio chunking.
    
    Uses webrtcvad library to detect speech activity and optimize
    audio chunks sent to Whisper for transcription.
    """
    
    # Supported sample rates by webrtcvad
    SUPPORTED_SAMPLE_RATES = [8000, 16000, 32000, 48000]
    
    def __init__(
        self,
        sample_rate: int = 16000,
        frame_duration_ms: int = 20,
        aggressiveness: int = 2,
        min_speech_duration_ms: int = 300,
        max_silence_duration_ms: int = 800,
        pre_speech_padding_ms: int = 100,
        post_speech_padding_ms: int = 200
    ):
        """
        Initialize Voice Activity Detector.
        
        Args:
            sample_rate: Audio sample rate (8000, 16000, 32000, or 48000 Hz)
            frame_duration_ms: Frame duration in milliseconds (10, 20, or 30 ms)
            aggressiveness: VAD aggressiveness level (0-3, higher = more aggressive)
            min_speech_duration_ms: Minimum speech duration to consider as voice activity
            max_silence_duration_ms: Maximum silence duration before ending speech segment
            pre_speech_padding_ms: Padding before speech starts
            post_speech_padding_ms: Padding after speech ends
        """
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.aggressiveness = aggressiveness
        self.min_speech_duration_ms = min_speech_duration_ms
        self.max_silence_duration_ms = max_silence_duration_ms
        self.pre_speech_padding_ms = pre_speech_padding_ms
        self.post_speech_padding_ms = post_speech_padding_ms
        
        # Validate parameters
        self._validate_parameters()
        
        # Calculate frame size in samples and bytes
        self.frame_size_samples = int(sample_rate * frame_duration_ms / 1000)
        self.frame_size_bytes = self.frame_size_samples * 2  # 16-bit samples
        
        # Initialize webrtcvad if available
        self.vad = None
        if HAS_WEBRTCVAD:
            self.vad = webrtcvad.Vad(aggressiveness)
            logger.info(f"WebRTC VAD initialized: rate={sample_rate}Hz, "
                       f"frame={frame_duration_ms}ms, aggr={aggressiveness}")
        else:
            logger.warning("Using fallback VAD implementation")
        
        # Internal state
        self._audio_buffer = deque()
        self._speech_frames = deque()
        self._silence_frames = deque()
        self._is_in_speech = False
        self._speech_start_time = None
        self._last_speech_time = None
        
        # Statistics
        self.stats = {
            'total_frames': 0,
            'speech_frames': 0,
            'silence_frames': 0,
            'speech_segments': 0,
            'total_audio_duration': 0.0,
            'speech_duration': 0.0,
            'silence_duration': 0.0
        }
    
    def _validate_parameters(self):
        """Validate VAD parameters."""
        if self.sample_rate not in self.SUPPORTED_SAMPLE_RATES:
            raise ValueError(f"Unsupported sample rate: {self.sample_rate}. "
                           f"Supported rates: {self.SUPPORTED_SAMPLE_RATES}")
        
        if self.frame_duration_ms not in [10, 20, 30]:
            raise ValueError(f"Unsupported frame duration: {self.frame_duration_ms}ms. "
                           f"Supported durations: [10, 20, 30]")
        
        if not 0 <= self.aggressiveness <= 3:
            raise ValueError(f"Aggressiveness must be 0-3, got: {self.aggressiveness}")
    
    def process_audio_chunk(
        self,
        audio_data: Union[bytes, np.ndarray],
        timestamp: Optional[datetime] = None
    ) -> List[Tuple[bytes, datetime, bool]]:
        """
        Process audio chunk and return speech segments.
        
        Args:
            audio_data: Audio data as bytes or numpy array (int16)
            timestamp: Timestamp of audio chunk
            
        Returns:
            List of tuples: (audio_segment, timestamp, is_final)
        """
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        # Convert to bytes if necessary
        if isinstance(audio_data, np.ndarray):
            audio_bytes = (audio_data * 32767).astype(np.int16).tobytes()
        else:
            audio_bytes = audio_data
        
        # Add to buffer
        self._audio_buffer.extend(audio_bytes)
        
        # Process complete frames
        speech_segments = []
        while len(self._audio_buffer) >= self.frame_size_bytes:
            # Extract one frame
            frame_bytes = bytes(list(self._audio_buffer)[:self.frame_size_bytes])
            for _ in range(self.frame_size_bytes):
                self._audio_buffer.popleft()
            
            # Detect voice activity in frame
            is_speech = self._detect_voice_activity(frame_bytes)
            
            # Process frame based on voice activity
            segments = self._process_frame(frame_bytes, timestamp, is_speech)
            speech_segments.extend(segments)
            
            # Update timestamp for next frame
            frame_duration_seconds = self.frame_duration_ms / 1000.0
            timestamp += timedelta(seconds=frame_duration_seconds)
        
        return speech_segments
    
    def _detect_voice_activity(self, frame_bytes: bytes) -> bool:
        """
        Detect voice activity in audio frame.
        
        Args:
            frame_bytes: Audio frame as bytes (16-bit PCM)
            
        Returns:
            True if voice activity detected, False otherwise
        """
        self.stats['total_frames'] += 1
        
        if self.vad and HAS_WEBRTCVAD:
            try:
                is_speech = self.vad.is_speech(frame_bytes, self.sample_rate)
            except Exception as e:
                logger.warning(f"WebRTC VAD error: {e}, using fallback")
                is_speech = self._fallback_vad(frame_bytes)
        else:
            is_speech = self._fallback_vad(frame_bytes)
        
        # Update statistics
        if is_speech:
            self.stats['speech_frames'] += 1
            self.stats['speech_duration'] += self.frame_duration_ms / 1000.0
        else:
            self.stats['silence_frames'] += 1
            self.stats['silence_duration'] += self.frame_duration_ms / 1000.0
        
        self.stats['total_audio_duration'] += self.frame_duration_ms / 1000.0
        
        return is_speech
    
    def _fallback_vad(self, frame_bytes: bytes) -> bool:
        """
        Fallback VAD implementation based on audio energy.
        
        Args:
            frame_bytes: Audio frame as bytes (16-bit PCM)
            
        Returns:
            True if voice activity detected, False otherwise
        """
        # Convert bytes to int16 samples
        samples = np.frombuffer(frame_bytes, dtype=np.int16)
        
        # Calculate RMS energy
        rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2))
        
        # Simple threshold-based detection
        # This is a basic implementation; in production, you might want
        # adaptive thresholding based on background noise estimation
        energy_threshold = 1000  # Adjust based on your audio characteristics
        
        return rms > energy_threshold
    
    def _process_frame(
        self,
        frame_bytes: bytes,
        timestamp: datetime,
        is_speech: bool
    ) -> List[Tuple[bytes, datetime, bool]]:
        """
        Process audio frame and manage speech segments.
        
        Args:
            frame_bytes: Audio frame as bytes
            timestamp: Frame timestamp
            is_speech: Whether frame contains speech
            
        Returns:
            List of speech segments ready for transcription
        """
        speech_segments = []
        
        if is_speech:
            self._last_speech_time = timestamp
            
            if not self._is_in_speech:
                # Starting new speech segment
                self._is_in_speech = True
                self._speech_start_time = timestamp
                self.stats['speech_segments'] += 1
                
                # Add pre-speech padding from silence buffer
                padding_frames = min(
                    len(self._silence_frames),
                    self.pre_speech_padding_ms // self.frame_duration_ms
                )
                
                for _ in range(padding_frames):
                    if self._silence_frames:
                        self._speech_frames.append(self._silence_frames.popleft())
                
                logger.debug(f"Speech segment started at {timestamp} "
                           f"with {padding_frames} padding frames")
            
            # Add speech frame to current segment
            self._speech_frames.append(frame_bytes)
            
            # Clear silence buffer since we're in speech
            self._silence_frames.clear()
        
        else:  # silence
            if self._is_in_speech:
                # Add silence frame to speech segment (for post-speech padding)
                self._silence_frames.append(frame_bytes)
                
                # Check if silence duration exceeded threshold
                silence_duration = len(self._silence_frames) * self.frame_duration_ms
                
                if silence_duration >= self.max_silence_duration_ms:
                    # End speech segment
                    segment = self._finalize_speech_segment(timestamp)
                    if segment:
                        speech_segments.append(segment)
            else:
                # Pure silence - keep limited buffer for pre-speech padding
                self._silence_frames.append(frame_bytes)
                
                # Limit silence buffer size
                max_silence_frames = self.pre_speech_padding_ms // self.frame_duration_ms
                while len(self._silence_frames) > max_silence_frames:
                    self._silence_frames.popleft()
        
        return speech_segments
    
    def _finalize_speech_segment(
        self,
        end_timestamp: datetime
    ) -> Optional[Tuple[bytes, datetime, bool]]:
        """
        Finalize current speech segment.
        
        Args:
            end_timestamp: End timestamp of speech segment
            
        Returns:
            Speech segment tuple or None if too short
        """
        if not self._speech_frames:
            return None
        
        # Calculate speech duration
        speech_duration = len(self._speech_frames) * self.frame_duration_ms
        
        # Check minimum speech duration
        if speech_duration < self.min_speech_duration_ms:
            logger.debug(f"Speech segment too short ({speech_duration}ms), discarding")
            self._speech_frames.clear()
            self._silence_frames.clear()
            self._is_in_speech = False
            return None
        
        # Add post-speech padding
        padding_frames = min(
            len(self._silence_frames),
            self.post_speech_padding_ms // self.frame_duration_ms
        )
        
        # Combine speech and padding frames
        segment_frames = list(self._speech_frames)
        for _ in range(padding_frames):
            if self._silence_frames:
                segment_frames.append(self._silence_frames.popleft())
        
        # Create final segment
        segment_bytes = b''.join(segment_frames)
        segment_timestamp = self._speech_start_time
        
        logger.info(f"Finalized speech segment: duration={speech_duration}ms, "
                   f"size={len(segment_bytes)} bytes, "
                   f"padding_frames={padding_frames}")
        
        # Reset state
        self._speech_frames.clear()
        self._silence_frames.clear()
        self._is_in_speech = False
        self._speech_start_time = None
        
        return (segment_bytes, segment_timestamp, True)
    
    def flush(self, timestamp: Optional[datetime] = None) -> List[Tuple[bytes, datetime, bool]]:
        """
        Flush any remaining audio segments.
        
        Args:
            timestamp: Current timestamp
            
        Returns:
            List of remaining speech segments
        """
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        segments = []
        
        if self._is_in_speech and self._speech_frames:
            # Force finalize current speech segment
            segment = self._finalize_speech_segment(timestamp)
            if segment:
                segments.append(segment)
        
        return segments
    
    def get_statistics(self) -> dict:
        """
        Get VAD processing statistics.
        
        Returns:
            Dictionary containing VAD statistics
        """
        stats = self.stats.copy()
        
        if stats['total_frames'] > 0:
            stats['speech_ratio'] = stats['speech_frames'] / stats['total_frames']
            stats['silence_ratio'] = stats['silence_frames'] / stats['total_frames']
        else:
            stats['speech_ratio'] = 0.0
            stats['silence_ratio'] = 0.0
        
        return stats
    
    def reset(self):
        """Reset VAD state and statistics."""
        self._audio_buffer.clear()
        self._speech_frames.clear()
        self._silence_frames.clear()
        self._is_in_speech = False
        self._speech_start_time = None
        self._last_speech_time = None
        
        # Reset statistics
        for key in self.stats:
            self.stats[key] = 0 if isinstance(self.stats[key], (int, float)) else self.stats[key]
        
        logger.info("VAD state and statistics reset")


class VADOptimizer:
    """
    VAD-based audio chunk optimizer for Whisper transcription.
    
    Manages multiple VAD instances and optimizes audio chunks
    for cost-effective and high-quality transcription.
    """
    
    def __init__(self, default_config: Optional[dict] = None):
        """
        Initialize VAD optimizer.
        
        Args:
            default_config: Default VAD configuration
        """
        self.default_config = default_config or {
            'sample_rate': 16000,
            'frame_duration_ms': 20,
            'aggressiveness': 2,
            'min_speech_duration_ms': 300,
            'max_silence_duration_ms': 800,
            'pre_speech_padding_ms': 100,
            'post_speech_padding_ms': 200
        }
        
        # Active VAD instances per session/call
        self._vad_instances = {}
        
        logger.info("VAD Optimizer initialized")
    
    def create_vad_for_session(
        self,
        session_id: str,
        config: Optional[dict] = None
    ) -> VoiceActivityDetector:
        """
        Create VAD instance for audio session.
        
        Args:
            session_id: Unique session identifier
            config: VAD configuration (uses default if None)
            
        Returns:
            VoiceActivityDetector instance
        """
        if config is None:
            config = self.default_config.copy()
        
        vad = VoiceActivityDetector(**config)
        self._vad_instances[session_id] = vad
        
        logger.info(f"Created VAD instance for session {session_id}")
        return vad
    
    def process_session_audio(
        self,
        session_id: str,
        audio_data: Union[bytes, np.ndarray],
        timestamp: Optional[datetime] = None
    ) -> List[Tuple[bytes, datetime, bool]]:
        """
        Process audio for specific session.
        
        Args:
            session_id: Session identifier
            audio_data: Audio data
            timestamp: Audio timestamp
            
        Returns:
            List of speech segments ready for transcription
        """
        if session_id not in self._vad_instances:
            self.create_vad_for_session(session_id)
        
        vad = self._vad_instances[session_id]
        return vad.process_audio_chunk(audio_data, timestamp)
    
    def flush_session(
        self,
        session_id: str,
        timestamp: Optional[datetime] = None
    ) -> List[Tuple[bytes, datetime, bool]]:
        """
        Flush remaining audio segments for session.
        
        Args:
            session_id: Session identifier
            timestamp: Current timestamp
            
        Returns:
            List of remaining speech segments
        """
        if session_id not in self._vad_instances:
            return []
        
        vad = self._vad_instances[session_id]
        return vad.flush(timestamp)
    
    def remove_session(self, session_id: str) -> dict:
        """
        Remove VAD instance for session and return statistics.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Session VAD statistics
        """
        if session_id in self._vad_instances:
            vad = self._vad_instances[session_id]
            stats = vad.get_statistics()
            del self._vad_instances[session_id]
            logger.info(f"Removed VAD instance for session {session_id}")
            return stats
        
        return {}
    
    def get_session_statistics(self, session_id: str) -> dict:
        """
        Get VAD statistics for session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Session VAD statistics
        """
        if session_id in self._vad_instances:
            return self._vad_instances[session_id].get_statistics()
        
        return {}
    
    def get_all_statistics(self) -> dict:
        """
        Get aggregated statistics for all sessions.
        
        Returns:
            Aggregated VAD statistics
        """
        all_stats = {}
        
        for session_id, vad in self._vad_instances.items():
            all_stats[session_id] = vad.get_statistics()
        
        return all_stats


# Global VAD optimizer instance
_vad_optimizer = None


def get_vad_optimizer() -> VADOptimizer:
    """
    Get global VAD optimizer instance.
    
    Returns:
        VADOptimizer instance
    """
    global _vad_optimizer
    
    if _vad_optimizer is None:
        _vad_optimizer = VADOptimizer()
    
    return _vad_optimizer
