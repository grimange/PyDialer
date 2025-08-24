"""
Audio resampling module for Whisper compatibility.
Handles high-quality resampling from various sample rates to 16kHz for OpenAI Whisper.
"""

import logging
import numpy as np
from typing import Optional, Union, Tuple
import struct
from scipy import signal
from django.conf import settings

logger = logging.getLogger(__name__)

# Try to import soxr for high-quality resampling (production)
try:
    import soxr
    HAS_SOXR = True
    logger.info("Using soxr for high-quality audio resampling")
except ImportError:
    HAS_SOXR = False
    logger.warning("soxr not available, using scipy for audio resampling")


class AudioResampler:
    """
    High-quality audio resampler optimized for speech recognition.
    Supports conversion to 16kHz for OpenAI Whisper compatibility.
    """
    
    TARGET_SAMPLE_RATE = 16000  # Whisper optimal sample rate
    
    def __init__(self, quality: str = "high"):
        """
        Initialize audio resampler.
        
        Args:
            quality: Resampling quality ("low", "medium", "high", "very_high")
        """
        self.quality = quality
        
        # Quality settings for different backends
        self.soxr_quality_map = {
            "low": soxr.HQ if HAS_SOXR else None,
            "medium": soxr.VHQ if HAS_SOXR else None,
            "high": soxr.VHQ if HAS_SOXR else None,
            "very_high": soxr.VHQ if HAS_SOXR else None
        }
        
        # Cache for resampling configurations
        self._resample_cache = {}
        
        logger.info(f"Audio resampler initialized with {quality} quality")
    
    def resample_to_16khz(
        self,
        audio_data: Union[bytes, np.ndarray],
        input_sample_rate: int,
        input_format: str = "int16"
    ) -> np.ndarray:
        """
        Resample audio data to 16kHz for Whisper compatibility.
        
        Args:
            audio_data: Input audio data (bytes or numpy array)
            input_sample_rate: Input sample rate in Hz
            input_format: Input format ("int16", "float32", "int32")
            
        Returns:
            Resampled audio as float32 numpy array
        """
        try:
            # Convert input to numpy array if needed
            if isinstance(audio_data, bytes):
                audio_array = self._bytes_to_numpy(audio_data, input_format)
            else:
                audio_array = np.asarray(audio_data, dtype=np.float32)
            
            # Normalize to float32 if needed
            if audio_array.dtype != np.float32:
                audio_array = self._normalize_to_float32(audio_array)
            
            # Skip resampling if already at target rate
            if input_sample_rate == self.TARGET_SAMPLE_RATE:
                return audio_array
            
            # Perform resampling
            if HAS_SOXR and self.quality in ["high", "very_high"]:
                resampled = self._resample_with_soxr(
                    audio_array, input_sample_rate, self.TARGET_SAMPLE_RATE
                )
            else:
                resampled = self._resample_with_scipy(
                    audio_array, input_sample_rate, self.TARGET_SAMPLE_RATE
                )
            
            # Ensure output is float32 and properly scaled for Whisper
            resampled = np.asarray(resampled, dtype=np.float32)
            
            # Clamp values to [-1.0, 1.0]
            resampled = np.clip(resampled, -1.0, 1.0)
            
            logger.debug(f"Resampled audio from {input_sample_rate}Hz to {self.TARGET_SAMPLE_RATE}Hz: "
                        f"{len(audio_array)} -> {len(resampled)} samples")
            
            return resampled
            
        except Exception as e:
            logger.error(f"Error resampling audio: {e}")
            raise
    
    def _bytes_to_numpy(self, audio_data: bytes, format_type: str) -> np.ndarray:
        """
        Convert bytes to numpy array based on format.
        
        Args:
            audio_data: Raw audio bytes
            format_type: Format type ("int16", "float32", "int32")
            
        Returns:
            Numpy array with audio data
        """
        if format_type == "int16":
            # Unpack as 16-bit signed integers, little-endian
            sample_count = len(audio_data) // 2
            samples = struct.unpack('<' + 'h' * sample_count, audio_data)
            return np.array(samples, dtype=np.float32) / 32768.0  # Normalize to [-1, 1]
        
        elif format_type == "int32":
            # Unpack as 32-bit signed integers, little-endian
            sample_count = len(audio_data) // 4
            samples = struct.unpack('<' + 'i' * sample_count, audio_data)
            return np.array(samples, dtype=np.float32) / 2147483648.0  # Normalize to [-1, 1]
        
        elif format_type == "float32":
            # Unpack as 32-bit floats, little-endian
            sample_count = len(audio_data) // 4
            samples = struct.unpack('<' + 'f' * sample_count, audio_data)
            return np.array(samples, dtype=np.float32)
        
        else:
            raise ValueError(f"Unsupported audio format: {format_type}")
    
    def _normalize_to_float32(self, audio_array: np.ndarray) -> np.ndarray:
        """
        Normalize audio array to float32 format.
        
        Args:
            audio_array: Input audio array
            
        Returns:
            Normalized float32 array
        """
        if audio_array.dtype == np.int16:
            return audio_array.astype(np.float32) / 32768.0
        elif audio_array.dtype == np.int32:
            return audio_array.astype(np.float32) / 2147483648.0
        elif audio_array.dtype == np.uint8:
            return (audio_array.astype(np.float32) - 128.0) / 128.0
        else:
            return audio_array.astype(np.float32)
    
    def _resample_with_soxr(
        self,
        audio_data: np.ndarray,
        input_rate: int,
        output_rate: int
    ) -> np.ndarray:
        """
        High-quality resampling using soxr library.
        
        Args:
            audio_data: Input audio data
            input_rate: Input sample rate
            output_rate: Output sample rate
            
        Returns:
            Resampled audio data
        """
        try:
            quality = self.soxr_quality_map.get(self.quality, soxr.VHQ)
            
            # Use soxr for high-quality resampling
            resampled = soxr.resample(
                audio_data,
                input_rate,
                output_rate,
                quality=quality
            )
            
            return resampled
            
        except Exception as e:
            logger.error(f"Error with soxr resampling: {e}")
            # Fallback to scipy
            return self._resample_with_scipy(audio_data, input_rate, output_rate)
    
    def _resample_with_scipy(
        self,
        audio_data: np.ndarray,
        input_rate: int,
        output_rate: int
    ) -> np.ndarray:
        """
        Resampling using scipy.signal.
        
        Args:
            audio_data: Input audio data
            input_rate: Input sample rate
            output_rate: Output sample rate
            
        Returns:
            Resampled audio data
        """
        try:
            # Calculate resampling ratio
            ratio = output_rate / input_rate
            
            # Use cached configuration if available
            cache_key = (input_rate, output_rate, self.quality)
            if cache_key in self._resample_cache:
                filter_params = self._resample_cache[cache_key]
            else:
                # Design anti-aliasing filter parameters based on quality
                if self.quality == "low":
                    # Fast but lower quality
                    num_zeros = 5
                    beta = 5.0
                elif self.quality == "medium":
                    num_zeros = 7
                    beta = 7.0
                elif self.quality == "high":
                    num_zeros = 9
                    beta = 8.6
                else:  # very_high
                    num_zeros = 13
                    beta = 10.0
                
                filter_params = {"num_zeros": num_zeros, "beta": beta}
                self._resample_cache[cache_key] = filter_params
            
            # Perform resampling using polyphase filtering
            if ratio > 1:
                # Upsampling
                output_length = int(len(audio_data) * ratio)
                resampled = signal.resample_poly(
                    audio_data,
                    up=output_rate,
                    down=input_rate,
                    window=('kaiser', filter_params["beta"])
                )
            else:
                # Downsampling - apply anti-aliasing filter
                resampled = signal.resample_poly(
                    audio_data,
                    up=output_rate,
                    down=input_rate,
                    window=('kaiser', filter_params["beta"])
                )
            
            return resampled
            
        except Exception as e:
            logger.error(f"Error with scipy resampling: {e}")
            # Fallback to simple linear interpolation
            return self._linear_interpolation_resample(audio_data, input_rate, output_rate)
    
    def _linear_interpolation_resample(
        self,
        audio_data: np.ndarray,
        input_rate: int,
        output_rate: int
    ) -> np.ndarray:
        """
        Simple linear interpolation resampling (fallback method).
        
        Args:
            audio_data: Input audio data
            input_rate: Input sample rate
            output_rate: Output sample rate
            
        Returns:
            Resampled audio data
        """
        try:
            ratio = output_rate / input_rate
            output_length = int(len(audio_data) * ratio)
            
            # Create input and output time indices
            input_indices = np.arange(len(audio_data))
            output_indices = np.arange(output_length) / ratio
            
            # Perform linear interpolation
            resampled = np.interp(output_indices, input_indices, audio_data)
            
            return resampled
            
        except Exception as e:
            logger.error(f"Error with linear interpolation resampling: {e}")
            raise
    
    def preprocess_for_whisper(
        self,
        audio_data: Union[bytes, np.ndarray],
        input_sample_rate: int,
        input_format: str = "int16",
        apply_preemphasis: bool = True,
        normalize_volume: bool = True
    ) -> np.ndarray:
        """
        Complete preprocessing pipeline for Whisper compatibility.
        
        Args:
            audio_data: Input audio data
            input_sample_rate: Input sample rate
            input_format: Input format
            apply_preemphasis: Apply preemphasis filter for speech enhancement
            normalize_volume: Normalize audio volume
            
        Returns:
            Processed audio ready for Whisper
        """
        try:
            # Step 1: Resample to 16kHz
            resampled = self.resample_to_16khz(audio_data, input_sample_rate, input_format)
            
            # Step 2: Apply preemphasis filter (enhances high frequencies for speech)
            if apply_preemphasis:
                resampled = self._apply_preemphasis(resampled)
            
            # Step 3: Normalize volume
            if normalize_volume:
                resampled = self._normalize_volume(resampled)
            
            # Step 4: Remove DC offset
            resampled = resampled - np.mean(resampled)
            
            # Step 5: Final clipping to ensure valid range
            resampled = np.clip(resampled, -1.0, 1.0)
            
            logger.debug(f"Audio preprocessing completed: {len(resampled)} samples at 16kHz")
            
            return resampled
            
        except Exception as e:
            logger.error(f"Error in Whisper preprocessing: {e}")
            raise
    
    def _apply_preemphasis(self, audio_data: np.ndarray, alpha: float = 0.97) -> np.ndarray:
        """
        Apply preemphasis filter to enhance high frequencies.
        
        Args:
            audio_data: Input audio data
            alpha: Preemphasis coefficient (typically 0.95-0.97)
            
        Returns:
            Preemphasized audio data
        """
        try:
            # Apply preemphasis: y[n] = x[n] - α * x[n-1]
            preemphasized = np.zeros_like(audio_data)
            preemphasized[0] = audio_data[0]
            preemphasized[1:] = audio_data[1:] - alpha * audio_data[:-1]
            
            return preemphasized
            
        except Exception as e:
            logger.error(f"Error applying preemphasis: {e}")
            return audio_data  # Return original if failed
    
    def _normalize_volume(
        self,
        audio_data: np.ndarray,
        target_peak: float = 0.95,
        min_rms: float = 0.01
    ) -> np.ndarray:
        """
        Normalize audio volume for consistent levels.
        
        Args:
            audio_data: Input audio data
            target_peak: Target peak level (0.0-1.0)
            min_rms: Minimum RMS level to avoid over-amplification
            
        Returns:
            Volume-normalized audio data
        """
        try:
            # Calculate RMS level
            rms = np.sqrt(np.mean(audio_data ** 2))
            
            if rms < min_rms:
                # Very quiet audio - use peak normalization instead
                peak = np.max(np.abs(audio_data))
                if peak > 0:
                    gain = target_peak / peak
                    normalized = audio_data * gain
                else:
                    normalized = audio_data
            else:
                # Normal audio - use RMS normalization
                target_rms = target_peak * 0.3  # Conservative target RMS
                gain = min(target_rms / rms, target_peak / np.max(np.abs(audio_data)))
                normalized = audio_data * gain
            
            return normalized
            
        except Exception as e:
            logger.error(f"Error normalizing volume: {e}")
            return audio_data  # Return original if failed
    
    def batch_resample(
        self,
        audio_chunks: list,
        input_sample_rate: int,
        input_format: str = "int16"
    ) -> list:
        """
        Batch process multiple audio chunks for efficiency.
        
        Args:
            audio_chunks: List of audio data chunks
            input_sample_rate: Input sample rate
            input_format: Input format
            
        Returns:
            List of resampled audio chunks
        """
        try:
            resampled_chunks = []
            
            for i, chunk in enumerate(audio_chunks):
                try:
                    resampled = self.preprocess_for_whisper(
                        chunk, input_sample_rate, input_format
                    )
                    resampled_chunks.append(resampled)
                except Exception as e:
                    logger.error(f"Error processing chunk {i}: {e}")
                    continue
            
            logger.debug(f"Batch resampled {len(resampled_chunks)} chunks")
            return resampled_chunks
            
        except Exception as e:
            logger.error(f"Error in batch resampling: {e}")
            raise
    
    def get_optimal_chunk_size(self, sample_rate: int, duration_ms: int = 500) -> int:
        """
        Get optimal chunk size for processing.
        
        Args:
            sample_rate: Audio sample rate
            duration_ms: Desired chunk duration in milliseconds
            
        Returns:
            Optimal chunk size in samples
        """
        # Calculate samples for desired duration
        chunk_size = int(sample_rate * duration_ms / 1000)
        
        # Round to nearest power of 2 for efficiency
        power_of_2 = 2 ** int(np.log2(chunk_size))
        if chunk_size - power_of_2 > power_of_2 // 2:
            power_of_2 *= 2
        
        return power_of_2
    
    def validate_audio_format(
        self,
        audio_data: Union[bytes, np.ndarray],
        expected_format: str
    ) -> bool:
        """
        Validate audio format and data integrity.
        
        Args:
            audio_data: Audio data to validate
            expected_format: Expected format
            
        Returns:
            True if valid, False otherwise
        """
        try:
            if isinstance(audio_data, bytes):
                if expected_format == "int16" and len(audio_data) % 2 != 0:
                    return False
                elif expected_format == "int32" and len(audio_data) % 4 != 0:
                    return False
                elif expected_format == "float32" and len(audio_data) % 4 != 0:
                    return False
            
            elif isinstance(audio_data, np.ndarray):
                if audio_data.ndim != 1:  # Only mono audio supported
                    return False
                if len(audio_data) == 0:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating audio format: {e}")
            return False


