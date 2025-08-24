"""
OpenAI Whisper integration for speech-to-text transcription.
Handles real-time audio transcription for AI Media Gateway.
"""

import asyncio
import logging
import tempfile
import os
from typing import Optional, Dict, Any, List, Callable, Union
from datetime import datetime, timedelta
import numpy as np
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
class TranscriptionResult:
    """Result of speech-to-text transcription."""
    text: str
    language: Optional[str] = None
    confidence: Optional[float] = None
    segments: Optional[List[Dict[str, Any]]] = None
    processing_time: Optional[float] = None
    timestamp: Optional[str] = None
    audio_duration: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class WhisperConfig:
    """Configuration for Whisper API integration."""
    api_key: str
    model: str = "whisper-1"
    language: Optional[str] = None  # Auto-detect if None
    prompt: Optional[str] = None
    response_format: str = "verbose_json"
    temperature: float = 0.0
    timeout: int = 30
    max_retries: int = 3
    base_url: str = "https://api.openai.com/v1"


class WhisperRateLimiter:
    """
    Rate limiter for OpenAI Whisper API calls.
    Implements token bucket algorithm with backoff.
    """
    
    def __init__(
        self,
        requests_per_minute: int = 50,
        requests_per_hour: int = 1000,
        max_audio_minutes_per_hour: int = 200
    ):
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.max_audio_minutes_per_hour = max_audio_minutes_per_hour
        
        # Token buckets
        self.minute_tokens = requests_per_minute
        self.hour_tokens = requests_per_hour
        self.audio_minutes_used = 0.0
        
        # Timestamps for bucket refill
        self.last_minute_refill = datetime.now()
        self.last_hour_refill = datetime.now()
        
        # Lock for thread safety
        self._lock = asyncio.Lock()
        
        logger.info(f"Whisper rate limiter initialized: {requests_per_minute}/min, {requests_per_hour}/hour")
    
    async def acquire(self, audio_duration_seconds: float = 0.0) -> bool:
        """
        Acquire permission for API call.
        
        Args:
            audio_duration_seconds: Duration of audio to be processed
            
        Returns:
            True if permission granted, False if rate limited
        """
        async with self._lock:
            now = datetime.now()
            audio_minutes = audio_duration_seconds / 60.0
            
            # Refill token buckets
            await self._refill_buckets(now)
            
            # Check rate limits
            if self.minute_tokens < 1:
                logger.warning("Rate limited: minute requests exceeded")
                return False
            
            if self.hour_tokens < 1:
                logger.warning("Rate limited: hourly requests exceeded")
                return False
            
            if self.audio_minutes_used + audio_minutes > self.max_audio_minutes_per_hour:
                logger.warning("Rate limited: hourly audio minutes exceeded")
                return False
            
            # Consume tokens
            self.minute_tokens -= 1
            self.hour_tokens -= 1
            self.audio_minutes_used += audio_minutes
            
            return True
    
    async def _refill_buckets(self, now: datetime) -> None:
        """Refill token buckets based on elapsed time."""
        # Refill minute bucket
        if now - self.last_minute_refill >= timedelta(minutes=1):
            minutes_elapsed = (now - self.last_minute_refill).total_seconds() / 60.0
            tokens_to_add = int(minutes_elapsed * self.requests_per_minute)
            self.minute_tokens = min(
                self.requests_per_minute,
                self.minute_tokens + tokens_to_add
            )
            self.last_minute_refill = now
        
        # Refill hour bucket
        if now - self.last_hour_refill >= timedelta(hours=1):
            self.hour_tokens = self.requests_per_hour
            self.audio_minutes_used = 0.0
            self.last_hour_refill = now
    
    def get_status(self) -> Dict[str, Any]:
        """Get current rate limiter status."""
        return {
            "minute_tokens_available": self.minute_tokens,
            "hour_tokens_available": self.hour_tokens,
            "audio_minutes_used": self.audio_minutes_used,
            "audio_minutes_remaining": self.max_audio_minutes_per_hour - self.audio_minutes_used
        }


