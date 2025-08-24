"""
Audio format conversion utilities for PyDialer AI Media Gateway.

This module provides comprehensive audio format conversion capabilities
including PCM format conversions, G.711 μ-law/A-law codecs, bit depth
conversions, and endianness handling for telephony and AI processing.
"""

import logging
import numpy as np
import struct
from typing import Union, Optional, Tuple, List
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class AudioFormat(Enum):
    """Supported audio formats."""
    PCM_S16LE = "pcm_s16le"  # 16-bit signed little-endian PCM
    PCM_S16BE = "pcm_s16be"  # 16-bit signed big-endian PCM
    PCM_S8 = "pcm_s8"        # 8-bit signed PCM
    PCM_U8 = "pcm_u8"        # 8-bit unsigned PCM
    PCM_S24LE = "pcm_s24le"  # 24-bit signed little-endian PCM
    PCM_S24BE = "pcm_s24be"  # 24-bit signed big-endian PCM
    PCM_S32LE = "pcm_s32le"  # 32-bit signed little-endian PCM
    PCM_S32BE = "pcm_s32be"  # 32-bit signed big-endian PCM
    PCM_F32LE = "pcm_f32le"  # 32-bit float little-endian PCM
    PCM_F32BE = "pcm_f32be"  # 32-bit float big-endian PCM
    G711_ULAW = "g711_ulaw"  # G.711 μ-law
    G711_ALAW = "g711_alaw"  # G.711 A-law


class AudioSampleRate(Enum):
    """Common audio sample rates."""
    RATE_8KHZ = 8000
    RATE_16KHZ = 16000
    RATE_22KHZ = 22050
    RATE_32KHZ = 32000
    RATE_44KHZ = 44100
    RATE_48KHZ = 48000
    RATE_96KHZ = 96000