class WhisperAudioProcessor:
    """
    Specialized audio processor for OpenAI Whisper integration.
    Handles optimal preprocessing and chunking for speech recognition.
    """
    
    def __init__(self, quality: str = "high"):
        """
        Initialize Whisper audio processor.
        
        Args:
            quality: Resampling quality
        """
        self.resampler = AudioResampler(quality=quality)
        self.chunk_duration_ms = 500  # 500ms chunks for processing
        self.overlap_ms = 50  # 50ms overlap between chunks
        
        logger.info("Whisper audio processor initialized")
    
    def process_for_transcription(
        self,
        audio_data: Union[bytes, np.ndarray],
        input_sample_rate: int,
        input_format: str = "int16"
    ) -> Tuple[np.ndarray, dict]:
        """
        Process audio for optimal Whisper transcription.
        
        Args:
            audio_data: Input audio data
            input_sample_rate: Input sample rate
            input_format: Input format
            
        Returns:
            Tuple of (processed_audio, metadata)
        """
        try:
            # Validate input
            if not self.resampler.validate_audio_format(audio_data, input_format):
                raise ValueError("Invalid audio format")
            
            # Process audio
            processed = self.resampler.preprocess_for_whisper(
                audio_data, input_sample_rate, input_format
            )
            
            # Generate metadata
            metadata = {
                "sample_rate": 16000,
                "duration_seconds": len(processed) / 16000,
                "format": "float32",
                "channels": 1,
                "preprocessing_applied": {
                    "resampled": input_sample_rate != 16000,
                    "preemphasized": True,
                    "volume_normalized": True,
                    "dc_removed": True
                },
                "original_sample_rate": input_sample_rate,
                "original_format": input_format
            }
            
            logger.debug(f"Audio processed for transcription: {metadata['duration_seconds']:.3f}s")
            
            return processed, metadata
            
        except Exception as e:
            logger.error(f"Error processing audio for transcription: {e}")
            raise
    
    def create_overlapping_chunks(
        self,
        audio_data: np.ndarray,
        chunk_duration_ms: Optional[int] = None,
        overlap_ms: Optional[int] = None
    ) -> list:
        """
        Create overlapping audio chunks for continuous processing.
        
        Args:
            audio_data: Input audio data (16kHz float32)
            chunk_duration_ms: Chunk duration in milliseconds
            overlap_ms: Overlap duration in milliseconds
            
        Returns:
            List of overlapping audio chunks
        """
        try:
            chunk_duration_ms = chunk_duration_ms or self.chunk_duration_ms
            overlap_ms = overlap_ms or self.overlap_ms
            
            sample_rate = 16000
            chunk_samples = int(sample_rate * chunk_duration_ms / 1000)
            overlap_samples = int(sample_rate * overlap_ms / 1000)
            step_samples = chunk_samples - overlap_samples
            
            chunks = []
            start = 0
            
            while start < len(audio_data):
                end = min(start + chunk_samples, len(audio_data))
                chunk = audio_data[start:end]
                
                # Pad last chunk if necessary
                if len(chunk) < chunk_samples:
                    padded = np.zeros(chunk_samples, dtype=np.float32)
                    padded[:len(chunk)] = chunk
                    chunk = padded
                
                chunks.append({
                    "audio": chunk,
                    "start_time": start / sample_rate,
                    "end_time": end / sample_rate,
                    "start_sample": start,
                    "end_sample": end
                })
                
                start += step_samples
            
            logger.debug(f"Created {len(chunks)} overlapping chunks")
            return chunks
            
        except Exception as e:
            logger.error(f"Error creating overlapping chunks: {e}")
            raise


