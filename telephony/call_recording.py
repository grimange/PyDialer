"""
Call Recording and Storage Integration for PyDialer.

This module provides comprehensive call recording functionality including
recording management, storage integration, and metadata handling.
"""

import logging
import asyncio
import os
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
from pathlib import Path
import uuid
import json
import hashlib

from django.conf import settings
from django.utils import timezone
from django.core.files.storage import default_storage
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


class RecordingStatus(Enum):
    """Recording status enumeration."""
    IDLE = "idle"
    STARTING = "starting"
    RECORDING = "recording"
    STOPPING = "stopping"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class RecordingFormat(Enum):
    """Recording format enumeration."""
    WAV = "wav"
    MP3 = "mp3"
    GSM = "gsm"
    G729 = "g729"
    OPUS = "opus"


class StorageType(Enum):
    """Storage backend type enumeration."""
    LOCAL = "local"
    S3 = "s3"
    AZURE = "azure"
    GCS = "gcs"
    FTP = "ftp"


class RecordingTrigger(Enum):
    """Recording trigger type enumeration."""
    MANUAL = "manual"
    AUTOMATIC = "automatic"
    COMPLIANCE = "compliance"
    QUALITY = "quality"


@dataclass
class RecordingMetadata:
    """Recording metadata information."""
    recording_id: str
    call_id: str
    agent_id: Optional[str] = None
    customer_id: Optional[str] = None
    campaign_id: Optional[str] = None
    
    # Call information
    caller_id: str = ""
    called_number: str = ""
    direction: str = "inbound"  # inbound/outbound
    
    # Recording details
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration: Optional[float] = None  # seconds
    file_size: Optional[int] = None  # bytes
    format: RecordingFormat = RecordingFormat.WAV
    sample_rate: int = 8000
    channels: int = 1
    
    # Storage information
    storage_type: StorageType = StorageType.LOCAL
    file_path: str = ""
    url: Optional[str] = None
    checksum: Optional[str] = None
    
    # Metadata
    trigger: RecordingTrigger = RecordingTrigger.MANUAL
    status: RecordingStatus = RecordingStatus.IDLE
    tags: List[str] = field(default_factory=list)
    notes: str = ""
    retention_date: Optional[datetime] = None
    
    # Compliance
    consent_obtained: bool = False
    privacy_level: str = "standard"  # standard/sensitive/restricted
    
    def __post_init__(self):
        if isinstance(self.start_time, str):
            self.start_time = datetime.fromisoformat(self.start_time)
        if isinstance(self.end_time, str):
            self.end_time = datetime.fromisoformat(self.end_time)
        if isinstance(self.retention_date, str):
            self.retention_date = datetime.fromisoformat(self.retention_date)
    
    @property
    def is_active(self) -> bool:
        """Check if recording is currently active."""
        return self.status in [RecordingStatus.STARTING, RecordingStatus.RECORDING, RecordingStatus.PAUSED]
    
    @property
    def calculated_duration(self) -> Optional[float]:
        """Calculate duration from start/end times."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return self.duration


@dataclass 
class RecordingConfig:
    """Recording configuration settings."""
    enabled: bool = True
    auto_record: bool = False
    format: RecordingFormat = RecordingFormat.WAV
    sample_rate: int = 8000
    channels: int = 1
    max_duration: int = 7200  # 2 hours in seconds
    storage_type: StorageType = StorageType.LOCAL
    storage_path: str = "recordings"
    retention_days: int = 365
    consent_required: bool = True
    privacy_mode: bool = False
    compression: bool = False
    encryption: bool = False


class RecordingStorage:
    """
    Recording storage abstraction layer.
    Handles different storage backends for call recordings.
    """
    
    def __init__(self, storage_type: StorageType, config: Dict[str, Any] = None):
        self.storage_type = storage_type
        self.config = config or {}
        self._initialize_storage()
    
    def _initialize_storage(self) -> None:
        """Initialize storage backend based on type."""
        if self.storage_type == StorageType.LOCAL:
            self.base_path = Path(self.config.get('base_path', 'media/recordings'))
            self.base_path.mkdir(parents=True, exist_ok=True)
        
        elif self.storage_type == StorageType.S3:
            # S3 configuration would go here
            self.bucket_name = self.config.get('bucket_name', 'call-recordings')
            self.aws_region = self.config.get('aws_region', 'us-east-1')
        
        # Add other storage types as needed
        logger.info(f"Initialized {self.storage_type.value} storage")
    
    async def store_recording(
        self,
        recording_id: str,
        file_data: bytes,
        metadata: RecordingMetadata
    ) -> str:
        """Store recording file and return storage path/URL."""
        try:
            if self.storage_type == StorageType.LOCAL:
                return await self._store_local(recording_id, file_data, metadata)
            elif self.storage_type == StorageType.S3:
                return await self._store_s3(recording_id, file_data, metadata)
            else:
                raise NotImplementedError(f"Storage type {self.storage_type.value} not implemented")
        
        except Exception as e:
            logger.error(f"Error storing recording {recording_id}: {e}")
            raise
    
    async def _store_local(
        self,
        recording_id: str,
        file_data: bytes,
        metadata: RecordingMetadata
    ) -> str:
        """Store recording in local filesystem."""
        # Create directory structure: YYYY/MM/DD/
        date_path = metadata.start_time.strftime("%Y/%m/%d") if metadata.start_time else "unknown"
        storage_dir = self.base_path / date_path
        storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename
        filename = f"{recording_id}.{metadata.format.value}"
        file_path = storage_dir / filename
        
        # Write file
        with open(file_path, 'wb') as f:
            f.write(file_data)
        
        # Calculate checksum
        checksum = hashlib.sha256(file_data).hexdigest()
        metadata.checksum = checksum
        metadata.file_size = len(file_data)
        
        logger.info(f"Stored recording locally: {file_path}")
        return str(file_path.relative_to(self.base_path))
    
    async def _store_s3(
        self,
        recording_id: str,
        file_data: bytes,
        metadata: RecordingMetadata
    ) -> str:
        """Store recording in S3."""
        # This would implement S3 storage
        # For now, just return a placeholder
        s3_key = f"recordings/{recording_id}.{metadata.format.value}"
        # TODO: Implement actual S3 upload
        logger.info(f"Would store recording in S3: {s3_key}")
        return s3_key
    
    async def retrieve_recording(self, file_path: str) -> Optional[bytes]:
        """Retrieve recording file data."""
        try:
            if self.storage_type == StorageType.LOCAL:
                full_path = self.base_path / file_path
                if full_path.exists():
                    with open(full_path, 'rb') as f:
                        return f.read()
            
            # Add other storage types
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving recording {file_path}: {e}")
            return None
    
    async def delete_recording(self, file_path: str) -> bool:
        """Delete recording file."""
        try:
            if self.storage_type == StorageType.LOCAL:
                full_path = self.base_path / file_path
                if full_path.exists():
                    full_path.unlink()
                    logger.info(f"Deleted recording: {full_path}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error deleting recording {file_path}: {e}")
            return False
    
    def get_recording_url(self, file_path: str) -> Optional[str]:
        """Get URL for accessing recording."""
        if self.storage_type == StorageType.LOCAL:
            # Return relative URL for local files
            return f"/media/recordings/{file_path}"
        elif self.storage_type == StorageType.S3:
            # Return S3 URL
            return f"https://{self.bucket_name}.s3.{self.aws_region}.amazonaws.com/{file_path}"
        
        return None


class CallRecordingManager:
    """
    Call Recording Manager for PyDialer.
    
    Manages call recording lifecycle, storage, and metadata.
    """
    
    def __init__(self, config: Optional[RecordingConfig] = None):
        self.config = config or self._load_default_config()
        self.active_recordings: Dict[str, RecordingMetadata] = {}
        self.completed_recordings: Dict[str, RecordingMetadata] = {}
        
        # Initialize storage
        storage_config = {
            'base_path': getattr(settings, 'RECORDING_STORAGE_PATH', 'media/recordings'),
            'bucket_name': getattr(settings, 'RECORDING_S3_BUCKET', 'call-recordings'),
            'aws_region': getattr(settings, 'AWS_REGION', 'us-east-1')
        }
        self.storage = RecordingStorage(self.config.storage_type, storage_config)
        
        logger.info("Call recording manager initialized")
    
    def _load_default_config(self) -> RecordingConfig:
        """Load default recording configuration from settings."""
        return RecordingConfig(
            enabled=getattr(settings, 'RECORDING_ENABLED', True),
            auto_record=getattr(settings, 'RECORDING_AUTO_RECORD', False),
            format=RecordingFormat(getattr(settings, 'RECORDING_FORMAT', 'wav')),
            sample_rate=getattr(settings, 'RECORDING_SAMPLE_RATE', 8000),
            channels=getattr(settings, 'RECORDING_CHANNELS', 1),
            max_duration=getattr(settings, 'RECORDING_MAX_DURATION', 7200),
            storage_type=StorageType(getattr(settings, 'RECORDING_STORAGE_TYPE', 'local')),
            storage_path=getattr(settings, 'RECORDING_STORAGE_PATH', 'recordings'),
            retention_days=getattr(settings, 'RECORDING_RETENTION_DAYS', 365),
            consent_required=getattr(settings, 'RECORDING_CONSENT_REQUIRED', True),
        )
    
    async def start_recording(
        self,
        call_id: str,
        agent_id: Optional[str] = None,
        trigger: RecordingTrigger = RecordingTrigger.MANUAL,
        **kwargs
    ) -> Optional[str]:
        """Start recording a call."""
        if not self.config.enabled:
            logger.warning("Recording is disabled")
            return None
        
        # Check if already recording
        if call_id in self.active_recordings:
            logger.warning(f"Call {call_id} is already being recorded")
            return self.active_recordings[call_id].recording_id
        
        # Generate recording ID
        recording_id = str(uuid.uuid4())
        
        # Create metadata
        metadata = RecordingMetadata(
            recording_id=recording_id,
            call_id=call_id,
            agent_id=agent_id,
            start_time=timezone.now(),
            format=self.config.format,
            sample_rate=self.config.sample_rate,
            channels=self.config.channels,
            storage_type=self.config.storage_type,
            trigger=trigger,
            status=RecordingStatus.STARTING,
            **kwargs
        )
        
        # Set retention date
        if self.config.retention_days > 0:
            metadata.retention_date = timezone.now() + timedelta(days=self.config.retention_days)
        
        try:
            # Start actual recording via Asterisk
            success = await self._start_asterisk_recording(call_id, recording_id, metadata)
            
            if success:
                metadata.status = RecordingStatus.RECORDING
                self.active_recordings[call_id] = metadata
                
                # Notify via WebSocket
                await self._notify_recording_started(metadata)
                
                logger.info(f"Started recording for call {call_id} (ID: {recording_id})")
                return recording_id
            else:
                metadata.status = RecordingStatus.FAILED
                logger.error(f"Failed to start recording for call {call_id}")
                return None
                
        except Exception as e:
            metadata.status = RecordingStatus.FAILED
            logger.error(f"Error starting recording for call {call_id}: {e}")
            return None
    
    async def stop_recording(self, call_id: str) -> bool:
        """Stop recording a call."""
        if call_id not in self.active_recordings:
            logger.warning(f"No active recording found for call {call_id}")
            return False
        
        metadata = self.active_recordings[call_id]
        metadata.status = RecordingStatus.STOPPING
        
        try:
            # Stop actual recording via Asterisk
            success = await self._stop_asterisk_recording(call_id, metadata.recording_id)
            
            if success:
                metadata.end_time = timezone.now()
                metadata.status = RecordingStatus.COMPLETED
                
                # Move to completed recordings
                self.completed_recordings[metadata.recording_id] = metadata
                del self.active_recordings[call_id]
                
                # Process the recorded file
                await self._process_completed_recording(metadata)
                
                # Notify via WebSocket
                await self._notify_recording_stopped(metadata)
                
                logger.info(f"Stopped recording for call {call_id}")
                return True
            else:
                metadata.status = RecordingStatus.FAILED
                logger.error(f"Failed to stop recording for call {call_id}")
                return False
                
        except Exception as e:
            metadata.status = RecordingStatus.FAILED
            logger.error(f"Error stopping recording for call {call_id}: {e}")
            return False
    
    async def pause_recording(self, call_id: str) -> bool:
        """Pause recording a call."""
        if call_id not in self.active_recordings:
            return False
        
        metadata = self.active_recordings[call_id]
        if metadata.status != RecordingStatus.RECORDING:
            return False
        
        try:
            success = await self._pause_asterisk_recording(call_id, metadata.recording_id)
            if success:
                metadata.status = RecordingStatus.PAUSED
                await self._notify_recording_paused(metadata)
                logger.info(f"Paused recording for call {call_id}")
            return success
            
        except Exception as e:
            logger.error(f"Error pausing recording for call {call_id}: {e}")
            return False
    
    async def resume_recording(self, call_id: str) -> bool:
        """Resume recording a call."""
        if call_id not in self.active_recordings:
            return False
        
        metadata = self.active_recordings[call_id]
        if metadata.status != RecordingStatus.PAUSED:
            return False
        
        try:
            success = await self._resume_asterisk_recording(call_id, metadata.recording_id)
            if success:
                metadata.status = RecordingStatus.RECORDING
                await self._notify_recording_resumed(metadata)
                logger.info(f"Resumed recording for call {call_id}")
            return success
            
        except Exception as e:
            logger.error(f"Error resuming recording for call {call_id}: {e}")
            return False
    
    async def _start_asterisk_recording(
        self,
        call_id: str,
        recording_id: str,
        metadata: RecordingMetadata
    ) -> bool:
        """Start recording via Asterisk ARI."""
        try:
            # This would integrate with the ARI controller
            # For now, simulate success
            logger.info(f"Starting Asterisk recording for call {call_id}")
            
            # TODO: Implement actual ARI recording start
            # Example ARI call:
            # POST /channels/{channelId}/record
            # {
            #   "name": recording_id,
            #   "format": metadata.format.value,
            #   "maxDurationSeconds": self.config.max_duration,
            #   "maxSilenceSeconds": 30,
            #   "terminateOn": "#"
            # }
            
            return True
            
        except Exception as e:
            logger.error(f"Error starting Asterisk recording: {e}")
            return False
    
    async def _stop_asterisk_recording(self, call_id: str, recording_id: str) -> bool:
        """Stop recording via Asterisk ARI."""
        try:
            logger.info(f"Stopping Asterisk recording {recording_id} for call {call_id}")
            
            # TODO: Implement actual ARI recording stop
            # Example ARI call:
            # DELETE /recordings/live/{recordingName}
            
            return True
            
        except Exception as e:
            logger.error(f"Error stopping Asterisk recording: {e}")
            return False
    
    async def _pause_asterisk_recording(self, call_id: str, recording_id: str) -> bool:
        """Pause recording via Asterisk ARI."""
        try:
            logger.info(f"Pausing Asterisk recording {recording_id}")
            
            # TODO: Implement actual ARI recording pause
            # POST /recordings/live/{recordingName}/pause
            
            return True
            
        except Exception as e:
            logger.error(f"Error pausing Asterisk recording: {e}")
            return False
    
    async def _resume_asterisk_recording(self, call_id: str, recording_id: str) -> bool:
        """Resume recording via Asterisk ARI."""
        try:
            logger.info(f"Resuming Asterisk recording {recording_id}")
            
            # TODO: Implement actual ARI recording resume
            # DELETE /recordings/live/{recordingName}/pause
            
            return True
            
        except Exception as e:
            logger.error(f"Error resuming Asterisk recording: {e}")
            return False
    
    async def _process_completed_recording(self, metadata: RecordingMetadata) -> None:
        """Process a completed recording."""
        try:
            # Get recording file from Asterisk
            recording_data = await self._get_asterisk_recording_file(metadata.recording_id)
            
            if recording_data:
                # Store in configured storage
                file_path = await self.storage.store_recording(
                    metadata.recording_id,
                    recording_data,
                    metadata
                )
                
                metadata.file_path = file_path
                metadata.url = self.storage.get_recording_url(file_path)
                
                # Save metadata to database
                await self._save_recording_metadata(metadata)
                
                logger.info(f"Processed recording {metadata.recording_id}")
            else:
                logger.error(f"Could not retrieve recording file for {metadata.recording_id}")
                
        except Exception as e:
            logger.error(f"Error processing recording {metadata.recording_id}: {e}")
    
    async def _get_asterisk_recording_file(self, recording_id: str) -> Optional[bytes]:
        """Get recording file from Asterisk."""
        try:
            # TODO: Implement actual ARI recording file retrieval
            # GET /recordings/stored/{recordingName}/file
            
            # For now, return dummy data
            dummy_data = b"RIFF\x00\x00\x00\x00WAVEfmt \x00\x00\x00\x00data\x00\x00\x00\x00"
            return dummy_data
            
        except Exception as e:
            logger.error(f"Error getting Asterisk recording file: {e}")
            return None
    
    async def _save_recording_metadata(self, metadata: RecordingMetadata) -> None:
        """Save recording metadata to database."""
        try:
            # TODO: Save to Django models
            # This would save to a Recording model
            logger.info(f"Saved metadata for recording {metadata.recording_id}")
            
        except Exception as e:
            logger.error(f"Error saving recording metadata: {e}")
    
    async def _notify_recording_started(self, metadata: RecordingMetadata) -> None:
        """Notify about recording start via WebSocket."""
        await self._send_recording_notification("recording_started", metadata)
    
    async def _notify_recording_stopped(self, metadata: RecordingMetadata) -> None:
        """Notify about recording stop via WebSocket."""
        await self._send_recording_notification("recording_stopped", metadata)
    
    async def _notify_recording_paused(self, metadata: RecordingMetadata) -> None:
        """Notify about recording pause via WebSocket."""
        await self._send_recording_notification("recording_paused", metadata)
    
    async def _notify_recording_resumed(self, metadata: RecordingMetadata) -> None:
        """Notify about recording resume via WebSocket."""
        await self._send_recording_notification("recording_resumed", metadata)
    
    async def _send_recording_notification(self, event_type: str, metadata: RecordingMetadata) -> None:
        """Send recording notification via WebSocket."""
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                # Notify agent
                if metadata.agent_id:
                    await channel_layer.group_send(
                        f"agent_{metadata.agent_id}",
                        {
                            'type': event_type,
                            'recording_id': metadata.recording_id,
                            'call_id': metadata.call_id,
                            'status': metadata.status.value,
                            'duration': metadata.calculated_duration
                        }
                    )
                
                # Notify supervisors
                await channel_layer.group_send(
                    "supervisors",
                    {
                        'type': event_type,
                        'recording_id': metadata.recording_id,
                        'call_id': metadata.call_id,
                        'agent_id': metadata.agent_id,
                        'status': metadata.status.value,
                        'duration': metadata.calculated_duration
                    }
                )
                
        except Exception as e:
            logger.error(f"Error sending recording notification: {e}")
    
    def get_recording_metadata(self, recording_id: str) -> Optional[RecordingMetadata]:
        """Get recording metadata by ID."""
        # Check active recordings
        for metadata in self.active_recordings.values():
            if metadata.recording_id == recording_id:
                return metadata
        
        # Check completed recordings
        return self.completed_recordings.get(recording_id)
    
    def get_call_recordings(self, call_id: str) -> List[RecordingMetadata]:
        """Get all recordings for a specific call."""
        recordings = []
        
        # Check active recordings
        if call_id in self.active_recordings:
            recordings.append(self.active_recordings[call_id])
        
        # Check completed recordings
        for metadata in self.completed_recordings.values():
            if metadata.call_id == call_id:
                recordings.append(metadata)
        
        return recordings
    
    def get_agent_recordings(self, agent_id: str) -> List[RecordingMetadata]:
        """Get all recordings for a specific agent."""
        recordings = []
        
        # Check active recordings
        for metadata in self.active_recordings.values():
            if metadata.agent_id == agent_id:
                recordings.append(metadata)
        
        # Check completed recordings
        for metadata in self.completed_recordings.values():
            if metadata.agent_id == agent_id:
                recordings.append(metadata)
        
        return recordings
    
    async def cleanup_expired_recordings(self) -> int:
        """Clean up expired recordings based on retention policy."""
        cleaned_count = 0
        current_time = timezone.now()
        
        expired_recordings = [
            metadata for metadata in self.completed_recordings.values()
            if (metadata.retention_date and 
                metadata.retention_date < current_time and 
                metadata.status == RecordingStatus.COMPLETED)
        ]
        
        for metadata in expired_recordings:
            try:
                # Delete file from storage
                if metadata.file_path:
                    await self.storage.delete_recording(metadata.file_path)
                
                # Remove from memory
                del self.completed_recordings[metadata.recording_id]
                
                # TODO: Mark as deleted in database
                cleaned_count += 1
                logger.info(f"Cleaned up expired recording {metadata.recording_id}")
                
            except Exception as e:
                logger.error(f"Error cleaning up recording {metadata.recording_id}: {e}")
        
        return cleaned_count


# Global recording manager instance
_recording_manager: Optional[CallRecordingManager] = None


def get_recording_manager() -> CallRecordingManager:
    """Get or create global recording manager instance."""
    global _recording_manager
    if _recording_manager is None:
        _recording_manager = CallRecordingManager()
    return _recording_manager


async def cleanup_recording_manager() -> None:
    """Clean up global recording manager instance."""
    global _recording_manager
    if _recording_manager:
        # Cleanup any active recordings
        for call_id in list(_recording_manager.active_recordings.keys()):
            await _recording_manager.stop_recording(call_id)
        _recording_manager = None