class AudioFormatConverter:
    """
    Comprehensive audio format conversion utility.
    
    Handles conversion between various audio formats commonly used
    in telephony systems and AI processing pipelines.
    """
    
    def __init__(self):
        """Initialize audio format converter."""
        self.stats = {
            'conversions_performed': 0,
            'total_samples_processed': 0,
            'errors_encountered': 0,
            'formats_converted': {}
        }
        logger.info("Audio format converter initialized")
    
    def convert(
        self,
        audio_data: Union[bytes, np.ndarray],
        source_format: AudioFormat,
        target_format: AudioFormat,
        sample_rate: Optional[int] = None,
        channels: int = 1
    ) -> Union[bytes, np.ndarray]:
        """
        Convert audio data between different formats.
        
        Args:
            audio_data: Input audio data
            source_format: Source audio format
            target_format: Target audio format
            sample_rate: Sample rate in Hz (for metadata)
            channels: Number of audio channels
            
        Returns:
            Converted audio data
        """
        try:
            # Update statistics
            self._update_conversion_stats(source_format, target_format)
            
            # Convert to intermediate format (numpy float32)
            intermediate = self._to_float32_array(audio_data, source_format)
            
            # Convert from intermediate to target format
            result = self._from_float32_array(intermediate, target_format)
            
            # Update sample count
            self.stats['total_samples_processed'] += len(intermediate)
            
            logger.debug(f"Converted audio: {source_format.value} -> {target_format.value}, "
                        f"samples: {len(intermediate)}")
            
            return result
            
        except Exception as e:
            self.stats['errors_encountered'] += 1
            logger.error(f"Audio conversion error: {e}")
            raise
    
    def convert_pcm_to_g711(
        self,
        pcm_data: Union[bytes, np.ndarray],
        codec: str = "ulaw",
        source_format: AudioFormat = AudioFormat.PCM_S16LE
    ) -> bytes:
        """
        Convert PCM audio to G.711 format.
        
        Args:
            pcm_data: PCM audio data
            codec: G.711 codec ("ulaw" or "alaw")
            source_format: Source PCM format
            
        Returns:
            G.711 encoded audio data
        """
        if codec.lower() == "ulaw":
            target_format = AudioFormat.G711_ULAW
        elif codec.lower() == "alaw":
            target_format = AudioFormat.G711_ALAW
        else:
            raise ValueError(f"Unsupported G.711 codec: {codec}")
        
        return self.convert(pcm_data, source_format, target_format)
    
    def convert_g711_to_pcm(
        self,
        g711_data: bytes,
        codec: str = "ulaw",
        target_format: AudioFormat = AudioFormat.PCM_S16LE
    ) -> Union[bytes, np.ndarray]:
        """
        Convert G.711 audio to PCM format.
        
        Args:
            g711_data: G.711 encoded audio data
            codec: G.711 codec ("ulaw" or "alaw")
            target_format: Target PCM format
            
        Returns:
            PCM audio data
        """
        if codec.lower() == "ulaw":
            source_format = AudioFormat.G711_ULAW
        elif codec.lower() == "alaw":
            source_format = AudioFormat.G711_ALAW
        else:
            raise ValueError(f"Unsupported G.711 codec: {codec}")
        
        return self.convert(g711_data, source_format, target_format)
    
    def convert_bit_depth(
        self,
        audio_data: Union[bytes, np.ndarray],
        source_bits: int,
        target_bits: int,
        is_signed: bool = True,
        endian: str = "little"
    ) -> Union[bytes, np.ndarray]:
        """
        Convert audio between different bit depths.
        
        Args:
            audio_data: Input audio data
            source_bits: Source bit depth (8, 16, 24, 32)
            target_bits: Target bit depth (8, 16, 24, 32)
            is_signed: Whether samples are signed
            endian: Byte order ("little" or "big")
            
        Returns:
            Converted audio data
        """
        try:
            # Determine source and target formats
            source_format = self._get_pcm_format(source_bits, is_signed, endian)
            target_format = self._get_pcm_format(target_bits, is_signed, endian)
            
            return self.convert(audio_data, source_format, target_format)
            
        except Exception as e:
            logger.error(f"Bit depth conversion error: {e}")
            raise
    
    def normalize_audio(
        self,
        audio_data: Union[bytes, np.ndarray],
        source_format: AudioFormat,
        target_peak: float = 0.95
    ) -> Union[bytes, np.ndarray]:
        """
        Normalize audio to target peak level.
        
        Args:
            audio_data: Input audio data
            source_format: Source audio format
            target_peak: Target peak level (0.0 to 1.0)
            
        Returns:
            Normalized audio data in same format
        """
        try:
            # Convert to float32 for processing
            float_data = self._to_float32_array(audio_data, source_format)
            
            # Find current peak
            current_peak = np.max(np.abs(float_data))
            
            if current_peak > 0:
                # Calculate scaling factor
                scale_factor = target_peak / current_peak
                
                # Apply normalization
                normalized = float_data * scale_factor
                
                # Convert back to original format
                result = self._from_float32_array(normalized, source_format)
                
                logger.debug(f"Normalized audio: peak {current_peak:.3f} -> {target_peak:.3f}")
                return result
            else:
                logger.warning("Audio contains only silence, no normalization applied")
                return audio_data
                
        except Exception as e:
            logger.error(f"Audio normalization error: {e}")
            raise
    
    def batch_convert(
        self,
        audio_chunks: List[Union[bytes, np.ndarray]],
        source_format: AudioFormat,
        target_format: AudioFormat
    ) -> List[Union[bytes, np.ndarray]]:
        """
        Convert multiple audio chunks in batch.
        
        Args:
            audio_chunks: List of audio chunks to convert
            source_format: Source audio format
            target_format: Target audio format
            
        Returns:
            List of converted audio chunks
        """
        converted_chunks = []
        
        for i, chunk in enumerate(audio_chunks):
            try:
                converted = self.convert(chunk, source_format, target_format)
                converted_chunks.append(converted)
            except Exception as e:
                logger.error(f"Error converting chunk {i}: {e}")
                # Optionally, you might want to skip failed chunks or raise
                raise
        
        logger.info(f"Batch converted {len(converted_chunks)} audio chunks")
        return converted_chunks
    
    def _to_float32_array(
        self,
        audio_data: Union[bytes, np.ndarray],
        format_type: AudioFormat
    ) -> np.ndarray:
        """Convert audio data to float32 numpy array."""
        if isinstance(audio_data, np.ndarray) and audio_data.dtype == np.float32:
            return audio_data
        
        if format_type == AudioFormat.PCM_S16LE:
            if isinstance(audio_data, bytes):
                samples = np.frombuffer(audio_data, dtype='<i2')
            else:
                samples = audio_data.astype(np.int16)
            return samples.astype(np.float32) / 32768.0
        
        elif format_type == AudioFormat.PCM_S16BE:
            if isinstance(audio_data, bytes):
                samples = np.frombuffer(audio_data, dtype='>i2')
            else:
                samples = audio_data.astype(np.int16)
            return samples.astype(np.float32) / 32768.0
        
        elif format_type == AudioFormat.PCM_S8:
            if isinstance(audio_data, bytes):
                samples = np.frombuffer(audio_data, dtype=np.int8)
            else:
                samples = audio_data.astype(np.int8)
            return samples.astype(np.float32) / 128.0
        
        elif format_type == AudioFormat.PCM_U8:
            if isinstance(audio_data, bytes):
                samples = np.frombuffer(audio_data, dtype=np.uint8)
            else:
                samples = audio_data.astype(np.uint8)
            return (samples.astype(np.float32) - 128.0) / 128.0
        
        elif format_type == AudioFormat.PCM_S24LE:
            return self._convert_24bit_to_float32(audio_data, 'little')
        
        elif format_type == AudioFormat.PCM_S24BE:
            return self._convert_24bit_to_float32(audio_data, 'big')
        
        elif format_type == AudioFormat.PCM_S32LE:
            if isinstance(audio_data, bytes):
                samples = np.frombuffer(audio_data, dtype='<i4')
            else:
                samples = audio_data.astype(np.int32)
            return samples.astype(np.float32) / 2147483648.0
        
        elif format_type == AudioFormat.PCM_S32BE:
            if isinstance(audio_data, bytes):
                samples = np.frombuffer(audio_data, dtype='>i4')
            else:
                samples = audio_data.astype(np.int32)
            return samples.astype(np.float32) / 2147483648.0
        
        elif format_type == AudioFormat.PCM_F32LE:
            if isinstance(audio_data, bytes):
                return np.frombuffer(audio_data, dtype='<f4')
            else:
                return audio_data.astype(np.float32)
        
        elif format_type == AudioFormat.PCM_F32BE:
            if isinstance(audio_data, bytes):
                return np.frombuffer(audio_data, dtype='>f4')
            else:
                return audio_data.astype(np.float32)
        
        elif format_type == AudioFormat.G711_ULAW:
            return self._g711_to_float32(audio_data, 'ulaw')
        
        elif format_type == AudioFormat.G711_ALAW:
            return self._g711_to_float32(audio_data, 'alaw')
        
        else:
            raise ValueError(f"Unsupported source format: {format_type}")
    
    def _from_float32_array(
        self,
        float_data: np.ndarray,
        format_type: AudioFormat
    ) -> Union[bytes, np.ndarray]:
        """Convert float32 numpy array to target format."""
        # Clamp values to valid range
        clamped = np.clip(float_data, -1.0, 1.0)
        
        if format_type == AudioFormat.PCM_S16LE:
            samples = (clamped * 32767.0).astype('<i2')
            return samples.tobytes()
        
        elif format_type == AudioFormat.PCM_S16BE:
            samples = (clamped * 32767.0).astype('>i2')
            return samples.tobytes()
        
        elif format_type == AudioFormat.PCM_S8:
            samples = (clamped * 127.0).astype(np.int8)
            return samples.tobytes()
        
        elif format_type == AudioFormat.PCM_U8:
            samples = ((clamped + 1.0) * 127.5).astype(np.uint8)
            return samples.tobytes()
        
        elif format_type == AudioFormat.PCM_S24LE:
            return self._convert_float32_to_24bit(clamped, 'little')
        
        elif format_type == AudioFormat.PCM_S24BE:
            return self._convert_float32_to_24bit(clamped, 'big')
        
        elif format_type == AudioFormat.PCM_S32LE:
            samples = (clamped * 2147483647.0).astype('<i4')
            return samples.tobytes()
        
        elif format_type == AudioFormat.PCM_S32BE:
            samples = (clamped * 2147483647.0).astype('>i4')
            return samples.tobytes()
        
        elif format_type == AudioFormat.PCM_F32LE:
            return clamped.astype('<f4').tobytes()
        
        elif format_type == AudioFormat.PCM_F32BE:
            return clamped.astype('>f4').tobytes()
        
        elif format_type == AudioFormat.G711_ULAW:
            return self._float32_to_g711(clamped, 'ulaw')
        
        elif format_type == AudioFormat.G711_ALAW:
            return self._float32_to_g711(clamped, 'alaw')
        
        else:
            raise ValueError(f"Unsupported target format: {format_type}")
    
    def _convert_24bit_to_float32(self, audio_data: Union[bytes, np.ndarray], endian: str) -> np.ndarray:
        """Convert 24-bit audio to float32."""
        if isinstance(audio_data, np.ndarray):
            # Assume it's already converted somehow
            return audio_data.astype(np.float32) / (2**23)
        
        # Convert 24-bit packed bytes to int32
        samples = []
        for i in range(0, len(audio_data), 3):
            if i + 2 < len(audio_data):
                if endian == 'little':
                    sample = struct.unpack('<i', audio_data[i:i+3] + b'\x00')[0]
                else:
                    sample = struct.unpack('>i', b'\x00' + audio_data[i:i+3])[0]
                
                # Sign extend from 24-bit to 32-bit
                if sample & 0x800000:
                    sample |= 0xFF000000
                
                samples.append(sample)
        
        return np.array(samples, dtype=np.float32) / (2**23)
    
    def _convert_float32_to_24bit(self, float_data: np.ndarray, endian: str) -> bytes:
        """Convert float32 to 24-bit audio."""
        # Convert to 24-bit integers
        int24_data = (float_data * (2**23 - 1)).astype(np.int32)
        
        # Pack as 24-bit bytes
        result = bytearray()
        for sample in int24_data:
            # Clamp to 24-bit range
            sample = max(-2**23, min(2**23 - 1, sample))
            
            if endian == 'little':
                result.extend(struct.pack('<i', sample)[:3])
            else:
                result.extend(struct.pack('>i', sample)[1:])
        
        return bytes(result)
    
    def _g711_to_float32(self, g711_data: Union[bytes, np.ndarray], codec: str) -> np.ndarray:
        """Convert G.711 to float32 using enhanced codec."""
        if isinstance(g711_data, np.ndarray):
            g711_bytes = g711_data.astype(np.uint8).tobytes()
        else:
            g711_bytes = g711_data
        
        samples = []
        for byte in g711_bytes:
            if codec == 'ulaw':
                sample = self._mulaw_to_linear(byte)
            else:  # alaw
                sample = self._alaw_to_linear(byte)
            samples.append(sample)
        
        return np.array(samples, dtype=np.float32) / 32768.0
    
    def _float32_to_g711(self, float_data: np.ndarray, codec: str) -> bytes:
        """Convert float32 to G.711."""
        # Convert to 16-bit PCM first
        pcm_data = (float_data * 32767.0).astype(np.int16)
        
        g711_bytes = bytearray()
        for sample in pcm_data:
            if codec == 'ulaw':
                byte = self._linear_to_mulaw(sample)
            else:  # alaw
                byte = self._linear_to_alaw(sample)
            g711_bytes.append(byte)
        
        return bytes(g711_bytes)
    
    def _mulaw_to_linear(self, mulaw_byte: int) -> int:
        """Enhanced μ-law to linear conversion."""
        mulaw_byte = ~mulaw_byte & 0xFF
        sign = (mulaw_byte & 0x80)
        exponent = (mulaw_byte >> 4) & 0x07
        mantissa = mulaw_byte & 0x0F
        
        sample = mantissa << (exponent + 3)
        if exponent > 0:
            sample += (0x84 << exponent)
        
        if sign != 0:
            sample = -sample
            
        return max(-32768, min(32767, sample))
    
    def _linear_to_mulaw(self, linear_sample: int) -> int:
        """Enhanced linear to μ-law conversion."""
        MULAW_BIAS = 0x84
        MULAW_CLIP = 32635
        
        sample = max(-MULAW_CLIP, min(MULAW_CLIP, linear_sample))
        sign = (sample >> 8) & 0x80
        if sign != 0:
            sample = -sample
        
        sample += MULAW_BIAS
        
        exponent = 0
        temp = sample >> 7
        while temp > 0 and exponent < 7:
            temp >>= 1
            exponent += 1
        
        mantissa = (sample >> (exponent + 3)) & 0x0F
        mulaw_byte = ~(sign | (exponent << 4) | mantissa)
        return mulaw_byte & 0xFF
    
    def _alaw_to_linear(self, alaw_byte: int) -> int:
        """Enhanced A-law to linear conversion."""
        alaw_byte ^= 0x55
        
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
    
    def _linear_to_alaw(self, linear_sample: int) -> int:
        """Enhanced linear to A-law conversion."""
        ALAW_CLIP = 32635
        
        sample = max(-ALAW_CLIP, min(ALAW_CLIP, linear_sample))
        sign = (sample >> 8) & 0x80
        if sign != 0:
            sample = -sample
        
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
        
        alaw_byte = sign | (exponent << 4) | mantissa
        return alaw_byte ^ 0x55
    
    def _get_pcm_format(self, bits: int, is_signed: bool, endian: str) -> AudioFormat:
        """Get AudioFormat enum for PCM parameters."""
        if bits == 8:
            return AudioFormat.PCM_S8 if is_signed else AudioFormat.PCM_U8
        elif bits == 16:
            return AudioFormat.PCM_S16LE if endian == "little" else AudioFormat.PCM_S16BE
        elif bits == 24:
            return AudioFormat.PCM_S24LE if endian == "little" else AudioFormat.PCM_S24BE
        elif bits == 32:
            return AudioFormat.PCM_S32LE if endian == "little" else AudioFormat.PCM_S32BE
        else:
            raise ValueError(f"Unsupported bit depth: {bits}")
    
    def _update_conversion_stats(self, source_format: AudioFormat, target_format: AudioFormat):
        """Update conversion statistics."""
        self.stats['conversions_performed'] += 1
        
        conversion_key = f"{source_format.value}_to_{target_format.value}"
        if conversion_key not in self.stats['formats_converted']:
            self.stats['formats_converted'][conversion_key] = 0
        self.stats['formats_converted'][conversion_key] += 1
    
    def get_statistics(self) -> dict:
        """Get conversion statistics."""
        return self.stats.copy()
    
    def reset_statistics(self):
        """Reset conversion statistics."""
        self.stats = {
            'conversions_performed': 0,
            'total_samples_processed': 0,
            'errors_encountered': 0,
            'formats_converted': {}
        }
        logger.info("Audio converter statistics reset")