# Global resampler instances
_default_resampler: Optional[AudioResampler] = None
_whisper_processor: Optional[WhisperAudioProcessor] = None


def get_default_resampler() -> AudioResampler:
    """Get or create the default audio resampler."""
    global _default_resampler
    
    if _default_resampler is None:
        # Get quality setting from Django settings
        quality = getattr(settings, 'AUDIO_RESAMPLER_QUALITY', 'high')
        _default_resampler = AudioResampler(quality=quality)
    
    return _default_resampler


def get_whisper_processor() -> WhisperAudioProcessor:
    """Get or create the Whisper audio processor."""
    global _whisper_processor
    
    if _whisper_processor is None:
        quality = getattr(settings, 'AUDIO_RESAMPLER_QUALITY', 'high')
        _whisper_processor = WhisperAudioProcessor(quality=quality)
    
    return _whisper_processor


def resample_for_whisper(
    audio_data: Union[bytes, np.ndarray],
    input_sample_rate: int,
    input_format: str = "int16"
) -> np.ndarray:
    """
    Convenience function to resample audio for Whisper.
    
    Args:
        audio_data: Input audio data
        input_sample_rate: Input sample rate
        input_format: Input format
        
    Returns:
        Resampled audio ready for Whisper
    """
    resampler = get_default_resampler()
    return resampler.preprocess_for_whisper(audio_data, input_sample_rate, input_format)


def process_audio_chunk_for_ai(
    audio_data: Union[bytes, np.ndarray],
    input_sample_rate: int,
    input_format: str = "int16"
) -> Tuple[np.ndarray, dict]:
    """
    Process audio chunk for AI transcription.
    
    Args:
        audio_data: Input audio data
        input_sample_rate: Input sample rate
        input_format: Input format
        
    Returns:
        Tuple of (processed_audio, metadata)
    """
    processor = get_whisper_processor()
    return processor.process_for_transcription(audio_data, input_sample_rate, input_format)
