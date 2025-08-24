"""
OpenAI TTS (Text-to-Speech) integration for AI response playback.
Handles real-time text-to-speech generation for AI Media Gateway.
"""

import asyncio
import logging
import tempfile
import os
from typing import Optional, Dict, Any, List, Callable, Union, Literal
from datetime import datetime, timedelta
import aiohttp
import json
from dataclasses import dataclass, asdict
from django.conf import settings

logger = logging.getLogger(__name__)

# Try to import soundfile for audio file operations
try:
    import soundfile as sf
    HAS_SOUNDFILE = True
except ImportError:
    HAS_SOUNDFILE = False
    logger.warning("soundfile not available, using temporary file fallback")


@dataclass
class TTSResult:
    """Result of text-to-speech generation."""
    audio_data: bytes
    format: str
    sample_rate: int
    duration: Optional[float] = None
    processing_time: Optional[float] = None
    timestamp: Optional[str] = None
    text: Optional[str] = None
    voice: Optional[str] = None
    model: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization (excluding audio_data)."""
        result = asdict(self)
        # Don't serialize audio_data as it's binary
        result.pop('audio_data', None)
        return result


@dataclass
class TTSConfig:
    """Configuration for OpenAI TTS API integration."""
    api_key: str
    model: Literal["tts-1", "tts-1-hd"] = "tts-1"
    voice: Literal["alloy", "echo", "fable", "onyx", "nova", "shimmer"] = "alloy"
    response_format: Literal["mp3", "opus", "aac", "flac", "wav", "pcm"] = "wav"
    speed: float = 1.0  # 0.25 to 4.0
    timeout: int = 30
    max_retries: int = 3
    base_url: str = "https://api.openai.com/v1"
    max_text_length: int = 4096  # OpenAI TTS limit


class TTSRateLimiter:
    """
    Rate limiter for OpenAI TTS API calls.
    Implements token bucket algorithm with backoff.
    """
    
    def __init__(
        self,
        requests_per_minute: int = 50,
        requests_per_hour: int = 1000,
        max_characters_per_hour: int = 500000
    ):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.max_characters_per_hour = max_characters_per_hour
        
        # Token buckets
        self.minute_tokens = requests_per_minute
        self.hour_tokens = requests_per_hour
        self.characters_used = 0
        
        # Timestamps for bucket refill
        self.last_minute_refill = datetime.now()
        self.last_hour_refill = datetime.now()
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
        
        logger.info(f"TTS rate limiter initialized: {requests_per_minute}/min, {requests_per_hour}/hour")
    
    async def acquire(self, text_length: int = 0) -> bool:
        """
        Acquire permission for API call.
        
        Args:
            text_length: Number of characters to be synthesized
            
        Returns:
            True if permission granted, False if rate limited
        """
        async with self._lock:
            now = datetime.now()
            
            # Refill token buckets
            await self._refill_buckets(now)
            
            # Check rate limits
            if self.minute_tokens < 1:
                logger.warning("Rate limited: minute requests exceeded")
                return False
            
            if self.hour_tokens < 1:
                logger.warning("Rate limited: hourly requests exceeded")
                return False
            
            if self.characters_used + text_length > self.max_characters_per_hour:
                logger.warning("Rate limited: hourly character limit exceeded")
                return False
            
            # Consume tokens
            self.minute_tokens -= 1
            self.hour_tokens -= 1
            self.characters_used += text_length
            
            return True
    
    async def _refill_buckets(self, now: datetime) -> None:
        """Refill token buckets based on elapsed time."""
        # Refill minute bucket
        if (now - self.last_minute_refill).total_seconds() >= 60:
            self.minute_tokens = self.requests_per_minute
            self.last_minute_refill = now
        
        # Refill hour bucket
        if (now - self.last_hour_refill).total_seconds() >= 3600:
            self.hour_tokens = self.requests_per_hour
            self.characters_used = 0
            self.last_hour_refill = now


class TTSError(Exception):
    """Custom exception for TTS-related errors."""
    pass


class TTSAPIError(TTSError):
    """Exception for OpenAI TTS API errors."""
    def __init__(self, message: str, status_code: int = None, response_data: Dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data or {}


class TTSService:
    """
    OpenAI TTS (Text-to-Speech) service for AI response playback.
    Handles text-to-speech generation with rate limiting and error handling.
    """
    
    def __init__(
        self,
        config: Optional[TTSConfig] = None,
        rate_limiter: Optional[TTSRateLimiter] = None
    ):
        self.config = config or self._create_default_config()
        self.rate_limiter = rate_limiter or TTSRateLimiter()
        self.session: Optional[aiohttp.ClientSession] = None
        self._callbacks: List[Callable[[TTSResult], None]] = []
        
        logger.info(f"TTS service initialized with model: {self.config.model}, voice: {self.config.voice}")
    
    def _create_default_config(self) -> TTSConfig:
        """Create default configuration from Django settings."""
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if not api_key:
            raise TTSError("OPENAI_API_KEY not configured in Django settings")
        
        return TTSConfig(
            api_key=api_key,
            model=getattr(settings, 'TTS_MODEL', 'tts-1'),
            voice=getattr(settings, 'TTS_VOICE', 'alloy'),
            response_format=getattr(settings, 'TTS_FORMAT', 'wav'),
            speed=getattr(settings, 'TTS_SPEED', 1.0),
            timeout=getattr(settings, 'TTS_TIMEOUT', 30),
            max_retries=getattr(settings, 'TTS_MAX_RETRIES', 3),
        )
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()
    
    async def start(self) -> None:
        """Initialize the TTS service."""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self.session = aiohttp.ClientSession(timeout=timeout)
            logger.info("TTS service started")
    
    async def stop(self) -> None:
        """Clean up the TTS service."""
        if self.session:
            await self.session.close()
            self.session = None
            logger.info("TTS service stopped")
    
    def add_callback(self, callback: Callable[[TTSResult], None]) -> None:
        """Add callback for TTS completion events."""
        self._callbacks.append(callback)
    
    def remove_callback(self, callback: Callable[[TTSResult], None]) -> None:
        """Remove callback for TTS completion events."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    async def synthesize_speech(
        self,
        text: str,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        speed: Optional[float] = None,
        response_format: Optional[str] = None
    ) -> TTSResult:
        """
        Synthesize speech from text using OpenAI TTS API.
        
        Args:
            text: Text to synthesize
            voice: Voice to use (overrides config)
            model: Model to use (overrides config)
            speed: Speed multiplier (overrides config)
            response_format: Audio format (overrides config)
            
        Returns:
            TTSResult with generated audio data
        """
        if not self.session:
            raise TTSError("TTS service not started. Call start() first.")
        
        # Validate text length
        if len(text) > self.config.max_text_length:
            raise TTSError(f"Text length ({len(text)}) exceeds maximum ({self.config.max_text_length})")
        
        if not text.strip():
            raise TTSError("Text cannot be empty")
        
        # Check rate limits
        if not await self.rate_limiter.acquire(len(text)):
            raise TTSError("Rate limit exceeded. Please try again later.")
        
        # Prepare parameters
        params = {
            "model": model or self.config.model,
            "input": text,
            "voice": voice or self.config.voice,
            "response_format": response_format or self.config.response_format,
            "speed": speed or self.config.speed
        }
        
        start_time = datetime.now()
        
        try:
            result = await self._make_api_call(params)
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            # Create TTS result
            tts_result = TTSResult(
                audio_data=result['audio_data'],
                format=params['response_format'],
                sample_rate=self._get_sample_rate_for_format(params['response_format']),
                processing_time=processing_time,
                timestamp=start_time.isoformat(),
                text=text,
                voice=params['voice'],
                model=params['model']
            )
            
            # Calculate duration if possible
            if HAS_SOUNDFILE and params['response_format'] in ['wav', 'flac']:
                try:
                    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                        tmp_file.write(result['audio_data'])
                        tmp_file.flush()
                        
                        info = sf.info(tmp_file.name)
                        tts_result.duration = info.duration
                        
                        os.unlink(tmp_file.name)
                except Exception as e:
                    logger.warning(f"Could not determine audio duration: {e}")
            
            logger.info(f"TTS synthesis completed in {processing_time:.2f}s for {len(text)} characters")
            
            # Notify callbacks
            for callback in self._callbacks:
                try:
                    callback(tts_result)
                except Exception as e:
                    logger.error(f"Error in TTS callback: {e}")
            
            return tts_result
            
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            raise
    
    async def _make_api_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Make API call to OpenAI TTS endpoint with retry logic."""
        url = f"{self.config.base_url}/audio/speech"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json"
        }
        
        last_error = None
        
        for attempt in range(self.config.max_retries + 1):
            try:
                async with self.session.post(url, headers=headers, json=params) as response:
                    if response.status == 200:
                        audio_data = await response.read()
                        return {"audio_data": audio_data}
                    else:
                        error_text = await response.text()
                        try:
                            error_data = json.loads(error_text)
                        except json.JSONDecodeError:
                            error_data = {"error": {"message": error_text}}
                        
                        error_msg = error_data.get("error", {}).get("message", f"HTTP {response.status}")
                        raise TTSAPIError(
                            f"OpenAI TTS API error: {error_msg}",
                            status_code=response.status,
                            response_data=error_data
                        )
            
            except aiohttp.ClientError as e:
                last_error = TTSAPIError(f"Network error: {str(e)}")
                if attempt < self.config.max_retries:
                    wait_time = (2 ** attempt) * 1.0  # Exponential backoff
                    logger.warning(f"TTS API call failed (attempt {attempt + 1}/{self.config.max_retries + 1}), retrying in {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                    continue
            except Exception as e:
                last_error = e
                break
        
        raise last_error or TTSError("TTS API call failed after all retries")
    
    def _get_sample_rate_for_format(self, format: str) -> int:
        """Get sample rate for audio format."""
        # OpenAI TTS typically outputs at 24kHz for most formats
        format_rates = {
            'wav': 24000,
            'mp3': 24000,
            'opus': 24000,
            'aac': 24000,
            'flac': 24000,
            'pcm': 24000
        }
        return format_rates.get(format, 24000)
    
    async def synthesize_and_save(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        model: Optional[str] = None,
        speed: Optional[float] = None,
        response_format: Optional[str] = None
    ) -> TTSResult:
        """
        Synthesize speech and save to file.
        
        Args:
            text: Text to synthesize
            output_path: Path to save audio file
            voice: Voice to use (overrides config)
            model: Model to use (overrides config) 
            speed: Speed multiplier (overrides config)
            response_format: Audio format (overrides config)
            
        Returns:
            TTSResult with generated audio data
        """
        result = await self.synthesize_speech(text, voice, model, speed, response_format)
        
        # Save to file
        with open(output_path, 'wb') as f:
            f.write(result.audio_data)
        
        logger.info(f"TTS audio saved to: {output_path}")
        return result
    
    def get_available_voices(self) -> List[str]:
        """Get list of available voices."""
        return ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
    
    def get_available_models(self) -> List[str]:
        """Get list of available models."""
        return ["tts-1", "tts-1-hd"]
    
    def get_supported_formats(self) -> List[str]:
        """Get list of supported audio formats."""
        return ["mp3", "opus", "aac", "flac", "wav", "pcm"]


# Global TTS service instance
_tts_service: Optional[TTSService] = None


async def get_tts_service() -> TTSService:
    """Get or create global TTS service instance."""
    global _tts_service
    if _tts_service is None:
        _tts_service = TTSService()
        await _tts_service.start()
    return _tts_service


async def cleanup_tts_service() -> None:
    """Clean up global TTS service instance."""
    global _tts_service
    if _tts_service:
        await _tts_service.stop()
        _tts_service = None


# Convenience functions for direct usage
async def synthesize_text(
    text: str,
    voice: str = "alloy",
    model: str = "tts-1",
    speed: float = 1.0,
    format: str = "wav"
) -> TTSResult:
    """
    Quick text-to-speech synthesis.
    
    Args:
        text: Text to synthesize
        voice: Voice to use
        model: Model to use
        speed: Speed multiplier
        format: Audio format
        
    Returns:
        TTSResult with generated audio
    """
    service = await get_tts_service()
    return await service.synthesize_speech(
        text=text,
        voice=voice,
        model=model,
        speed=speed,
        response_format=format
    )


async def synthesize_to_file(
    text: str,
    output_path: str,
    voice: str = "alloy",
    model: str = "tts-1",
    speed: float = 1.0,
    format: str = "wav"
) -> TTSResult:
    """
    Quick text-to-speech synthesis with file output.
    
    Args:
        text: Text to synthesize
        output_path: Path to save audio file
        voice: Voice to use
        model: Model to use
        speed: Speed multiplier
        format: Audio format
        
    Returns:
        TTSResult with generated audio
    """
    service = await get_tts_service()
    return await service.synthesize_and_save(
        text=text,
        output_path=output_path,
        voice=voice,
        model=model,
        speed=speed,
        response_format=format
    )