# Global converter instance
_audio_converter = None


def get_audio_converter() -> AudioFormatConverter:
    """
    Get global audio format converter instance.
    
    Returns:
        AudioFormatConverter instance
    """
    global _audio_converter
    
    if _audio_converter is None:
        _audio_converter = AudioFormatConverter()
    
    return _audio_converter


def convert_audio_format(
    audio_data: Union[bytes, np.ndarray],
    source_format: AudioFormat,
    target_format: AudioFormat,
    sample_rate: Optional[int] = None
) -> Union[bytes, np.ndarray]:
    """
    Convenience function for audio format conversion.
    
    Args:
        audio_data: Input audio data
        source_format: Source audio format
        target_format: Target audio format
        sample_rate: Sample rate in Hz (for metadata)
        
    Returns:
        Converted audio data
    """
    converter = get_audio_converter()
    return converter.convert(audio_data, source_format, target_format, sample_rate)


def normalize_audio_level(
    audio_data: Union[bytes, np.ndarray],
    source_format: AudioFormat,
    target_peak: float = 0.95
) -> Union[bytes, np.ndarray]:
    """
    Convenience function for audio normalization.
    
    Args:
        audio_data: Input audio data
        source_format: Source audio format
        target_peak: Target peak level (0.0 to 1.0)
        
    Returns:
        Normalized audio data
    """
    converter = get_audio_converter()
    return converter.normalize_audio(audio_data, source_format, target_peak)