class WhisperClient:
    """
    OpenAI Whisper API client with async support.
    Handles authentication, request formatting, and error handling.
    """
    
    def __init__(self, config: WhisperConfig):
        self.config = config
        self.rate_limiter = WhisperRateLimiter()
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Statistics
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.total_audio_processed = 0.0
        
        logger.info(f"Whisper client initialized with model: {config.model}")
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()
    
    async def start(self) -> None:
        """Start the Whisper client."""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self.session = aiohttp.ClientSession(timeout=timeout)
        
        logger.info("Whisper client started")
    
    async def stop(self) -> None:
        """Stop the Whisper client."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
        
        logger.info("Whisper client stopped")
    
    async def transcribe_audio(
        self,
        audio_data: np.ndarray,
        sample_rate: int = 16000,
        language: Optional[str] = None,
        prompt: Optional[str] = None
    ) -> TranscriptionResult:
        """
        Transcribe audio using OpenAI Whisper API.
        
        Args:
            audio_data: Audio data as numpy array (float32, -1 to 1)
            sample_rate: Audio sample rate
            language: Language code (optional, auto-detect if None)
            prompt: Context prompt for better accuracy (optional)
            
        Returns:
            TranscriptionResult with transcription and metadata
        """
        start_time = datetime.now()
        audio_duration = len(audio_data) / sample_rate
        
        try:
            # Check rate limits
            if not await self.rate_limiter.acquire(audio_duration):
                raise Exception("Rate limited by Whisper API limits")
            
            # Prepare audio file
            audio_file_data = await self._prepare_audio_file(audio_data, sample_rate)
            
            # Make API request
            response_data = await self._make_api_request(
                audio_file_data, language or self.config.language, prompt
            )
            
            # Parse response
            result = self._parse_response(response_data, start_time, audio_duration)
            
            # Update statistics
            self.total_requests += 1
            self.successful_requests += 1
            self.total_audio_processed += audio_duration
            
            logger.debug(f"Transcription completed in {result.processing_time:.3f}s: {result.text[:50]}...")
            
            return result
            
        except Exception as e:
            self.total_requests += 1
            self.failed_requests += 1
            logger.error(f"Whisper transcription failed: {e}")
            
            # Return empty result on failure
            return TranscriptionResult(
                text="",
                timestamp=start_time.isoformat(),
                audio_duration=audio_duration,
                processing_time=(datetime.now() - start_time).total_seconds()
            )
    
    async def _prepare_audio_file(
        self,
        audio_data: np.ndarray,
        sample_rate: int
    ) -> bytes:
        """
        Prepare audio data for API upload.
        
        Args:
            audio_data: Audio data as numpy array
            sample_rate: Audio sample rate
            
        Returns:
            Audio file data as bytes (WAV format)
        """
        try:
            if HAS_SOUNDFILE:
                # Use soundfile for high-quality audio encoding
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                    sf.write(temp_file.name, audio_data, sample_rate, format='WAV', subtype='PCM_16')
                    
                    with open(temp_file.name, 'rb') as f:
                        audio_bytes = f.read()
                    
                    os.unlink(temp_file.name)
                    
                return audio_bytes
            else:
                # Fallback: Create simple WAV file manually
                return self._create_wav_bytes(audio_data, sample_rate)
                
        except Exception as e:
            logger.error(f"Error preparing audio file: {e}")
            raise
    
    def _create_wav_bytes(
        self,
        audio_data: np.ndarray,
        sample_rate: int
    ) -> bytes:
        """
        Create WAV file bytes manually (fallback method).
        
        Args:
            audio_data: Audio data as numpy array (float32)
            sample_rate: Audio sample rate
            
        Returns:
            WAV file as bytes
        """
        # Convert float32 to int16
        audio_int16 = (audio_data * 32767).astype(np.int16)
        audio_bytes = audio_int16.tobytes()
        
        # WAV header
        file_size = len(audio_bytes) + 36
        wav_header = b'RIFF'
        wav_header += file_size.to_bytes(4, 'little')
        wav_header += b'WAVE'
        wav_header += b'fmt '
        wav_header += (16).to_bytes(4, 'little')  # PCM format size
        wav_header += (1).to_bytes(2, 'little')   # PCM format
        wav_header += (1).to_bytes(2, 'little')   # Mono
        wav_header += sample_rate.to_bytes(4, 'little')
        wav_header += (sample_rate * 2).to_bytes(4, 'little')  # Byte rate
        wav_header += (2).to_bytes(2, 'little')   # Block align
        wav_header += (16).to_bytes(2, 'little')  # Bits per sample
        wav_header += b'data'
        wav_header += len(audio_bytes).to_bytes(4, 'little')
        
        return wav_header + audio_bytes
    
    async def _make_api_request(
        self,
        audio_file_data: bytes,
        language: Optional[str],
        prompt: Optional[str]
    ) -> Dict[str, Any]:
        """
        Make API request to OpenAI Whisper.
        
        Args:
            audio_file_data: Audio file as bytes
            language: Language code
            prompt: Context prompt
            
        Returns:
            API response data
        """
        if not self.session:
            raise RuntimeError("Whisper client not started")
        
        url = f"{self.config.base_url}/audio/transcriptions"
        
        # Prepare form data
        data = aiohttp.FormData()
        data.add_field('file', audio_file_data, filename='audio.wav', content_type='audio/wav')
        data.add_field('model', self.config.model)
        data.add_field('response_format', self.config.response_format)
        data.add_field('temperature', str(self.config.temperature))
        
        if language:
            data.add_field('language', language)
        
        if prompt or self.config.prompt:
            data.add_field('prompt', prompt or self.config.prompt)
        
        # Prepare headers
        headers = {
            'Authorization': f'Bearer {self.config.api_key}'
        }
        
        # Make request with retries
        for attempt in range(self.config.max_retries):
            try:
                async with self.session.post(url, data=data, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 429:
                        # Rate limited - wait and retry
                        wait_time = 2 ** attempt
                        logger.warning(f"Rate limited, waiting {wait_time}s before retry")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        error_text = await response.text()
                        raise aiohttp.ClientResponseError(
                            response.request_info,
                            response.history,
                            status=response.status,
                            message=error_text
                        )
                        
            except aiohttp.ClientError as e:
                if attempt == self.config.max_retries - 1:
                    raise
                
                wait_time = 2 ** attempt
                logger.warning(f"API request failed (attempt {attempt + 1}), retrying in {wait_time}s: {e}")
                await asyncio.sleep(wait_time)
        
        raise Exception("Max retries exceeded")
    
    def _parse_response(
        self,
        response_data: Dict[str, Any],
        start_time: datetime,
        audio_duration: float
    ) -> TranscriptionResult:
        """
        Parse Whisper API response.
        
        Args:
            response_data: API response JSON
            start_time: Request start time
            audio_duration: Audio duration in seconds
            
        Returns:
            Parsed TranscriptionResult
        """
        processing_time = (datetime.now() - start_time).total_seconds()
        
        if self.config.response_format == "verbose_json":
            return TranscriptionResult(
                text=response_data.get('text', ''),
                language=response_data.get('language'),
                segments=response_data.get('segments'),
                processing_time=processing_time,
                timestamp=start_time.isoformat(),
                audio_duration=audio_duration
            )
        else:
            # Simple text response
            text = response_data if isinstance(response_data, str) else response_data.get('text', '')
            return TranscriptionResult(
                text=text,
                processing_time=processing_time,
                timestamp=start_time.isoformat(),
                audio_duration=audio_duration
            )
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get client statistics."""
        success_rate = (self.successful_requests / max(1, self.total_requests)) * 100
        
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "success_rate": success_rate,
            "total_audio_processed": self.total_audio_processed,
            "rate_limiter": self.rate_limiter.get_status()
        }


class WhisperIntegration:
    """
    High-level Whisper integration for AI Media Gateway.
    Manages multiple clients and provides easy-to-use interface.
    """
    
    def __init__(self, config: Optional[WhisperConfig] = None):
        """
        Initialize Whisper integration.
        
        Args:
            config: Whisper configuration (optional, uses Django settings if None)
        """
        self.config = config or self._load_config_from_settings()
        self.client: Optional[WhisperClient] = None
        
        # Callback for transcription results
        self.on_transcription: Optional[Callable] = None
        
        # Queue for batch processing
        self._transcription_queue = asyncio.Queue()
        self._processing_task: Optional[asyncio.Task] = None
        
        logger.info("Whisper integration initialized")
    
    def _load_config_from_settings(self) -> WhisperConfig:
        """Load Whisper configuration from Django settings."""
        whisper_settings = getattr(settings, 'WHISPER_CONFIG', {})
        
        return WhisperConfig(
            api_key=whisper_settings.get('api_key', ''),
            model=whisper_settings.get('model', 'whisper-1'),
            language=whisper_settings.get('language'),
            prompt=whisper_settings.get('prompt'),
            response_format=whisper_settings.get('response_format', 'verbose_json'),
            temperature=whisper_settings.get('temperature', 0.0),
            timeout=whisper_settings.get('timeout', 30),
            max_retries=whisper_settings.get('max_retries', 3)
        )
    
    async def start(self) -> None:
        """Start Whisper integration."""
        if not self.config.api_key:
            raise ValueError("OpenAI API key not configured")
        
        self.client = WhisperClient(self.config)
        await self.client.start()
        
        # Start background processing task
        self._processing_task = asyncio.create_task(self._process_queue())
        
        logger.info("Whisper integration started")
    
    async def stop(self) -> None:
        """Stop Whisper integration."""
        # Stop background processing
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
        
        # Stop client
        if self.client:
            await self.client.stop()
            self.client = None
        
        logger.info("Whisper integration stopped")
    
    async def transcribe_sync(
        self,
        audio_data: np.ndarray,
        sample_rate: int = 16000,
        language: Optional[str] = None,
        prompt: Optional[str] = None
    ) -> TranscriptionResult:
        """
        Synchronous transcription (blocks until complete).
        
        Args:
            audio_data: Audio data as numpy array
            sample_rate: Audio sample rate
            language: Language code (optional)
            prompt: Context prompt (optional)
            
        Returns:
            TranscriptionResult
        """
        if not self.client:
            raise RuntimeError("Whisper integration not started")
        
        return await self.client.transcribe_audio(audio_data, sample_rate, language, prompt)
    
    async def transcribe_async(
        self,
        audio_data: np.ndarray,
        sample_rate: int = 16000,
        language: Optional[str] = None,
        prompt: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Asynchronous transcription (queued for background processing).
        
        Args:
            audio_data: Audio data as numpy array
            sample_rate: Audio sample rate
            language: Language code (optional)
            prompt: Context prompt (optional)
            metadata: Additional metadata to pass through
        """
        await self._transcription_queue.put({
            "audio_data": audio_data,
            "sample_rate": sample_rate,
            "language": language,
            "prompt": prompt,
            "metadata": metadata or {}
        })
    
    async def _process_queue(self) -> None:
        """Background queue processing task."""
        while True:
            try:
                # Get item from queue
                item = await self._transcription_queue.get()
                
                # Process transcription
                result = await self.client.transcribe_audio(
                    item["audio_data"],
                    item["sample_rate"],
                    item["language"],
                    item["prompt"]
                )
                
                # Call callback if set
                if self.on_transcription:
                    try:
                        await self.on_transcription(result, item["metadata"])
                    except Exception as e:
                        logger.error(f"Error in transcription callback: {e}")
                
                # Mark task as done
                self._transcription_queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing transcription queue: {e}")
                # Mark task as done even on error
                if not self._transcription_queue.empty():
                    self._transcription_queue.task_done()
    
    def set_transcription_callback(
        self,
        callback: Callable[[TranscriptionResult, Dict[str, Any]], None]
    ) -> None:
        """
        Set callback for transcription results.
        
        Args:
            callback: Async callback function
                     Signature: async def callback(result: TranscriptionResult, metadata: dict)
        """
        self.on_transcription = callback
        logger.info("Transcription callback configured")
    
    def get_queue_size(self) -> int:
        """Get current queue size."""
        return self._transcription_queue.qsize()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get integration statistics."""
        stats = {
            "queue_size": self.get_queue_size(),
            "config": {
                "model": self.config.model,
                "language": self.config.language,
                "response_format": self.config.response_format
            }
        }
        
        if self.client:
            stats.update(self.client.get_statistics())
        
        return stats


# Global Whisper integration instance
_whisper_integration: Optional[WhisperIntegration] = None


async def get_whisper_integration() -> WhisperIntegration:
    """Get or create the global Whisper integration instance."""
    global _whisper_integration
    
    if _whisper_integration is None:
        _whisper_integration = WhisperIntegration()
    
    return _whisper_integration


async def start_whisper_integration() -> None:
    """Start the global Whisper integration."""
    integration = await get_whisper_integration()
    if not integration.client:
        await integration.start()


async def stop_whisper_integration() -> None:
    """Stop the global Whisper integration."""
    global _whisper_integration
    
    if _whisper_integration and _whisper_integration.client:
        await _whisper_integration.stop()
        _whisper_integration = None


async def transcribe_audio_chunk(
    audio_data: np.ndarray,
    sample_rate: int = 16000,
    language: Optional[str] = None,
    prompt: Optional[str] = None
) -> TranscriptionResult:
    """
    Convenience function to transcribe audio chunk.
    
    Args:
        audio_data: Audio data as numpy array
        sample_rate: Audio sample rate
        language: Language code (optional)
        prompt: Context prompt (optional)
        
    Returns:
        TranscriptionResult
    """
    integration = await get_whisper_integration()
    return await integration.transcribe_sync(audio_data, sample_rate, language, prompt)


async def queue_transcription(
    audio_data: np.ndarray,
    sample_rate: int = 16000,
    language: Optional[str] = None,
    prompt: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """
    Queue audio for background transcription.
    
    Args:
        audio_data: Audio data as numpy array
        sample_rate: Audio sample rate
        language: Language code (optional)
        prompt: Context prompt (optional)
        metadata: Additional metadata
    """
    integration = await get_whisper_integration()
    await integration.transcribe_async(audio_data, sample_rate, language, prompt, metadata)
